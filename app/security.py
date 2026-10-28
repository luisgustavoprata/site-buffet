"""Senhas (PBKDF2, da biblioteca padrão) e tokens de acesso (JWT)."""

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

ALGORITHM = "HS256"


def hash_password(password: str, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "$".join(
        [
            "pbkdf2_sha256",
            str(iterations),
            base64.b64encode(salt).decode(),
            base64.b64encode(digest).decode(),
        ]
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), base64.b64decode(salt), int(iterations)
    )
    # Comparação em tempo constante: não revela quantos caracteres "acertaram".
    return hmac.compare_digest(candidate, base64.b64decode(digest))


def create_access_token(user_id: int, secret: str, minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def read_access_token(token: str, secret: str) -> int | None:
    """Devolve o id do usuário, ou None se o token for inválido ou estiver vencido."""
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"require": ["exp"]})
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
