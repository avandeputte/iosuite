"""Paths and tunables: config.env in the app folder (setup.sh writes it; config.env.example lists them all), or the
environment, which wins. The settings every app of the suite shares come from iosuite_shared.config.standard.

Everything ionotes keeps lives in its database: MySQL/MariaDB (DB_TYPE=mysql and DB_HOST, DB_PORT, DB_NAME,
DB_USER, DB_PASSWORD), or a SQLite file in DATA_DIR for a quick try or the tests. The notes' images are stored in
the database too (BLOBs), so one database backup holds everything. DATA_DIR only keeps the session secret,
the log and the database settings an admin saved from the web app.
"""
import os
from pathlib import Path

from iosuite_shared import config as shared

APP = "ionotes"
APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, FORWARDED_ALLOW_IPS, TLS_CERT_FILE, TLS_KEY_FILE,
# MCP_FORCED, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
globals().update(shared.standard(APP, APP_DIR))

# READ_ONLY=1: browsing and searching only, for everyone
READ_ONLY = env_flag("READ_ONLY")
# OCR=0 keeps the server from reading text in images itself (the apps read it on the device and send it along)
OCR = env_flag("OCR", True)
# the account `python -m app.mcp` (stdio) acts as. Updates: IONOTES_REPO, IONOTES_BRANCH and UPDATE_CHECK are read by
# iosuite_shared.updates (app.auth.updater)
MCP_USER = env("MCP_USER")

# the largest image a note may carry; MariaDB's max_allowed_packet (16 MB by default) must be larger
MAX_IMAGE_MB = env_int("MAX_IMAGE_MB", 15)
THUMB_SIZE = env_int("THUMB_SIZE", 480)
THUMB_QUALITY = env_int("THUMB_QUALITY", 80)
MAX_JSON_BYTES = 8 << 20                  # a JSON request larger than this is refused before it is read (pictures go as their own body)
MAX_IMAGE_BYTES = (MAX_IMAGE_MB + 1) << 20
MAX_IMPORT_BYTES = 4 << 30                # an export with every picture; spooled to disk as it arrives, never held in memory


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
