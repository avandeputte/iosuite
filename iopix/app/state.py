"""The app's own writable state: favorites, app-side albums, settings, users, the
pending-edit and tag-manager queues, and (through analysis.py and consistency.py,
which share the database) the analysis results.

Everything lives in the viewer's own database (vdb.py: the SQLite file data/viewer.db
by default, or MySQL/MariaDB), never in digiKam's database. Photos are referenced by
digiKam image id; the file hash is stored alongside so entries could be re-matched if
digiKam ever renumbers its images. Installs from before v1.8 had two SQLite files,
state.db and analysis.db: migrate_legacy() folds them into viewer.db once, keeping
every row, and parks the old files in db-backups.
"""
import logging
import shutil
import sqlite3
import threading
import time

from . import config

STATE_DB = config.DATA_DIR / "viewer.db"  # the SQLite file (vdb.SQLITE_FILE); the legacy migration's target
LEGACY = (config.DATA_DIR / "state.db", config.DATA_DIR / "analysis.db")
rev = 0  # bumped on every write so cached query results can be invalidated
_lock = threading.Lock()
_settings = (-1, {})  # (stamp it was read at, {key: value}); settings are read on every poll and every POST


def migrate_legacy():
    """state.db + analysis.db -> viewer.db, once. Returns where the old files were parked, or None."""
    if STATE_DB.exists() or not any(p.exists() for p in LEGACY):
        return None
    old_state, old_an = LEGACY
    tmp = STATE_DB.with_name(STATE_DB.name + ".migrating")
    tmp.unlink(missing_ok=True)
    if old_state.exists():  # the state file is the base: same tables, same ids
        src = sqlite3.connect(f"file:{old_state}?mode=ro", uri=True)
        try:
            dst = sqlite3.connect(tmp)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
    con = sqlite3.connect(tmp)
    try:
        if old_an.exists():  # the analysis tables are copied over, schema and rows (no name overlaps)
            con.execute("ATTACH DATABASE ? AS a", (str(old_an),))
            tables = con.execute("SELECT name, sql FROM a.sqlite_master WHERE type = 'table' AND sql IS NOT NULL").fetchall()
            for name, sql in tables:
                con.execute(sql)
                con.execute(f'INSERT INTO main."{name}" SELECT * FROM a."{name}"')
            for (sql,) in con.execute("SELECT sql FROM a.sqlite_master WHERE type = 'index' AND sql IS NOT NULL").fetchall():
                con.execute(sql)
            con.commit()
            con.execute("DETACH DATABASE a")
        con.execute("PRAGMA journal_mode = WAL")
        con.commit()
    finally:
        con.close()
    tmp.replace(STATE_DB)
    park = config.DATA_DIR / "db-backups" / ("migrated-" + time.strftime("%Y%m%d-%H%M%S"))
    park.mkdir(parents=True, exist_ok=True)
    for f in LEGACY:
        for g in (f, f.with_name(f.name + "-wal"), f.with_name(f.name + "-shm"), f.with_name(f.name + "-journal")):
            if g.exists():
                shutil.move(str(g), str(park / g.name))
    return park


def connect():
    """The viewer database, SQLite or MySQL as configured (see vdb.py); rows answer to names and indexes."""
    from . import vdb
    return vdb.connect(timeout=10)


def init():
    from . import vdb
    park = migrate_legacy()
    if park:
        logging.getLogger("app.state").info("state.db and analysis.db were folded into viewer.db; the old files are in %s", park)
    vdb.init()  # the tables of every module, on whichever database is configured


def _write(fn):
    global rev
    with _lock:
        con = connect()
        try:
            out = fn(con)
            con.commit()
        finally:
            con.close()
        rev += 1
        return out


def summary() -> dict:
    con = connect()
    try:
        return {
            "favorites": [r[0] for r in con.execute("SELECT photo_id FROM favorites ORDER BY added DESC")],
            "albums": [dict(r) for r in con.execute(
                "SELECT a.id, a.name, a.created, count(i.photo_id) AS n, "
                "(SELECT photo_id FROM ualbum_items WHERE album_id = a.id ORDER BY added, photo_id LIMIT 1) AS cover "
                "FROM ualbums a LEFT JOIN ualbum_items i ON i.album_id = a.id GROUP BY a.id ORDER BY a.created DESC")],
        }
    finally:
        con.close()


def set_favorites(items: list, on: bool):
    """items: [(photo_id, hash)]"""
    now = int(time.time())
    if on:
        _write(lambda c: c.executemany("INSERT OR IGNORE INTO favorites VALUES (?,?,?)", [(i, h, now) for i, h in items]))
    else:
        _write(lambda c: c.executemany("DELETE FROM favorites WHERE photo_id = ?", [(i,) for i, _ in items]))


def create_album(name: str) -> int:
    return _write(lambda c: c.execute("INSERT INTO ualbums (name, created) VALUES (?,?)", (name, int(time.time()))).lastrowid)


def rename_album(album_id: int, name: str):
    _write(lambda c: c.execute("UPDATE ualbums SET name = ? WHERE id = ?", (name, album_id)))


def delete_album(album_id: int):
    def run(c):
        c.execute("DELETE FROM ualbum_items WHERE album_id = ?", (album_id,))
        c.execute("DELETE FROM ualbums WHERE id = ?", (album_id,))
    _write(run)


def set_album_items(album_id: int, items: list, on: bool):
    now = int(time.time())
    if on:
        _write(lambda c: c.executemany("INSERT OR IGNORE INTO ualbum_items VALUES (?,?,?,?)",
                                       [(album_id, i, h, now) for i, h in items]))
    else:
        _write(lambda c: c.executemany("DELETE FROM ualbum_items WHERE album_id = ? AND photo_id = ?",
                                       [(album_id, i) for i, _ in items]))


def _settings_stamp() -> tuple:
    """Changes on every write: rev for this process, and for writes by another one (the stdio
    MCP server shares this database) the file's mtime on SQLite, or a few-second clock on MySQL,
    where no cheap change marker exists."""
    from . import vdb
    if vdb.is_mysql():
        return rev, int(time.time() / 5)
    try:
        return rev, STATE_DB.stat().st_mtime_ns
    except OSError:
        return rev, None


def get_setting(key: str, default: str = "") -> str:
    """Settings are tiny and read on every status poll and every POST, so the whole
    table is cached and re-read only after a write."""
    global _settings
    stamp, values = _settings
    now = _settings_stamp()  # taken before the query: a write racing with it makes the next call reload
    if stamp != now:
        con = connect()
        try:
            values = dict(con.execute("SELECT key, value FROM settings").fetchall())
        except Exception:
            return default
        finally:
            con.close()
        _settings = (now, values)
    return values.get(key, default)


def read_only() -> bool:
    """Nothing in the library may be changed: READ_ONLY=1 in the environment (locked) or the read_only setting."""
    return config.READ_ONLY or get_setting("read_only", "0") == "1"


def set_setting(key: str, value: str):
    _write(lambda c: c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value)))


# ---- what the index queries used to read through an attached copy of this database
def favorite_ids() -> list:
    con = connect()
    try:
        return [r[0] for r in con.execute("SELECT photo_id FROM favorites")]
    finally:
        con.close()


def album_item_ids(album_ids: list) -> list:
    if not album_ids:
        return []
    con = connect()
    try:
        return [r[0] for r in con.execute(f"SELECT photo_id FROM ualbum_items WHERE album_id IN ({','.join(str(int(a)) for a in album_ids)})")]
    finally:
        con.close()


def albums_of(photo_id: int) -> list:
    con = connect()
    try:
        return [r[0] for r in con.execute("SELECT album_id FROM ualbum_items WHERE photo_id = ?", (photo_id,))]
    finally:
        con.close()


def is_favorite(photo_id: int) -> bool:
    con = connect()
    try:
        return con.execute("SELECT 1 FROM favorites WHERE photo_id = ?", (photo_id,)).fetchone() is not None
    finally:
        con.close()


def album_id_by_name(name_or_id) -> int:
    con = connect()
    try:
        r = con.execute("SELECT id FROM ualbums WHERE lower(name) = lower(?) OR id = ?", (str(name_or_id), str(name_or_id))).fetchone()
        return r[0] if r else None
    finally:
        con.close()
