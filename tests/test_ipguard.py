import dataclasses
import hashlib
import ipaddress

import pytest
from fastapi.testclient import TestClient

import app.ipguard as ipguard_module
from app.deps import get_today
from app.ipguard import IntervalSet, IpGuard, parse_ip
from app.main import create_app
from tests.conftest import PASSWORD, TODAY

BRAZIL_IP = "177.10.20.30"
BRAZIL_V6 = "2804:14c:1:2::99"
FOREIGN_IP = "8.8.4.4"
VPN_IP = "45.12.34.56"


def test_interval_set_lookup():
    nets = IntervalSet(["10.0.0.0/24", "10.0.1.0/24", "2804::/16", "# comentário", "lixo"])
    assert len(nets) == 2  # as duas /24 vizinhas viram uma faixa só
    assert ipaddress.ip_address("10.0.1.200") in nets
    assert ipaddress.ip_address("10.0.2.1") not in nets
    assert ipaddress.ip_address("2804:abcd::1") in nets
    assert ipaddress.ip_address("2805::1") not in nets
    assert parse_ip("::ffff:177.10.20.30") == ipaddress.ip_address(BRAZIL_IP)


def test_bundled_brazil_list_is_loaded():
    guard = IpGuard("x")
    guard.load_bundled()
    assert len(guard.country) > 1000
    assert guard.classify(parse_ip("200.147.3.157")) == "br"  # bloco brasileiro conhecido
    assert guard.classify(parse_ip("8.8.8.8")) == "fora"


@pytest.fixture
def guarded(settings, monkeypatch):
    monkeypatch.setattr(ipguard_module, "BITS", 8)  # desafio fácil: o teste fica rápido
    application = create_app(dataclasses.replace(settings, ipguard_enabled=True))
    application.dependency_overrides[get_today] = lambda: TODAY
    application.state.ipguard.clock = lambda: 1_900_000_000.0  # relógio parado: sem virar janela
    application.state.ipguard.load(
        country=["177.0.0.0/8", "2804::/16"], vpn=["45.0.0.0/8", "2a01::/16"]
    )
    with TestClient(application) as test_client:
        yield test_client


def as_ip(ip):
    return {"CF-Connecting-IP": ip}


def solve(client, ip) -> str:
    challenge = client.get("/_seguranca/desafio", headers=as_ip(ip)).json()
    n = 0
    while True:
        digest = hashlib.sha256(f"{challenge['salt']}:{n}".encode()).digest()
        if int.from_bytes(digest, "big") >> (256 - challenge["bits"]) == 0:
            return client.post(
                "/_seguranca/verificar",
                json={"token": challenge["token"], "nonce": str(n)},
                headers=as_ip(ip),
            )
        n += 1


def register(client, ip, email):
    payload = {
        "name": "Ana Souza",
        "email": email,
        "phone": "11987654321",
        "city": "Campinas, SP",
        "password": PASSWORD,
    }
    return client.post("/auth/register", json=payload, headers=as_ip(ip))


def test_brazil_has_free_access(guarded):
    assert guarded.get("/site", headers=as_ip(BRAZIL_IP)).status_code == 200
    assert register(guarded, BRAZIL_IP, "ana@ex.com").status_code == 201
    assert guarded.get("/site", headers=as_ip(BRAZIL_V6)).status_code == 200


def test_vpn_goes_to_the_challenge_page(guarded):
    page = guarded.get("/", headers={**as_ip(VPN_IP), "Accept": "text/html"})
    assert page.status_code == 403 and "Verificação de segurança" in page.text
    api = guarded.get("/site", headers=as_ip(VPN_IP))
    assert api.status_code == 403 and api.json()["challenge"] is True
    # O que é necessário para a própria verificação (e para o monitor) continua aberto.
    assert guarded.get("/health", headers=as_ip(VPN_IP)).status_code == 200
    assert guarded.get("/static/marca-clara.png", headers=as_ip(VPN_IP)).status_code == 200

    passed = solve(guarded, VPN_IP)
    assert passed.status_code == 200
    assert guarded.get("/site", headers=as_ip(VPN_IP)).status_code == 200  # cookie liberou
    # O mesmo cookie não vale para outro IP.
    assert guarded.get("/site", headers=as_ip("45.99.99.99")).status_code == 403


def test_forged_forwarded_for_does_not_bypass(guarded):
    headers = {**as_ip(VPN_IP), "X-Forwarded-For": BRAZIL_IP}
    assert guarded.get("/site", headers=headers).status_code == 403


def test_abroad_can_look_but_actions_need_the_challenge(guarded):
    assert guarded.get("/site", headers=as_ip(FOREIGN_IP)).status_code == 200
    assert guarded.get("/events", headers=as_ip(FOREIGN_IP)).status_code == 200
    blocked = register(guarded, FOREIGN_IP, "bia@ex.com")
    assert blocked.status_code == 403 and blocked.json()["challenge"] is True
    assert solve(guarded, FOREIGN_IP).status_code == 200
    assert register(guarded, FOREIGN_IP, "bia@ex.com").status_code == 201


def test_abroad_has_a_low_request_limit(guarded):
    statuses = [guarded.get("/site", headers=as_ip(FOREIGN_IP)).status_code for _ in range(160)]
    assert statuses[:150] == [200] * 150
    assert set(statuses[150:]) == {403}


def test_abuse_after_passing_means_endless_challenges(guarded):
    assert solve(guarded, FOREIGN_IP).status_code == 200
    for _ in range(151):
        guarded.get("/site", headers=as_ip(FOREIGN_IP))
    # Marcado: o desafio continua aparecendo e nunca é aprovado, por mais que resolva.
    for _ in range(3):
        assert solve(guarded, FOREIGN_IP).status_code == 403
    assert guarded.get("/site", headers=as_ip(FOREIGN_IP)).status_code == 403


def test_fake_answers_and_wrong_passwords_flag_the_ip(guarded):
    challenge = guarded.get("/_seguranca/desafio", headers=as_ip(VPN_IP)).json()
    for n in range(5):
        guarded.post(
            "/_seguranca/verificar",
            json={"token": challenge["token"] + "x", "nonce": str(n)},
            headers=as_ip(VPN_IP),
        )
    assert solve(guarded, VPN_IP).status_code == 403  # marcado

    other = "45.1.1.1"
    assert solve(guarded, other).status_code == 200
    for _ in range(5):
        guarded.post(
            "/auth/token",
            data={"username": "x@ex.com", "password": "errada-123"},
            headers=as_ip(other),
        )
    assert solve(guarded, other).status_code == 403


def test_brazil_flood_only_slows_down(guarded):
    statuses = {guarded.get("/site", headers=as_ip(BRAZIL_IP)).status_code for _ in range(905)}
    assert statuses == {200, 429}
    assert not guarded.app.state.ipguard.is_flagged(BRAZIL_IP)  # nunca marcado


def test_link_previews_still_work(guarded):
    preview = {**as_ip(VPN_IP), "User-Agent": "WhatsApp/2.23", "Accept": "text/html"}
    response = guarded.get("/", headers=preview)
    assert response.status_code == 200 and "Verificação de segurança" not in response.text
    assert guarded.get("/site", headers=preview).status_code == 403  # dados, não
