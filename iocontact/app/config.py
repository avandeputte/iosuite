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

# updates: the GitHub repository and branch followed by the version check and update.sh
REPO = env("IOCONTACTS_REPO", "avandeputte/iocontacts")
BRANCH = env("IOCONTACTS_BRANCH", "main")
# UPDATE_CHECK=0 turns the daily "is there a newer version" check off for good (the setting cannot turn it back on)
UPDATE_CHECK_LOCKED = env("UPDATE_CHECK", "").strip().lower() in ("0", "off", "false", "no")

# the MCP server at /mcp: off until an admin turns it on in Settings, or MCP=1 here
MCP_FORCED = env("MCP", "").strip().lower() in ("1", "on", "true", "yes")
# `python -m app.mcp` (stdio) acts as this account
MCP_USER = env("IOCONTACTS_MCP_USER")
