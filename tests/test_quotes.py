def test_client_requests_a_quote(api, ana):
    quote = api.quote(ana, budget="R$ 10 a 20 mil", details="Jantar para 120 pessoas")
    assert quote["status"] == "novo"
    assert quote["client"]["name"] == "Ana Souza"
    assert quote["client"]["phone"] == "(11) 98765-4321"
    assert quote["messages"] == []


def test_quote_validation(client, ana):
    past = client.post(
        "/quotes",
        json={
            "event_type": "Casamento",
            "event_date": "2029-12-31",
            "guests": 10,
            "location": "Casa",
        },
        headers=ana,
    )
    assert past.status_code == 422
    assert "já passou" in past.json()["detail"]
    bad = client.post(
        "/quotes",
        json={
            "event_type": "Show",
            "event_date": "2030-02-01",
            "guests": 0,
            "location": "",
            "budget": "R$ 1 milhão",
        },
        headers=ana,
    )
    fields = {e["field"] for e in bad.json()["errors"]}
    assert fields == {"event_type", "guests", "location", "budget"}


def test_login_is_required(client):
    assert client.get("/quotes").status_code == 401
    assert client.post("/quotes", json={}).status_code == 401


def test_owner_does_not_request_quotes(api, owner):
    response = api.client.post(
        "/quotes",
        json={
            "event_type": "Casamento",
            "event_date": "2030-02-01",
            "guests": 10,
            "location": "Casa",
        },
        headers=owner,
    )
    assert response.status_code == 403


def test_clients_only_see_their_own_quotes(api, client, ana):
    bruno = api.headers("bruno@exemplo.com", "Bruno Lima")
    quote = api.quote(ana)
    assert client.get("/quotes", headers=bruno).json() == []
    assert client.get(f"/quotes/{quote['id']}", headers=bruno).status_code == 404
    send = client.post(f"/quotes/{quote['id']}/messages", json={"body": "oi"}, headers=bruno)
    assert send.status_code == 404


def test_conversation_and_unread_counts(api, client, ana, owner):
    quote = api.quote(ana)
    assert client.get("/quotes/unread", headers=owner).json() == {"unread": 0, "new_quotes": 1}

    first = api.say(ana, quote["id"], "Vocês atendem em Valinhos?")
    assert first["from_owner"] is False
    assert client.get("/quotes/unread", headers=owner).json()["unread"] == 1
    assert client.get("/quotes/unread", headers=ana).json()["unread"] == 0

    listed = client.get("/quotes", headers=owner).json()[0]
    assert listed["unread"] == 1
    assert listed["last_message"] == "Vocês atendem em Valinhos?"

    detail = client.get(f"/quotes/{quote['id']}", headers=owner).json()  # abrir = ler
    assert [m["body"] for m in detail["messages"]] == ["Vocês atendem em Valinhos?"]
    assert client.get("/quotes/unread", headers=owner).json()["unread"] == 0

    reply = api.say(owner, quote["id"], "Atendemos sim!")
    assert reply["from_owner"] is True
    assert client.get(f"/quotes/{quote['id']}", headers=ana).json()["status"] == "em_conversa"
    assert client.get("/quotes/unread", headers=owner).json()["new_quotes"] == 0


def test_polling_returns_only_new_messages(api, client, ana, owner):
    quote = api.quote(ana)
    first = api.say(ana, quote["id"], "Primeira")
    api.say(owner, quote["id"], "Resposta")
    api.say(owner, quote["id"], "Mais uma")
    assert client.get("/quotes/unread", headers=ana).json()["unread"] == 2
    new = client.get(
        f"/quotes/{quote['id']}/messages", params={"after": first["id"]}, headers=ana
    ).json()
    assert [m["body"] for m in new] == ["Resposta", "Mais uma"]
    assert client.get("/quotes/unread", headers=ana).json()["unread"] == 0
    assert (
        client.get(
            f"/quotes/{quote['id']}/messages", params={"after": new[-1]["id"]}, headers=ana
        ).json()
        == []
    )


def test_empty_message_is_rejected(api, client, ana):
    quote = api.quote(ana)
    response = client.post(f"/quotes/{quote['id']}/messages", json={"body": "   "}, headers=ana)
    assert response.status_code == 422


def test_owner_changes_status_and_filters(api, client, ana, owner):
    one, two = api.quote(ana), api.quote(ana, event_type="Aniversário")
    response = client.patch(f"/admin/quotes/{one['id']}", json={"status": "fechado"}, headers=owner)
    assert response.status_code == 200
    assert response.json()["status"] == "fechado"
    closed = client.get("/quotes", params={"status": "fechado"}, headers=owner).json()
    assert [q["id"] for q in closed] == [one["id"]]
    assert (
        client.patch(
            f"/admin/quotes/{two['id']}", json={"status": "fechado"}, headers=ana
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/admin/quotes/{two['id']}", json={"status": "aprovado"}, headers=owner
        ).status_code
        == 422
    )


def test_owner_searches_quotes_by_client(api, client, ana, owner):
    bruno = api.headers("bruno@exemplo.com", "Bruno Lima")
    api.quote(ana)
    api.quote(bruno)
    found = client.get("/quotes", params={"q": "bruno"}, headers=owner).json()
    assert [q["client"]["name"] for q in found] == ["Bruno Lima"]


def test_most_recent_conversation_comes_first(api, client, ana, owner):
    old, new = api.quote(ana), api.quote(ana)
    api.say(ana, old["id"], "Voltei a falar deste")
    ids = [q["id"] for q in client.get("/quotes", headers=owner).json()]
    assert ids == [old["id"], new["id"]]
    by_date = client.get("/quotes", params={"sort": "evento"}, headers=owner).json()
    assert len(by_date) == 2


def test_client_list_for_the_owner(api, client, ana, owner):
    api.quote(ana)
    api.headers("bruno@exemplo.com", "Bruno Lima")
    clients = client.get("/admin/clients", headers=owner).json()
    assert {c["name"]: c["quotes"] for c in clients} == {"Ana Souza": 1, "Bruno Lima": 0}
    assert clients[0]["phone"]
    found = client.get("/admin/clients", params={"q": "bruno"}, headers=owner).json()
    assert [c["name"] for c in found] == ["Bruno Lima"]
    assert client.get("/admin/clients", headers=ana).status_code == 403
