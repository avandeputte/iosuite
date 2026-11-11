"""Settings: config.env in the app folder (setup.sh writes it), or the environment, which wins. What ioBackup keeps
(servers, destinations, jobs, the history of runs) lives in MariaDB; the passwords and Google keys with the suite's
keys and tokens. The settings every app of the suite shares come from iosuite_shared.config.standard."""
from pathlib import Path

from iosuite_shared import config as shared

APP = "iobackup"
APP_DIR = Path(__file__).resolve().parent.parent
shared.load_file(APP_DIR)  # first: iosuite_shared reads its settings (the Shared ioSuite database, COOKIE_DOMAIN) from it too
env, env_flag, env_int = shared.env, shared.env_flag, shared.env_int
# APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL, BASE_URL, TLS_CERT_FILE, TLS_KEY_FILE,
# MCP_FORCED, ADMIN_USER, ADMIN_PASSWORD: the same names in every app (iosuite_shared.config.standard says what each is)
_std = shared.standard(APP, APP_DIR)
globals().update(_std)

# the app's own database (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD; no default password)
_db = shared.own_db("backup")
DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD = _db["host"], _db["port"], _db["database"], _db["user"], _db["password"]

TZ = env("TZ")

# the folder a new local destination suggests (the Docker image mounts a volume there)
BACKUP_DIR = env("BACKUP_DIR", "/var/backups/iobackup")
# where a backup is put together before it is stored (room for two compressed backups), and where a backup read from
# Google Drive is kept while it is restored
WORK_DIR = Path(env("WORK_DIR", str(_std["DATA_DIR"] / "work"))).expanduser()
CACHE_DIR = Path(env("CACHE_DIR", str(_std["DATA_DIR"] / "cache"))).expanduser()

MAX_JSON_BYTES = 1024 * 1024   # any request body (a service account key fits)

# Updates: IOBACKUP_REPO, IOBACKUP_BRANCH and UPDATE_CHECK are read by iosuite_shared.updates (app.auth.updater)
