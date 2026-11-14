"""`iosuite-shared install`: the plan built from a calling app's config.env, without GitHub or a database."""
import pytest

from iosuite_shared import cli, install


@pytest.fixture
def fresh_db(monkeypatch):
    """Overrides conftest's autouse database fixture: nothing here needs MariaDB. The suite's one-address switch,
    which lives there, is off unless a test says otherwise."""
    monkeypatch.setattr(install, "_switch", lambda: False)
    yield


CFG = """DB_HOST=db.lan
DB_PORT=3307
DB_NAME=suite
DB_USER=suite
DB_PASSWORD=s3cret
IOSUITE_DB_HOST=db.lan
IOSUITE_DB_PORT=3307
IOSUITE_DB_NAME=iostart
IOSUITE_DB_USER=iostart
IOSUITE_DB_PASSWORD=sh4red
COOKIE_DOMAIN=example.com
PORT=8630
"""


def test_parse_apps():
    assert install.parse_apps("iopix, ionote") == ["iopix", "ionote"]
    assert install.parse_apps(["iocalendar,iocontact", "iocalendar"]) == ["iocalendar", "iocontact"]
    assert install.parse_apps("none") == []
    assert install.parse_apps("all") == list(install.APPS)
    with pytest.raises(SystemExit):
        install.parse_apps("iofoo")


def test_plan_shares_the_answers(tmp_path):
    app = tmp_path / "opt" / "iostart" / "app"
    app.mkdir(parents=True)
    (app / "config.env").write_text(CFG)
    cfg = install.read_env_file(app / "config.env")
    base = install.base_dir(app)
    assert base == tmp_path / "opt"
    entries = install.plan(["iocalendar", "iopix", "iostart"], cfg, base, admin="alex", service=True, from_app="iostart")
    assert [e["name"] for e in entries] == ["iocalendar", "iopix"]  # the caller is never reinstalled
    cal = entries[0]
    assert cal["target"] == tmp_path / "opt" / "iocalendar" / "app"
    # the same server, user and password; the app's own database name; the Shared ioSuite database as it is
    assert cal["env"]["IOCALENDAR_DB"] == "db.lan:3307/calendar:suite:s3cret"
    assert cal["env"]["IOCALENDAR_SUITE_DB"] == "db.lan:3307/iostart:iostart:sh4red"
    assert cal["env"]["IOCALENDAR_ADMIN"].startswith("alex:")
    assert cal["args"][:5] == ["--yes", "--cookie-domain", "example.com", "--public-url", ""]
    assert "--service" in cal["args"] and "--no-admin" not in cal["args"]
    pix = entries[1]
    assert pix["env"]["IOPIX_DB"] == "db.lan:3307/iopix:suite:s3cret"
    assert "--no-digikam" in pix["args"] and "--photos" in pix["args"]
    assert pix["args"][pix["args"].index("--data") + 1] == str(tmp_path / "opt" / "iopix" / "data")


def test_plan_without_an_app_database_lends_the_shared_one(tmp_path):
    cfg = install.read_env_file(tmp_path / "missing")  # ionote on SQLite: no DB_* at all
    cfg.update(IOSUITE_DB_HOST="db.lan", IOSUITE_DB_PASSWORD="pw")
    [e] = install.plan(["iohealth"], cfg, tmp_path, service=False)
    assert e["env"]["IOHEALTH_DB"] == "db.lan:3306/health:iosuite:pw"
    assert e["env"]["IOHEALTH_SUITE_DB"] == "db.lan:3306/iosuite:iosuite:pw"
    assert "--no-service" in e["args"] and "--no-admin" in e["args"]


def test_install_runs_each_setup_and_skips_what_is_there(tmp_path, monkeypatch):
    app = tmp_path / "opt" / "iostart" / "app"
    app.mkdir(parents=True)
    (app / "config.env").write_text(CFG)
    done = tmp_path / "opt" / "iocontact" / "app"
    done.mkdir(parents=True)
    (done / "config.env").write_text("PORT=8640\n")
    fetched, ran, lines = [], [], []

    def fetcher(name, target, log):
        fetched.append(name)
        target.mkdir(parents=True, exist_ok=True)

    def runner(entry, log):
        ran.append(entry["name"])
        return 1 if entry["name"] == "iohealth" else 0

    failed = install.install(["iocontact", "iocalendar", "iohealth"], app, photos=str(tmp_path / "photos"),
                             fetcher=fetcher, runner=runner, log=lines.append)
    assert fetched == ["iocalendar", "iohealth"] and ran == ["iocalendar", "iohealth"]
    assert failed == ["iohealth"]
    assert any("already set up" in l for l in lines)


def test_cli_has_install(tmp_path, monkeypatch):
    calls = {}
    monkeypatch.setattr(install, "install", lambda names, config_dir, **kw: calls.update(names=names, config_dir=config_dir, **kw) or [])
    assert cli.main(["--config", str(tmp_path), "install", "iopix,ionote", "--admin", "alex", "--no-service", "--from", "iostart"]) == 0
    assert calls["names"] == ["iopix", "ionote"] and calls["admin"] == "alex" and calls["service"] is False and calls["from_app"] == "iostart"


def test_local_mariadb_gets_the_databases(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.setattr(install.os, "geteuid", lambda: 0)
    monkeypatch.setattr(install.shutil, "which", lambda n: "/usr/bin/mariadb")

    class R:
        returncode, stderr = 0, ""

    monkeypatch.setattr(install.subprocess, "run", lambda cmd, **kw: seen.update(cmd=cmd, sql=kw["input"]) or R())
    cfg = dict(DB_HOST="127.0.0.1", DB_USER="iopix", DB_PASSWORD="x")
    entries = install.plan(["iocalendar", "ionote"], cfg, tmp_path)
    install.prepare_local_databases(entries, cfg, log=lambda *_: None)
    assert seen["cmd"] == ["mariadb"] and "`calendar`" in seen["sql"] and "`notes`" in seen["sql"] and "'iopix'@'localhost'" in seen["sql"]
    seen.clear()
    install.prepare_local_databases(entries, dict(DB_HOST="db.lan", DB_USER="suite"), log=lambda *_: None)
    assert not seen  # a remote server is left to its administrator


# ---- what is here, removing, the checklist

def _server(tmp_path, apps=("iocalendar", "iotask"), data=("ionote",)):
    """An /opt with ioStart (the caller) and some companions, as `install` leaves them."""
    opt = tmp_path / "opt"
    own = opt / "iostart" / "app"
    own.mkdir(parents=True)
    (own / "config.env").write_text(CFG)
    for n in apps + tuple(data):
        d = opt / n / "app"
        (d / ".venv").mkdir(parents=True)
        (d / "app").mkdir()
        (d / "app" / "main.py").write_text("x")
        (d / "data").mkdir()
        (d / "data" / f"{n}.log").write_text("log")
        cfg = CFG.replace("DB_NAME=suite", f"DB_NAME={install.APPS[n]['db']}")
        if n in data:
            (opt / n / "data").mkdir()
            (opt / n / "data" / "keep.me").write_text("x")
            cfg += f"DATA_DIR={opt / n / 'data'}\n"
        (d / "config.env").write_text(cfg)
    return opt, own


def _remove(names, own, **kw):
    calls = {"stop": [], "forget": [], "drop": []}
    failed = install.remove(names, own, stopper=lambda n, t, log=print: calls["stop"].append(n),
                            forgetter=lambda n, log=print: calls["forget"].append(n),
                            dropper=lambda p, db_admin=None, log=print: calls["drop"].append(p["db"]) or True, **kw)
    return failed, calls


def test_installed_lists_the_caller_and_what_has_a_config(tmp_path):
    opt, own = _server(tmp_path)
    assert install.app_of(own) == "iostart"
    assert install.installed(opt, own) == ["iostart", "iocalendar", "ionote", "iotask"]
    (opt / "iorecipe" / "app" / "data").mkdir(parents=True)  # what a removed app leaves: no config.env, not installed
    assert "iorecipe" not in install.installed(opt, own)


def test_remove_keeps_the_database_and_the_data(tmp_path, capsys):
    opt, own = _server(tmp_path)
    failed, calls = _remove(["iocalendar", "ionote"], own)
    assert failed == [] and calls["stop"] == calls["forget"] == ["iocalendar", "ionote"] and calls["drop"] == []
    cal = opt / "iocalendar" / "app"
    assert not (cal / "config.env").exists() and not (cal / ".venv").exists() and not (cal / "app").exists()
    assert (cal / "data" / "iocalendar.log").is_file()  # the data folder inside the app's folder stays
    assert (opt / "ionote" / "data" / "keep.me").is_file() and not (opt / "ionote" / "app" / "config.env").exists()
    assert install.installed(opt, own) == ["iostart", "iotask"]
    assert (opt / "iotask" / "app" / "config.env").is_file() and (own / "config.env").is_file()  # nobody else is touched
    out = capsys.readouterr().out
    assert "kept the database calendar" in out and "adding ioCalendar again later finds them" in out


def test_remove_with_delete_data_drops_only_the_apps_own_database(tmp_path):
    opt, own = _server(tmp_path)
    failed, calls = _remove(["iocalendar", "ionote"], own, delete_data=True)
    assert failed == [] and calls["drop"] == [("db.lan", "3307", "calendar"), ("db.lan", "3307", "notes")]
    assert not (opt / "iocalendar").exists() and not (opt / "ionote").exists()
    assert (opt / "iotask" / "app" / "data").is_dir()


def test_delete_data_never_drops_a_shared_or_borrowed_database(tmp_path, capsys):
    opt, own = _server(tmp_path)
    cal = opt / "iocalendar" / "app" / "config.env"
    cal.write_text(cal.read_text().replace("DB_NAME=calendar", "DB_NAME=iostart"))  # the Shared ioSuite database's name here
    task = opt / "iotask" / "app" / "config.env"
    task.write_text(task.read_text().replace("DB_NAME=tasks", "DB_NAME=suite"))  # ioStart's own database
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    task.write_text(task.read_text() + f"DATA_DIR={outside}\n")
    failed, calls = _remove(["iocalendar", "iotask"], own, delete_data=True)
    assert failed == [] and calls["drop"] == []
    out = capsys.readouterr().out
    assert "it is the Shared ioSuite database" in out and "ioStart uses it too" in out
    assert outside.is_dir() and not (opt / "iotask" / "app").exists()  # a data folder elsewhere is the person's to delete


def test_remove_never_deletes_the_photos_the_backups_or_digikams_database(tmp_path, capsys):
    """The folders config.env names for them stay, wherever they are: inside the app's own folder too."""
    opt, own = _server(tmp_path, apps=("iopix", "iobackup"), data=())
    photos, dk = opt / "iopix" / "photos", opt / "iopix" / "app" / "library" / "digikam"
    backups = opt / "iobackup" / "app" / "backups"
    for d, f in ((photos, "holiday.jpg"), (dk, "digikam4.db"), (backups, "monday.sql.gz")):
        d.mkdir(parents=True)
        (d / f).write_text("x")
    (dk.parent / "notes.txt").write_text("x")  # beside digiKam's folder, in a folder of the app: goes
    pix, bak = opt / "iopix" / "app" / "config.env", opt / "iobackup" / "app" / "config.env"
    pix.write_text(pix.read_text() + f"PHOTOS_ROOT={photos}\nDIGIKAM_DB_DIR={dk}\n")
    bak.write_text(bak.read_text() + "BACKUP_DIR=backups\n")  # as config.env may name it: from the app's folder
    failed, _ = _remove(["iobackup"], own)  # a plain remove: the program files go, the backups among them stay
    assert failed == [] and (backups / "monday.sql.gz").is_file() and (opt / "iobackup" / "app" / "data").is_dir()
    assert not (opt / "iobackup" / "app" / "app").exists() and not bak.exists()
    failed, _ = _remove(["iopix"], own, delete_data=True)  # with the data: everything of the app but those two folders
    assert failed == [] and (photos / "holiday.jpg").is_file() and (dk / "digikam4.db").is_file()
    assert not (opt / "iopix" / "app" / "data").exists() and not pix.exists() and not (dk.parent / "notes.txt").exists()
    assert sorted(x.name for x in (opt / "iopix").iterdir()) == ["app", "photos"]
    out = capsys.readouterr().out
    assert f"the photos in {photos} are never touched" in out and f"the digiKam database in {dk} is never touched" in out
    assert f"{opt / 'iopix'} stays for what is never deleted" in out


def test_clear_never_follows_a_link(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.me").write_text("x")
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "link").symlink_to(outside, target_is_directory=True)
    (folder / "file").write_text("x")
    assert install._clear(folder) is True and list(folder.iterdir()) == [] and (outside / "keep.me").is_file()


def test_remove_of_the_calling_app_is_done_by_another_and_never_the_last(tmp_path):
    opt, own = _server(tmp_path)
    failed, calls = _remove(["iostart", "iorecipe"], own, delete_data=True, delegate=lambda *a: 1 / 0)
    assert failed == ["iostart"] and calls == {"stop": [], "forget": [], "drop": []}  # no other app has an environment to run it
    assert (own / "config.env").is_file()
    (opt / "iotask" / "app" / ".venv" / "bin").mkdir()
    (opt / "iotask" / "app" / ".venv" / "bin" / "iosuite-shared").write_text("")
    asked = []
    failed, calls = _remove(["iostart", "iocalendar"], own, delegate=lambda other, n, base, dd, dba: asked.append((other, n, dd)) or 0)
    assert failed == [] and asked == [("iotask", "iostart", False)] and calls["stop"] == ["iocalendar"]
    failed, _ = _remove(["iostart", "iotask"], own, delegate=lambda *a: 1 / 0)  # iotask goes too: nobody left to do it
    assert failed == ["iostart"]


def test_stop_service_without_systemd_runs_nothing(tmp_path, monkeypatch):
    ran = []
    monkeypatch.setattr(install.shutil, "which", lambda x: None)
    install.stop_service("iotask", tmp_path, run=lambda *a, **k: ran.append(a))
    assert ran == []  # no systemd here: nothing run, the person is told


def test_choose_ticks_and_unticks(tmp_path):
    opt, own = _server(tmp_path)
    names = list(install.APPS)

    def answers(*a):
        it = iter(a)
        return lambda prompt: next(it)

    out = []
    # untick ioCalendar (by number), tick ioRecipe (by name), try the caller; keep the data; go ahead
    picked = install.choose(opt, own, ask=answers(f"{names.index('iocalendar') + 1} iorecipe", "", "", ""), log=out.append)
    assert picked == (["iorecipe"], ["iocalendar"], False, [])
    assert any("to remove" in line for line in out)
    assert install.choose(opt, own, ask=answers(""), log=out.append) is None  # nothing ticked: nothing to do
    # deleting the data needs the word and a yes (Enter is no)
    assert install.choose(opt, own, ask=answers("iotask", "", "DELETE", ""), log=out.append) is None
    assert install.choose(opt, own, ask=answers("iotask", "", "DELETE", "y"), log=out.append) == ([], ["iotask"], True, [])
    assert install.choose(opt, own, ask=answers("iotask", "", "delete", "y"), log=out.append) == ([], ["iotask"], False, [])


def test_cli_apps_adds_and_removes(tmp_path, monkeypatch, capsys):
    opt, own = _server(tmp_path)
    seen = {}
    monkeypatch.setattr(install, "remove", lambda names, cfg, **kw: seen.update(remove=(names, kw["delete_data"])) or [])
    monkeypatch.setattr(install, "install", lambda names, cfg, **kw: seen.update(add=(names, kw["from_app"])) or [])
    assert cli.main(["--config", str(own), "apps", "--add", "iorecipe", "--remove", "iotask,iocalendar"]) == 0
    assert seen == {"remove": (["iotask", "iocalendar"], False), "add": (["iorecipe"], "iostart")}
    assert cli.main(["--config", str(own), "apps", "--list"]) == 0
    out = capsys.readouterr().out
    assert "[x] ioCalendar" in out and "[ ] ioRecipe" in out and "this app" in out
    with pytest.raises(SystemExit):
        cli.main(["--config", str(own), "apps", "--add", "iotask", "--remove", "iotask"])


def test_choose_reconfigure(tmp_path):
    opt, own = _server(tmp_path)
    names = list(install.APPS)
    out = []

    def answers(*a):
        it = iter(a)
        return lambda prompt: next(it)

    n = names.index("iotask") + 1
    assert install.choose(opt, own, ask=answers(f"r{n} r iostart riorecipe", ""), log=out.append) == ([], [], False, ["iostart", "iotask"])
    assert any("ioRecipe is not installed here" in line for line in out) and any("to reconfigure" in line for line in out)
    # an app that is unticked is removed, not reconfigured
    assert install.choose(opt, own, ask=answers(f"r{n} {n}", "", "", ""), log=out.append) == ([], ["iotask"], False, [])


def test_reconfigure_runs_the_apps_own_setup(tmp_path):
    opt, own = _server(tmp_path)
    for d in (own, opt / "iotask" / "app"):
        (d / "setup.sh").write_text("exit 0\n")
    ran = []
    assert install.reconfigure(["iostart", "iotask", "iorecipe"], own, runner=lambda folder: ran.append(folder) or 0) == ["iorecipe"]
    assert ran == [own, opt / "iotask" / "app"]
    assert install.reconfigure(["iotask"], own) == []  # the real runner: sh ./setup.sh --also none, in the app's folder
    with pytest.raises(SystemExit):
        cli.main(["--config", str(own), "apps", "--reconfigure", "iotask", "--remove", "iotask"])


# ---- how the apps are reached: each on its own port, all at the start page's address, or behind a reverse proxy here
def _reach(mode, own, opt, **kw):
    calls = {"switch": [], "restart": [], "lines": []}
    ok = install.set_reach(mode, own, base=opt, switcher=calls["switch"].append,
                           restarter=lambda n, folder, log=print: calls["restart"].append(n) or True, log=calls["lines"].append, **kw)
    return ok, calls


def _env(opt, name):
    return install.read_env_file(opt / name / "app" / "config.env")


def test_reach_one_address_the_start_page_answers_for_every_app(tmp_path):
    opt, own = _server(tmp_path)
    assert install.reach_now(opt, own) == "ports"
    ok, calls = _reach("one", own, opt)
    assert ok and calls["switch"] == [True] and calls["restart"] == ["iocalendar", "ionote", "iotask"]
    assert "HOST" not in _env(opt, "iostart")  # the start page is the one the network reaches
    assert _env(opt, "iocalendar")["HOST"] == "127.0.0.1" and _env(opt, "ionote")["HOST"] == "127.0.0.1"
    assert _env(opt, "iocalendar")["DB_PASSWORD"] == "s3cret" and _env(opt, "ionote")["DATA_DIR"]  # every other line as it was
    assert install.reach_now(opt, own, switch=lambda: True) == "one"
    assert any("/calendar/" in line for line in calls["lines"])
    ok, calls = _reach("one", own, opt)  # again: nothing to write, nobody restarted
    assert ok and calls["restart"] == []
    # behind a reverse proxy on this server: the start page too, with its address
    ok, calls = _reach("one-proxy", own, opt, address="https://home.example.com/")
    assert ok and calls["restart"] == ["iostart"] and _env(opt, "iostart")["HOST"] == "127.0.0.1"
    assert _env(opt, "iostart")["PUBLIC_URL"] == "https://home.example.com" and "PUBLIC_URL" not in _env(opt, "iotask")
    assert install.reach_now(opt, own, switch=lambda: True) == "one-proxy"
    assert any("reverse_proxy 127.0.0.1:8630" in line for line in calls["lines"]) and any("home.example.com {" in line for line in calls["lines"])
    # and back: every app on its own port again
    ok, calls = _reach("ports", own, opt)
    assert ok and calls["switch"] == [False] and set(calls["restart"]) == {"iostart", "iocalendar", "iotask", "ionote"}
    assert all("HOST" not in _env(opt, n) for n in ("iostart", "iocalendar", "iotask", "ionote"))
    assert install.reach_now(opt, own) == "ports"


def test_reach_behind_a_proxy_of_ones_own(tmp_path):
    opt, own = _server(tmp_path)
    with open(opt / "iotask" / "app" / "config.env", "a") as f:
        f.write("HOST=192.168.1.151\n# HOST=0.0.0.0\n")
    ok, calls = _reach("proxy", own, opt, address="https://home.example.com")
    assert ok and calls["switch"] == [False] and install.reach_now(opt, own) == "proxy"
    assert _env(opt, "iostart")["PUBLIC_URL"] == "https://home.example.com" and _env(opt, "iostart")["HOST"] == "127.0.0.1"
    assert _env(opt, "iocalendar")["PUBLIC_URL"] == "https://home.example.com/calendar" and _env(opt, "ionote")["PUBLIC_URL"] == "https://home.example.com/notes"
    assert _env(opt, "iotask")["HOST"] == "127.0.0.1" and "# HOST=0.0.0.0" in (opt / "iotask" / "app" / "config.env").read_text()
    text = "\n".join(calls["lines"])  # a Caddyfile for what is here
    assert "handle_path /calendar/* {" in text and "reverse_proxy 127.0.0.1:8630" in text and "redir /.well-known/caldav /calendar/dav/ 301" in text
    assert "/contacts" not in text  # ioContact is not on this server
    assert install.shared_address(opt, own) == "https://home.example.com"
    # an address the person named is not ours to take out, a name per app is each app's own setting
    with open(opt / "iotask" / "app" / "config.env", "a") as f:
        f.write("HOST=192.168.1.151\n")
    ok, calls = _reach("ports", own, opt)
    assert _env(opt, "iotask")["HOST"] == "192.168.1.151" and "HOST" not in _env(opt, "iocalendar")
    assert _env(opt, "iocalendar")["PUBLIC_URL"] == "https://home.example.com/calendar"
    ok, calls = _reach("proxy", own, opt)
    assert any("r and its number" in line for line in calls["lines"])


def test_reach_refuses_what_cannot_be(tmp_path):
    opt, own = _server(tmp_path)
    ok, calls = _reach("one", opt / "iotask" / "app", tmp_path / "elsewhere")  # a server without the start page
    assert not ok and calls["switch"] == [] and any("needs the start page" in line for line in calls["lines"])
    ok, calls = _reach("one", own, opt, address="home.example.com")
    assert not ok and calls["switch"] == [] and "HOST" not in _env(opt, "iocalendar")

    def broken(on):
        raise RuntimeError("no database")
    ok = install.set_reach("one", own, base=opt, switcher=broken, restarter=lambda *a, **k: True, log=lambda line: None)
    assert not ok and "HOST" not in _env(opt, "iocalendar")  # the switch first: the apps never go quiet behind a door that is shut


def test_reach_keeps_the_ldap_directory_where_it_listened(tmp_path):
    opt, own = _server(tmp_path)
    d = opt / "iocontact" / "app"
    d.mkdir(parents=True)
    (d / "config.env").write_text(CFG.replace("DB_NAME=suite", "DB_NAME=contacts"))
    _reach("one", own, opt)
    assert _env(opt, "iocontact")["HOST"] == "127.0.0.1" and _env(opt, "iocontact")["LDAP_HOST"] == "0.0.0.0"
    _reach("ports", own, opt)
    assert "HOST" not in _env(opt, "iocontact") and "LDAP_HOST" not in _env(opt, "iocontact")
    (d / "config.env").write_text(CFG + "LDAP_PORT=0\n")  # the directory is off: nothing to keep
    _reach("proxy", own, opt)
    assert "LDAP_HOST" not in _env(opt, "iocontact")


def test_an_app_added_later_is_reached_like_the_others(tmp_path, monkeypatch):
    opt, own = _server(tmp_path)
    _reach("proxy", own, opt, address="https://home.example.com")
    seen = {}

    def fetcher(name, target, log):
        target.mkdir(parents=True, exist_ok=True)

    def runner(entry, log):
        seen[entry["name"]] = (install.read_env_file(entry["target"] / "config.env"), entry["args"][entry["args"].index("--public-url") + 1])
        return 1 if entry["name"] == "iohealth" else 0
    failed = install.install(["iorecipe", "iohealth"], own, base=opt, fetcher=fetcher, runner=runner, log=lambda line: None)
    assert seen["iorecipe"] == ({"HOST": "127.0.0.1"}, "https://home.example.com/recipes")  # before its setup.sh starts it
    assert failed == ["iohealth"] and not (opt / "iohealth" / "app" / "config.env").exists()  # a failed setup leaves no half an app
    _reach("ports", own, opt)
    install.install(["iodns"], own, base=opt, fetcher=fetcher, runner=runner, log=lambda line: None)
    assert seen["iodns"] == ({}, "")
    monkeypatch.setattr(install, "_switch", lambda: True)  # one address: the new app behind the start page at once
    install.install(["iobackup"], own, base=opt, fetcher=fetcher, runner=runner, log=lambda line: None)
    assert seen["iobackup"] == ({"HOST": "127.0.0.1"}, "")


def test_choose_how_the_apps_are_reached(tmp_path):
    opt, own = _server(tmp_path)

    def answers(*a):
        it = iter(a)
        return lambda prompt: next(it)
    out, reach = [], {}
    assert install.choose(opt, own, ask=answers("a", "2", "", ""), log=out.append, reach=reach) == ([], [], False, [])
    assert reach == {"mode": "one", "address": None}
    assert any("Reached: each app on its own port" in line for line in out) and any("to change to: one address" in line for line in out)
    reach = {}
    assert install.choose(opt, own, ask=answers("a", "4", "home.example.com", "https://home.example.com/", "iorecipe", ""), log=out.append, reach=reach) == (["iorecipe"], [], False, [])
    assert reach == {"mode": "proxy", "address": "https://home.example.com"}
    reach = {}
    assert install.choose(opt, own, ask=answers("a", "", ""), log=out.append, reach=reach) is None and reach == {}  # left as it is
    assert install.choose(opt, own, ask=answers("a", "1", ""), log=out.append, reach=reach) is None and reach == {}  # what it already is
    assert install.choose(opt, own, ask=answers("iostart", "a", "2", "", "iostart", ""), log=out.append, reach=reach) is None  # not without the start page
    assert any("tick ioStart first" in line for line in out)
    assert install.choose(opt, own, ask=answers("a", ""), log=out.append) is None  # the old list has no such letter
    assert any("a: not one of the apps" in line for line in out)


def test_cli_reach(tmp_path, monkeypatch, capsys):
    opt, own = _server(tmp_path)
    seen = {}
    monkeypatch.setattr(install, "set_reach", lambda mode, cfg, **kw: seen.update(mode=mode, address=kw["address"], base=kw["base"]) or True)
    monkeypatch.setattr(install, "install", lambda names, cfg, **kw: seen.update(add=names, reach=kw["reach"]) or [])
    assert cli.main(["--config", str(own), "apps", "--reach", "one-proxy", "--address", "https://home.example.com", "--add", "iorecipe"]) == 0
    assert seen == {"mode": "one-proxy", "address": "https://home.example.com", "base": opt, "add": ["iorecipe"], "reach": "one-proxy"}
    monkeypatch.setattr(install, "set_reach", lambda mode, cfg, **kw: False)
    assert cli.main(["--config", str(own), "apps", "--reach", "ports"]) == 1
    assert cli.main(["--config", str(own), "apps", "--list"]) == 0 and "Reached: each app on its own port" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        cli.main(["--config", str(own), "apps", "--address", "https://home.example.com"])
    with pytest.raises(SystemExit):
        cli.main(["--config", str(own), "apps", "--reach", "sideways"])


def test_restart_service_without_systemd_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(install.shutil, "which", lambda x: None)
    lines = []
    assert install.restart_service("iotask", tmp_path, log=lines.append, run=lambda *a, **k: pytest.fail("nothing to run")) is True
    assert "started by hand" in lines[0]
