"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. What the page keeps
(the weather and home page settings, the daily update check) lives in MariaDB; the environment wins over Settings where
both name the same thing."""
import os
from pathlib import Path

from iosuite_shared import config as shared

ROOT = Path(__file__).resolve().parent.parent
shared.load_file(ROOT)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int


DB_HOST = env("DB_HOST", "127.0.0.1")
DB_PORT = env_int("DB_PORT", 3306)
DB_NAME = env("DB_NAME", "suite")
DB_USER = env("DB_USER", "suite")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "suite")

STATIC_DIR = ROOT / "static"
# the address people and the other apps reach the start page at, e.g. https://home.example.com (behind a reverse
# proxy); empty: the address it is reached at
PUBLIC_URL = env("PUBLIC_URL").rstrip("/")

# where the server listens (python -m app); every app of the suite has its own default port (iosuite_shared.suite.PORTS)
HOST = env("HOST", "0.0.0.0")
PORT = env_int("PORT", 8630)
# the addresses that may tell the server the visitor's address and scheme (X-Forwarded-For / -Proto): * (any), or a
# comma-separated list such as the reverse proxy's
FORWARDED_ALLOW_IPS = env("FORWARDED_ALLOW_IPS", "*")
# HTTPS served directly instead of behind a reverse proxy: both files
TLS_CERT_FILE = env("TLS_CERT_FILE")
TLS_KEY_FILE = env("TLS_KEY_FILE")

# where the apps are: each registers itself in the suite's list in the Shared ioSuite database (see app/apps.py)

# the weather (AccuWeather; Settings › Home page does the same, the environment wins): an API key from developer.accuweather.com
ACCUWEATHER_API_KEY = env("ACCUWEATHER_API_KEY").strip()
ACCUWEATHER_LOCATION = env("ACCUWEATHER_LOCATION").strip()   # a location key (Settings finds it from a city name)

# Home Assistant (Settings › Home Assistant does the same, the environment wins): its address and a long-lived access token
HA_URL = env("HA_URL").strip().rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "").strip()
HA_FEED = env_flag("HA_FEED", True)   # HA_FEED=0: no websocket to Home Assistant, the page polls instead

# updates: IOSUITE_REPO, IOSUITE_BRANCH and UPDATE_CHECK are read by iosuite_shared.updates (app.auth.updater)
# the server log that Maintenance › Updates and logs shows (LOG_FILE= with nothing after it: none)
LOG_FILE = Path(os.environ.get("LOG_FILE", str(ROOT / "iosuite.log"))) if os.environ.get("LOG_FILE", "x") else None
