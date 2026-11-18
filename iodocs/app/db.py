"""MariaDB access: one short connection per unit of work, and the schema (created at start)."""

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 1  # recorded in doc_schema_version; the tables are made as SCHEMA says, and get the columns and indexes added to it later (schema.create)
PREFIX = "doc"

# Every table is doc_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
# Who sees which document is app/model.py's (visible_sql): each one says who may see it.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS doc_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite-shared, app/auth.py)
    # a document: a passport, a driver's license, an insurance policy, a birth certificate... kind: one of
    # model.KINDS. number: the passport's or the policy's number; issuer: who gave it (a country's passport office, a
    # state's DMV, an insurer); country: a country code (US, BE) or name. Dates are days. remind_days: how many days
    # before expires_on a reminder goes (NULL: the kind's usual, 0: none). visibility: family (everyone with a role
    # here), people (the people it is for, whoever added it, editors and admins) or private (the people it is for and
    # whoever added it, nobody else). fields: its own details as a JSON list of {name, value} (nationality, class,
    # coverage...). cover: the id in doc_files of the picture the cards show (0: none). words: everything a search looks
    # in, the text read off its scans too, in lower case. renewed_by: the document that took its place.
    """CREATE TABLE IF NOT EXISTS doc_documents (
        id INT AUTO_INCREMENT PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        kind VARCHAR(24) NOT NULL,
        number VARCHAR(191) NULL,
        issuer VARCHAR(255) NULL,
        country VARCHAR(64) NULL,
        issued_on DATE NULL,
        expires_on DATE NULL,
        remind_days INT NULL,
        visibility VARCHAR(8) NOT NULL DEFAULT 'people',
        archived TINYINT(1) NOT NULL DEFAULT 0,
        renewed_by INT NULL,
        notes MEDIUMTEXT NULL,
        fields MEDIUMTEXT NOT NULL,
        cover INT NOT NULL DEFAULT 0,
        words MEDIUMTEXT NOT NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_doc_documents_expires (archived, expires_on),
        KEY idx_doc_documents_kind (kind),
        KEY idx_doc_documents_by (created_by)
    )""",
    # whose a document is: the people of the family (the suite's one list, iosuite_shared.family). user_id is the
    # account in the Shared ioSuite database.
    """CREATE TABLE IF NOT EXISTS doc_people (
        doc_id INT NOT NULL,
        user_id INT NOT NULL,
        PRIMARY KEY (doc_id, user_id),
        KEY idx_doc_people_user (user_id),
        CONSTRAINT fk_doc_people_doc FOREIGN KEY (doc_id) REFERENCES doc_documents(id) ON DELETE CASCADE
    )""",
    # its scans and files: the front, the back, the pages of a policy. The bytes are in doc_file_parts, in parts of
    # PART_BYTES; thumb: a small JPEG of a picture (or of a PDF's first page). text: what OCR read off it (app/ocr.py);
    # found: what was made of that, as JSON ({kind, number, expiresOn, ...}); read_at: when it was read (NULL: not yet).
    """CREATE TABLE IF NOT EXISTS doc_files (
        id INT AUTO_INCREMENT PRIMARY KEY,
        doc_id INT NOT NULL,
        name VARCHAR(255) NOT NULL,
        mime VARCHAR(127) NOT NULL,
        size BIGINT NOT NULL,
        sha256 CHAR(64) NOT NULL,
        thumb MEDIUMBLOB NULL,
        position INT NOT NULL DEFAULT 0,
        text MEDIUMTEXT NULL,
        found MEDIUMTEXT NULL,
        read_at TIMESTAMP NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_doc_files_doc (doc_id, position),
        CONSTRAINT fk_doc_files_doc FOREIGN KEY (doc_id) REFERENCES doc_documents(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS doc_file_parts (
        file_id INT NOT NULL,
        n INT NOT NULL,
        data MEDIUMBLOB NOT NULL,
        PRIMARY KEY (file_id, n),
        CONSTRAINT fk_doc_file_parts_file FOREIGN KEY (file_id) REFERENCES doc_files(id) ON DELETE CASCADE
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
tx, q, one, ex, many = _db.tx, _db.q, _db.one, _db.ex, _db.many


def marks(n: int) -> str:
    return ",".join(["%s"] * n) if n else "NULL"


def get_setting(k: str, default: str | None = None) -> str | None:
    r = one("SELECT value FROM doc_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM doc_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO doc_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


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
        schema.create(cur, SCHEMA, " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci")
        schema.ensure_version_table(cur, PREFIX)
        schema.record_version(cur, PREFIX, SCHEMA_VERSION)


def reset_all() -> None:
    """Tests only: drop every table of this app (doc_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
