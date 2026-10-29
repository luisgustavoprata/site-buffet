"""Pedidos de orçamento e a conversa entre o cliente e a administração do buffet.

O cliente só enxerga os próprios pedidos; a administração enxerga todos. As mensagens novas
chegam por consulta periódica (`GET /quotes/{id}/messages?after=`), sem WebSocket: funciona
em qualquer hospedagem, inclusive no plano gratuito do Render.
"""

import secrets
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.orm import Session

from app.deps import CurrentUser, OwnerUser, SessionDep, SettingsDep, TodayDep
from app.models import Message, Quote, QuoteStatus, Role, User, utcnow
from app.schemas import (
    ClientSummary,
    ErrorResponse,
    MessageCreate,
    MessageOut,
    QuoteCreate,
    QuoteDetail,
    QuoteOut,
    QuoteStatusUpdate,
    SortQuotes,
    Unread,
)
from app.services import store_upload

router = APIRouter(tags=["Orçamentos"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Pedido não encontrado."}}


def _unread_filter(user: User):
    """Mensagens que este usuário ainda não leu (as do outro lado, depois da última lida)."""
    if user.is_owner:
        return and_(Message.from_owner.is_(False), Message.id > Quote.owner_read_id)
    return and_(Message.from_owner.is_(True), Message.id > Quote.client_read_id)


def _visible(user: User):
    return true() if user.is_owner else Quote.client_id == user.id


def _get_quote(db: Session, quote_id: int, user: User) -> Quote:
    quote = db.get(Quote, quote_id)
    # Pedido de outro cliente responde 404, e não 403: não revela que ele existe.
    if quote is None or (not user.is_owner and quote.client_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pedido não encontrado.")
    return quote


def _summaries(db: Session, quotes: list[Quote], user: User) -> list[QuoteOut]:
    ids = [q.id for q in quotes]
    unread: dict[int, int] = {}
    last: dict[int, str] = {}
    if ids:
        unread = dict(
            db.execute(
                select(Message.quote_id, func.count())
                .join(Quote, Quote.id == Message.quote_id)
                .where(Message.quote_id.in_(ids), _unread_filter(user))
                .group_by(Message.quote_id)
            ).all()
        )
        newest = (
            select(func.max(Message.id)).where(Message.quote_id.in_(ids)).group_by(Message.quote_id)
        )
        rows = db.execute(
            select(Message.quote_id, Message.body, Message.image_id).where(Message.id.in_(newest))
        )
        last = {qid: body or ("📷 Foto" if image_id else "") for qid, body, image_id in rows}
    out = []
    for quote in quotes:
        item = QuoteOut.model_validate(quote)
        item.unread = unread.get(quote.id, 0)
        item.last_message = last.get(quote.id)
        out.append(item)
    return out


@router.post(
    "/quotes",
    response_model=QuoteDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Pede um orçamento (abre a conversa)",
    responses={403: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def create_quote(data: QuoteCreate, db: SessionDep, user: CurrentUser, today: TodayDep):
    if user.role != Role.CLIENT:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "A administração não pede orçamento para si mesma."
        )
    if data.event_date < today:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A data do evento já passou. Confira a data."
        )
    quote = Quote(client_id=user.id, **data.model_dump())
    db.add(quote)
    db.flush()
    db.refresh(quote)
    return QuoteDetail.model_validate(quote)


@router.get("/quotes", response_model=list[QuoteOut], summary="Pedidos de orçamento")
def list_quotes(
    db: SessionDep,
    user: CurrentUser,
    status_filter: QuoteStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=80, description="Nome ou e-mail do cliente."),
    sort: SortQuotes = "recentes",
) -> list[QuoteOut]:
    query = select(Quote).where(_visible(user))
    if status_filter:
        query = query.where(Quote.status == status_filter)
    if q and user.is_owner:
        term = f"%{q.strip().lower()}%"
        query = query.join(User, User.id == Quote.client_id).where(
            or_(func.lower(User.name).like(term), func.lower(User.email).like(term))
        )
    if sort == "evento":
        query = query.order_by(Quote.event_date, Quote.id)
    else:
        query = query.order_by(Quote.last_message_at.desc(), Quote.id.desc())
    return _summaries(db, list(db.scalars(query.limit(200)).unique()), user)


@router.get("/quotes/unread", response_model=Unread, summary="Contagem para o aviso de novidades")
def unread(db: SessionDep, user: CurrentUser) -> Unread:
    count = db.scalar(
        select(func.count())
        .select_from(Message)
        .join(Quote, Quote.id == Message.quote_id)
        .where(_visible(user), _unread_filter(user))
    )
    new_quotes = 0
    if user.is_owner:
        new_quotes = db.scalar(
            select(func.count()).select_from(Quote).where(Quote.status == QuoteStatus.NEW)
        )
    return Unread(unread=count or 0, new_quotes=new_quotes or 0)


@router.get(
    "/quotes/{quote_id}",
    response_model=QuoteDetail,
    summary="Um pedido com toda a conversa (marca como lida)",
    responses=NOT_FOUND,
)
def read_quote(quote_id: int, db: SessionDep, user: CurrentUser) -> QuoteDetail:
    quote = _get_quote(db, quote_id, user)
    _mark_read(quote, user)
    return QuoteDetail.model_validate(quote)


@router.get(
    "/quotes/{quote_id}/messages",
    response_model=list[MessageOut],
    summary="Mensagens novas da conversa (marca como lidas)",
    responses=NOT_FOUND,
)
def new_messages(
    quote_id: int,
    db: SessionDep,
    user: CurrentUser,
    after: int = Query(default=0, ge=0, description="Id da última mensagem que você já tem."),
) -> list[Message]:
    quote = _get_quote(db, quote_id, user)
    messages = list(
        db.scalars(
            select(Message)
            .where(Message.quote_id == quote.id, Message.id > after)
            .order_by(Message.id)
        )
    )
    if messages:
        _mark_read(quote, user, messages[-1].id)
    return messages


def _mark_read(quote: Quote, user: User, last_id: int | None = None) -> None:
    if last_id is None:
        last_id = quote.messages[-1].id if quote.messages else 0
    if user.is_owner:
        quote.owner_read_id = max(quote.owner_read_id, last_id)
    else:
        quote.client_read_id = max(quote.client_read_id, last_id)


@router.post(
    "/quotes/{quote_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma mensagem na conversa",
    responses={**NOT_FOUND, 409: {"model": ErrorResponse}},
)
def send_message(quote_id: int, data: MessageCreate, db: SessionDep, user: CurrentUser) -> Message:
    quote = _get_quote(db, quote_id, user)
    return _post(db, quote, user, body=data.body)


@router.post(
    "/quotes/{quote_id}/photos",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma foto na conversa (com legenda opcional)",
    description="A foto só abre para quem participa da conversa: o endereço leva uma chave.",
    responses={
        **NOT_FOUND,
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def send_photo(
    quote_id: int,
    file: Annotated[UploadFile, File(description="A foto (JPG, PNG ou WebP).")],
    db: SessionDep,
    user: CurrentUser,
    settings: SettingsDep,
    caption: Annotated[str, Form(max_length=4000, description="Legenda.")] = "",
) -> Message:
    quote = _get_quote(db, quote_id, user)
    image = await store_upload(db, file, settings, access_key=secrets.token_urlsafe(24))
    return _post(db, quote, user, body=caption.strip(), image=image)


def _post(db: Session, quote: Quote, user: User, **fields) -> Message:
    message = Message(quote=quote, sender_id=user.id, from_owner=user.is_owner, **fields)
    db.add(message)
    quote.last_message_at = utcnow()
    if user.is_owner and quote.status == QuoteStatus.NEW:
        quote.status = QuoteStatus.TALKING  # a primeira resposta tira o pedido de "novo"
    db.flush()
    _mark_read(quote, user, message.id)
    return message


@router.patch(
    "/admin/quotes/{quote_id}",
    response_model=QuoteOut,
    summary="Muda a situação de um pedido",
    responses=NOT_FOUND,
)
def update_status(
    quote_id: int, data: QuoteStatusUpdate, db: SessionDep, owner: OwnerUser
) -> QuoteOut:
    quote = _get_quote(db, quote_id, owner)
    quote.status = data.status
    return _summaries(db, [quote], owner)[0]


@router.get(
    "/admin/clients",
    response_model=list[ClientSummary],
    summary="Clientes cadastrados, com a quantidade de pedidos",
)
def list_clients(
    db: SessionDep,
    _owner: OwnerUser,
    q: str | None = Query(default=None, max_length=80, description="Nome, e-mail ou cidade."),
) -> list[ClientSummary]:
    stats = (
        select(
            Quote.client_id,
            func.count(Quote.id).label("quotes"),
            func.max(Quote.created_at).label("last_quote_at"),
        )
        .group_by(Quote.client_id)
        .subquery()
    )
    query = (
        select(User, stats.c.quotes, stats.c.last_quote_at)
        .outerjoin(stats, stats.c.client_id == User.id)
        .where(User.role == Role.CLIENT)
        .order_by(User.created_at.desc(), User.id.desc())
    )
    if q:
        term = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(User.name).like(term),
                func.lower(User.email).like(term),
                func.lower(User.city).like(term),
            )
        )
    return [
        ClientSummary(
            id=user.id,
            name=user.name,
            email=user.email,
            phone=user.phone,
            city=user.city,
            created_at=user.created_at,
            quotes=quotes or 0,
            last_quote_at=last,
        )
        for user, quotes, last in db.execute(query.limit(500))
    ]
