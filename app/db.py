"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start).

The start page keeps little: a `meta` table of settings (the apps' addresses, the update switch, the schema version).
The dynamic content the page grows later gets its tables here, in the same way as in the other io apps."""
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

SCHEMA_VERSION = 1

# Every table is InnoDB/utf8mb4. Accounts and app passwords live in the suite's shared auth database (iothing-auth,
# app/auth.py), not here.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS meta (
        k VARCHAR(64) PRIMARY KEY,
        v MEDIUMTEXT
    )""",
]


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
    r = one("SELECT v FROM meta WHERE k = %s", (f"setting:{k}",))
    return r["v"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM meta WHERE k = %s", (f"setting:{k}",))
    else:
        ex("INSERT INTO meta (k, v) VALUES (%s, %s) ON DUPLICATE KEY UPDATE v = VALUES(v)", (f"setting:{k}", v))


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
        cur.execute("INSERT INTO meta (k, v) VALUES ('schema', %s) ON DUPLICATE KEY UPDATE v = GREATEST(v, VALUES(v))",
                    (str(SCHEMA_VERSION),))


def reset_all() -> None:
    """Tests only: drop every table."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("SHOW TABLES")
        for r in cur.fetchall():
            cur.execute(f"DROP TABLE `{list(r.values())[0]}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
