"""Notifications (iosuite_shared.push): the encryption, the sender key, devices, choices, who gets what, and the routes."""
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from iosuite_shared import credentials, push, suite, users
from tests.test_fastapi import make_app


def ua_keys():
    k = ec.generate_private_key(ec.SECP256R1())
    return k, push.b64u(push._raw_public(k.public_key()))


def subscription(n=1):
    _k, pub = ua_keys()
    return {"endpoint": f"https://fcm.googleapis.com/fcm/send/device-{n}", "keys": {"p256dh": pub, "auth": push.b64u(b"0123456789abcdef")}}


class Sent(list):
    pass


@pytest.fixture
def sent(monkeypatch):
    """Nothing leaves the test: the push services answer 201 (or what `codes` says) and every request is kept."""
    out = Sent()
    codes = {}

    def post(endpoint, body, headers):
        out.append({"endpoint": endpoint, "body": body, "headers": headers})
        return codes.get(endpoint, 201)
    monkeypatch.setattr(push, "_post", post)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    out.codes = codes
    return out


def test_encryption_matches_rfc8291_example():
    """RFC 8291 section 5: the same keys, secret and salt give the same message, byte for byte."""
    as_key = ec.derive_private_key(int.from_bytes(push.b64u_decode("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    body = push.encrypt("BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4", "BTBZMqHH6r4Tts7J_aSIgg",
                        b"When I grow up, I want to be a watermelon", salt=push.b64u_decode("DGv6ra1nlYgDCS1FRnbzlw"), server_key=as_key)
    assert push.b64u(body) == ("DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6"
                               "cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def test_sender_key_is_made_once_and_kept_with_the_suites_keys():
    k1 = push.public_key()
    assert len(push.b64u_decode(k1)) == 65
    credentials.forget()
    assert push.public_key() == k1
    row = [x for x in credentials.listing("") if x["name"] == push.KEY_NAME][0]
    assert row["set"] and row["label"] == "Notifications sender key" and row["updatedBy"] == "made by itself"
    # the VAPID header is signed with it, for the push service's origin
    h = push._vapid_header("https://web.push.apple.com/abc")
    t = h.split("t=")[1].split(",")[0]
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push.b64u_decode(k1))
    claims = jwt.decode(t, pub.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo),
                        algorithms=["ES256"], audience="https://web.push.apple.com")
    assert claims["sub"].startswith("https://") and h.endswith("k=" + k1)


def test_clearing_the_key_makes_a_new_one_and_forgets_the_devices(sent):
    uid = users.create("alex", "secret123", "admin", "iostart", suite_admin=True)["id"]
    k1 = push.public_key()
    push.add_device(uid, subscription(), "iostart")
    credentials.put(push.KEY_APP, push.KEY_NAME, "")
    assert push.public_key() != k1
    assert push.devices(uid) == []


def test_devices_choices_and_who_gets_what(sent):
    suite.register("iotask", "ioTask")
    suite.register("iohealth", "ioHealth")
    alex = users.create("alex", "secret123", "admin", "iotask", suite_admin=True)["id"]
    bob = users.create("bob", "secret123", "member", "iotask")["id"]
    users.set_role(bob, "iohealth", "none")
    with pytest.raises(ValueError):
        push.add_device(bob, {"endpoint": "http://example.com/x", "keys": {}}, "iotask")
    with pytest.raises(ValueError):
        push.add_device(bob, {**subscription(), "keys": {"p256dh": "nope", "auth": "x"}}, "iotask")
    d = push.add_device(bob, subscription(1), "iotask", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131 Safari/537.36 Vivaldi/7.0")
    assert d["label"] == "Vivaldi on Mac" and d["appName"] == "ioTask"
    assert push.add_device(bob, subscription(1), "iotask")["id"] == d["id"], "the same subscription is one device"
    bob_kinds = [k["kind"] for k in push.overview(users.get(bob))["kinds"]]
    assert bob_kinds == ["tasks"], "only the kinds of the apps one uses, and no admin kinds"
    assert "updates" in [k["kind"] for k in push.offered(users.get(alex))]
    assert [u["id"] for u in push.recipients("tasks")] == [bob], "alex has no device"
    push.set_prefs(bob, {"tasks": False}, "07:30")
    assert push.recipients("tasks") == [] and push.prefs(bob) == {"off": ["tasks"], "morning": "07:30"}
    with pytest.raises(ValueError):
        push.set_prefs(bob, {"nonsense": True})
    with pytest.raises(ValueError):
        push.set_prefs(bob, morning="25:00")
    assert push.notify(bob, "tasks", "Due", "now") == 0 and not sent, "turned off: nothing goes out"
    push.set_prefs(bob, {"tasks": True})
    assert push.notify(bob, "health", "Goal") == 0, "not an ioHealth user"


def test_notify_once_and_what_the_push_service_gets(sent):
    suite.register("iotask", "ioTask", url="https://tasks.example.com")
    bob = users.create("bob", "secret123", "member", "iotask")["id"]
    sub = subscription(1)
    push.add_device(bob, sub, "iotask")
    push.add_device(bob, subscription(2), "iostart")
    url = push.link("iotask", "#/today")
    assert url == "https://tasks.example.com/#/today"
    assert push.notify(bob, "tasks", "Pack the swim bag", "Due now", url=url, once="task:1") == 2
    assert push.notify(bob, "tasks", "Pack the swim bag", "Due now", url=url, once="task:1") == 0, "once is once"
    assert len(sent) == 2
    h = sent[0]["headers"]
    assert h["Content-Encoding"] == "aes128gcm" and h["Authorization"].startswith("vapid t=") and h["TTL"] == "86400"
    assert sent[0]["body"][:16] != sent[1]["body"][:16], "a salt of its own each time"
    # 410: the browser dropped the subscription; 500: tried again later
    sent.codes[sub["endpoint"]] = 410
    sent.codes["https://fcm.googleapis.com/fcm/send/device-2"] = 500
    assert push.notify(bob, "tasks", "Again") == 0
    assert [d["app"] for d in push.devices(bob)] == ["iostart"]


def test_a_once_key_is_kept_only_when_a_device_took_it(sent):
    """A push service that is down (500, or not reached) leaves the key free: the next run sends it after all."""
    suite.register("iotask", "ioTask", url="https://tasks.example.com")
    bob = users.create("bob", "secret123", "member", "iotask")["id"]
    sub = subscription(1)
    push.add_device(bob, sub, "iotask")
    sent.codes[sub["endpoint"]] = 503
    assert push.notify(bob, "tasks", "Swim", once="task:9") == 0
    assert not push.was_sent(bob, "task:9")
    del sent.codes[sub["endpoint"]]
    assert push.notify(bob, "tasks", "Swim", once="task:9") == 1 and push.was_sent(bob, "task:9")
    assert push.notify(bob, "tasks", "Swim", once="task:9") == 0


def test_admin_kinds_go_to_suite_admins_only(sent):
    alex = users.create("alex", "secret123", "admin", "iostart", suite_admin=True)["id"]
    bob = users.create("bob", "secret123", "admin", "iostart")["id"]
    push.add_device(alex, subscription(1), "iostart")
    push.add_device(bob, subscription(2), "iostart")
    assert push.notify_admins("updates", "ioSuite 9.0.0 is out", once="update:9.0.0") == 1
    assert push.notify_admins("updates", "ioSuite 9.0.0 is out", once="update:9.0.0") == 0
    assert [s["endpoint"][-1] for s in sent] == ["1"]


def test_routes(sent):
    app, _ = make_app("iostart")
    users.create("alex", "secret123", "admin", "iostart", suite_admin=True)
    c = TestClient(app, base_url="http://start.example.com")
    assert c.get("/api/auth/push").status_code == 401
    assert c.get("/api/auth/push/sw.js").status_code == 200, "the worker script is open"
    c.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    r = c.get("/api/auth/push").json()
    assert r["key"] and r["devices"] == [] and r["morning"] == "08:00"
    assert "updates" in [k["kind"] for k in r["kinds"]]
    r = c.post("/api/auth/push/devices", json={"subscription": subscription(), "standalone": True},
               headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"})
    assert r.status_code == 200, r.text
    dev = r.json()["device"]
    assert dev["label"] == "Home-screen app on iPhone"
    r = c.put("/api/auth/push/prefs", json={"kinds": {"updates": False}, "morning": "07:00"}).json()
    assert r["morning"] == "07:00" and not [k for k in r["kinds"] if k["kind"] == "updates"][0]["on"]
    r = c.post("/api/auth/push/test", json={}).json()
    assert r == {"sent": 1, "devices": 1}
    assert c.delete(f"/api/auth/push/devices/{dev['id']}").json()["devices"] == []
    assert c.delete(f"/api/auth/push/devices/{dev['id']}").status_code == 404


def test_morning():
    import datetime as dt
    uid = users.create("bob", "secret123", "member", "iostart")["id"]
    push.set_prefs(uid, morning="08:00")
    assert not push.is_morning(uid, dt.datetime(2026, 11, 14, 7, 59))
    assert push.is_morning(uid, dt.datetime(2026, 11, 14, 8, 0))
    assert not push.is_morning(uid, dt.datetime(2026, 11, 14, 14, 0)), "not the morning summary in the afternoon"
    assert not push.was_sent(uid, "x") and push.claim(uid, "x") and push.was_sent(uid, "x")
