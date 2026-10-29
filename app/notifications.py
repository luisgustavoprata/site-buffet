"""Notificações para os clientes: as mensagens e a programação em horários sorteados.

Todo dia o site sorteia `push_per_day` horários dentro da janela (por padrão das 07:00 às
19:00, horário de Brasília) e, em cada um, envia uma mensagem do catálogo para os aparelhos
dos clientes que ativaram as notificações. Fora da janela nada é enviado, nem atrasado.
"""

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import AppSecret, PushDevice, PushPlan, Role, SiteContent, User, utcnow
from app.webpush import Device, Vapid

log = logging.getLogger(__name__)

Sender = Callable[[Device, dict, Vapid], int]


@dataclass(frozen=True)
class Message:
    key: str
    title: str
    body: str
    url: str = "/"
    period: str = ""  # "manha" (antes do meio-dia), "tarde" ou "" (qualquer hora)
    tone: str = "convite"  # "convite" (tranquila) ou "divertida"


# {nome}: primeiro nome do cliente · {empresa}: nome do buffet · {chef}: primeiro nome da chef
MESSAGES = [
    # Divertidas, com trocadilhos, puxando para uma festa
    Message(
        "vontade-festa",
        "Bateu aquela vontade de festa? 🎉",
        "A gente corta a ansiedade em cubinhos e serve um cardápio sob medida. Bora planejar?",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "forno",
        "Ideia saindo do forno 🔥",
        "Sua próxima festa pode estar mais perto do que parece. Que tal tirar do papel?",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "idade-bolo",
        "Aniversário chegando? 🎂",
        "A idade a gente não conta para ninguém. Já o bolo… esse a gente capricha.",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "doce-salgado",
        "Docinho ou salgadinho?",
        "Por que escolher? Numa festa da {empresa} cabem os dois. 😋",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "canape",
        "A vida é curta para canapé sem graça",
        "Deixa a comida com a gente e aproveite a festa com quem você ama.",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "brunoise",
        "O corte mais caprichado da cozinha 🔪",
        "Se a gente pica legumes em cubinhos de 3 mm, imagine o cuidado com a sua festa.",
        "/historia",
        tone="divertida",
    ),
    Message(
        "plano",
        "Plano infalível em 3 passos",
        "1. Escolha a data. 2. Chame quem você ama. 3. Deixe o cardápio com a gente. ✨",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "fome",
        "Fome de comemorar? 🍽️",
        "A gente tem o cardápio, você tem o motivo. Combinação perfeita.",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "sim",
        'O "sim" é com vocês 💍',
        "O jantar inesquecível pode ficar com a gente. Vamos conversar sobre o grande dia?",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "reuniao",
        "Reunião sem graça? ☕",
        "Um coffee break caprichado muda o humor de qualquer equipe. Fale com a gente.",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "mesa-posta",
        "{nome}, a mesa está posta 🥂",
        "Só falta a sua ideia de festa. Conta pra gente?",
        "/orcamento",
        tone="divertida",
    ),
    Message(
        "sobremesa",
        "Pensou em sobremesa?",
        "A gente também. Na verdade, a gente pensa nisso o dia inteiro. 🍰",
        "/portfolio",
        tone="divertida",
    ),
    # Tranquilas, convidando a conhecer o buffet e ver as fotos
    Message(
        "bom-dia",
        "Bom dia, {nome} ☀️",
        "Que tal começar o dia se inspirando? Veja os eventos que já servimos.",
        "/portfolio",
        period="manha",
    ),
    Message(
        "cafe-tarde",
        "Uma pausa para o café ☕",
        "Um cafezinho combina com uma olhada no nosso portfólio. Fique à vontade.",
        "/portfolio",
        period="tarde",
    ),
    Message(
        "inspiracao",
        "Inspiração para a sua festa",
        "Mesas, bolos e decorações de eventos reais. Dê uma olhada com calma.",
        "/portfolio",
    ),
    Message(
        "historia",
        "Conheça a nossa história",
        "Descubra por que escolhemos o nome Brunoise e como cuidamos de cada detalhe.",
        "/historia",
    ),
    Message(
        "detalhes",
        "Cada detalhe importa",
        "Do primeiro canapé ao último cafezinho. Venha ver como trabalhamos.",
        "/sobre",
    ),
    Message(
        "com-calma",
        "Planejar com calma é melhor",
        "Quanto antes a gente conversa, mais tranquila fica a sua festa. Sem compromisso.",
        "/orcamento",
    ),
    Message(
        "chef",
        "Estamos por aqui",
        "Dúvidas sobre cardápio, data ou convidados? É só chamar a {chef} pelo site.",
        "/orcamento",
    ),
    Message(
        "olhos",
        "Uma mesa bonita também alimenta",
        "Veja algumas das mesas que montamos e imagine a sua.",
        "/portfolio",
    ),
    Message(
        "obrigado",
        "Que bom ter você aqui 💛",
        "Obrigado por acompanhar a {empresa}. Passe para ver nossos eventos quando quiser.",
        "/portfolio",
    ),
    Message(
        "boa-tarde",
        "Boa tarde, {nome}!",
        "Separe um minutinho para conhecer os eventos que preparamos com carinho.",
        "/portfolio",
        period="tarde",
    ),
]
BY_KEY = {m.key: m for m in MESSAGES}

TEST_MESSAGE = Message(
    "teste",
    "Notificações ativadas ✅",
    "Pronto, {nome}! É assim que as novidades da {empresa} vão chegar para você.",
    "/portfolio",
)


def render(message: Message, user: User | None, site: SiteContent | None) -> dict:
    business = (site.business_name if site else "") or "o buffet"
    chef = ((site.owner_name if site else "") or "equipe").split()[0]
    name = user.name.split()[0] if user and user.name else "olá"
    values = {"nome": name, "empresa": business, "chef": chef}
    return {
        "title": message.title.format(**values),
        "body": message.body.format(**values),
        "url": "/" if message.url == "/" else f"/#{message.url}",
        "tag": "brunoise-novidades",
    }


# ---------- Chave do site ----------


def get_vapid(db: Session, settings: Settings) -> Vapid:
    if settings.vapid_private_key:
        return Vapid.from_private(settings.vapid_private_key, settings.push_subject)
    stored = db.get(AppSecret, "vapid_private_key")
    if stored is None:
        vapid = Vapid.generate(settings.push_subject)
        db.add(AppSecret(name="vapid_private_key", value=vapid.private_b64))
        db.flush()
        return vapid
    return Vapid.from_private(stored.value, settings.push_subject)


# ---------- Programação do dia ----------


def local_now(settings: Settings, now: datetime) -> datetime:
    return now.astimezone(ZoneInfo(settings.push_timezone))


def in_window(settings: Settings, local: datetime) -> bool:
    return settings.push_start_hour <= local.hour < settings.push_end_hour


def _choose(rng: random.Random, recent: list[str], period: str) -> Message:
    fits = [m for m in MESSAGES if not m.period or m.period == period]
    fresh = [m for m in fits if m.key not in recent] or fits
    return rng.choice(fresh)


def ensure_plan(db: Session, settings: Settings, now: datetime, rng: random.Random) -> None:
    """Sorteia os horários de hoje, se ainda não foram sorteados."""
    if settings.push_per_day <= 0:
        return
    local = local_now(settings, now)
    day = local.date()
    if db.scalar(select(PushPlan.id).where(PushPlan.day == day).limit(1)) is not None:
        return
    tz = ZoneInfo(settings.push_timezone)
    opens = datetime.combine(day, time(settings.push_start_hour), tz)
    closes = datetime.combine(day, time(settings.push_end_hour), tz) - timedelta(minutes=10)
    start = max(opens, local + timedelta(minutes=5))
    if start >= closes:
        return  # o dia já acabou para notificações; amanhã sorteia de novo
    # Divide o tempo que resta em partes iguais e sorteia um horário em cada uma: aleatório,
    # mas sem duas notificações coladas.
    span = (closes - start) / settings.push_per_day
    recent = list(db.scalars(select(PushPlan.message_key).order_by(PushPlan.id.desc()).limit(12)))
    for n in range(settings.push_per_day):
        at = start + span * (n + rng.uniform(0.15, 0.85))  # folga entre uma e outra
        at = at.replace(second=0, microsecond=0)
        message = _choose(rng, recent, "manha" if at.hour < 12 else "tarde")
        recent.append(message.key)
        db.add(PushPlan(day=day, send_at=at.astimezone(ZoneInfo("UTC")), message_key=message.key))
    db.flush()


def deliver(
    db: Session, devices: list[PushDevice], message: Message, vapid: Vapid, sender: Sender
) -> int:
    site = db.get(SiteContent, 1)
    sent = 0
    for device in devices:
        payload = render(message, device.user, site)
        status = sender(Device(device.endpoint, device.p256dh, device.auth), payload, vapid)
        if status in (404, 410):
            db.delete(device)  # a pessoa desativou ou o navegador trocou o endereço
        elif 200 <= status < 300:
            device.last_sent_at = utcnow()
            sent += 1
        else:
            log.warning("Notificação recusada (%s) por %s", status, device.endpoint[:60])
    db.flush()
    return sent


def run_due(
    db: Session,
    settings: Settings,
    now: datetime,
    sender: Sender,
    rng: random.Random | None = None,
) -> int:
    """Envia o que estiver na hora. Chamado a cada minuto pelo servidor."""
    ensure_plan(db, settings, now, rng or random.Random())
    due = list(
        db.scalars(
            select(PushPlan)
            .where(PushPlan.status == "programada", PushPlan.send_at <= now)
            .order_by(PushPlan.send_at)
        )
    )
    if not due:
        return 0
    # Fora da janela (ex.: o servidor estava parado) nada sai atrasado. Se várias ficaram
    # para trás, só a mais recente é enviada, para não chegar tudo de uma vez.
    allowed = in_window(settings, local_now(settings, now))
    keep = due[-1] if allowed else None
    for plan in due:
        if plan is not keep:
            plan.status, plan.done_at = "pulada", now
    if keep is None:
        return 0
    claimed = db.execute(
        update(PushPlan)
        .where(PushPlan.id == keep.id, PushPlan.status == "programada")
        .values(status="enviando")
        .execution_options(synchronize_session=False)
    ).rowcount
    if not claimed:
        return 0  # outro processo do servidor já pegou esta
    devices = list(db.scalars(select(PushDevice).join(User).where(User.role == Role.CLIENT)))
    message = BY_KEY.get(keep.message_key) or MESSAGES[0]
    sent = deliver(db, devices, message, get_vapid(db, settings), sender)
    db.execute(
        update(PushPlan)
        .where(PushPlan.id == keep.id)
        .values(status="enviada", devices=sent, done_at=now)
        .execution_options(synchronize_session=False)
    )
    db.expire(keep)
    return sent


def forget_device(db: Session, endpoint: str, user: User) -> None:
    db.execute(
        delete(PushDevice).where(PushDevice.endpoint == endpoint, PushDevice.user_id == user.id)
    )
