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


def _required(value: str | None) -> str:
    if not value:
        raise ValueError("Campo obrigatório.")  # o buffet responde pelo WhatsApp
    return value


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
    phone: Annotated[str, AfterValidator(_phone), AfterValidator(_required)]
    city: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(Input):
    name: str | None = Field(default=None, min_length=3, max_length=120)
    phone: Phone = None
    city: str | None = Field(default=None, min_length=2, max_length=80)


class PasswordChange(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


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


class FaqItem(Input):
    question: str = Field(min_length=3, max_length=200)
    answer: str = Field(min_length=1, max_length=1500)


class Testimonial(Input):
    name: str = Field(min_length=2, max_length=80)
    event: str = Field(default="", max_length=80)
    text: str = Field(min_length=3, max_length=600)


class IncludedItem(Input):
    title: str = Field(min_length=2, max_length=80)
    text: str = Field(default="", max_length=300)


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
    faq: list[FaqItem] = []
    testimonials: list[Testimonial] = []
    included: list[IncludedItem] = []
    bio_photos: list[BioPhotoOut] = []

    @field_validator("faq", "testimonials", "included", mode="before")
    @classmethod
    def empty_list(cls, value):
        return value or []  # bancos antigos: a coluna nova começa vazia (nula)

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
    faq: list[FaqItem] | None = Field(default=None, max_length=12)
    testimonials: list[Testimonial] | None = Field(default=None, max_length=12)
    included: list[IncludedItem] | None = Field(default=None, max_length=12)

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
    likes: int = 0
    comments: int = 0
    liked: bool = False  # a pessoa que está vendo já deixou o coração


class LikeOut(BaseModel):
    likes: int
    liked: bool


class CommentCreate(Input):
    body: str = Field(min_length=1, max_length=1000)


class CommentOut(BaseModel):
    id: int
    author: str  # só o primeiro nome e a inicial do sobrenome: o comentário é público
    from_owner: bool
    body: str
    created_at: UtcDatetime
    can_delete: bool = False


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
    image_url: str | None = None
    image_width: int | None = None
    image_height: int | None = None
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


class TemporaryPassword(BaseModel):
    password: str


class ClientSummary(ClientOut):
    quotes: int
    last_quote_at: UtcDatetime | None


SortQuotes = Literal["recentes", "evento"]


# ---------- Gestão (estoque, eventos, despesas, DRE e precificação) ----------

Money = Annotated[float, Field(ge=0, le=100_000_000)]
Qty = Annotated[float, Field(gt=0, le=10_000_000)]
Rate = Annotated[float, Field(ge=0, lt=1)]
ShortList = Annotated[
    list[Annotated[str, Field(min_length=1, max_length=60)]], Field(max_length=60)
]
EventStatus = Literal["orcamento", "confirmado", "realizado", "cancelado"]
OutKind = Literal["evento", "perda", "consumo"]
DreGroup = Literal[
    "Custo direto do evento",
    "Pessoal",
    "Ocupação",
    "Utilidades",
    "Comercial",
    "Administrativa",
    "Manutenção",
    "Depreciação",
    "Despesa financeira",
    "Receita financeira",
]
PricingKind = Literal["Comida", "Bebidas", "Descartáveis"]


class FinanceConfigIn(Input):
    tax_rate: Rate
    income_tax_rate: Rate
    item_categories: ShortList
    units: ShortList
    event_types: ShortList
    payment_methods: ShortList


class FinanceConfigOut(Output):
    tax_rate: float
    income_tax_rate: float
    item_categories: list[str]
    units: list[str]
    event_types: list[str]
    payment_methods: list[str]
    groups: list[str] = []


class ExpenseCategoryIn(Input):
    name: str = Field(min_length=1, max_length=80)
    group: DreGroup


class ExpenseCategoryOut(Output):
    id: int
    name: str
    group: str
    position: int


class StockItemIn(Input):
    code: str = Field(default="", max_length=20, description="Vazio: o site cria (ex.: CAR012).")
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=60)
    unit: str = Field(min_length=1, max_length=20)
    min_stock: Money = 0
    initial_stock: Money = 0
    initial_cost: Money = 0
    active: bool = True


class StockItemOut(BaseModel):
    id: int
    code: str
    name: str
    category: str
    unit: str
    min_stock: float
    initial_stock: float
    initial_cost: float
    active: bool
    total_in: float
    total_out: float
    balance: float
    avg_cost: float
    value: float
    status: str
    suggestion: float


class StockInIn(Input):
    entry_date: date
    item_id: int
    quantity: Qty
    unit_cost: Money
    supplier: str = Field(default="", max_length=120)
    invoice: str = Field(default="", max_length=40)


class StockInOut(Output):
    id: int
    entry_date: date
    item_id: int
    item_code: str
    item_name: str
    unit: str
    quantity: float
    unit_cost: float
    total: float
    supplier: str
    invoice: str


class StockOutIn(Input):
    entry_date: date
    item_id: int
    quantity: Qty
    kind: OutKind
    event_id: int | None = None
    note: str = Field(default="", max_length=200)


class StockOutOut(Output):
    id: int
    entry_date: date
    item_id: int
    item_code: str
    item_name: str
    unit: str
    quantity: float
    kind: str
    event_id: int | None
    event_code: str | None
    unit_cost: float
    total: float
    note: str


class FinanceEventIn(Input):
    code: str = Field(default="", max_length=20, description="Vazio: o site cria (EV001...).")
    event_date: date
    client: str = Field(min_length=1, max_length=120)
    event_type: str = Field(min_length=1, max_length=40)
    guests: int = Field(ge=1, le=100_000)
    price_per_guest: Money
    discount: Money = 0
    status: EventStatus = "confirmado"
    quote_id: int | None = None
    notes: str = Field(default="", max_length=2000)


class FinanceEventOut(Output):
    id: int
    code: str
    event_date: date
    client: str
    event_type: str
    guests: int
    price_per_guest: float
    discount: float
    status: str
    quote_id: int | None
    notes: str
    gross: float = 0
    net: float = 0
    cmv: float = 0
    direct_costs: float = 0
    cmv_per_guest: float = 0
    margin_on_inputs: float = 0
    contribution: float = 0


class ExpenseIn(Input):
    entry_date: date
    category_id: int
    description: str = Field(default="", max_length=200)
    supplier: str = Field(default="", max_length=120)
    amount: Annotated[float, Field(gt=0, le=100_000_000)]
    payment: str = Field(default="", max_length=40)
    event_id: int | None = None


class ExpenseOut(Output):
    id: int
    entry_date: date
    category_id: int
    category: str
    group: str
    description: str
    supplier: str
    amount: float
    payment: str
    event_id: int | None
    event_code: str | None


class PricingItemIn(Input):
    item_id: int
    kind: PricingKind = "Comida"
    per_guest: Annotated[float, Field(ge=0, le=100_000)]


class PricingIn(Input):
    name: str = Field(min_length=1, max_length=120)
    event_type: str = Field(default="", max_length=40)
    guests: int = Field(ge=1, le=100_000)
    safety_margin: Annotated[float, Field(ge=0, le=2)] = 0.1
    # Até 1000%: a regra "margem + imposto < 100%" é conferida na rota, com uma explicação.
    profit_margin: Annotated[float, Field(ge=0, le=10)] = 0.2
    charged_per_guest: Money | None = None
    items: list[PricingItemIn] = Field(default_factory=list, max_length=200)


class PricingOut(Output):
    id: int | None = None
    name: str
    event_type: str
    guests: int
    safety_margin: float
    profit_margin: float
    charged_per_guest: float | None
    items: list[dict]
    updated_at: UtcDatetime | None = None
    result: dict = {}


class FinanceImport(Input):
    """Tudo da planilha antiga, lido no navegador. Substitui os dados da gestão."""

    config: FinanceConfigIn | None = None
    categories: list[ExpenseCategoryIn] = Field(default_factory=list, max_length=500)
    items: list[StockItemIn] = Field(default_factory=list, max_length=5000)
    events: list[FinanceEventIn] = Field(default_factory=list, max_length=5000)
    # Nas linhas abaixo, item/evento/categoria vêm pelo código ou pelo nome.
    stock_in: list[dict] = Field(default_factory=list, max_length=20000)
    stock_out: list[dict] = Field(default_factory=list, max_length=20000)
    expenses: list[dict] = Field(default_factory=list, max_length=20000)
    # Simulações da aba Precificação: {"name", "event_type", "guests", "safety_margin",
    # "profit_margin", "items": [{"item": "CAR001", "kind": "Comida", "per_guest": 0.12}]}
    pricing: list[dict] = Field(default_factory=list, max_length=50)
