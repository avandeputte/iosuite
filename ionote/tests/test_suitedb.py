"""The Shared ioSuite database's settings: the new names, the old ones, the defaults and an install on the old defaults."""
import os

import pytest

from app import suitedb

KEYS = suitedb.KEYS


@pytest.fixture
def env(monkeypatch):
    saved = {p + k: os.environ.get(p + k) for p in (suitedb.NEW, suitedb.OLD) for k in KEYS}
    for v in saved:
        monkeypatch.delenv(v, raising=False)
    import iothing_auth.config as cfg
    before = (cfg.DB_HOST, cfg.DB_PORT, cfg.DB_NAME, cfg.DB_USER, cfg.DB_PASSWORD)
    yield monkeypatch
    for k, v in saved.items():  # back to the test database for the other tests
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    cfg.DB_HOST, cfg.DB_PORT, cfg.DB_NAME, cfg.DB_USER, cfg.DB_PASSWORD = before
    suitedb.note = ""


def test_defaults_are_iosuite(env):
    env.setattr(suitedb, "_reaches", lambda s: None)
    suitedb.apply()
    assert [os.environ[suitedb.OLD + k] for k in KEYS] == ["127.0.0.1", "3306", "iosuite", "iosuite", "iosuite"]
    import iothing_auth.config as cfg
    assert (cfg.DB_NAME, cfg.DB_USER) == ("iosuite", "iosuite")
    assert suitedb.public()["fromEnv"] == []


def test_old_names_still_work_and_new_ones_win(env):
    env.setenv("IOTHING_AUTH_DB_HOST", "10.0.0.5")
    env.setenv("IOTHING_AUTH_DB_NAME", "auth")
    env.setenv("IOTHING_AUTH_DB_USER", "auth")
    env.setenv("IOTHING_AUTH_DB_PASSWORD", "pw")
    env.setenv("IOSUITE_DB_USER", "suiteuser")
    env.setattr(suitedb, "_reaches", lambda s: pytest.fail("no probe when everything is named"))
    suitedb.apply()
    assert os.environ["IOTHING_AUTH_DB_HOST"] == "10.0.0.5" and os.environ["IOTHING_AUTH_DB_NAME"] == "auth"
    assert os.environ["IOTHING_AUTH_DB_USER"] == "suiteuser"
    p = suitedb.public()
    assert p["database"] == "auth" and "IOSUITE_DB_USER" in p["fromEnv"] and "IOTHING_AUTH_DB_NAME" in p["fromEnv"]
    assert "password" not in p


def test_an_install_on_the_old_defaults_keeps_auth(env):
    env.setenv("IOSUITE_DB_HOST", "10.0.0.5")
    env.setattr(suitedb, "_reaches", lambda s: None if s["NAME"] == "auth" and s["USER"] == "auth" else 1045)
    suitedb.apply()
    assert (os.environ["IOTHING_AUTH_DB_NAME"], os.environ["IOTHING_AUTH_DB_USER"], os.environ["IOTHING_AUTH_DB_HOST"]) == ("auth", "auth", "10.0.0.5")
    assert "old default" in suitedb.note


def test_unreachable_server_keeps_iosuite(env):
    env.setattr(suitedb, "_reaches", lambda s: 0)
    suitedb.apply()
    assert os.environ["IOTHING_AUTH_DB_NAME"] == "iosuite" and suitedb.note == ""
