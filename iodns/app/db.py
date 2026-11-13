"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 1
PREFIX = "dns"

# Every table is dns_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
#
# The master list is a list of entries (a host name, with a note), each with records per view: a view is one answer
# to "who is asking" (Internal: the house; External: the internet; Tailscale: the tailnet), and each DNS server
# answers for one view. So calendar.example.com can be 192.168.1.151 inside, a public address outside and 100.x on
# the tailnet, and a name without an External record is never pushed to public DNS.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS dns_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    """CREATE TABLE IF NOT EXISTS dns_views (
        id INT AUTO_INCREMENT PRIMARY KEY,
        slug VARCHAR(32) NOT NULL,
        name VARCHAR(64) NOT NULL,
        description VARCHAR(255) NULL,
        position INT NOT NULL DEFAULT 0,
        UNIQUE KEY uq_dns_views_slug (slug)
    )""",
    """CREATE TABLE IF NOT EXISTS dns_entries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(253) NOT NULL,
        comment VARCHAR(512) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        updated_by VARCHAR(64) NULL,
        UNIQUE KEY uq_dns_entries_name (name)
    )""",
    # source: where the value comes from when it is not typed in, "tailscale:<server id>:<device>" (the device's tailnet
    # address, read again before every sync); value then holds the address last read
    """CREATE TABLE IF NOT EXISTS dns_records (
        id INT AUTO_INCREMENT PRIMARY KEY,
        entry_id INT NOT NULL,
        view_id INT NOT NULL,
        type VARCHAR(8) NOT NULL,
        value VARCHAR(253) NOT NULL,
        ttl INT NULL,
        source VARCHAR(255) NULL,
        UNIQUE KEY uq_dns_records_entry_view_value (entry_id, view_id, type, value),
        KEY idx_dns_records_view (view_id),
        FOREIGN KEY (entry_id) REFERENCES dns_entries(id) ON DELETE CASCADE,
        FOREIGN KEY (view_id) REFERENCES dns_views(id) ON DELETE CASCADE
    )""",
    # a DNS server ioDNS keeps in sync (or reads from: Tailscale); its password or key is in the Shared ioSuite
    # database's keys and tokens (iosuite_shared.credentials, app iodns, name server_<id>), never here
    """CREATE TABLE IF NOT EXISTS dns_servers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        kind VARCHAR(32) NOT NULL,
        url VARCHAR(512) NOT NULL DEFAULT '',
        view_id INT NULL,
        options TEXT NULL,
        enabled TINYINT NOT NULL DEFAULT 1,
        position INT NOT NULL DEFAULT 0,
        checked_at TIMESTAMP NULL,
        check_ok TINYINT NULL,
        check_message VARCHAR(512) NULL,
        differences INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_dns_servers_view (view_id),
        FOREIGN KEY (view_id) REFERENCES dns_views(id) ON DELETE SET NULL
    )""",
    # what was changed where, and by whom: the master list's changes, pushes and imports
    """CREATE TABLE IF NOT EXISTS dns_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        user_name VARCHAR(64) NULL,
        action VARCHAR(32) NOT NULL,
        server_id INT NULL,
        server_name VARCHAR(64) NULL,
        detail TEXT NULL,
        ok TINYINT NOT NULL DEFAULT 1,
        KEY idx_dns_log_at (at)
    )""",
]

VIEWS = [("internal", "Internal", "The house: what the LAN's DNS servers answer", 0),
         ("external", "External", "The internet: public DNS (Cloudflare…)", 1),
         ("tailscale", "Tailscale", "The tailnet: the DNS server Tailscale's split DNS points at", 2)]


def connect(database: str | None = None):
    return pymysql.connect(host=config.DB_HOST, port=config.DB_PORT, user=config.DB_USER, password=config.DB_PASSWORD,
                           database=database if database is not None else config.DB_NAME, charset="utf8mb4",
                           cursorclass=DictCursor, autocommit=False, connect_timeout=8)


_local = threading.local()
pool = shared_db.Pool(connect)  # a few open connections, reused: no new handshake and sign-in for every query


@contextmanager
def tx():
    """A pooled connection inside one transaction: committed on success, rolled back on error. Nested calls share it."""
    con = getattr(_local, "con", None)
    if con is not None:
        yield con
        return
    con = pool.borrow()
    _local.con = con
    broken = False
    try:
        yield con
        con.commit()
    except BaseException as e:
        broken = isinstance(e, (pymysql.err.OperationalError, pymysql.err.InterfaceError))
        if not broken:
            con.rollback()
        raise
    finally:
        _local.con = None
        pool.give_back(con, broken)


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


def marks(n: int) -> str:
    return ",".join(["%s"] * n) if n else "NULL"


def get_setting(k: str, default: str | None = None) -> str | None:
    r = one("SELECT value FROM dns_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM dns_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO dns_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


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
        cur.execute("SELECT count(*) AS n FROM dns_views")
        if not cur.fetchone()["n"]:
            cur.executemany("INSERT INTO dns_views (slug, name, description, position) VALUES (%s, %s, %s, %s)", VIEWS)


def reset_all() -> None:
    """Tests only: drop every table of this app (dns_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
