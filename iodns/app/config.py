"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. Everything stored
lives in MariaDB. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared, suite

APP = "iodns"
PORT_DEFAULT = 8660
APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int
# the suite's list of ports (iosuite_shared.suite.PORTS) names ioDNS from iosuite-shared 0.31; until then, its port here
suite.PORTS.setdefault(APP, PORT_DEFAULT)
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, FORWARDED_ALLOW_IPS, TLS_CERT_FILE, TLS_KEY_FILE,
# MCP_FORCED, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR))

# the app's own database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD; no default password)
_db = shared.own_db("dns")
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

TZ = env("TZ")

# how often the servers are compared with the master list on their own (minutes; 0: only when someone looks)
CHECK_MINUTES = env_int("CHECK_MINUTES", 30)

MAX_JSON_BYTES = 4 * 1024 * 1024   # any request body (an import of a few thousand entries fits)

# Updates: IODNS_REPO, IODNS_BRANCH and UPDATE_CHECK are read by iosuite_shared.updates (app.auth.updater)
