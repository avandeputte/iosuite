"""Notifications from ioTask: a task's alert, a timed task falling due, the morning summary, and who gets them."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from iosuite_shared import push, users

from app import notify
from tests.test_api import new
from iosuite_shared import testing

NY = ZoneInfo("America/New_York")


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "_post", lambda endpoint, body, headers: out.append(endpoint) or 201)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    return out


def device(uid, n=1):
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    push.add_device(uid, {"endpoint": f"https://fcm.googleapis.com/fcm/send/{uid}-{n}",
                          "keys": {"p256dh": push.b64u(push._raw_public(k.public_key())), "auth": push.b64u(b"0123456789abcdef")}}, "iotask")


def test_nothing_without_a_device(client, family_id, sent):
    new(client, title="Soon", due=(dt.datetime.now(NY) - dt.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M"), timezone="America/New_York", listId=family_id)
    assert notify.run() == 0 and sent == []


def test_due_alert_and_morning(client, family_id, sent):
    alex = users.find("alex")["id"]
    bob = testing.add_account(client, {"name": "bob", "password": "secret123", "role": "member"}).json()
    bob = bob.get("id") or users.find("bob")["id"]
    device(alex)
    device(bob)
    now = dt.datetime.now(NY)
    new(client, title="Take the bins out", due=(now - dt.timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M"), timezone="America/New_York", listId=family_id)
    new(client, title="Later", due=(now + dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"), timezone="America/New_York", listId=family_id)
    new(client, title="Old", due=(now - dt.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"), timezone="America/New_York", listId=family_id)
    alert_at = (now - dt.timedelta(minutes=1)).astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M+00:00")
    new(client, title="For bob", due=(now + dt.timedelta(days=2)).date().isoformat(), listId=family_id, members=[bob], alarms=[alert_at])
    later = (now + dt.timedelta(hours=1)).strftime("%H:%M")  # the morning summary is another test's
    push.set_prefs(alex, morning=later)
    push.set_prefs(bob, morning=later)
    assert notify.run() == 2, sent
    assert sorted(e.rsplit("/", 1)[1] for e in sent) == sorted([f"{alex}-1", f"{bob}-1"]), "the bins for alex (who added it), the alert for bob"
    assert notify.run() == 0, "once each"


def test_morning_summary(client, family_id, sent):
    alex = users.find("alex")["id"]
    device(alex)
    today = dt.datetime.now(NY).date()
    new(client, title="Pay the school trip", due=today.isoformat(), listId=family_id)
    new(client, title="Renew passport", due=(today - dt.timedelta(days=2)).isoformat(), listId=family_id)
    new(client, title="Next week", due=(today + dt.timedelta(days=7)).isoformat(), listId=family_id)
    push.set_prefs(alex, morning="08:00")
    at = dt.datetime.combine(today, dt.time(7, 0), NY)
    assert notify.run(at) == 0, "not yet morning"
    at = dt.datetime.combine(today, dt.time(8, 1), NY)
    assert notify.run(at) == 1
    assert notify.run(at) == 0, "one summary a day"
    assert push.was_sent(alex, f"tasks:morning:{today}")
