"""Tests run against a test MariaDB of their own (iosuite_shared.testing: a Docker container, or the server named by
IOTHING_TEST_DB=host:port:user:password): two scratch databases, contacts_test and contacts_test_iosuite, dropped and
recreated per session, never a live one. Without a test server the suite is skipped."""
import os
import sys

import pytest  # noqa: E402

from iosuite_shared import testing as _authtest  # noqa: E402

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOTHING_TEST_DB=host:port:user:password)", allow_module_level=True)
_s = _authtest.server()
os.environ.update(DB_HOST=_s["host"], DB_PORT=str(_s["port"]), DB_USER=_s["user"], DB_PASSWORD=_s["password"], DB_NAME="contacts_test")
_authtest.fresh_database("contacts_test")
os.environ.update(_authtest.auth_env("contacts_test_iosuite"))
os.environ.setdefault("LDAP_PORT", "0")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, users  # noqa: E402


@pytest.fixture()
def client():
    db.reset_all()
    from iosuite_shared import db as authdb
    users.ensure_admin_from_env()  # the auth tables
    authdb.ex("DELETE FROM users")
    authdb.ex("ALTER TABLE users AUTO_INCREMENT = 1")
    authdb.ex("DELETE FROM settings")
    authdb.ex("DELETE FROM suite_apps")  # the suite's list of apps: registered again on the first request
    from iosuite_shared import suite
    from app.auth import auth
    suite.invalidate()
    auth._registered = False
    users.forget_cached_auth()
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
        assert r.status_code == 200
        yield c


@pytest.fixture()
def family_id(client):
    return next(b["id"] for b in client.get("/api/books").json()["items"] if b["shared"])
