"""Barreira de segurança por IP: VPN/datacenter, acessos de fora do Brasil e excesso de pedidos.

Regras (veja `IpGuard.decide`):
- **Brasil**: acesso livre, só com um limite alto contra enxurrada (vários clientes podem
  dividir o mesmo IP da operadora, o CGNAT, então o limite é generoso).
- **Fora do Brasil**: pode ver o site, mas com limite baixo; para entrar, se cadastrar, pedir
  orçamento, comentar ou mandar mensagens, precisa passar pelo desafio de segurança.
- **VPN ou datacenter**: tudo passa pelo desafio antes.
- **Abuso** (vindo de fora do Brasil ou de VPN): passar do limite depois de liberado, errar o
  desafio várias vezes ou errar senhas marca o IP por 24 horas. Marcado, o desafio nunca é
  aprovado: a pessoa fica refazendo testes sem fim. IPs do Brasil nunca são marcados.

O desafio é uma "prova de trabalho": o navegador calcula por 1 a 2 segundos um número que o
servidor confere em microssegundos. Para uma pessoa é uma espera curta; para quem dispara
milhares de pedidos, fica caro. Tudo em memória, num processo só (o plano do Render).
"""

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import secrets
import socket
import threading
import time
import urllib.request
from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# Blocos de IP do Brasil (registro oficial da LACNIC, via ipverse/rir-ip, domínio público CC0).
COUNTRY_URLS = (
    "https://raw.githubusercontent.com/ipverse/rir-ip/master/country/br/ipv4-aggregated.txt",
    "https://raw.githubusercontent.com/ipverse/rir-ip/master/country/br/ipv6-aggregated.txt",
)
# VPNs e datacenters (X4BNet/lists_vpn): baixada ao iniciar e atualizada todo dia.
VPN_URLS = (
    "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/datacenter/ipv4.txt",
    "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/datacenter/ipv6.txt",
)

BRAZIL, FOREIGN, VPN, LOCAL = "br", "fora", "vpn", "local"
WINDOW = 300  # segundos da janela de contagem
FLAG_SECONDS = 24 * 3600
PASS_SECONDS = {VPN: 6 * 3600, FOREIGN: 24 * 3600}
LIMITS = {BRAZIL: 900, LOCAL: 900, FOREIGN: 150, VPN: 300}  # pedidos por janela, por IP
BITS = 20  # dificuldade normal (~1 milhão de tentativas, 1 a 2 s no celular)
COOKIE = "seguranca"


class IntervalSet:
    """Conjunto de faixas de IP com busca binária: milhares de faixas, consulta instantânea."""

    def __init__(self, networks: Iterable[str] = ()):
        ranges: list[tuple[int, int]] = []
        for line in networks:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                net = ipaddress.ip_network(line, strict=False)
            except ValueError:
                continue
            # IPv4 e IPv6 em faixas separadas do mesmo espaço numérico.
            offset = 0 if net.version == 4 else 1 << 32
            ranges.append((int(net.network_address) + offset, int(net.broadcast_address) + offset))
        ranges.sort()
        self.starts: list[int] = []
        self.ends: list[int] = []
        for start, end in ranges:
            if self.ends and start <= self.ends[-1] + 1:
                self.ends[-1] = max(self.ends[-1], end)
            else:
                self.starts.append(start)
                self.ends.append(end)

    def __len__(self) -> int:
        return len(self.starts)

    def __contains__(self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        value = int(ip) + (0 if ip.version == 4 else 1 << 32)
        i = bisect_right(self.starts, value) - 1
        return i >= 0 and self.ends[i] >= value


def _read_lines(source: str) -> list[str]:
    if source.startswith("https://"):
        request = urllib.request.Request(source, headers={"User-Agent": "site-buffet/1.0"})
        # Só chega aqui endereço https:// (conferido acima).
        with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310
            return response.read().decode().splitlines()
    return Path(source).read_text().splitlines()


def parse_ip(value: str | None) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        ip = ipaddress.ip_address((value or "").strip())
    except ValueError:
        return None
    if ip.version == 6 and ip.ipv4_mapped:
        return ip.ipv4_mapped
    return ip


def rate_key(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str:
    """No IPv6, cada pessoa recebe um bloco /64 inteiro: conta o bloco, não o endereço."""
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


@dataclass(frozen=True)
class Decision:
    action: str  # "ok", "challenge" ou "slow_down"
    kind: str  # br, fora, vpn ou local


# Robôs de busca de verdade (confirmados pelo DNS reverso): o site continua no Google.
SEARCH_BOTS = {
    "googlebot": (".googlebot.com", ".google.com", ".googleusercontent.com"),
    "bingbot": (".search.msn.com",),
    "applebot": (".applebot.apple.com",),
    "duckduckbot": (".duckduckgo.com",),
}
# Prévia de link (WhatsApp, Instagram, Telegram...): só a página inicial, que não tem dados.
PREVIEW_BOTS = (
    "facebookexternalhit",
    "whatsapp",
    "telegrambot",
    "twitterbot",
    "linkedinbot",
    "slackbot",
    "discordbot",
    "pinterest",
    "skypeuripreview",
)


class IpGuard:
    def __init__(self, secret: str, *, clock=time.time):
        self.key = hashlib.sha256(f"ipguard|{secret}".encode()).digest()
        self.clock = clock
        self.country = IntervalSet()
        self.vpn = IntervalSet()
        self._lock = threading.Lock()
        self._hits: dict[str, tuple[int, int]] = {}  # chave -> (janela, contagem)
        self._flags: dict[str, float] = {}  # chave -> marcado até
        self._strikes: dict[str, tuple[int, int]] = {}
        self._used: dict[str, float] = {}  # desafios já usados
        self._bots: dict[str, tuple[bool, float]] = {}

    # ---------- listas ----------

    def load(self, country: Iterable[str] = (), vpn: Iterable[str] = ()) -> None:
        if country:
            self.country = IntervalSet(country)
        if vpn:
            self.vpn = IntervalSet(vpn)

    def load_bundled(self) -> None:
        files = sorted(DATA_DIR.glob("br-ipv*.txt"))
        lines = [line for f in files for line in f.read_text().splitlines()]
        self.load(country=lines)

    def refresh(self, country_sources=COUNTRY_URLS, vpn_sources=VPN_URLS) -> None:
        """Baixa as listas atualizadas. Se falhar, continua com as que já tem."""
        for name, sources in (("country", country_sources), ("vpn", vpn_sources)):
            try:
                lines = [line for src in sources for line in _read_lines(src)]
            except (OSError, ValueError) as exc:
                log.warning("Lista de IPs (%s) não atualizada: %s", name, exc)
                continue
            if len(lines) > 100:  # lista vazia ou cortada não substitui a atual
                self.load(**{name: lines})
                log.info("Lista de IPs (%s): %d faixas", name, len(getattr(self, name)))

    # ---------- classificação ----------

    def classify(self, ip) -> str:
        if ip is None:
            return FOREIGN
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return LOCAL
        if len(self.vpn) and ip in self.vpn:
            return VPN
        if not len(self.country) or ip in self.country:
            return BRAZIL  # sem a lista do Brasil carregada, não barra ninguém
        return FOREIGN

    def is_flagged(self, key: str) -> bool:
        with self._lock:
            until = self._flags.get(key)
            if until and until < self.clock():
                del self._flags[key]
                return False
            return bool(until)

    def flag(self, key: str) -> None:
        with self._lock:
            self._flags[key] = self.clock() + FLAG_SECONDS
        log.warning("IP marcado por abuso: %s", key)

    def strike(self, ip, weight: int = 1) -> None:
        """Comportamento suspeito (senha errada, desafio errado): 5 em 5 minutos marcam."""
        if ip is None or self.classify(ip) in (BRAZIL, LOCAL):
            return
        key = rate_key(ip)
        window = int(self.clock() // WINDOW)
        with self._lock:
            w, count = self._strikes.get(key, (window, 0))
            count = (count if w == window else 0) + weight
            self._strikes[key] = (window, count)
        if count >= 5:
            self.flag(key)

    def _count(self, key: str) -> int:
        window = int(self.clock() // WINDOW)
        with self._lock:
            w, count = self._hits.get(key, (window, 0))
            count = (count if w == window else 0) + 1
            self._hits[key] = (window, count)
            if len(self._hits) > 50_000:  # limpeza de janelas antigas
                self._hits = {k: v for k, v in self._hits.items() if v[0] == window}
            return count

    def decide(self, ip, *, passed: bool, sensitive: bool) -> Decision:
        """`passed`: tem o cookie do desafio. `sensitive`: entrar, cadastrar, enviar algo."""
        kind = self.classify(ip)
        key = rate_key(ip) if ip else "?"
        if kind not in (BRAZIL, LOCAL) and self.is_flagged(key):
            return Decision("challenge", kind)
        over = self._count(key) > LIMITS[kind]
        if kind in (BRAZIL, LOCAL):
            return Decision("slow_down" if over else "ok", kind)
        if over:
            if passed:
                self.flag(key)  # liberado e mesmo assim em excesso: abuso
            return Decision("challenge", kind)
        if passed:
            return Decision("ok", kind)
        if kind == VPN or sensitive:
            return Decision("challenge", kind)
        return Decision("ok", kind)

    # ---------- robôs de busca ----------

    def is_search_bot(self, ip, user_agent: str) -> bool:
        agent = user_agent.lower()
        domains = next((d for bot, d in SEARCH_BOTS.items() if bot in agent), None)
        if not domains or ip is None:
            return False
        cached = self._bots.get(str(ip))
        if cached and cached[1] > self.clock():
            return cached[0]
        ok = False
        try:  # DNS reverso + confirmação: o nome aponta de volta para o mesmo IP
            host = socket.gethostbyaddr(str(ip))[0].lower()
            if host.endswith(domains):
                ok = str(ip) in {a[4][0] for a in socket.getaddrinfo(host, None)}
        except OSError:
            ok = False
        self._bots[str(ip)] = (ok, self.clock() + 86400)
        return ok

    @staticmethod
    def is_preview_bot(user_agent: str) -> bool:
        agent = user_agent.lower()
        return any(bot in agent for bot in PREVIEW_BOTS)

    # ---------- desafio (prova de trabalho) ----------

    def _sign(self, payload: dict) -> str:
        body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        mac = hmac.new(self.key, body, hashlib.sha256).hexdigest()[:32]
        return f"{body.decode()}.{mac}"

    def _open(self, token: str) -> dict | None:
        try:
            body, mac = token.rsplit(".", 1)
            expected = hmac.new(self.key, body.encode(), hashlib.sha256).hexdigest()[:32]
            if not hmac.compare_digest(mac, expected):
                return None
            return json.loads(base64.urlsafe_b64decode(body))
        except (ValueError, TypeError):
            return None

    def _ip_tag(self, ip) -> str:
        return hmac.new(self.key, rate_key(ip).encode(), hashlib.sha256).hexdigest()[:16]

    def new_challenge(self, ip) -> dict:
        key = rate_key(ip) if ip else "?"
        flagged = self.is_flagged(key)
        bits = BITS + (2 if flagged else 0)
        salt = secrets.token_hex(12)
        token = self._sign(
            {
                "s": salt,
                "b": bits,
                "e": int(self.clock()) + 300,
                "i": self._ip_tag(ip) if ip else "",
            }
        )
        return {"token": token, "salt": salt, "bits": bits}

    def verify(self, ip, token: str, nonce: str) -> str | None:
        """Confere a resposta. Devolve o cookie de liberação, ou None se não passou."""
        data = self._open(token)
        if not data or ip is None or len(nonce) > 32:
            self.strike(ip)
            return None
        now = self.clock()
        if data.get("e", 0) < now or data.get("i") != self._ip_tag(ip):
            return None  # vencido ou de outro IP: pede outro, sem punir
        digest = hashlib.sha256(f"{data['s']}:{nonce}".encode()).digest()
        if int.from_bytes(digest, "big") >> (256 - int(data["b"])) != 0:
            self.strike(ip)  # resposta inventada
            return None
        with self._lock:
            if data["s"] in self._used:
                return None
            self._used[data["s"]] = now + 600
            if len(self._used) > 20_000:
                self._used = {k: v for k, v in self._used.items() if v > now}
        if self.is_flagged(rate_key(ip)):
            return None  # marcado por abuso: o teste nunca é aprovado
        kind = self.classify(ip)
        seconds = PASS_SECONDS.get(kind, PASS_SECONDS[FOREIGN])
        return self._sign({"i": self._ip_tag(ip), "e": int(now) + seconds})

    def has_pass(self, ip, cookie: str | None) -> bool:
        if not cookie or ip is None:
            return False
        data = self._open(cookie)
        return bool(data and data.get("e", 0) > self.clock() and data.get("i") == self._ip_tag(ip))


def env_sources(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(v.strip() for v in value.split(",") if v.strip())
