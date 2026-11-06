"""What the tiles show (app/widgets.py), with the apps' answers mocked: no app is asked over the network."""
import datetime as dt
from zoneinfo import ZoneInfo

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
    assert client.get("/api/widgets/ionotes").status_code == 404
    assert client.get("/api/widgets/iopix").status_code == 502


def test_iopix_on_this_day_one_per_year(client, apps_answer):
    table, asked = apps_answer
    year = dt.date.today().year
    table[("iopix", "/api/photos")] = {"id": [1, 2, 3, 4], "ts": [_ts(year, 1, 1), _ts(year - 1, 1, 1), _ts(year - 1, 1, 1), _ts(year - 5, 1, 1)]}
    d = client.get("/api/widgets/iopix?tz=Europe/Brussels").json()
    assert d["kind"] == "onthisday" and d["count"] == 3
    assert [i["yearsAgo"] for i in d["items"]] == [1, 5, 1]    # this year's photos left out; one from each year, then the rest
    assert {d["items"][0]["id"], d["items"][2]["id"]} == {2, 3} and d["items"][1]["id"] == 4
    table[("iopix", "/api/photos")] = {"id": [1, 2, 3, 4, 5], "ts": [_ts(year - 14, 1, 1)] * 5}
    d = client.get("/api/widgets/iopix").json()
    assert d["count"] == 5 and len(d["items"]) == 4 and all(i["yearsAgo"] == 14 for i in d["items"])  # four of one year's five
    key, path, params, cookie = asked[0]
    assert params["md"] == dt.datetime.now(widgets._zone("Europe/Brussels")).strftime("%m-%d") and cookie  # the viewer's own session goes along


def test_iopix_rediscover_when_nothing_today(client, apps_answer):
    table, _ = apps_answer
    table[("iopix", "/api/photos")] = {"id": [], "ts": []}
    table[("iopix", "/api/random")] = {"id": [7, 8], "ts": [_ts(2019, 5, 1), _ts(2020, 6, 1)]}
    d = client.get("/api/widgets/iopix").json()
    assert d == {"kind": "rediscover", "items": [{"id": 7, "year": 2019}, {"id": 8, "year": 2020}]}


def test_iopix_strip_asks_for_a_kind_and_a_count(client, apps_answer):
    table, asked = apps_answer
    year = dt.date.today().year
    table[("iopix", "/api/photos")] = {"id": [2], "ts": [_ts(year - 1, 1, 1)]}
    table[("iopix", "/api/random")] = lambda p: {"id": list(range(int(p["n"]))), "ts": [None] * int(p["n"])}
    d = client.get("/api/widgets/iopix?kind=rediscover&n=16").json()
    assert d["kind"] == "rediscover" and len(d["items"]) == 16 and asked[-1][1] == "/api/random"
    assert len(client.get("/api/widgets/iopix?kind=rediscover&n=99").json()["items"]) == 24  # capped
    d = client.get("/api/widgets/iopix?kind=onthisday&n=16").json()
    assert d["kind"] == "onthisday" and [i["id"] for i in d["items"]] == [2]
    assert client.get("/api/widgets/iopix?kind=whatever").json()["kind"] == "onthisday"  # an unknown kind: as the tile asks


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


def test_iohealth_steps_rings_sleep_and_week(client, apps_answer):
    table, asked = apps_answer
    zone = widgets._zone("Europe/Brussels")
    today = dt.datetime.now(zone).date()
    at = lambda d: int(dt.datetime.combine(d, dt.time(12), zone).timestamp())  # noqa: E731
    table[("iohealth", "/api/series")] = {"points": [{"t": at(today), "v": 8421.4, "n": 30}, {"t": at(today - dt.timedelta(days=2)), "v": 12000, "n": 40}]}
    table[("iohealth", "/api/activity")] = [{"date": "x", "move": 300, "moveGoal": 500, "exercise": 20, "exerciseGoal": 30, "stand": 8, "standGoal": 12}]
    table[("iohealth", "/api/sleep")] = [{"date": (today - dt.timedelta(days=1)).isoformat(), "asleep": 400, "inBed": 450, "start": "a", "end": "b"},
                                        {"date": today.isoformat(), "asleep": 441.6, "inBed": 480.2, "start": "2026-11-03T23:10:00+01:00", "end": "2026-11-04T07:30:00+01:00"}]
    d = client.get("/api/widgets/iohealth?tz=Europe/Brussels").json()
    assert d["steps"] == 8421 and d["rings"]["moveGoal"] == 500
    assert d["sleep"] == {"date": today.isoformat(), "asleep": 442, "inBed": 480, "start": "2026-11-03T23:10:00+01:00", "end": "2026-11-04T07:30:00+01:00"}
    assert len(d["week"]) == 7 and d["week"][-1] == {"date": today.isoformat(), "steps": 8421} and d["week"][4]["steps"] == 12000
    assert d["week"][0]["date"] == (today - dt.timedelta(days=6)).isoformat() and d["week"][0]["steps"] is None
    assert all(p["tz"] == "Europe/Brussels" and p["to"] == today.isoformat() for _, _, p, _ in asked)
    series = next(p for _, path, p, _ in asked if path == "/api/series")
    assert series["from"] == (today - dt.timedelta(days=6)).isoformat()  # seven days, today included

    table[("iohealth", "/api/series")] = {"points": []}
    table[("iohealth", "/api/activity")] = []
    del table[("iohealth", "/api/sleep")]  # sleep is a bonus: without it the tile still shows
    assert client.get("/api/widgets/iohealth").json() == {"steps": None, "rings": None, "sleep": None, "week": [{"date": (dt.date.today() - dt.timedelta(days=6 - i)).isoformat(), "steps": None} for i in range(7)]}


def test_iocalendar_yesterdays_all_day_event_is_not_today(client, apps_answer):
    """ioCalendar answers a window with the all-day events of the days around it (it pads by 14 h): yesterday's birthday
    must not show under Today, and a multi-day all-day event that is still on does."""
    table, _ = apps_answer
    table[("iocalendar", "/api/calendars")] = {"items": []}
    today = dt.date.today()
    yday, tmrw = today - dt.timedelta(days=1), today + dt.timedelta(days=1)
    later = {"calendarId": 1, "title": "Later", "start": (today + dt.timedelta(days=5)).isoformat(), "end": (today + dt.timedelta(days=6)).isoformat(), "allDay": True}
    table[("iocalendar", "/api/occurrences")] = {"items": [
        {"calendarId": 1, "title": "Ed's birthday", "start": yday.isoformat(), "end": today.isoformat(), "allDay": True},
        {"calendarId": 1, "title": "Holiday week", "start": yday.isoformat(), "end": (today + dt.timedelta(days=3)).isoformat(), "allDay": True},
        {"calendarId": 1, "title": "Tomorrow's thing", "start": tmrw.isoformat(), "end": (tmrw + dt.timedelta(days=1)).isoformat(), "allDay": True},
        later]}
    d = client.get("/api/widgets/iocalendar").json()
    assert [o["title"] for o in d["today"]] == ["Holiday week"]
    d = client.get("/api/widgets/iocalendar?kind=week").json()
    assert [(x["date"], [o["title"] for o in x["items"]]) for x in d["days"]] == [(tmrw.isoformat(), ["Holiday week", "Tomorrow's thing"]), ((today + dt.timedelta(days=5)).isoformat(), ["Later"])]
    table[("iocalendar", "/api/occurrences")] = {"items": [
        {"calendarId": 1, "title": "Ed's birthday", "start": yday.isoformat(), "end": today.isoformat(), "allDay": True}, later]}
    d = client.get("/api/widgets/iocalendar").json()
    assert d["today"] == [] and d["next"]["title"] == "Later"


def test_iocalendar_week_ahead(client, apps_answer):
    table, asked = apps_answer
    table[("iocalendar", "/api/calendars")] = {"items": [{"id": 1, "color": "#963522"}]}
    today = dt.datetime.now(ZoneInfo("Europe/Brussels")).date()  # the viewer's day, not the runner's (UTC 23:00 is Brussels' next day)
    tomorrow = today + dt.timedelta(days=1)
    day3 = today + dt.timedelta(days=3)
    table[("iocalendar", "/api/occurrences")] = {"items": [
        {"calendarId": 1, "title": "Dentist", "start": f"{day3}T10:00:00", "end": f"{day3}T11:00:00", "location": "Town"},
        {"calendarId": 2, "title": "Off", "start": tomorrow.isoformat(), "end": tomorrow.isoformat(), "allDay": True},
        {"calendarId": 1, "title": "Gone", "start": f"{tomorrow}T09:00:00", "end": f"{tomorrow}T10:00:00", "status": "CANCELLED"},
    ]}
    d = client.get("/api/widgets/iocalendar?kind=week&tz=Europe/Brussels").json()
    assert [x["date"] for x in d["days"]] == [tomorrow.isoformat(), day3.isoformat()] and d["more"] == 0
    assert d["days"][0]["items"] == [{"title": "Off", "start": tomorrow.isoformat(), "end": tomorrow.isoformat(), "allDay": True, "location": None, "color": None}]
    assert d["days"][1]["items"][0]["color"] == "#963522" and d["days"][1]["items"][0]["location"] == "Town"
    params = next(p for _, path, p, _ in asked if path == "/api/occurrences")
    assert params["start"].startswith(f"{tomorrow}T00:00:00") and params["end"].startswith((tomorrow + dt.timedelta(days=7)).isoformat())
    # without kind=week the tile's own view, as before
    assert "today" in client.get("/api/widgets/iocalendar").json()


def test_iocontacts_birthdays_and_photo(client, apps_answer):
    table, asked = apps_answer
    table[("iocontacts", "/api/upcoming")] = {"items": [
        {"contactId": 5, "fn": "Ada Lovelace", "hasPhoto": True, "label": "birthday", "turns": 41, "inDays": 0, "date": "2026-11-04"},
        {"contactId": 9, "fn": "Bob", "hasPhoto": False, "label": "anniversary", "turns": 10, "inDays": 12, "date": "2026-11-16"},
    ] + [{"contactId": i, "fn": f"P{i}", "inDays": 20} for i in range(10, 20)]}
    d = client.get("/api/widgets/iocontacts").json()
    assert len(d["items"]) == 8 and d["more"] == 4
    assert d["items"][0] == {"id": 5, "name": "Ada Lovelace", "hasPhoto": True, "label": "birthday", "turns": 41, "in": 0, "date": "2026-11-04"}
    assert d["items"][1]["label"] == "anniversary" and d["items"][2]["label"] == "birthday"
    assert asked[-1][2] == {"days": 30}
    table[("iocontacts", "/api/contacts/5/photo")] = (b"\xff\xd8jpeg", "image/jpeg")
    r = client.get("/api/widgets/iocontacts/photo/5")
    assert r.status_code == 200 and r.content == b"\xff\xd8jpeg" and r.headers["content-type"] == "image/jpeg"
    assert client.get("/api/widgets/iocontacts/photo/6").status_code == 502


def test_app_refusal_is_not_a_sign_out(client, monkeypatch):
    """An app's 401 must not read as "sign in to the start page"."""
    import urllib.error

    def refuse(*a, **kw):
        raise urllib.error.HTTPError("http://x", 401, "no", {}, None)
    monkeypatch.setattr(widgets.urllib.request, "urlopen", refuse)
    assert client.get("/api/widgets/iohealth").status_code == 403
    assert client.get("/api/widgets/iopix/thumb/5").status_code == 403


def test_quick_add_event(client, apps_answer):
    table, asked = apps_answer
    table[("iocalendar", "/api/calendars")] = {"items": [{"id": 1, "name": "Family", "color": "#f00", "writable": True},
                                                         {"id": 2, "name": "Holidays", "color": "#0f0", "writable": False}]}
    assert client.get("/api/widgets/iocalendar/calendars").json() == {"items": [{"id": 1, "name": "Family", "color": "#f00"}]}
    sent = []
    table[("iocalendar", "/api/events")] = lambda p: {"id": 42}

    def fake_post(request, key, path, params=None, raw=False, body=None):
        sent.append(body)
        return table[(key, path)](params or {})
    import app.widgets as w
    orig = w.fetch
    w.fetch = fake_post
    try:
        r = client.post("/api/widgets/iocalendar/events", json={"title": " Dinner ", "start": "2026-11-07T19:00:00+01:00", "allDay": False,
                                                                "timezone": "Europe/Brussels", "calendarId": 1})
        assert r.status_code == 200, r.text
        assert r.json()["id"] == 42 and r.json()["url"].endswith("/#/event/42")
        assert sent[-1] == {"title": "Dinner", "start": "2026-11-07T19:00:00+01:00", "allDay": False, "timezone": "Europe/Brussels", "calendarId": 1}
        r = client.post("/api/widgets/iocalendar/events", json={"title": "Holiday", "start": "2026-12-24", "allDay": True})
        assert r.status_code == 200 and sent[-1] == {"title": "Holiday", "start": "2026-12-24", "allDay": True}
        assert client.post("/api/widgets/iocalendar/events", json={"title": "", "start": "2026-12-24"}).status_code == 400
        assert client.post("/api/widgets/iocalendar/events", json={"title": "x", "start": "friday"}).status_code == 400
    finally:
        w.fetch = orig
