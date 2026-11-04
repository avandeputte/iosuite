"""The Shared ioSuite database settings: IOSUITE_DB_* with `iosuite` defaults, and the IOTHING_AUTH_DB_* of installs
from before 0.4.7 still honoured as they were."""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROBE = ("import json, os; from app import config; "
         "print(json.dumps({k: os.environ['IOTHING_AUTH_DB_' + k] for k in ('HOST', 'PORT', 'NAME', 'USER', 'PASSWORD')}))")


def _suite(**env):
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("IOTHING_AUTH_DB_", "IOSUITE_DB_", "DB_"))}
    clean.update(env, IOCONTACTS_ENV="/nonexistent")
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=clean, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_new_install_defaults_to_iosuite_on_the_contacts_server():
    assert _suite(DB_HOST="db.lan", DB_PORT="3307") == {
        "HOST": "db.lan", "PORT": "3307", "NAME": "iosuite", "USER": "iosuite", "PASSWORD": "iosuite"}


def test_iosuite_settings_are_passed_to_the_library():
    s = _suite(IOSUITE_DB_HOST="h", IOSUITE_DB_NAME="n", IOSUITE_DB_USER="u", IOSUITE_DB_PASSWORD="p")
    assert (s["HOST"], s["NAME"], s["USER"], s["PASSWORD"]) == ("h", "n", "u", "p")


def test_an_older_install_keeps_its_auth_database():
    s = _suite(IOTHING_AUTH_DB_HOST="192.168.1.89", IOTHING_AUTH_DB_USER="contacts", IOTHING_AUTH_DB_PASSWORD="x")
    assert s == {"HOST": "192.168.1.89", "PORT": "3306", "NAME": "auth", "USER": "contacts", "PASSWORD": "x"}
