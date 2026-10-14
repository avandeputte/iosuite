"""The app's own writable state: favorites, app-side albums and settings.

Lives in data/state.db, never in digiKam's database (edits.py and tagmanager.py
keep their queues in the same file, through connect() and _write()). Photos are
referenced by digiKam image id; the file hash is stored alongside so entries
could be re-matched if digiKam ever renumbers its images.
"""
import sqlite3
import threading
import time

from . import config

STATE_DB = config.DATA_DIR / "state.db"
rev = 0  # bumped on every write so cached query results can be invalidated
_lock = threading.Lock()
_settings = (-1, {})  # (rev it was read at, {key: value}); settings are read on every poll and every POST


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(STATE_DB, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def init():
    con = connect()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS favorites (photo_id INTEGER PRIMARY KEY, hash TEXT, added INTEGER);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS ualbums (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, created INTEGER);
        CREATE TABLE IF NOT EXISTS ualbum_items (album_id INTEGER, photo_id INTEGER, hash TEXT, added INTEGER,
                                                 PRIMARY KEY (album_id, photo_id));
    """)
    con.commit()
    con.close()


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
    """Changes on every write: rev for this process, the file's mtime for writes by
    another one (the MCP server shares this database)."""
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
        except sqlite3.Error:
            return default
        finally:
            con.close()
        _settings = (now, values)
    return values.get(key, default)


def read_only() -> bool:
    """Nothing in the library may be changed: READ_ONLY=1 in the environment (locked) or the read_only setting."""
    return config.READ_ONLY or get_setting("read_only", "0") == "1"


def set_setting(key: str, value: str):
    _write(lambda c: c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, value)))
