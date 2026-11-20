"""Kitchen timers (app/timers.py), the exchange rates for the search box's conversions (app/rates.py), and what the
iPhone app's widgets and Siri read and add (/dav/ext/today and friends, app/bookmarkext.py) with a full app password
from the sign-in flow (?scope=full, app/ncbookmarks.py)."""
import base64
import time

import pytest

from app import rates, timers, widgets


def _basic(name, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{name}:{pw}".encode()).decode()}


def _anon():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


# ------------------------------------------------------------------ timers

def test_timers_start_count_down_and_go(client):
    assert client.get("/api/timers").json()["items"] == []
    r = client.post("/api/timers", json={"seconds": 600, "label": "  Pasta  al dente "})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["label"] == "Pasta al dente" and t["seconds"] == 600 and t["by"] == "alex"
    got = client.get("/api/timers").json()
    assert [x["id"] for x in got["items"]] == [t["id"]] and 590 < got["items"][0]["endsAt"] - got["now"] <= 600
    assert client.post("/api/timers", json={"seconds": 0}).status_code == 400
    assert client.post("/api/timers", json={"seconds": 90000}).status_code == 400
    assert client.post("/api/timers", json={"seconds": "soon"}).status_code == 400
    assert client.post("/api/timers", json={"seconds": 5}).json()["label"] == "Timer"
    more = client.post(f"/api/timers/{t['id']}/more", json={"seconds": 60}).json()
    assert more["seconds"] == 660 and abs(more["endsAt"] - t["endsAt"] - 60) < 1
    assert client.delete(f"/api/timers/{t['id']}").status_code == 200
    assert client.delete(f"/api/timers/{t['id']}").status_code == 404
    assert client.post("/api/timers/999/more", json={}).status_code == 404
    client.cookies.clear()
    assert client.get("/api/timers").status_code == 401


def test_an_ended_timer_notifies_who_started_it_once_and_more_time_restarts_it(client, monkeypatch):
    sent = []
    monkeypatch.setattr(timers.push, "notify", lambda uid, kind, title, body="", **kw: sent.append((uid, kind, title, body, kw.get("once"))) or 1)
    t = client.post("/api/timers", json={"seconds": 90, "label": "Eggs"}).json()
    assert timers.tick() == 0 and sent == []
    assert timers.tick(time.time() + 91) == 1
    assert sent[0][1:4] == ("timers", "⏰ Eggs", "Your 1 min 30 s timer is done")
    assert timers.tick(time.time() + 95) == 0  # once
    # an ended timer given more time starts again from now, and rings again when that ends
    from app import db
    db.ex("UPDATE prt_timers SET ends_at = %s WHERE id = %s", (time.time() - 5, t["id"]))
    again = client.post(f"/api/timers/{t['id']}/more", json={"seconds": 60}).json()
    assert again["seconds"] == 60
    assert timers.tick(time.time() + 61) == 1 and len(sent) == 2
    # gone a while after it ended, without anyone dismissing it
    assert timers.listing(time.time() + 61 + timers.KEEP_AFTER_END + 5)["items"] == []


def test_timers_are_the_whole_familys(client):
    from iosuite_shared import testing
    client.post("/api/timers", json={"seconds": 300, "label": "Bread"})
    assert testing.add_account(client, {"name": "riley", "password": "secret123", "role": "viewer"}).status_code in (200, 201)
    other = _anon()
    assert other.post("/api/auth/login", json={"name": "riley", "password": "secret123"}).status_code == 200
    items = other.get("/api/timers").json()["items"]
    assert [(x["label"], x["by"]) for x in items] == [("Bread", "alex")]
    assert other.delete(f"/api/timers/{items[0]['id']}").status_code == 200


def test_the_timers_kind_of_notification_is_offered(client):
    from iosuite_shared import push
    assert push.KIND["timers"]["app"] == "iostart"


# ------------------------------------------------------------------ exchange rates

def test_rates_fetched_once_then_kept_and_the_old_ones_when_away(client, monkeypatch):
    calls = []

    def fetch():
        calls.append(1)
        return {"date": "2026-11-20", "rates": {"USD": 1.08, "GBP": 0.85, "EUR": 1.0}}
    monkeypatch.setattr(rates, "_fetch", fetch)
    r = client.get("/api/rates").json()
    assert r == {"base": "EUR", "date": "2026-11-20", "rates": {"USD": 1.08, "GBP": 0.85, "EUR": 1.0}}
    client.get("/api/rates")
    assert len(calls) == 1
    # six hours on, Frankfurter is away: the last rates, with their date
    from app import db
    import json
    kept = json.loads(db.get_setting("rates"))
    kept["at"] -= rates.RATES_TTL + 1
    db.set_setting("rates", json.dumps(kept))
    monkeypatch.setattr(rates, "_fetch", lambda: (_ for _ in ()).throw(rates.RatesError("down")))
    assert client.get("/api/rates").json()["date"] == "2026-11-20"


def test_rates_without_any_yet(client, monkeypatch):
    monkeypatch.setattr(rates, "_fetch", lambda: (_ for _ in ()).throw(rates.RatesError("Could not reach the exchange rates")))
    r = client.get("/api/rates")
    assert r.status_code == 502 and "exchange rates" in r.json()["detail"]


# ------------------------------------------------------------------ the iPhone app's widgets and Siri

def _flow(client, scope=""):
    anon = _anon()
    f = anon.post(f"/dav/nextcloud/index.php/login/v2?client=ioStart%20on%20aphone{'&scope=' + scope if scope else ''}", headers={"Host": "start.example.com"}).json()
    page = f["login"].replace("http://start.example.com", "")
    text = client.get(page).text
    client.post("/dav/nextcloud/index.php/login/v2/grant", data={"page": page.rsplit("/", 1)[-1]})
    got = anon.post("/dav/nextcloud/index.php/login/v2/poll", json={"token": f["poll"]["token"]}).json()
    return text, got["appPassword"], anon


def test_the_iphone_app_asks_for_a_full_app_password(client):
    text, pw, anon = _flow(client, "full")
    assert "full access" in text and "ioStart on aphone" in text
    items = client.get("/api/auth/app-passwords").json()["items"]
    assert [(p["label"], p.get("scope", "")) for p in items] == [("App: ioStart on aphone", "")]
    assert anon.get("/dav/ext", headers=_basic("alex", pw)).json()["full"] is True


def test_a_sync_only_password_is_told_to_sign_in_again(client):
    text, pw, anon = _flow(client)
    assert "sync only" in text
    h = _basic("alex", pw)
    assert anon.get("/dav/ext", headers=h).json()["full"] is False
    r = anon.get("/dav/ext/today", headers=h)
    assert r.status_code == 403 and r.json()["detail"]["signInAgain"] is True
    assert anon.post("/dav/ext/tasks", headers=h, json={"title": "x"}).status_code == 403
    assert anon.get("/dav/ext/today").status_code == 401


@pytest.fixture()
def apps_answer(monkeypatch):
    asked = []

    def fetch(request, key, path, params=None, raw=False, body=None, timeout=4):
        asked.append((key, path, params, body, request.headers.get("authorization")))
        if key == "iocalendar" and path == "/api/suite/tile":
            if (params or {}).get("kind") == "week":
                return {"days": [{"date": "2026-11-21", "items": [{"title": "Swim"}]}], "more": 0}
            return {"today": [{"title": "Dentist", "start": "2026-11-20T15:00:00+01:00"}], "more": 0, "next": None}
        if key == "iotask" and path == "/api/suite/tile":
            raise widgets.Unavailable(502, "ioTask answered 500")
        if path == "/api/calendars":
            return {"items": [{"id": 1, "name": "Family", "color": "#f00", "writable": True}]}
        if path == "/api/lists":
            return {"items": [{"id": 2, "name": "Home", "color": "#0f0", "writable": True}]}
        if path in ("/api/tasks", "/api/events"):
            return {"id": 7}
        raise AssertionError((key, path))
    monkeypatch.setattr(widgets, "fetch", fetch)
    return asked


def test_widgets_read_the_day_as_the_person(client, apps_answer):
    _, pw, anon = _flow(client, "full")
    h = _basic("alex", pw)
    d = anon.get("/dav/ext/today?tz=Europe/Brussels", headers=h).json()
    assert d["today"]["today"][0]["title"] == "Dentist" and d["week"]["days"][0]["items"][0]["title"] == "Swim"
    assert d["tasks"] is None and "ioTask" in d["errors"]["tasks"]
    assert d["links"]["iocalendar"].startswith("https://calendar.example.com")
    # asked with the app's own sign-in, passed on
    assert all(a[4] == h["Authorization"] for a in apps_answer)
    c = anon.get("/dav/ext/calendars", headers=h).json()
    assert c["calendars"] == [{"id": 1, "name": "Family", "color": "#f00"}] and c["lists"] == [{"id": 2, "name": "Home", "color": "#0f0"}]


def test_siri_adds_a_task_and_an_event(client, apps_answer):
    _, pw, anon = _flow(client, "full")
    h = _basic("alex", pw)
    r = anon.post("/dav/ext/tasks", headers=h, json={"title": "Buy milk", "due": "2026-11-21"})
    assert r.status_code == 200 and r.json()["url"].endswith("/#/task/7")
    assert apps_answer[-1][:4] == ("iotask", "/api/tasks", None, {"title": "Buy milk", "due": "2026-11-21"})
    r = anon.post("/dav/ext/events", headers=h, json={"title": "Dinner", "start": "2026-11-21T19:00:00+01:00", "allDay": False})
    assert r.status_code == 200 and r.json()["url"].endswith("/#/event/7")
    assert anon.post("/dav/ext/tasks", headers=h, json={"title": ""}).status_code == 400
