"""Notifications from ioHealth: "goal reached" after a sync, once per goal and day, only for goals in units that mean
the same everywhere."""
from datetime import datetime, timedelta, timezone

import pytest
from iosuite_shared import push

from app import notify
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
    t = max(now - timedelta(hours=1), datetime.now(notify._zone()).replace(hour=0, minute=5, second=0, microsecond=0).astimezone(timezone.utc))
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
