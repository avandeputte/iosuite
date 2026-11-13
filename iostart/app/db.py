"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start).

The start page keeps prt_settings (the default photo strip, the weather settings and its cached answers, the update
switch, each account's layout), prt_schema_version and the bookmarks. What the page grows later gets its tables here
too. Every table is prt_<name>, the suite's naming convention (the apps can share one database)."""

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 6  # 6: the bookmarked sites' own icons (prt_site_icons)
PREFIX = "prt"

# Every table is InnoDB/utf8mb4. Accounts and app passwords live in the Shared ioSuite database (iosuite-shared,
# app/auth.py), not here.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS prt_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # the bookmarks: one tree of folders and links, as a browser keeps them, which sync clients (Floccus, anything that
    # speaks the Nextcloud Bookmarks API, a bookmarks file over WebDAV) read and write. An id is handed out by the app
    # (never reused: sync clients remember them). `start` picks what the start page shows: on a folder, 1 shows it as a
    # group with its links; on a link, NULL follows its folder, 1 shows it anyway and 0 hides it. `rev` / `created_rev`
    # are the store's revision (prt_settings bookmarks_rev) when the row last changed and when it was made.
    """CREATE TABLE IF NOT EXISTS prt_bookmark_nodes (
        id INT PRIMARY KEY,
        parent_id INT NULL,
        folder TINYINT(1) NOT NULL DEFAULT 0,
        name VARCHAR(1024) NOT NULL,
        url TEXT NULL,
        abbr VARCHAR(8) NULL,
        description VARCHAR(512) NULL,
        icon VARCHAR(1024) NULL,
        tags TEXT NULL,
        start TINYINT(1) NULL,
        position INT NOT NULL DEFAULT 0,
        rev BIGINT NOT NULL DEFAULT 0,
        created_rev BIGINT NOT NULL DEFAULT 0,
        created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
        KEY idx_prt_bookmark_nodes_parent_position (parent_id, position),
        FOREIGN KEY (parent_id) REFERENCES prt_bookmark_nodes(id) ON DELETE CASCADE
    )""",
    # an SVG uploaded for a bookmark (the Bookmarks page), served by the page itself: it wins over the icon field
    """CREATE TABLE IF NOT EXISTS prt_bookmark_node_icons (
        node_id INT PRIMARY KEY,
        svg MEDIUMTEXT NOT NULL,
        etag CHAR(16) NOT NULL,
        FOREIGN KEY (node_id) REFERENCES prt_bookmark_nodes(id) ON DELETE CASCADE
    )""",
    # a bookmarked site's own icon (app/siteicons.py), one per scheme://host[:port]: what a link without an icon of
    # its own shows. data NULL: looked for, none found
    """CREATE TABLE IF NOT EXISTS prt_site_icons (
        site VARCHAR(255) PRIMARY KEY,
        data MEDIUMBLOB NULL,
        mime VARCHAR(32) NULL,
        etag CHAR(16) NULL,
        fetched_at DATETIME NOT NULL
    )""",
]

def connect(database: str | None = None):
    return pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=config.DB_PASSWORD,
                           database=database if database is not None else config.DB_NAME, charset="utf8mb4",
                           cursorclass=DictCursor, autocommit=True, connect_timeout=8)


# The pool, the transaction nested calls share, and q / one / ex / many are the suite's (iosuite_shared.db.Database):
# a statement on its own is one round trip, tx() is one transaction (committed on success, rolled back on error), and
# q / one / ex inside a `with tx():` block run in it.
_db = shared_db.Database(connect)
pool = _db.pool
tx, q, one, ex, many = _db.tx, _db.q, _db.one, _db.ex, _db.many


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


def migrate() -> None:
    ensure_database()
    with tx() as con, con.cursor() as cur:
        for stmt in SCHEMA:
            cur.execute(stmt + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        schema.ensure_version_table(cur, PREFIX)
        schema.record_version(cur, PREFIX, SCHEMA_VERSION)


def reset_all() -> None:
    """Tests only: drop every table of this app (prt_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
