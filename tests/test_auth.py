from tests.conftest import OWNER_EMAIL, PASSWORD


def test_register_normalizes_email_and_phone(api):
    response = api.register(email="  Ana@Exemplo.COM ", phone="+55 (11) 98765-4321")
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["email"] == "ana@exemplo.com"
    assert body["phone"] == "(11) 98765-4321"
    assert body["role"] == "client"
    assert "password_hash" not in body


def test_register_requires_contact_data(api, client):
    response = client.post("/auth/register", json={"name": "An", "email": "x", "password": "123"})
    assert response.status_code == 422
    fields = {e["field"] for e in response.json()["errors"]}
    assert {"email", "phone", "city", "password", "name"} <= fields


def test_invalid_phone_has_a_clear_message(api):
    response = api.register(phone="1234")
    assert response.status_code == 422
    assert "Telefone inválido" in response.json()["errors"][0]["message"]


def test_cannot_register_as_owner(api):
    response = api.register(role="owner")
    assert response.status_code == 422  # campo não permitido


def test_duplicate_email_returns_409(api):
    api.register()
    assert api.register(email="ANA@exemplo.com").status_code == 409


def test_owner_account_comes_from_settings(api):
    response = api.login(OWNER_EMAIL)
    assert response.status_code == 200
    me = api.client.get(
        "/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}
    ).json()
    assert me["role"] == "owner"


def test_wrong_password_and_unknown_email_look_the_same(api):
    api.register()
    wrong = api.login("ana@exemplo.com", "senha-errada")
    unknown = api.login("ninguem@exemplo.com", PASSWORD)
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_is_blocked_after_five_failures(api):
    api.register()
    for _ in range(5):
        assert api.login("ana@exemplo.com", "errada-123").status_code == 401
    blocked = api.login("ana@exemplo.com")
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_update_profile(api, ana, client):
    response = client.patch(
        "/auth/me", json={"phone": "(19) 3232-1010", "city": "Sousas"}, headers=ana
    )
    assert response.status_code == 200
    assert response.json()["phone"] == "(19) 3232-1010"
    assert response.json()["city"] == "Sousas"


def test_bad_token_returns_401(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer nada"})
    assert response.status_code == 401


def test_change_password_logs_out_other_devices(api, client):
    other_device = api.headers("ana@exemplo.com")
    this_device = api.token_headers("ana@exemplo.com")
    wrong = client.post(
        "/auth/me/password",
        json={"current_password": "errada", "new_password": "nova-senha-123"},
        headers=this_device,
    )
    assert wrong.status_code == 400
    response = client.post(
        "/auth/me/password",
        json={"current_password": PASSWORD, "new_password": "nova-senha-123"},
        headers=this_device,
    )
    assert response.status_code == 200, response.json()
    fresh = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/auth/me", headers=fresh).status_code == 200
    assert client.get("/auth/me", headers=other_device).status_code == 401
    assert client.get("/auth/me", headers=this_device).status_code == 401
    assert api.login("ana@exemplo.com").status_code == 401
    assert api.login("ana@exemplo.com", "nova-senha-123").status_code == 200


def test_change_password_needs_a_strong_new_one(api, client, ana):
    response = client.post(
        "/auth/me/password", json={"current_password": PASSWORD, "new_password": "123"}, headers=ana
    )
    assert response.status_code == 422


def test_guessing_the_current_password_is_limited(client, ana):
    for _ in range(5):
        client.post(
            "/auth/me/password",
            json={"current_password": "chute", "new_password": "nova-senha-123"},
            headers=ana,
        )
    response = client.post(
        "/auth/me/password",
        json={"current_password": PASSWORD, "new_password": "nova-senha-123"},
        headers=ana,
    )
    assert response.status_code == 429
