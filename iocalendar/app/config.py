"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. Everything stored
lives in MariaDB."""
import os
from pathlib import Path

from iosuite_shared import config as shared

ROOT = Path(__file__).resolve().parent.parent
shared.load_file(ROOT)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int


DB_HOST = env("DB_HOST", "127.0.0.1")
DB_PORT = env_int("DB_PORT", 3306)
DB_NAME = env("DB_NAME", "calendar")
DB_USER = env("DB_USER", "calendar")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "calendar")

STATIC_DIR = ROOT / "static"
# the address people and the other apps reach ioCalendar at, e.g. https://calendar.example.com (links in feeds,
# Settings, MCP); empty: the address it is reached at
PUBLIC_URL = env("PUBLIC_URL").rstrip("/")

# where the server listens (python -m app); every app of the suite has its own default port (iosuite_shared.suite.PORTS)
HOST = env("HOST", "0.0.0.0")
PORT = env_int("PORT", 8620)
# the addresses that may tell the server the visitor's address and scheme (X-Forwarded-For / -Proto): * (any), or a
# comma-separated list such as the reverse proxy's
FORWARDED_ALLOW_IPS = env("FORWARDED_ALLOW_IPS", "*")
# HTTPS served directly instead of behind a reverse proxy: both files
TLS_CERT_FILE = env("TLS_CERT_FILE")
TLS_KEY_FILE = env("TLS_KEY_FILE")

# the time zone new events and all-day feeds default to (the server's own when empty)
TZ = env("TZ")

# public holidays (Settings › Holidays wins once an admin has chosen): a two-letter country code (off: none), and
# optionally its region (a state or province code) and the language of the names; no country: the time zone's
HOLIDAYS_COUNTRY = env("HOLIDAYS_COUNTRY").strip()
HOLIDAYS_REGION = env("HOLIDAYS_REGION").strip().upper()
HOLIDAYS_LANGUAGE = env("HOLIDAYS_LANGUAGE").strip()

# ioContacts (can also be set in Settings › ioContacts; the environment wins)
IOCONTACTS_URL = env("IOCONTACTS_URL")
IOCONTACTS_USER = env("IOCONTACTS_USER")
IOCONTACTS_PASSWORD = env("IOCONTACTS_PASSWORD")
IOCONTACTS_CF_CLIENT_ID = env("IOCONTACTS_CF_CLIENT_ID")
IOCONTACTS_CF_CLIENT_SECRET = env("IOCONTACTS_CF_CLIENT_SECRET")

MAX_EVENT_BYTES = 2 * 1024 * 1024     # one calendar object (CalDAV PUT, REST)
MAX_IMPORT_BYTES = 32 * 1024 * 1024   # an .ics file to import

# the server log, for Maintenance › Updates and logs (LOG_FILE= with nothing after it: none). Updates: IOCALENDAR_REPO,
# IOCALENDAR_BRANCH and UPDATE_CHECK are read by iosuite_shared.updates (app.auth.updater)
LOG_FILE = Path(os.environ.get("LOG_FILE", str(ROOT / "iocalendar.log"))) if os.environ.get("LOG_FILE", "x") else None

# the MCP server at /mcp: off until an admin turns it on in Settings, or MCP=1 here
MCP_FORCED = env_flag("MCP")
# `python -m app.mcp` (stdio) acts as this account
MCP_USER = env("MCP_USER")
