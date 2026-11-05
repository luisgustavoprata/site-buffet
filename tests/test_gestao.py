"""Gestão: estoque com custo médio, eventos, despesas, DRE e precificação (antes, a planilha)."""

import pytest

G = "/admin/gestao"


@pytest.fixture
def gestao(client, owner):
    """Atalhos para lançar dados como a dona do buffet."""

    class Gestao:
        def post(self, path, **payload):
            response = client.post(f"{G}{path}", json=payload, headers=owner)
            assert response.status_code == 201, response.json()
            return response.json()

        def get(self, path, **params):
            response = client.get(f"{G}{path}", params=params, headers=owner)
            assert response.status_code == 200, response.json()
            return response.json()

        def category(self, name):
            return next(c["id"] for c in self.get("/categorias") if c["name"] == name)

        def item(self, name="Picanha bovina", **extra):
            data = {
                "name": name,
                "category": "Carnes",
                "unit": "kg",
                "min_stock": 15,
                "initial_stock": 20,
                "initial_cost": 85,
                **extra,
            }
            return self.post("/insumos", **data)

        def event(self, **extra):
            data = {
                "event_date": "2030-01-10",
                "client": "Família Andrade",
                "event_type": "Casamento",
                "guests": 100,
                "price_per_guest": 150,
                "status": "realizado",
                **extra,
            }
            return self.post("/eventos", **data)

    return Gestao()


def line(report, key):
    rows = [*report["lines"], *report["indicators"]]
    return next(r for r in rows if r["key"] == key)


def test_only_the_owner_gets_in(client, ana):
    for path in ("/insumos", "/dre", "/resumo", "/eventos", "/despesas", "/exportar"):
        assert client.get(f"{G}{path}", headers=ana).status_code == 403
        assert client.get(f"{G}{path}").status_code == 401


def test_defaults_come_from_the_spreadsheet(gestao):
    config = gestao.get("/config")
    assert config["tax_rate"] == 0.08
    assert "Carnes" in config["item_categories"]
    assert "Receita financeira" in config["groups"]
    categories = {c["name"]: c["group"] for c in gestao.get("/categorias")}
    assert categories["Aluguel"] == "Ocupação"
    assert categories["Freelancers (garçons, copeiros, cozinheiros)"] == "Custo direto do evento"


def test_item_codes_are_created_by_category(gestao):
    first = gestao.item()
    second = gestao.item("Alcatra bovina")
    drinks = gestao.item("Coca-Cola 2 L", category="Bebidas não alcoólicas", unit="un")
    assert (first["code"], second["code"], drinks["code"]) == ("CAR001", "CAR002", "BEB001")
    assert first["status"] == "OK"
    assert first["value"] == 1700


def test_moving_average_cost_is_frozen_at_the_exit(gestao):
    item = gestao.item()  # 20 kg a R$ 85
    event = gestao.event()
    out = gestao.post(
        "/saidas",
        entry_date="2030-01-10",
        item_id=item["id"],
        quantity=10,
        kind="evento",
        event_id=event["id"],
    )
    assert out["unit_cost"] == 85
    # Compra depois da saída (mais cara) não muda o custo da saída.
    gestao.post("/compras", entry_date="2030-01-20", item_id=item["id"], quantity=10, unit_cost=95)
    assert gestao.get("/saidas")[0]["unit_cost"] == 85
    position = gestao.get("/insumos")[0]
    assert position["balance"] == 20
    assert position["avg_cost"] == 90  # (10 × 85 + 10 × 95) ÷ 20
    # Compra com data anterior, lançada depois, recalcula a saída.
    gestao.post("/compras", entry_date="2030-01-05", item_id=item["id"], quantity=20, unit_cost=95)
    assert gestao.get("/saidas")[0]["unit_cost"] == 90  # (20 × 85 + 20 × 95) ÷ 40


def test_stock_status_and_purchase_suggestion(client, owner, gestao):
    item = gestao.item()
    gestao.post("/saidas", entry_date="2030-01-03", item_id=item["id"], quantity=12, kind="perda")
    position = gestao.get("/insumos")[0]
    assert (position["balance"], position["status"], position["suggestion"]) == (8, "REPOR", 22)
    gestao.post("/saidas", entry_date="2030-01-04", item_id=item["id"], quantity=10, kind="consumo")
    assert gestao.get("/insumos")[0]["status"] == "NEGATIVO"
    deleted = client.delete(f"{G}/insumos/{item['id']}", headers=owner)
    assert deleted.status_code == 409


def test_exit_for_an_event_needs_the_event(client, owner, gestao):
    item = gestao.item()
    response = client.post(
        f"{G}/saidas",
        json={"entry_date": "2030-01-03", "item_id": item["id"], "quantity": 1, "kind": "evento"},
        headers=owner,
    )
    assert response.status_code == 422
    assert "escolha o evento" in response.json()["detail"]


def test_event_margin(gestao):
    item = gestao.item()
    event = gestao.event(discount=1000)
    gestao.post(
        "/saidas",
        entry_date="2030-01-10",
        item_id=item["id"],
        quantity=20,
        kind="evento",
        event_id=event["id"],
    )
    gestao.post(
        "/despesas",
        entry_date="2030-01-10",
        category_id=gestao.category("Freelancers (garçons, copeiros, cozinheiros)"),
        amount=1500,
        event_id=event["id"],
    )
    row = gestao.get("/eventos")[0]
    assert row["code"] == "EV001"
    assert (row["gross"], row["net"], row["cmv"]) == (15000, 14000, 1700)
    assert row["direct_costs"] == 1500
    assert row["cmv_per_guest"] == 17
    assert row["margin_on_inputs"] == pytest.approx((14000 - 1700) / 14000, abs=1e-4)


def test_dre_follows_the_spreadsheet_rules(gestao):
    item = gestao.item()
    done = gestao.event(discount=500)  # janeiro, realizado: 15.000 brutos
    gestao.event(event_date="2030-02-10", status="confirmado")  # ainda não é receita
    gestao.post(
        "/saidas",
        entry_date="2030-01-10",
        item_id=item["id"],
        quantity=10,
        kind="evento",
        event_id=done["id"],
    )
    gestao.post("/saidas", entry_date="2030-01-11", item_id=item["id"], quantity=1, kind="perda")
    gestao.post("/compras", entry_date="2030-01-12", item_id=item["id"], quantity=5, unit_cost=80)
    for name, amount in (
        ("Freelancers (garçons, copeiros, cozinheiros)", 1200),
        ("Salários", 3000),
        ("Aluguel", 2000),
        ("Depreciação", 300),
        ("Tarifas bancárias / maquininha", 100),
        ("Rendimentos de aplicações", 50),
    ):
        gestao.post(
            "/despesas",
            entry_date="2030-01-15",
            category_id=gestao.category(name),
            amount=amount,
        )
    report = gestao.get("/dre", ano=2030)
    jan = {
        r["key"]: r["months"][0] for r in [*report["lines"], *report["indicators"]] if "months" in r
    }
    assert jan["gross"] == 15000
    assert jan["discounts"] == -500
    assert jan["taxes"] == -1200  # 8% sobre a receita bruta
    assert jan["net"] == 13300
    assert jan["cmv"] == -850
    assert jan["direct"] == -1200
    assert jan["gross_profit"] == 11250
    assert jan["losses"] == -85
    assert jan["opex"] == -5085
    assert jan["ebitda"] == 6165
    assert jan["ebit"] == 5865
    assert jan["ebt"] == 5815
    assert jan["net_profit"] == 5815  # IR/CSLL 0% (Simples Nacional)
    assert jan["events"] == 1 and jan["guests"] == 100
    assert jan["ticket"] == 150
    assert jan["purchases"] == 400  # informativo: compra não é despesa
    assert line(report, "gross")["months"][1] == 0  # fevereiro: evento só confirmado
    assert line(report, "net")["av"] == 1


def test_income_tax_only_on_profit(client, owner, gestao):
    config = gestao.get("/config")
    config.pop("groups")
    config["income_tax_rate"] = 0.1
    assert client.put(f"{G}/config", json=config, headers=owner).status_code == 200
    gestao.event()
    report = gestao.get("/dre", ano=2030)
    assert line(report, "income_tax")["months"][0] == pytest.approx(-0.1 * 13800)


def test_quote_becomes_an_event(client, api, ana, owner, gestao):
    quote = api.quote(ana, guests=120)
    response = client.post(f"{G}/eventos/do-orcamento/{quote['id']}", headers=owner)
    assert response.status_code == 201, response.json()
    event = response.json()
    assert (event["guests"], event["event_type"], event["status"]) == (
        120,
        "Casamento",
        "orcamento",
    )
    assert event["quote_id"] == quote["id"]
    assert "Ana Souza" in event["client"]
    again = client.post(f"{G}/eventos/do-orcamento/{quote['id']}", headers=owner)
    assert again.status_code == 409
    linked = client.get(f"{G}/eventos/do-orcamento/{quote['id']}", headers=owner).json()
    assert linked["code"] == event["code"]


def test_pricing_rejects_margin_plus_tax_of_100_percent(client, owner, gestao):
    item = gestao.item()
    payload = {
        "name": "Simulação — casamento",
        "guests": 160,
        "profit_margin": 0.95,
        "items": [{"item_id": item["id"], "kind": "Comida", "per_guest": 0.12}],
    }
    response = client.post(f"{G}/precificacao", json=payload, headers=owner)
    assert response.status_code == 422
    assert "abaixo de 100%" in response.json()["detail"]


def test_pricing_suggests_a_price(gestao):
    item = gestao.item()  # 20 kg a R$ 85
    sim = gestao.post(
        "/precificacao",
        name="Casamento 160",
        guests=160,
        safety_margin=0.1,
        profit_margin=0.2,
        items=[{"item_id": item["id"], "kind": "Comida", "per_guest": 0.12}],
    )
    result = sim["result"]
    line_ = result["items"][0]
    assert line_["quantity"] == pytest.approx(21.12)  # 0,12 × 160 × 1,1
    assert line_["total"] == pytest.approx(1795.2)
    assert line_["missing"] == pytest.approx(1.12)
    assert result["cost_total"] == pytest.approx(1795.2)  # sem histórico de custos ainda
    assert result["suggested_price"] == pytest.approx(1795.2 / 0.72, abs=0.01)
    assert result["charged"]["per_guest"] == 16  # arredonda para cima: 2493,33 ÷ 160
    assert len(gestao.get("/precificacao")) == 1


def test_summary_for_the_dashboard(gestao):
    item = gestao.item(min_stock=50)
    gestao.event()
    gestao.event(event_date="2030-03-01", status="confirmado", client="Turma 2030")
    body = gestao.get("/resumo", ano=2030)
    assert body["year"] == 2030
    assert len(body["events"]) == 1
    assert [e["client"] for e in body["upcoming"]] == ["Turma 2030"]
    assert body["alerts"][0]["code"] == item["code"]
    assert body["stock_value"] == 1700


def test_import_the_old_spreadsheet(client, owner, gestao):
    payload = {
        "items": [
            {
                "code": "CAR001",
                "name": "Picanha bovina",
                "category": "Carnes",
                "unit": "kg",
                "min_stock": 15,
                "initial_stock": 20,
                "initial_cost": 85,
            }
        ],
        "events": [
            {
                "code": "EV001",
                "event_date": "2030-01-05",
                "client": "Família Andrade",
                "event_type": "Casamento",
                "guests": 180,
                "price_per_guest": 145,
                "status": "realizado",
            }
        ],
        "stock_in": [{"date": "2030-01-03", "item": "CAR001", "quantity": 20, "unit_cost": 87}],
        "stock_out": [
            {
                "date": "2030-01-05",
                "item": "car001",
                "quantity": 30,
                "kind": "evento",
                "event": "EV001",
            }
        ],
        "expenses": [{"date": "2030-01-05", "category": "Aluguel", "amount": 2450}],
    }
    gestao.item("Insumo antigo")  # a importação substitui o que havia
    response = client.post(f"{G}/importar", json=payload, headers=owner)
    assert response.status_code == 200, response.json()
    assert response.json()["stock_out"] == 1
    items = gestao.get("/insumos")
    assert [i["code"] for i in items] == ["CAR001"]
    assert items[0]["balance"] == 10
    assert gestao.get("/saidas")[0]["unit_cost"] == 86
    report = gestao.get("/dre", ano=2030)
    assert line(report, "gross")["months"][0] == 26100
    assert line(report, "Ocupação")["months"][0] == -2450


def test_import_reports_the_bad_line(client, owner):
    payload = {"expenses": [{"date": "2030-01-05", "category": "Inexistente", "amount": 10}]}
    response = client.post(f"{G}/importar", json=payload, headers=owner)
    assert response.status_code == 422
    assert "linha 1" in response.json()["detail"]


def test_export_has_everything(gestao):
    gestao.item()
    gestao.event()
    body = gestao.get("/exportar")
    assert body["items"][0]["code"] == "CAR001"
    assert body["events"][0]["code"] == "EV001"
    assert body["dre"][0]["year"] == 2030


def test_import_fixes_an_impossible_pricing_margin(client, owner, gestao):
    item = {
        "code": "CAR001",
        "name": "Picanha",
        "category": "Carnes",
        "unit": "kg",
        "initial_cost": 85,
    }
    sim = {
        "name": "Simulação — casamento",
        "guests": 160,
        "profit_margin": 1.0,  # como na planilha: 100% + 8% de imposto dava preço negativo
        "items": [{"item": "CAR001", "kind": "Comida", "per_guest": 0.12}],
    }
    response = client.post(f"{G}/importar", json={"items": [item], "pricing": [sim]}, headers=owner)
    assert response.status_code == 200, response.json()
    assert "30%" in response.json()["warnings"][0]
    saved = gestao.get("/precificacao")[0]
    assert saved["profit_margin"] == 0.3
    assert saved["items"][0]["per_guest"] == 0.12
    assert saved["result"]["suggested_price"] > 0
