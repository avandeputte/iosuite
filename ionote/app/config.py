"""Paths and tunables: config.env in the app folder (setup.sh writes it; config.env.example lists them all), or the
environment, which wins.

Everything ionotes keeps lives in its database: MySQL/MariaDB (DB_TYPE=mysql and DB_HOST, DB_PORT, DB_NAME,
DB_USER, DB_PASSWORD), or a SQLite file in DATA_DIR for a quick try or the tests. The notes' images are stored in
the database too (BLOBs), so one database backup holds everything. DATA_DIR only keeps the session secret,
the log and the database settings an admin saved from the web app.
"""
import os
from pathlib import Path

from iosuite_shared import config as shared

APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int


def _path(name: str, default: Path) -> Path:
    return Path(env(name, str(default))).expanduser().resolve()


DATA_DIR = _path("DATA_DIR", APP_DIR / "data")
STATIC_DIR = APP_DIR / "static"
# the server log, for Maintenance › Updates and logs and the MCP tool (LOG_FILE= with nothing after it: none)
LOG_FILE = _path("LOG_FILE", DATA_DIR / "ionotes.log") if os.environ.get("LOG_FILE", "x") else None
DATA_DIR.mkdir(parents=True, exist_ok=True)

# the address people and the other apps reach ionotes at, e.g. https://notes.example.com (the suite's list of apps);
# empty: the address it is reached at, noted by iosuite-shared
PUBLIC_URL = env("PUBLIC_URL").rstrip("/")

# where the server listens (python -m app); every app of the suite has its own default port (iosuite_shared.suite.PORTS)
HOST = env("HOST", "0.0.0.0")
PORT = env_int("PORT", 8610)
# the addresses that may tell the server the visitor's address and scheme (X-Forwarded-For / -Proto): * (any), or a
# comma-separated list such as the reverse proxy's
FORWARDED_ALLOW_IPS = env("FORWARDED_ALLOW_IPS", "*")
# HTTPS served directly instead of behind a reverse proxy: both files
TLS_CERT_FILE = env("TLS_CERT_FILE")
TLS_KEY_FILE = env("TLS_KEY_FILE")
# the address links in MCP results point at
BASE_URL = PUBLIC_URL or f"http://localhost:{PORT}"

# the first admin account, created on a first start with no accounts (containers, installers)
ADMIN_USER = env("ADMIN_USER")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# READ_ONLY=1: browsing and searching only, for everyone
READ_ONLY = env_flag("READ_ONLY")
# MCP=1 turns the MCP endpoint on whatever Settings says (MCP_ADMIN_TOKEN, which fixes its token, and UPDATE_CHECK=0,
# which locks the daily version check off, are read by iosuite_shared.updates: app.auth.updater)
MCP_FORCED = env_flag("MCP")
# OCR=0 keeps the server from reading text in images itself (the apps read it on the device and send it along)
OCR = env_flag("OCR", True)

# the largest image a note may carry; MariaDB's max_allowed_packet (16 MB by default) must be larger
MAX_IMAGE_MB = env_int("MAX_IMAGE_MB", 15)
THUMB_SIZE = env_int("THUMB_SIZE", 480)
THUMB_QUALITY = env_int("THUMB_QUALITY", 80)


# the names of the database settings in config.env, by db.KEYS
DB_ENV = {"type": "DB_TYPE", "host": "DB_HOST", "port": "DB_PORT", "database": "DB_NAME", "user": "DB_USER",
          "password": "DB_PASSWORD"}


def db_env(key: str):
    """DB_TYPE, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD from the environment (None when unset)."""
    v = os.environ.get(DB_ENV[key])
    return v if v not in (None, "") else None


def proxy_env(name: str):
    """A proxy sign-in setting from the environment, or None when it is not set there."""
    v = os.environ.get(name)
    return v if v is not None and v.strip() != "" else None
