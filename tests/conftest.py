"""Tests run against a test MariaDB of their own (iothing_auth.testing: a Docker container, or the server named by
IOTHING_TEST_DB=host:port:user:password): two scratch databases, suite_test and suite_test_auth, dropped and
recreated per session, never a live one. Without a test server the suite is skipped."""
import os
import sys

import pytest  # noqa: E402

from iothing_auth import testing as _authtest  # noqa: E402

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOTHING_TEST_DB=host:port:user:password)", allow_module_level=True)
_s = _authtest.server()
os.environ.update(DB_HOST=_s["host"], DB_PORT=str(_s["port"]), DB_USER=_s["user"], DB_PASSWORD=_s["password"], DB_NAME="suite_test")
_authtest.fresh_database("suite_test")
os.environ.update(_authtest.auth_env("suite_test_auth"))
os.environ.setdefault("UPDATE_CHECK", "0")
for k in ("IOPIX_URL", "IOHEALTH_URL", "IOCALENDAR_URL", "IOCONTACTS_URL", "IONOTES_URL"):
    os.environ.pop(k, None)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, users  # noqa: E402


@pytest.fixture()
def client():
    db.reset_all()
    from iothing_auth import db as authdb
    users.ensure_admin_from_env()  # the auth tables
    for t in ("user_roles", "user_data", "app_passwords", "sessions", "users", "settings", "suite_apps"):
        try:
            authdb.ex(f"DELETE FROM {t}")
        except Exception:  # noqa: BLE001 - a table this version does not have
            pass
    authdb.ex("ALTER TABLE users AUTO_INCREMENT = 1")
    users.forget_cached_auth()
    from iothing_auth import suite
    from app import apps
    suite.invalidate()
    apps.forget_registry()
    from app.auth import auth
    auth._registered = False  # the row was just deleted: registered again at the next request
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
        assert r.status_code == 200, r.text
        yield c
