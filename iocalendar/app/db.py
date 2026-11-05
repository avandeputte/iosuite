"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

SCHEMA_VERSION = 1

# Every table is InnoDB/utf8mb4. An event is kept as the iCalendar object a client sent (or the web app made), so
# whatever a calendar app puts in it (alarms, attachments, its own X- properties, changed occurrences) comes back
# unchanged; the columns beside it are what the app searches and draws from, filled in whenever the object is saved.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS meta (
        k VARCHAR(64) PRIMARY KEY,
        v MEDIUMTEXT
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iothing-auth, app/auth.py)
    # owner_id NULL: a shared calendar (everyone sees it); kind 'birthdays' is filled from ioContacts and read-only.
    # owner_key stands in for owner_id in the unique key: NULLs never clash in a unique key, so (owner_id, slug) alone
    # would let two shared calendars share a slug
    """CREATE TABLE IF NOT EXISTS calendars (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        color VARCHAR(16) NULL,
        timezone VARCHAR(64) NULL,
        kind VARCHAR(16) NOT NULL DEFAULT 'events',
        sort INT NOT NULL DEFAULT 0,
        sync_token BIGINT NOT NULL DEFAULT 1,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT,
        UNIQUE KEY (owner_key, slug)
    )""",
    # dtstart / dtend / range_* are UTC (an all-day event: its dates at midnight UTC, all_day = 1). range_start is the
    # first occurrence's start, range_end the last one's end (NULL: repeats for ever): what a time-range query needs.
    """CREATE TABLE IF NOT EXISTS events (
        id INT AUTO_INCREMENT PRIMARY KEY,
        calendar_id INT NOT NULL,
        uid VARCHAR(255) NOT NULL,
        href VARCHAR(255) NOT NULL,
        summary VARCHAR(512) NOT NULL DEFAULT '',
        location VARCHAR(1024) NULL,
        description TEXT NULL,
        all_day TINYINT NOT NULL DEFAULT 0,
        dtstart DATETIME NULL,
        dtend DATETIME NULL,
        tzid VARCHAR(64) NULL,
        rrule VARCHAR(1024) NULL,
        status VARCHAR(16) NULL,
        range_start DATETIME NULL,
        range_end DATETIME NULL,
        ics MEDIUMTEXT NOT NULL,
        etag VARCHAR(64) NOT NULL,
        changed_token BIGINT NOT NULL DEFAULT 0,
        deleted TINYINT NOT NULL DEFAULT 0,
        created_by INT NULL,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY (calendar_id, href),
        KEY (calendar_id, uid),
        KEY (calendar_id, deleted, changed_token),
        KEY (calendar_id, deleted, range_start),
        FOREIGN KEY (calendar_id) REFERENCES calendars(id) ON DELETE CASCADE
    )""",
    # the people on an event (ATTENDEE, and ORGANIZER with role 'organizer'), for search and "what is X doing";
    # contact_id is the ioContacts contact the web app picked them from
    """CREATE TABLE IF NOT EXISTS event_people (
        id INT AUTO_INCREMENT PRIMARY KEY, event_id INT NOT NULL, pos SMALLINT NOT NULL DEFAULT 0,
        name VARCHAR(255) NULL, email VARCHAR(255) NULL, contact_id INT NULL, role VARCHAR(16) NULL,
        KEY (email), KEY (contact_id),
        FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE)""",
    # the private links of the iCalendar subscriptions (/ics/<token>/...), one per account
    """CREATE TABLE IF NOT EXISTS feed_tokens (
        id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, token CHAR(40) NOT NULL UNIQUE,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""",
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


def many(sql: str, rows: list) -> None:
    if rows:
        with tx() as con, con.cursor() as cur:
            cur.executemany(sql, rows)


def marks(n: int) -> str:
    return ",".join(["%s"] * n) if n else "NULL"


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
        # calendars made before 0.2.7 have the unique key on (owner_id, slug), which NULL owner_ids slip past
        cur.execute("ALTER TABLE calendars ADD COLUMN IF NOT EXISTS owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT")
        cur.execute("ALTER TABLE calendars ADD UNIQUE INDEX IF NOT EXISTS owner_key (owner_key, slug)")
        cur.execute("INSERT INTO meta (k, v) VALUES ('schema', %s) ON DUPLICATE KEY UPDATE v = GREATEST(v, VALUES(v))",
                    (str(SCHEMA_VERSION),))
        # the family calendar everyone shares
        cur.execute("SELECT id FROM calendars WHERE owner_id IS NULL AND kind = 'events' LIMIT 1")
        if not cur.fetchone():
            cur.execute("INSERT INTO calendars (owner_id, slug, name, description, color) VALUES "
                        "(NULL, 'family', 'Family', 'Shared with everyone in the family', '#8e44d6')")


def reset_all() -> None:
    """Tests only: drop every table."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("SHOW TABLES")
        for r in cur.fetchall():
            cur.execute(f"DROP TABLE `{list(r.values())[0]}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
