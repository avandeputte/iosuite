"""The viewer's own database: SQLite (data/viewer.db, the default) or MySQL/MariaDB.

Every module that keeps viewer data (state, users, edits, tagmanager, analysis, consistency)
gets its connection here. The wrapper translates the SQLite dialect the code is written in
(? placeholders, INSERT OR REPLACE / OR IGNORE, COLLATE NOCASE, the `key` column) and hands
back rows that answer to both an index and a column name, so the same code runs on both.

Where the connection goes is kept outside the database itself, in data/viewer-db.json
(or VIEWER_DB_* in the environment), since the settings table lives inside. Switching is
done from Settings: the target is tested, the tables are (re)created there, every row is
copied, the file is written, and the viewer restarts on the new database.
"""
import json
import logging
import os
import re
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

from . import config
from .dkdb import Conn, _Cursor, _norm_value

log = logging.getLogger("app.vdb")
CONF = config.DATA_DIR / "viewer-db.json"
SQLITE_FILE = config.DATA_DIR / "viewer.db"
KEYS = ("type", "host", "port", "database", "user", "password")
_cfg = None
_lock = threading.Lock()
error = None  # why the configured database could not be used (then SQLite is used instead)
_KEY_COL = re.compile(r"(?<![\w`.])key(?![\w`(])")  # the settings column, a reserved word on MySQL

try:
    import pymysql
    Error = (sqlite3.Error, pymysql.err.Error)
except ImportError:  # pragma: no cover
    pymysql = None
    Error = (sqlite3.Error,)

# ---- schema: one definition per table, the SQLite and the MySQL spelling; columns in copy order
TABLES = {
    "settings": (["key", "value"],
                 "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)",
                 "CREATE TABLE IF NOT EXISTS settings (`key` VARCHAR(191) PRIMARY KEY, value MEDIUMTEXT)"),
    "users": (["id", "name", "hash", "role", "settings", "created", "last_login", "person", "email"],
              "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL COLLATE NOCASE, hash TEXT NOT NULL, "
              "role TEXT NOT NULL, settings TEXT NOT NULL DEFAULT '{}', created INTEGER, last_login INTEGER, person INTEGER, email TEXT)",
              "CREATE TABLE IF NOT EXISTS users (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(191) NOT NULL UNIQUE, hash TEXT NOT NULL, "
              "role VARCHAR(32) NOT NULL, settings MEDIUMTEXT NOT NULL DEFAULT ('{}'), created BIGINT, last_login BIGINT, person INT, email VARCHAR(191))"),
    "favorites": (["photo_id", "hash", "added"],
                  "CREATE TABLE IF NOT EXISTS favorites (photo_id INTEGER PRIMARY KEY, hash TEXT, added INTEGER)",
                  "CREATE TABLE IF NOT EXISTS favorites (photo_id BIGINT PRIMARY KEY, hash VARCHAR(64), added BIGINT)"),
    "ualbums": (["id", "name", "created"],
                "CREATE TABLE IF NOT EXISTS ualbums (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created INTEGER)",
                "CREATE TABLE IF NOT EXISTS ualbums (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL, created BIGINT)"),
    "ualbum_items": (["album_id", "photo_id", "hash", "added"],
                     "CREATE TABLE IF NOT EXISTS ualbum_items (album_id INTEGER, photo_id INTEGER, hash TEXT, added INTEGER, PRIMARY KEY (album_id, photo_id))",
                     "CREATE TABLE IF NOT EXISTS ualbum_items (album_id INT, photo_id BIGINT, hash VARCHAR(64), added BIGINT, PRIMARY KEY (album_id, photo_id))"),
    "searches": (["id", "name", "query", "created"],
                 "CREATE TABLE IF NOT EXISTS searches (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, query TEXT NOT NULL, created INTEGER)",
                 "CREATE TABLE IF NOT EXISTS searches (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(255) NOT NULL, query TEXT NOT NULL, created BIGINT)"),
    "edits": (["photo_id", "data", "ts"],
              "CREATE TABLE IF NOT EXISTS edits (photo_id INTEGER PRIMARY KEY, data TEXT, ts INTEGER)",
              "CREATE TABLE IF NOT EXISTS edits (photo_id BIGINT PRIMARY KEY, data MEDIUMTEXT, ts BIGINT)"),
    "tagjobs": (["id", "op", "path", "image_id"],
                "CREATE TABLE IF NOT EXISTS tagjobs (id INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT, path TEXT, image_id INTEGER)",
                "CREATE TABLE IF NOT EXISTS tagjobs (id INT AUTO_INCREMENT PRIMARY KEY, op VARCHAR(64), path TEXT, image_id BIGINT)"),
    "quality": (["photo_id", "stamp", "sharp", "bright", "clip_lo", "clip_hi"],
                "CREATE TABLE IF NOT EXISTS quality (photo_id INTEGER PRIMARY KEY, stamp TEXT, sharp REAL, bright REAL, clip_lo REAL, clip_hi REAL)",
                "CREATE TABLE IF NOT EXISTS quality (photo_id BIGINT PRIMARY KEY, stamp VARCHAR(191), sharp DOUBLE, bright DOUBLE, clip_lo DOUBLE, clip_hi DOUBLE)"),
    "vision": (["photo_id", "stamp", "text", "nfaces", "faceq"],
               "CREATE TABLE IF NOT EXISTS vision (photo_id INTEGER PRIMARY KEY, stamp TEXT, text TEXT, nfaces INTEGER, faceq REAL)",
               "CREATE TABLE IF NOT EXISTS vision (photo_id BIGINT PRIMARY KEY, stamp VARCHAR(191), text MEDIUMTEXT, nfaces INT, faceq DOUBLE)"),
    "objects": (["photo_id", "cls", "score", "x", "y", "w", "h"],
                "CREATE TABLE IF NOT EXISTS objects (photo_id INTEGER, cls TEXT, score REAL, x REAL, y REAL, w REAL, h REAL)",
                "CREATE TABLE IF NOT EXISTS objects (photo_id BIGINT, cls VARCHAR(64), score DOUBLE, x DOUBLE, y DOUBLE, w DOUBLE, h DOUBLE, INDEX objects_photo (photo_id))"),
    "objects_done": (["photo_id", "stamp"],
                     "CREATE TABLE IF NOT EXISTS objects_done (photo_id INTEGER PRIMARY KEY, stamp TEXT)",
                     "CREATE TABLE IF NOT EXISTS objects_done (photo_id BIGINT PRIMARY KEY, stamp VARCHAR(191))"),
    "captions": (["photo_id", "stamp", "text"],
                 "CREATE TABLE IF NOT EXISTS captions (photo_id INTEGER PRIMARY KEY, stamp TEXT, text TEXT)",
                 "CREATE TABLE IF NOT EXISTS captions (photo_id BIGINT PRIMARY KEY, stamp VARCHAR(191), text MEDIUMTEXT)"),
    "face_vecs": (["photo_id", "x", "y", "w", "h", "vec"],
                  "CREATE TABLE IF NOT EXISTS face_vecs (photo_id INTEGER, x INTEGER, y INTEGER, w INTEGER, h INTEGER, vec BLOB, PRIMARY KEY (photo_id, x, y, w, h))",
                  "CREATE TABLE IF NOT EXISTS face_vecs (photo_id BIGINT, x INT, y INT, w INT, h INT, vec BLOB, PRIMARY KEY (photo_id, x, y, w, h))"),
    "face_protos": (["tag_id", "photo_id", "x", "y", "w", "h", "vec"],
                    "CREATE TABLE IF NOT EXISTS face_protos (tag_id INTEGER, photo_id INTEGER, x INTEGER, y INTEGER, w INTEGER, h INTEGER, vec BLOB, PRIMARY KEY (photo_id, x, y, w, h))",
                    "CREATE TABLE IF NOT EXISTS face_protos (tag_id BIGINT, photo_id BIGINT, x INT, y INT, w INT, h INT, vec BLOB, PRIMARY KEY (photo_id, x, y, w, h))"),
    "near_dups": (["a", "b", "score"],
                  "CREATE TABLE IF NOT EXISTS near_dups (a INTEGER, b INTEGER, score REAL)",
                  "CREATE TABLE IF NOT EXISTS near_dups (a BIGINT, b BIGINT, score DOUBLE, INDEX near_dups_a (a))"),
    "consistency": (["photo_id", "stamp", "data", "mismatch", "has_sidecar", "file_xmp", "checked"],
                    "CREATE TABLE IF NOT EXISTS consistency (photo_id INTEGER PRIMARY KEY, stamp TEXT, data TEXT, mismatch INTEGER, has_sidecar INTEGER, file_xmp INTEGER, checked INTEGER)",
                    "CREATE TABLE IF NOT EXISTS consistency (photo_id BIGINT PRIMARY KEY, stamp VARCHAR(191), data MEDIUMTEXT, mismatch INT, has_sidecar INT, file_xmp INT, checked BIGINT)"),
}
SQLITE_INDEXES = ["CREATE INDEX IF NOT EXISTS objects_photo ON objects (photo_id)", "CREATE INDEX IF NOT EXISTS near_dups_a ON near_dups (a)"]


# ---- configuration
def settings() -> dict:
    """{type, host, port, database, user, password}: the file, else the environment, else SQLite."""
    global _cfg
    if _cfg is None:
        c = {"type": "sqlite", "host": "", "port": 3306, "database": "digikam_viewer", "user": "", "password": ""}
        try:
            c.update({k: v for k, v in json.loads(CONF.read_text()).items() if k in KEYS})
        except (OSError, ValueError):
            pass
        for k in KEYS:
            v = os.environ.get("VIEWER_DB_" + k.upper())
            if v:
                c[k] = v
        c["port"] = int(c.get("port") or 3306)
        c["type"] = "mysql" if str(c.get("type")).lower() in ("mysql", "mariadb") else "sqlite"
        _cfg = c
    return dict(_cfg)


def public_settings() -> dict:
    c = settings()
    return {**{k: v for k, v in c.items() if k != "password"}, "password_set": bool(c["password"]), "error": error, "sqlite_file": str(SQLITE_FILE)}


def save_settings(c: dict):
    """Write the file and use it from now on (callers switch the data first)."""
    global _cfg
    keep = {k: c.get(k, "") for k in KEYS}
    keep["port"] = int(keep.get("port") or 3306)
    CONF.parent.mkdir(parents=True, exist_ok=True)
    CONF.write_text(json.dumps(keep, indent=1))
    try:
        os.chmod(CONF, 0o600)
    except OSError:
        pass
    _cfg = None
    settings()


def is_mysql() -> bool:
    return settings()["type"] == "mysql" and error is None


def describe() -> str:
    c = settings()
    if is_mysql():
        return f"MySQL {c['user']}@{c['host']}:{c['port']}/{c['database']}"
    return f"SQLite {SQLITE_FILE.name}" + (f" (fallback: {error})" if error else "")


def exists() -> bool:
    """Whether there is a database to read at all (SQLite: the file; MySQL: assumed, connect decides)."""
    return is_mysql() or SQLITE_FILE.exists()


# ---- connections
class _Row(tuple):
    """A tuple that also answers to column names (what sqlite3.Row gives us on SQLite)."""
    __slots__ = ()
    _keys = ()

    def __getitem__(self, k):
        if isinstance(k, str):
            return tuple.__getitem__(self, self._keys.index(k))
        return tuple.__getitem__(self, k)

    def keys(self):
        return list(self._keys)


@lru_cache(maxsize=256)
def _row_class(keys: tuple):
    """One row class per column list (the same few queries run again and again)."""
    return type("Row", (_Row,), {"__slots__": (), "_keys": keys})


class _VCursor(_Cursor):
    def __init__(self, cur, mysql: bool):
        super().__init__(cur, mysql)
        desc = getattr(cur, "description", None)
        self._cls = _row_class(tuple(d[0] for d in desc)) if mysql and desc else tuple

    def _fix(self, row):
        if row is None or not self._mysql:
            return row
        return self._cls(_norm_value(v) for v in row)


class VConn(Conn):
    """The dialect bridge for the viewer's own SQL (written for SQLite)."""

    def _sql(self, sql: str) -> str:
        if not self.mysql:
            return sql
        sql = super()._sql(sql).replace(" COLLATE NOCASE", "")
        return _KEY_COL.sub("`key`", sql)

    def _params(self, params):  # text stamps stay text: no datetime coercion here
        return tuple(params)

    def execute(self, sql: str, params=()):
        if self.mysql:
            cur = self.raw.cursor()
            cur.execute(self._sql(sql), self._params(params))
            return _VCursor(cur, True)
        return _VCursor(self.raw.execute(sql, params), False)

    def executemany(self, sql: str, rows):
        if self.mysql:
            cur = self.raw.cursor()
            rows = [self._params(r) for r in rows]
            if rows:
                cur.executemany(self._sql(sql), rows)
            return _VCursor(cur, True)
        return _VCursor(self.raw.executemany(sql, rows), False)

    def executescript(self, script: str):
        if self.mysql:
            for stmt in script.split(";"):
                if stmt.strip():
                    self.execute(stmt)
        else:
            self.raw.executescript(script)


def _mysql_raw(c: dict):
    if pymysql is None:
        raise RuntimeError("MySQL support needs the PyMySQL package (pip install pymysql)")
    return pymysql.connect(host=c["host"], port=int(c["port"]), database=c["database"], user=c["user"], password=c["password"],
                           charset="utf8mb4", autocommit=False, connect_timeout=8, read_timeout=120, write_timeout=120)


def _sqlite_raw(path: Path, timeout: float):
    raw = sqlite3.connect(path, timeout=timeout)
    raw.row_factory = sqlite3.Row
    return raw


def connect(timeout: float = 10, cfg: dict = None) -> VConn:
    """The configured viewer database (or a given configuration, for tests and switching)."""
    c = cfg or settings()
    if c["type"] == "mysql" and (cfg is not None or error is None):
        return VConn(_mysql_raw(c), True, True)
    return VConn(_sqlite_raw(SQLITE_FILE, timeout), False, True)


def columns(con: VConn, table: str) -> list:
    if con.mysql:
        return [r[0] for r in con.execute(f"SHOW COLUMNS FROM `{table}`")]
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]


def ensure_schema(con: VConn = None):
    """Every table, idempotently; SQLite gets WAL and the two column additions older files lack."""
    own = con is None
    con = con or connect()
    try:
        if not con.mysql:
            con.execute("PRAGMA journal_mode = WAL")
            cols = columns(con, "tagjobs")
            if cols and "image_id" not in cols:  # an early schema whose rows cannot be replayed
                con.execute("DROP TABLE tagjobs")
        for name, (cols, sq, my) in TABLES.items():
            con.execute(my if con.mysql else sq)
        if not con.mysql:  # MySQL declares its index in the CREATE TABLE and never had the older schema
            for sql in SQLITE_INDEXES:
                con.execute(sql)
            have = columns(con, "users")
            if "person" not in have:
                con.execute("ALTER TABLE users ADD COLUMN person INTEGER")
            if "email" not in have:
                con.execute("ALTER TABLE users ADD COLUMN email TEXT")
        con.commit()
    finally:
        if own:
            con.close()


def init():
    """Called once at start: use the configured database, or fall back to SQLite with a recorded reason."""
    global error
    error = None
    c = settings()
    if c["type"] == "mysql":
        try:
            con = connect(cfg=c)
            try:
                ensure_schema(con)
            finally:
                con.close()
            return
        except Exception as e:  # the server is down, the password changed...: the viewer must still start
            error = f"{type(e).__name__}: {str(e)[:160]}"
            log.error("viewer database on MySQL unavailable (%s); using the SQLite file instead", error)
    ensure_schema()


# ---- testing, copying, switching
def test_connection(c: dict) -> dict:
    """Connect with the given settings (an empty password keeps the stored one) and count what is there."""
    c = {**settings(), **{k: v for k, v in c.items() if k in KEYS and v not in (None, "")}}
    c["type"] = "mysql" if str(c["type"]).lower() in ("mysql", "mariadb") else "sqlite"
    con = connect(cfg=c)
    try:
        if con.mysql:
            ver = con.execute("SELECT VERSION()").fetchone()[0]
            have = {r[0] for r in con.execute("SHOW TABLES")}
        else:
            ver = "SQLite " + sqlite3.sqlite_version
            have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        counts = {}
        for t in TABLES:
            if t in have:
                counts[t] = con.execute(f"SELECT count(*) FROM `{t}`" if con.mysql else f"SELECT count(*) FROM {t}").fetchone()[0]
        return {"ok": True, "version": ver, "tables": counts, "existing": sorted(have & set(TABLES))}
    finally:
        con.close()


def copy_all(src: VConn, dst: VConn, drop: bool = True, progress=None) -> dict:
    """Every table, row by row, ids kept. drop: DROP the viewer tables at the target first (so a
    re-run or a stale copy never leaves rows behind); else existing rows are replaced by id."""
    counts = {}
    q = (lambda t: f"`{t}`") if dst.mysql else (lambda t: t)
    qs = (lambda t: f"`{t}`") if src.mysql else (lambda t: t)
    for name, (cols, sq, my) in TABLES.items():  # the whole schema first, then the rows
        if drop:
            dst.execute(f"DROP TABLE IF EXISTS {q(name)}")
        dst.execute(my if dst.mysql else sq)
    if not dst.mysql:
        for sql in SQLITE_INDEXES:
            dst.execute(sql)
    dst.commit()
    for name, (cols, sq, my) in TABLES.items():
        present = ({r[0] for r in src.execute("SHOW TABLES")} if src.mysql
                   else {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type = 'table'")})
        have = columns(src, name) if name in present else []  # a table the source never had (hand-made schema) copies nothing
        if not have:
            counts[name] = 0
            dst.commit()
            continue
        use = [c for c in cols if c in have]
        collist = ", ".join(("`key`" if c == "key" and dst.mysql else c) for c in use)
        sel = ", ".join(("`key`" if c == "key" and src.mysql else c) for c in use)
        rows = src.execute(f"SELECT {sel} FROM {qs(name)}").fetchall()
        for i in range(0, len(rows), 2000):
            dst.executemany(f"INSERT OR REPLACE INTO {q(name)} ({collist}) VALUES ({','.join('?' * len(use))})", [tuple(r) for r in rows[i:i + 2000]])
        dst.commit()
        counts[name] = len(rows)
        if progress:
            progress(name, len(rows))
    return counts


def switch(c: dict, copy: bool = True, drop: bool = True) -> dict:
    """Move the viewer to the given database: test it, (re)create the tables there, copy the data from
    the current one, save the configuration. The caller restarts the viewer afterwards."""
    cur = settings()
    c = {**cur, **{k: v for k, v in c.items() if k in KEYS and v not in (None, "")}}
    c["type"] = "mysql" if str(c["type"]).lower() in ("mysql", "mariadb") else "sqlite"
    if c["type"] == "sqlite":
        if cur["type"] == "sqlite":
            raise ValueError("The viewer already uses the SQLite file")
        if error is not None:  # the configured MySQL is unreachable: the viewer already runs on the
            with _lock:        # SQLite file, so there is nothing to copy; only the configuration changes
                save_settings(c)
            return {"ok": True, "copied": {}, "database": describe()}
    elif is_mysql() and all(str(c[k]) == str(cur[k]) for k in ("host", "port", "database")):
        # copying a database onto itself would drop every table and then copy from the empty result
        raise ValueError("The viewer already uses that MySQL database")
    counts = {}
    with _lock:
        dst = connect(cfg=c)
        try:
            if copy:
                src = connect()
                try:
                    counts = copy_all(src, dst, drop=drop)
                finally:
                    src.close()
            else:
                ensure_schema(dst)
        finally:
            dst.close()
        save_settings(c)
    return {"ok": True, "copied": counts, "database": describe()}


def snapshot_sqlite(dst_path: Path):
    """A SQLite copy of the current viewer database, whatever it runs on (the portable backup form)."""
    dst_path.unlink(missing_ok=True)
    if not is_mysql():
        src = sqlite3.connect(f"file:{SQLITE_FILE}?mode=ro", uri=True)
        try:
            out = sqlite3.connect(str(dst_path))
            try:
                src.backup(out)
            finally:
                out.close()
        finally:
            src.close()
        return
    src = connect()
    try:
        dst = VConn(_sqlite_raw(dst_path, 10), False, True)
        try:
            copy_all(src, dst, drop=True)
        finally:
            dst.close()
    finally:
        src.close()
