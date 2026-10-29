"""Cada teste ganha um banco limpo e uma "data de hoje" fixa.

Com TEST_DATABASE_URL definido (ex.: no CI), os testes rodam no PostgreSQL.
"""

import io
import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from PIL import Image as PILImage

from app.config import Settings, normalize_database_url
from app.database import Base
from app.deps import get_today
from app.main import create_app

TODAY = date(2030, 1, 7)  # segunda-feira
PASSWORD = "senha-forte-123"
OWNER_EMAIL = "dona@buffet.com"


@pytest.fixture
def settings(tmp_path) -> Settings:
    url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    return Settings(
        database_url=normalize_database_url(url),
        secret_key="chave-de-teste-com-pelo-menos-32-bytes!",
        password_iterations=1_000,  # rápido nos testes
        owner_email=OWNER_EMAIL,
        owner_password=PASSWORD,
        owner_name="Helena",
        max_upload_mb=1,
        push_scheduler=False,
    )


@pytest.fixture
def app(settings):
    application = create_app(settings)
    Base.metadata.drop_all(application.state.engine)  # PostgreSQL: começa do zero
    application.dependency_overrides[get_today] = lambda: TODAY
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def png_bytes(size=(64, 48), color=(200, 80, 40), mode="RGB", fmt="PNG", **save) -> bytes:
    buffer = io.BytesIO()
    PILImage.new(mode, size, color).save(buffer, fmt, **save)
    return buffer.getvalue()


class Api:
    """Atalhos para os testes ficarem curtos e legíveis."""

    def __init__(self, client: TestClient):
        self.client = client

    def register(self, email="ana@exemplo.com", name="Ana Souza", **extra):
        payload = {
            "name": name,
            "email": email,
            "phone": "11987654321",
            "city": "Campinas, SP",
            "password": PASSWORD,
            **extra,
        }
        return self.client.post("/auth/register", json=payload)

    def login(self, email, password=PASSWORD):
        return self.client.post("/auth/token", data={"username": email, "password": password})

    def headers(self, email="ana@exemplo.com", name="Ana Souza") -> dict:
        """Cria a conta de cliente (se preciso), entra e devolve o cabeçalho Authorization."""
        self.register(email=email, name=name)
        return self.token_headers(email)

    def token_headers(self, email) -> dict:
        response = self.login(email)
        assert response.status_code == 200, response.json()
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def upload(self, headers, content=None, name="foto.png", ctype="image/png"):
        content = content if content is not None else png_bytes()
        return self.client.post(
            "/admin/images", files={"file": (name, content, ctype)}, headers=headers
        )

    def image(self, headers) -> int:
        response = self.upload(headers)
        assert response.status_code == 201, response.json()
        return response.json()["id"]

    def quote(self, headers, **fields):
        payload = {
            "event_type": "Casamento",
            "event_date": "2030-03-20",
            "guests": 120,
            "location": "Chácara em Valinhos",
            **fields,
        }
        response = self.client.post("/quotes", json=payload, headers=headers)
        assert response.status_code == 201, response.json()
        return response.json()

    def say(self, headers, quote_id, body="Olá!"):
        response = self.client.post(
            f"/quotes/{quote_id}/messages", json={"body": body}, headers=headers
        )
        assert response.status_code == 201, response.json()
        return response.json()


@pytest.fixture
def api(client) -> Api:
    return Api(client)


@pytest.fixture
def ana(api) -> dict:
    return api.headers("ana@exemplo.com")


@pytest.fixture
def owner(api) -> dict:
    return api.token_headers(OWNER_EMAIL)
