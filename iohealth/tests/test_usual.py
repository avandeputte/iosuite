"""Outside your usual: the last seven days against the four weeks before, on the dashboard (GET /api/usual) and as a
notification once, on the day it begins."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from iosuite_shared import push

from app import notify, usual, webapi
from tests.test_api import app_password, sample, upload
from tests.test_notify import _night, _with_device

UTC = timezone.utc


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "_post", lambda endpoint, body, headers: out.append(endpoint) or 201)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    return out


def _noon(admin, days_ago):
    """Noon UTC on the person's day `days_ago` days back (the same day in Brussels, the tests' zone)."""
    d = datetime.now(webapi.zone_of(admin["id"])).date() - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day, 12, tzinfo=UTC)


def _days(admin, typ, unit, values, first_ago):
    """One sample a day, the first `first_ago` days back."""
    return [sample(f"{typ}-{first_ago - i}", typ, _noon(admin, first_ago - i), v, unit) for i, v in enumerate(values) if v is not None]


def test_the_week_against_the_four_before():
    steady = [55] * 28
    assert usual.off("rhr", steady + [61] * 7, 5) == {"key": "rhr", "now": 61, "usual": 55}
    assert usual.off("rhr", steady + [59] * 7, 5) is None, "four up is within five"
    assert usual.off("rhr", steady + [61] * 7, 0) is None, "0 turns it off"
    assert usual.off("rhr", steady + [None] * 5 + [70, 70], 5) is None, "two days are not a week"
    assert usual.off("rhr", [None] * 22 + [55] * 6 + [70] * 7, 5) is None, "six days are not a usual"
    assert usual.off("hrv", [50] * 28 + [42] * 7, 15)["now"] == 42          # 16% down
    assert usual.off("hrv", [50] * 28 + [43] * 7, 15) is None               # 14% down
    assert usual.off("hrv", [50] * 28 + [60] * 7, 15) is None, "up is good news"
    assert usual.off("sleep", [7.5] * 28 + [6.7] * 7, 45)["usual"] == 7.5   # 48 minutes less
    assert usual.off("sleep", [7.5] * 28 + [7.0] * 7, 45) is None


def test_defaults_are_the_settings_pages():
    js = (Path(__file__).parent.parent / "static/js/core.js").read_text()
    shown = dict(re.findall(r"(\w+): (\d+)", re.search(r"ALERT_DEFAULTS = \{([^}]*)\}", js).group(1)))
    assert {k: int(shown[k]) for k in usual.DEFAULTS} == usual.DEFAULTS


def test_dashboard_says_what_left_the_usual(client, admin):
    pw = app_password(client)
    assert client.get("/api/usual").json() == [], "nothing synced: nothing to say"
    upload(client, pw, *_days(admin, "resting_heart_rate", "count/min", [55] * 28 + [62] * 7, 34),
           *_days(admin, "heart_rate_variability_sdnn", "ms", [50] * 28 + [49] * 7, 34))
    found = client.get("/api/usual").json()
    assert [f["key"] for f in found] == ["rhr"]
    f = found[0]
    assert f["title"] == "Resting heart rate is up" and f["body"].startswith("62 bpm this week against your usual 55.")
    assert f["href"].startswith("#/metrics?types=resting_heart_rate") and f["new"] is False, "it has been up all week"
    client.put("/api/settings", json={"alerts": {"rhr": "10"}})
    assert client.get("/api/usual").json() == []
    client.put("/api/settings", json={"alerts": {"rhr": "", "hrv": "1"}})  # empty: the default again
    assert [f["key"] for f in client.get("/api/usual").json()] == ["rhr", "hrv"]
    client.put("/api/settings", json={"alerts": {"rhr": "0", "hrv": 0}})
    assert client.get("/api/usual").json() == []


def test_sleep_and_the_hidden_section(client, admin):
    pw = app_password(client)
    nights = [_night(f"n{i}", _noon(admin, i) - timedelta(hours=13), 450 if i > 6 else 380) for i in range(34, -1, -1)]  # from 23:00 UTC the evening before
    upload(client, pw, *nights)
    found = client.get("/api/usual").json()
    assert [f["key"] for f in found] == ["sleep"]
    assert found[0]["title"] == "Sleep is down" and found[0]["body"] == "6 h 20 a night this week against your usual 7 h 30 (70 min less)."
    client.put("/api/settings", json={"hiddenSections": ["sleep"]})
    assert client.get("/api/usual").json() == [], "sleep switched off in Settings › Display"


def test_notified_once_on_the_day_it_begins(client, admin, sent):
    """Resting heart rate of 55 for five weeks, then three days of 75 up to today: today the week's average passes
    the usual by five (yesterday it had not)."""
    uid = admin["id"]
    pw = app_password(client)
    upload(client, pw, *_days(admin, "resting_heart_rate", "count/min", [55] * 39 + [70, 70, 72], 41))
    _with_device(uid)
    loc = webapi.zone_of(uid)
    today = datetime.now(loc).replace(hour=0, minute=0, second=0, microsecond=0)
    found = usual.findings(uid, loc)
    assert [f["key"] for f in found] == ["rhr"] and found[0]["new"] is True
    assert notify.outside_usual(uid, now=today.replace(hour=6)) == 0, "not before the morning time (08:00)"
    assert notify.usual_morning(now=today.replace(hour=7, minute=59)) == 0
    assert notify.usual_morning(now=today.replace(hour=8, minute=1)) == 1
    assert notify.usual_morning(now=today.replace(hour=8, minute=2)) == 0, "looked at once a morning"
    assert notify.outside_usual(uid, now=today.replace(hour=15)) == 0, "a later sync does not say it again"
    assert len(sent) == 1
    tomorrow = today + timedelta(days=1)
    assert usual.findings(uid, loc, tomorrow.replace(hour=9))[0]["new"] is False
    assert notify.outside_usual(uid, now=tomorrow.replace(hour=9)) == 0, "still up tomorrow: nothing new"
    push.set_prefs(uid, {"health_usual": False})
    assert notify.outside_usual(uid, now=today.replace(hour=16)) == 0


def test_a_sync_after_the_morning_time_looks_again(client, admin, sent):
    """The morning came with nothing to say; the sync that brings today's reading does."""
    uid = admin["id"]
    pw = app_password(client)
    upload(client, pw, *_days(admin, "resting_heart_rate", "count/min", [55] * 39 + [66, 66], 41))  # up to yesterday: +3.1
    _with_device(uid)
    loc = webapi.zone_of(uid)
    today = datetime.now(loc).replace(hour=0, minute=0, second=0, microsecond=0)
    assert notify.usual_morning(now=today.replace(hour=8, minute=1)) == 0
    upload(client, pw, sample("today", "resting_heart_rate", _noon(admin, 0), 75, "count/min"))  # 7 days: 55 x4, 66, 66, 75 = +5.3
    assert notify.outside_usual(uid, now=today.replace(hour=13)) == 1
    assert notify.outside_usual(uid, now=today.replace(hour=14)) == 0
