"""Settings from the environment (or iocontacts.env next to the app). Everything stored lives in MariaDB."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file():
    p = Path(os.environ.get("IOCONTACTS_ENV", ROOT / "iocontacts.env"))
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env_file()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


DB_HOST = env("DB_HOST", "127.0.0.1")
DB_PORT = int(env("DB_PORT", "3306"))
DB_NAME = env("DB_NAME", "contacts")
DB_USER = env("DB_USER", "contacts")
DB_PASSWORD = env("DB_PASSWORD", "contacts")

# The Shared ioSuite database (MariaDB, `iosuite`): the suite's accounts, passwords, sessions, app passwords and roles
# (the iothing-auth library) and the settings shared by every ioThing app. IOSUITE_DB_* set it; by default it is on the
# same server as the contacts. Installs from before 0.4.7 set IOTHING_AUTH_DB_* (the library's own names, database and
# user `auth`): those still work and keep their old defaults, so an update changes nothing for them.
_LEGACY_SUITE = any(k.startswith("IOTHING_AUTH_DB_") for k in os.environ)
_SUITE_DEFAULTS = ({"HOST": "127.0.0.1", "PORT": "3306", "NAME": "auth", "USER": "auth", "PASSWORD": "auth"} if _LEGACY_SUITE
                   else {"HOST": DB_HOST, "PORT": str(DB_PORT), "NAME": "iosuite", "USER": "iosuite", "PASSWORD": "iosuite"})
for _k, _d in _SUITE_DEFAULTS.items():
    # the library reads IOTHING_AUTH_DB_* when it is imported, so they are filled in here, before any app module uses it
    os.environ["IOTHING_AUTH_DB_" + _k] = env("IOSUITE_DB_" + _k, env("IOTHING_AUTH_DB_" + _k, _d))
SUITE_DB_HOST = os.environ["IOTHING_AUTH_DB_HOST"]
SUITE_DB_PORT = int(os.environ["IOTHING_AUTH_DB_PORT"])
SUITE_DB_NAME = os.environ["IOTHING_AUTH_DB_NAME"]
SUITE_DB_USER = os.environ["IOTHING_AUTH_DB_USER"]

STATIC_DIR = ROOT / "static"
PUBLIC_URL = env("PUBLIC_URL", "").rstrip("/")   # e.g. https://contacts.example.com (links in feeds and LDAP)

ADMIN_USER = env("ADMIN_USER")
ADMIN_PASSWORD = env("ADMIN_PASSWORD")

# LDAP directory (read-only): port 0 turns it off
LDAP_PORT = int(env("LDAP_PORT", "3890"))
LDAP_HOST = env("LDAP_HOST", "0.0.0.0")
LDAP_BASE = env("LDAP_BASE", "dc=iocontacts")

# sign-in at a reverse proxy, as in iopix
AUTH_PROXY = env("AUTH_PROXY", "off").lower()
AUTH_PROXY_HEADER = env("AUTH_PROXY_HEADER", "")
AUTH_PROXY_TRUSTED = env("AUTH_PROXY_TRUSTED", "127.0.0.1,::1")
CF_ACCESS_TEAM = env("CF_ACCESS_TEAM")
CF_ACCESS_AUD = env("CF_ACCESS_AUD")

# ioPix (can also be set in Settings; the environment wins)
IOPIX_URL = env("IOPIX_URL")
IOPIX_USER = env("IOPIX_USER")
IOPIX_PASSWORD = env("IOPIX_PASSWORD")
IOPIX_CF_CLIENT_ID = env("IOPIX_CF_CLIENT_ID")
IOPIX_CF_CLIENT_SECRET = env("IOPIX_CF_CLIENT_SECRET")

MAX_PHOTO_BYTES = 2 * 1024 * 1024

# the server log, for Maintenance › Updates and logs (empty: none). Updates: IOCONTACTS_REPO, IOCONTACTS_BRANCH and
# UPDATE_CHECK are read by iothing_auth.updates (app.auth.updater)
LOG_FILE = Path(env("LOG_FILE", str(ROOT / "iocontacts.log"))) if env("LOG_FILE", "x") else None

# the MCP server at /mcp: off until an admin turns it on in Settings, or MCP=1 here
MCP_FORCED = env("MCP", "").strip().lower() in ("1", "on", "true", "yes")
# `python -m app.mcp` (stdio) acts as this account
MCP_USER = env("IOCONTACTS_MCP_USER")
