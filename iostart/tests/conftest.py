"""Tests run against a test MariaDB of their own (iosuite_shared.testing: a Docker container, or the server named by
IOSUITE_TEST_DB=host:port:user:password): two scratch databases, suite_test and suite_test_shared, dropped and
recreated per session, never a live one. Without a test server the suite is skipped. The app starts once per session;
every test begins with empty tables and a fresh admin, alex."""
import os
import sys

import pytest

from iosuite_shared import apppasswords, testing as _authtest, users

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOSUITE_TEST_DB=host:port:user:password)", allow_module_level=True)
_s = _authtest.server()
os.environ.update(DB_HOST=_s["host"], DB_PORT=str(_s["port"]), DB_USER=_s["user"], DB_PASSWORD=_s["password"], DB_NAME="suite_test")
_authtest.fresh_database("suite_test")
os.environ.update(_authtest.auth_env("suite_test_shared"))
os.environ.setdefault("UPDATE_CHECK", "0")
os.environ.setdefault("SITE_ICONS", "0")  # no fetching of the bookmarked sites' icons (tests/test_site_icons.py turns it on, mocked)
os.environ.setdefault("HA_FEED", "0")  # no websocket thread toward a mocked Home Assistant
os.environ.setdefault("TRMNL_PUSH", "0")  # no thread pushing TRMNL screens (tests/test_trmnl.py calls trmnlpush.push itself)
os.environ.setdefault("LOG_FILE", "")  # no server log from the tests
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402


@pytest.fixture(scope="session")
def app():
    from app.main import app as a
    return a


@pytest.fixture(scope="session")
def _client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client(_client):
    db.reset_all()
    db.migrate()
    from app.auth import auth
    _authtest.clean_shared_tables(auth)
    apppasswords.forget()
    users.invalidate()
    from iosuite_shared import suite
    from app import apps
    for key in apps.ORDER:  # every io app registered (each does so itself when it starts)
        suite.register(key, "io" + key[2:].capitalize(), url=f"https://{key[2:]}.example.com", version="1.0",
                       description=key[2:].capitalize(), color="#123456")
    apps.forget_registry()
    from app import bookmarkcheck, homeassistant, status, widgets
    homeassistant.reload()  # the settings of the test before, the apps it found down, the answers it kept
    widgets.forget()
    status.forget()
    bookmarkcheck.forget()
    _client.cookies.clear()
    r = _client.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
    assert r.status_code == 200, r.text
    return _client


_PROVIDERS = {}


def via_providers(table: dict, asked: list, sent: list = None, cookie: bool = True):
    """A stand-in for widgets.fetch: the suite's standard endpoints (/api/suite/*) answered by each app's own provider
    (its app/suiteitems.py, run here), which reads the app's own API from table {(key, path): reply or
    callable(params)}; a path of the app's own API (quick add) straight from the table. asked: (key, path, params[,
    cookie]) of every request to an app's own API."""
    from pathlib import Path
    from iosuite_shared import suiteitems, testing as _t
    from app import widgets
    root = Path(__file__).resolve().parents[2]

    def fake(request, key, path, params=None, raw=False, body=None, timeout=None):
        def inner(p, prm, raw_):
            asked.append((key, p, dict(prm or {}), request.cookies.get("iothing_session")) if cookie else (key, p, dict(prm or {})))
            r = table.get((key, p))
            if r is None:
                raise suiteitems.Unavailable(502, f"{key} is not reachable")
            return r(prm or {}) if callable(r) else r
        if body is not None and sent is not None:
            sent.append((key, path, body))
        if not path.startswith("/api/suite/"):
            try:
                return inner(path, params, raw)
            except suiteitems.Unavailable as e:
                raise widgets.Unavailable(e.status, str(e))
        if key not in _PROVIDERS:
            if not (root / key / "app" / "suiteitems.py").exists():
                raise widgets.Unavailable(404, f"{key} has no {path}")
            _PROVIDERS[key] = _t.suite_provider(root, key)
        try:
            got = _t.suite_answer(_PROVIDERS[key], path, params, inner, {"headers": [(b"cookie", (request.headers.get("cookie") or "").encode())]})
        except suiteitems.Unavailable as e:
            raise widgets.Unavailable(403 if e.status == 401 else e.status, str(e))
        return got
    return fake


@pytest.fixture()
def apps_answer(monkeypatch):
    """The apps a TRMNL screen reads, stood in for by their own providers over a table: (table, asked, sent). Times are
    New York's (tests/test_trmnl.py, tests/test_trmnl_server.py)."""
    import datetime as dt
    from app import wall, widgets
    table, asked, sent = {}, [], []
    monkeypatch.setattr(widgets, "fetch", via_providers(table, asked, sent))
    wall.forget()
    zone = dt.timezone(dt.timedelta(hours=-5))
    now = dt.datetime.now(dt.timezone.utc).astimezone(zone)
    soon = (now + dt.timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    today = now.date()
    table[("iocalendar", "/api/calendars")] = {"items": [{"id": 1, "color": "#963522"}]}
    table[("iocalendar", "/api/occurrences")] = lambda p: {"items": [
        {"calendarId": 1, "title": "Dinner", "start": soon.isoformat(), "end": (soon + dt.timedelta(hours=2)).isoformat(), "allDay": False,
         "location": "Nan Xiang Dumpling, 38-12 Prince St, Flushing"}] if p["start"][:10] == today.isoformat() else [
        {"calendarId": 1, "title": "Dentist", "start": f"{(today + dt.timedelta(days=1)).isoformat()}T09:30:00-05:00",
         "end": f"{(today + dt.timedelta(days=1)).isoformat()}T10:30:00-05:00", "allDay": False, "location": ""}]}
    table[("iotask", "/api/lists")] = {"items": [{"id": 3, "color": "#2266aa"}]}
    due = [{"id": 41, "title": "Take out the bins", "due": today.isoformat(), "dueAllDay": True, "listId": 3},
           {"id": 42, "title": "Pay the water bill", "due": (today - dt.timedelta(days=2)).isoformat(), "dueAllDay": True, "listId": 3}]
    week = [{"id": 43, "title": "Book flights", "due": (today + dt.timedelta(days=3)).isoformat(), "dueAllDay": True, "listId": 3}]
    table[("iotask", "/api/tasks")] = lambda p: {"items": due if p.get("due") == "today" else [{"id": 42}] if p.get("due") == "overdue"
                                                 else due + week if p.get("due") == "week" else []}
    table[("iocontact", "/api/upcoming")] = {"items": [{"contactId": 5, "fn": "Ava", "label": "birthday", "turns": 9, "inDays": 1, "date": "x"}]}
    table[("iopix", "/api/random")] = {"id": [], "ts": []}
    table[("iodocs", "/api/documents")] = {"items": [
        {"id": 1, "title": "Morgan's passport", "kindLabel": "Passport", "expiresOn": (today - dt.timedelta(days=7)).isoformat(),
         "expiry": {"days": -7, "state": "expired"}, "people": []},
        {"id": 2, "title": "Car registration", "kindLabel": "Registration", "expiresOn": (today + dt.timedelta(days=12)).isoformat(),
         "expiry": {"days": 12, "state": "soon"}, "people": []}]}
    table[("iohealth", "/api/series")] = lambda p: {"points": [{"t": int(dt.datetime.combine(today - dt.timedelta(days=i), dt.time(12)).replace(tzinfo=dt.timezone.utc).timestamp()),
                                                                "v": 1000 * (i + 1)} for i in range(7)]}
    table[("iohealth", "/api/sleep")] = {"items": [{"date": today.isoformat(), "asleep": 431, "inBed": 470}]}
    table[("iohealth", "/api/activity")] = {"items": [{"move": 180, "moveGoal": 500, "exercise": 12, "exerciseGoal": 30, "stand": 3, "standGoal": 12}]}
    table[("iomoney", "/api/bills")] = {"currency": "USD", "items": [{"day": today.isoformat(), "merchant": "Con Edison", "amount": -142.17, "currency": "USD"},
                                                                     {"day": today.isoformat(), "merchant": "Netflix", "amount": -22.99, "currency": "USD", "paid": True}]}
    table[("iomoney", "/api/forecast")] = {"items": []}
    table[("iomoney", "/api/summary")] = {"monarch": {"stale": [{"name": "Checking", "institution": "Chase"}]}}
    return table, asked, sent
