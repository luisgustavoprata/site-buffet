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


def password_stamp(password_hash: str) -> str:
    """Marca da senha atual dentro do token: trocar a senha desconecta os outros aparelhos."""
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_access_token(user_id: int, secret: str, minutes: int, stamp: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "pwd": stamp,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def read_access_token(token: str, secret: str) -> tuple[int, str] | None:
    """Devolve (id do usuário, marca da senha), ou None se o token for inválido ou vencido."""
    try:
        payload = jwt.decode(
            token, secret, algorithms=[ALGORITHM], options={"require": ["exp", "pwd"]}
        )
        return int(payload["sub"]), str(payload["pwd"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
