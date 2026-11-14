"""Notifications from ioHealth: "goal reached" after a sync, once per goal and day, only for goals in units that mean
the same everywhere."""
from datetime import datetime, timedelta, timezone

import pytest
from iosuite_shared import push

from app import notify, webapi
from tests.test_api import app_password, sample, upload


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "_post", lambda endpoint, body, headers: out.append(endpoint) or 201)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    return out


def test_goal_reached(client, admin, sent):
    from cryptography.hazmat.primitives.asymmetric import ec
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    t = max(now - timedelta(hours=1), datetime.now(webapi.zone_of(admin['id'])).replace(hour=0, minute=5, second=0, microsecond=0).astimezone(timezone.utc))
    pw = app_password(client)
    upload(client, pw, sample("a", "step_count", t, 6000), sample("b", "step_count", t + timedelta(minutes=2), 5000),
           sample("c", "distance_walking_running", t, 9.0, "km"))
    client.put("/api/settings", json={"goals": [{"type": "step_count", "dir": "min", "value": "10000"},
                                                {"type": "distance_walking_running", "dir": "min", "value": "5"},
                                                {"type": "body_mass", "dir": "max", "value": "80"}]})
    assert notify.after_sync(admin["id"]) == 0, "no device yet"
    k = ec.generate_private_key(ec.SECP256R1())
    push.add_device(admin["id"], {"endpoint": "https://fcm.googleapis.com/fcm/send/h",
                                  "keys": {"p256dh": push.b64u(push._raw_public(k.public_key())), "auth": push.b64u(b"0123456789abcdef")}}, "iohealth")
    assert notify.after_sync(admin["id"]) == 1, "steps only: a distance goal is in the units the page shows"
    assert notify.after_sync(admin["id"]) == 0, "once a day"
    assert len(sent) == 1


def _with_device(uid):
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    push.add_device(uid, {"endpoint": "https://fcm.googleapis.com/fcm/send/z",
                          "keys": {"p256dh": push.b64u(push._raw_public(k.public_key())), "auth": push.b64u(b"0123456789abcdef")}}, "iohealth")


def test_today_is_the_persons_own_day(client, admin, sent):
    """Steps walked at 01:00 on the 11th in Kiritimati (UTC+14) are the 10th in UTC: they count for the 11th once the
    phone (or the web app) said where the person is."""
    pw = app_password(client)
    t = datetime(2026, 11, 10, 11, 0, tzinfo=timezone.utc)
    upload(client, pw, sample("k", "step_count", t, 12000))
    client.put("/api/settings", json={"goals": [{"type": "step_count", "dir": "min", "value": "10000"}]})
    _with_device(admin["id"])
    noon_11th = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)
    assert notify.after_sync(admin["id"], now=noon_11th) == 0, "in UTC (the server's TZ) they are the 10th's"
    r = client.post("/v1/sessions", json={"deviceName": "aphone", "timeZone": "Pacific/Kiritimati"}, headers={"Authorization": f"Bearer {pw}"})
    assert r.status_code == 201
    assert str(webapi.zone_of(admin["id"])) == "Pacific/Kiritimati"
    assert notify.after_sync(admin["id"], now=datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)) == 1  # 13:00 on the 11th there
    # the web app's zone counts too, and a name that is no zone is ignored
    client.get("/api/series?type=step_count&tz=Europe/Brussels")
    assert str(webapi.zone_of(admin["id"])) == "Europe/Brussels"
    client.post("/v1/sessions", json={"timeZone": "Mars/Olympus"}, headers={"Authorization": f"Bearer {pw}"})
    assert str(webapi.zone_of(admin["id"])) == "Europe/Brussels"
