"""Settings from the environment (or iocalendar.env next to the app). Everything stored lives in MariaDB."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file():
    p = Path(os.environ.get("IOCALENDAR_ENV", ROOT / "iocalendar.env"))
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
DB_NAME = env("DB_NAME", "calendar")
DB_USER = env("DB_USER", "calendar")
DB_PASSWORD = env("DB_PASSWORD", "calendar")

STATIC_DIR = ROOT / "static"
PUBLIC_URL = env("PUBLIC_URL", "").rstrip("/")   # e.g. https://calendar.example.com (links in feeds, Settings, MCP)

# the time zone new events and all-day feeds default to (the server's own when empty)
TIMEZONE = env("TIMEZONE", env("TZ", "")).strip()

# ioContacts (can also be set in Settings › ioContacts; the environment wins)
IOCONTACTS_URL = env("IOCONTACTS_URL")
IOCONTACTS_USER = env("IOCONTACTS_USER")
IOCONTACTS_PASSWORD = env("IOCONTACTS_PASSWORD")
IOCONTACTS_CF_CLIENT_ID = env("IOCONTACTS_CF_CLIENT_ID")
IOCONTACTS_CF_CLIENT_SECRET = env("IOCONTACTS_CF_CLIENT_SECRET")

MAX_EVENT_BYTES = 2 * 1024 * 1024     # one calendar object (CalDAV PUT, REST)
MAX_IMPORT_BYTES = 32 * 1024 * 1024   # an .ics file to import

# updates: the GitHub repository and branch followed by the version check and update.sh
REPO = env("IOCALENDAR_REPO", "avandeputte/iocalendar")
BRANCH = env("IOCALENDAR_BRANCH", "main")
# UPDATE_CHECK=0 turns the daily "is there a newer version" check off for good (the setting cannot turn it back on)
UPDATE_CHECK_LOCKED = env("UPDATE_CHECK", "").strip().lower() in ("0", "off", "false", "no")

# the MCP server at /mcp: off until an admin turns it on in Settings, or MCP=1 here
MCP_FORCED = env("MCP", "").strip().lower() in ("1", "on", "true", "yes")
# `python -m app.mcp` (stdio) acts as this account
MCP_USER = env("IOCALENDAR_MCP_USER")
