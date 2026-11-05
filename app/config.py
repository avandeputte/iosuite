"""Settings from the environment (or iosuite.env next to the app). What the page keeps (the weather and
home page settings, the daily update check) lives in MariaDB; the environment wins over Settings where both name the same thing."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env_file():
    p = Path(os.environ.get("IOSUITE_ENV", ROOT / "iosuite.env"))
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
DB_NAME = env("DB_NAME", "suite")
DB_USER = env("DB_USER", "suite")
DB_PASSWORD = env("DB_PASSWORD", "suite")

STATIC_DIR = ROOT / "static"
PUBLIC_URL = env("PUBLIC_URL", "").rstrip("/")   # e.g. https://home.example.com (behind a reverse proxy)

# where the apps are: each registers itself in the suite's list in the Shared ioSuite database (see app/apps.py)

# the weather (AccuWeather; Settings › Home page does the same, the environment wins): an API key from developer.accuweather.com
ACCUWEATHER_API_KEY = env("ACCUWEATHER_API_KEY").strip()
ACCUWEATHER_LOCATION = env("ACCUWEATHER_LOCATION").strip()   # a location key (Settings finds it from a city name)

# updates: IOSUITE_REPO, IOSUITE_BRANCH and UPDATE_CHECK are read by iothing_auth.updates (app.auth.updater)
# the server log that Maintenance › Updates and logs shows (LOG_FILE= switches it off)
LOG_FILE = Path(env("LOG_FILE", str(ROOT / "iosuite.log"))) if env("LOG_FILE", "x") else None
