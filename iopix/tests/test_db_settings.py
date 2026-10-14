"""The digiKam database connection is a setting the admin can change at runtime: settings
override the environment, the password is stored but never shown, a test connection reports
counts without saving, and saving kicks the index."""
from app import dkdb, state


def _clear():
    for k in dkdb.KEYS:
        state.set_setting("db_" + k, "")


def test_settings_override_environment_and_hide_password(client):
    _clear()
    assert dkdb.settings()["type"] == "sqlite" and dkdb.is_mysql() is False
    r = client.post("/api/settings", json={"database": {"type": "mysql", "host": "db.local", "port": "3307", "database": "dk", "user": "u", "password": "p@ss"}})
    assert r.status_code == 200
    c = dkdb.settings()
    assert c["type"] == "mysql" and c["host"] == "db.local" and c["port"] == 3307 and c["password"] == "p@ss"
    pub = client.get("/api/settings").json()["database"]
    assert "password" not in pub and pub["password_set"] is True and pub["host"] == "db.local"
    assert "p@ss" not in client.get("/api/settings").text
    client.post("/api/settings", json={"database": {"type": "mysql", "password": ""}})
    assert dkdb.settings()["password"] == "p@ss", "an empty password field keeps the stored one"
    assert "MySQL u@db.local:3307/dk" == dkdb.describe()
    _clear()
    assert dkdb.describe().endswith("digikam4.db")


def test_test_connection_sqlite_and_mysql(client, monkeypatch, lib):
    _clear()
    r = client.post("/api/db/test", json={"type": "sqlite", "sqlite_dir": str(lib["db"].parent)}).json()
    assert r["ok"] and r["images"] == len(lib["ids"]) and r["roots"]
    bad = client.post("/api/db/test", json={"type": "sqlite", "sqlite_dir": "/nowhere"})
    assert bad.status_code == 400 and "digikam4.db" in bad.json()["detail"]

    class FakeCur:
        def __init__(self): self.q = None
        def execute(self, sql, params=()): self.q = sql
        def fetchone(self): return (3,) if "count" in self.q else ("17",)
        def fetchall(self): return [("/photos",)]
        def __iter__(self): return iter(self.fetchall())
        @property
        def lastrowid(self): return 0
        @property
        def rowcount(self): return 0
    class FakeRaw:
        def cursor(self): return FakeCur()
        def close(self): pass
        def commit(self): pass
        def rollback(self): pass
    import types, sys
    monkeypatch.setitem(sys.modules, "pymysql", types.SimpleNamespace(connect=lambda **kw: FakeRaw()))
    r = client.post("/api/db/test", json={"type": "mysql", "host": "h", "port": "3306", "database": "d", "user": "u", "password": "p"}).json()
    assert r["ok"] and r["images"] == 3 and r["dbVersion"] == "17" and r["roots"] == ["/photos"]
    _clear()
