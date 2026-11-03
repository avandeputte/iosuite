"""Test set-up: a scratch DATA_DIR and a scratch database, emptied before every test.

SQLite by default. With IONOTES_TEST_DB=mysql the same tests run on MySQL/MariaDB, on the database named by
IONOTES_TEST_DB_HOST / _PORT / _NAME / _USER / _PASSWORD (default 127.0.0.1:3306, notes_test, notes/notes);
CI runs both."""
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp(prefix="ionotes-test-")
os.environ["DATA_DIR"] = _tmp
os.environ.pop("ADMIN_USER", None)
os.environ.pop("ADMIN_PASSWORD", None)
os.environ["UPDATE_CHECK"] = "0"
if os.environ.get("IONOTES_TEST_DB") == "mysql":
    os.environ.update(DB_TYPE="mysql", DB_HOST=os.environ.get("IONOTES_TEST_DB_HOST", "127.0.0.1"),
                      DB_PORT=os.environ.get("IONOTES_TEST_DB_PORT", "3306"), DB_DATABASE=os.environ.get("IONOTES_TEST_DB_NAME", "notes_test"),
                      DB_USER=os.environ.get("IONOTES_TEST_DB_USER", "notes"), DB_PASSWORD=os.environ.get("IONOTES_TEST_DB_PASSWORD", "notes"))
else:
    os.environ["DB_TYPE"] = "sqlite"
# the shared accounts (iothing-auth) in a database of their own on the auth server, never the suite's `auth`
os.environ["IOTHING_AUTH_DB_NAME"] = os.environ.get("IOTHING_TEST_AUTH_DB", "auth_test_ionotes")

from app import db, users, proxyauth  # noqa: E402

TABLES = ["notes", "note_images", "folders", "tag_colors", "change_log", "change_counter", "app_settings"]


@pytest.fixture(scope="session")
def app():
    from app.main import app as a
    return a


@pytest.fixture(autouse=True)
def clean():
    db.init()
    with db.connect() as con:
        for t in TABLES:
            con.execute(f"DELETE FROM {t}")
        con.commit()
    from iothing_auth import db as authdb
    users.init()
    authdb.ex("DELETE FROM users")
    authdb.ex("ALTER TABLE users AUTO_INCREMENT = 1")  # the tests count on the first account being #1
    authdb.ex("DELETE FROM settings")
    users.invalidate()
    users._attempts.clear()
    proxyauth.forget_identities()
    from app import notes
    notes._claimed = False  # each test starts before any account claimed the open install's notes
    yield


@pytest.fixture(scope="session")
def _client(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as c:  # once: the MCP session manager starts only once per process
        yield c


@pytest.fixture
def client(_client):
    _client.cookies.clear()
    return _client


@pytest.fixture
def admin(client):
    """A signed-in admin (the client carries the session cookie)."""
    r = client.post("/api/auth/setup", json={"name": "alex", "password": "secretpw1"})
    assert r.status_code == 200, r.text
    return r.json()["user"]
