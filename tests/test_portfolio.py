def _event(api, owner, **fields):
    payload = {"title": "Casamento de Júlia", "event_type": "Casamento", **fields}
    response = api.client.post("/admin/events", json=payload, headers=owner)
    assert response.status_code == 201, response.json()
    return response.json()


def test_publish_event_with_photos(api, client, owner):
    photos = [api.image(owner), api.image(owner)]
    event = _event(api, owner, image_ids=photos, guests=120, event_date="2029-11-02")
    assert [p["image_id"] for p in event["photos"]] == photos
    public = client.get(f"/events/{event['id']}").json()
    assert public["guests"] == 120


def test_events_newest_first_and_filter(api, client, owner):
    _event(api, owner, title="Antigo", event_date="2028-01-01")
    _event(api, owner, title="Sem data")
    _event(api, owner, title="Novo", event_date="2029-12-01", event_type="Corporativo")
    titles = [e["title"] for e in client.get("/events").json()]
    assert titles == ["Novo", "Antigo", "Sem data"]
    corporate = client.get("/events", params={"event_type": "Corporativo"}).json()
    assert [e["title"] for e in corporate] == ["Novo"]
    assert client.get("/events/types").json() == ["Casamento", "Corporativo"]


def test_edit_event_reorders_and_cleans_photos(api, client, owner):
    a, b, c = api.image(owner), api.image(owner), api.image(owner)
    event = _event(api, owner, image_ids=[a, b])
    payload = {"title": "Casamento editado", "event_type": "Casamento", "image_ids": [c, a, c]}
    response = client.put(f"/admin/events/{event['id']}", json=payload, headers=owner)
    assert response.status_code == 200, response.json()
    assert [p["image_id"] for p in response.json()["photos"]] == [c, a]
    assert client.get(f"/media/{b}").status_code == 404  # a foto tirada some
    assert client.get(f"/media/{a}").status_code == 200


def test_delete_event_deletes_its_photos(api, client, owner):
    photo = api.image(owner)
    event = _event(api, owner, image_ids=[photo])
    assert client.delete(f"/admin/events/{event['id']}", headers=owner).status_code == 204
    assert client.get(f"/events/{event['id']}").status_code == 404
    assert client.get(f"/media/{photo}").status_code == 404


def test_clients_cannot_publish(client, ana):
    payload = {"title": "Evento", "event_type": "Outro"}
    assert client.post("/admin/events", json=payload, headers=ana).status_code == 403


def test_event_validation(api, client, owner):
    response = client.post(
        "/admin/events", json={"title": "X", "event_type": "Outro", "guests": 0}, headers=owner
    )
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {"title", "guests"}
    missing = client.post(
        "/admin/events",
        json={"title": "Evento", "event_type": "Outro", "image_ids": [77]},
        headers=owner,
    )
    assert missing.status_code == 422


def test_site_stats_count_the_portfolio(api, client, owner):
    _event(api, owner, guests=120, image_ids=[api.image(owner), api.image(owner)])
    _event(api, owner, title="Outro evento", guests=80)
    assert client.get("/site").json()["stats"] == {"events": 2, "guests": 200, "photos": 2}


def test_hearts_on_events(api, client, owner, ana):
    event = _event(api, owner)
    url = f"/events/{event['id']}/like"
    assert client.put(url).status_code == 401  # precisa entrar na conta

    assert client.put(url, headers=ana).json() == {"likes": 1, "liked": True}
    assert client.put(url, headers=ana).json() == {"likes": 1, "liked": True}  # não soma 2x
    bia = api.headers(email="bia@exemplo.com", name="Bia Lima")
    assert client.put(url, headers=bia).json() == {"likes": 2, "liked": True}

    seen = client.get(f"/events/{event['id']}", headers=ana).json()
    assert (seen["likes"], seen["liked"]) == (2, True)
    anonymous = client.get("/events").json()[0]
    assert (anonymous["likes"], anonymous["liked"]) == (2, False)

    assert client.delete(url, headers=ana).json() == {"likes": 1, "liked": False}
    assert client.put("/events/999/like", headers=ana).status_code == 404


def test_comments_on_events(api, client, owner, ana):
    event = _event(api, owner)
    url = f"/events/{event['id']}/comments"
    assert client.post(url, json={"body": "Lindo!"}).status_code == 401
    assert client.post(url, json={"body": "   "}, headers=ana).status_code == 422

    mine = client.post(url, json={"body": "Que mesa linda!"}, headers=ana)
    assert mine.status_code == 201
    assert mine.json()["author"] == "Ana S."  # só a inicial do sobrenome fica pública
    reply = client.post(url, json={"body": "Obrigada, Ana!"}, headers=owner).json()
    assert (reply["author"], reply["from_owner"]) == ("Helena", True)

    public = client.get(url).json()
    assert [c["body"] for c in public] == ["Que mesa linda!", "Obrigada, Ana!"]
    assert not any(c["can_delete"] for c in public)
    assert client.get("/events").json()[0]["comments"] == 2

    # Cada um apaga o seu; a administração apaga qualquer um.
    bia = api.headers(email="bia@exemplo.com", name="Bia Lima")
    assert client.delete(f"/comments/{mine.json()['id']}", headers=bia).status_code == 403
    assert [c["can_delete"] for c in client.get(url, headers=ana).json()] == [True, False]
    assert client.delete(f"/comments/{mine.json()['id']}", headers=owner).status_code == 204
    assert [c["body"] for c in client.get(url).json()] == ["Obrigada, Ana!"]


def test_comment_flood_is_limited(api, client, owner, ana):
    event = _event(api, owner)
    url = f"/events/{event['id']}/comments"
    for n in range(5):
        assert client.post(url, json={"body": f"Comentário {n}"}, headers=ana).status_code == 201
    blocked = client.post(url, json={"body": "Mais um"}, headers=ana)
    assert blocked.status_code == 429


def test_deleting_an_event_removes_its_reactions(api, client, owner, ana):
    event = _event(api, owner)
    client.put(f"/events/{event['id']}/like", headers=ana)
    client.post(f"/events/{event['id']}/comments", json={"body": "Oi"}, headers=ana)
    assert client.delete(f"/admin/events/{event['id']}", headers=owner).status_code == 204
    assert client.get(f"/events/{event['id']}/comments").status_code == 404
