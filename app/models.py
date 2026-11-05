"""Tabelas do banco (SQLAlchemy 2, ORM tipado)."""

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """O SQLite devolve as datas sem fuso; elas sempre foram gravadas em UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class Role(enum.StrEnum):
    OWNER = "owner"  # a dona do buffet: edita o site e responde os orçamentos
    CLIENT = "client"  # quem se cadastra para pedir orçamento


class QuoteStatus(enum.StrEnum):
    NEW = "novo"
    TALKING = "em_conversa"
    PROPOSAL = "proposta_enviada"
    CLOSED = "fechado"
    DECLINED = "nao_fechado"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20))
    city: Mapped[str | None] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Conta da administração: hash do OWNER_PASSWORD já aplicado. Se o Render mudar a senha,
    # ela passa a valer (recuperação de senha esquecida); se não mudar, a do painel continua.
    owner_env_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    role: Mapped[Role] = mapped_column(
        Enum(Role, native_enum=False, length=10), default=Role.CLIENT
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER


class Image(Base):
    """Fotos guardadas no próprio banco: sobrevivem a novos deploys sem serviço extra."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    content_type: Mapped[str] = mapped_column(String(30))
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    # Fotos da conversa são particulares: só abrem com esta chave no endereço (?k=...).
    access_key: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SiteContent(Base):
    """Textos e fotos da apresentação. Existe uma linha só (id = 1)."""

    __tablename__ = "site_content"

    id: Mapped[int] = mapped_column(primary_key=True)
    business_name: Mapped[str] = mapped_column(String(80))
    tagline: Mapped[str] = mapped_column(String(160), default="")
    hero_title: Mapped[str] = mapped_column(String(160), default="")
    hero_text: Mapped[str] = mapped_column(Text, default="")
    owner_name: Mapped[str] = mapped_column(String(120), default="")
    owner_role: Mapped[str] = mapped_column(String(120), default="")
    bio: Mapped[str] = mapped_column(Text, default="")
    history_title: Mapped[str] = mapped_column(String(160), default="")
    history: Mapped[str] = mapped_column(Text, default="")
    founded_year: Mapped[int | None] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(String(80), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    instagram: Mapped[str] = mapped_column(String(60), default="")
    hero_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"))
    owner_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id", ondelete="SET NULL"))
    history_image_id: Mapped[int | None] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL")
    )
    # Listas editadas no painel: perguntas frequentes, depoimentos e o que está incluído.
    faq: Mapped[list] = mapped_column(JSON, default=list)
    testimonials: Mapped[list] = mapped_column(JSON, default=list)
    included: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class BioPhoto(Base):
    """Fotos extras da seção "Sobre mim" (a dona escolhe a ordem)."""

    __tablename__ = "bio_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    caption: Mapped[str] = mapped_column(String(160), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)


class Event(Base):
    """Um evento realizado, publicado no portfólio."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(40))
    event_date: Mapped[date | None] = mapped_column(Date)
    guests: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    photos: Mapped[list["EventPhoto"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="EventPhoto.position",
        lazy="selectin",
    )


class EventPhoto(Base):
    __tablename__ = "event_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)

    event: Mapped[Event] = relationship(back_populates="photos")


class EventLike(Base):
    """Um coração deixado por uma pessoa cadastrada (no máximo um por evento)."""

    __tablename__ = "event_likes"
    __table_args__ = (UniqueConstraint("event_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EventComment(Base):
    """Comentário ou feedback de uma pessoa cadastrada sobre um evento do portfólio."""

    __tablename__ = "event_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(lazy="joined")


class Quote(Base):
    """Pedido de orçamento: abre uma conversa entre o cliente e a dona do buffet."""

    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40))
    event_date: Mapped[date] = mapped_column(Date)
    guests: Mapped[int] = mapped_column(Integer)
    location: Mapped[str] = mapped_column(String(120))
    budget: Mapped[str] = mapped_column(String(40), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[QuoteStatus] = mapped_column(
        Enum(QuoteStatus, native_enum=False, length=20), default=QuoteStatus.NEW
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Última mensagem que cada lado já leu: as de id maior contam como "não lidas".
    client_read_id: Mapped[int] = mapped_column(Integer, default=0)
    owner_read_id: Mapped[int] = mapped_column(Integer, default=0)

    client: Mapped[User] = relationship(lazy="joined")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="Message.id",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_id: Mapped[int] = mapped_column(ForeignKey("quotes.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    from_owner: Mapped[bool] = mapped_column(default=False)
    body: Mapped[str] = mapped_column(Text)
    image_id: Mapped[int | None] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    quote: Mapped[Quote] = relationship(back_populates="messages")
    image: Mapped[Image | None] = relationship(lazy="joined")

    @property
    def image_url(self) -> str | None:
        if self.image is None:
            return None
        return f"/media/{self.image.id}?k={self.image.access_key}"

    @property
    def image_width(self) -> int | None:
        return self.image.width if self.image else None

    @property
    def image_height(self) -> int | None:
        return self.image.height if self.image else None


class PushDevice(Base):
    """Um navegador/aparelho que aceitou receber notificações (cada pessoa pode ter vários)."""

    __tablename__ = "push_devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(lazy="joined")


class PushPlan(Base):
    """Notificações programadas para um dia, em horários sorteados dentro da janela."""

    __tablename__ = "push_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    message_key: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="programada")  # enviada, pulada
    devices: Mapped[int] = mapped_column(Integer, default=0)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppSecret(Base):
    """Chaves geradas pelo próprio site e guardadas no banco (ex.: a chave das notificações)."""

    __tablename__ = "app_secrets"

    name: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


# ---------- Gestão: estoque, eventos, despesas e DRE (antes, a planilha do buffet) ----------


class FinanceSettings(Base):
    """Alíquotas e listas da gestão. Existe uma linha só (id = 1)."""

    __tablename__ = "fin_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.08)  # sobre o faturamento
    income_tax_rate: Mapped[float] = mapped_column(Float, default=0.0)  # IR/CSLL sobre o lucro
    item_categories: Mapped[list] = mapped_column(JSON, default=list)
    units: Mapped[list] = mapped_column(JSON, default=list)
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    payment_methods: Mapped[list] = mapped_column(JSON, default=list)


class ExpenseCategory(Base):
    """Categoria de despesa e a linha do DRE em que ela cai (ex.: Aluguel → Ocupação)."""

    __tablename__ = "fin_expense_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    group: Mapped[str] = mapped_column(String(40))
    position: Mapped[int] = mapped_column(Integer, default=0)


class StockItem(Base):
    """Insumo do estoque. Saldo e custo médio vêm das compras e das saídas."""

    __tablename__ = "fin_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    unit: Mapped[str] = mapped_column(String(20))
    min_stock: Mapped[float] = mapped_column(Float, default=0)
    initial_stock: Mapped[float] = mapped_column(Float, default=0)
    initial_cost: Mapped[float] = mapped_column(Float, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FinanceEvent(Base):
    """Evento vendido: a receita do DRE. Pode ter nascido de um pedido de orçamento do site."""

    __tablename__ = "fin_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    client: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(40))
    guests: Mapped[int] = mapped_column(Integer)
    price_per_guest: Mapped[float] = mapped_column(Float)
    discount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="orcamento")
    quote_id: Mapped[int | None] = mapped_column(
        ForeignKey("quotes.id", ondelete="SET NULL"), default=None
    )
    notes: Mapped[str] = mapped_column(Text, default="")


class StockIn(Base):
    """Compra de insumo: vira estoque (não é despesa)."""

    __tablename__ = "fin_stock_in"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("fin_items.id", ondelete="RESTRICT"))
    quantity: Mapped[float] = mapped_column(Float)
    unit_cost: Mapped[float] = mapped_column(Float)
    supplier: Mapped[str] = mapped_column(String(120), default="")
    invoice: Mapped[str] = mapped_column(String(40), default="")

    item: Mapped[StockItem] = relationship(lazy="joined")


class StockOut(Base):
    """Saída de insumo. `unit_cost` é o custo médio do dia da saída (recalculado se uma compra
    anterior for lançada ou corrigida depois); compras mais novas não mudam o passado."""

    __tablename__ = "fin_stock_out"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("fin_items.id", ondelete="RESTRICT"))
    quantity: Mapped[float] = mapped_column(Float)
    kind: Mapped[str] = mapped_column(String(20))  # evento | perda | consumo
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("fin_events.id", ondelete="SET NULL"), default=None
    )
    unit_cost: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str] = mapped_column(String(200), default="")

    item: Mapped[StockItem] = relationship(lazy="joined")
    event: Mapped[FinanceEvent | None] = relationship(lazy="joined")


class Expense(Base):
    """Despesa (ou receita financeira): a categoria define a linha do DRE."""

    __tablename__ = "fin_expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("fin_expense_categories.id", ondelete="RESTRICT")
    )
    description: Mapped[str] = mapped_column(String(200), default="")
    supplier: Mapped[str] = mapped_column(String(120), default="")
    amount: Mapped[float] = mapped_column(Float)
    payment: Mapped[str] = mapped_column(String(40), default="")
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("fin_events.id", ondelete="SET NULL"), default=None
    )

    category: Mapped[ExpenseCategory] = relationship(lazy="joined")
    event: Mapped[FinanceEvent | None] = relationship(lazy="joined")


class PricingSim(Base):
    """Simulação de preço de um evento: cardápio com o consumo por convidado."""

    __tablename__ = "fin_pricing"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(40), default="")
    guests: Mapped[int] = mapped_column(Integer)
    safety_margin: Mapped[float] = mapped_column(Float, default=0.1)
    profit_margin: Mapped[float] = mapped_column(Float, default=0.2)
    charged_per_guest: Mapped[float | None] = mapped_column(Float, default=None)
    # [{"item_id": 1, "kind": "Comida", "per_guest": 0.12}]
    items: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
