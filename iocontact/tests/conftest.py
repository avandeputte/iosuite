"""Tests run against a scratch MariaDB database (TEST_DB_NAME, default contacts_test), dropped and recreated per test.
Set DB_HOST / DB_PORT / DB_USER / DB_PASSWORD for the server; the account needs rights on that database."""
import os
import sys

os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "contacts_test")
os.environ.setdefault("LDAP_PORT", "0")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import db, users  # noqa: E402


@pytest.fixture()
def client():
    db.reset_all()
    users._secret_cache = None
    users.forget_cached_auth()
    from app.main import app
    with TestClient(app) as c:
        r = c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
        assert r.status_code == 200
        yield c


@pytest.fixture()
def family_id(client):
    return next(b["id"] for b in client.get("/api/books").json()["items"] if b["shared"])
