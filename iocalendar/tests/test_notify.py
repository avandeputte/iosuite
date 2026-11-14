"""Notifications from ioCalendar: an event's reminders when they go off, once, for whom the event is."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from iosuite_shared import push, users

from app import notify
from tests.test_api import mk

NY = ZoneInfo("America/New_York")


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "_post", lambda endpoint, body, headers: out.append(endpoint) or 201)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    return out


def device(uid):
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    push.add_device(uid, {"endpoint": f"https://fcm.googleapis.com/fcm/send/{uid}",
                          "keys": {"p256dh": push.b64u(push._raw_public(k.public_key())), "auth": push.b64u(b"0123456789abcdef")}}, "iocalendar")


def test_reminders(client, family_id, sent):
    alex = users.find("alex")["id"]
    start = dt.datetime(2026, 11, 20, 14, 0, tzinfo=NY)
    mk(client, family_id, title="Dentist", start="2026-11-20T14:00", end="2026-11-20T15:00", timezone="America/New_York",
       location="Main St 1", reminders=[30, 1440])
    mk(client, family_id, title="No reminder", start="2026-11-20T14:00", end="2026-11-20T15:00", timezone="America/New_York")
    mk(client, family_id, title="Weekly swim", start="2026-11-06T17:00", end="2026-11-06T18:00", timezone="America/New_York",
       rrule="FREQ=WEEKLY", reminders=[60])
    assert notify.run(start - dt.timedelta(minutes=29)) == 0, "nobody has a device"
    device(alex)
    assert notify.run(start - dt.timedelta(minutes=45)) == 0, "too early"
    assert notify.run(start - dt.timedelta(minutes=29)) == 1
    assert notify.run(start - dt.timedelta(minutes=28)) == 0, "once"
    assert notify.run(start - dt.timedelta(days=1) + dt.timedelta(minutes=5), long=True) == 1, "a day ahead"
    assert notify.run(start - dt.timedelta(days=1) + dt.timedelta(minutes=6)) == 0, "once, whichever pass sent it"
    # the weekly swim: each occurrence's reminder
    assert notify.run(dt.datetime(2026, 11, 13, 16, 2, tzinfo=NY)) == 1
    assert notify.run(dt.datetime(2026, 11, 20, 16, 2, tzinfo=NY)) == 1
    assert len(sent) == 4
    assert notify._when(start, False, start - dt.timedelta(minutes=30)) == "In 30 minutes"
    assert notify._when(start, False, start - dt.timedelta(days=1)) == "Tomorrow at 14:00"
