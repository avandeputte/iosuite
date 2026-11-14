"""The MariaDB the test suites run against: never a real server unless asked.

The library's own tests and the apps' suites need a MariaDB for the Shared ioSuite database. Two ways, the same as iopix:

- IOSUITE_TEST_DB=host:port:user:password names one (CI uses a MariaDB service this way). The user must be allowed
  to CREATE and DROP databases: every run starts from empty databases of its own.
- Otherwise a container is started with Docker, `iosuite-test-mariadb` on a free local port, and left running for
  the next run (`docker rm -f iosuite-test-mariadb` throws it away). Without Docker and without IOSUITE_TEST_DB the
  suite is skipped with a message that says so.

Nothing here ever touches the suite's live Shared ioSuite database: the test databases are made on that test server and
dropped at the start of every session.
"""
import os
import socket
import subprocess
import time

from argon2 import PasswordHasher

# Cheap Argon2id for test suites: monkeypatch.setattr("iosuite_shared.passwords.HASHER", testing.FAST_HASHER)
FAST_HASHER = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1)

CONTAINER = "iosuite-test-mariadb"
IMAGE = "mariadb:11"
ROOT_PASSWORD = "iosuite-test"
_server = None


def server() -> dict:
    """{host, port, user, password} of a reachable MariaDB, or None (with the reason in `server.reason`)."""
    global _server
    if _server is not None:
        return _server or None
    given = os.environ.get("IOSUITE_TEST_DB", "")
    if given:
        host, port, user, password = (given.split(":", 3) + ["", "", ""])[:4]
        c = {"host": host, "port": int(port or 3306), "user": user or "root", "password": password}
    else:
        c = _docker()
    if c and _wait(c):
        _server = c
        return c
    _server = {}
    return None


server.reason = ""


def _docker():
    try:
        out = subprocess.run(["docker", "port", CONTAINER, "3306/tcp"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        server.reason = f"no Docker ({e}) and no IOSUITE_TEST_DB"
        return None
    if out.returncode != 0:  # not running: start it (a stopped one of the same name is removed first)
        subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True, timeout=30)
        run = subprocess.run(["docker", "run", "-d", "--name", CONTAINER, "-p", "127.0.0.1:0:3306",
                              "-e", f"MARIADB_ROOT_PASSWORD={ROOT_PASSWORD}", IMAGE], capture_output=True, text=True, timeout=600)
        if run.returncode != 0:
            server.reason = "docker run failed: " + run.stderr.strip()[-300:]
            return None
        out = subprocess.run(["docker", "port", CONTAINER, "3306/tcp"], capture_output=True, text=True, timeout=20)
    port = int(out.stdout.strip().splitlines()[0].rsplit(":", 1)[1])
    return {"host": "127.0.0.1", "port": port, "user": "root", "password": ROOT_PASSWORD}


def _wait(c: dict, seconds: float = 90) -> bool:
    import pymysql
    end = time.time() + seconds
    while time.time() < end:
        try:
            con = pymysql.connect(host=c["host"], port=c["port"], user=c["user"], password=c["password"], connect_timeout=3)
            con.close()
            return True
        except (pymysql.err.Error, OSError, socket.error) as e:
            server.reason = f"MariaDB at {c['host']}:{c['port']} does not answer: {e}"
            time.sleep(0.5)
    return False


def fresh_database(name: str) -> dict:
    """Drop and create `name` on the test server; the connection settings for it."""
    import pymysql
    c = server()
    con = pymysql.connect(host=c["host"], port=c["port"], user=c["user"], password=c["password"], connect_timeout=5)
    try:
        with con.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
            cur.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        con.commit()
    finally:
        con.close()
    return {"host": c["host"], "port": c["port"], "database": name, "user": c["user"], "password": c["password"]}


def auth_env(name: str) -> dict:
    """A fresh Shared ioSuite database for a test session, as the IOSUITE_DB_* variables an app process reads."""
    s = fresh_database(name)
    out = {}
    for k, v in s.items():
        key = "NAME" if k == "database" else k.upper()
        out["IOSUITE_DB_" + key] = str(v)
    return out


# ---- what every app's test suite does the same way
SHARED_TABLES = ("ios_user_roles", "ios_user_data", "ios_app_passwords", "ios_sessions", "ios_users", "ios_settings", "ios_apps", "ios_credentials", "ios_updates")


def clean_shared_tables(auth=None) -> None:
    """Empty the Shared ioSuite database between two tests and forget every cache: accounts, roles, sessions, app
    passwords, settings, keys and tokens and the list of apps (the first account is #1 again). `auth` (the app's Auth) registers again on
    the next request."""
    from iosuite_shared import apppasswords, credentials, db, proxyauth, sessions, suite, users
    users.init()
    for t in SHARED_TABLES:
        db.ex(f"DELETE FROM {t}")
    db.ex("ALTER TABLE ios_users AUTO_INCREMENT = 1")
    db.settings_cache.clear()
    users.invalidate()
    users._attempts.clear()
    users._known.clear()
    sessions.invalidate()
    suite.invalidate()
    apppasswords.forget()
    credentials.forget()
    proxyauth.forget_identities()
    if auth is not None:
        auth._registered = False


def check_conventions(root, app: str, version: str, config, port_files=("Dockerfile", "docker-compose.yml", "config.env.example", "run.sh")) -> None:
    """The conventions every app's repository follows (one test per app calls this): the suite's port for the app
    (config.PORT, and named in the files that bind it), the suite's version as the app's (`version` is the app's
    __version__; its pyproject.toml carries no number of its own), config.env as the settings file (ignored by git, no
    older name left in the scripts or the README), and a page that asks for everything with relative addresses
    (check_relative: the app may be served in a folder of an address)."""
    import re
    from pathlib import Path
    import iosuite_shared
    from iosuite_shared import suite
    root = Path(root)
    assert config.PORT == suite.PORTS[app], f"PORT defaults to {config.PORT}, the suite's port for {app} is {suite.PORTS[app]}"
    for f in port_files:
        assert str(suite.PORTS[app]) in (root / f).read_text(), f"{f} does not name port {suite.PORTS[app]}"
    assert version == iosuite_shared.__version__, "the app's __version__ is the suite's: from iosuite_shared import __version__"
    assert 'version = "0.0.0"' in (root / "pyproject.toml").read_text(), "pyproject.toml carries a version of its own (the suite's is iosuite_shared.__version__)"
    assert "config.env" in (root / ".gitignore").read_text().split(), "config.env is not in .gitignore"
    for f in ("setup.sh", "update.sh", "README.md"):
        if (root / f).exists():
            text = (root / f).read_text()
            assert f"{app}.env" not in text and not re.search(r"(?<![\w.])\.env\b", text), f"{f} still names a settings file other than config.env"
    check_relative(root)


ABSOLUTE = r"""(?:["'`]|url\(\s*)/(?:api|static|dav|mcp|ics|cal|profile|thumb|preview|orig|video|face|facecrop|share|v1|manifest\.webmanifest|sw\.js)(?![\w-])"""
ABSOLUTE_ATTR = r"""(?:src|href|action)\s*=\s*["']/(?!/)"""


def check_relative(root, skip=("extension", "vendor")) -> None:
    """The page asks for everything with relative addresses (api/events, static/app.js), never from the root of the
    address (/api/events): an app may be served in a folder of it (https://home.example.com/calendar/, the whole suite
    on one address: iosuite_shared.prefix), where /api/… is somebody else's. Every script, page, stylesheet and
    manifest under static/ is read, but for the folders in `skip` (the browser extension talks to a server it is
    given the address of; vendor code is not ours)."""
    import re
    from pathlib import Path
    found = []
    for f in sorted(Path(root, "static").rglob("*")):
        if f.suffix not in (".js", ".html", ".css", ".webmanifest") or set(f.relative_to(root).parts) & set(skip):
            continue
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(ABSOLUTE, line) or (f.suffix == ".html" and re.search(ABSOLUTE_ATTR, line)):
                found.append(f"{f.relative_to(root)}:{n}: {line.strip()[:120]}")
    assert not found, "addresses from the root of the server in the page (write api/…, static/… without the first slash):\n" + "\n".join(found)


def check_folder(client, folder: str = "/suite-app", host: str = "home.example.com") -> None:
    """The app answers in a folder of an address (iosuite_shared.prefix) as it does at the root: the page, its files,
    the manifest and the API, whether the proxy in front took the folder off the path or left it; the folder without
    its slash goes to the one with it; the API's docs find their document; and a request that names another host
    (straight to the app's port) has no folder. One test per app calls this with its client."""
    import re
    old = os.environ.get("PUBLIC_URL")
    os.environ["PUBLIC_URL"] = f"https://{host}{folder}"
    try:
        h = {"host": host}
        for kept in (folder, ""):  # the proxy left the folder on the path; it took it off
            r = client.get(kept + "/", headers=h)
            assert r.status_code == 200 and "<html" in r.text.lower(), f"GET {kept}/ answers {r.status_code}"
            assert not re.search(ABSOLUTE_ATTR, r.text) and not re.search(ABSOLUTE, r.text), "the page names an address from the root of the server"
            assert client.get(kept + "/api/status", headers=h).status_code == 200, f"GET {kept}/api/status"
            for name in re.findall(r"""(?:src|href)="(static/[^"?]+|manifest\.webmanifest)""", r.text):
                assert client.get(f"{kept}/{name}", headers=h).status_code == 200, f"GET {kept}/{name}"
        r = client.get(folder + "?x=1", headers=h, follow_redirects=False)
        assert r.status_code == 308 and r.headers["location"] == folder + "/?x=1", "the folder without its slash goes to the folder"
        r = client.get("/api/docs", headers=h)
        if r.status_code == 200:
            assert f"{folder}/api/openapi.json" in r.text, "the API's docs page looks for its document outside the folder"
        assert client.get(folder + "/api/status").status_code == 404, "a request that does not name the public host has no folder"
    finally:
        if old is None:
            os.environ.pop("PUBLIC_URL", None)
        else:
            os.environ["PUBLIC_URL"] = old


def api_routes(app) -> list:
    """Every API route of the FastAPI app as (methods, full path, route), through included routers. FastAPI keeps an
    included router as one entry of app.routes, so a plain walk of app.routes sees none of its routes (and a check
    over them passes with nothing checked)."""
    from fastapi.routing import APIRoute, iter_route_contexts
    return [(set(c.methods or ()), c.path, c.original_route) for c in iter_route_contexts(app.routes) if isinstance(c.original_route, APIRoute)]


def check_access_declared(app, declared, ignore=("/api/openapi.json", "/api/docs"), prefix="/api/") -> None:
    """Every API route of the FastAPI app carries exactly one access marker (dependencies=[access.<level>]), so a new
    route can never be open to everyone by mistake. `declared` is the app's access.declared (Auth.access.declared)."""
    routes = [(m, p, r) for m, p, r in api_routes(app) if p.startswith(prefix) and p not in ignore]
    assert routes, f"no API routes under {prefix}: nothing was checked"
    missing = [f"{sorted(m)} {p}" for m, p, r in routes if declared(r) is None]
    assert not missing, "routes without exactly one access marker (dependencies=[access.<level>]):\n" + "\n".join(missing)
