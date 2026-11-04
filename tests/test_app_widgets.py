"""What the tiles show (app/widgets.py), with the apps' answers mocked: no app is asked over the network."""
import datetime as dt

import pytest

from app import widgets


def _ts(y, m, d):
    return int(dt.datetime(y, m, d, 12, tzinfo=dt.timezone.utc).timestamp())


@pytest.fixture()
def apps_answer(monkeypatch):
    """Replace the request to an app with a table of answers: {(key, path): reply or callable(params)}."""
    table, asked = {}, []

    def fake(request, key, path, params=None, raw=False):
        asked.append((key, path, dict(params or {}), request.cookies.get("iothing_session")))
        r = table.get((key, path))
        if r is None:
            raise widgets.Unavailable(502, f"{key} is not reachable")
        return r(params or {}) if callable(r) else r
    monkeypatch.setattr(widgets, "fetch", fake)
    return table, asked


def test_needs_sign_in(client):
    client.cookies.clear()
    assert client.get("/api/widgets/iopix").status_code == 401


def test_unknown_app_and_unreachable(client, apps_answer):
    assert client.get("/api/widgets/iocontacts").status_code == 404
    assert client.get("/api/widgets/iopix").status_code == 502


def test_iopix_on_this_day_one_per_year(client, apps_answer):
    table, asked = apps_answer
    year = dt.date.today().year
    table[("iopix", "/api/photos")] = {"id": [1, 2, 3, 4], "ts": [_ts(year, 1, 1), _ts(year - 1, 1, 1), _ts(year - 1, 1, 1), _ts(year - 5, 1, 1)]}
    d = client.get("/api/widgets/iopix?tz=Europe/Brussels").json()
    assert d["kind"] == "onthisday" and d["count"] == 3
    assert [i["yearsAgo"] for i in d["items"]] == [1, 5]       # this year's photos left out, one per year
    assert d["items"][0]["id"] in (2, 3) and d["items"][1]["id"] == 4
    key, path, params, cookie = asked[0]
    assert params["md"] == dt.datetime.now(widgets._zone("Europe/Brussels")).strftime("%m-%d") and cookie  # the viewer's own session goes along


def test_iopix_rediscover_when_nothing_today(client, apps_answer):
    table, _ = apps_answer
    table[("iopix", "/api/photos")] = {"id": [], "ts": []}
    table[("iopix", "/api/random")] = {"id": [7, 8], "ts": [_ts(2019, 5, 1), _ts(2020, 6, 1)]}
    d = client.get("/api/widgets/iopix").json()
    assert d == {"kind": "rediscover", "items": [{"id": 7, "year": 2019}, {"id": 8, "year": 2020}]}


def test_iocalendar_rest_of_today_then_next(client, apps_answer):
    table, _ = apps_answer
    table[("iocalendar", "/api/calendars")] = {"items": [{"id": 1, "color": "#963522"}]}
    now = dt.datetime.now(dt.timezone.utc)
    past, soon = now - dt.timedelta(hours=3), now + dt.timedelta(hours=1)
    today = [
        {"calendarId": 1, "title": "Birthday", "start": now.date().isoformat(), "end": now.date().isoformat(), "allDay": True},
        {"calendarId": 1, "title": "Over", "start": past.isoformat(), "end": (past + dt.timedelta(minutes=30)).isoformat(), "allDay": False},
        {"calendarId": 1, "title": "Dentist", "start": soon.isoformat(), "end": (soon + dt.timedelta(hours=1)).isoformat(), "allDay": False},
        {"calendarId": 1, "title": "Off", "start": soon.isoformat(), "end": (soon + dt.timedelta(hours=1)).isoformat(), "allDay": False, "status": "CANCELLED"},
    ]
    table[("iocalendar", "/api/occurrences")] = {"items": today}
    d = client.get("/api/widgets/iocalendar?tz=UTC").json()
    assert [o["title"] for o in d["today"]] == ["Birthday", "Dentist"] and d["next"] is None
    assert d["today"][0]["color"] == "#963522"

    later = [{"calendarId": 1, "title": "Trip", "start": "2030-01-01", "end": "2030-01-02", "allDay": True}]
    table[("iocalendar", "/api/occurrences")] = lambda p: {"items": [] if p["start"].startswith(now.date().isoformat()) else later}
    d = client.get("/api/widgets/iocalendar?tz=UTC").json()
    assert d["today"] == [] and d["next"]["title"] == "Trip"


def test_iohealth_steps_and_rings(client, apps_answer):
    table, asked = apps_answer
    table[("iohealth", "/api/series")] = {"points": [{"t": 0, "v": 8421.4, "n": 30}]}
    table[("iohealth", "/api/activity")] = [{"date": "x", "move": 300, "moveGoal": 500, "exercise": 20, "exerciseGoal": 30, "stand": 8, "standGoal": 12}]
    d = client.get("/api/widgets/iohealth?tz=Europe/Brussels").json()
    assert d["steps"] == 8421 and d["rings"]["moveGoal"] == 500
    assert all(p["tz"] == "Europe/Brussels" and p["from"] == p["to"] for _, _, p, _ in asked)

    table[("iohealth", "/api/series")] = {"points": []}
    table[("iohealth", "/api/activity")] = []
    assert client.get("/api/widgets/iohealth").json() == {"steps": None, "rings": None}


def test_app_refusal_is_not_a_sign_out(client, monkeypatch):
    """An app's 401 must not read as "sign in to the start page"."""
    import urllib.error

    def refuse(*a, **kw):
        raise urllib.error.HTTPError("http://x", 401, "no", {}, None)
    monkeypatch.setattr(widgets.urllib.request, "urlopen", refuse)
    assert client.get("/api/widgets/iohealth").status_code == 403
    assert client.get("/api/widgets/iopix/thumb/5").status_code == 403
