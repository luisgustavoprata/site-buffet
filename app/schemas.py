"""Formatos de entrada e saída da API (Pydantic v2)."""

import re
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
)

from app.models import QuoteStatus, Role

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
EVENT_TYPES = (
    "Casamento",
    "Aniversário",
    "15 anos",
    "Corporativo",
    "Batizado",
    "Chá de bebê",
    "Formatura",
    "Outro",
)
BUDGETS = (
    "",
    "Até R$ 5 mil",
    "R$ 5 a 10 mil",
    "R$ 10 a 20 mil",
    "R$ 20 a 40 mil",
    "Acima de R$ 40 mil",
)


def _as_utc(value: datetime) -> str:
    # O SQLite devolve datas sem fuso; tudo é gravado em UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[datetime, PlainSerializer(_as_utc, return_type=str)]


def _email(value: str) -> str:
    value = value.strip().lower()
    if not EMAIL_RE.match(value):
        raise ValueError("E-mail inválido.")
    return value


def _phone(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    digits = re.sub(r"\D", "", value)
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        raise ValueError("Telefone inválido. Use DDD + número, ex.: (11) 98765-4321.")
    return f"({digits[:2]}) {digits[2:-4]}-{digits[-4:]}"


Email = Annotated[str, Field(max_length=255), AfterValidator(_email)]
Phone = Annotated[str | None, AfterValidator(_phone)]
Text = Annotated[str, Field(max_length=4000)]


class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    detail: str


# ---------- Contas ----------


class UserCreate(Input):
    name: str = Field(min_length=3, max_length=120)
    email: Email
    phone: Annotated[str, AfterValidator(_phone)]
    city: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(Input):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    phone: Phone = None
    city: str | None = Field(default=None, min_length=2, max_length=80)


class UserOut(Output):
    id: int
    name: str
    email: str
    phone: str | None
    city: str | None
    role: Role
    created_at: UtcDatetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ---------- Conteúdo do site ----------


class BioPhotoOut(Output):
    id: int
    image_id: int
    caption: str


class SiteStats(BaseModel):
    events: int = 0
    guests: int = 0  # soma dos convidados dos eventos do portfólio
    photos: int = 0


class SiteOut(Output):
    business_name: str
    tagline: str
    hero_title: str
    hero_text: str
    owner_name: str
    owner_role: str
    bio: str
    history_title: str
    history: str
    founded_year: int | None
    city: str
    phone: str
    email: str
    instagram: str
    hero_image_id: int | None
    owner_image_id: int | None
    history_image_id: int | None
    bio_photos: list[BioPhotoOut] = []
    stats: SiteStats = SiteStats()
    event_types: list[str] = list(EVENT_TYPES)
    budgets: list[str] = list(BUDGETS)


class SiteUpdate(Input):
    business_name: str | None = Field(default=None, min_length=2, max_length=80)
    tagline: str | None = Field(default=None, max_length=160)
    hero_title: str | None = Field(default=None, max_length=160)
    hero_text: Text | None = None
    owner_name: str | None = Field(default=None, max_length=120)
    owner_role: str | None = Field(default=None, max_length=120)
    bio: Text | None = None
    history_title: str | None = Field(default=None, max_length=160)
    history: Text | None = None
    founded_year: int | None = Field(default=None, ge=1900, le=2100)
    city: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    instagram: str | None = Field(default=None, max_length=60)
    hero_image_id: int | None = None
    owner_image_id: int | None = None
    history_image_id: int | None = None

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str | None) -> str | None:
        return _email(value) if value else value

    @field_validator("instagram")
    @classmethod
    def clean_instagram(cls, value: str | None) -> str | None:
        return value.strip().lstrip("@") if value else value


class BioPhotoCreate(Input):
    image_id: int
    caption: str = Field(default="", max_length=160)


class ImageOut(Output):
    id: int
    width: int
    height: int
    content_type: str


# ---------- Portfólio ----------


class EventIn(Input):
    title: str = Field(min_length=3, max_length=120)
    event_type: str = Field(min_length=2, max_length=40)
    event_date: date | None = None
    guests: int | None = Field(default=None, ge=1, le=100_000)
    location: str = Field(default="", max_length=120)
    description: Text = ""
    image_ids: list[int] = Field(default_factory=list, max_length=40)


class EventPhotoOut(Output):
    image_id: int


class EventOut(Output):
    id: int
    title: str
    event_type: str
    event_date: date | None
    guests: int | None
    location: str
    description: str
    photos: list[EventPhotoOut]
    created_at: UtcDatetime


# ---------- Orçamentos e conversa ----------


class QuoteCreate(Input):
    event_type: str = Field(min_length=2, max_length=40)
    event_date: date
    guests: int = Field(ge=1, le=100_000)
    location: str = Field(min_length=2, max_length=120)
    budget: str = Field(default="", max_length=40)
    details: Text = ""

    @field_validator("event_type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in EVENT_TYPES:
            raise ValueError("Escolha um dos tipos de evento da lista.")
        return value

    @field_validator("budget")
    @classmethod
    def known_budget(cls, value: str) -> str:
        if value not in BUDGETS:
            raise ValueError("Escolha uma das faixas de valor da lista.")
        return value


class QuoteStatusUpdate(Input):
    status: QuoteStatus


class MessageCreate(Input):
    body: str = Field(min_length=1, max_length=4000)


class MessageOut(Output):
    id: int
    from_owner: bool
    body: str
    created_at: UtcDatetime


class ClientOut(Output):
    id: int
    name: str
    email: str
    phone: str | None
    city: str | None
    created_at: UtcDatetime


class QuoteOut(Output):
    id: int
    event_type: str
    event_date: date
    guests: int
    location: str
    budget: str
    details: str
    status: QuoteStatus
    created_at: UtcDatetime
    last_message_at: UtcDatetime
    unread: int = 0
    last_message: str | None = None
    client: ClientOut


class QuoteDetail(QuoteOut):
    messages: list[MessageOut]


class Unread(BaseModel):
    unread: int
    new_quotes: int = 0


class ClientSummary(ClientOut):
    quotes: int
    last_quote_at: UtcDatetime | None


SortQuotes = Literal["recentes", "evento"]
