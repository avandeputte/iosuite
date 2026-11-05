"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start).

The start page keeps prt_settings (the default photo strip, the weather settings and its cached answers, the update
switch, each account's layout), prt_schema_version and the bookmarks. What the page grows later gets its tables here
too. Every table is prt_<name>, the suite's naming convention (the apps can share one database)."""
import logging
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import schema

SCHEMA_VERSION = 4  # 4: the suite naming convention (prt_ tables, prt_settings, position, url, named indexes)
PREFIX = "prt"

# Every table is InnoDB/utf8mb4. Accounts and app passwords live in the Shared ioSuite database (iosuite-shared,
# app/auth.py), not here.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS prt_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # bookmarks, as homepage lays them out: groups of links, each with a name, an abbreviation (or an icon), the link and a
    # line under it (the host name when empty). Shared by the family; editors and admins change them.
    """CREATE TABLE IF NOT EXISTS prt_bookmark_groups (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(128) NOT NULL,
        position INT NOT NULL DEFAULT 0
    )""",
    """CREATE TABLE IF NOT EXISTS prt_bookmarks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        group_id INT NOT NULL,
        name VARCHAR(128) NOT NULL,
        abbr VARCHAR(8) NULL,
        url VARCHAR(2048) NOT NULL,
        description VARCHAR(512) NULL,
        icon VARCHAR(1024) NULL,
        position INT NOT NULL DEFAULT 0,
        KEY idx_prt_bookmarks_group_position (group_id, position),
        FOREIGN KEY (group_id) REFERENCES prt_bookmark_groups(id) ON DELETE CASCADE
    )""",
    # an SVG uploaded for a bookmark (Settings › Bookmarks), served by the page itself: it wins over the icon field
    """CREATE TABLE IF NOT EXISTS prt_bookmark_icons (
        bookmark_id INT PRIMARY KEY,
        svg MEDIUMTEXT NOT NULL,
        etag CHAR(16) NOT NULL,
        FOREIGN KEY (bookmark_id) REFERENCES prt_bookmarks(id) ON DELETE CASCADE
    )""",
]

# 0.7.0: the names from before the suite naming convention, renamed once at start (every row kept). Remove once every
# server has run 0.7.0.
RENAME_TABLES = {"bookmark_groups": "prt_bookmark_groups", "bookmarks": "prt_bookmarks", "bookmark_icons": "prt_bookmark_icons"}
RENAME_COLUMNS = {
    "prt_bookmark_groups": {"sort": "position"},
    "prt_bookmarks": {"href": "url", "sort": "position"},
    "prt_bookmark_icons": {"link_id": "bookmark_id"},
}
RENAME_INDEXES = {"prt_bookmarks": {"group_id": "idx_prt_bookmarks_group_position"}}


def connect(database: str | None = None):
    return pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=config.DB_PASSWORD,
                           database=database if database is not None else config.DB_NAME, charset="utf8mb4",
                           cursorclass=DictCursor, autocommit=False, connect_timeout=8)


_local = threading.local()


@contextmanager
def tx():
    """A connection inside one transaction: committed on success, rolled back on error. Nested calls share it."""
    con = getattr(_local, "con", None)
    if con is not None:
        yield con
        return
    con = connect()
    _local.con = con
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        _local.con = None
        con.close()


def q(sql: str, args=None) -> list[dict]:
    with tx() as con, con.cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def one(sql: str, args=None) -> dict | None:
    rows = q(sql, args)
    return rows[0] if rows else None


def ex(sql: str, args=None) -> int:
    """Run a statement; returns lastrowid (inserts) or rowcount."""
    with tx() as con, con.cursor() as cur:
        n = cur.execute(sql, args)
        return cur.lastrowid or n


def get_setting(k: str, default: str | None = None) -> str | None:
    r = one("SELECT value FROM prt_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM prt_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO prt_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


def ensure_database() -> None:
    """Create the database when it is missing and the user may (CREATE privilege); otherwise leave it to the admin."""
    try:
        connect().close()
        return
    except pymysql.err.OperationalError as e:
        if e.args[0] != 1049:  # anything but "unknown database"
            raise
    con = connect(database="")
    try:
        with con.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        con.close()


def _meta_to_settings(cur) -> None:
    """0.7.0: the meta table's settings rows (setting:<name>) move to prt_settings; its schema row is replaced by
    prt_schema_version."""
    if "meta" in schema.tables(cur):
        cur.execute("INSERT IGNORE INTO prt_settings (name, value) "
                    "SELECT SUBSTRING(k, 9), COALESCE(v, '') FROM meta WHERE k LIKE 'setting:%'")
        cur.execute("DROP TABLE meta")


def migrate() -> None:
    ensure_database()
    with tx() as con, con.cursor() as cur:
        done = schema.rename(cur, RENAME_TABLES, RENAME_COLUMNS)
        for stmt in SCHEMA:
            cur.execute(stmt + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        done += schema.rename(cur, None, None, RENAME_INDEXES)
        _meta_to_settings(cur)
        schema.ensure_version_table(cur, PREFIX)
        schema.record_version(cur, PREFIX, SCHEMA_VERSION)
        if done:
            logging.getLogger("app.db").info("renamed to the suite naming convention: %s", ", ".join(done))


def reset_all() -> None:
    """Tests only: drop every table of this app (prt_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_") or t == "meta" or t in RENAME_TABLES:
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
