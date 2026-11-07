"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 2  # 2: the suite naming convention (cal_ tables, *_at times, cal_settings, named indexes)
PREFIX = "cal"

# Every table is cal_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4. An
# event is kept as the iCalendar object a client sent (or the web app made), so whatever a calendar app puts in it
# (alarms, attachments, its own X- properties, changed occurrences) comes back unchanged; the columns beside it are
# what the app searches and draws from, filled in whenever the object is saved.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS cal_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite-shared, app/auth.py)
    # owner_id NULL: a shared calendar (everyone sees it); kind 'birthdays' is filled from ioContacts and read-only.
    # owner_key stands in for owner_id in the unique key: NULLs never clash in a unique key, so (owner_id, slug) alone
    # would let two shared calendars share a slug
    """CREATE TABLE IF NOT EXISTS cal_calendars (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        color VARCHAR(16) NULL,
        timezone VARCHAR(64) NULL,
        kind VARCHAR(16) NOT NULL DEFAULT 'events',
        position INT NOT NULL DEFAULT 0,
        sync_token BIGINT NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT,
        UNIQUE KEY uq_cal_calendars_owner_slug (owner_key, slug)
    )""",
    # dtstart / dtend / range_* are UTC (an all-day event: its dates at midnight UTC, all_day = 1). range_start is the
    # first occurrence's start, range_end the last one's end (NULL: repeats for ever): what a time-range query needs.
    """CREATE TABLE IF NOT EXISTS cal_events (
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
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_cal_events_calendar_href (calendar_id, href),
        KEY idx_cal_events_calendar_uid (calendar_id, uid),
        KEY idx_cal_events_calendar_changes (calendar_id, deleted, changed_token),
        KEY idx_cal_events_calendar_range (calendar_id, deleted, range_start),
        FOREIGN KEY (calendar_id) REFERENCES cal_calendars(id) ON DELETE CASCADE
    )""",
    # the people on an event (ATTENDEE, and ORGANIZER with role 'organizer'), for search and "what is X doing";
    # contact_id is the ioContacts contact the web app picked them from
    """CREATE TABLE IF NOT EXISTS cal_event_people (
        id INT AUTO_INCREMENT PRIMARY KEY, event_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        name VARCHAR(255) NULL, email VARCHAR(255) NULL, contact_id INT NULL, role VARCHAR(16) NULL,
        KEY idx_cal_event_people_event (event_id), KEY idx_cal_event_people_email (email), KEY idx_cal_event_people_contact (contact_id),
        FOREIGN KEY (event_id) REFERENCES cal_events(id) ON DELETE CASCADE)""",
    # the private links of the iCalendar subscriptions (/ics/<token>/...), one per account
    """CREATE TABLE IF NOT EXISTS cal_feed_tokens (
        id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, token CHAR(40) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_cal_feed_tokens_token (token), KEY idx_cal_feed_tokens_user (user_id))""",
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


def many(sql: str, rows: list) -> None:
    if rows:
        with tx() as con, con.cursor() as cur:
            cur.executemany(sql, rows)


def marks(n: int) -> str:
    return ",".join(["%s"] * n) if n else "NULL"


def get_setting(k: str, default: str | None = None) -> str | None:
    r = one("SELECT value FROM cal_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM cal_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO cal_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


def schema_version() -> int:
    with tx() as con, con.cursor() as cur:
        return schema.current_version(cur, PREFIX)


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
        # the family calendar everyone shares
        cur.execute("SELECT id FROM cal_calendars WHERE owner_id IS NULL AND kind = 'events' LIMIT 1")
        if not cur.fetchone():
            cur.execute("INSERT INTO cal_calendars (owner_id, slug, name, description, color) VALUES "
                        "(NULL, 'family', 'Family', 'Shared with everyone in the family', '#8e44d6')")


def reset_all() -> None:
    """Tests only: drop every table of this app (cal_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
