"""Tests run against a test MariaDB of their own (iosuite_shared.testing: a Docker container, or the server named by
IOSUITE_TEST_DB=host:port:user:password): two scratch databases, dns_test and dns_test_auth, dropped and recreated per
session, never a live one. Without a test server the database tests are skipped (the comparison and the providers'
parsing are tested without one). Every database test begins with empty tables and a fresh admin, alex."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("UPDATE_CHECK", "0")
os.environ.setdefault("LOG_FILE", "")  # no server log from the tests
os.environ.setdefault("BACKGROUND", "0")  # no background checks or dynamic DNS during the tests

from iosuite_shared import testing as _authtest  # noqa: E402

_s = _authtest.server()
if _s is not None:
    os.environ.update(DB_HOST=_s["host"], DB_PORT=str(_s["port"]), DB_USER=_s["user"], DB_PASSWORD=_s["password"], DB_NAME="dns_test")
    _authtest.fresh_database("dns_test")
    os.environ.update(_authtest.auth_env("dns_test_auth"))
else:
    os.environ.setdefault("DB_PASSWORD", "unused")

from tests import fake  # noqa: E402,F401  (the in-memory DNS server registers itself)


def need_db():
    if _s is None:
        pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOSUITE_TEST_DB=host:port:user:password)")


@pytest.fixture(scope="session")
def app():
    from app.main import app as a
    return a


@pytest.fixture(scope="session")
def _client(app):
    need_db()
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client(_client):
    from app import db
    from iosuite_shared import apppasswords, users as shared_users
    from app.auth import auth
    db.reset_all()
    db.migrate()
    _authtest.clean_shared_tables(auth)
    apppasswords.forget()
    shared_users.invalidate()
    fake.SERVERS.clear()
    fake.DOWN.clear()
    _client.cookies.clear()
    r = _client.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
    assert r.status_code == 200, r.text
    return _client
