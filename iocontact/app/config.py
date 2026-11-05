"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. Everything stored
lives in MariaDB."""
import os
from pathlib import Path

from iosuite_shared import config as shared

ROOT = Path(__file__).resolve().parent.parent
shared.load_file(ROOT)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int


DB_HOST = env("DB_HOST", "127.0.0.1")
DB_PORT = env_int("DB_PORT", 3306)
DB_NAME = env("DB_NAME", "contacts")
DB_USER = env("DB_USER", "contacts")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "contacts")

# The Shared ioSuite database (MariaDB, `iosuite`): the suite's accounts, passwords, sessions, app passwords and roles
# and the settings shared by every app of the suite. IOSUITE_DB_* set it; iosuite_shared reads them itself, and puts it
# on the contacts' server (DB_HOST, DB_PORT) unless told otherwise.

STATIC_DIR = ROOT / "static"
# the address people and the other apps reach ioContacts at, e.g. https://contacts.example.com (links in feeds and
# LDAP); empty: the address it is reached at
PUBLIC_URL = env("PUBLIC_URL").rstrip("/")

# where the server listens (python -m app); every app of the suite has its own default port (iosuite_shared.suite.PORTS)
HOST = env("HOST", "0.0.0.0")
PORT = env_int("PORT", 8640)
# the addresses that may tell the server the visitor's address and scheme (X-Forwarded-For / -Proto): * (any), or a
# comma-separated list such as the reverse proxy's
FORWARDED_ALLOW_IPS = env("FORWARDED_ALLOW_IPS", "*")
# HTTPS served directly instead of behind a reverse proxy: both files
TLS_CERT_FILE = env("TLS_CERT_FILE")
TLS_KEY_FILE = env("TLS_KEY_FILE")

# LDAP directory (read-only): port 0 turns it off
LDAP_PORT = env_int("LDAP_PORT", 3890)
LDAP_HOST = env("LDAP_HOST", "0.0.0.0")
LDAP_BASE = env("LDAP_BASE", "dc=iocontacts")

# ioPix (can also be set in Settings; the environment wins)
IOPIX_URL = env("IOPIX_URL")
IOPIX_USER = env("IOPIX_USER")
IOPIX_PASSWORD = env("IOPIX_PASSWORD")
IOPIX_CF_CLIENT_ID = env("IOPIX_CF_CLIENT_ID")
IOPIX_CF_CLIENT_SECRET = env("IOPIX_CF_CLIENT_SECRET")

MAX_PHOTO_BYTES = 2 * 1024 * 1024

# the server log, for Maintenance › Updates and logs (LOG_FILE= with nothing after it: none). Updates: IOCONTACTS_REPO,
# IOCONTACTS_BRANCH and UPDATE_CHECK are read by iosuite_shared.updates (app.auth.updater)
LOG_FILE = Path(os.environ.get("LOG_FILE", str(ROOT / "iocontacts.log"))) if os.environ.get("LOG_FILE", "x") else None

# the MCP server at /mcp: off until an admin turns it on in Settings, or MCP=1 here
MCP_FORCED = env_flag("MCP")
# `python -m app.mcp` (stdio) acts as this account
MCP_USER = env("MCP_USER")
