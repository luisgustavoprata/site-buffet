import random
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.models import PushPlan, as_utc
from app.notifications import MESSAGES, ensure_plan, run_due
from app.webpush import Vapid, b64url, encrypt, is_push_service, unb64url

BRT = ZoneInfo("America/Sao_Paulo")


def test_encryption_matches_rfc_8291_example():
    """Exemplo oficial da RFC 8291 (seção 5): mesmas chaves e sal, mesmo resultado."""
    sender = ec.derive_private_key(
        int.from_bytes(unb64url("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"),
        ec.SECP256R1(),
    )
    body = encrypt(
        b"When I grow up, I want to be a watermelon",
        unb64url(
            "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
        ),
        unb64url("BTBZMqHH6r4Tts7J_aSIgg"),
        sender_key=sender,
        salt=unb64url("DGv6ra1nlYgDCS1FRnbzlw"),
    )
    assert b64url(body) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27ml"
        "mlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPT"
        "pK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )


def test_vapid_signature():
    vapid = Vapid.generate("mailto:dona@buffet.com")
    header = vapid.authorization("https://fcm.googleapis.com/fcm/send/abc", now=1_000_000)
    token = header.split("t=")[1].split(",")[0]
    key = header.split("k=")[1]
    public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), unb64url(key))
    claims = jwt.decode(
        token,
        public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ),
        algorithms=["ES256"],
        audience="https://fcm.googleapis.com",
        options={"verify_exp": False},
    )
    assert claims["sub"] == "mailto:dona@buffet.com"
    assert claims["exp"] == 1_000_000 + 12 * 3600
    assert Vapid.from_private(vapid.private_b64, "x").public_b64 == vapid.public_b64


def test_only_real_push_services_are_accepted():
    assert is_push_service("https://fcm.googleapis.com/fcm/send/x")
    assert is_push_service("https://updates.push.services.mozilla.com/wpush/v2/x")
    assert is_push_service("https://web.push.apple.com/x")
    assert is_push_service("https://wns2-bl2p.notify.windows.com/w/?token=x")
    assert not is_push_service("http://fcm.googleapis.com/x")
    assert not is_push_service("https://fcm.googleapis.com.evil.com/x")
    assert not is_push_service("https://localhost:8000/x")


def device(endpoint="https://fcm.googleapis.com/fcm/send/abc"):
    key = ec.generate_private_key(ec.SECP256R1()).public_key()
    raw = key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return {"endpoint": endpoint, "keys": {"p256dh": b64url(raw), "auth": b64url(b"0" * 16)}}


@pytest.fixture
def outbox(app):
    sent = []

    def fake_sender(target, payload, vapid):
        sent.append((target.endpoint, payload))
        return 410 if "gone" in target.endpoint else 201

    app.state.push_sender = fake_sender
    return sent


def test_turn_notifications_on_and_off(client, ana, outbox):
    config = client.get("/push/config").json()
    assert len(unb64url(config["public_key"])) == 65
    assert (config["start_hour"], config["end_hour"]) == (7, 19)

    assert client.post("/push/devices", json=device()).status_code == 401
    bad = device("https://meu-servidor.com/coleta")
    assert client.post("/push/devices", json=bad, headers=ana).status_code == 422
    broken = device()
    broken["keys"]["auth"] = "curta"
    assert client.post("/push/devices", json=broken, headers=ana).status_code == 422

    assert client.post("/push/devices", json=device(), headers=ana).status_code == 201
    assert client.post("/push/devices", json=device(), headers=ana).status_code == 201  # de novo
    result = client.post("/push/test", headers=ana).json()
    assert result == {"devices": 1, "sent": 1}
    assert outbox[0][1]["title"] == "Notificações ativadas ✅"
    assert outbox[0][1]["body"].startswith("Pronto, Ana!")
    assert client.post("/push/test", headers=ana).status_code == 429  # calma

    params = {"endpoint": device()["endpoint"]}
    assert client.delete("/push/devices", params=params, headers=ana).status_code == 204


def _session(app):
    return app.state.session_factory.begin()


def test_daily_plan_stays_inside_the_window(app, client, settings):
    morning = datetime(2030, 1, 7, 6, 30, tzinfo=BRT).astimezone(UTC)
    with _session(app) as db:
        ensure_plan(db, settings, morning, random.Random(1))
        ensure_plan(db, settings, morning, random.Random(2))  # não sorteia de novo
        plans = list(db.query(PushPlan).order_by(PushPlan.send_at))
        assert len(plans) == settings.push_per_day == 2
        times = [as_utc(p.send_at).astimezone(BRT) for p in plans]
        assert all(7 <= t.hour < 19 for t in times)
        assert times[1] - times[0] >= timedelta(hours=1)  # nunca coladas
        assert all(t.date() == morning.astimezone(BRT).date() for t in times)

    late = datetime(2030, 1, 8, 18, 55, tzinfo=BRT).astimezone(UTC)  # dia seguinte, tarde demais
    with _session(app) as db:
        ensure_plan(db, settings, late, random.Random(3))
        assert db.query(PushPlan).filter(PushPlan.day == late.astimezone(BRT).date()).count() == 0


@pytest.mark.parametrize("seed", range(30))
def test_random_times_never_leave_the_window(app, client, settings, seed):
    start = datetime(2030, 1, 7, 0, 0, tzinfo=BRT) + timedelta(minutes=37 * seed)
    with _session(app) as db:
        ensure_plan(db, settings, start.astimezone(UTC), random.Random(seed))
        for plan in db.query(PushPlan):
            local = as_utc(plan.send_at).astimezone(BRT)
            assert 7 <= local.hour < 19 and local >= start


def test_scheduled_messages_go_only_to_clients_inside_the_window(
    app, client, settings, ana, owner, outbox
):
    client.post("/push/devices", json=device(), headers=ana)
    client.post("/push/devices", json=device("https://fcm.googleapis.com/x/gone"), headers=ana)
    client.post("/push/devices", json=device("https://web.push.apple.com/owner"), headers=owner)
    morning = datetime(2030, 1, 7, 7, 0, tzinfo=BRT).astimezone(UTC)
    with _session(app) as db:
        ensure_plan(db, settings, morning, random.Random(5))
        first, second = db.query(PushPlan).order_by(PushPlan.send_at).all()
        first_at, second_at = as_utc(first.send_at), as_utc(second.send_at)

    with _session(app) as db:  # antes da hora: nada
        assert run_due(db, settings, first_at - timedelta(minutes=1), app.state.push_sender) == 0
    with _session(app) as db:  # na hora: só os aparelhos dos clientes
        assert run_due(db, settings, first_at, app.state.push_sender) == 1
    assert [e for e, _ in outbox] == [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://fcm.googleapis.com/x/gone",
    ]
    assert outbox[0][1]["url"].startswith("/#/")
    with _session(app) as db:  # o aparelho desativado (410) saiu da lista; não repete
        assert run_due(db, settings, first_at + timedelta(minutes=1), app.state.push_sender) == 0

    # O servidor ficou parado e só voltou às 20h: a segunda não sai atrasada.
    night = datetime(2030, 1, 7, 20, 0, tzinfo=BRT).astimezone(UTC)
    assert night > second_at
    with _session(app) as db:
        assert run_due(db, settings, night, app.state.push_sender) == 0
        assert {p.status for p in db.query(PushPlan)} == {"enviada", "pulada"}
    assert len(outbox) == 2

    summary = client.get("/admin/push", headers=owner).json()
    assert summary["clients"] == 1 and summary["devices"] == 1
    assert len(summary["messages"]) == len(MESSAGES)
    assert client.get("/admin/push", headers=ana).status_code == 403


def test_messages_fit_a_notification():
    for message in MESSAGES:
        assert len(message.title) <= 50, message.key
        assert len(message.body) <= 120, message.key
