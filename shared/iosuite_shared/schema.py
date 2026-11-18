"""Schema helpers every app's database code uses: what tables, columns and indexes exist, and the schema_version table.

The suite's naming convention: tables `<app prefix>_<name>`, `*_at` timestamps, `name`/`value` key-value columns,
`idx_`/`uq_` index names.

The functions take a PyMySQL cursor (tuple or dict rows) and run on the cursor's database.

create() is how an app makes its tables at every start: the CREATE TABLE IF NOT EXISTS statements of its SCHEMA, and
for a table that was there already, the columns and the indexes its statement names and the table lacks. So a column
added to SCHEMA reaches a database made before it, with nothing to write for it and nothing to take out later. It
adds, and only adds: a column whose definition changed, was renamed or was dropped stays as the database has it.
"""
import logging
import re

log = logging.getLogger("iosuite_shared.schema")


def _rows(cur, sql: str, args=None) -> list:
    cur.execute(sql, args)
    return [tuple(r.values()) if isinstance(r, dict) else tuple(r) for r in cur.fetchall()]


def tables(cur) -> set:
    return {r[0] for r in _rows(cur, "SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")}


def columns(cur, table: str) -> set:
    return {r[0] for r in _rows(cur, "SELECT column_name FROM information_schema.columns "
                                     "WHERE table_schema = DATABASE() AND table_name = %s", (table,))}


def indexes(cur, table: str) -> set:
    return {r[0] for r in _rows(cur, "SELECT DISTINCT index_name FROM information_schema.statistics "
                                     "WHERE table_schema = DATABASE() AND table_name = %s", (table,))}


def version_table(prefix: str) -> str:
    return f"{prefix}_schema_version"


def ensure_version_table(cur, prefix: str, options: str = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"):
    cur.execute(f"CREATE TABLE IF NOT EXISTS {version_table(prefix)} (version INT PRIMARY KEY, applied_at DATETIME(3) NOT NULL)" + options)


def current_version(cur, prefix: str) -> int:
    rows = _rows(cur, f"SELECT COALESCE(MAX(version), 0) FROM {version_table(prefix)}")
    return int(rows[0][0]) if rows else 0


def record_version(cur, prefix: str, version: int):
    """Record that the schema is at `version` (idempotent)."""
    cur.execute(f"INSERT IGNORE INTO {version_table(prefix)} (version, applied_at) VALUES (%s, UTC_TIMESTAMP(3))", (version,))


# ---- the tables of a SCHEMA, and what an older database lacks of them
_TABLE = re.compile(r"\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?(\w+)`?\s*\(", re.I)
# a column's type that takes brackets: `key VARCHAR(64)` is a column named key, not an index named VARCHAR
_TYPES = ("VARCHAR|CHAR|VARBINARY|BINARY|TINYINT|SMALLINT|MEDIUMINT|INT|INTEGER|BIGINT|DECIMAL|NUMERIC|FLOAT|DOUBLE|"
          "DATETIME|TIMESTAMP|TIME|BIT|ENUM|SET")
_INDEX = re.compile(rf"^(?:(?:UNIQUE|FULLTEXT|SPATIAL)\s+)?(?:INDEX|KEY)\s+(?!(?:{_TYPES})\s*\()[`\"]?(\w+)[`\"]?\s*\(", re.I)
# what is neither a column nor an index with a name: left as the table has it
_CONSTRAINT = re.compile(r"^(PRIMARY\s+KEY|FOREIGN\s+KEY|CONSTRAINT\b|CHECK\s*\(|(UNIQUE|FULLTEXT|SPATIAL)(\s+(INDEX|KEY))?\s*\(|(INDEX|KEY)\s*\()", re.I)
_ALREADY = (1060, 1061)  # duplicate column, duplicate index name: another process of the app added it a moment ago


def declared(create_sql: str) -> tuple:
    """(columns, indexes) of a CREATE TABLE statement, each {name: definition} in the statement's order. Constraints
    without a name of their own (PRIMARY KEY (a, b), UNIQUE (a), FOREIGN KEY ...) are in neither."""
    body = create_sql[create_sql.index("(") + 1:create_sql.rindex(")")]
    defs, depth, cur, quote = [], 0, [], ""
    for ch in body:  # split on the commas between definitions, not those inside VARCHAR(191) or DEFAULT 'a, b'
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not quote:
            defs.append("".join(cur)); cur = []
        else:
            cur.append(ch)
    defs.append("".join(cur))
    columns, indexes = {}, {}
    for d in (" ".join(d.split()) for d in defs):
        m = _INDEX.match(d)
        if m:
            indexes[m.group(1)] = d
        elif d and not _CONSTRAINT.match(d):
            columns[d.split()[0].strip('`"')] = d
    return columns, indexes


def _by_table(cur, sql: str) -> dict:
    out = {}
    for table, name in _rows(cur, sql):
        out.setdefault(table, set()).add(name.lower())
    return out


def _add(cur, table: str, what: str) -> bool:
    try:
        cur.execute(f"ALTER TABLE `{table}` ADD {what}")
    except Exception as e:
        if e.args and e.args[0] in _ALREADY:
            return False
        raise
    return True


def create(cur, statements, options: str = "") -> list:
    """Run an app's SCHEMA: every statement (with `options` after it: the engine and the character set), and for each
    table that was there before, the columns and named indexes its statement has and the table lacks. Returns what
    was added to tables that were there, as "table.column" and "table.index".

    A column is added with its definition as written, after the column the statement has before it. One that cannot
    be added as written (NOT NULL without a default on a type that has none) stops the start with the database's
    error: give it a DEFAULT. An index that cannot be added (a UNIQUE one over rows that are not) is logged and left
    out, so the app starts as it did before the index was written."""
    before = tables(cur)
    columns = indexes = None
    added = []
    for stmt in statements:
        cur.execute(stmt + options)
        m = _TABLE.match(stmt)
        if not m or m.group(1) not in before:
            continue
        table = m.group(1)
        if columns is None:  # asked once, and only when a table was there already
            columns = _by_table(cur, "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = DATABASE()")
            indexes = _by_table(cur, "SELECT DISTINCT table_name, index_name FROM information_schema.statistics WHERE table_schema = DATABASE()")
        want_columns, want_indexes = declared(stmt)
        have, previous = columns.get(table, set()), None
        for name, definition in want_columns.items():
            if name.lower() not in have:
                where = f" AFTER `{previous}`" if previous else ""
                if _add(cur, table, f"COLUMN {definition}{where}"):
                    added.append(f"{table}.{name}")
                have.add(name.lower())
            previous = name
        have = indexes.get(table, set())
        for name, definition in want_indexes.items():
            if name.lower() in have:
                continue
            try:
                if _add(cur, table, definition):
                    added.append(f"{table}.{name}")
            except Exception as e:
                log.error("%s: the index %s could not be added (%s); the table stays without it", table, name, e)
    if added:
        log.info("added to the tables that were there: %s", ", ".join(added))
    return added
