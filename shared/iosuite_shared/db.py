"""The Shared ioSuite database: connections, the schema, and the suite-wide / per-app settings table.

Connections come from a small pool (Pool), in autocommit mode: a statement on its own (q, one, ex) is one round trip,
and a unit of work (tx) begins a transaction, commits or rolls back, and gives the connection back. A PyMySQL
connection is never used by two threads at once. Rows come back as dicts. The apps use Database (the pool, the
transaction and q / one / ex / many) for their own databases too.
"""
import json
import logging
import queue
import select
import threading
import time
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from iosuite_shared import config, schema

log = logging.getLogger("iosuite_shared.db")

SCHEMA_VERSION = 8  # 4: the suite naming convention (ios_ tables, *_at times, name/value, named indexes); 5: ios_apps.admin_tool;
# 6: the member role (between viewer and editor); the viewers of before, who kept their own things, became members;
# 7: ios_updates (updating the apps from one place); 8: ioNotes, ioTasks and ioContacts became ioNote, ioTask, ioContact
PREFIX = "ios"
OPTIONS = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"

# Every table is ios_<name>, so the shared tables can sit in the same database as the apps' own (each app has its
# own three-letter prefix). Times are seconds since 1970 (UTC).
SCHEMA = [
    # one account for the whole suite. hash '' is a passwordless account: one-click sign-in on the LAN, member at most.
    # session_gen is read by nothing; the column stays while an app on iosuite-shared before 0.34 may still select it.
    """CREATE TABLE IF NOT EXISTS ios_users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        display_name VARCHAR(128) NULL,
        email VARCHAR(191) NULL,
        hash VARCHAR(255) NOT NULL DEFAULT '',
        suite_admin TINYINT NOT NULL DEFAULT 0,
        listed TINYINT NOT NULL DEFAULT 1,
        created_at BIGINT NOT NULL,
        last_login_at BIGINT NULL,
        session_gen INT NOT NULL DEFAULT 0,
        service VARCHAR(32) NULL,
        UNIQUE KEY uq_ios_users_name (name),
        UNIQUE KEY uq_ios_users_email (email)
    )""",
    # the role an account holds in one app; no row: the app's default_role setting (member unless changed)
    """CREATE TABLE IF NOT EXISTS ios_user_roles (
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        role ENUM('none','viewer','member','editor','admin') NOT NULL,
        PRIMARY KEY (user_id, app),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # per-user, per-app values (display settings, the ioPix person tag, the ioContact "me" contact), JSON-encoded
    """CREATE TABLE IF NOT EXISTS ios_user_data (
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        value MEDIUMTEXT NOT NULL,
        PRIMARY KEY (user_id, app, name),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # a browser or app session: the cookie carries a random token, the table its hash. Shared by every app on the
    # domain. Where it began and was last seen: the visitor's address (the real one, through Cloudflare or a trusted
    # proxy), whether it came through Cloudflare, the client (web, or the app's User-Agent product) and the full User-Agent.
    """CREATE TABLE IF NOT EXISTS ios_sessions (
        token_hash CHAR(64) PRIMARY KEY,
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        via VARCHAR(16) NOT NULL,
        created_at BIGINT NOT NULL,
        expires_at BIGINT NOT NULL,
        renewed_at BIGINT NOT NULL,
        ip VARCHAR(64) NULL,
        cloudflare TINYINT NOT NULL DEFAULT 0,
        client VARCHAR(32) NOT NULL DEFAULT '',
        user_agent VARCHAR(255) NULL,
        last_seen_at BIGINT NULL,
        last_ip VARCHAR(64) NULL,
        INDEX idx_ios_sessions_user (user_id),
        INDEX idx_ios_sessions_expires (expires_at),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # app passwords: one per device, for one app (CardDAV, LDAP, MCP clients...); shown once, revocable
    """CREATE TABLE IF NOT EXISTS ios_app_passwords (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT NOT NULL,
        app VARCHAR(32) NOT NULL,
        label VARCHAR(128) NOT NULL,
        prefix CHAR(8) NOT NULL,
        hash VARCHAR(255) NOT NULL,
        created_at BIGINT NOT NULL,
        last_used_at BIGINT NULL,
        scope VARCHAR(32) NOT NULL DEFAULT '',
        INDEX idx_ios_app_passwords_prefix (prefix),
        INDEX idx_ios_app_passwords_user (user_id),
        FOREIGN KEY (user_id) REFERENCES ios_users(id) ON DELETE CASCADE
    )""",
    # suite-wide (app '') and per-app settings: proxy sign-in, require_login, default_role
    """CREATE TABLE IF NOT EXISTS ios_settings (
        app VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        value MEDIUMTEXT NOT NULL,
        PRIMARY KEY (app, name)
    )""",
    # keys and tokens: every credential an app keeps (an integration's API key, the sign-in one app uses to reach
    # another), one row per key the app declares; value '' while none is set (iosuite_shared.credentials)
    """CREATE TABLE IF NOT EXISTS ios_credentials (
        app VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        value MEDIUMTEXT NOT NULL,
        label VARCHAR(128) NOT NULL,
        hint VARCHAR(255) NOT NULL DEFAULT '',
        env VARCHAR(64) NOT NULL DEFAULT '',
        env_set TINYINT NOT NULL DEFAULT 0,
        updated_at BIGINT NULL,
        updated_by VARCHAR(64) NULL,
        PRIMARY KEY (app, name)
    )""",
    # the suite's apps, each written by the app itself when it starts (iosuite_shared.suite): what it is called, its
    # version, and where it is (the address its configuration names, else the best one it was reached at; and inside the
    # network: its LAN address and port), so the start
    # page and the others link to it without anybody typing an address
    """CREATE TABLE IF NOT EXISTS ios_apps (
        app VARCHAR(32) PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        description VARCHAR(255) NULL,
        version VARCHAR(32) NULL,
        color VARCHAR(16) NULL,
        icon VARCHAR(512) NULL,
        configured_url VARCHAR(512) NULL,
        seen_url VARCHAR(512) NULL,
        internal_url VARCHAR(512) NULL,
        admin_tool TINYINT NOT NULL DEFAULT 0,
        created_at BIGINT NOT NULL,
        updated_at BIGINT NOT NULL,
        last_seen_at BIGINT NULL
    )""",
    # updating the apps from one place (iosuite_shared.suiteupdates): a suite admin leaves an action for an app, the
    # app takes it off and runs it, and writes back what it knows about its own version and its last update
    """CREATE TABLE IF NOT EXISTS ios_updates (
        app VARCHAR(32) PRIMARY KEY,
        action VARCHAR(16) NULL,
        requested_at BIGINT NULL,
        requested_by VARCHAR(64) NULL,
        installed VARCHAR(32) NULL,
        git_commit VARCHAR(40) NULL,
        latest VARCHAR(32) NULL,
        status VARCHAR(16) NULL,
        checked_at BIGINT NULL,
        can_run TINYINT NOT NULL DEFAULT 0,
        docker TINYINT NOT NULL DEFAULT 0,
        state VARCHAR(16) NULL,
        message VARCHAR(300) NULL,
        updated_at BIGINT NOT NULL
    )""",
]

_overrides: dict = {}  # the tests point the library at another database


def configure(**values):
    """Override host, port, database, user, password (the tests; an app that keeps its own configuration)."""
    global _ready
    _overrides.update({k: v for k, v in values.items() if v is not None})
    settings_cache.clear()
    _pool.drain()  # the kept connections point at the old database
    _ready = False  # another database: its tables are checked again


def params() -> dict:
    p = {"host": config.DB_HOST, "port": config.DB_PORT, "database": config.DB_NAME, "user": config.DB_USER, "password": config.DB_PASSWORD}
    p.update(_overrides)
    return p


def connect(database: str | None = ...):
    p = params()
    return pymysql.connect(host=p["host"], port=int(p["port"]), user=p["user"], password=p["password"],
                           database=p["database"] if database is ... else database, charset="utf8mb4",
                           cursorclass=DictCursor, autocommit=True, connect_timeout=8, read_timeout=60, write_timeout=60)


BROKEN = (pymysql.err.OperationalError, pymysql.err.InterfaceError)  # the connection itself failed: it is closed, not kept


class Pool:
    """A few open connections, reused: `connect` makes a new one, `size` is how many are kept. A connection that sat
    unused for more than IDLE_S is pinged before it is lent again (and replaced when the server dropped it); one that
    was in use a moment ago is only looked at (_open: no round trip), so a query is one round trip to the server and
    not three. A connection
    that failed inside a unit of work is closed, and so are the kept ones (the server went away: they are gone too).
    Thread-safe: a connection is in one thread's hands at a time.

    `connect` should open connections in autocommit mode: `auto()` then runs a statement with nothing around it, and
    `tx()` begins and commits its own transaction. Connections with autocommit off work as well (both commit at the end)."""

    IDLE_S = 30.0

    def __init__(self, connect, size: int = 8):
        self._connect, self._kept = connect, queue.LifoQueue(maxsize=size)

    def borrow(self):
        try:
            con, at = self._kept.get_nowait()
        except queue.Empty:
            return self._connect()
        try:
            if time.monotonic() - at >= self.IDLE_S:
                con.ping(reconnect=False)
            elif not _open(con):
                raise pymysql.err.InterfaceError(0, "closed")
            return con
        except pymysql.MySQLError:
            _close(con)
            return self._connect()

    def give_back(self, con, broken: bool = False):
        if broken:
            _close(con)
            self.drain()
            return
        try:
            self._kept.put_nowait((con, time.monotonic()))
        except queue.Full:
            _close(con)

    def drain(self):
        """Close every kept connection (the database changed; shutdown)."""
        while True:
            try:
                _close(self._kept.get_nowait()[0])
            except queue.Empty:
                return

    @contextmanager
    def _lend(self, transaction: bool):
        con = self.borrow()
        broken, commits = False, False
        try:
            commits = not con.get_autocommit()
            if transaction and not commits:
                con.begin()
                commits = True
            yield con
            if commits:
                con.commit()
        except BaseException as e:
            broken = isinstance(e, BROKEN)
            try:
                if not broken and commits:
                    con.rollback()
            except pymysql.MySQLError:
                broken = True
            raise
        finally:
            self.give_back(con, broken)

    def tx(self):
        """A connection whose work is one transaction: committed at the end of the block, rolled back on an exception."""
        return self._lend(True)

    def auto(self):
        """A connection for statements that each stand on their own (a read, one insert): no transaction is begun."""
        return self._lend(False)


class Database:
    """One database as an app uses it: a Pool, a transaction that nested calls on the same thread share, and the
    helpers q / one / ex / many, which run inside the thread's open transaction when there is one and on their own
    otherwise. The apps keep one for their own database (`_db = Database(connect)`; `tx, q, one, ex = _db.tx, ...`)."""

    def __init__(self, connect, size: int = 8):
        self.pool = Pool(connect, size)
        self._local = threading.local()

    @contextmanager
    def tx(self):
        """One transaction: committed on success, rolled back on an exception. Nested calls share it."""
        con = getattr(self._local, "con", None)
        if con is not None:
            yield con
            return
        with self.pool.tx() as con:
            self._local.con = con
            try:
                yield con
            finally:
                self._local.con = None

    @contextmanager
    def cursor(self, kind=None):
        """A cursor for one statement: in the thread's open transaction, else on a connection of its own. `kind`: a
        PyMySQL cursor class other than the connection's (DictCursor on a connection that gives tuples)."""
        con = getattr(self._local, "con", None)
        if con is not None:
            with con.cursor(kind) as cur:
                yield cur
            return
        with self.pool.auto() as con, con.cursor(kind) as cur:
            yield cur

    def q(self, sql: str, args=None, kind=None) -> list:
        with self.cursor(kind) as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())

    def one(self, sql: str, args=None):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    def ex(self, sql: str, args=None) -> int:
        """Run one statement; returns lastrowid (inserts) or the affected row count."""
        with self.cursor() as cur:
            n = cur.execute(sql, args)
            return cur.lastrowid or n

    def many(self, sql: str, rows: list) -> None:
        if rows:
            with self.tx() as con, con.cursor() as cur:
                cur.executemany(sql, rows)


def _open(con) -> bool:
    """Whether a kept connection still looks usable, without asking the server: it was not closed here, and nothing
    waits to be read on its socket (a server that closed the connection, or went away, leaves an end-of-file there)."""
    if not con.open:
        return False
    sock = getattr(con, "_sock", None)
    try:
        return sock is None or not select.select([sock], [], [], 0)[0]
    except (OSError, ValueError):
        return False


def _close(con):
    try:
        con.close()
    except Exception:  # noqa: BLE001 - already gone
        pass


_db = Database(connect)
_pool = _db.pool



def tx():
    """A pooled connection whose work is one transaction: committed at the end of the block, rolled back on an
    exception. Nested calls on the same thread share it, and so do q / one / ex inside the block."""
    return _db.tx()


q, one, ex = _db.q, _db.one, _db.ex


_ready = False
error = None  # why the database could not be opened at start (None once it could)
_init_lock = threading.Lock()
_retry_at = 0.0


def init():
    """Create the database if the account may, then every table (idempotent)."""
    global _ready
    with _init_lock:
        if _ready:
            return
        p = params()
        try:
            con = connect(database=None)
            try:
                with con.cursor() as cur:
                    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{p['database']}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                con.commit()
            finally:
                con.close()
        except pymysql.MySQLError:
            pass  # no right to create databases: it has to exist already
        with tx() as con:
            with con.cursor() as cur:
                for stmt in SCHEMA:
                    cur.execute(stmt + OPTIONS)
                if "admin_tool" not in schema.columns(cur, "ios_apps"):  # 5: an app may be an admin tool
                    cur.execute("ALTER TABLE ios_apps ADD COLUMN admin_tool TINYINT NOT NULL DEFAULT 0 AFTER internal_url")
                schema.ensure_version_table(cur, PREFIX)
                if schema.current_version(cur, PREFIX) < 6:
                    _members(cur)
                if schema.current_version(cur, PREFIX) < 8:
                    _renamed(cur)
                schema.record_version(cur, PREFIX, SCHEMA_VERSION)
        _ready = True


def _members(cur):
    """6: the member role. A viewer used to keep their own things (calendars, lists, address books); that is a member
    now and a viewer is read-only, so the people who were viewers become members (the apps' own service accounts stay
    viewers: they only read), and an app whose default was viewer gets the new default, member."""
    cur.execute("ALTER TABLE ios_user_roles MODIFY role ENUM('none','viewer','member','editor','admin') NOT NULL")
    cur.execute("UPDATE ios_user_roles r JOIN ios_users u ON u.id = r.user_id SET r.role = 'member' "
                "WHERE r.role = 'viewer' AND u.service IS NULL")
    cur.execute("DELETE FROM ios_settings WHERE name = 'default_role' AND value = 'viewer'")


# 8: the apps' ids before and after the suite's names became singular
RENAMED = {"ionotes": "ionote", "iotasks": "iotask", "iocontacts": "iocontact"}
_APP_TABLES = ("ios_user_roles", "ios_user_data", "ios_sessions", "ios_app_passwords", "ios_settings", "ios_credentials",
               "ios_apps", "ios_updates")


def _renamed(cur):
    """8: ioNotes, ioTasks and ioContacts are ioNote, ioTask and ioContact, so every row kept under the old app id
    moves to the new one (roles, sessions, app passwords, settings, the list of apps...), and so do the apps' own
    service accounts (<app>-app). A row the renamed app already wrote under its new id wins over the old one."""
    for old, new in RENAMED.items():
        for t in _APP_TABLES:
            cur.execute(f"UPDATE IGNORE {t} SET app = %s WHERE app = %s", (new, old))
            cur.execute(f"DELETE FROM {t} WHERE app = %s", (old,))
        cur.execute("UPDATE IGNORE ios_users SET name = %s, display_name = %s WHERE service = %s AND name = %s",
                    (new + "-app", f"{new} (automatic)", old, old + "-app"))
        cur.execute("UPDATE ios_users SET service = %s WHERE service = %s", (new, old))


def ready() -> bool:
    return _ready


def available() -> bool:
    """Whether the database can be used; when the start failed, another try at most every 10 seconds."""
    global _retry_at
    if _ready:
        return True
    if time.time() < _retry_at:
        return False
    _retry_at = time.time() + 10
    from iosuite_shared import users
    return users.init()


# ---- settings: suite-wide (app '') with a per-app override
settings_cache: dict = {}  # (app, key) -> (value, at)
CACHE_S = 5.0


def get_setting(key: str, default: str = "", app: str = "") -> str:
    """The setting for this app, else the suite-wide one, else default. Cached a few seconds: asked on every request."""
    now = time.time()
    hit = settings_cache.get((app, key))
    if hit and now - hit[1] < CACHE_S:
        return hit[0] if hit[0] is not None else default
    v = None
    rows = q("SELECT app, value FROM ios_settings WHERE name = %s AND app IN (%s, '')", (key, app))
    by_app = {r["app"]: r["value"] for r in rows}
    if app in by_app:
        v = by_app[app]
    elif "" in by_app:
        v = by_app[""]
    settings_cache[(app, key)] = (v, now)
    return v if v is not None else default


def set_setting(key: str, value, app: str = ""):
    """Store (or, with None / '', remove) a setting for the app ('' : suite-wide)."""
    if value is None or str(value) == "":
        ex("DELETE FROM ios_settings WHERE app = %s AND name = %s", (app, key))
    else:
        ex("INSERT INTO ios_settings (app, name, value) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (app, key, str(value)))
    settings_cache.clear()


def settings_of(app: str = "") -> dict:
    """Every setting stored for exactly this app (no fallback), for Settings screens."""
    return {r["name"]: r["value"] for r in q("SELECT name, value FROM ios_settings WHERE app = %s", (app,))}


def json_load(s, default=None):
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default
