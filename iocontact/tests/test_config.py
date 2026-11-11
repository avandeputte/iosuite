"""The conventions every app of the suite follows (iosuite_shared.testing): the port, one version, config.env, and an
access marker on every API route. And the Shared ioSuite database settings: IOSUITE_DB_* with `iosuite` defaults, on the
contacts' server unless set."""
import json
import os
import subprocess
import sys

from iosuite_shared import testing

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = ("import json; from app import config; from iosuite_shared import config as sc; "
         "print(json.dumps({'HOST': sc.DB_HOST, 'PORT': str(sc.DB_PORT), 'NAME': sc.DB_NAME, 'USER': sc.DB_USER, 'PASSWORD': sc.DB_PASSWORD}))")


def _suite(**env):
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("IOTHING_AUTH_DB_", "IOSUITE_DB_", "DB_"))}
    clean.update(env)
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=clean, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_new_install_defaults_to_iosuite_on_the_contacts_server():
    assert _suite(DB_HOST="db.lan", DB_PORT="3307") == {
        "HOST": "db.lan", "PORT": "3307", "NAME": "iosuite", "USER": "iosuite", "PASSWORD": ""}


def test_iosuite_settings_are_passed_to_the_library():
    s = _suite(IOSUITE_DB_HOST="h", IOSUITE_DB_NAME="n", IOSUITE_DB_USER="u", IOSUITE_DB_PASSWORD="p")
    assert (s["HOST"], s["NAME"], s["USER"], s["PASSWORD"]) == ("h", "n", "u", "p")


def test_the_old_names_are_not_read():
    s = _suite(IOTHING_AUTH_DB_HOST="192.168.1.89", IOTHING_AUTH_DB_NAME="auth", IOTHING_AUTH_DB_USER="auth")
    assert (s["HOST"], s["NAME"], s["USER"]) == ("127.0.0.1", "iosuite", "iosuite")


def test_suite_conventions():
    from app import __version__, config
    testing.check_conventions(ROOT, "iocontact", __version__, config)


def test_every_api_route_declares_who_may_call_it(app):
    from app import access
    testing.check_access_declared(app, access.declared)


def test_standard_paths():
    from pathlib import Path
    from app import config
    root = Path(ROOT)
    assert config.APP_DIR == root and config.STATIC_DIR == root / "static" and config.DATA_DIR == root / "data"
    assert config.LOG_FILE is None  # LOG_FILE= in the tests' environment
