"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. What the page keeps
(the weather and home page settings, the daily update check) lives in MariaDB; the environment wins over Settings where
both name the same thing. The settings every app of the suite shares come from iosuite_shared.config.standard."""
import os
from pathlib import Path

from iosuite_shared import config as shared

APP = "iosuite"
APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# MCP_FORCED, KEEP_DELETED_DAYS, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR))
ROOT = APP_DIR

# the app's own database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD; no default password). The Shared ioSuite database
# (IOSUITE_DB_*: accounts, sessions, app passwords, roles, suite-wide settings and the list of apps) is read by
# iosuite_shared itself, on the same server unless told otherwise.
_db = shared.own_db("suite")
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

# where the apps are: each registers itself in the suite's list in the Shared ioSuite database (see app/apps.py)

# the weather (AccuWeather; Settings › Home page does the same, the environment wins): an API key from developer.accuweather.com
ACCUWEATHER_API_KEY = env("ACCUWEATHER_API_KEY").strip()
ACCUWEATHER_LOCATION = env("ACCUWEATHER_LOCATION").strip()   # a location key (Settings finds it from a city name)

# Home Assistant (Settings › Home Assistant does the same, the environment wins): its address and a long-lived access token
HA_URL = env("HA_URL").strip().rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "").strip()
HA_FEED = env_flag("HA_FEED", True)   # HA_FEED=0: no websocket to Home Assistant, the page polls instead

MAX_IMPORT_BYTES = 16 * 1024 * 1024   # a bookmarks file to import
MAX_JSON_BYTES = 4 * 1024 * 1024      # any other request body

# updates: IOSUITE_REPO, IOSUITE_BRANCH and UPDATE_CHECK are read by iosuite_shared.updates (app.auth.updater)
