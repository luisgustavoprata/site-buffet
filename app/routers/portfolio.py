"""Portfólio: os eventos que o buffet já fez, com fotos."""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.deps import OwnerUser, SessionDep
from app.models import Event, EventPhoto
from app.schemas import ErrorResponse, EventIn, EventOut
from app.services import delete_unused_images, require_images

router = APIRouter(tags=["Portfólio"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Evento não encontrado."}}


def _get(db, event_id: int) -> Event:
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento não encontrado.")
    return event


@router.get("/events", response_model=list[EventOut], summary="Eventos do portfólio")
def list_events(
    db: SessionDep,
    event_type: str | None = Query(default=None, description="Filtra pelo tipo de evento."),
    limit: int = Query(default=60, ge=1, le=200),
) -> list[Event]:
    query = select(Event)
    if event_type:
        query = query.where(Event.event_type == event_type)
    # Mais recentes primeiro; eventos sem data ficam por último.
    query = query.order_by(Event.event_date.is_(None), Event.event_date.desc(), Event.id.desc())
    return list(db.scalars(query.limit(limit)))


@router.get("/events/types", response_model=list[str], summary="Tipos com eventos publicados")
def event_types(db: SessionDep) -> list[str]:
    rows = db.execute(
        select(Event.event_type, func.count()).group_by(Event.event_type).order_by(Event.event_type)
    )
    return [row[0] for row in rows]


@router.get("/events/{event_id}", response_model=EventOut, summary="Um evento", responses=NOT_FOUND)
def read_event(event_id: int, db: SessionDep) -> Event:
    return _get(db, event_id)


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
