"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. Everything stored
lives in MariaDB, the photos, manuals and receipts too (so a backup of the database is a backup of everything). The
settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iothings"
APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# MCP_FORCED, KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR))

# the app's own database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD; no default password)
_db = shared.own_db("iothings")
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

MAX_FILE_BYTES = env_int("MAX_FILE_MB", 100) * 1024 * 1024  # one attachment (a manual, a receipt, a photo) as uploaded
MAX_IMPORT_BYTES = 20 * 1024 * 1024   # a Homebox export (CSV) to import
MAX_JSON_BYTES = 2 * 1024 * 1024      # any other request body

# `python -m app.mcp` (stdio) acts as this account. Updates: IOTHINGS_REPO, IOTHINGS_BRANCH and UPDATE_CHECK are read
# by iosuite_shared.updates (app.auth.updater)
MCP_USER = env("MCP_USER")
