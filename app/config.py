"""Configuração lida de variáveis de ambiente (veja `.env.example`)."""

import os
from dataclasses import dataclass

DEV_SECRET_KEY = "chave-de-desenvolvimento-troque-em-producao"


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "on"}


def normalize_database_url(url: str) -> str:
    """O Render entrega `postgres://`; o SQLAlchemy usa o driver psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url.removeprefix(prefix)
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./buffet.db"
    secret_key: str = DEV_SECRET_KEY
    token_minutes: int = 60 * 24 * 7  # uma semana: o cliente volta para ver a resposta
    timezone: str = "America/Sao_Paulo"
    seed_demo: bool = False
    # Conta da dona do buffet, criada (ou atualizada) ao iniciar o servidor.
    owner_email: str = ""
    owner_password: str = ""
    owner_name: str = "Administração"
    password_iterations: int = 600_000
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    max_upload_mb: int = 10
    environment: str = "development"
    # Notificações: quantas por dia (0 desliga) e a janela de horário (Brasília).
    push_per_day: int = 2
    push_start_hour: int = 7
    push_end_hour: int = 19  # nenhuma notificação a partir deste horário
    push_timezone: str = "America/Sao_Paulo"
    push_scheduler: bool = True  # verificação automática em segundo plano
    push_subject: str = "mailto:contato@brunoisegastronomia.com.br"
    vapid_private_key: str = ""  # vazio: o site gera uma e guarda no banco

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        settings = cls(
            database_url=normalize_database_url(env.get("DATABASE_URL") or cls.database_url),
            secret_key=env.get("SECRET_KEY") or DEV_SECRET_KEY,
            token_minutes=int(env.get("TOKEN_MINUTES") or cls.token_minutes),
            timezone=env.get("APP_TIMEZONE") or cls.timezone,
            seed_demo=_bool(env.get("SEED_DEMO"), False),
            owner_email=(env.get("OWNER_EMAIL") or "").strip().lower(),
            owner_password=env.get("OWNER_PASSWORD") or "",
            owner_name=env.get("OWNER_NAME") or cls.owner_name,
            password_iterations=int(env.get("PASSWORD_ITERATIONS") or 600_000),
            login_max_attempts=int(env.get("LOGIN_MAX_ATTEMPTS") or 5),
            login_window_seconds=int(env.get("LOGIN_WINDOW_SECONDS") or 300),
            max_upload_mb=int(env.get("MAX_UPLOAD_MB") or 10),
            environment=env.get("ENVIRONMENT") or "development",
            push_per_day=int(env.get("PUSH_PER_DAY") or cls.push_per_day),
            push_start_hour=int(env.get("PUSH_START_HOUR") or cls.push_start_hour),
            push_end_hour=int(env.get("PUSH_END_HOUR") or cls.push_end_hour),
            push_scheduler=_bool(env.get("PUSH_SCHEDULER"), True),
            push_subject=env.get("PUSH_SUBJECT") or cls.push_subject,
            vapid_private_key=env.get("VAPID_PRIVATE_KEY") or "",
        )
        if not 0 <= settings.push_start_hour < settings.push_end_hour <= 24:
            raise RuntimeError("PUSH_START_HOUR precisa ser menor que PUSH_END_HOUR.")
        if settings.environment == "production" and settings.secret_key == DEV_SECRET_KEY:
            raise RuntimeError("Defina SECRET_KEY em produção.")
        if settings.owner_password and len(settings.owner_password) < 8:
            raise RuntimeError("OWNER_PASSWORD precisa ter pelo menos 8 caracteres.")
        return settings
