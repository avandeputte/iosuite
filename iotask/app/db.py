"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 2   # 2: tsk_activity, tsk_templates
PREFIX = "tsk"

# Every table is tsk_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4. A
# task is kept as the iCalendar object (a VTODO) a client sent (or the web app made), so whatever a reminders app puts
# in it (alarms, its own X- properties, sort order) comes back unchanged; the columns beside it are what the app
# searches, sorts and filters on, filled in whenever the object is saved.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS tsk_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite-shared, app/auth.py)
    # owner_id NULL: a shared list (everyone sees it). owner_key stands in for owner_id in the unique key: NULLs never
    # clash in a unique key, so (owner_id, slug) alone would let two shared lists share a slug
    """CREATE TABLE IF NOT EXISTS tsk_lists (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        color VARCHAR(16) NULL,
        position INT NOT NULL DEFAULT 0,
        sync_token BIGINT NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT,
        UNIQUE KEY uq_tsk_lists_owner_slug (owner_key, slug)
    )""",
    # due / start / completed_at are UTC (a due date without a time: that date at midnight UTC, due_all_day = 1).
    # status: NEEDS-ACTION, IN-PROCESS, COMPLETED or CANCELLED; priority 0 (none) or 1 (high) .. 9 (low), as RFC 5545;
    # parent_uid: RELATED-TO (a subtask's parent); sort_order: X-APPLE-SORT-ORDER, where a reminders app put it.
    """CREATE TABLE IF NOT EXISTS tsk_tasks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        list_id INT NOT NULL,
        uid VARCHAR(255) NOT NULL,
        href VARCHAR(255) NOT NULL,
        summary VARCHAR(512) NOT NULL DEFAULT '',
        description TEXT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'NEEDS-ACTION',
        done TINYINT NOT NULL DEFAULT 0,
        priority TINYINT NOT NULL DEFAULT 0,
        due DATETIME NULL,
        due_all_day TINYINT NOT NULL DEFAULT 0,
        start DATETIME NULL,
        completed_at DATETIME NULL,
        parent_uid VARCHAR(255) NULL,
        rrule VARCHAR(1024) NULL,
        sort_order BIGINT NULL,
        ics MEDIUMTEXT NOT NULL,
        etag VARCHAR(64) NOT NULL,
        changed_token BIGINT NOT NULL DEFAULT 0,
        deleted TINYINT NOT NULL DEFAULT 0,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_tsk_tasks_list_href (list_id, href),
        KEY idx_tsk_tasks_list_uid (list_id, uid),
        KEY idx_tsk_tasks_list_changes (list_id, deleted, changed_token),
        KEY idx_tsk_tasks_list_open (list_id, deleted, done, due),
        FOREIGN KEY (list_id) REFERENCES tsk_lists(id) ON DELETE CASCADE
    )""",
    # The activity log: who added, changed, ticked off or deleted which task, and through what (the web app and the
    # API, a reminders app over CalDAV, an assistant over MCP). before_ics is the task as it was (NULL: it was not
    # there), so a step can be undone while the task is still as that step left it (etag_after). The entries of one
    # step (a task and its subtasks, "clear completed", a move to another list) share a batch and are undone together.
    """CREATE TABLE IF NOT EXISTS tsk_activity (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        list_id INT NOT NULL,
        task_id INT NULL,
        uid VARCHAR(255) NOT NULL,
        title VARCHAR(512) NOT NULL DEFAULT '',
        user_id INT NULL,
        action VARCHAR(16) NOT NULL,
        via VARCHAR(8) NOT NULL DEFAULT 'web',
        detail VARCHAR(255) NULL,
        before_ics MEDIUMTEXT NULL,
        etag_after VARCHAR(64) NULL,
        batch VARCHAR(32) NOT NULL,
        undone TINYINT NOT NULL DEFAULT 0,
        at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
        KEY idx_tsk_activity_list (list_id, id),
        KEY idx_tsk_activity_task (list_id, uid, id),
        KEY idx_tsk_activity_batch (batch),
        FOREIGN KEY (list_id) REFERENCES tsk_lists(id) ON DELETE CASCADE
    )""",
    # A template: the tasks of a list as they were when it was saved (items: JSON, [{title, notes, priority, url,
    # categories, children}]), to add to a list again. owner_id NULL: shared with everyone.
    """CREATE TABLE IF NOT EXISTS tsk_templates (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        name VARCHAR(128) NOT NULL,
        items MEDIUMTEXT NOT NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
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


def marks(n: int) -> str:
    return ",".join(["%s"] * n) if n else "NULL"


def get_setting(k: str, default: str | None = None) -> str | None:
    r = one("SELECT value FROM tsk_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM tsk_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO tsk_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


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
        # the family list everyone shares
        cur.execute("SELECT id FROM tsk_lists WHERE owner_id IS NULL LIMIT 1")
        if not cur.fetchone():
            cur.execute("INSERT INTO tsk_lists (owner_id, slug, name, description, color) VALUES "
                        "(NULL, 'family', 'Family', 'Shared with everyone in the family', '#146b5e')")


def reset_all() -> None:
    """Tests only: drop every table of this app (tsk_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
