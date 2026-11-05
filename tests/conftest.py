"""Tests run against a test MariaDB of their own (iosuite_shared.testing: a Docker container, or the server named by
IOSUITE_TEST_DB=host:port:user:password): two scratch databases, suite_test and suite_test_shared, dropped and
recreated per session, never a live one. Without a test server the suite is skipped."""
import os
import sys

import pytest  # noqa: E402

from iosuite_shared import testing as _authtest  # noqa: E402

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOSUITE_TEST_DB=host:port:user:password)", allow_module_level=True)
_s = _authtest.server()
os.environ.update(DB_HOST=_s["host"], DB_PORT=str(_s["port"]), DB_USER=_s["user"], DB_PASSWORD=_s["password"], DB_NAME="suite_test")
_authtest.fresh_database("suite_test")
os.environ.update(_authtest.auth_env("suite_test_shared"))
os.environ.setdefault("UPDATE_CHECK", "0")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, users  # noqa: E402


@pytest.fixture()
def client():
    db.reset_all()
    from iosuite_shared import db as authdb
    users.ensure_admin_from_env()  # the auth tables
    for t in ("ios_user_roles", "ios_user_data", "ios_app_passwords", "ios_sessions", "ios_users", "ios_settings", "ios_apps"):
        try:
            authdb.ex(f"DELETE FROM {t}")
        except Exception:  # noqa: BLE001 - a table this version does not have
            pass
    authdb.ex("ALTER TABLE ios_users AUTO_INCREMENT = 1")
    users.forget_cached_auth()
    from iosuite_shared import suite
    from app import apps
    suite.invalidate()
    for key in apps.ORDER:  # every io app registered (each does so itself when it starts)
        suite.register(key, "io" + key[2:].capitalize(), url=f"https://{key[2:]}.example.com", version="1.0",
                       description=key[2:].capitalize(), color="#123456")
    apps.forget_registry()
    from app.auth import auth
    auth._registered = False  # the row was just deleted: registered again at the next request
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
        assert r.status_code == 200, r.text
        yield c
