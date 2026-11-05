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
# (the iosuite-shared library) and the settings shared by every ioThing app. IOSUITE_DB_* set it; by default it is on the
# same server as the contacts. The library reads IOSUITE_DB_* when it is imported, so the defaults are filled in here,
# before any app module uses it.
os.environ.setdefault("IOSUITE_DB_HOST", DB_HOST)
os.environ.setdefault("IOSUITE_DB_PORT", str(DB_PORT))
SUITE_DB_HOST = os.environ["IOSUITE_DB_HOST"]
SUITE_DB_PORT = int(os.environ["IOSUITE_DB_PORT"])
SUITE_DB_NAME = env("IOSUITE_DB_NAME", "iosuite")
SUITE_DB_USER = env("IOSUITE_DB_USER", "iosuite")

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
# UPDATE_CHECK are read by iosuite_shared.updates (app.auth.updater)
LOG_FILE = Path(env("LOG_FILE", str(ROOT / "iocontacts.log"))) if env("LOG_FILE", "x") else None

# the MCP server at /mcp: off until an admin turns it on in Settings, or MCP=1 here
MCP_FORCED = env("MCP", "").strip().lower() in ("1", "on", "true", "yes")
# `python -m app.mcp` (stdio) acts as this account
MCP_USER = env("IOCONTACTS_MCP_USER")
