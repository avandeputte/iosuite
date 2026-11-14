"""MariaDB access: one short connection per unit of work, and the schema (created and migrated at start)."""

import pymysql
from pymysql.cursors import DictCursor

from app import config

from iosuite_shared import db as shared_db, schema

SCHEMA_VERSION = 2   # 2: several photos (rcp_photos by id, one may belong to a step), rcp_marks, rcp_books
PREFIX = "rcp"

# Every table is rcp_<name> (the suite's naming convention: the apps can share one database) and InnoDB/utf8mb4.
SCHEMA = [
    """CREATE TABLE IF NOT EXISTS rcp_settings (
        name VARCHAR(191) PRIMARY KEY,
        value MEDIUMTEXT NOT NULL,
        updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3)
    )""",
    # accounts and app passwords live in the Shared ioSuite database (iosuite-shared, app/auth.py)
    # owner_id NULL: a family recipe (everyone sees it); otherwise the private recipe of that account.
    # ingredients, steps and tags are JSON lists of strings; a line of ingredients or steps that ends with a colon
    # ("For the icing:") is a heading. Times are minutes. words: everything a search looks in, in lower case.
    # photo: the id in rcp_photos of the picture the cards show (the first of the recipe's own; 0: none).
    """CREATE TABLE IF NOT EXISTS rcp_recipes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        title VARCHAR(255) NOT NULL,
        description TEXT NULL,
        servings VARCHAR(64) NULL,
        prep_minutes INT NULL,
        cook_minutes INT NULL,
        total_minutes INT NULL,
        ingredients MEDIUMTEXT NOT NULL,
        steps MEDIUMTEXT NOT NULL,
        notes TEXT NULL,
        tags TEXT NOT NULL,
        source_url VARCHAR(2048) NULL,
        source_name VARCHAR(255) NULL,
        photo INT NOT NULL DEFAULT 0,
        words MEDIUMTEXT NOT NULL,
        created_by INT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        KEY idx_rcp_recipes_owner (owner_id, title)
    )""",
    # the pictures, as JPEG: the picture the page shows and a small one for the cards. step NULL: one of the recipe's
    # own, in the order of position (the first is the one the cards show); otherwise the picture of that step (its
    # place in the recipe's steps, from 0).
    """CREATE TABLE IF NOT EXISTS rcp_photos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        recipe_id INT NOT NULL,
        step INT NULL,
        position INT NOT NULL DEFAULT 0,
        picture MEDIUMBLOB NOT NULL,
        thumb MEDIUMBLOB NOT NULL,
        width INT NOT NULL,
        height INT NOT NULL,
        KEY idx_rcp_photos_recipe (recipe_id, position),
        CONSTRAINT fk_rcp_photos_recipe FOREIGN KEY (recipe_id) REFERENCES rcp_recipes(id) ON DELETE CASCADE
    )""",
    # what one account thinks of a recipe: a favourite or not, and its rating (1 to 5, NULL: none)
    """CREATE TABLE IF NOT EXISTS rcp_marks (
        recipe_id INT NOT NULL,
        user_id INT NOT NULL,
        favourite TINYINT(1) NOT NULL DEFAULT 0,
        rating TINYINT NULL,
        PRIMARY KEY (recipe_id, user_id),
        KEY idx_rcp_marks_user (user_id, favourite),
        CONSTRAINT fk_rcp_marks_recipe FOREIGN KEY (recipe_id) REFERENCES rcp_recipes(id) ON DELETE CASCADE
    )""",
    # cookbooks: owner_id NULL is a family cookbook (everyone sees it, it holds family recipes); otherwise the private
    # cookbook of that account, which may hold the family's recipes and its own
    """CREATE TABLE IF NOT EXISTS rcp_books (
        id INT AUTO_INCREMENT PRIMARY KEY,
        owner_id INT NULL,
        name VARCHAR(191) NOT NULL,
        description TEXT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_rcp_books_owner (owner_id, name)
    )""",
    """CREATE TABLE IF NOT EXISTS rcp_book_recipes (
        book_id INT NOT NULL,
        recipe_id INT NOT NULL,
        added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (book_id, recipe_id),
        KEY idx_rcp_book_recipes_recipe (recipe_id),
        CONSTRAINT fk_rcp_book_recipes_book FOREIGN KEY (book_id) REFERENCES rcp_books(id) ON DELETE CASCADE,
        CONSTRAINT fk_rcp_book_recipes_recipe FOREIGN KEY (recipe_id) REFERENCES rcp_recipes(id) ON DELETE CASCADE
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
    r = one("SELECT value FROM rcp_settings WHERE name = %s", (k,))
    return r["value"] if r else default


def set_setting(k: str, v: str | None) -> None:
    if v is None:
        ex("DELETE FROM rcp_settings WHERE name = %s", (k,))
    else:
        ex("INSERT INTO rcp_settings (name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)", (k, v))


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
    """Tests only: drop every table of this app (rcp_*; the database may hold the other apps' too)."""
    with tx() as con, con.cursor() as cur:
        cur.execute("SET FOREIGN_KEY_CHECKS = 0")
        for t in schema.tables(cur):
            if t.startswith(PREFIX + "_"):
                cur.execute(f"DROP TABLE `{t}`")
        cur.execute("SET FOREIGN_KEY_CHECKS = 1")
