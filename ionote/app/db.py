"""ioNote's database: MariaDB/MySQL, through the suite's layer (iosuite_shared.db.Database: a pool of connections
and a transaction nested calls share), like every app of the suite. Rows answer to an index and to a column name.

Where the database is comes from config.env or the environment (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD).

Every note, folder and tag colour carries `rev`, a number from one counter that grows with every change. The
apps ask for everything changed since the last rev they saw (GET /api/sync?since=), which is how they keep
their offline copy current. Deletions are kept as tombstones (deleted = 1) for that reason.
"""
import logging
import threading
import time
from contextlib import contextmanager

import pymysql

from iosuite_shared import db as shared_db, schema

from app import config

log = logging.getLogger("app.db")
SCHEMA_VERSION = 4  # recorded in nts_schema_version (iosuite_shared.schema); the tables are made as SCHEMA says
PREFIX = "nts"
Error = pymysql.err.Error
_lock = threading.Lock()
_ready = False
error = None  # why the configured database could not be used at start

# ---- schema: every table is nts_<name>, the suite's naming convention (the apps can share one database), InnoDB
# and utf8mb4 (migrate() adds that). Accounts live in the Shared ioSuite database (iosuite-shared, app/auth.py)
SCHEMA = [
    # accounts live in the Shared ioSuite database (iosuite-shared, app/auth.py)
    ('CREATE TABLE IF NOT EXISTS nts_settings (name VARCHAR(191) PRIMARY KEY, value MEDIUMTEXT, '
     'updated_at DATETIME(3) NULL)'),
    # one row per change: its id is the rev stamped on what changed
    ('CREATE TABLE IF NOT EXISTS nts_change_counter (rev BIGINT AUTO_INCREMENT PRIMARY KEY, created_at BIGINT)'),
    # times are seconds since 1970 (UTC) as the apps send them; tags is a JSON list of names; user_id: the account's
    # id in the Shared ioSuite database (0: made while the install was open, before the first account)
    ('CREATE TABLE IF NOT EXISTS nts_notes (uuid VARCHAR(64) PRIMARY KEY, title TEXT NOT NULL, '
     "body MEDIUMTEXT NOT NULL, ocr_text MEDIUMTEXT NOT NULL, source VARCHAR(32) NOT NULL DEFAULT 'manual', "
     'source_app VARCHAR(191), created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, tags TEXT NOT NULL, '
     'pinned INT NOT NULL DEFAULT 0, folder_id VARCHAR(64), has_image INT NOT NULL DEFAULT 0, image_sha VARCHAR(64), '
     'deleted INT NOT NULL DEFAULT 0, rev BIGINT NOT NULL DEFAULT 0, changed_by VARCHAR(191), '
     'user_id BIGINT NOT NULL DEFAULT 0, INDEX idx_nts_notes_rev (rev), INDEX idx_nts_notes_folder (folder_id), '
     'INDEX idx_nts_notes_updated (updated_at), INDEX idx_nts_notes_user (user_id, rev), '
     'FULLTEXT INDEX idx_nts_notes_text (title, body, ocr_text, tags))'),
    # the picture of a note: the bytes as sent, and a small JPEG for lists
    ('CREATE TABLE IF NOT EXISTS nts_note_images (uuid VARCHAR(64) PRIMARY KEY, mime VARCHAR(64) NOT NULL, '
     'data LONGBLOB NOT NULL, thumb MEDIUMBLOB, width INT, height INT, size_bytes BIGINT, sha VARCHAR(64), '
     'updated_at DOUBLE)'),
    ("CREATE TABLE IF NOT EXISTS nts_folders (uuid VARCHAR(64) PRIMARY KEY, name VARCHAR(255) NOT NULL DEFAULT '', "
     'color VARCHAR(16), created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, deleted INT NOT NULL DEFAULT 0, '
     'rev BIGINT NOT NULL DEFAULT 0, user_id BIGINT NOT NULL DEFAULT 0, INDEX idx_nts_folders_rev (rev), '
     'INDEX idx_nts_folders_user (user_id, rev))'),
    # a tag's colour; tags themselves are names on notes. tag_key: the name in lower case; two accounts may colour
    # the same tag differently
    ('CREATE TABLE IF NOT EXISTS nts_tag_colors (user_id BIGINT NOT NULL DEFAULT 0, tag_key VARCHAR(191) NOT NULL, '
     'name VARCHAR(191) NOT NULL, color VARCHAR(16), updated_at DOUBLE NOT NULL, deleted INT NOT NULL DEFAULT 0, '
     'rev BIGINT NOT NULL DEFAULT 0, PRIMARY KEY (user_id, tag_key), INDEX idx_nts_tag_colors_rev (rev))'),
    # files attached to a note beside its picture (PDFs, more pictures, documents): the bytes, a small JPEG for
    # pictures, and the text found in them (a PDF's text, a picture's text read by RapidOCR, a text file), which search
    # covers. A note's rev moves whenever its attachments change, and the note lists them (notes.py), so the devices
    # learn of them with the note itself
    ('CREATE TABLE IF NOT EXISTS nts_attachments (uuid VARCHAR(64) PRIMARY KEY, note_uuid VARCHAR(64) NOT NULL, '
     "user_id BIGINT NOT NULL DEFAULT 0, name VARCHAR(255) NOT NULL DEFAULT '', mime VARCHAR(128) NOT NULL, "
     'size_bytes BIGINT NOT NULL DEFAULT 0, sha VARCHAR(64), width INT, height INT, data LONGBLOB NOT NULL, '
     'thumb MEDIUMBLOB, text MEDIUMTEXT NOT NULL, created_at DOUBLE NOT NULL, '
     'INDEX idx_nts_attachments_note (note_uuid), FULLTEXT INDEX idx_nts_attachments_text (name, text))'),
    # templates for new notes: a title, text, tags and a folder; {{date}} and the like are filled in when a note is
    # made from one. Synced to the devices like folders (rev, tombstones)
    ('CREATE TABLE IF NOT EXISTS nts_templates (uuid VARCHAR(64) PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 0, '
     "name VARCHAR(255) NOT NULL DEFAULT '', title TEXT NOT NULL, body MEDIUMTEXT NOT NULL, tags TEXT NOT NULL, "
     'folder_id VARCHAR(64), created_at DOUBLE NOT NULL, updated_at DOUBLE NOT NULL, deleted INT NOT NULL DEFAULT 0, '
     'rev BIGINT NOT NULL DEFAULT 0, INDEX idx_nts_templates_rev (rev), INDEX idx_nts_templates_user (user_id, rev))'),
    # what changed and who changed it, for the change log (Manage › Change log)
    ('CREATE TABLE IF NOT EXISTS nts_change_log (id BIGINT AUTO_INCREMENT PRIMARY KEY, created_at BIGINT, '
     'user_name VARCHAR(191), action VARCHAR(32), kind VARCHAR(16), uuid VARCHAR(64), summary TEXT, '
     'user_id BIGINT NOT NULL DEFAULT 0, INDEX idx_nts_change_log_created (created_at), '
     'INDEX idx_nts_change_log_user (user_id, id))'),
]


class Row(tuple):
    """A row that answers to an index and to a column name."""

    def __new__(cls, values, names):
        r = super().__new__(cls, values)
        r._names = names
        return r

    def __getitem__(self, k):
        if isinstance(k, str):
            return tuple.__getitem__(self, self._names.index(k))
        return tuple.__getitem__(self, k)


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
    """A connection of the pool as ioNote's code uses it: execute() gives a cursor whose rows answer to names too.
    connect() lends one for reads (each statement on its own: the connections are in autocommit mode); tx() hands
    out the thread's transaction."""

    def __init__(self, raw, lent: bool = False):
        self.raw, self._lent = raw, lent

    def execute(self, sql: str, params=()):
        cur = self.raw.cursor()
        cur.execute(sql, tuple(params))
        return Cursor(cur)

    def commit(self):
        """Nothing to do outside tx(): every statement commits by itself."""

    def close(self, broken: bool = False):
        """Hands a connection from connect() back to the pool (closed when it failed); tx() ends its own."""
        raw, self.raw = self.raw, None
        if raw is not None and self._lent:
            _db.pool.give_back(raw, broken)

    def __enter__(self):
        return self

    def __exit__(self, kind, *exc):
        self.close(broken=kind is not None and issubclass(kind, shared_db.BROKEN))


# ---- configuration
def settings() -> dict:
    """{host, port, database, user, password}: from config.env or the environment."""
    return {"host": config.DB_HOST, "port": config.DB_PORT, "database": config.DB_NAME, "user": config.DB_USER,
            "password": config.DB_PASSWORD}


def public_settings() -> dict:
    """For the MCP diagnostics: the password replaced by whether one is set."""
    c = settings()
    return {**{k: v for k, v in c.items() if k != "password"}, "password_set": bool(c["password"]), "error": error}


def _open(c: dict, database=True):
    return pymysql.connect(host=c["host"], port=int(c["port"]), user=c["user"], password=c["password"],
                           database=c["database"] if database else None, charset="utf8mb4", connect_timeout=8,
                           read_timeout=120, write_timeout=120, autocommit=True)


# the pool, and the transaction nested calls on one thread share (iosuite_shared.db.Database)
_db = shared_db.Database(lambda: _open(settings()))


def connect() -> Conn:
    """A connection for reads, from the pool; the caller closes it (with connect() as con: ...), which hands it back."""
    if not _ready:
        init()
    return Conn(_db.pool.borrow(), lent=True)


@contextmanager
def tx():
    """A connection in a write transaction: committed on success, rolled back on an exception; nested calls share it.
    Writers take the lock row first, one at a time. That keeps commits in rev order: a reader never sees rev 101
    committed while rev 100 is still on its way, which would let a device's sync cursor (GET /api/sync) pass it by
    for good."""
    if not _ready:
        init()
    with _db.tx() as raw:
        con = Conn(raw)
        if not con.execute("SELECT value FROM nts_settings WHERE name = 'write_lock' FOR UPDATE").fetchone():
            con.execute("INSERT IGNORE INTO nts_settings (name, value) VALUES ('write_lock', '')")
            con.execute("SELECT value FROM nts_settings WHERE name = 'write_lock' FOR UPDATE")
        yield con


def same_server(c: dict) -> bool:
    """Whether c names the configured server and user, the only place the saved password may be sent."""
    cur = settings()
    return (str(c.get("host") or "").strip().lower() == str(cur["host"] or "").strip().lower()
            and int(c.get("port") or 3306) == int(cur["port"] or 3306) and str(c.get("user") or "") == str(cur["user"] or ""))


def test(values: dict) -> dict:
    """Try a MySQL/MariaDB connection (setup.sh, the MCP diagnostics): {ok, version} or {ok: False, error}."""
    keys = ("host", "port", "database", "user", "password")
    c = {**settings(), **{k: v for k, v in values.items() if k in keys}}
    if not values.get("password"):  # the saved password, only ever for the server and user it belongs to
        if not same_server(c):
            return {"ok": False, "error": "Enter the password: the saved one is only used for the server and user it belongs to"}
        c["password"] = settings()["password"]
    try:
        raw = _open(c)
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


def ensure_database() -> None:
    """Create the database when it is missing and the user may (CREATE privilege); otherwise leave it to the admin."""
    c = settings()
    try:
        _open(c).close()
        return
    except pymysql.err.OperationalError as e:
        if e.args[0] != 1049:  # anything but "unknown database"
            raise
    con = _open(c, database=False)
    try:
        with con.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{c['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        con.close()


def init():
    """Create the database and the tables that are missing (idempotent). Called at start and by the first connect()."""
    global _ready, error
    with _lock:
        if _ready:
            return
        ensure_database()
        with _db.tx() as con, con.cursor() as cur:
            for stmt in SCHEMA:
                cur.execute(stmt + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
            cur.execute("INSERT IGNORE INTO nts_settings (name, value) VALUES ('write_lock', '')")  # tx()
            schema.ensure_version_table(cur, PREFIX)
            schema.record_version(cur, PREFIX, SCHEMA_VERSION)
        error = None
        _ready = True


# ---- settings table
def get_setting(key: str, default: str = None):
    with connect() as con:
        r = con.execute("SELECT value FROM nts_settings WHERE name = %s", (key,)).fetchone()
    return r[0] if r else default


def set_setting(key: str, value):
    with tx() as con:
        con.execute("REPLACE INTO nts_settings (name, value, updated_at) VALUES (%s, %s, UTC_TIMESTAMP(3))",
                    (key, None if value is None else str(value)))


def next_rev(con: Conn) -> int:
    """A new change number, inside the caller's transaction."""
    return con.execute("INSERT INTO nts_change_counter (created_at) VALUES (%s)", (int(time.time()),)).lastrowid


def current_rev() -> int:
    with connect() as con:
        r = con.execute("SELECT max(rev) FROM nts_change_counter").fetchone()
    return int(r[0] or 0)
