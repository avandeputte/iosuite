"""The viewer database (MariaDB-only since v1.113): the schema lands in an empty database, data copies to
another database with ids intact, the dump is the backup form, and the viewer waits for a database instead of
starting on a file."""

import pytest

import mariadb
from app.ai import analysis
from app.data import state, appdb
from app import users


@pytest.fixture
def other_db():
    """A second, empty database on the test server, dropped afterwards."""
    cfg = mariadb.fresh_database("iopix_test_other")
    yield cfg
    import pymysql
    c = mariadb.server()
    con = pymysql.connect(host=c["host"], port=c["port"], user=c["user"], password=c["password"], autocommit=True)
    con.cursor().execute("DROP DATABASE IF EXISTS `iopix_test_other`")
    con.close()


def _seed():
    alex = users.create("alex", "correct horse", "admin")
    state.set_setting("zz_probe", "value with ? and %s and `key`")
    assert state.set_favorites([(1, "h1"), (2, "h2")], True, user=alex), "favorites are an account's own"
    aid = state.create_album("Trip"); state.set_album_items(aid, [(1, "h1")], True)
    with appdb.writer() as con:
        con.execute("INSERT OR REPLACE INTO pix_ai_quality VALUES (?,?,?,?,?)", (1, 0.5, 0.4, 0, 0))
        con.execute("INSERT OR REPLACE INTO pix_ai_scans VALUES (?,?,?,?)", (1, "quality", "2026-10-15T00:00:00.000", None))
        con.execute("INSERT OR REPLACE INTO pix_ai_descriptions VALUES (?,?)", (1, "a dog on a beach"))
    return aid


def test_a_fresh_empty_database_gets_every_table(other_db):
    """setup.sh and the set-up page point a new install at an empty database: the first start creates the tables."""
    con = appdb.connect(cfg=other_db)
    try:
        assert appdb.columns(con, "pix_ai_quality") == []
        appdb.ensure_schema(con)
        assert set(appdb.TABLES) <= appdb.table_names(con)
        assert appdb.add_missing_columns(con) == [], "a second open adds nothing"
    finally:
        con.close()


def test_copy_to_another_database_keeps_every_row(client, fresh, other_db):
    aid = _seed()
    t = appdb.test_connection(other_db)
    assert t["ok"] and t["tables"] == {} and t["existing"] == []
    src, dst = appdb.connect(), appdb.connect(cfg=other_db)
    try:
        counts = appdb.copy_all(src, dst, drop=True)
        assert counts["pix_favorite_photos"] >= 2 and counts["pix_albums"] >= 1  # (accounts live in the Shared ioSuite database)
        r = dst.execute("SELECT id, name FROM pix_albums WHERE id = ?", (aid,)).fetchone()
        assert r["name"] == "Trip" and r[1] == "Trip", "rows answer to names and indexes"
        assert dst.execute("SELECT value FROM pix_settings WHERE name = 'zz_probe'").fetchone()[0] == "value with ? and %s and `key`"
        assert dst.execute("SELECT stamp FROM pix_ai_scans WHERE photo_id = 1 AND job = 'quality'").fetchone()[0] == "2026-10-15T00:00:00.000", "text stamps stay text"
    finally:
        src.close(); dst.close()
    t = appdb.test_connection(other_db)
    assert t["tables"]["pix_favorite_photos"] >= 2 and "pix_favorite_photos" in t["existing"]
    res = analysis.results()
    assert res[1]["sharp"] == 0.5 and res[1]["caption_ai"] == "a dog on a beach"


def test_private_albums_and_accounts_on_the_server(client, fresh):
    """The modules' queries on MariaDB (GROUP BY under ONLY_FULL_GROUP_BY, COLLATE NOCASE dropped, the `key` column)."""
    with appdb.writer() as con:  # leftovers from the tests before
        for t in ("pix_favorite_photos", "pix_album_photos", "pix_albums"):
            con.execute(f"DELETE FROM {t}")
    users.create("alex", "correct horse", "admin"); users.create("vi", "", "viewer")
    state._settings = (-1, {})
    state.set_setting("zz_probe", "héllo ? %s"); state._settings = (-1, {})
    assert state.get_setting("zz_probe") == "héllo ? %s"
    me = users.get(next(u["id"] for u in users.list_users() if u["name"] == "alex"))
    assert me["role"] == "admin" and users.authenticate("alex", "correct horse") and not users.authenticate("alex", "wrong")
    assert users.authenticate("vi", ""), "a passwordless viewer signs in with one click"
    u = users.create("new", "password-1", "editor", "New@Example.com")
    assert u["email"] == "new@example.com" and users.get(u["id"])["name"] == "new"
    aid = state.create_album("Trip"); state.set_album_items(aid, [(1, "h1")], True)
    priv = state.create_album("Secret", me["id"], shared=False); state.set_album_items(priv, [(1, "h1")], True)
    assert "Secret" not in {a["name"] for a in state.summary(None)["albums"]}
    assert {a["name"] for a in state.summary(me)["albums"]} >= {"Trip", "Secret"}
    assert state.album_item_ids([priv]) == [] and state.album(priv)["shared"] is False
    tok = state.viewer.set(me)
    try:
        assert state.album_item_ids([priv]) == [1] and sorted(state.albums_of(1)) == sorted([aid, priv])
    finally:
        state.viewer.reset(tok)


def test_a_column_added_to_the_schema_reaches_an_existing_table(client):
    c = appdb.connect()
    try:
        c.execute("ALTER TABLE pix_albums DROP COLUMN shared")
        c.commit()
        appdb.ensure_schema(c)
        assert "shared" in appdb.columns(c, "pix_albums")
    finally:
        c.close()


def test_switch_refuses_the_database_in_use(client, monkeypatch):
    monkeypatch.setattr(appdb.config, "_PROCESS_ENV", {})
    with pytest.raises(ValueError, match="already uses"):
        appdb.switch(appdb.settings(), copy=False)


def test_the_set_up_page_writes_config_env(tmp_path, other_db, monkeypatch):
    """Use this database on a fresh install: the DB_* lines go into config.env (a commented example filled in,
    the rest kept), and the viewer reads them from there."""
    conf = tmp_path / "config.env"
    conf.write_text("# iopix settings\nPORT=8600\n# DB_HOST=\n")
    monkeypatch.setattr(appdb.config, "CONFIG_FILE", conf)
    monkeypatch.setattr(appdb.config, "_PROCESS_ENV", {})  # as a service that reads config.env: nothing fixed outside it
    for n in appdb.config.DB_ENV.values():
        monkeypatch.delenv(n, raising=False)  # the test session's DB_* must not count as "configured" (and come back afterwards)
    monkeypatch.setattr(appdb, "_cfg", None)
    assert not appdb.configured()
    with pytest.raises(ValueError):
        appdb.switch({"host": other_db["host"]}, copy=True)  # a database and a user are needed too
    appdb.switch(other_db, copy=True)
    saved = appdb.config.file_values(conf)
    assert saved["DB_NAME"] == other_db["database"] and saved["DB_HOST"] == other_db["host"] and saved["PORT"] == "8600"
    assert conf.read_text().startswith("# iopix settings\n") and "# DB_HOST=" not in conf.read_text(), "the commented line is filled in"
    assert appdb.settings()["database"] == other_db["database"]


def test_switch_refuses_a_database_the_environment_fixes(other_db, tmp_path, monkeypatch):
    """docker-compose's environment wins over config.env: a switch from Settings would be undone by the restart."""
    monkeypatch.setattr(appdb.config, "CONFIG_FILE", tmp_path / "config.env")
    assert "DB_HOST" in appdb.public_settings()["fromEnv"]
    with pytest.raises(ValueError, match="environment"):
        appdb.switch(other_db, copy=False)
    assert not (tmp_path / "config.env").exists()


def test_dump_is_the_backup_form(client, fresh, tmp_path):
    if not appdb.dump_tool():
        pytest.skip("no mysqldump/mariadb-dump on this machine")
    _seed()
    out = tmp_path / "iopix.sql"
    appdb.dump(out)
    text = out.read_text(errors="replace")
    assert "CREATE TABLE `pix_favorite_photos`" in text and "'zz_probe'" in text


def test_without_a_configuration_the_viewer_waits(monkeypatch):
    monkeypatch.setattr(appdb, "_cfg", None)
    monkeypatch.setattr(appdb.config, "db_env", lambda k: None)
    monkeypatch.setattr(appdb, "error", None)
    assert not appdb.configured()
    appdb.init()  # never raises
    assert appdb.error and not appdb.ready() and appdb.describe() == "no database configured"
    with pytest.raises(RuntimeError):
        appdb.connect()


def test_an_unreachable_server_is_recorded_not_fatal(monkeypatch):
    monkeypatch.setattr(appdb, "settings", lambda: {"type": "mysql", "host": "127.0.0.1", "port": 1, "database": "x", "user": "u", "password": ""})
    monkeypatch.setattr(appdb, "error", None)
    appdb.init()
    assert appdb.error and appdb.configured() and not appdb.ready() and "unavailable" in appdb.describe()


def test_every_declared_column_is_in_the_create_statement():
    for name, (cols, ddl) in appdb.TABLES.items():
        assert list(appdb.declared_columns(ddl)) == cols, name
    assert "undo" not in appdb.TABLES["pix_photo_history"][0] and " undo " not in appdb.TABLES["pix_photo_history"][1]
