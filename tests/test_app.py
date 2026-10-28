from fastapi.testclient import TestClient

from app.config import Settings, normalize_database_url
from app.main import create_app
from app.seed import DEMO_CLIENT, DEMO_OWNER


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "version": "1.0.0", "demo": False}


def test_home_serves_the_site_with_security_headers(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/docs").status_code == 200


def test_openapi_lists_every_route(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert {
        "/auth/register",
        "/auth/token",
        "/auth/me",
        "/site",
        "/admin/site",
        "/admin/site/bio-photos",
        "/admin/images",
        "/media/{image_id}",
        "/events",
        "/events/{event_id}",
        "/admin/events",
        "/quotes",
        "/quotes/{quote_id}",
        "/quotes/{quote_id}/messages",
        "/admin/quotes/{quote_id}",
        "/admin/clients",
    } <= paths


def test_demo_is_created_once(settings):
    demo = Settings(**{**settings.__dict__, "seed_demo": True})
    for _ in range(2):  # reiniciar o servidor não duplica nada
        with TestClient(create_app(demo)) as client:
            assert len(client.get("/events").json()) == 5
            site = client.get("/site").json()
            assert site["business_name"] == "Buffet Alecrim"
            assert len(site["bio_photos"]) == 2
            for email, password in (DEMO_CLIENT, DEMO_OWNER):
                login = client.post("/auth/token", data={"username": email, "password": password})
                assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            assert len(client.get("/quotes", headers=headers).json()) == 1


def test_demo_fills_a_site_opened_before(settings, client, owner):
    assert client.get("/site").json()["business_name"] == "Meu Buffet"  # criado na 1ª visita
    demo = Settings(**{**settings.__dict__, "seed_demo": True})
    with TestClient(create_app(demo)) as again:
        assert again.get("/site").json()["business_name"] == "Buffet Alecrim"
        assert len(again.get("/events").json()) == 5


def test_demo_never_overwrites_real_content(settings, client, owner):
    client.patch(
        "/admin/site", json={"business_name": "Buffet Real", "bio": "Minha história"}, headers=owner
    )
    demo = Settings(**{**settings.__dict__, "seed_demo": True})
    with TestClient(create_app(demo)) as again:
        assert again.get("/site").json()["business_name"] == "Buffet Real"
        assert again.get("/events").json() == []


def test_database_url_normalization():
    assert normalize_database_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"


def test_production_requires_a_secret_key(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    try:
        Settings.from_env()
    except RuntimeError as exc:
        assert "SECRET_KEY" in str(exc)
    else:
        raise AssertionError("deveria exigir SECRET_KEY em produção")
