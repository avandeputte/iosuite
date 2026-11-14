"""`iosuite-shared provision`: the SQL planned from config.env and the run against a fake connection; no MariaDB."""
import pytest

from iosuite_shared import cli, install, provision


@pytest.fixture
def fresh_db():
    """Overrides conftest's autouse database fixture: nothing here needs MariaDB."""
    yield


CFG = dict(DB_HOST="db.lan", DB_PORT="3307", DB_NAME="suite", DB_USER="suite", DB_PASSWORD="s3cret",
           IOSUITE_DB_HOST="db.lan", IOSUITE_DB_PORT="3307", IOSUITE_DB_NAME="iosuite", IOSUITE_DB_USER="iosuite", IOSUITE_DB_PASSWORD="sh4red")


HERE = lambda host, port: "192.168.1.30"  # noqa: E731  this machine's address towards db.lan


def test_plan_one_server():
    jobs = provision.plan_sql(CFG, also=["iocalendar"], here=HERE)
    assert list(jobs) == [("db.lan", "3307")]
    sql = [s for s, _ in jobs[("db.lan", "3307")]]
    assert "CREATE DATABASE IF NOT EXISTS `suite` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" in sql
    assert "CREATE DATABASE IF NOT EXISTS `iosuite` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" in sql
    assert "CREATE DATABASE IF NOT EXISTS `calendar` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" in sql
    stmts = jobs[("db.lan", "3307")]
    assert ("GRANT ALL PRIVILEGES ON `calendar`.* TO `suite`@%s", ("192.168.1.30",)) in stmts
    assert ("ALTER USER `suite`@%s IDENTIFIED BY %s", ("192.168.1.30", "s3cret")) in stmts  # the app's own user: a re-run sets it
    assert ("CREATE USER IF NOT EXISTS `iosuite`@%s IDENTIFIED BY %s", ("192.168.1.30", "sh4red")) in stmts
    assert not any(s.startswith("ALTER USER `iosuite`") for s, _ in stmts), "the other apps sign in as the Shared user: never re-passworded"
    assert sql[-1] == "FLUSH PRIVILEGES"
    assert sum(s.startswith("CREATE USER IF NOT EXISTS `suite`") for s, _ in stmts) == 1, "made once, granted per database"
    assert all(a[0] == "192.168.1.30" for s, a in stmts if a), "a remote server: this machine only, never '%' or localhost"


def test_the_users_can_be_made_for_another_host():
    jobs = provision.plan_sql(CFG, client="192.168.1.%", here=HERE)
    assert {a[0] for _, a in jobs[("db.lan", "3307")] if a} == {"192.168.1.%"}
    jobs = provision.plan_sql(dict(CFG, DB_CLIENT_HOST="10.0.0.7"), here=HERE)
    assert {a[0] for _, a in jobs[("db.lan", "3307")] if a} == {"10.0.0.7"}


def test_plan_local_server_and_two_servers():
    cfg = dict(CFG, DB_HOST="127.0.0.1", DB_PORT="3306")
    jobs = provision.plan_sql(cfg, here=HERE)
    assert set(jobs) == {("127.0.0.1", "3306"), ("db.lan", "3307")}
    assert {a[0] for _, a in jobs[("127.0.0.1", "3306")] if a} == {"localhost", "127.0.0.1"}


def test_plan_without_an_app_database_uses_the_shared_one():
    cfg = dict(IOSUITE_DB_HOST="db.lan", IOSUITE_DB_PASSWORD="pw")
    [stmts] = provision.plan_sql(cfg, also=["ionote"], here=HERE).values()
    assert ("GRANT ALL PRIVILEGES ON `notes`.* TO `iosuite`@%s", ("192.168.1.30",)) in stmts
    assert not any("`suite`" in s for s, _ in stmts)


def test_bad_identifier():
    with pytest.raises(SystemExit):
        provision.plan_sql(dict(CFG, DB_NAME="suite; drop"), here=HERE)


class FakeConn:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        conn = self

        class Cur:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def execute(self, sql, args=None):
                conn.log.append((sql, args))

        return Cur()

    def close(self):
        self.log.append(("close", None))


def test_run_executes_everything(monkeypatch):
    seen, lines = [], []
    n = provision.run("root", "rootpw", CFG, also=["iohealth"], connect=lambda h, p: FakeConn(seen), log=lines.append, here=HERE)
    assert n == 1 and seen[-1] == ("close", None) and seen[-2] == ("FLUSH PRIVILEGES", None)
    assert any(s.startswith("CREATE DATABASE IF NOT EXISTS `health`") for s, _ in seen)
    assert "database(s) health, iosuite, suite and user(s) iosuite, suite ready" in lines[0]


def test_run_reports_a_connection_failure():
    def connect(h, p):
        raise OSError("refused")
    with pytest.raises(SystemExit, match="could not connect to db.lan:3307 as root"):
        provision.run("root", "x", CFG, connect=connect, log=lambda *_: None, here=HERE)


def test_a_shared_user_with_another_password_is_said_not_changed():
    seen = []
    def wrong(h, o, u, w, d):
        raise OSError("Access denied")
    with pytest.raises(SystemExit, match="Shared ioSuite user iosuite cannot sign in"):
        provision.run("root", "x", CFG, connect=lambda h, p: FakeConn(seen), log=lambda *_: None, here=HERE, check=wrong)
    signed = []
    provision.run("root", "x", CFG, connect=lambda h, p: FakeConn(seen), log=lambda *_: None, here=HERE,
                  check=lambda *a: signed.append(a))
    assert signed == [("db.lan", "3307", "iosuite", "sh4red", "iosuite")]


def test_install_uses_the_admin_for_the_companions(tmp_path, monkeypatch):
    app = tmp_path / "opt" / "iosuite" / "app"
    app.mkdir(parents=True)
    (app / "config.env").write_text("".join(f"{k}={v}\n" for k, v in CFG.items()))
    calls = {}
    monkeypatch.setenv("DB_ADMIN_PASSWORD", "rootpw")
    monkeypatch.setattr(provision, "run", lambda user, pw, cfg, also=(), **kw: calls.update(user=user, pw=pw, also=list(also)))
    install.install(["iocalendar"], app, db_admin="root", fetcher=lambda n, t, log: t.mkdir(parents=True, exist_ok=True),
                    runner=lambda e, log: 0, log=lambda *_: None)
    assert calls == dict(user="root", pw="rootpw", also=["iocalendar"])


def test_cli_provision(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(provision, "own_address", HERE)
    (tmp_path / "config.env").write_text("".join(f"{k}={v}\n" for k, v in CFG.items()))
    assert cli.main(["--config", str(tmp_path), "provision", "--admin", "root", "--also", "ionote", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "db.lan:3307" in out and "`notes`" in out and "s3cret" not in out and "-- 192.168.1.30" in out and "-- %" not in out
    seen = {}
    monkeypatch.setenv("DB_ADMIN_PASSWORD", "rootpw")
    monkeypatch.setattr(provision, "run", lambda user, pw, cfg, also=(), **kw: seen.update(user=user, pw=pw, also=list(also)))
    assert cli.main(["--config", str(tmp_path), "provision", "--admin", "root"]) == 0
    assert seen == dict(user="root", pw="rootpw", also=[])
