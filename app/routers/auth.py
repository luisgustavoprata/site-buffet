from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.deps import CurrentUser, SessionDep, SettingsDep
from app.models import Role, User
from app.schemas import ErrorResponse, Token, UserCreate, UserOut, UserUpdate
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Conta"])

EMAIL_TAKEN = "Já existe uma conta com este e-mail. Use a opção Entrar."


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Cria a conta de um cliente",
    responses={409: {"model": ErrorResponse, "description": "E-mail já cadastrado."}},
)
def register(data: UserCreate, db: SessionDep, settings: SettingsDep) -> User:
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
    user = User(
        name=data.name,
        email=data.email,
        phone=data.phone,
        city=data.city,
        role=Role.CLIENT,  # a conta da administração nunca nasce por aqui
        password_hash=hash_password(data.password, settings.password_iterations),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # duas contas iguais criadas ao mesmo tempo
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from exc
    return user


@router.post(
    "/token",
    response_model=Token,
    summary="Entra e recebe o token de acesso",
    description="Formulário OAuth2: no campo `username`, informe o **e-mail**.",
    responses={
        401: {"model": ErrorResponse, "description": "E-mail ou senha incorretos."},
        429: {"model": ErrorResponse, "description": "Muitas tentativas seguidas."},
    },
)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request,
    db: SessionDep,
    settings: SettingsDep,
) -> Token:
    email = form.username.strip().lower()
    limiter = request.app.state.login_limiter
    key = f"{request.client.host if request.client else '-'}|{email}"
    wait = limiter.retry_after(key)
    if wait is not None:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Muitas tentativas. Tente de novo em {wait} segundos.",
            headers={"Retry-After": str(wait)},
        )

    user = db.scalar(select(User).where(User.email == email))
    # Sem usuário, compara com um hash qualquer mesmo assim: o tempo de resposta
    # não revela se o e-mail tem conta.
    stored = user.password_hash if user else request.app.state.dummy_hash
    if not verify_password(form.password, stored) or user is None:
        limiter.register_failure(key)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "E-mail ou senha incorretos.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    limiter.reset(key)
    token = create_access_token(user.id, settings.secret_key, settings.token_minutes)
    return Token(access_token=token, expires_in=settings.token_minutes * 60)


@router.get("/me", response_model=UserOut, summary="Dados da conta logada")
def me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut, summary="Atualiza nome, telefone ou cidade")
def update_me(data: UserUpdate, user: CurrentUser) -> User:
    for field, value in data.model_dump(exclude_unset=True).items():
        if value is None and field != "phone":
            continue
        setattr(user, field, value)
    return user
