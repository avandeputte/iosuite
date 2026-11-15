"""MariaDB access: one short connection per unit of work, and the schema (created at start)."""

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 1  # recorded in thg_schema_version; the tables are made as SCHEMA says (pre-release: no upgrade steps)
PREFIX = "thg"

# Every table is thg_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
# Everything is the household's: whoever has a role here sees every thing; who may change what is app/model.py's.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS thg_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite-shared, app/auth.py)
    # where things are: a tree (the house, the kitchen, the drawer by the sink); parent_id NULL: at the top
    """CREATE TABLE IF NOT EXISTS thg_locations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        parent_id INT NULL,
        name VARCHAR(191) NOT NULL,
        description TEXT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_hom_locations_parent (parent_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS thg_labels (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(100) NOT NULL,
        color VARCHAR(16) NULL,
        UNIQUE KEY uq_hom_labels_name (name)
    )""",
    # a thing. Dates are days; prices are in the currency of Settings › Things. fields: the thing's
    # own details as a JSON list of {name, value}. photo: the id in thg_files of the picture the cards show (0: none).
    # words: everything a search looks in, in lower case. import_ref: Homebox's HB.import_ref, so that importing the
    # same export again changes the things it brought instead of adding them twice.
    """CREATE TABLE IF NOT EXISTS thg_items (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        description TEXT NULL,
        location_id INT NULL,
        quantity INT NOT NULL DEFAULT 1,
        manufacturer VARCHAR(255) NULL,
        model_number VARCHAR(255) NULL,
        serial_number VARCHAR(255) NULL,
        asset_id VARCHAR(64) NULL,
        url VARCHAR(2048) NULL,
        purchase_date DATE NULL,
        purchase_price DECIMAL(14,2) NULL,
        purchase_from VARCHAR(255) NULL,
        warranty_expires DATE NULL,
        lifetime_warranty TINYINT(1) NOT NULL DEFAULT 0,
        warranty_details TEXT NULL,
        insured TINYINT(1) NOT NULL DEFAULT 0,
        archived TINYINT(1) NOT NULL DEFAULT 0,
        sold_date DATE NULL,
        sold_price DECIMAL(14,2) NULL,
        sold_to VARCHAR(255) NULL,
        sold_notes TEXT NULL,
        notes MEDIUMTEXT NULL,
        fields MEDIUMTEXT NOT NULL,
        photo INT NOT NULL DEFAULT 0,
        words MEDIUMTEXT NOT NULL,
        import_ref VARCHAR(191) NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_hom_items_location (location_id),
        KEY idx_hom_items_name (archived, name),
        KEY idx_hom_items_warranty (warranty_expires),
        UNIQUE KEY uq_hom_items_import (import_ref),
        CONSTRAINT fk_hom_items_location FOREIGN KEY (location_id) REFERENCES thg_locations(id) ON DELETE SET NULL
    )""",
    """CREATE TABLE IF NOT EXISTS thg_item_labels (
        item_id INT NOT NULL,
        label_id INT NOT NULL,
        PRIMARY KEY (item_id, label_id),
        KEY idx_hom_item_labels_label (label_id),
        CONSTRAINT fk_hom_item_labels_item FOREIGN KEY (item_id) REFERENCES thg_items(id) ON DELETE CASCADE,
        CONSTRAINT fk_hom_item_labels_label FOREIGN KEY (label_id) REFERENCES thg_labels(id) ON DELETE CASCADE
    )""",
    # what comes with a thing: its photos, its manual, the receipt, the warranty card, anything else. kind: photo,
    # manual, receipt, warranty or other. The bytes are in thg_file_parts, in parts of PART_BYTES (a database server's
    # max_allowed_packet stays out of the way of a 100 MB manual); thumb: a small JPEG for a picture (NULL otherwise).
    """CREATE TABLE IF NOT EXISTS thg_files (
        id INT AUTO_INCREMENT PRIMARY KEY,
        item_id INT NOT NULL,
        kind VARCHAR(16) NOT NULL,
        name VARCHAR(255) NOT NULL,
        mime VARCHAR(127) NOT NULL,
        size BIGINT NOT NULL,
        sha256 CHAR(64) NOT NULL,
        thumb MEDIUMBLOB NULL,
        position INT NOT NULL DEFAULT 0,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_hom_files_item (item_id, kind, position),
        CONSTRAINT fk_hom_files_item FOREIGN KEY (item_id) REFERENCES thg_items(id) ON DELETE CASCADE
    )""",
    """CREATE TABLE IF NOT EXISTS thg_file_parts (
        file_id INT NOT NULL,
        n INT NOT NULL,
        data MEDIUMBLOB NOT NULL,
        PRIMARY KEY (file_id, n),
        CONSTRAINT fk_hom_file_parts_file FOREIGN KEY (file_id) REFERENCES thg_files(id) ON DELETE CASCADE
    )""",
    # upkeep: what a thing needs every so often (the boiler's service every year, the car's MOT, the filter every
    # three months). every: a number of days, weeks, months or years; next_due: the day it is due next. When ioTask is
    # in the suite the upkeep is a repeating task there too: task_id (ioTask's id of it), task_list, and task_by (the
    # account that made it, in whose list it is).
    """CREATE TABLE IF NOT EXISTS thg_upkeep (
        id INT AUTO_INCREMENT PRIMARY KEY,
        item_id INT NOT NULL,
        title VARCHAR(255) NOT NULL,
        every_n INT NOT NULL,
        every_unit VARCHAR(8) NOT NULL,
        next_due DATE NOT NULL,
        notes TEXT NULL,
        task_id VARCHAR(64) NULL,
        task_list INT NULL,
        task_by INT NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_hom_upkeep_due (next_due),
        KEY idx_hom_upkeep_item (item_id),
        CONSTRAINT fk_hom_upkeep_item FOREIGN KEY (item_id) REFERENCES thg_items(id) ON DELETE CASCADE
    )""",
    # what was done to a thing, and when: a service, a repair, a part replaced; upkeep_id: the upkeep it was (NULL: a
    # one-off). cost in the currency.
    """CREATE TABLE IF NOT EXISTS thg_maintenance (
        id INT AUTO_INCREMENT PRIMARY KEY,
        item_id INT NOT NULL,
        upkeep_id INT NULL,
        done_on DATE NOT NULL,
        title VARCHAR(255) NOT NULL,
        notes TEXT NULL,
        cost DECIMAL(14,2) NULL,
        done_by VARCHAR(255) NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_hom_maintenance_item (item_id, done_on),
        CONSTRAINT fk_hom_maintenance_item FOREIGN KEY (item_id) REFERENCES thg_items(id) ON DELETE CASCADE,
        CONSTRAINT fk_hom_maintenance_upkeep FOREIGN KEY (upkeep_id) REFERENCES thg_upkeep(id) ON DELETE SET NULL
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
    r = one("SELECT value FROM thg_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM thg_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO thg_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


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


def reset_all() -> None:
    """Tests only: drop every table of this app (thg_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
