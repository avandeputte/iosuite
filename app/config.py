"""Settings from the environment (or iosuite.env next to the app). What the page keeps (the weather and
home page settings, the update switch) lives in MariaDB; the environment wins over Settings where both name the same thing."""
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

# updates: the GitHub repository and branch followed by the version check and update.sh
REPO = env("IOSUITE_REPO", "avandeputte/iosuite")
BRANCH = env("IOSUITE_BRANCH", "main")
# UPDATE_CHECK=0 turns the daily "is there a newer version" check off for good (the setting cannot turn it back on)
UPDATE_CHECK_LOCKED = env("UPDATE_CHECK", "").strip().lower() in ("0", "off", "false", "no")
