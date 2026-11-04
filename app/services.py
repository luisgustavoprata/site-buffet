"""Regras que mais de uma rota usa: conteúdo do site e limpeza de fotos sem uso."""

from collections.abc import Iterable
from datetime import timedelta

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.images import InvalidImage, process_upload
from app.models import BioPhoto, EventPhoto, Image, SiteContent, utcnow

SITE_ID = 1


def get_site(db: Session) -> SiteContent:
    site = db.get(SiteContent, SITE_ID)
    if site is None:
        site = SiteContent(id=SITE_ID, business_name="Meu Buffet")
        db.add(site)
        db.flush()
    return site


def require_images(db: Session, image_ids: Iterable[int]) -> None:
    ids = {i for i in image_ids if i is not None}
    if not ids:
        return
    found = set(db.scalars(select(Image.id).where(Image.id.in_(ids), Image.access_key.is_(None))))
    missing = ids - found
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Foto não encontrada: {sorted(missing)[0]}. Envie a foto antes de usá-la.",
        )


def delete_unused_images(db: Session, image_ids: Iterable[int]) -> None:
    """Apaga as fotos que deixaram de aparecer no site (capa, biografia ou portfólio)."""
    ids = {i for i in image_ids if i is not None}
    if not ids:
        return
    db.flush()
    in_use = set(db.scalars(select(BioPhoto.image_id).where(BioPhoto.image_id.in_(ids))))
    in_use |= set(db.scalars(select(EventPhoto.image_id).where(EventPhoto.image_id.in_(ids))))
    site = db.get(SiteContent, SITE_ID)
    if site is not None:
        in_use |= {site.hero_image_id, site.owner_image_id, site.history_image_id}
    unused = ids - in_use
    if unused:
        db.execute(delete(Image).where(Image.id.in_(unused), Image.access_key.is_(None)))


async def store_upload(
    db: Session, file: UploadFile, settings: Settings, access_key: str | None = None
) -> Image:
    """Lê a foto enviada (com limite de tamanho), trata no Pillow e guarda no banco."""
    limit = settings.max_upload_mb * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"A foto passa de {settings.max_upload_mb} MB. Envie uma versão menor.",
        )
    try:
        processed = process_upload(raw)
    except InvalidImage as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    image = Image(
        data=processed.data,
        content_type=processed.content_type,
        width=processed.width,
        height=processed.height,
        access_key=access_key,
    )
    db.add(image)
    db.flush()
    return image


def delete_orphan_images(db: Session, older_than: timedelta = timedelta(days=1)) -> int:
    """Fotos enviadas no painel que nunca chegaram ao site (ex.: evento cancelado).

    Só as públicas e com mais de um dia: quem está editando agora não perde nada.
    """
    site = db.get(SiteContent, SITE_ID)
    fields = (site.hero_image_id, site.owner_image_id, site.history_image_id) if site else ()
    on_site = [i for i in fields if i]
    used = or_(
        Image.id.in_(select(BioPhoto.image_id)),
        Image.id.in_(select(EventPhoto.image_id)),
        Image.id.in_(on_site),
    )
    result = db.execute(
        delete(Image).where(
            Image.access_key.is_(None), Image.created_at < utcnow() - older_than, ~used
        )
    )
    return result.rowcount or 0
