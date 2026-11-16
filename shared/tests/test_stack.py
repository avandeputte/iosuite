"""`iosuite-shared stack`: what a Docker stack's setup service does before the apps start (iosuite_shared.stack)."""
import pytest

from iosuite_shared import cli, db, proxyauth, stack, suite, users

ENV = dict(DB_HOST="db", DB_PORT="3306", DB_USER="suite", DB_PASSWORD="s3cret", IOSUITE_DB_NAME="iosuite", IOSUITE_DB_USER="iosuite",
           IOSUITE_DB_PASSWORD="sh4red", DB_ADMIN_PASSWORD="r00t", TZ="Europe/Brussels")


def test_the_databases_come_from_the_environment_and_the_list():
    seen = {}

    def run(admin, password, cfg, also, client=None, log=print):
        seen.update(admin=admin, password=password, cfg=cfg, also=list(also), client=client)
        return 1
    stack.provision_from_env("root", "iostart, iocalendar,iotask", "%", env=ENV, run=run, log=lambda *_: None)
    assert seen["admin"] == "root" and seen["password"] == "r00t" and seen["client"] == "%"
    assert seen["cfg"]["DB_NAME"] == "iostart" and seen["also"] == ["iocalendar", "iotask"]
    assert seen["cfg"]["DB_USER"] == "suite" and seen["cfg"]["IOSUITE_DB_PASSWORD"] == "sh4red" and "TZ" not in seen["cfg"]


def test_the_planned_sql_is_one_user_for_every_database():
    from iosuite_shared import provision
    jobs = {}
    stack.provision_from_env("root", "iostart,iocalendar", "%", env=ENV, log=lambda *_: None,
                             run=lambda admin, password, cfg, also, client=None, log=print: jobs.update(provision.plan_sql(cfg, also, client)))
    stmts = jobs[("db", "3306")]
    sql = [s for s, _ in stmts]
    for name in ("iostart", "iocalendar", "iosuite"):
        assert f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci" in sql
    assert ("GRANT ALL PRIVILEGES ON `iocalendar`.* TO `suite`@%s", ("%",)) in stmts
    assert ("GRANT ALL PRIVILEGES ON `iosuite`.* TO `iosuite`@%s", ("%",)) in stmts
    assert not any(s.startswith("ALTER USER `iosuite`") for s in sql)


def test_a_database_that_is_still_starting_is_waited_for():
    calls, logged = [], []

    def run(*a, **k):
        calls.append(1)
        if len(calls) < 3:
            raise SystemExit("error: could not connect to db:3306 as root: (2003, \"Can't connect\")")
        return 1
    assert stack.provision_from_env("root", "iostart", "%", env=ENV, run=run, log=logged.append, sleep=lambda s: None) == 1
    assert len(calls) == 3 and len(logged) == 2


def test_what_is_wrong_is_said_at_once():
    with pytest.raises(SystemExit, match="--databases"):
        stack.provision_from_env("root", "", "%", env=ENV, run=lambda *a, **k: 1)
    with pytest.raises(SystemExit, match="letters, digits"):
        stack.provision_from_env("root", "io start", "%", env=ENV, run=lambda *a, **k: 1)
    with pytest.raises(SystemExit, match="DB_HOST"):
        stack.provision_from_env("root", "iostart", "%", env={}, run=lambda *a, **k: 1)

    def denied(*a, **k):
        raise SystemExit("error: db:3306: CREATE DATABASE: (1044, 'Access denied')")
    with pytest.raises(SystemExit, match="Access denied"):  # not a server that is still starting: no waiting
        stack.provision_from_env("root", "iostart", "%", env=ENV, run=denied, sleep=lambda s: pytest.fail("waited"))


def test_what_the_stack_says_is_written_once_and_again_only_when_it_changes():
    quiet = lambda *_: None  # noqa: E731
    assert stack.declare("on", "10.186.30.10, 10.186.30.11", log=quiet) == {"one": "1", "proxies": "10.186.30.10,10.186.30.11"}
    assert suite.one_address() and db.get_setting("auth_proxy_trusted", "", "") == "10.186.30.10, 10.186.30.11"
    assert proxyauth.Forwarded.allows("10.186.30.10") and not proxyauth.Forwarded.allows("10.186.30.1")
    # a suite admin changes both under Settings; the same stack file started again leaves them alone
    suite.set_one_address(False)
    proxyauth.save_suite({"AUTH_PROXY_TRUSTED": "192.168.1.2"})
    db.settings_cache.clear()
    assert stack.declare("on", "10.186.30.10,10.186.30.11", log=quiet) == {}
    assert db.get_setting(suite.ONE_ADDRESS, "", "") == "" and db.get_setting("auth_proxy_trusted", "", "") == "192.168.1.2"
    # a stack file that says something else is applied
    assert stack.declare("off", "", log=quiet) == {"one": "0", "proxies": ""}
    assert db.get_setting("auth_proxy_trusted", "", "") == ""
    assert stack.declare(None, None, log=quiet) == {}


def test_the_command_makes_the_tables_and_the_first_admin(monkeypatch, capsys):
    monkeypatch.setattr("iosuite_shared.config.ADMIN_USER", "alex")
    monkeypatch.setattr("iosuite_shared.config.ADMIN_PASSWORD", "long-enough-1")
    cli.main(["stack", "--one-address", "on", "--proxies", "10.186.30.10"])
    assert [u["name"] for u in users.list_users()] == ["alex"] and users.list_users()[0]["suiteAdmin"]
    assert suite.one_address()
    out = capsys.readouterr().out
    assert "1 account(s)" in out and out.rstrip().endswith("ok")
    cli.main(["stack", "--one-address", "on", "--proxies", "10.186.30.10"])  # again: nothing to do, nobody made twice
    assert len(users.list_users()) == 1
