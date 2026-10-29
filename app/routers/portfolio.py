"""Portfólio: os eventos que o buffet já fez, com fotos."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, MaybeUser, OwnerUser, SessionDep
from app.models import Event, EventComment, EventLike, EventPhoto, User, utcnow
from app.schemas import (
    CommentCreate,
    CommentOut,
    ErrorResponse,
    EventIn,
    EventOut,
    LikeOut,
)
from app.services import delete_unused_images, require_images

router = APIRouter(tags=["Portfólio"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Evento não encontrado."}}


def _with_reactions(db: Session, events: list[Event], viewer: User | None) -> list[EventOut]:
    """Junta a cada evento os corações, os comentários e se quem vê já deixou o coração."""
    ids = [e.id for e in events]
    likes: dict[int, int] = {}
    comments: dict[int, int] = {}
    mine: set[int] = set()
    if ids:
        likes = dict(
            db.execute(
                select(EventLike.event_id, func.count())
                .where(EventLike.event_id.in_(ids))
                .group_by(EventLike.event_id)
            ).all()
        )
        comments = dict(
            db.execute(
                select(EventComment.event_id, func.count())
                .where(EventComment.event_id.in_(ids))
                .group_by(EventComment.event_id)
            ).all()
        )
        if viewer is not None:
            mine = set(
                db.scalars(
                    select(EventLike.event_id).where(
                        EventLike.event_id.in_(ids), EventLike.user_id == viewer.id
                    )
                )
            )
    out = []
    for event in events:
        item = EventOut.model_validate(event)
        item.likes = likes.get(event.id, 0)
        item.comments = comments.get(event.id, 0)
        item.liked = event.id in mine
        out.append(item)
    return out


def _get(db, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento não encontrado.")
    return event


@router.get("/events", response_model=list[EventOut], summary="Eventos do portfólio")
def list_events(
    db: SessionDep,
    viewer: MaybeUser,
    event_type: str | None = Query(default=None, description="Filtra pelo tipo de evento."),
    limit: int = Query(default=60, ge=1, le=200),
) -> list[EventOut]:
    query = select(Event)
    if event_type:
        query = query.where(Event.event_type == event_type)
    # Mais recentes primeiro; eventos sem data ficam por último.
    query = query.order_by(Event.event_date.is_(None), Event.event_date.desc(), Event.id.desc())
    return _with_reactions(db, list(db.scalars(query.limit(limit))), viewer)


@router.get("/events/types", response_model=list[str], summary="Tipos com eventos publicados")
def event_types(db: SessionDep) -> list[str]:
    rows = db.execute(
        select(Event.event_type, func.count()).group_by(Event.event_type).order_by(Event.event_type)
    )
    return [row[0] for row in rows]


@router.get("/events/{event_id}", response_model=EventOut, summary="Um evento", responses=NOT_FOUND)
def read_event(event_id: int, db: SessionDep, viewer: MaybeUser) -> EventOut:
    return _with_reactions(db, [_get(db, event_id)], viewer)[0]


def _set_photos(event: Event, image_ids: list[int]) -> None:
    seen: list[int] = []
    for image_id in image_ids:
        if image_id not in seen:
            seen.append(image_id)
    event.photos = [EventPhoto(image_id=i, position=n) for n, i in enumerate(seen)]


@router.post(
    "/admin/events",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
    summary="Publica um evento no portfólio",
    description="A primeira foto de `image_ids` é a capa.",
)
def create_event(data: EventIn, db: SessionDep, _owner: OwnerUser) -> Event:
    require_images(db, data.image_ids)
    event = Event(**data.model_dump(exclude={"image_ids"}))
    _set_photos(event, data.image_ids)
    db.add(event)
    db.flush()
    return event


@router.put(
    "/admin/events/{event_id}",
    response_model=EventOut,
    summary="Edita um evento (fotos na ordem enviada)",
    responses=NOT_FOUND,
)
def update_event(event_id: int, data: EventIn, db: SessionDep, _owner: OwnerUser) -> Event:
    event = _get(db, event_id)
    require_images(db, data.image_ids)
    removed = {p.image_id for p in event.photos} - set(data.image_ids)
    for field, value in data.model_dump(exclude={"image_ids"}).items():
        setattr(event, field, value)
    _set_photos(event, data.image_ids)
    delete_unused_images(db, removed)
    return event


@router.delete(
    "/admin/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Tira um evento do portfólio (e as fotos dele)",
    responses=NOT_FOUND,
)
def delete_event(event_id: int, db: SessionDep, _owner: OwnerUser) -> None:
    event = _get(db, event_id)
    image_ids = [p.image_id for p in event.photos]
    db.delete(event)
    delete_unused_images(db, image_ids)


# ---------- Corações e comentários ----------

COMMENTS_PER_WINDOW = 5  # por pessoa, a cada 10 minutos: evita enxurrada de comentários
COMMENT_WINDOW = timedelta(minutes=10)


def _like_state(db: Session, event_id: int, user: User) -> LikeOut:
    db.flush()
    likes = db.scalar(select(func.count()).where(EventLike.event_id == event_id)) or 0
    liked = db.scalar(
        select(EventLike.id).where(EventLike.event_id == event_id, EventLike.user_id == user.id)
    )
    return LikeOut(likes=likes, liked=liked is not None)


@router.put(
    "/events/{event_id}/like",
    response_model=LikeOut,
    summary="Deixa um coração no evento (repetir não soma de novo)",
    responses=NOT_FOUND,
)
def like_event(event_id: int, db: SessionDep, user: CurrentUser) -> LikeOut:
    _get(db, event_id)
    exists = db.scalar(
        select(EventLike.id).where(EventLike.event_id == event_id, EventLike.user_id == user.id)
    )
    if exists is None:
        db.add(EventLike(event_id=event_id, user_id=user.id))
    return _like_state(db, event_id, user)


@router.delete(
    "/events/{event_id}/like",
    response_model=LikeOut,
    summary="Tira o coração do evento",
    responses=NOT_FOUND,
)
def unlike_event(event_id: int, db: SessionDep, user: CurrentUser) -> LikeOut:
    _get(db, event_id)
    db.execute(
        delete(EventLike).where(EventLike.event_id == event_id, EventLike.user_id == user.id)
    )
    return _like_state(db, event_id, user)


def _public_name(user: User) -> str:
    parts = user.name.split()
    if len(parts) < 2:
        return user.name
    return f"{parts[0]} {parts[-1][0]}."


def _comment_out(comment: EventComment, viewer: User | None) -> CommentOut:
    owner = comment.user.is_owner
    return CommentOut(
        id=comment.id,
        author=comment.user.name if owner else _public_name(comment.user),
        from_owner=owner,
        body=comment.body,
        created_at=comment.created_at,
        can_delete=viewer is not None and (viewer.is_owner or viewer.id == comment.user_id),
    )


@router.get(
    "/events/{event_id}/comments",
    response_model=list[CommentOut],
    summary="Comentários do evento (mais antigos primeiro)",
    responses=NOT_FOUND,
)
def list_comments(event_id: int, db: SessionDep, viewer: MaybeUser) -> list[CommentOut]:
    _get(db, event_id)
    comments = db.scalars(
        select(EventComment)
        .where(EventComment.event_id == event_id)
        .order_by(EventComment.created_at, EventComment.id)
        .limit(500)
    )
    return [_comment_out(c, viewer) for c in comments]


@router.post(
    "/events/{event_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Comenta o evento (precisa entrar na conta)",
    responses={**NOT_FOUND, 429: {"model": ErrorResponse}},
)
def add_comment(event_id: int, data: CommentCreate, db: SessionDep, user: CurrentUser):
    _get(db, event_id)
    if not user.is_owner:
        recent = db.scalar(
            select(func.count()).where(
                EventComment.user_id == user.id,
                EventComment.created_at >= utcnow() - COMMENT_WINDOW,
            )
        )
        if (recent or 0) >= COMMENTS_PER_WINDOW:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Você comentou muitas vezes em pouco tempo. Tente de novo em alguns minutos.",
            )
    comment = EventComment(event_id=event_id, user_id=user.id, body=data.body)
    comment.user = user
    db.add(comment)
    db.flush()
    return _comment_out(comment, user)


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Apaga um comentário (quem escreveu, ou a administração)",
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
def delete_comment(comment_id: int, db: SessionDep, user: CurrentUser) -> None:
    comment = db.get(EventComment, comment_id)
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comentário não encontrado.")
    if not (user.is_owner or comment.user_id == user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Você só pode apagar os seus comentários.")
    db.delete(comment)
