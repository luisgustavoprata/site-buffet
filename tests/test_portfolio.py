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
