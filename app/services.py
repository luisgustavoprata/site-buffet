"""Regras que mais de uma rota usa: conteúdo do site e limpeza de fotos sem uso."""

from collections.abc import Iterable

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import BioPhoto, EventPhoto, Image, SiteContent

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
    found = set(db.scalars(select(Image.id).where(Image.id.in_(ids))))
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
        db.execute(delete(Image).where(Image.id.in_(unused)))
