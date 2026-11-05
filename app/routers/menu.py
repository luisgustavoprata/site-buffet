"""Cardápio: aparece na página inicial e na aba Gestão › Cardápio (onde a dona edita)."""

import json
from pathlib import Path

from fastapi import APIRouter
from sqlalchemy.orm import Session

from app.deps import OwnerUser, SessionDep
from app.models import MenuContent
from app.schemas import MenuIn, MenuOut
from app.services import delete_unused_images, menu_image_ids

router = APIRouter(tags=["Cardápio"])

MENU_ID = 1
DEFAULT = Path(__file__).resolve().parent.parent / "menu_default.json"


def current_menu(db: Session) -> MenuOut:
    row = db.get(MenuContent, MENU_ID)
    if row is None:
        return MenuOut.model_validate(json.loads(DEFAULT.read_text(encoding="utf-8")))
    return MenuOut.model_validate({**row.data, "updated_at": row.updated_at})


@router.get("/menu", response_model=MenuOut, summary="Cardápio do buffet (público)")
def read_menu(db: SessionDep) -> MenuOut:
    menu = current_menu(db)
    if not menu.show_prices:
        for package in menu.packages:
            package.prices = []
    return menu


@router.get("/admin/menu", response_model=MenuOut, summary="Cardápio para editar")
def read_menu_admin(db: SessionDep, _owner: OwnerUser) -> MenuOut:
    return current_menu(db)


@router.put("/admin/menu", response_model=MenuOut, summary="Salva o cardápio")
def save_menu(payload: MenuIn, db: SessionDep, _owner: OwnerUser) -> MenuOut:
    before = menu_image_ids(db)
    row = db.get(MenuContent, MENU_ID)
    data = payload.model_dump()
    if row is None:
        row = MenuContent(id=MENU_ID, data=data)
        db.add(row)
    else:
        row.data = data
    db.flush()
    delete_unused_images(db, before - menu_image_ids(db))  # foto trocada no editor
    db.refresh(row)
    return current_menu(db)


@router.post("/admin/menu/restaurar", response_model=MenuOut, summary="Volta ao cardápio do PDF")
def reset_menu(db: SessionDep, _owner: OwnerUser) -> MenuOut:
    before = menu_image_ids(db)
    row = db.get(MenuContent, MENU_ID)
    if row is not None:
        db.delete(row)
        db.flush()
    delete_unused_images(db, before)
    return current_menu(db)
