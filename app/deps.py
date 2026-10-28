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
from app.security import read_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


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


SessionDep = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
TodayDep = Annotated[date, Depends(get_today)]


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: SessionDep, settings: SettingsDep
) -> User:
    user_id = read_access_token(token, settings.secret_key)
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sua sessão expirou. Entre novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_owner(user: CurrentUser) -> User:
    if not user.is_owner:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Área restrita à administração do site.")
    return user


OwnerUser = Annotated[User, Depends(get_owner)]
