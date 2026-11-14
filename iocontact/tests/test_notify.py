"""Notifications from ioContact: the morning's birthdays and anniversaries, once a day."""
import datetime as dt

import pytest
from iosuite_shared import push, users

from app import notify
from tests.test_api import mk


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "_post", lambda endpoint, body, headers: out.append(body) or 201)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    return out


def test_birthdays_in_the_morning(client, family_id, sent):
    from cryptography.hazmat.primitives.asymmetric import ec
    alex = users.find("alex")["id"]
    today = dt.date.today()
    mk(client, family_id, fn="Emma", birthday={"year": today.year - 9, "month": today.month, "day": today.day})
    mk(client, family_id, fn="Quiet", birthday={"year": 1981, "month": today.month, "day": today.day}, birthdayRemind=False)
    mk(client, family_id, fn="Tomorrow", birthday={"month": (today + dt.timedelta(days=1)).month, "day": (today + dt.timedelta(days=1)).day})
    k = ec.generate_private_key(ec.SECP256R1())
    push.add_device(alex, {"endpoint": "https://fcm.googleapis.com/fcm/send/a",
                           "keys": {"p256dh": push.b64u(push._raw_public(k.public_key())), "auth": push.b64u(b"0123456789abcdef")}}, "iocontact")
    assert [notify._line(x) for x in notify.today_for(users.get(alex, "iocontact"))] == ["Emma turns 9"]
    push.set_prefs(alex, morning="08:00")
    assert notify.run(dt.datetime.combine(today, dt.time(7, 30))) == 0
    assert notify.run(dt.datetime.combine(today, dt.time(8, 5))) == 1
    assert notify.run(dt.datetime.combine(today, dt.time(8, 6))) == 0
    push.set_prefs(alex, {"birthdays": False})
    assert notify.run(dt.datetime.combine(today + dt.timedelta(days=1), dt.time(8, 5))) == 0, "turned off"
