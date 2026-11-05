"""Tests run against a test MariaDB of their own (iosuite_shared.testing: a Docker container, or the server named by
IOTHING_TEST_DB=host:port:user:password): two scratch databases, calendar_test and calendar_test_auth, dropped and
recreated per session, never a live one. Without a test server the suite is skipped."""
import os
import sys

import pytest  # noqa: E402

from iosuite_shared import testing as _authtest  # noqa: E402

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOTHING_TEST_DB=host:port:user:password)", allow_module_level=True)
_s = _authtest.server()
os.environ.update(DB_HOST=_s["host"], DB_PORT=str(_s["port"]), DB_USER=_s["user"], DB_PASSWORD=_s["password"], DB_NAME="calendar_test")
_authtest.fresh_database("calendar_test")
os.environ.update(_authtest.auth_env("calendar_test_auth"))
os.environ.setdefault("TIMEZONE", "America/New_York")
os.environ.setdefault("UPDATE_CHECK", "0")
os.environ.setdefault("HOLIDAYS_COUNTRY", "off")  # the tests that want holidays choose a country
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, users  # noqa: E402


@pytest.fixture()
def client():
    db.reset_all()
    from iosuite_shared import db as authdb
    users.ensure_admin_from_env()  # the auth tables
    for t in ("user_roles", "user_data", "app_passwords", "sessions", "users", "settings", "suite_apps"):
        try:
            authdb.ex(f"DELETE FROM {t}")
        except Exception:  # noqa: BLE001 - a table this version does not have
            pass
    authdb.ex("ALTER TABLE users AUTO_INCREMENT = 1")
    from app.auth import auth as _auth
    _auth._registered = False  # suite_apps was emptied: register again on the next request
    users.forget_cached_auth()
    from app import model
    model._cache_clear()
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture()
def family_id(client):
    return next(c["id"] for c in client.get("/api/calendars").json()["items"] if c["shared"] and c["kind"] == "events")
