"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared, serve

APP = "iocontact"
APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# MCP_FORCED, KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR))

# the app's own database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD; no default password). The Shared ioSuite database
# (IOSUITE_DB_*: accounts, sessions, app passwords, roles, suite-wide settings) is read by iosuite_shared itself, on the
# contacts' server unless told otherwise.
_db = shared.own_db("contacts")
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

# LDAP directory (read-only): port 0 turns it off; it listens where the web app does unless told otherwise
LDAP_PORT = env_int("LDAP_PORT", 3890)
LDAP_HOST = [h.strip("[]") for h in serve.hosts(env("LDAP_HOST", env("HOST")))]
LDAP_BASE = env("LDAP_BASE", "dc=iocontact")

# ioPix is found in the suite's list of apps and signed in to by itself (app/iopix.py): nothing to set

MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_IMPORT_BYTES = 64 * 1024 * 1024   # a vCard, CSV or JSON file to import
MAX_JSON_BYTES = 16 * 1024 * 1024     # any other request body: a contact (JSON or vCard, a photo inline) or a CardDAV request

# `python -m app.mcp` (stdio) acts as this account. Updates: IOCONTACT_REPO, IOCONTACT_BRANCH and UPDATE_CHECK are read
# by iosuite_shared.updates (app.auth.updater)
MCP_USER = env("MCP_USER")
