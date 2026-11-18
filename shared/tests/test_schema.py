"""A fresh Shared ioSuite database gets every table, with the suite's names, and records its schema version."""
from iosuite_shared import db, schema


def test_fresh_database_has_every_table():
    db.init()
    with db.tx() as con, con.cursor() as cur:
        assert {"ios_users", "ios_user_roles", "ios_user_data", "ios_sessions", "ios_app_passwords", "ios_settings",
                "ios_apps", "ios_credentials", "ios_updates", "ios_schema_version"} <= schema.tables(cur)
        assert schema.current_version(cur, "ios") == db.SCHEMA_VERSION
        assert "uq_ios_users_email" in schema.indexes(cur, "ios_users")
        assert "idx_ios_app_passwords_user" in schema.indexes(cur, "ios_app_passwords")
        assert {"ip", "last_seen_at", "last_ip"} <= schema.columns(cur, "ios_sessions")


# ---- schema.create: a column or an index added to SCHEMA reaches a database made before it
OLD = "CREATE TABLE IF NOT EXISTS tst_things (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(64) NOT NULL)"
NEW = """CREATE TABLE IF NOT EXISTS tst_things (
    id INT AUTO_INCREMENT PRIMARY KEY,
    owner_id INT NULL,
    name VARCHAR(64) NOT NULL,
    `key` VARCHAR(32) NOT NULL DEFAULT 'a, (b',
    price DECIMAL(10,2) NOT NULL DEFAULT 0,
    owner_key INT AS (COALESCE(owner_id, 0)) PERSISTENT,
    UNIQUE KEY uq_tst_things_owner_name (owner_key, name),
    KEY idx_tst_things_price (price),
    FULLTEXT INDEX idx_tst_things_text (name)
)"""
OPTIONS = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"


def _column_order(cur, table):
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = %s "
                "ORDER BY ordinal_position", (table,))
    return [list(r.values())[0] if isinstance(r, dict) else r[0] for r in cur.fetchall()]


def test_declared_tells_columns_from_indexes_and_constraints():
    columns, indexes = schema.declared(NEW + OPTIONS)
    assert list(columns) == ["id", "owner_id", "name", "key", "price", "owner_key"]
    assert columns["key"] == "`key` VARCHAR(32) NOT NULL DEFAULT 'a, (b'" and columns["price"] == "price DECIMAL(10,2) NOT NULL DEFAULT 0"
    assert list(indexes) == ["uq_tst_things_owner_name", "idx_tst_things_price", "idx_tst_things_text"]
    # a column named key is a column; constraints without a name of their own are neither
    columns, indexes = schema.declared("CREATE TABLE IF NOT EXISTS t (key VARCHAR(10), a INT, b INT, PRIMARY KEY (a, b), "
                                       "UNIQUE (b), INDEX (a), FOREIGN KEY (a) REFERENCES u (id), CHECK (a > 0), KEY old_name (a))")
    assert list(columns) == ["key", "a", "b"] and list(indexes) == ["old_name"]


def test_create_adds_what_an_older_table_lacks():
    with db.tx() as con, con.cursor() as cur:
        assert schema.create(cur, [NEW], OPTIONS) == [], "a table made now has everything: nothing is added"
        cur.execute("DROP TABLE tst_things")
        cur.execute(OLD + OPTIONS)
        cur.execute("INSERT INTO tst_things (name) VALUES ('boiler'), ('ladder')")
        added = schema.create(cur, [NEW], OPTIONS)
        assert added == ["tst_things.owner_id", "tst_things.key", "tst_things.price", "tst_things.owner_key",
                         "tst_things.uq_tst_things_owner_name", "tst_things.idx_tst_things_price", "tst_things.idx_tst_things_text"]
        assert _column_order(cur, "tst_things") == ["id", "owner_id", "name", "key", "price", "owner_key"], "each after the one before it"
        assert {"uq_tst_things_owner_name", "idx_tst_things_price", "idx_tst_things_text"} <= schema.indexes(cur, "tst_things")
        cur.execute("SELECT name, `key`, price, owner_key FROM tst_things ORDER BY id")
        rows = [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]
        assert rows == [("boiler", "a, (b", 0, 0), ("ladder", "a, (b", 0, 0)], "the rows that were there get the defaults"
        assert schema.create(cur, [NEW], OPTIONS) == [], "a second start adds nothing"
        cur.execute("DROP TABLE tst_things")


def test_create_leaves_out_an_index_the_rows_do_not_allow(caplog):
    with db.tx() as con, con.cursor() as cur:
        cur.execute(OLD + OPTIONS)
        cur.execute("INSERT INTO tst_things (name) VALUES ('same'), ('same')")
        wanted = OLD[:-1] + ", note VARCHAR(16) NULL, UNIQUE KEY uq_tst_things_name (name))"
        assert schema.create(cur, [wanted], OPTIONS) == ["tst_things.note"], "the column is added; the app starts"
        assert "uq_tst_things_name" not in schema.indexes(cur, "tst_things")
        assert "uq_tst_things_name could not be added" in caplog.text
        cur.execute("DROP TABLE tst_things")


def test_create_stops_on_a_column_that_cannot_be_added():
    import pymysql
    import pytest
    with db.tx() as con, con.cursor() as cur:
        cur.execute(OLD + OPTIONS)
        with pytest.raises(pymysql.MySQLError):  # a second AUTO_INCREMENT column: the database's own error, not a silent skip
            schema.create(cur, [OLD[:-1] + ", n INT AUTO_INCREMENT)"], OPTIONS)
        cur.execute("DROP TABLE tst_things")


def test_the_shared_database_gets_a_column_added_to_its_schema(monkeypatch):
    db.init()
    with db.tx() as con, con.cursor() as cur:
        cur.execute("ALTER TABLE ios_sessions DROP COLUMN last_ip")  # a database made before last_ip
    monkeypatch.setattr(db, "_ready", False)
    db.init()
    with db.tx() as con, con.cursor() as cur:
        assert "last_ip" in schema.columns(cur, "ios_sessions")
