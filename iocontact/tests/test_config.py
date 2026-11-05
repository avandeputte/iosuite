"""The Shared ioSuite database settings: IOSUITE_DB_* with `iosuite` defaults, on the contacts' server unless set."""
import json
import os
import subprocess
import sys

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
        "HOST": "db.lan", "PORT": "3307", "NAME": "iosuite", "USER": "iosuite", "PASSWORD": "iosuite"}


def test_iosuite_settings_are_passed_to_the_library():
    s = _suite(IOSUITE_DB_HOST="h", IOSUITE_DB_NAME="n", IOSUITE_DB_USER="u", IOSUITE_DB_PASSWORD="p")
    assert (s["HOST"], s["NAME"], s["USER"], s["PASSWORD"]) == ("h", "n", "u", "p")


def test_the_old_names_are_not_read():
    s = _suite(IOTHING_AUTH_DB_HOST="192.168.1.89", IOTHING_AUTH_DB_NAME="auth", IOTHING_AUTH_DB_USER="auth")
    assert (s["HOST"], s["NAME"], s["USER"]) == ("127.0.0.1", "iosuite", "iosuite")


def test_default_port_is_the_suites():
    from pathlib import Path
    from iosuite_shared import suite
    from app import config
    assert config.PORT == suite.PORTS["iocontacts"] == 8640
    for f in ("Dockerfile", "docker-compose.yml", "config.env.example", "run.sh", "setup.sh"):
        assert "8640" in (Path(ROOT) / f).read_text(), f


def test_one_version_and_settings_file():
    from pathlib import Path
    from app import __version__
    root = Path(ROOT)
    assert f'version = "{__version__}"' in (root / "pyproject.toml").read_text()
    assert "config.env" in (root / ".gitignore").read_text().split()
    for f in ("setup.sh", "update.sh", "README.md"):
        assert "iocontacts.env" not in (root / f).read_text(), f
