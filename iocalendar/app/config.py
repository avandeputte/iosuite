"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iocalendar"
APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, FORWARDED_ALLOW_IPS, TLS_CERT_FILE, TLS_KEY_FILE,
# MCP_FORCED, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR))

# the app's own database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD; no default password)
_db = shared.own_db("calendar")
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

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
MAX_JSON_BYTES = 4 * 1024 * 1024      # any other request body

# `python -m app.mcp` (stdio) acts as this account. Updates: IOCALENDAR_REPO, IOCALENDAR_BRANCH and UPDATE_CHECK are read
# by iosuite_shared.updates (app.auth.updater)
MCP_USER = env("MCP_USER")
