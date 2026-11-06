"""Test set-up: a scratch DATA_DIR and a scratch database, emptied before every test; the Shared ioSuite database on a
test MariaDB of their own (iosuite_shared.testing: Docker, or IOSUITE_TEST_DB).

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
os.environ["LOG_FILE"] = ""  # no server log from the tests
if os.environ.get("IONOTES_TEST_DB") == "mysql":
    os.environ.update(DB_TYPE="mysql", DB_HOST=os.environ.get("IONOTES_TEST_DB_HOST", "127.0.0.1"),
                      DB_PORT=os.environ.get("IONOTES_TEST_DB_PORT", "3306"), DB_NAME=os.environ.get("IONOTES_TEST_DB_NAME", "notes_test"),
                      DB_USER=os.environ.get("IONOTES_TEST_DB_USER", "notes"), DB_PASSWORD=os.environ.get("IONOTES_TEST_DB_PASSWORD", "notes"))
else:
    os.environ["DB_TYPE"] = "sqlite"
# the shared accounts (iosuite-shared): a fresh database on the test MariaDB (a Docker container, or
# IOSUITE_TEST_DB=host:port:user:password), never the suite's live `iosuite`
from iosuite_shared import testing as _authtest  # noqa: E402

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the shared accounts need a MariaDB (Docker, or IOSUITE_TEST_DB=host:port:user:password)", allow_module_level=True)
os.environ.update(_authtest.auth_env("ionotes_test_auth"))  # IOSUITE_DB_*: the test database, never one named in the shell

from app import db  # noqa: E402
from iosuite_shared import proxyauth  # noqa: E402

TABLES = ["nts_notes", "nts_note_images", "nts_folders", "nts_tag_colors", "nts_change_log", "nts_change_counter", "nts_settings"]


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
    from app.auth import auth
    _authtest.clean_shared_tables(auth)  # accounts, sessions, app passwords, settings, the list of apps; the first account is #1 again
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
