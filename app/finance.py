"""Gestão do buffet: as contas que a planilha fazia (estoque, custo médio, DRE e precificação).

Regras contábeis (as mesmas da planilha, com uma melhoria no custo):
- Compra de insumo não é despesa: vira estoque. O custo entra no DRE quando o insumo sai.
- Custo médio móvel: cada saída usa o custo médio do dia em que aconteceu. Compras mais novas
  não mudam o CMV de meses passados; uma compra antiga lançada depois recalcula as saídas.
- Receita no mês da data do evento, só para eventos "realizado" (regime de competência).
"""

import math
import re
from collections import defaultdict
from datetime import date

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.models import (
    Expense,
    ExpenseCategory,
    FinanceEvent,
    FinanceSettings,
    PricingSim,
    StockIn,
    StockItem,
    StockOut,
)

SETTINGS_ID = 1

# Linhas do DRE em que uma categoria de despesa pode cair.
DIRECT = "Custo direto do evento"
DRE_GROUPS = (
    DIRECT,
    "Pessoal",
    "Ocupação",
    "Utilidades",
    "Comercial",
    "Administrativa",
    "Manutenção",
    "Depreciação",
    "Despesa financeira",
    "Receita financeira",
)
EVENT_STATUS = ("orcamento", "confirmado", "realizado", "cancelado")
OUT_KINDS = ("evento", "perda", "consumo")
PRICING_KINDS = ("Comida", "Bebidas", "Descartáveis")

DEFAULT_ITEM_CATEGORIES = [
    "Carnes",
    "Peixes e frutos do mar",
    "Frios e embutidos",
    "Laticínios e ovos",
    "Congelados",
    "Verduras e legumes",
    "Frutas",
    "Mercearia",
    "Bebidas não alcoólicas",
    "Bebidas alcoólicas",
    "Descartáveis",
    "Limpeza",
]
DEFAULT_UNITS = ["kg", "g", "L", "ml", "un", "pct", "cx", "dz", "cento", "rolo", "maço", "bandeja"]
DEFAULT_EVENT_TYPES = [
    "Casamento",
    "Aniversário",
    "Infantil",
    "15 anos",
    "Corporativo",
    "Formatura",
    "Batizado",
    "Chá de bebê",
    "Confraternização",
    "Outro",
]
DEFAULT_PAYMENTS = ["PIX", "Boleto", "Cartão", "Dinheiro", "Transferência", "Débito automático"]
DEFAULT_EXPENSE_CATEGORIES = [
    ("Freelancers (garçons, copeiros, cozinheiros)", DIRECT),
    ("Locação de equipamentos e louças", DIRECT),
    ("Transporte/frete de eventos", DIRECT),
    ("Serviços terceirizados (decoração, som)", DIRECT),
    ("Salários", "Pessoal"),
    ("Encargos (INSS, FGTS)", "Pessoal"),
    ("Benefícios (VT, VA)", "Pessoal"),
    ("Pró-labore", "Pessoal"),
    ("Aluguel", "Ocupação"),
    ("IPTU / condomínio", "Ocupação"),
    ("Energia elétrica", "Utilidades"),
    ("Água e esgoto", "Utilidades"),
    ("Gás GLP", "Utilidades"),
    ("Internet e telefone", "Utilidades"),
    ("Marketing e anúncios", "Comercial"),
    ("Comissões de venda", "Comercial"),
    ("Contabilidade", "Administrativa"),
    ("Sistemas e software", "Administrativa"),
    ("Material de escritório", "Administrativa"),
    ("Taxas, alvarás e licenças", "Administrativa"),
    ("Manutenção de equipamentos", "Manutenção"),
    ("Manutenção predial", "Manutenção"),
    ("Depreciação", "Depreciação"),
    ("Tarifas bancárias / maquininha", "Despesa financeira"),
    ("Juros e multas", "Despesa financeira"),
    ("Rendimentos de aplicações", "Receita financeira"),
]


def r2(value: float) -> float:
    return round(value + 0.0, 2)


def ensure_defaults(db: Session) -> FinanceSettings:
    """Cria os parâmetros e as categorias de despesa na primeira vez que a gestão abre."""
    settings = db.get(FinanceSettings, SETTINGS_ID)
    if settings is None:
        settings = FinanceSettings(
            id=SETTINGS_ID,
            tax_rate=0.08,
            income_tax_rate=0.0,
            item_categories=list(DEFAULT_ITEM_CATEGORIES),
            units=list(DEFAULT_UNITS),
            event_types=list(DEFAULT_EVENT_TYPES),
            payment_methods=list(DEFAULT_PAYMENTS),
        )
        db.add(settings)
        if db.scalar(select(ExpenseCategory.id).limit(1)) is None:
            for position, (name, group) in enumerate(DEFAULT_EXPENSE_CATEGORIES):
                db.add(ExpenseCategory(name=name, group=group, position=position))
        db.flush()
    return settings


def next_code(db: Session, model, prefix: str) -> str:
    """O próximo código livre: EV001, EV002... (ou CAR001 para insumos de Carnes)."""
    numbers = [0]
    for code in db.scalars(select(model.code).where(model.code.like(f"{prefix}%"))):
        match = re.fullmatch(rf"{re.escape(prefix)}(\d+)", code)
        if match:
            numbers.append(int(match.group(1)))
    return f"{prefix}{max(numbers) + 1:03d}"


def item_prefix(category: str) -> str:
    letters = re.sub(
        r"[^A-Z]", "", category.upper().translate(str.maketrans("ÁÂÃÉÊÍÓÔÕÚÇ", "AAAEEIOOOUC"))
    )
    return (letters[:3] or "INS").ljust(3, "X")


# ---------- Estoque e custo médio ----------


def _movements(db: Session, item_ids: list[int] | None = None):
    ins = select(StockIn)
    outs = select(StockOut)
    if item_ids is not None:
        ins = ins.where(StockIn.item_id.in_(item_ids))
        outs = outs.where(StockOut.item_id.in_(item_ids))
    by_item: dict[int, list] = defaultdict(list)
    for row in db.scalars(ins):
        by_item[row.item_id].append((row.entry_date, 0, row.id, row))
    for row in db.scalars(outs):
        by_item[row.item_id].append((row.entry_date, 1, row.id, row))
    for moves in by_item.values():
        moves.sort(key=lambda m: m[:3])  # no mesmo dia, as compras vêm antes das saídas
    return by_item


def revalue(db: Session, item_ids: list[int] | None = None) -> None:
    """Recalcula o custo médio de cada saída dos insumos informados (ou de todos)."""
    db.flush()
    items = {i.id: i for i in db.scalars(select(StockItem))}
    for item_id, moves in _movements(db, item_ids).items():
        item = items[item_id]
        qty, avg = item.initial_stock, item.initial_cost
        for _d, kind, _id, row in moves:
            if kind == 0:
                avg = (
                    row.unit_cost
                    if qty <= 0
                    else (qty * avg + row.quantity * row.unit_cost) / (qty + row.quantity)
                )
                qty += row.quantity
            else:
                if abs(row.unit_cost - avg) > 1e-9:
                    row.unit_cost = avg
                qty -= row.quantity
    db.flush()


def stock_status(balance: float, minimum: float) -> str:
    if balance < -1e-9:
        return "NEGATIVO"
    if abs(balance) <= 1e-9:
        return "SEM ESTOQUE"
    if balance < minimum:
        return "REPOR"
    return "OK"


def stock_positions(db: Session) -> list[dict]:
    """Posição de cada insumo: entradas, saídas, saldo, custo médio, valor e status."""
    items = list(db.scalars(select(StockItem).order_by(StockItem.category, StockItem.code)))
    moves = _movements(db)
    out = []
    for item in items:
        qty, avg = item.initial_stock, item.initial_cost
        total_in = total_out = 0.0
        for _d, kind, _id, row in moves.get(item.id, []):
            if kind == 0:
                avg = (
                    row.unit_cost
                    if qty <= 0
                    else (qty * avg + row.quantity * row.unit_cost) / (qty + row.quantity)
                )
                qty += row.quantity
                total_in += row.quantity
            else:
                qty -= row.quantity
                total_out += row.quantity
        suggestion = max(0.0, 2 * item.min_stock - qty) if qty < item.min_stock else 0.0
        out.append(
            {
                "id": item.id,
                "code": item.code,
                "name": item.name,
                "category": item.category,
                "unit": item.unit,
                "min_stock": item.min_stock,
                "initial_stock": item.initial_stock,
                "initial_cost": item.initial_cost,
                "active": item.active,
                "total_in": round(total_in, 3),
                "total_out": round(total_out, 3),
                "balance": round(qty, 3),
                "avg_cost": round(avg, 4),
                "value": r2(max(0.0, qty) * avg),
                "status": stock_status(qty, item.min_stock),
                "suggestion": round(suggestion, 3),
            }
        )
    return out


# ---------- Eventos ----------


def event_results(db: Session, events: list[FinanceEvent]) -> dict[int, dict]:
    """Receita, CMV, custos diretos e margem de cada evento."""
    ids = [e.id for e in events]
    cmv: dict[int, float] = defaultdict(float)
    direct: dict[int, float] = defaultdict(float)
    if ids:
        for row in db.scalars(
            select(StockOut).where(StockOut.event_id.in_(ids), StockOut.kind == "evento")
        ):
            cmv[row.event_id] += row.quantity * row.unit_cost
        for row in db.scalars(select(Expense).where(Expense.event_id.in_(ids))):
            if row.category.group == DIRECT:
                direct[row.event_id] += row.amount
    out = {}
    for e in events:
        gross = e.guests * e.price_per_guest
        net = gross - e.discount
        c = cmv[e.id]
        d = direct[e.id]
        out[e.id] = {
            "gross": r2(gross),
            "net": r2(net),
            "cmv": r2(c),
            "direct_costs": r2(d),
            "cmv_per_guest": r2(c / e.guests) if e.guests else 0.0,
            "margin_on_inputs": round((net - c) / net, 4) if net else 0.0,
            "contribution": r2(net - c - d),
        }
    return out


# ---------- DRE ----------

DRE_LINES = [
    # chave, rótulo, tipo (line | total | pct | head)
    ("gross", "Receita bruta de eventos", "total"),
    ("discounts", "(-) Descontos concedidos", "line"),
    ("taxes", "(-) Impostos sobre o faturamento", "line"),
    ("net", "Receita líquida", "total"),
    ("cmv", "(-) CMV: insumos consumidos nos eventos", "line"),
    ("direct", "(-) Custos diretos dos eventos (mão de obra extra, locações, frete)", "line"),
    ("gross_profit", "Lucro bruto", "total"),
    ("gross_margin", "Margem bruta", "pct"),
    ("opex_head", "Despesas operacionais", "head"),
    ("Pessoal", "(-) Pessoal (salários, encargos, benefícios, pró-labore)", "line"),
    ("Ocupação", "(-) Ocupação (aluguel, IPTU)", "line"),
    ("Utilidades", "(-) Utilidades (energia, água, gás, internet)", "line"),
    ("Comercial", "(-) Comerciais (marketing, comissões)", "line"),
    ("Administrativa", "(-) Administrativas", "line"),
    ("Manutenção", "(-) Manutenção", "line"),
    ("losses", "(-) Perdas e quebras de estoque", "line"),
    ("internal", "(-) Consumo interno (refeição da equipe etc.)", "line"),
    ("opex", "Total despesas operacionais", "total"),
    ("ebitda", "EBITDA", "total"),
    ("Depreciação", "(-) Depreciação", "line"),
    ("ebit", "Resultado operacional (EBIT)", "total"),
    ("Receita financeira", "(+) Receitas financeiras", "line"),
    ("Despesa financeira", "(-) Despesas financeiras (tarifas, maquininha, juros)", "line"),
    ("ebt", "Resultado antes do IR/CSLL", "total"),
    ("income_tax", "(-) IR/CSLL", "line"),
    ("net_profit", "Lucro líquido", "total"),
    ("net_margin", "Margem líquida", "pct"),
]
OPEX_GROUPS = ("Pessoal", "Ocupação", "Utilidades", "Comercial", "Administrativa", "Manutenção")
INDICATORS = [
    ("events", "Eventos realizados", "int"),
    ("guests", "Convidados atendidos", "int"),
    ("ticket", "Ticket médio por convidado (receita bruta)", "money"),
    ("cmv_per_guest", "CMV por convidado", "money"),
    ("cmv_pct", "CMV % da receita líquida", "pct"),
    ("purchases", "Compras de insumos (informativo, não entra no resultado)", "money"),
]


def _by_month(rows, year: int) -> list[float]:
    months = [0.0] * 12
    for when, value in rows:
        if when.year == year:
            months[when.month - 1] += value
    return months


def dre(db: Session, year: int) -> dict:
    settings = ensure_defaults(db)
    M = range(12)
    L: dict[str, list[float]] = {}

    events = [
        e
        for e in db.scalars(
            select(FinanceEvent).where(
                FinanceEvent.status == "realizado", extract("year", FinanceEvent.event_date) == year
            )
        )
    ]
    L["gross"] = _by_month(((e.event_date, e.guests * e.price_per_guest) for e in events), year)
    L["discounts"] = [-v for v in _by_month(((e.event_date, e.discount) for e in events), year)]
    L["taxes"] = [-L["gross"][i] * settings.tax_rate for i in M]
    L["net"] = [L["gross"][i] + L["discounts"][i] + L["taxes"][i] for i in M]

    outs = list(db.scalars(select(StockOut).where(extract("year", StockOut.entry_date) == year)))

    def out_sum(kind):
        rows = ((o.entry_date, o.quantity * o.unit_cost) for o in outs if o.kind == kind)
        return [-v for v in _by_month(rows, year)]

    L["cmv"] = out_sum("evento")
    L["losses"] = out_sum("perda")
    L["internal"] = out_sum("consumo")

    expenses = list(db.scalars(select(Expense).where(extract("year", Expense.entry_date) == year)))
    for group in DRE_GROUPS:
        rows = ((x.entry_date, x.amount) for x in expenses if x.category.group == group)
        sign = 1 if group == "Receita financeira" else -1
        L[group] = [sign * v for v in _by_month(rows, year)]
    L["direct"] = L.pop(DIRECT)

    L["gross_profit"] = [L["net"][i] + L["cmv"][i] + L["direct"][i] for i in M]
    L["opex"] = [sum(L[g][i] for g in OPEX_GROUPS) + L["losses"][i] + L["internal"][i] for i in M]
    L["ebitda"] = [L["gross_profit"][i] + L["opex"][i] for i in M]
    L["ebit"] = [L["ebitda"][i] + L["Depreciação"][i] for i in M]
    L["ebt"] = [L["ebit"][i] + L["Receita financeira"][i] + L["Despesa financeira"][i] for i in M]
    L["income_tax"] = [-max(0.0, L["ebt"][i]) * settings.income_tax_rate for i in M]
    L["net_profit"] = [L["ebt"][i] + L["income_tax"][i] for i in M]

    totals = {k: sum(v) for k, v in L.items()}

    def ratio(a, b):
        return [a[i] / b[i] if b[i] else 0.0 for i in M], (sum(a) / sum(b) if sum(b) else 0.0)

    L["gross_margin"], totals["gross_margin"] = ratio(L["gross_profit"], L["net"])
    L["net_margin"], totals["net_margin"] = ratio(L["net_profit"], L["net"])

    net_total = totals["net"]
    lines = []
    for key, label, kind in DRE_LINES:
        if kind == "head":
            lines.append({"key": key, "label": label, "kind": kind})
            continue
        values = L[key]
        digits = 4 if kind == "pct" else 2
        lines.append(
            {
                "key": key,
                "label": label,
                "kind": kind,
                "months": [round(v + 0.0, digits) for v in values],
                "total": round(totals[key] + 0.0, digits),
                "av": None
                if kind == "pct"
                else (round(totals[key] / net_total, 4) if net_total else 0.0),
            }
        )

    IND: dict[str, list[float]] = {}
    IND["events"] = [float(v) for v in _by_month(((e.event_date, 1) for e in events), year)]
    IND["guests"] = [float(v) for v in _by_month(((e.event_date, e.guests) for e in events), year)]
    purchases = db.scalars(select(StockIn).where(extract("year", StockIn.entry_date) == year))
    IND["purchases"] = _by_month(
        ((p.entry_date, p.quantity * p.unit_cost) for p in purchases), year
    )
    cmv_pos = [-v for v in L["cmv"]]
    ind_totals = {k: sum(v) for k, v in IND.items()}
    IND["ticket"], ind_totals["ticket"] = ratio(L["gross"], IND["guests"])
    IND["cmv_per_guest"], ind_totals["cmv_per_guest"] = ratio(cmv_pos, IND["guests"])
    IND["cmv_pct"], ind_totals["cmv_pct"] = ratio(cmv_pos, L["net"])
    indicators = [
        {
            "key": key,
            "label": label,
            "kind": kind,
            "months": [round(v + 0.0, 4) for v in IND[key]],
            "total": round(ind_totals[key] + 0.0, 4),
        }
        for key, label, kind in INDICATORS
    ]
    return {"year": year, "lines": lines, "indicators": indicators}


def dre_values(report: dict) -> dict[str, dict]:
    """Atalho: {chave: {"months": [...], "total": x}} das linhas e dos indicadores."""
    rows = [*report["lines"], *report["indicators"]]
    return {r["key"]: r for r in rows if "months" in r}


def years_with_data(db: Session, today: date) -> list[int]:
    years = {today.year}
    for model in (FinanceEvent,):
        years |= {d.year for d in db.scalars(select(model.event_date))}
    for model in (StockIn, StockOut, Expense):
        years |= {d.year for d in db.scalars(select(model.entry_date))}
    return sorted(years, reverse=True)


# ---------- Precificação ----------


def history(db: Session, year: int) -> dict:
    """As referências do DRE que a precificação usa (mão de obra, custos fixos, ticket)."""
    v = dre_values(dre(db, year))
    guests = v["guests"]["total"]
    direct_total = -v["direct"]["total"]
    fixed_year = (
        -(
            sum(v[g]["total"] for g in OPEX_GROUPS)
            + v["Depreciação"]["total"]
            + v["Despesa financeira"]["total"]
        )
        - v["Receita financeira"]["total"]
    )
    months = sum(1 for n in v["events"]["months"] if n > 0)
    fixed_month = fixed_year / months if months else 0.0
    events_month = v["events"]["total"] / months if months else 0.0
    return {
        "year": year,
        "direct_total": r2(direct_total),
        "direct_per_guest": r2(direct_total / guests) if guests else 0.0,
        "fixed_year": r2(fixed_year),
        "months_with_events": months,
        "fixed_per_month": r2(fixed_month),
        "events_per_month": round(events_month, 2),
        "fixed_per_event": r2(fixed_month / events_month) if events_month else 0.0,
        "ticket": r2(v["ticket"]["total"]),
        "cmv_per_guest": r2(v["cmv_per_guest"]["total"]),
    }


def price(db: Session, sim: PricingSim, year: int) -> dict:
    """Custo estimado da festa, preço sugerido e o que falta comprar."""
    settings = ensure_defaults(db)
    ref = history(db, year)
    positions = {p["id"]: p for p in stock_positions(db)}
    guests = sim.guests
    lines = []
    by_kind = dict.fromkeys(PRICING_KINDS, 0.0)
    to_buy = 0.0
    for entry in sim.items:
        pos = positions.get(entry.get("item_id"))
        if pos is None:
            continue
        qty = float(entry.get("per_guest", 0)) * guests * (1 + sim.safety_margin)
        cost = qty * pos["avg_cost"]
        missing = max(0.0, qty - max(0.0, pos["balance"]))
        kind = entry.get("kind") if entry.get("kind") in PRICING_KINDS else "Comida"
        by_kind[kind] += cost
        to_buy += missing * pos["avg_cost"]
        lines.append(
            {
                "item_id": pos["id"],
                "kind": kind,
                "code": pos["code"],
                "name": pos["name"],
                "unit": pos["unit"],
                "per_guest": float(entry.get("per_guest", 0)),
                "quantity": round(qty, 3),
                "unit_cost": round(pos["avg_cost"], 4),
                "total": r2(cost),
                "per_guest_cost": r2(cost / guests) if guests else 0.0,
                "balance": pos["balance"],
                "missing": round(missing, 3),
                "missing_value": r2(missing * pos["avg_cost"]),
            }
        )
    labor = ref["direct_per_guest"] * guests
    fixed = ref["fixed_per_event"]
    cost_total = sum(by_kind.values()) + labor + fixed
    divisor = 1 - settings.tax_rate - sim.profit_margin
    suggested = cost_total / divisor if divisor > 0 else 0.0

    def per(v):
        return r2(v / guests) if guests else 0.0

    def share(v):
        return round(v / suggested, 4) if suggested else 0.0

    breakdown = [
        {"key": "food", "label": "Comida (insumos)", "total": r2(by_kind["Comida"])},
        {"key": "drinks", "label": "Bebidas (insumos)", "total": r2(by_kind["Bebidas"])},
        {
            "key": "disposables",
            "label": "Descartáveis e limpeza",
            "total": r2(by_kind["Descartáveis"]),
        },
        {"key": "labor", "label": "Mão de obra e custos diretos", "total": r2(labor)},
        {"key": "fixed", "label": "Rateio de custos fixos", "total": r2(fixed)},
    ]
    for row in breakdown:
        row["per_guest"] = per(row["total"])
        row["share"] = share(row["total"])

    charged_pg = sim.charged_per_guest
    if charged_pg is None:
        charged_pg = math.ceil(suggested / guests) if guests else 0.0
    revenue = charged_pg * guests
    taxes_charged = revenue * settings.tax_rate
    profit_charged = revenue - cost_total - taxes_charged
    return {
        "history": ref,
        "tax_rate": settings.tax_rate,
        "items": lines,
        "breakdown": breakdown,
        "cost_total": r2(cost_total),
        "cost_per_guest": per(cost_total),
        "suggested_price": r2(suggested),
        "suggested_per_guest": per(suggested),
        "taxes": r2(suggested * settings.tax_rate),
        "profit": r2(suggested * sim.profit_margin),
        "to_buy": r2(to_buy),
        "charged": {
            "per_guest": r2(charged_pg),
            "revenue": r2(revenue),
            "taxes": r2(taxes_charged),
            "profit": r2(profit_charged),
            "margin": round(profit_charged / revenue, 4) if revenue else 0.0,
            "vs_ticket": r2(charged_pg - ref["ticket"]),
        },
    }
