"""Dependências do FastAPI: sessão do banco, configuração, usuário logado e data de hoje."""

from collections.abc import Iterator
from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User
from app.security import password_stamp, read_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")
optional_oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Iterator[Session]:
    """Uma sessão por requisição: confirma no fim, ou desfaz tudo se algo falhar."""
    session: Session = request.app.state.session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_today(settings: Annotated[Settings, Depends(get_settings)]) -> date:
    """A data de hoje no fuso da aplicação. Os testes substituem por uma data fixa."""
    return datetime.now(ZoneInfo(settings.timezone)).date()


def client_ip(request: Request) -> str:
    """O IP de quem está acessando (veja `client_ip_headers` na configuração)."""
    for header in request.app.state.settings.client_ip_headers:
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else ""


SessionDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
TodayDep = Annotated[date, Depends(get_today)]


def token_user(db: Session, token: str, settings: Settings) -> User | None:
    """O dono do token, se ele ainda vale (a senha não foi trocada depois de entrar)."""
    data = read_access_token(token, settings.secret_key)
    if data is None:
        return None
    user = db.get(User, data[0])
    if user is None or data[1] != password_stamp(user.password_hash):
        return None
    return user


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: SessionDep, settings: SettingsDep
) -> User:
    user = token_user(db, token, settings)
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sua sessão expirou. Entre novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_optional_user(
    token: Annotated[str | None, Depends(optional_oauth2)], db: SessionDep, settings: SettingsDep
) -> User | None:
    """Páginas públicas que mudam um pouco para quem entrou (ex.: o coração já marcado)."""
    if not token:
        return None
    return token_user(db, token, settings)


MaybeUser = Annotated[User | None, Depends(get_optional_user)]


def get_owner(user: CurrentUser) -> User:
    if not user.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Área restrita à administração do site.")
    return user


OwnerUser = Annotated[User, Depends(get_owner)]
