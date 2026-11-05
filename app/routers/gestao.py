"""Gestão do buffet no painel: estoque, compras, saídas, eventos, despesas, DRE e precificação.

Substitui a planilha (.ods): a dona lança tudo aqui e o site faz as contas (veja app/finance.py).
Só a administração acessa.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, extract, func, select
from sqlalchemy.orm import Session

from app import finance
from app.deps import OwnerUser, SessionDep, TodayDep
from app.models import (
    Expense,
    ExpenseCategory,
    FinanceEvent,
    PricingSim,
    Quote,
    QuoteStatus,
    StockIn,
    StockItem,
    StockOut,
)
from app.schemas import (
    ErrorResponse,
    ExpenseCategoryIn,
    ExpenseCategoryOut,
    ExpenseIn,
    ExpenseOut,
    FinanceConfigIn,
    FinanceConfigOut,
    FinanceEventIn,
    FinanceEventOut,
    FinanceImport,
    PricingIn,
    PricingOut,
    StockInIn,
    StockInOut,
    StockItemIn,
    StockItemOut,
    StockOutIn,
    StockOutOut,
)

router = APIRouter(prefix="/admin/gestao", tags=["Gestão"])

NOT_FOUND = {404: {"model": ErrorResponse, "description": "Não encontrado."}}


def _get(db: Session, model, row_id: int, label: str):
    row = db.get(model, row_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} não encontrado.")
    return row


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def _period(query, column, year: int | None, month: int | None):
    if year:
        query = query.where(extract("year", column) == year)
    if month:
        query = query.where(extract("month", column) == month)
    return query


# ---------- Parâmetros e categorias ----------


def _config_out(db: Session) -> FinanceConfigOut:
    out = FinanceConfigOut.model_validate(finance.ensure_defaults(db))
    out.groups = list(finance.DRE_GROUPS)
    return out


@router.get("/config", response_model=FinanceConfigOut, summary="Alíquotas e listas")
def read_config(db: SessionDep, _owner: OwnerUser) -> FinanceConfigOut:
    return _config_out(db)


@router.put("/config", response_model=FinanceConfigOut, summary="Altera alíquotas e listas")
def save_config(payload: FinanceConfigIn, db: SessionDep, _owner: OwnerUser) -> FinanceConfigOut:
    settings = finance.ensure_defaults(db)
    for key, value in payload.model_dump().items():
        setattr(settings, key, value)
    db.flush()
    return _config_out(db)


@router.get("/categorias", response_model=list[ExpenseCategoryOut], summary="Categorias de despesa")
def list_categories(db: SessionDep, _owner: OwnerUser) -> list[ExpenseCategory]:
    finance.ensure_defaults(db)
    return list(db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.position)))


def _unique_category(db: Session, name: str, current: int | None = None) -> None:
    other = db.scalar(select(ExpenseCategory).where(ExpenseCategory.name == name))
    if other is not None and other.id != current:
        raise _invalid(f"Já existe a categoria “{name}”.")


@router.post("/categorias", response_model=ExpenseCategoryOut, status_code=201)
def create_category(
    payload: ExpenseCategoryIn, db: SessionDep, _owner: OwnerUser
) -> ExpenseCategory:
    finance.ensure_defaults(db)
    _unique_category(db, payload.name)
    last = db.scalar(select(func.max(ExpenseCategory.position))) or 0
    row = ExpenseCategory(name=payload.name, group=payload.group, position=last + 1)
    db.add(row)
    db.flush()
    return row


@router.put("/categorias/{category_id}", response_model=ExpenseCategoryOut, responses=NOT_FOUND)
def update_category(
    category_id: int, payload: ExpenseCategoryIn, db: SessionDep, _owner: OwnerUser
) -> ExpenseCategory:
    row = _get(db, ExpenseCategory, category_id, "Categoria")
    _unique_category(db, payload.name, row.id)
    row.name, row.group = payload.name, payload.group
    db.flush()
    return row


@router.delete("/categorias/{category_id}", status_code=204, responses=NOT_FOUND)
def delete_category(category_id: int, db: SessionDep, _owner: OwnerUser) -> Response:
    row = _get(db, ExpenseCategory, category_id, "Categoria")
    if db.scalar(select(Expense.id).where(Expense.category_id == row.id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Esta categoria tem despesas lançadas. Mude a categoria delas antes de apagar.",
        )
    db.delete(row)
    return Response(status_code=204)


# ---------- Insumos (estoque) ----------


def _position(db: Session, item_id: int) -> dict:
    return next(p for p in finance.stock_positions(db) if p["id"] == item_id)


@router.get("/insumos", response_model=list[StockItemOut], summary="Insumos e posição do estoque")
def list_items(db: SessionDep, _owner: OwnerUser) -> list[dict]:
    return finance.stock_positions(db)


def _save_item(db: Session, row: StockItem, payload: StockItemIn) -> None:
    code = payload.code.strip().upper() or finance.next_code(
        db, StockItem, finance.item_prefix(payload.category)
    )
    other = db.scalar(select(StockItem).where(StockItem.code == code))
    if other is not None and other is not row:
        raise _invalid(f"O código {code} já é de outro insumo ({other.name}).")
    data = payload.model_dump()
    data["code"] = code
    for key, value in data.items():
        setattr(row, key, value)


@router.post("/insumos", response_model=StockItemOut, status_code=201)
def create_item(payload: StockItemIn, db: SessionDep, _owner: OwnerUser) -> dict:
    row = StockItem()
    _save_item(db, row, payload)
    db.add(row)
    db.flush()
    return _position(db, row.id)


@router.put("/insumos/{item_id}", response_model=StockItemOut, responses=NOT_FOUND)
def update_item(item_id: int, payload: StockItemIn, db: SessionDep, _owner: OwnerUser) -> dict:
    row = _get(db, StockItem, item_id, "Insumo")
    _save_item(db, row, payload)
    finance.revalue(db, [row.id])  # estoque/custo inicial mudam o custo das saídas
    return _position(db, row.id)


@router.delete("/insumos/{item_id}", status_code=204, responses=NOT_FOUND)
def delete_item(item_id: int, db: SessionDep, _owner: OwnerUser) -> Response:
    row = _get(db, StockItem, item_id, "Insumo")
    used = db.scalar(select(StockIn.id).where(StockIn.item_id == row.id).limit(1)) or db.scalar(
        select(StockOut.id).where(StockOut.item_id == row.id).limit(1)
    )
    if used:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este insumo tem compras ou saídas lançadas. Desative-o em vez de apagar.",
        )
    db.delete(row)
    return Response(status_code=204)


# ---------- Compras (entradas) ----------


def _stock_in_out(row: StockIn) -> StockInOut:
    return StockInOut(
        id=row.id,
        entry_date=row.entry_date,
        item_id=row.item_id,
        item_code=row.item.code,
        item_name=row.item.name,
        unit=row.item.unit,
        quantity=row.quantity,
        unit_cost=row.unit_cost,
        total=finance.r2(row.quantity * row.unit_cost),
        supplier=row.supplier,
        invoice=row.invoice,
    )


@router.get("/compras", response_model=list[StockInOut], summary="Compras de insumos")
def list_stock_in(
    db: SessionDep,
    _owner: OwnerUser,
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None, ge=1, le=12),
    insumo: int | None = Query(default=None),
) -> list[StockInOut]:
    query = _period(select(StockIn), StockIn.entry_date, ano, mes)
    if insumo:
        query = query.where(StockIn.item_id == insumo)
    rows = db.scalars(query.order_by(StockIn.entry_date.desc(), StockIn.id.desc()))
    return [_stock_in_out(r) for r in rows]


def _save_stock_in(db: Session, row: StockIn, payload: StockInIn) -> StockIn:
    _get(db, StockItem, payload.item_id, "Insumo")
    before = row.item_id
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    db.refresh(row)
    finance.revalue(db, list({row.item_id, before} - {None}))
    return row


@router.post("/compras", response_model=StockInOut, status_code=201)
def create_stock_in(payload: StockInIn, db: SessionDep, _owner: OwnerUser) -> StockInOut:
    return _stock_in_out(_save_stock_in(db, StockIn(), payload))


@router.put("/compras/{row_id}", response_model=StockInOut, responses=NOT_FOUND)
def update_stock_in(
    row_id: int, payload: StockInIn, db: SessionDep, _owner: OwnerUser
) -> StockInOut:
    return _stock_in_out(_save_stock_in(db, _get(db, StockIn, row_id, "Lançamento"), payload))


@router.delete("/compras/{row_id}", status_code=204, responses=NOT_FOUND)
def delete_stock_in(row_id: int, db: SessionDep, _owner: OwnerUser) -> Response:
    row = _get(db, StockIn, row_id, "Lançamento")
    item_id = row.item_id
    db.delete(row)
    finance.revalue(db, [item_id])
    return Response(status_code=204)


# ---------- Saídas ----------


def _stock_out_out(row: StockOut) -> StockOutOut:
    return StockOutOut(
        id=row.id,
        entry_date=row.entry_date,
        item_id=row.item_id,
        item_code=row.item.code,
        item_name=row.item.name,
        unit=row.item.unit,
        quantity=row.quantity,
        kind=row.kind,
        event_id=row.event_id,
        event_code=row.event.code if row.event else None,
        unit_cost=round(row.unit_cost, 4),
        total=finance.r2(row.quantity * row.unit_cost),
        note=row.note,
    )


@router.get("/saidas", response_model=list[StockOutOut], summary="Saídas de insumos")
def list_stock_out(
    db: SessionDep,
    _owner: OwnerUser,
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None, ge=1, le=12),
    insumo: int | None = Query(default=None),
    evento: int | None = Query(default=None),
) -> list[StockOutOut]:
    query = _period(select(StockOut), StockOut.entry_date, ano, mes)
    if insumo:
        query = query.where(StockOut.item_id == insumo)
    if evento:
        query = query.where(StockOut.event_id == evento)
    rows = db.scalars(query.order_by(StockOut.entry_date.desc(), StockOut.id.desc()))
    return [_stock_out_out(r) for r in rows]


def _save_stock_out(db: Session, row: StockOut, payload: StockOutIn) -> StockOut:
    _get(db, StockItem, payload.item_id, "Insumo")
    if payload.kind == "evento":
        if payload.event_id is None:
            raise _invalid("Saída para evento: escolha o evento (o custo vira CMV dele).")
        _get(db, FinanceEvent, payload.event_id, "Evento")
    before = row.item_id
    data = payload.model_dump()
    if payload.kind != "evento":
        data["event_id"] = None
    for key, value in data.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    finance.revalue(db, list({row.item_id, before} - {None}))
    db.refresh(row)
    return row


@router.post("/saidas", response_model=StockOutOut, status_code=201)
def create_stock_out(payload: StockOutIn, db: SessionDep, _owner: OwnerUser) -> StockOutOut:
    return _stock_out_out(_save_stock_out(db, StockOut(), payload))


@router.put("/saidas/{row_id}", response_model=StockOutOut, responses=NOT_FOUND)
def update_stock_out(
    row_id: int, payload: StockOutIn, db: SessionDep, _owner: OwnerUser
) -> StockOutOut:
    return _stock_out_out(_save_stock_out(db, _get(db, StockOut, row_id, "Lançamento"), payload))


@router.delete("/saidas/{row_id}", status_code=204, responses=NOT_FOUND)
def delete_stock_out(row_id: int, db: SessionDep, _owner: OwnerUser) -> Response:
    db.delete(_get(db, StockOut, row_id, "Lançamento"))
    return Response(status_code=204)


# ---------- Eventos (receitas) ----------


def _events_out(db: Session, rows: list[FinanceEvent]) -> list[FinanceEventOut]:
    results = finance.event_results(db, rows)
    out = []
    for row in rows:
        item = FinanceEventOut.model_validate(row)
        for key, value in results[row.id].items():
            setattr(item, key, value)
        out.append(item)
    return out


@router.get(
    "/eventos", response_model=list[FinanceEventOut], summary="Eventos com receita e margem"
)
def list_events(
    db: SessionDep,
    _owner: OwnerUser,
    ano: int | None = Query(default=None),
    situacao: str | None = Query(default=None),
) -> list[FinanceEventOut]:
    query = _period(select(FinanceEvent), FinanceEvent.event_date, ano, None)
    if situacao:
        query = query.where(FinanceEvent.status == situacao)
    rows = list(db.scalars(query.order_by(FinanceEvent.event_date.desc(), FinanceEvent.id.desc())))
    return _events_out(db, rows)


def _save_event(db: Session, row: FinanceEvent, payload: FinanceEventIn) -> FinanceEventOut:
    code = payload.code.strip().upper() or row.code or finance.next_code(db, FinanceEvent, "EV")
    other = db.scalar(select(FinanceEvent).where(FinanceEvent.code == code))
    if other is not None and other is not row:
        raise _invalid(f"O código {code} já é de outro evento ({other.client}).")
    if payload.discount > payload.guests * payload.price_per_guest:
        raise _invalid("O desconto é maior que o valor do evento.")
    if payload.quote_id is not None:
        _get(db, Quote, payload.quote_id, "Pedido de orçamento")
    data = payload.model_dump()
    data["code"] = code
    for key, value in data.items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    return _events_out(db, [row])[0]


@router.post("/eventos", response_model=FinanceEventOut, status_code=201)
def create_event(payload: FinanceEventIn, db: SessionDep, _owner: OwnerUser) -> FinanceEventOut:
    return _save_event(db, FinanceEvent(), payload)


@router.put("/eventos/{event_id}", response_model=FinanceEventOut, responses=NOT_FOUND)
def update_event(
    event_id: int, payload: FinanceEventIn, db: SessionDep, _owner: OwnerUser
) -> FinanceEventOut:
    return _save_event(db, _get(db, FinanceEvent, event_id, "Evento"), payload)


@router.delete("/eventos/{event_id}", status_code=204, responses=NOT_FOUND)
def delete_event(event_id: int, db: SessionDep, _owner: OwnerUser) -> Response:
    row = _get(db, FinanceEvent, event_id, "Evento")
    if db.scalar(select(StockOut.id).where(StockOut.event_id == row.id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Este evento tem saídas de estoque. Apague as saídas ou marque o evento "
            "como cancelado.",
        )
    db.delete(row)
    return Response(status_code=204)


@router.get(
    "/eventos/do-orcamento/{quote_id}",
    response_model=FinanceEventOut | None,
    summary="O evento criado a partir de um pedido de orçamento (se houver)",
)
def event_of_quote(quote_id: int, db: SessionDep, _owner: OwnerUser) -> FinanceEventOut | None:
    row = db.scalar(select(FinanceEvent).where(FinanceEvent.quote_id == quote_id))
    return _events_out(db, [row])[0] if row else None


@router.post(
    "/eventos/do-orcamento/{quote_id}",
    response_model=FinanceEventOut,
    status_code=201,
    responses=NOT_FOUND,
    summary="Cria o evento da gestão com os dados do pedido de orçamento",
)
def event_from_quote(quote_id: int, db: SessionDep, _owner: OwnerUser) -> FinanceEventOut:
    quote = _get(db, Quote, quote_id, "Pedido de orçamento")
    existing = db.scalar(select(FinanceEvent).where(FinanceEvent.quote_id == quote.id))
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Este pedido já virou o evento {existing.code}."
        )
    payload = FinanceEventIn(
        event_date=quote.event_date,
        client=f"{quote.client.name} ({quote.event_type.lower()})",
        event_type=quote.event_type,
        guests=quote.guests,
        price_per_guest=0,
        status="confirmado" if quote.status == QuoteStatus.CLOSED else "orcamento",
        quote_id=quote.id,
        notes=quote.location,
    )
    return _save_event(db, FinanceEvent(), payload)


# ---------- Despesas ----------


def _expense_out(row: Expense) -> ExpenseOut:
    return ExpenseOut(
        id=row.id,
        entry_date=row.entry_date,
        category_id=row.category_id,
        category=row.category.name,
        group=row.category.group,
        description=row.description,
        supplier=row.supplier,
        amount=row.amount,
        payment=row.payment,
        event_id=row.event_id,
        event_code=row.event.code if row.event else None,
    )


@router.get("/despesas", response_model=list[ExpenseOut], summary="Despesas")
def list_expenses(
    db: SessionDep,
    _owner: OwnerUser,
    ano: int | None = Query(default=None),
    mes: int | None = Query(default=None, ge=1, le=12),
    grupo: str | None = Query(default=None),
) -> list[ExpenseOut]:
    query = _period(select(Expense), Expense.entry_date, ano, mes)
    if grupo:
        query = query.join(ExpenseCategory).where(ExpenseCategory.group == grupo)
    rows = db.scalars(query.order_by(Expense.entry_date.desc(), Expense.id.desc()))
    return [_expense_out(r) for r in rows]


def _save_expense(db: Session, row: Expense, payload: ExpenseIn) -> ExpenseOut:
    _get(db, ExpenseCategory, payload.category_id, "Categoria")
    if payload.event_id is not None:
        _get(db, FinanceEvent, payload.event_id, "Evento")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.add(row)
    db.flush()
    db.refresh(row)
    return _expense_out(row)


@router.post("/despesas", response_model=ExpenseOut, status_code=201)
def create_expense(payload: ExpenseIn, db: SessionDep, _owner: OwnerUser) -> ExpenseOut:
    return _save_expense(db, Expense(), payload)


@router.put("/despesas/{row_id}", response_model=ExpenseOut, responses=NOT_FOUND)
def update_expense(
    row_id: int, payload: ExpenseIn, db: SessionDep, _owner: OwnerUser
) -> ExpenseOut:
    return _save_expense(db, _get(db, Expense, row_id, "Lançamento"), payload)


@router.delete("/despesas/{row_id}", status_code=204, responses=NOT_FOUND)
def delete_expense(row_id: int, db: SessionDep, _owner: OwnerUser) -> Response:
    db.delete(_get(db, Expense, row_id, "Lançamento"))
    return Response(status_code=204)


# ---------- DRE e resumo ----------


@router.get("/anos", response_model=list[int], summary="Anos com lançamentos")
def list_years(db: SessionDep, _owner: OwnerUser, today: TodayDep) -> list[int]:
    return finance.years_with_data(db, today)


@router.get("/dre", summary="DRE gerencial mês a mês")
def read_dre(
    db: SessionDep, _owner: OwnerUser, today: TodayDep, ano: int | None = Query(default=None)
) -> dict:
    return finance.dre(db, ano or today.year)


@router.get("/resumo", summary="Números do painel: DRE, eventos, despesas e alertas de estoque")
def summary(
    db: SessionDep, _owner: OwnerUser, today: TodayDep, ano: int | None = Query(default=None)
) -> dict:
    year = ano or today.year
    report = finance.dre(db, year)
    values = finance.dre_values(report)
    groups = [(finance.DIRECT, "direct", "Custo direto")] + [
        (g, g, g) for g in (*finance.OPEX_GROUPS, "Depreciação", "Despesa financeira")
    ]
    expenses = [{"name": label, "value": -values[key]["total"]} for _g, key, label in groups]
    expenses.insert(
        -2,
        {
            "name": "Perdas e consumo",
            "value": -(values["losses"]["total"] + values["internal"]["total"]),
        },
    )
    events = list(
        db.scalars(
            select(FinanceEvent)
            .where(
                extract("year", FinanceEvent.event_date) == year, FinanceEvent.status == "realizado"
            )
            .order_by(FinanceEvent.event_date)
        )
    )
    upcoming = list(
        db.scalars(
            select(FinanceEvent)
            .where(
                FinanceEvent.event_date >= today,
                FinanceEvent.status.in_(("orcamento", "confirmado")),
            )
            .order_by(FinanceEvent.event_date)
            .limit(8)
        )
    )
    stock = finance.stock_positions(db)
    alerts = [p for p in stock if p["active"] and p["status"] != "OK"]
    by_category: dict[str, float] = {}
    for p in stock:
        by_category[p["category"]] = by_category.get(p["category"], 0) + p["value"]
    return {
        "year": year,
        "today": today.isoformat(),
        "dre": report,
        "expenses": [e for e in expenses if abs(e["value"]) > 0.004],
        "events": [e.model_dump(mode="json") for e in _events_out(db, events)],
        "upcoming": [e.model_dump(mode="json") for e in _events_out(db, upcoming)],
        "stock_value": finance.r2(sum(p["value"] for p in stock)),
        "stock_by_category": [
            {"name": k, "value": finance.r2(v)}
            for k, v in sorted(by_category.items(), key=lambda x: -x[1])
            if v
        ],
        "alerts": alerts,
    }


# ---------- Precificação ----------


def _pricing_out(db: Session, sim: PricingSim, year: int) -> PricingOut:
    out = PricingOut.model_validate(sim)
    out.result = finance.price(db, sim, year)
    return out


def _check_margins(db: Session, payload: PricingIn) -> None:
    tax = finance.ensure_defaults(db).tax_rate
    if payload.profit_margin + tax >= 1:
        raise _invalid(
            f"Margem de lucro + impostos ({payload.profit_margin + tax:.0%}) precisa ficar abaixo "
            f"de 100%. Com {tax:.0%} de imposto, a margem vai até {1 - tax - 0.01:.0%}."
        )


@router.get("/precificacao", response_model=list[PricingOut], summary="Simulações de preço")
def list_pricing(db: SessionDep, _owner: OwnerUser, today: TodayDep) -> list[PricingOut]:
    sims = db.scalars(select(PricingSim).order_by(PricingSim.updated_at.desc(), PricingSim.id))
    return [_pricing_out(db, sim, today.year) for sim in sims]


@router.post("/precificacao/calcular", response_model=PricingOut, summary="Calcula sem salvar")
def preview_pricing(
    payload: PricingIn, db: SessionDep, _owner: OwnerUser, today: TodayDep
) -> PricingOut:
    _check_margins(db, payload)
    sim = PricingSim(**payload.model_dump())
    out = PricingOut.model_validate(sim)
    out.result = finance.price(db, sim, today.year)
    return out


@router.get("/precificacao/{sim_id}", response_model=PricingOut, responses=NOT_FOUND)
def read_pricing(sim_id: int, db: SessionDep, _owner: OwnerUser, today: TodayDep) -> PricingOut:
    return _pricing_out(db, _get(db, PricingSim, sim_id, "Simulação"), today.year)


@router.post("/precificacao", response_model=PricingOut, status_code=201)
def create_pricing(
    payload: PricingIn, db: SessionDep, _owner: OwnerUser, today: TodayDep
) -> PricingOut:
    _check_margins(db, payload)
    sim = PricingSim(**payload.model_dump())
    db.add(sim)
    db.flush()
    return _pricing_out(db, sim, today.year)


@router.put("/precificacao/{sim_id}", response_model=PricingOut, responses=NOT_FOUND)
def update_pricing(
    sim_id: int, payload: PricingIn, db: SessionDep, _owner: OwnerUser, today: TodayDep
) -> PricingOut:
    _check_margins(db, payload)
    sim = _get(db, PricingSim, sim_id, "Simulação")
    for key, value in payload.model_dump().items():
        setattr(sim, key, value)
    db.flush()
    return _pricing_out(db, sim, today.year)


@router.delete("/precificacao/{sim_id}", status_code=204, responses=NOT_FOUND)
def delete_pricing(sim_id: int, db: SessionDep, _owner: OwnerUser) -> Response:
    db.delete(_get(db, PricingSim, sim_id, "Simulação"))
    return Response(status_code=204)


# ---------- Backup e importação da planilha ----------


@router.get("/exportar", summary="Todos os dados da gestão (backup / planilha para o contador)")
def export_all(db: SessionDep, _owner: OwnerUser, today: TodayDep) -> dict:
    years = finance.years_with_data(db, today)
    return {
        "exported_at": today.isoformat(),
        "config": _config_out(db).model_dump(),
        "categories": [
            ExpenseCategoryOut.model_validate(c).model_dump()
            for c in db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.position))
        ],
        "items": finance.stock_positions(db),
        "stock_in": [
            r.model_dump(mode="json")
            for r in list_stock_in(db, _owner, ano=None, mes=None, insumo=None)
        ],
        "stock_out": [
            r.model_dump(mode="json")
            for r in list_stock_out(db, _owner, ano=None, mes=None, insumo=None, evento=None)
        ],
        "events": [
            r.model_dump(mode="json") for r in list_events(db, _owner, ano=None, situacao=None)
        ],
        "expenses": [
            r.model_dump(mode="json")
            for r in list_expenses(db, _owner, ano=None, mes=None, grupo=None)
        ],
        "dre": [finance.dre(db, y) for y in years],
    }


def _ref(lookup: dict, value, label: str, line: int, required: bool = True):
    key = str(value or "").strip().upper()
    if not key:
        if required:
            raise _invalid(f"{label} vazio na linha {line}.")
        return None
    if key not in lookup:
        raise _invalid(f"{label} “{value}” não existe (linha {line}).")
    return lookup[key]


def _date(value, label: str, line: int) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise _invalid(f"Data inválida em {label}, linha {line}: “{value}”.") from None


def _num(value, label: str, line: int, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise _invalid(f"Número inválido em {label}, linha {line}: “{value}”.") from None
    if number < 0 or (positive and number <= 0):
        raise _invalid(f"Em {label}, linha {line}: o valor precisa ser maior que zero.")
    return number


@router.post("/importar", summary="Importa a planilha antiga (substitui os dados da gestão)")
def import_all(payload: FinanceImport, db: SessionDep, _owner: OwnerUser) -> dict:
    return import_data(db, payload)


def import_data(db: Session, payload: FinanceImport) -> dict:
    """Apaga os lançamentos da gestão e grava os da planilha (também usado na demonstração)."""
    finance.ensure_defaults(db)
    for model in (StockOut, StockIn, Expense, PricingSim):
        db.execute(delete(model))
    db.execute(delete(FinanceEvent))
    db.execute(delete(StockItem))
    if payload.config is not None:
        save_config(payload.config, db, None)
    if payload.categories:
        db.execute(delete(ExpenseCategory))
        seen = set()
        for position, c in enumerate(payload.categories):
            if c.name in seen:
                continue
            seen.add(c.name)
            db.add(ExpenseCategory(name=c.name, group=c.group, position=position))
    db.flush()

    items: dict[str, StockItem] = {}
    for item in payload.items:
        row = StockItem()
        _save_item(db, row, item)
        db.add(row)
        db.flush()
        items[row.code] = row
        items.setdefault(row.name.upper(), row)
    events: dict[str, FinanceEvent] = {}
    for event in payload.events:
        row = FinanceEvent()
        _save_event(db, row, event)
        events[row.code] = row
    categories = {c.name.upper(): c for c in db.scalars(select(ExpenseCategory))}

    for n, r in enumerate(payload.stock_in, 1):
        item = _ref(items, r.get("item"), "Insumo (compras)", n)
        db.add(
            StockIn(
                entry_date=_date(r.get("date"), "Compras", n),
                item_id=item.id,
                quantity=_num(r.get("quantity"), "Compras", n, positive=True),
                unit_cost=_num(r.get("unit_cost"), "Compras", n),
                supplier=str(r.get("supplier") or "")[:120],
                invoice=str(r.get("invoice") or "")[:40],
            )
        )
    for n, r in enumerate(payload.stock_out, 1):
        item = _ref(items, r.get("item"), "Insumo (saídas)", n)
        kind = r.get("kind")
        if kind not in finance.OUT_KINDS:
            raise _invalid(f"Tipo de saída inválido na linha {n}: “{kind}”.")
        event = _ref(events, r.get("event"), "Evento (saídas)", n, required=kind == "evento")
        db.add(
            StockOut(
                entry_date=_date(r.get("date"), "Saídas", n),
                item_id=item.id,
                quantity=_num(r.get("quantity"), "Saídas", n, positive=True),
                kind=kind,
                event_id=event.id if event and kind == "evento" else None,
                note=str(r.get("note") or "")[:200],
            )
        )
    for n, r in enumerate(payload.expenses, 1):
        category = _ref(categories, r.get("category"), "Categoria (despesas)", n)
        event = _ref(events, r.get("event"), "Evento (despesas)", n, required=False)
        db.add(
            Expense(
                entry_date=_date(r.get("date"), "Despesas", n),
                category_id=category.id,
                description=str(r.get("description") or "")[:200],
                supplier=str(r.get("supplier") or "")[:120],
                amount=_num(r.get("amount"), "Despesas", n, positive=True),
                payment=str(r.get("payment") or "")[:40],
                event_id=event.id if event else None,
            )
        )
    warnings = []
    tax = finance.ensure_defaults(db).tax_rate
    for n, r in enumerate(payload.pricing, 1):
        lines = []
        for entry in r.get("items") or []:
            item = items.get(str(entry.get("item") or "").strip().upper())
            kind = entry.get("kind") if entry.get("kind") in finance.PRICING_KINDS else "Comida"
            per_guest = _num(entry.get("per_guest"), "Precificação", n)
            if item is not None and per_guest > 0:
                lines.append({"item_id": item.id, "kind": kind, "per_guest": per_guest})
        margin = _num(r.get("profit_margin", 0.2), "Precificação", n)
        if margin + tax >= 1:
            warnings.append(
                f"Precificação: a margem de lucro de {margin:.0%} somada aos impostos passava de "
                "100% (o preço ficava negativo). Ela foi trocada por 30%; ajuste se quiser."
            )
            margin = 0.3
        db.add(
            PricingSim(
                name=str(r.get("name") or "Simulação")[:120],
                event_type=str(r.get("event_type") or "")[:40],
                guests=max(1, int(_num(r.get("guests", 100), "Precificação", n))),
                safety_margin=min(2.0, _num(r.get("safety_margin", 0.1), "Precificação", n)),
                profit_margin=margin,
                items=lines,
            )
        )
    finance.revalue(db)
    return {
        "warnings": warnings,
        "pricing": len(payload.pricing),
        "items": len(payload.items),
        "events": len(payload.events),
        "stock_in": len(payload.stock_in),
        "stock_out": len(payload.stock_out),
        "expenses": len(payload.expenses),
    }
