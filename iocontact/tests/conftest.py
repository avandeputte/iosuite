"""Tests run against a scratch MariaDB database (TEST_DB_NAME, default contacts_test), dropped and recreated per test.
Set DB_HOST / DB_PORT / DB_USER / DB_PASSWORD for the server; the account needs rights on that database."""
import os
import sys

os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "contacts_test")
# the shared accounts (iothing-auth) in a database of their own, never the suite's `auth`
os.environ["IOTHING_AUTH_DB_NAME"] = os.environ.get("IOTHING_TEST_AUTH_DB", "auth_test_iocontacts")
os.environ.setdefault("LDAP_PORT", "0")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, users  # noqa: E402


@pytest.fixture()
def client():
    db.reset_all()
    from iothing_auth import db as authdb
    users.ensure_admin_from_env()  # the auth tables
    authdb.ex("DELETE FROM users")
    authdb.ex("ALTER TABLE users AUTO_INCREMENT = 1")
    authdb.ex("DELETE FROM settings")
    users.forget_cached_auth()
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
        assert r.status_code == 200
        yield c


@pytest.fixture()
def family_id(client):
    return next(b["id"] for b in client.get("/api/books").json()["items"] if b["shared"])
