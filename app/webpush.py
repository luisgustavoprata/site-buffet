"""Envio de notificações Web Push, sem serviço pago: o navegador entrega na barra do sistema.

Padrões usados:
- RFC 8291: a mensagem vai cifrada (ECDH P-256 + HKDF + AES-128-GCM, "aes128gcm"), e só o
  aparelho de quem ativou consegue abrir.
- RFC 8292 (VAPID): o site assina cada envio com a sua chave, e o serviço de push do navegador
  (Google, Mozilla, Apple, Microsoft) confere que veio mesmo deste site.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

RECORD_SIZE = 4096

# Só estes serviços recebem envios: impede que alguém cadastre um endereço qualquer e faça o
# servidor do buffet mandar requisições para lá.
PUSH_SERVICE_HOSTS = (
    "fcm.googleapis.com",  # Chrome, Edge (Android) e outros baseados no Chromium
    "android.googleapis.com",
    "updates.push.services.mozilla.com",  # Firefox
    "push.services.mozilla.com",
    "web.push.apple.com",  # Safari (Mac e iPhone/iPad)
    "push.apple.com",
    "notify.windows.com",  # Edge no Windows
)


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def is_push_service(endpoint: str) -> bool:
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    allowed = any(host == h or host.endswith("." + h) for h in PUSH_SERVICE_HOSTS)
    return parts.scheme == "https" and allowed


def _public_bytes(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def _hkdf(salt: bytes, info: bytes, length: int, key_material: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(key_material)


def encrypt(
    plaintext: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    *,
    sender_key: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """Cifra a mensagem para um aparelho (RFC 8291). `sender_key` e `salt` só nos testes."""
    sender_key = sender_key or ec.generate_private_key(ec.SECP256R1())
    salt = salt or os.urandom(16)
    as_public = _public_bytes(sender_key)
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = sender_key.exchange(ec.ECDH(), peer)
    ikm = _hkdf(auth_secret, b"WebPush: info\x00" + ua_public + as_public, 32, shared)
    cek = _hkdf(salt, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(salt, b"Content-Encoding: nonce\x00", 12, ikm)
    if len(plaintext) + 1 + 16 > RECORD_SIZE - 86:
        raise ValueError("Mensagem grande demais para uma notificação.")
    ciphertext = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)  # 0x02: último bloco
    header = salt + RECORD_SIZE.to_bytes(4, "big") + bytes([len(as_public)]) + as_public
    return header + ciphertext


@dataclass(frozen=True)
class Vapid:
    """A chave do site para assinar os envios."""

    private_key: ec.EllipticCurvePrivateKey
    subject: str  # contato do site (mailto: ou https:), exigido pelos serviços de push

    @classmethod
    def generate(cls, subject: str) -> "Vapid":
        return cls(ec.generate_private_key(ec.SECP256R1()), subject)

    @classmethod
    def from_private(cls, value: str, subject: str) -> "Vapid":
        number = int.from_bytes(unb64url(value), "big")
        return cls(ec.derive_private_key(number, ec.SECP256R1()), subject)

    @property
    def private_b64(self) -> str:
        return b64url(self.private_key.private_numbers().private_value.to_bytes(32, "big"))

    @property
    def public_b64(self) -> str:
        """Vai para o navegador (applicationServerKey) ao ativar as notificações."""
        return b64url(_public_bytes(self.private_key))

    def authorization(self, endpoint: str, now: float | None = None) -> str:
        parts = urlsplit(endpoint)
        claims = {
            "aud": f"{parts.scheme}://{parts.netloc}",
            "exp": int((now or time.time()) + 12 * 3600),
            "sub": self.subject,
        }
        token = jwt.encode(claims, self.private_key, algorithm="ES256")
        return f"vapid t={token}, k={self.public_b64}"


@dataclass(frozen=True)
class Device:
    endpoint: str
    p256dh: str
    auth: str


def send(device: Device, payload: dict, vapid: Vapid, ttl: int = 12 * 3600) -> int:
    """Envia e devolve o código HTTP do serviço de push (201 = aceito; 404/410 = desativado)."""
    if not is_push_service(device.endpoint):
        return 410  # endereço que não é de um serviço de push: tratado como desativado
    body = encrypt(
        json.dumps(payload, ensure_ascii=False).encode(),
        unb64url(device.p256dh),
        unb64url(device.auth),
    )
    request = urllib.request.Request(
        device.endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": vapid.authorization(device.endpoint),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(ttl),
            "Urgency": "low",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except OSError:
        return 0  # sem resposta: tenta de novo numa próxima vez
