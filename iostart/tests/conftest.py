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
