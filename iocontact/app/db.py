"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""
import logging
import threading
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import schema

SCHEMA_VERSION = 5  # 5: the suite naming convention (con_ tables, *_at times, con_settings, named indexes)
PREFIX = "con"

# Every table is con_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4. Child rows (emails, phones...) are replaced as a whole when a contact is saved.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS con_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite-shared, app/auth.py); the users and
    # app_passwords tables of ioContacts 0.3 are folded into it by `iosuite-shared migrate` and renamed *_migrated.
    # owner_id NULL: a shared address book. owner_key stands in for owner_id in the unique key: NULLs never clash in a
    # unique key, so (owner_id, slug) alone would let two shared address books share a slug
    """CREATE TABLE IF NOT EXISTS con_address_books (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        slug VARCHAR(64) NOT NULL,
        name VARCHAR(128) NOT NULL,
        description VARCHAR(512) NULL,
        color VARCHAR(16) NULL,
        sync_token BIGINT NOT NULL DEFAULT 1,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT,
        UNIQUE KEY uq_con_address_books_owner_slug (owner_key, slug)
    )""",
    """CREATE TABLE IF NOT EXISTS con_contacts (
        id INT AUTO_INCREMENT PRIMARY KEY,
        address_book_id INT NOT NULL,
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
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_con_contacts_book_href (address_book_id, href),
        KEY idx_con_contacts_book_uid (address_book_id, uid),
        KEY idx_con_contacts_book_changes (address_book_id, deleted, changed_token),
        KEY idx_con_contacts_fn (fn),
        KEY idx_con_contacts_iopix_person (iopix_person_id),
        FOREIGN KEY (address_book_id) REFERENCES con_address_books(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS con_contact_emails (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(255) NOT NULL, pref TINYINT NOT NULL DEFAULT 0,
        KEY idx_con_contact_emails_contact (contact_id), KEY idx_con_contact_emails_value (value), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_phones (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(64) NOT NULL, pref TINYINT NOT NULL DEFAULT 0,
        KEY idx_con_contact_phones_contact (contact_id), KEY idx_con_contact_phones_value (value), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_addresses (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, pobox VARCHAR(64) NULL, ext VARCHAR(128) NULL, street VARCHAR(255) NULL,
        city VARCHAR(128) NULL, region VARCHAR(128) NULL, postcode VARCHAR(32) NULL, country VARCHAR(128) NULL,
        pref TINYINT NOT NULL DEFAULT 0,
        KEY idx_con_contact_addresses_contact (contact_id), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_urls (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NULL, value VARCHAR(512) NOT NULL,
        KEY idx_con_contact_urls_contact (contact_id), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_social_profiles (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        service VARCHAR(64) NOT NULL, value VARCHAR(512) NOT NULL,
        KEY idx_con_contact_social_profiles_contact (contact_id), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_dates (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        label VARCHAR(64) NOT NULL, year SMALLINT NULL, month TINYINT NOT NULL, day TINYINT NOT NULL,
        KEY idx_con_contact_dates_contact (contact_id), FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS con_contact_tags (
        contact_id INT NOT NULL, tag VARCHAR(128) NOT NULL, PRIMARY KEY (contact_id, tag), KEY idx_con_contact_tags_tag (tag),
        FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    # relations are directed: "contact_id's <type> is related_id" (Ann's sibling is Bob). The inverse row
    # (Bob's sibling is Ann) is kept by the model. related_name holds a person who is not a contact.
    """CREATE TABLE IF NOT EXISTS con_contact_relations (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, position SMALLINT NOT NULL DEFAULT 0,
        type VARCHAR(32) NOT NULL, related_id INT NULL, related_name VARCHAR(255) NULL, label VARCHAR(64) NULL,
        KEY idx_con_contact_relations_contact (contact_id), KEY idx_con_contact_relations_related (related_id),
        FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE,
        FOREIGN KEY (related_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    # two contacts someone said are different people: never offered as duplicates again (contact_id < other_contact_id)
    """CREATE TABLE IF NOT EXISTS con_contact_non_duplicates (
        contact_id INT NOT NULL, other_contact_id INT NOT NULL, user_id INT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (contact_id, other_contact_id))""",
    # every merge, with the rows of the contacts as they were before, so it can be undone
    """CREATE TABLE IF NOT EXISTS con_contact_merges (
        id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NULL, kept_contact_id INT NOT NULL, other_ids VARCHAR(512) NOT NULL,
        names VARCHAR(1024) NULL, snapshot LONGTEXT NOT NULL, keep_etag VARCHAR(64) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, undone_at TIMESTAMP NULL, KEY idx_con_contact_merges_kept (kept_contact_id))""",
    # enrichment: what a lookup (Gravatar, GitHub...) or an assistant over MCP found, waiting for a person to accept it
    """CREATE TABLE IF NOT EXISTS con_contact_suggestions (
        id INT AUTO_INCREMENT PRIMARY KEY, contact_id INT NOT NULL, field VARCHAR(32) NOT NULL, value MEDIUMTEXT NOT NULL,
        vkey VARCHAR(255) NOT NULL, source VARCHAR(64) NOT NULL, evidence VARCHAR(1024) NULL, note VARCHAR(1024) NULL,
        status ENUM('pending','accepted','dismissed') NOT NULL DEFAULT 'pending', created_by INT NULL, decided_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, decided_at TIMESTAMP NULL,
        KEY idx_con_contact_suggestions_contact_status (contact_id, status), UNIQUE KEY uq_con_contact_suggestions_value (contact_id, field, vkey),
        FOREIGN KEY (contact_id) REFERENCES con_contacts(id) ON DELETE CASCADE)""",
    # the private links of the birthday calendar subscription, one per account
    """CREATE TABLE IF NOT EXISTS con_feed_tokens (
        id INT AUTO_INCREMENT PRIMARY KEY, user_id INT NOT NULL, token CHAR(40) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_con_feed_tokens_token (token), KEY idx_con_feed_tokens_user (user_id))""",
]


# 0.9.0: the names from before the suite naming convention, renamed once at start (every row kept). Remove once every
# server has run 0.9.0.
RENAME_TABLES = {"addressbooks": "con_address_books", "contacts": "con_contacts", "contact_emails": "con_contact_emails",
                 "contact_phones": "con_contact_phones", "contact_addresses": "con_contact_addresses", "contact_urls": "con_contact_urls",
                 "contact_social": "con_contact_social_profiles", "contact_dates": "con_contact_dates", "contact_tags": "con_contact_tags",
                 "relations": "con_contact_relations", "not_duplicates": "con_contact_non_duplicates", "merges": "con_contact_merges",
                 "suggestions": "con_contact_suggestions", "calendar_tokens": "con_feed_tokens"}
_CHILDREN = ("con_contact_emails", "con_contact_phones", "con_contact_addresses", "con_contact_urls", "con_contact_social_profiles",
             "con_contact_dates", "con_contact_relations")
RENAME_COLUMNS = {
    "con_address_books": {"created": "created_at"},
    "con_contacts": {"book_id": "address_book_id", "created": "created_at", "updated": "updated_at"},
    **{t: {"pos": "position"} for t in _CHILDREN},
    "con_contact_non_duplicates": {"a": "contact_id", "b": "other_contact_id", "created": "created_at"},
    "con_contact_merges": {"keep_id": "kept_contact_id", "created": "created_at", "undone": "undone_at"},
    "con_contact_suggestions": {"by_user_id": "created_by", "created": "created_at", "decided": "decided_at"},
    "con_feed_tokens": {"created": "created_at"},
}
RENAME_INDEXES = {
    "con_contacts": {"book_id": "uq_con_contacts_book_href", "book_id_2": "idx_con_contacts_book_uid",
                     "book_id_3": "idx_con_contacts_book_changes", "fn": "idx_con_contacts_fn", "iopix_person_id": "idx_con_contacts_iopix_person"},
    "con_contact_emails": {"contact_id": "idx_con_contact_emails_contact", "value": "idx_con_contact_emails_value"},
    "con_contact_phones": {"contact_id": "idx_con_contact_phones_contact", "value": "idx_con_contact_phones_value"},
    "con_contact_addresses": {"contact_id": "idx_con_contact_addresses_contact"},
    "con_contact_urls": {"contact_id": "idx_con_contact_urls_contact"},
    "con_contact_social_profiles": {"contact_id": "idx_con_contact_social_profiles_contact"},
    "con_contact_dates": {"contact_id": "idx_con_contact_dates_contact"},
    "con_contact_tags": {"tag": "idx_con_contact_tags_tag"},
    "con_contact_relations": {"contact_id": "idx_con_contact_relations_contact", "related_id": "idx_con_contact_relations_related"},
    "con_contact_merges": {"keep_id": "idx_con_contact_merges_kept"},
    "con_contact_suggestions": {"contact_id": "idx_con_contact_suggestions_contact_status", "one_value": "uq_con_contact_suggestions_value"},
    "con_feed_tokens": {"token": "uq_con_feed_tokens_token"},
}


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
    r = one("SELECT value FROM con_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM con_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO con_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


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


# columns added after a table was first made (MariaDB: ADD COLUMN IF NOT EXISTS). Schema 4: whether a birthday goes
# into the birthday feeds (calendar, upcoming, the suite); existing birthdays stay on
UPGRADES = [
    "ALTER TABLE con_contacts ADD COLUMN IF NOT EXISTS bday_remind TINYINT NOT NULL DEFAULT 1 AFTER bday_day",
]


def _address_book_owner_key(cur) -> None:
    """0.9.0: the unique slug of an address book takes owner_key (shared ones too: NULL owner_ids never clashed), as
    ioCalendar's calendars do. A shared slug that is already there twice gets its id appended first."""
    if "owner_key" in schema.columns(cur, "con_address_books"):
        return
    cur.execute("UPDATE con_address_books b JOIN (SELECT slug, MIN(id) AS keep FROM con_address_books WHERE owner_id IS NULL "
                "GROUP BY slug HAVING COUNT(*) > 1) d ON d.slug = b.slug AND b.owner_id IS NULL AND b.id <> d.keep "
                "SET b.slug = CONCAT(b.slug, '-', b.id)")
    cur.execute("ALTER TABLE con_address_books ADD COLUMN owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT, "
                "DROP INDEX owner_id, ADD UNIQUE INDEX uq_con_address_books_owner_slug (owner_key, slug)")


def _meta_to_settings(cur) -> None:
    """0.9.0: the meta table's settings rows (setting:<name>) move to con_settings; its schema row is replaced by
    con_schema_version."""
    if "meta" in schema.tables(cur):
        cur.execute("INSERT IGNORE INTO con_settings (name, value) "
                    "SELECT SUBSTRING(k, 9), COALESCE(v, '') FROM meta WHERE k LIKE 'setting:%'")
        cur.execute("DROP TABLE meta")


def migrate() -> None:
    ensure_database()
    with tx() as con, con.cursor() as cur:
        done = schema.rename(cur, RENAME_TABLES, RENAME_COLUMNS)
        if "con_address_books" in schema.tables(cur):
            _address_book_owner_key(cur)
        for stmt in SCHEMA:
            cur.execute(stmt + " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        for stmt in UPGRADES:
            cur.execute(stmt)
        done += schema.rename(cur, None, None, RENAME_INDEXES)
        _meta_to_settings(cur)
        schema.ensure_version_table(cur, PREFIX)
        schema.record_version(cur, PREFIX, SCHEMA_VERSION)
        if done:
            logging.getLogger("app.db").info("renamed to the suite naming convention: %s", ", ".join(done))
        # the family address book everyone shares
        cur.execute("SELECT id FROM con_address_books WHERE owner_id IS NULL LIMIT 1")
        if not cur.fetchone():
            cur.execute("INSERT INTO con_address_books (owner_id, slug, name, description) VALUES "
                        "(NULL, 'family', 'Family', 'Shared with everyone in the family')")


def reset_all() -> None:
    """Tests only: drop every table of this app (con_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_") or t == "meta" or t in RENAME_TABLES:
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
