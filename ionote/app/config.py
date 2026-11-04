"""Paths and tunables. Everything can be overridden with environment variables (ionotes.env, the container's
environment).

Everything ionotes keeps lives in its database: MySQL/MariaDB (DB_TYPE=mysql and DB_HOST, DB_PORT, DB_DATABASE,
DB_USER, DB_PASSWORD), or a SQLite file in DATA_DIR for a quick try or the tests. The notes' images are stored in
the database too (BLOBs), so one database backup holds everything. DATA_DIR only keeps the session secret,
the log and the database settings an admin saved from the web app.
"""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent


def _path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


DATA_DIR = _path("DATA_DIR", APP_DIR / "data")
STATIC_DIR = APP_DIR / "static"
LOG_FILE = DATA_DIR / "ionotes.log"
DATA_DIR.mkdir(parents=True, exist_ok=True)

PORT = int(os.environ.get("PORT", 8610))
# the address the web app is reached at (for links in MCP results), e.g. https://notes.example.com
APP_URL = os.environ.get("APP_URL", "").rstrip("/") or f"http://localhost:{PORT}"
# the address the suite's other apps link to (iothing-auth's list of apps): APP_URL as configured; empty: the address
# ionotes is reached at, noted by iothing-auth
PUBLIC_URL = os.environ.get("APP_URL", "").strip().rstrip("/")

# the first admin account, created on a first start with no accounts (containers, installers)
ADMIN_USER = os.environ.get("ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# READ_ONLY=1: browsing and searching only, for everyone
READ_ONLY = _flag("READ_ONLY")
# MCP=1 turns the MCP endpoint on whatever Settings says; MCP_ADMIN_TOKEN fixes its token
MCP_FORCED = _flag("MCP")
MCP_ADMIN_TOKEN = os.environ.get("MCP_ADMIN_TOKEN", "").strip()
# OCR=0 keeps the server from reading text in images itself (the apps read it on the device and send it along)
OCR = _flag("OCR", "1")
# UPDATE_CHECK=0: never ask GitHub whether a newer version exists
UPDATE_CHECK = _flag("UPDATE_CHECK", "1")

# the largest image a note may carry; MariaDB's max_allowed_packet (16 MB by default) must be larger
MAX_IMAGE_MB = int(os.environ.get("MAX_IMAGE_MB", 15))
THUMB_SIZE = int(os.environ.get("THUMB_SIZE", 480))
THUMB_QUALITY = int(os.environ.get("THUMB_QUALITY", 80))


def db_env(key: str):
    """DB_TYPE, DB_HOST... from the environment (None when unset)."""
    v = os.environ.get("DB_" + key.upper())
    return v if v not in (None, "") else None


def proxy_env(name: str):
    """A proxy sign-in setting from the environment, or None when it is not set there."""
    v = os.environ.get(name)
    return v if v is not None and v.strip() != "" else None
