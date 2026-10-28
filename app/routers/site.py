"""Apresentação do buffet (textos e fotos) e envio de imagens."""

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from fastapi import Path as PathParam
from sqlalchemy import func, select

from app.deps import OwnerUser, SessionDep, SettingsDep
from app.images import InvalidImage, process_upload
from app.models import BioPhoto, Image
from app.schemas import (
    BioPhotoCreate,
    BioPhotoOut,
    ErrorResponse,
    ImageOut,
    SiteOut,
    SiteUpdate,
)
from app.services import delete_unused_images, get_site, require_images

router = APIRouter(tags=["Site"])

IMAGE_FIELDS = ("hero_image_id", "owner_image_id", "history_image_id")


def site_out(db) -> SiteOut:
    out = SiteOut.model_validate(get_site(db))
    photos = db.scalars(select(BioPhoto).order_by(BioPhoto.position, BioPhoto.id))
    out.bio_photos = [BioPhotoOut.model_validate(photo) for photo in photos]
    return out


@router.get("/site", response_model=SiteOut, summary="Textos e fotos da apresentação")
def read_site(db: SessionDep) -> SiteOut:
    return site_out(db)


@router.patch(
    "/admin/site",
    response_model=SiteOut,
    summary="Edita a apresentação (só a administração)",
    description="Envie só o que muda. Fotos: primeiro envie em `POST /admin/images`.",
)
def update_site(data: SiteUpdate, db: SessionDep, _owner: OwnerUser) -> SiteOut:
    site = get_site(db)
    changes = data.model_dump(exclude_unset=True)
    require_images(db, [changes[f] for f in IMAGE_FIELDS if changes.get(f)])
    replaced = [getattr(site, f) for f in IMAGE_FIELDS if f in changes]
    for field, value in changes.items():
        if value is None and field not in (*IMAGE_FIELDS, "founded_year"):
            continue  # textos não viram "nulo"; para apagar, envie ""
        setattr(site, field, value)
    delete_unused_images(db, replaced)
    return site_out(db)


@router.post(
    "/admin/site/bio-photos",
    response_model=SiteOut,
    status_code=status.HTTP_201_CREATED,
    summary="Adiciona uma foto à seção Sobre mim",
)
def add_bio_photo(data: BioPhotoCreate, db: SessionDep, _owner: OwnerUser) -> SiteOut:
    require_images(db, [data.image_id])
    position = (db.scalar(select(func.max(BioPhoto.position))) or 0) + 1
    db.add(BioPhoto(image_id=data.image_id, caption=data.caption, position=position))
    db.flush()
    return site_out(db)


@router.delete(
    "/admin/site/bio-photos/{photo_id}",
    response_model=SiteOut,
    summary="Tira uma foto da seção Sobre mim",
    responses={404: {"model": ErrorResponse}},
)
def remove_bio_photo(photo_id: int, db: SessionDep, _owner: OwnerUser) -> SiteOut:
    photo = db.get(BioPhoto, photo_id)
    if photo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foto não encontrada.")
    image_id = photo.image_id
    db.delete(photo)
    delete_unused_images(db, [image_id])
    return site_out(db)


@router.post(
    "/admin/images",
    response_model=ImageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Envia uma foto (JPG, PNG ou WebP)",
    description="A foto é reduzida para no máximo 1920 px e perde os dados de GPS/EXIF.",
    responses={413: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def upload_image(
    file: Annotated[UploadFile, File(description="A foto.")],
    db: SessionDep,
    settings: SettingsDep,
    _owner: OwnerUser,
) -> Image:
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
    )
    db.add(image)
    db.flush()
    return image


@router.get(
    "/media/{image_id}",
    summary="Arquivo de uma foto",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/webp": {}}}, 404: {}},
)
def read_image(image_id: Annotated[int, PathParam(ge=1)], db: SessionDep) -> Response:
    row = db.execute(select(Image.data, Image.content_type).where(Image.id == image_id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Foto não encontrada.")
    # Cada foto tem um id próprio e nunca muda: o navegador pode guardar por um ano.
    return Response(
        content=row.data,
        media_type=row.content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
