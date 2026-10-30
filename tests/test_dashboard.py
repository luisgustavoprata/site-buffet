"""Resultados: a dona envia o resumo da planilha e vê de qualquer aparelho."""

SUMMARY = {
    "empresa": "Brunoise Gastronomia",
    "ano": 2030,
    "dre": {"receitaBruta": {"m": [0] * 12, "t": 57400}},
    "estoque": [{"code": "CAR001", "nome": "Picanha bovina", "valor": 620.87}],
}


def test_nothing_sent_yet(client, owner):
    response = client.get("/admin/dashboard", headers=owner)
    assert response.status_code == 404
    assert response.json()["detail"] == "Nenhuma planilha enviada ainda."


def test_owner_sends_and_reads_the_summary(client, owner):
    sent = client.put(
        "/admin/dashboard",
        json={"file_name": "Planilha_Buffet.ods", "data": SUMMARY},
        headers=owner,
    )
    assert sent.status_code == 200, sent.json()
    body = client.get("/admin/dashboard", headers=owner).json()
    assert body["file_name"] == "Planilha_Buffet.ods"
    assert body["data"]["dre"]["receitaBruta"]["t"] == 57400
    assert body["data"]["estoque"][0]["nome"] == "Picanha bovina"
    assert body["updated_at"].endswith("Z")


def test_new_version_replaces_the_old(client, owner):
    client.put("/admin/dashboard", json={"file_name": "a.ods", "data": SUMMARY}, headers=owner)
    newer = {**SUMMARY, "ano": 2031}
    client.put("/admin/dashboard", json={"file_name": "b.ods", "data": newer}, headers=owner)
    body = client.get("/admin/dashboard", headers=owner).json()
    assert (body["file_name"], body["data"]["ano"]) == ("b.ods", 2031)


def test_only_the_owner_sees_the_numbers(client, ana):
    payload = {"file_name": "x.ods", "data": SUMMARY}
    assert client.get("/admin/dashboard", headers=ana).status_code == 403
    assert client.put("/admin/dashboard", json=payload, headers=ana).status_code == 403
    assert client.get("/admin/dashboard").status_code == 401
    assert client.put("/admin/dashboard", json=payload).status_code == 401


def test_rejects_something_that_is_not_the_spreadsheet(client, owner):
    response = client.put(
        "/admin/dashboard", json={"file_name": "x.ods", "data": {"a": 1}}, headers=owner
    )
    assert response.status_code == 422
    assert "DRE" in response.json()["detail"]


def test_rejects_a_summary_that_is_too_big(client, owner):
    huge = {**SUMMARY, "extra": "x" * 2_100_000}
    response = client.put(
        "/admin/dashboard", json={"file_name": "x.ods", "data": huge}, headers=owner
    )
    assert response.status_code == 413
    assert client.get("/admin/dashboard", headers=owner).status_code == 404
