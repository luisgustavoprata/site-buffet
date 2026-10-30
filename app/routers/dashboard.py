"""Resultados: os números da planilha do buffet, para a dona ver no painel e no celular.

A planilha (.ods ou .xlsx) é lida no navegador da dona. O site guarda só o resumo em JSON,
para que o painel abra em qualquer aparelho com os números mais recentes que ela enviou.
"""

import json

from fastapi import APIRouter, HTTPException, status

from app.deps import OwnerUser, SessionDep
from app.models import Dashboard, utcnow
from app.schemas import DashboardIn, DashboardOut, ErrorResponse

router = APIRouter(tags=["Resultados"])

MAX_BYTES = 2_000_000
REQUIRED_KEYS = ("dre", "estoque")


def dashboard_out(row: Dashboard) -> DashboardOut:
    return DashboardOut(
        file_name=row.file_name, updated_at=row.updated_at, data=json.loads(row.data)
    )


@router.get(
    "/admin/dashboard",
    response_model=DashboardOut,
    summary="Últimos números enviados da planilha (só a administração)",
    responses={404: {"model": ErrorResponse, "description": "Nenhuma planilha enviada ainda"}},
)
def read_dashboard(db: SessionDep, _owner: OwnerUser) -> DashboardOut:
    row = db.get(Dashboard, 1)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nenhuma planilha enviada ainda.")
    return dashboard_out(row)


@router.put(
    "/admin/dashboard",
    response_model=DashboardOut,
    summary="Envia os números da planilha (só a administração)",
    description="Substitui o resumo guardado. `data` precisa ter pelo menos `dre` e `estoque`.",
    responses={
        413: {"model": ErrorResponse, "description": "Resumo grande demais"},
        422: {"model": ErrorResponse, "description": "Não é a planilha do buffet"},
    },
)
def save_dashboard(payload: DashboardIn, db: SessionDep, _owner: OwnerUser) -> DashboardOut:
    if any(key not in payload.data for key in REQUIRED_KEYS):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Esta não parece ser a planilha do buffet: faltam o DRE e o Estoque.",
        )
    raw = json.dumps(payload.data, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode()) > MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, "Planilha grande demais para enviar (máximo 2 MB)."
        )
    row = db.get(Dashboard, 1)
    if row is None:
        row = Dashboard(id=1, file_name=payload.file_name, data=raw)
        db.add(row)
    else:
        row.file_name = payload.file_name
        row.data = raw
        row.updated_at = utcnow()
    db.flush()
    return dashboard_out(row)
