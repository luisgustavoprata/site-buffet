from fastapi.testclient import TestClient

from app.config import Settings, normalize_database_url
from app.database import Base, make_engine
from app.main import create_app
from app.seed import DEMO_CLIENT, DEMO_OWNER


def demo_settings(settings, *, fresh: bool) -> Settings:
    """Configuração com a demonstração ligada. `fresh` apaga o banco (útil no PostgreSQL,
    que é compartilhado entre os testes)."""
    if fresh:
        engine = make_engine(settings.database_url)
        Base.metadata.drop_all(engine)
        engine.dispose()
    return Settings(**{**settings.__dict__, "seed_demo": True})


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
        "/admin/gestao/dre",
        "/admin/gestao/importar",
    } <= paths


def test_demo_is_created_once(settings):
    demo = demo_settings(settings, fresh=True)
    for _ in range(2):  # reiniciar o servidor não duplica nada
        with TestClient(create_app(demo)) as client:
            assert len(client.get("/events").json()) == 5
            site = client.get("/site").json()
            assert site["business_name"] == "Brunoise Gastronomia"
            assert len(site["bio_photos"]) == 2
            for email, password in (DEMO_CLIENT, DEMO_OWNER):
                login = client.post("/auth/token", data={"username": email, "password": password})
                assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
            assert len(client.get("/quotes", headers=headers).json()) == 1


def test_demo_fills_a_site_opened_before(settings, client, owner):
    assert client.get("/site").json()["business_name"] == "Meu Buffet"  # criado na 1ª visita
    demo = demo_settings(settings, fresh=False)
    with TestClient(create_app(demo)) as again:
        assert again.get("/site").json()["business_name"] == "Brunoise Gastronomia"
        assert len(again.get("/events").json()) == 5


def test_demo_never_overwrites_real_content(settings, client, owner):
    client.patch(
        "/admin/site", json={"business_name": "Buffet Real", "bio": "Minha história"}, headers=owner
    )
    demo = demo_settings(settings, fresh=False)
    with TestClient(create_app(demo)) as again:
        assert again.get("/site").json()["business_name"] == "Buffet Real"
        assert again.get("/events").json() == []


def test_old_demo_gets_the_new_brand(settings):
    demo = demo_settings(settings, fresh=True)
    with TestClient(create_app(demo)) as client:
        owner = client.post(
            "/auth/token", data={"username": DEMO_OWNER[0], "password": DEMO_OWNER[1]}
        )
        headers = {"Authorization": f"Bearer {owner.json()['access_token']}"}
        client.patch("/admin/site", json={"business_name": "Buffet Alecrim"}, headers=headers)
    with TestClient(create_app(demo)) as client:
        site = client.get("/site").json()
        assert site["business_name"] == "Brunoise Gastronomia"
        assert site["history_title"] == "Por que Brunoise"
        assert site["hero_image_id"]  # as fotos continuam


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


def test_demo_has_example_results(settings):
    demo = demo_settings(settings, fresh=True)
    with TestClient(create_app(demo)) as client:
        login = {"username": DEMO_OWNER[0], "password": DEMO_OWNER[1]}
        token = client.post("/auth/token", data=login).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        response = client.get("/admin/gestao/dre", params={"ano": 2026}, headers=headers)
        assert response.status_code == 200, response.json()
        gross = next(line for line in response.json()["lines"] if line["key"] == "gross")
        assert gross["total"] == 122050  # a mesma receita da planilha de exemplo
        assert len(client.get("/admin/gestao/insumos", headers=headers).json()) == 99


def test_turning_demo_off_removes_the_demo_accounts(settings):
    demo = demo_settings(settings, fresh=True)
    with TestClient(create_app(demo)) as client:
        assert client.get("/site").json()["business_name"] == "Brunoise Gastronomia"
    with TestClient(create_app(settings)) as client:  # SEED_DEMO desligado
        for email, password in (DEMO_CLIENT, DEMO_OWNER):
            login = client.post("/auth/token", data={"username": email, "password": password})
            assert login.status_code == 401
        assert client.get("/site").json()["business_name"] == "Brunoise Gastronomia"
        assert len(client.get("/events").json()) == 5  # o conteúdo continua
        owner = client.post(
            "/auth/token", data={"username": settings.owner_email, "password": "senha-forte-123"}
        )
        assert owner.status_code == 200


def test_production_hides_the_api_docs(settings):
    production = Settings(**{**settings.__dict__, "environment": "production"})
    with TestClient(create_app(production)) as client:
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404
        assert client.get("/").status_code == 200


def restart(settings, **changes) -> TestClient:
    return TestClient(create_app(Settings(**{**settings.__dict__, **changes})))


def login(client, email, password):
    return client.post("/auth/token", data={"username": email, "password": password})


def test_owner_password_changed_in_the_panel_survives_a_restart(settings, client, owner):
    response = client.post(
        "/auth/me/password",
        json={"current_password": "senha-forte-123", "new_password": "do-painel-123"},
        headers=owner,
    )
    assert response.status_code == 200
    with restart(settings) as again:  # mesmo OWNER_PASSWORD no Render
        assert login(again, settings.owner_email, "do-painel-123").status_code == 200


def test_new_owner_password_in_render_resets_a_forgotten_one(settings, client, owner):
    client.post(
        "/auth/me/password",
        json={"current_password": "senha-forte-123", "new_password": "esquecida-123"},
        headers=owner,
    )
    with restart(settings, owner_password="nova-do-render") as again:
        assert login(again, settings.owner_email, "esquecida-123").status_code == 401
        assert login(again, settings.owner_email, "nova-do-render").status_code == 200


def test_new_owner_email_demotes_the_old_owner(settings, client, owner):
    with restart(settings, owner_email="gracielle@brunoise.com") as again:
        old = login(again, settings.owner_email, "senha-forte-123")
        assert old.status_code == 200
        me = again.get(
            "/auth/me", headers={"Authorization": f"Bearer {old.json()['access_token']}"}
        )
        assert me.json()["role"] == "client"
        new = login(again, "gracielle@brunoise.com", "senha-forte-123")
        assert new.status_code == 200


def test_client_account_with_the_owner_email_does_not_keep_its_password(settings):
    engine = make_engine(settings.database_url)
    Base.metadata.drop_all(engine)
    engine.dispose()
    no_owner = Settings(**{**settings.__dict__, "owner_email": "", "owner_password": ""})
    with TestClient(create_app(no_owner)) as early:
        early.post(
            "/auth/register",
            json={
                "name": "Alguém",
                "email": settings.owner_email,
                "phone": "11987654321",
                "city": "Rio Verde",
                "password": "senha-do-intruso",
            },
        )
    with restart(settings) as again:
        assert login(again, settings.owner_email, "senha-do-intruso").status_code == 401
        assert login(again, settings.owner_email, "senha-forte-123").status_code == 200


def test_security_headers_and_small_routes(settings):
    production = Settings(**{**settings.__dict__, "environment": "production"})
    with TestClient(create_app(production)) as client:
        response = client.get("/")
        csp = response.headers["content-security-policy"]
        assert "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
        assert "object-src 'none'" in csp
        assert response.headers["strict-transport-security"].startswith("max-age=")
        assert "camera=()" in response.headers["permissions-policy"]
        assert response.headers["cross-origin-opener-policy"] == "same-origin"
        assert client.get("/robots.txt").text.startswith("User-agent: *")
        icon = client.get("/favicon.ico", follow_redirects=False)
        assert icon.status_code == 301
        assert client.get("/static/seguranca.js").status_code == 200


def test_huge_uploads_are_refused_before_reading(client, owner):
    response = client.post(
        "/admin/images",
        content=b"x",
        headers={**owner, "Content-Length": str(50 * 1024 * 1024), "Content-Type": "image/png"},
    )
    assert response.status_code == 413


def test_orphan_photos_are_cleaned_on_restart(settings, client, owner, api):
    from datetime import timedelta

    from app.models import Image, utcnow

    used = api.image(owner)
    orphan = api.image(owner)
    fresh = api.image(owner)
    client.patch("/admin/site", json={"hero_image_id": used}, headers=owner)
    factory = client.app.state.session_factory
    with factory.begin() as db:
        for image_id in (used, orphan):
            db.get(Image, image_id).created_at = utcnow() - timedelta(days=2)
    with TestClient(create_app(settings)) as again:
        assert again.get(f"/media/{used}").status_code == 200
        assert again.get(f"/media/{orphan}").status_code == 404
        assert again.get(f"/media/{fresh}").status_code == 200  # pode estar sendo editada


def test_challenge_page_gets_whatsapp_and_cover(client, owner, api):
    assert client.get("/_seguranca/contato").json() == {"whatsapp": None, "cover": None}
    cover = api.image(owner)
    client.patch(
        "/admin/site", json={"phone": "(64) 98113-1047", "hero_image_id": cover}, headers=owner
    )
    info = client.get("/_seguranca/contato").json()
    assert info == {"whatsapp": "https://wa.me/5564981131047", "cover": "/_seguranca/capa"}
    assert client.get("/_seguranca/capa").headers["content-type"].startswith("image/")
