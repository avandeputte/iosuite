"""ionotes' database: MySQL/MariaDB (the normal case), or a SQLite file in DATA_DIR (a quick try, the tests).

The code is written in one SQL dialect (? placeholders, INSERT OR REPLACE / OR IGNORE) and the wrapper translates
it for MySQL, the same way iopix's viewer database does. Rows answer to an index and to a column name.

Where the database is comes from the environment (DB_TYPE, DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD),
else from data/db.json (written by setup.sh or Settings › Database), else SQLite in data/ionotes.db. The settings
live outside the database since everything else is inside it.

Every note, folder and tag colour carries `rev`, a number from one counter that grows with every change. The
apps ask for everything changed since the last rev they saw (GET /api/sync?since=), which is how they keep
their offline copy current. Deletions are kept as tombstones (deleted = 1) for that reason.
"""
import json
import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from app import config

log = logging.getLogger("app.db")
CONF = config.DATA_DIR / "db.json"
SQLITE_FILE = config.DATA_DIR / "ionotes.db"
KEYS = ("type", "host", "port", "database", "user", "password")
SCHEMA_VERSION = 3  # 2: notes, folders, tag colours and the change log belong to an account; 3: the suite naming convention (nts_ tables)
PREFIX = "nts"
_cfg = None
_lock = threading.Lock()
_ready = False
error = None  # why the configured database could not be used at start

try:
    import pymysql
    Error = (sqlite3.Error, pymysql.err.Error)
except ImportError:  # pragma: no cover
    pymysql = None
    Error = (sqlite3.Error,)

# ---- schema: one definition per table, the SQLite and the MySQL spelling. Every table is nts_<name>, the suite's
# naming convention (the apps can share one database)
TABLES = {
    # accounts live in the Shared ioSuite database (iosuite-shared, app/auth.py)
    "nts_settings": (
        "CREATE TABLE IF NOT EXISTS nts_settings (name TEXT PRIMARY KEY, value TEXT, updated_at TEXT)",
        "CREATE TABLE IF NOT EXISTS nts_settings (name VARCHAR(191) PRIMARY KEY, value MEDIUMTEXT, updated_at DATETIME(3) NULL) "
        "ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"),
    "nts_schema_version": (
        "CREATE TABLE IF NOT EXISTS nts_schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS nts_schema_version (version INT PRIMARY KEY, applied_at DATETIME(3) NOT NULL) "
        "ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"),
    # one row per change: its id is the rev stamped on what changed
    "nts_change_counter": (
        "CREATE TABLE IF NOT EXISTS nts_change_counter (rev INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER)",
        "CREATE TABLE IF NOT EXISTS nts_change_counter (rev BIGINT AUTO_INCREMENT PRIMARY KEY, created_at BIGINT) "
        "ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"),
    # times are seconds since 1970 (UTC) as the apps send them; tags is a JSON list of names; user_id: the account's
    # id in the Shared ioSuite database (0 until the first admin claims the records made before accounts)
    "nts_notes": (
        "CREATE TABLE IF NOT EXISTS nts_notes (uuid TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', body TEXT NOT NULL DEFAULT '', "
        "ocr_text TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT 'manual', source_app TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, "
        "tags TEXT NOT NULL DEFAULT '[]', pinned INTEGER NOT NULL DEFAULT 0, folder_id TEXT, has_image INTEGER NOT NULL DEFAULT 0, image_sha TEXT, "
        "deleted INTEGER NOT NULL DEFAULT 0, rev INTEGER NOT NULL DEFAULT 0, changed_by TEXT, user_id INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS nts_notes (uuid VARCHAR(64) PRIMARY KEY, title TEXT NOT NULL, body MEDIUMTEXT NOT NULL, "
        "ocr_text MEDIUMTEXT NOT NULL, source VARCHAR(32) NOT NULL DEFAULT 'manual', source_app VARCHAR(191), created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, "
        "tags TEXT NOT NULL, pinned INT NOT NULL DEFAULT 0, folder_id VARCHAR(64), has_image INT NOT NULL DEFAULT 0, image_sha VARCHAR(64), "
        "deleted INT NOT NULL DEFAULT 0, rev BIGINT NOT NULL DEFAULT 0, changed_by VARCHAR(191), user_id BIGINT NOT NULL DEFAULT 0, "
        "INDEX idx_nts_notes_rev (rev), INDEX idx_nts_notes_folder (folder_id), INDEX idx_nts_notes_updated (updated_at), "
        "INDEX idx_nts_notes_user (user_id, rev), "
        "FULLTEXT INDEX idx_nts_notes_text (title, body, ocr_text, tags)) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"),
    # the picture of a note: the bytes as sent, and a small JPEG for lists
    "nts_note_images": (
        "CREATE TABLE IF NOT EXISTS nts_note_images (uuid TEXT PRIMARY KEY, mime TEXT NOT NULL, data BLOB NOT NULL, thumb BLOB, width INTEGER, height INTEGER, "
        "size_bytes INTEGER, sha TEXT, updated_at REAL)",
        "CREATE TABLE IF NOT EXISTS nts_note_images (uuid VARCHAR(64) PRIMARY KEY, mime VARCHAR(64) NOT NULL, data LONGBLOB NOT NULL, thumb MEDIUMBLOB, "
        "width INT, height INT, size_bytes BIGINT, sha VARCHAR(64), updated_at DOUBLE) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"),
    "nts_folders": (
        "CREATE TABLE IF NOT EXISTS nts_folders (uuid TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '', color TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL, "
        "deleted INTEGER NOT NULL DEFAULT 0, rev INTEGER NOT NULL DEFAULT 0, user_id INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS nts_folders (uuid VARCHAR(64) PRIMARY KEY, name VARCHAR(255) NOT NULL DEFAULT '', color VARCHAR(16), created_at DOUBLE NOT NULL, "
        "updated_at DOUBLE NOT NULL, deleted INT NOT NULL DEFAULT 0, rev BIGINT NOT NULL DEFAULT 0, user_id BIGINT NOT NULL DEFAULT 0, "
        "INDEX idx_nts_folders_rev (rev), INDEX idx_nts_folders_user (user_id, rev)) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"),
    # a tag's colour; tags themselves are names on notes. tag_key: the name in lower case; two accounts may colour
    # the same tag differently
    "nts_tag_colors": (
        "CREATE TABLE IF NOT EXISTS nts_tag_colors (user_id INTEGER NOT NULL DEFAULT 0, tag_key TEXT NOT NULL, name TEXT NOT NULL, color TEXT, "
        "updated_at REAL NOT NULL, deleted INTEGER NOT NULL DEFAULT 0, rev INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, tag_key))",
        "CREATE TABLE IF NOT EXISTS nts_tag_colors (user_id BIGINT NOT NULL DEFAULT 0, tag_key VARCHAR(191) NOT NULL, name VARCHAR(191) NOT NULL, "
        "color VARCHAR(16), updated_at DOUBLE NOT NULL, deleted INT NOT NULL DEFAULT 0, rev BIGINT NOT NULL DEFAULT 0, "
        "PRIMARY KEY (user_id, tag_key), INDEX idx_nts_tag_colors_rev (rev)) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"),
    # what changed and who changed it, for Maintenance › Change log
    "nts_change_log": (
        "CREATE TABLE IF NOT EXISTS nts_change_log (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at INTEGER, user_name TEXT, action TEXT, kind TEXT, "
        "uuid TEXT, summary TEXT, user_id INTEGER NOT NULL DEFAULT 0)",
        "CREATE TABLE IF NOT EXISTS nts_change_log (id BIGINT AUTO_INCREMENT PRIMARY KEY, created_at BIGINT, user_name VARCHAR(191), action VARCHAR(32), "
        "kind VARCHAR(16), uuid VARCHAR(64), summary TEXT, user_id BIGINT NOT NULL DEFAULT 0, INDEX idx_nts_change_log_created (created_at), "
        "INDEX idx_nts_change_log_user (user_id, id)) ENGINE=InnoDB CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"),
}
SQLITE_INDEXES = {  # SQLite's index names are database-wide: named after the table like MySQL's
    "idx_nts_notes_rev": "nts_notes (rev)",
    "idx_nts_notes_folder": "nts_notes (folder_id)",
    "idx_nts_notes_updated": "nts_notes (updated_at)",
    "idx_nts_notes_user": "nts_notes (user_id, rev)",
    "idx_nts_folders_rev": "nts_folders (rev)",
    "idx_nts_folders_user": "nts_folders (user_id, rev)",
    "idx_nts_tag_colors_rev": "nts_tag_colors (rev)",
    "idx_nts_change_log_created": "nts_change_log (created_at)",
    "idx_nts_change_log_user": "nts_change_log (user_id, id)",
}

_INSERT_IGNORE = re.compile(r"\bINSERT\s+OR\s+IGNORE\b", re.I)
_INSERT_REPLACE = re.compile(r"\bINSERT\s+OR\s+REPLACE\b", re.I)


class Row(tuple):
    """A row that answers to an index and to a column name, like sqlite3.Row on both databases."""

    def __new__(cls, values, names):
        r = super().__new__(cls, values)
        r._names = names
        return r

    def __getitem__(self, k):
        if isinstance(k, str):
            return tuple.__getitem__(self, self._names.index(k))
        return tuple.__getitem__(self, k)

    def keys(self):
        return list(self._names)


class Cursor:
    def __init__(self, cur):
        self.cur = cur

    def _names(self):
        return [d[0] for d in (self.cur.description or [])]

    def fetchone(self):
        r = self.cur.fetchone()
        return None if r is None else Row(r, self._names())

    def fetchall(self):
        names = self._names()
        return [Row(r, names) for r in self.cur.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def lastrowid(self):
        return self.cur.lastrowid

    @property
    def rowcount(self):
        return self.cur.rowcount


class Conn:
    def __init__(self, raw, mysql: bool):
        self.raw, self.mysql = raw, mysql

    def sql(self, sql: str) -> str:
        if not self.mysql:
            return sql
        sql = _INSERT_IGNORE.sub("INSERT IGNORE", sql)
        sql = _INSERT_REPLACE.sub("REPLACE", sql)
        return sql.replace("%", "%%").replace("?", "%s")

    def execute(self, sql: str, params=()):
        if self.mysql:
            cur = self.raw.cursor()
            cur.execute(self.sql(sql), tuple(params))
            return Cursor(cur)
        return Cursor(self.raw.execute(sql, tuple(params)))

    def executemany(self, sql: str, rows):
        if self.mysql:
            cur = self.raw.cursor()
            cur.executemany(self.sql(sql), [tuple(r) for r in rows])
            return Cursor(cur)
        return Cursor(self.raw.executemany(sql, rows))

    def begin(self):
        """A write transaction. SQLite's BEGIN IMMEDIATE lets one writer in at a time; on MySQL the lock row does the
        same. That keeps commits in rev order: a reader never sees rev 101 committed while rev 100 is still on its
        way, which would let a device's sync cursor (GET /api/sync) pass it by for good."""
        if not self.mysql:
            self.execute("BEGIN IMMEDIATE")
            return
        self.execute("START TRANSACTION")
        if not self.execute("SELECT value FROM nts_settings WHERE name = 'write_lock' FOR UPDATE").fetchone():
            self.execute("INSERT IGNORE INTO nts_settings (name, value) VALUES ('write_lock', '')")
            self.execute("SELECT value FROM nts_settings WHERE name = 'write_lock' FOR UPDATE")

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        try:
            self.raw.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# ---- configuration
def settings() -> dict:
    """{type, host, port, database, user, password}: the environment wins, then data/db.json, else SQLite."""
    global _cfg
    if _cfg is None:
        c = {"type": "sqlite", "host": "", "port": 3306, "database": "ionotes", "user": "", "password": ""}
        try:
            c.update({k: v for k, v in json.loads(CONF.read_text()).items() if k in KEYS})
        except (OSError, ValueError):
            pass
        for k in KEYS:
            v = config.db_env(k)
            if v:
                c[k] = v
        c["port"] = int(c.get("port") or 3306)
        c["type"] = "mysql" if str(c.get("type")).lower() in ("mysql", "mariadb") else "sqlite"
        _cfg = c
    return dict(_cfg)


def public_settings() -> dict:
    """For Settings › Database: the password replaced by whether one is set."""
    c = settings()
    return {**{k: v for k, v in c.items() if k != "password"}, "password_set": bool(c["password"]), "error": error,
            "sqlite_file": str(SQLITE_FILE), "fromEnv": [k for k in KEYS if config.db_env(k)]}


def save_settings(values: dict):
    """Write data/db.json (setup.sh and Settings › Database); used from the next start."""
    c = {k: values[k] for k in KEYS if k in values}
    CONF.write_text(json.dumps(c, indent=2))
    try:
        CONF.chmod(0o600)
    except OSError:
        pass


def is_mysql() -> bool:
    return settings()["type"] == "mysql"


def _open_mysql(c: dict, database=True):
    if pymysql is None:
        raise RuntimeError("PyMySQL is not installed")
    return pymysql.connect(host=c["host"], port=int(c["port"]), user=c["user"], password=c["password"],
                           database=c["database"] if database else None, charset="utf8mb4", connect_timeout=8,
                           read_timeout=120, write_timeout=120, autocommit=False)


def connect() -> Conn:
    """A new connection; the caller closes it (with connect() as con: ...)."""
    if not _ready:
        init()
    return _raw_connect()


def _raw_connect() -> Conn:
    c = settings()
    if c["type"] == "mysql":
        return Conn(_open_mysql(c), True)
    raw = sqlite3.connect(str(SQLITE_FILE), timeout=30, isolation_level=None if False else "")
    raw.execute("PRAGMA foreign_keys = OFF")
    raw.execute("PRAGMA busy_timeout = 30000")
    return Conn(raw, False)


@contextmanager
def tx():
    """A connection in a write transaction: committed on success, rolled back on an exception."""
    con = connect()
    try:
        con.begin()
        yield con
        con.commit()
    except BaseException:
        try:
            con.rollback()
        except Exception:
            pass
        raise
    finally:
        con.close()


def same_server(c: dict) -> bool:
    """Whether c names the configured MySQL server and user, the only place the saved password may be sent."""
    cur = settings()
    return (str(c.get("host") or "").strip().lower() == str(cur["host"] or "").strip().lower()
            and int(c.get("port") or 3306) == int(cur["port"] or 3306) and str(c.get("user") or "") == str(cur["user"] or ""))


def test(values: dict) -> dict:
    """Try a MySQL/MariaDB connection (Settings › Database, setup.sh): {ok, version} or {ok: False, error}."""
    c = {**settings(), **{k: v for k, v in values.items() if k in KEYS}}
    if not values.get("password"):  # the saved password, only ever for the server and user it belongs to
        if not same_server(c):
            return {"ok": False, "error": "Enter the password: the saved one is only used for the server and user it belongs to"}
        c["password"] = settings()["password"]
    try:
        raw = _open_mysql(c)
        try:
            cur = raw.cursor()
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]
            cur.execute("SHOW VARIABLES LIKE 'max_allowed_packet'")
            r = cur.fetchone()
            packet = int(r[1]) if r else None
        finally:
            raw.close()
        out = {"ok": True, "version": version, "maxAllowedPacket": packet}
        if packet and packet < (config.MAX_IMAGE_MB + 1) << 20:
            out["warning"] = (f"max_allowed_packet is {packet >> 20} MB: images up to {config.MAX_IMAGE_MB} MB need it larger "
                              f"(SET GLOBAL max_allowed_packet = {(config.MAX_IMAGE_MB + 9) << 20}, and in the server's config)")
        return out
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def init():
    """Create the tables that are missing (idempotent). Called at start and by the first connect()."""
    global _ready, error
    with _lock:
        if _ready:
            return
        con = _raw_connect()
        try:
            for name, (lite, my) in TABLES.items():
                con.execute(my if con.mysql else lite)
            if not con.mysql:
                for idx, on in SQLITE_INDEXES.items():
                    con.execute(f"CREATE INDEX IF NOT EXISTS {idx} ON {on}")
            con.execute("INSERT OR IGNORE INTO nts_settings (name, value) VALUES ('write_lock', '')")  # Conn.begin
            con.execute("INSERT OR IGNORE INTO nts_schema_version (version, applied_at) VALUES (?, ?)",
                        (SCHEMA_VERSION, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23]))
            con.commit()
        finally:
            con.close()
        error = None
        _ready = True


def schema_version() -> int:
    with connect() as con:
        r = con.execute("SELECT max(version) FROM nts_schema_version").fetchone()
    return int(r[0] or 0)


def reset_for_tests():
    """Forget the cached settings (the tests point DATA_DIR and DB_* elsewhere)."""
    global _cfg, _ready
    _cfg, _ready = None, False


# ---- settings table
def get_setting(key: str, default: str = None):
    with connect() as con:
        r = con.execute("SELECT value FROM nts_settings WHERE name = ?", (key,)).fetchone()
    return r[0] if r else default


def set_setting(key: str, value):
    with tx() as con:
        con.execute("INSERT OR REPLACE INTO nts_settings (name, value, updated_at) VALUES (?, ?, ?)",
                    (key, None if value is None else str(value), datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:23]))


def read_only() -> bool:
    return config.READ_ONLY or get_setting("read_only", "0") == "1"


def next_rev(con: Conn) -> int:
    """A new change number, inside the caller's transaction."""
    import time
    return con.execute("INSERT INTO nts_change_counter (created_at) VALUES (?)", (int(time.time()),)).lastrowid


def current_rev() -> int:
    with connect() as con:
        r = con.execute("SELECT max(rev) FROM nts_change_counter").fetchone()
    return int(r[0] or 0)
