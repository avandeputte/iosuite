"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 1
PREFIX = "bkp"

# Every table is bkp_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
# Passwords and Google keys are never here: they are kept with the suite's keys and tokens (iosuite_shared.credentials,
# app iobackup: server_<id>_password, destination_<id>_client_secret / _refresh_token / _service_account).
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS bkp_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # a MariaDB (or Galera node) to back up and restore onto: host and port, or a socket on this machine
    """CREATE TABLE IF NOT EXISTS bkp_servers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        host VARCHAR(253) NOT NULL DEFAULT '',
        port INT NULL,
        socket VARCHAR(255) NOT NULL DEFAULT '',
        user_name VARCHAR(80) NOT NULL DEFAULT '',
        tls TINYINT NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bkp_servers_name (name)
    )""",
    # where backups are kept: kind local (options: path) or gdrive (options: auth, folder_name, folder_id, client_id,
    # account)
    """CREATE TABLE IF NOT EXISTS bkp_destinations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        options TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bkp_destinations_name (name)
    )""",
    # what to back up, where, when and how many to keep. databases: a JSON list, or "all"; schedule: the form's
    # fields as JSON, cron: the five-field expression it makes ('' for on demand only)
    """CREATE TABLE IF NOT EXISTS bkp_jobs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(64) NOT NULL,
        server_id INT NOT NULL,
        destination_id INT NOT NULL,
        databases_json TEXT NOT NULL,
        include_users TINYINT NOT NULL DEFAULT 1,
        keep_count INT NOT NULL DEFAULT 7,
        schedule_json TEXT NOT NULL,
        cron VARCHAR(128) NOT NULL DEFAULT '',
        enabled TINYINT NOT NULL DEFAULT 1,
        desync TINYINT NOT NULL DEFAULT 0,
        lock_all TINYINT NOT NULL DEFAULT 0,
        compress_level TINYINT NOT NULL DEFAULT 6,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_bkp_jobs_name (name),
        KEY idx_bkp_jobs_server (server_id),
        KEY idx_bkp_jobs_destination (destination_id),
        FOREIGN KEY (server_id) REFERENCES bkp_servers(id),
        FOREIGN KEY (destination_id) REFERENCES bkp_destinations(id)
    )""",
    # every backup and restore, with its log: kind backup or restore; status queued, running, ok, failed, cancelled;
    # trigger_kind schedule or manual; payload what to do (JSON), result what came of it (JSON)
    """CREATE TABLE IF NOT EXISTS bkp_runs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        kind VARCHAR(16) NOT NULL,
        title VARCHAR(255) NOT NULL,
        job_id INT NULL,
        trigger_kind VARCHAR(16) NOT NULL DEFAULT 'manual',
        user_name VARCHAR(64) NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        queued_at DATETIME NOT NULL,
        started_at DATETIME NULL,
        finished_at DATETIME NULL,
        payload TEXT NULL,
        result TEXT NULL,
        log MEDIUMTEXT NOT NULL,
        KEY idx_bkp_runs_job (job_id),
        KEY idx_bkp_runs_status (status)
    )""",
]


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
    r = one("SELECT value FROM bkp_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM bkp_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO bkp_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


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
    """Tests only: drop every table of this app (bkp_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
