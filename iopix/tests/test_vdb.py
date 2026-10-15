"""The viewer database bridge: the same code runs on SQLite and on MySQL; data copies across with
ids intact, in both directions; the SQLite snapshot is the portable backup form. The MySQL half
runs only when VIEWER_TEST_MYSQL=host:port/database:user:password points at a server where that
database may be created and dropped."""
import os
import sqlite3

import pytest

from app import analysis, state, users, vdb


def _mysql_cfg():
    v = os.environ.get("VIEWER_TEST_MYSQL")
    if not v:
        return None
    hostport, _, rest = v.partition("/")
    database, user, password = rest.split(":", 2)
    host, _, port = hostport.partition(":")
    return {"type": "mysql", "host": host, "port": int(port or 3306), "database": database, "user": user, "password": password}


def test_sqlite_snapshot_and_copy_keep_every_row(client, tmp_path, fresh):
    users.create("alex", "correct horse", "admin")
    state.set_setting("zz_probe", "value with ? and %s and `key`")
    state.set_favorites([(1, "h1"), (2, "h2")], True)
    aid = state.create_album("Trip"); state.set_album_items(aid, [(1, "h1")], True)
    with analysis._writer() as con:
        con.execute("INSERT OR REPLACE INTO quality VALUES (?,?,?,?,?,?)", (1, "s1", 0.5, 0.4, 0, 0))
    snap = tmp_path / "snap.db"
    vdb.snapshot_sqlite(snap)
    con = sqlite3.connect(snap)
    assert con.execute("SELECT value FROM settings WHERE key = 'zz_probe'").fetchone()[0] == "value with ? and %s and `key`"
    assert con.execute("SELECT count(*) FROM favorites").fetchone()[0] >= 2 and con.execute("SELECT name FROM users").fetchone()[0] == "alex"
    assert con.execute("SELECT sharp FROM quality WHERE photo_id = 1").fetchone()[0] == 0.5
    con.close()
    # copy_all into another SQLite file, then read it through the bridge
    dst_path = tmp_path / "copy.db"
    src = vdb.connect()
    dst = vdb.VConn(vdb._sqlite_raw(dst_path, 5), False, True)
    try:
        counts = vdb.copy_all(src, dst, drop=True)
        assert counts["users"] >= 1 and counts["favorites"] >= 2 and counts["ualbums"] >= 1
        r = dst.execute("SELECT id, name FROM ualbums WHERE id = ?", (aid,)).fetchone()
        assert r["name"] == "Trip" and r[1] == "Trip", "rows answer to names and indexes"
    finally:
        src.close(); dst.close()


def test_switch_refuses_sqlite_to_sqlite(client):
    if vdb.is_mysql():
        pytest.skip("the suite runs with the viewer on MySQL; switching to SQLite is then a real switch")
    with pytest.raises(ValueError):
        vdb.switch({"type": "sqlite"}, copy=False)


def test_mysql_round_trip(client, tmp_path, fresh, monkeypatch):
    cfg = _mysql_cfg()
    if not cfg:
        pytest.skip("VIEWER_TEST_MYSQL not set")
    import pymysql
    admin = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"], password=cfg["password"], autocommit=True)
    admin.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{cfg['database']}` CHARACTER SET utf8mb4")
    try:
        # seed the SQLite side, then copy to MySQL (drop + recreate) and run the modules against MySQL
        users.create("alex", "correct horse", "admin"); users.create("vi", "", "viewer")
        state.set_setting("zz_probe", "héllo ? %s"); state.set_favorites([(1, "h1")], True)
        aid = state.create_album("Trip"); state.set_album_items(aid, [(1, "h1")], True)
        with analysis._writer() as con:
            con.execute("INSERT OR REPLACE INTO quality VALUES (?,?,?,?,?,?)", (1, "2026-10-15T00:00:00.000", 0.5, 0.4, 0, 0))
            con.execute("INSERT OR REPLACE INTO captions VALUES (?,?,?)", (1, "stamp", "a dog on a beach"))
        t = vdb.test_connection(cfg)
        assert t["ok"] and "MariaDB" in t["version"] or "ok" in str(t)
        src = vdb.connect(); dst = vdb.connect(cfg=cfg)
        try:
            counts = vdb.copy_all(src, dst, drop=True)
        finally:
            src.close(); dst.close()
        assert counts["users"] == 2 and counts["favorites"] >= 1 and counts["captions"] >= 1
        monkeypatch.setattr(vdb, "settings", lambda: dict(cfg))
        monkeypatch.setattr(vdb, "error", None)
        assert vdb.is_mysql()
        # the modules, unchanged, on MySQL
        state._settings = (-1, {})
        assert state.get_setting("zz_probe") == "héllo ? %s"
        state.set_setting("zz_probe", "changed"); state._settings = (-1, {})
        assert state.get_setting("zz_probe") == "changed"
        me = users.get(next(u["id"] for u in users.list_users() if u["name"] == "alex"))
        assert me["role"] == "admin" and me["email"] == ""
        assert users.authenticate("alex", "correct horse") and not users.authenticate("alex", "wrong")
        assert users.authenticate("vi", "") , "a passwordless viewer signs in with one click"
        u = users.create("new", "password-1", "editor", "New@Example.com")
        assert u["email"] == "new@example.com" and users.get(u["id"])["name"] == "new"
        assert any(a["name"] == "Trip" and a["n"] == 1 for a in state.summary()["albums"])
        assert 1 in state.favorite_ids() and state.albums_of(1) == [aid] and state.album_id_by_name("trip") == aid
        with analysis._writer() as con:
            con.execute("INSERT OR REPLACE INTO quality VALUES (?,?,?,?,?,?)", (2, "2026-10-15T00:00:00.000", 0.1, 0.9, 0, 0))
        res = analysis.results()
        assert res[1]["sharp"] == 0.5 and res[2]["bright"] == 0.9 and res[1]["caption_ai"] == "a dog on a beach"
        con = vdb.connect()
        try:
            assert con.execute("SELECT stamp FROM quality WHERE photo_id = ?", (1,)).fetchone()[0] == "2026-10-15T00:00:00.000", "text stamps stay text on MySQL"
        finally:
            con.close()
        # and back to SQLite: the portable snapshot
        snap = tmp_path / "from-mysql.db"
        vdb.snapshot_sqlite(snap)
        c2 = sqlite3.connect(snap)
        assert c2.execute("SELECT count(*) FROM users").fetchone()[0] == 3 and c2.execute("SELECT value FROM settings WHERE key = 'zz_probe'").fetchone()[0] == "changed"
        c2.close()
    finally:
        admin.cursor().execute(f"DROP DATABASE IF EXISTS `{cfg['database']}`")
        admin.close()
