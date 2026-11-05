"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

SCHEMA_VERSION = 4

# Every table is InnoDB/utf8mb4. Child rows (emails, phones...) are replaced as a whole when a contact is saved.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS meta (
        k VARCHAR(64) PRIMARY KEY,
        v MEDIUMTEXT
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite-shared, app/auth.py); the users and
    # app_passwords tables of ioContacts 0.3 are folded into it by `iosuite-shared migrate` and renamed *_migrated
    """CREATE TABLE IF NOT EXISTS addressbooks (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        color VARCHAR(16) NULL,
        sync_token BIGINT NOT NULL DEFAULT 1,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY (owner_id, slug)
    )""",
    """CREATE TABLE IF NOT EXISTS contacts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        book_id INT NOT NULL,
        uid VARCHAR(255) NOT NULL,
        href VARCHAR(255) NOT NULL,
        kind ENUM('individual','org','group') NOT NULL DEFAULT 'individual',
        fn VARCHAR(255) NOT NULL DEFAULT '',
        prefix VARCHAR(64) NULL,
        given VARCHAR(128) NULL,
        additional VARCHAR(128) NULL,
        family VARCHAR(128) NULL,
        suffix VARCHAR(64) NULL,
        nickname VARCHAR(128) NULL,
        maiden VARCHAR(128) NULL,
        phonetic_given VARCHAR(128) NULL,
        phonetic_family VARCHAR(128) NULL,
        gender CHAR(1) NULL,
        bday_year SMALLINT NULL,
        bday_month TINYINT NULL,
        bday_day TINYINT NULL,
        bday_remind TINYINT NOT NULL DEFAULT 1,
        org VARCHAR(255) NULL,
        department VARCHAR(255) NULL,
        title VARCHAR(255) NULL,
        role VARCHAR(255) NULL,
        notes TEXT NULL,
        favorite TINYINT NOT NULL DEFAULT 0,
        photo MEDIUMBLOB NULL,
        photo_type VARCHAR(32) NULL,
        iopix_person_id INT NULL,
        iopix_person_name VARCHAR(255) NULL,
        extra MEDIUMTEXT NULL,
        etag VARCHAR(64) NOT NULL,
        changed_token BIGINT NOT NULL DEFAULT 0,
        deleted TINYINT NOT NULL DEFAULT 0,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY (book_id, href),
        KEY (book_id, uid),
        KEY (book_id, deleted, changed_token),
        KEY (fn),
        KEY (iopix_person_id),
        FOREIGN KEY (book_id) REFERENCES addressbooks(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS contact_emails (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, pos SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(255) NOT NULL, pref TINYINT NOT NULL DEFAULT 0,
        KEY (value), FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS contact_phones (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, pos SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(64) NOT NULL, pref TINYINT NOT NULL DEFAULT 0,
        KEY (value), FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS contact_addresses (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, pos SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, pobox VARCHAR(64) NULL, ext VARCHAR(128) NULL, street VARCHAR(255) NULL,
        city VARCHAR(128) NULL, region VARCHAR(128) NULL, postcode VARCHAR(32) NULL, country VARCHAR(128) NULL,
        pref TINYINT NOT NULL DEFAULT 0,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS contact_urls (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, pos SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(512) NOT NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS contact_social (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, pos SMALLINT NOT NULL DEFAULT 0,
        service VARCHAR(64) NOT NULL, value VARCHAR(512) NOT NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS contact_dates (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, pos SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NOT NULL, year SMALLINT NULL, month TINYINT NOT NULL, day TINYINT NOT NULL,
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS contact_tags (
        contact_id INT NOT NULL, tag VARCHAR(128) NOT NULL, PRIMARY KEY (contact_id, tag), KEY (tag),
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    # relations are directed: "contact_id's <type> is related_id" (Ann's sibling is Bob). The inverse row
    # (Bob's sibling is Ann) is kept by the model. related_name holds a person who is not a contact.
    """CREATE TABLE IF NOT EXISTS relations (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, pos SMALLINT NOT NULL DEFAULT 0,
        type VARCHAR(32) NOT NULL, related_id INT NULL, related_name VARCHAR(255) NULL, label VARCHAR(64) NULL,
        KEY (related_id),
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE,
        FOREIGN KEY (related_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    # two contacts someone said are different people: never offered as duplicates again (a < b)
    """CREATE TABLE IF NOT EXISTS not_duplicates (
        a INT NOT NULL, b INT NOT NULL, user_id INT NULL, created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (a, b))""",
    # every merge, with the rows of the contacts as they were before, so it can be undone
    """CREATE TABLE IF NOT EXISTS merges (
        id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NULL, keep_id INT NOT NULL, other_ids VARCHAR(512) NOT NULL,
        names VARCHAR(1024) NULL, snapshot LONGTEXT NOT NULL, keep_etag VARCHAR(64) NULL,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, undone TIMESTAMP NULL, KEY (keep_id))""",
    # enrichment: what a lookup (Gravatar, GitHub...) or an assistant over MCP found, waiting for a person to accept it
    """CREATE TABLE IF NOT EXISTS suggestions (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, field VARCHAR(32) NOT NULL, value MEDIUMTEXT NOT NULL,
        vkey VARCHAR(255) NOT NULL, source VARCHAR(64) NOT NULL, evidence VARCHAR(1024) NULL, note VARCHAR(1024) NULL,
        status ENUM('pending','accepted','dismissed') NOT NULL DEFAULT 'pending', by_user_id INT NULL, decided_by INT NULL,
        created TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, decided TIMESTAMP NULL,
        KEY (contact_id, status), UNIQUE KEY one_value (contact_id, field, vkey),
        FOREIGN KEY (contact_id) REFERENCES contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS calendar_tokens (
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


_collation: str | None = None


def search_collation() -> str:
    """The most forgiving utf8mb4 collation the server has, for searches: case- and accent-insensitive, so "celia"
    matches "Célia" whatever collation the tables were created with (uca1400 on MariaDB 10.10+, which also folds
    ø, ł and đ; unicode_520 before it)."""
    global _collation
    if _collation is None:
        have = {r["Collation"] for r in q("SHOW COLLATION WHERE Collation IN "
                                           "('utf8mb4_uca1400_ai_ci', 'utf8mb4_unicode_520_ci')")}
        _collation = next((c for c in ("utf8mb4_uca1400_ai_ci", "utf8mb4_unicode_520_ci") if c in have),
                          "utf8mb4_unicode_ci")
    return _collation


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


# schema 4: whether a birthday goes into the birthday feeds (calendar, upcoming, the suite); existing birthdays stay on
UPGRADES = [
    "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS bday_remind TINYINT NOT NULL DEFAULT 1 AFTER bday_day",
]


def migrate() -> None:
    ensure_database()
    with tx() as con, con.cursor() as cur:
        for stmt in SCHEMA:
            cur.execute(stmt + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        # columns added after a table was first made (MariaDB: ADD COLUMN IF NOT EXISTS)
        for stmt in UPGRADES:
            cur.execute(stmt)
        cur.execute("INSERT INTO meta (k, v) VALUES ('schema', %s) ON DUPLICATE KEY UPDATE v = GREATEST(v, VALUES(v))",
                    (str(SCHEMA_VERSION),))
        # the family address book everyone shares
        cur.execute("SELECT id FROM addressbooks WHERE owner_id IS NULL LIMIT 1")
        if not cur.fetchone():
            cur.execute("INSERT INTO addressbooks (owner_id, slug, name, description) VALUES "
                        "(NULL, 'family', 'Family', 'Shared with everyone in the family')")


def reset_all() -> None:
    """Tests only: drop every table."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        cur.execute("SHOW TABLES")
        for r in cur.fetchall():
            cur.execute(f"DROP TABLE `{list(r.values())[0]}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
