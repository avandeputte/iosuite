"""Tests run against a test MariaDB of their own (iosuite_shared.testing: a Docker container, or the server named by
IOSUITE_TEST_DB=host:port:user:password): two scratch databases, suite_test and suite_test_shared, dropped and
recreated per session, never a live one. Without a test server the suite is skipped. The app starts once per session;
every test begins with empty tables and a fresh admin, alex."""
import os
import sys

import pytest

from iosuite_shared import testing as _authtest

if _authtest.server() is None:
    pytest.skip(f"{_authtest.server.reason}: the tests need a MariaDB (Docker, or IOSUITE_TEST_DB=host:port:user:password)", allow_module_level=True)
_s = _authtest.server()
os.environ.update(DB_HOST=_s["host"], DB_PORT=str(_s["port"]), DB_USER=_s["user"], DB_PASSWORD=_s["password"], DB_NAME="suite_test")
_authtest.fresh_database("suite_test")
os.environ.update(_authtest.auth_env("suite_test_shared"))
os.environ.setdefault("UPDATE_CHECK", "0")
os.environ.setdefault("HA_FEED", "0")  # no websocket thread toward a mocked Home Assistant
os.environ.setdefault("LOG_FILE", "")  # no server log from the tests
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, users  # noqa: E402


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
    users.forget_cached_auth()
    from iosuite_shared import suite
    from app import apps
    for key in apps.ORDER:  # every io app registered (each does so itself when it starts)
        suite.register(key, "io" + key[2:].capitalize(), url=f"https://{key[2:]}.example.com", version="1.0",
                       description=key[2:].capitalize(), color="#123456")
    apps.forget_registry()
    from app import homeassistant, status, widgets
    homeassistant.reload()  # the settings of the test before, the apps it found down, the answers it kept
    widgets.forget()
    status.forget()
    _client.cookies.clear()
    r = _client.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
    assert r.status_code == 200, r.text
    return _client
