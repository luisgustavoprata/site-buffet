"""Notificações no celular e no computador (Web Push)."""

import random
from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select

from app.deps import CurrentUser, OwnerUser, SessionDep, SettingsDep
from app.models import PushDevice, PushPlan, Role, User, as_utc, utcnow
from app.notifications import (
    BY_KEY,
    MESSAGES,
    TEST_MESSAGE,
    deliver,
    ensure_plan,
    forget_device,
    get_vapid,
    local_now,
)
from app.schemas import ErrorResponse
from app.webpush import is_push_service, unb64url

router = APIRouter(tags=["Notificações"])


class PushConfig(BaseModel):
    public_key: str
    per_day: int
    start_hour: int
    end_hour: int


class DeviceKeys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)

    @field_validator("p256dh")
    @classmethod
    def _public_key(cls, value: str) -> str:
        try:
            raw = unb64url(value)
        except ValueError:
            raw = b""
        if len(raw) != 65 or raw[0] != 4:
            raise ValueError("Chave do navegador inválida.")
        return value

    @field_validator("auth")
    @classmethod
    def _auth(cls, value: str) -> str:
        try:
            ok = len(unb64url(value)) == 16
        except ValueError:
            ok = False
        if not ok:
            raise ValueError("Chave do navegador inválida.")
        return value


class DeviceIn(BaseModel):
    endpoint: str = Field(max_length=1000)
    keys: DeviceKeys

    @field_validator("endpoint")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        if not is_push_service(value):
            raise ValueError("Este navegador não usa um serviço de notificações conhecido.")
        return value


class TestResult(BaseModel):
    devices: int
    sent: int


class PlanOut(BaseModel):
    time: str
    status: str
    title: str


class MessageOut(BaseModel):
    title: str
    body: str
    tone: str


class PushAdmin(BaseModel):
    clients: int
    devices: int
    per_day: int
    start_hour: int
    end_hour: int
    today: list[PlanOut]
    sent_7_days: int
    messages: list[MessageOut]


@router.get("/push/config", response_model=PushConfig, summary="Chave pública para ativar")
def push_config(db: SessionDep, settings: SettingsDep) -> PushConfig:
    return PushConfig(
        public_key=get_vapid(db, settings).public_b64,
        per_day=settings.push_per_day,
        start_hour=settings.push_start_hour,
        end_hour=settings.push_end_hour,
    )


@router.post(
    "/push/devices",
    status_code=status.HTTP_201_CREATED,
    summary="Ativa as notificações neste aparelho",
    responses={422: {"model": ErrorResponse}},
)
def add_device(data: DeviceIn, db: SessionDep, user: CurrentUser) -> dict:
    device = db.scalar(select(PushDevice).where(PushDevice.endpoint == data.endpoint))
    if device is None:
        device = PushDevice(endpoint=data.endpoint)
        db.add(device)
    # O mesmo navegador pode trocar de conta: fica com quem ativou por último.
    device.user_id = user.id
    device.p256dh = data.keys.p256dh
    device.auth = data.keys.auth
    db.flush()
    return {"active": True}


@router.delete(
    "/push/devices",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativa as notificações neste aparelho",
)
def remove_device(
    db: SessionDep, user: CurrentUser, endpoint: str = Query(max_length=1000)
) -> None:
    forget_device(db, endpoint, user)


_last_test: dict[int, float] = {}


@router.post(
    "/push/test",
    response_model=TestResult,
    summary="Manda uma notificação de teste para os seus aparelhos",
    responses={429: {"model": ErrorResponse}},
)
def send_test(request: Request, db: SessionDep, user: CurrentUser, settings: SettingsDep):
    now = utcnow().timestamp()
    if now - _last_test.get(user.id, 0) < 20:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Aguarde alguns segundos.")
    _last_test[user.id] = now
    devices = list(db.scalars(select(PushDevice).where(PushDevice.user_id == user.id)))
    sender = request.app.state.push_sender
    sent = deliver(db, devices, TEST_MESSAGE, get_vapid(db, settings), sender)
    return TestResult(devices=len(devices), sent=sent)


@router.get("/admin/push", response_model=PushAdmin, summary="Resumo das notificações")
def push_admin(db: SessionDep, settings: SettingsDep, _owner: OwnerUser) -> PushAdmin:
    now = utcnow()
    ensure_plan(db, settings, now, random.Random())
    tz = ZoneInfo(settings.push_timezone)
    today = local_now(settings, now).date()
    plans = db.scalars(select(PushPlan).where(PushPlan.day == today).order_by(PushPlan.send_at))
    client_devices = select(PushDevice).join(User).where(User.role == Role.CLIENT).subquery()
    week = db.scalar(
        select(func.coalesce(func.sum(PushPlan.devices), 0)).where(
            PushPlan.status == "enviada", PushPlan.day >= today - timedelta(days=6)
        )
    )
    return PushAdmin(
        clients=db.scalar(select(func.count(func.distinct(client_devices.c.user_id)))) or 0,
        devices=db.scalar(select(func.count()).select_from(client_devices)) or 0,
        per_day=settings.push_per_day,
        start_hour=settings.push_start_hour,
        end_hour=settings.push_end_hour,
        today=[
            PlanOut(
                time=as_utc(p.send_at).astimezone(tz).strftime("%H:%M"),
                status=p.status,
                title=BY_KEY[p.message_key].title if p.message_key in BY_KEY else "",
            )
            for p in plans
        ],
        sent_7_days=week or 0,
        messages=[MessageOut(title=m.title, body=m.body, tone=m.tone) for m in MESSAGES],
    )
