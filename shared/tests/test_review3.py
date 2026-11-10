"""The lower findings of the code review of 10 November 2026: a revoked app password stops at once, Cloudflare's keys
are not fetched for every made-up key id (test_review.py), the apps cannot be framed by another site, a page in a
browser reaches the MCP endpoint only under a name the app is known by, a proxy client without cookies keeps one
session, the account list and the version stay inside the network, a query is one round trip, and a ValueError that
no validation raised is logged with its traceback."""
import base64
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import Invalid, apppasswords, db, sessions, suite, users
from iosuite_shared.fastapi import Auth

LAN = ("192.168.1.20", 50000)
OUTSIDE = ("8.8.8.8", 50000)
PROXY = ("192.168.1.5", 50001)


class Version:
    """What the status route asks an Updater."""
    version = "1.2.3"

    def local_commit(self):
        return "0123456789abcdef"

    def auto_check_enabled(self):
        return False


def make_app(name="iocontacts", mcp_on=True, **kw):
    auth = Auth(name, register=False, **kw)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_paths=("/",), before=auth.mcp_gate(lambda: mcp_on)))
    app.include_router(auth.router())
    app.include_router(auth.status_router(Version()))

    @app.get("/")
    def shell():
        return {"shell": True}

    @app.post("/mcp", dependencies=[auth.access.public])
    def mcp():
        return {"mcp": True}

    @app.post("/api/checked", dependencies=[auth.access.public])
    def checked():
        raise Invalid("A name is needed")

    @app.post("/api/unchecked", dependencies=[auth.access.public])
    def unchecked():
        return {"n": int("twelve")}

    auth.install(app)
    return app, auth


def basic(name, pw):
    return {"authorization": "Basic " + base64.b64encode(f"{name}:{pw}".encode()).decode()}


@pytest.fixture(autouse=True)
def clean():
    users._attempts.clear()
    users._known.clear()
    apppasswords.forget()
    sessions._proxy_sessions.clear()
    yield
    users._attempts.clear()
    users._known.clear()


# ---- S-8
def test_a_revoked_app_password_stops_at_once_in_every_process():
    alex = users.create("alex", "secret123", "editor", "iocontacts")
    pw = apppasswords.create(alex["id"], "iocontacts", "Phone")
    assert apppasswords.authenticate("alex", pw, "iocontacts")["name"] == "alex"
    assert apppasswords._cache  # remembered: the next check computes no hash
    # another process (another app's server) revokes it: this one's cache is not cleared
    db.ex("DELETE FROM ios_app_passwords WHERE user_id = %s", (alex["id"],))
    assert apppasswords.authenticate("alex", pw, "iocontacts") is None
    # a scope set elsewhere counts at once too
    pw = apppasswords.create(alex["id"], "iocontacts", "Phone")
    assert apppasswords.authenticate_scoped("alex", pw, "iocontacts")[1] == ""
    db.ex("UPDATE ios_app_passwords SET scope = 'dav' WHERE user_id = %s", (alex["id"],))
    assert apppasswords.authenticate_scoped("alex", pw, "iocontacts")[1] == "dav"
    # and the account password, remembered the same way, stops when it is changed elsewhere
    assert apppasswords.authenticate("alex", "secret123", "iocontacts")["name"] == "alex"
    db.ex("UPDATE ios_users SET hash = %s WHERE id = %s", (users.hash_password("another-one"), alex["id"]))
    assert apppasswords.authenticate("alex", "secret123", "iocontacts") is None


# ---- S-10
def test_the_apps_cannot_be_framed_by_another_site():
    app, _ = make_app()
    for path in ("/", "/api/status"):
        h = TestClient(app, client=LAN).get(path).headers
        assert h["x-frame-options"] == "SAMEORIGIN" and h["content-security-policy"] == "frame-ancestors 'self'"
        assert h["x-content-type-options"] == "nosniff"


# ---- S-11
def test_a_page_in_a_browser_reaches_mcp_only_under_a_known_name(monkeypatch):
    app, auth = make_app()
    alex = users.create("alex", "secret123", "editor", "iocontacts")
    pw = apppasswords.create(alex["id"], "iocontacts", "Assistant")
    for host in ("192.168.1.10:8640", "contacts.lan", "nas:8640", "localhost:8640", "[fd00::1]:8640", "contacts.local"):
        r = TestClient(app, base_url=f"http://{host}", client=LAN).post("/mcp", headers={**basic("alex", pw), "origin": f"http://{host}"})
        assert r.status_code == 200, host
    evil = TestClient(app, base_url="http://rebind.evil.example", client=LAN)
    r = evil.post("/mcp", headers={**basic("alex", pw), "origin": "http://rebind.evil.example"})
    assert r.status_code == 403 and "not known by the name" in r.json()["detail"]
    assert evil.post("/mcp", headers={**basic("alex", pw), "sec-fetch-site": "same-origin"}).status_code == 403
    assert evil.post("/mcp", headers=basic("alex", pw)).status_code == 200  # an MCP client is not a browser: no Origin, not asked
    # the app's own addresses are known: PUBLIC_URL, and the shared cookie domain
    suite.register("iocontacts", name="ioContacts", url="https://contacts.example.org")
    suite._hosts.clear()
    pub = TestClient(app, base_url="https://contacts.example.org", client=LAN)
    assert pub.post("/mcp", headers={**basic("alex", pw), "origin": "https://contacts.example.org"}).status_code == 200
    monkeypatch.setattr("iosuite_shared.config.COOKIE_DOMAIN", "example.com")
    dom = TestClient(app, base_url="https://contacts.example.com", client=LAN)
    assert dom.post("/mcp", headers={**basic("alex", pw), "origin": "https://contacts.example.com"}).status_code == 200
    assert not suite.known_host("iocontacts", "example.com.evil.example") and not suite.known_host("iocontacts", "")


# ---- S-12
def test_a_proxy_client_without_cookies_keeps_one_session():
    app, _ = make_app()
    alex = users.create("alex", "secret123", "editor", "iocontacts", email="alex@example.com")
    db.set_setting("auth_proxy", "nginx", "")
    db.set_setting("auth_proxy_trusted", PROXY[0], "")
    who = {"remote-user": "alex", "user-agent": "curl/8"}
    for _ in range(5):
        c = TestClient(app, base_url="http://contacts.lan", client=PROXY)  # a new client each time: no cookie kept
        assert c.get("/api/auth/me", headers=who).json()["user"]["name"] == "alex"
    assert len(sessions.list_sessions(alex["id"])) == 1
    # another client of the same account gets its own; ending the session makes a new one next time
    assert TestClient(app, base_url="http://contacts.lan", client=PROXY).get("/api/auth/me", headers={**who, "user-agent": "feed/1"}).status_code == 200
    assert len(sessions.list_sessions(alex["id"])) == 2
    sessions.end_all(alex["id"])
    assert TestClient(app, base_url="http://contacts.lan", client=PROXY).get("/api/auth/me", headers=who).status_code == 200
    assert len(sessions.list_sessions(alex["id"])) == 1


def test_a_session_is_ended_by_its_exact_id():
    alex = users.create("alex", "secret123", "editor", "iocontacts")
    for _ in range(3):
        sessions.create(alex["id"], "iocontacts", "password")
    ids = [s["id"] for s in sessions.list_sessions(alex["id"])]
    for bad in ("%", "", "_" * 16, ids[0][:4], ids[0].upper() + "%"):
        with pytest.raises(Invalid):
            sessions.end_one(alex["id"], bad)
    assert len(sessions.list_sessions(alex["id"])) == 3
    sessions.end_one(alex["id"], ids[0])
    assert [s["id"] for s in sessions.list_sessions(alex["id"])] == ids[1:]


# ---- S-13
def test_the_account_list_and_the_version_stay_inside_the_network():
    app, _ = make_app()
    users.create("alex", "secret123", "editor", "iocontacts")
    users.create("kid", "", "viewer", "iocontacts")
    inside = TestClient(app, base_url="http://contacts.lan", client=LAN)
    assert [a["name"] for a in inside.get("/api/auth/accounts").json()["accounts"]] == ["alex", "kid"]
    assert inside.get("/api/status").json()["version"] == "1.2.3"
    for c in (TestClient(app, base_url="http://contacts.example.org", client=OUTSIDE),
              TestClient(app, base_url="http://contacts.example.org", client=LAN, headers={"cf-ray": "abc-EWR"})):
        assert c.get("/api/auth/accounts").json() == {"accounts": []}
        s = c.get("/api/status").json()
        assert s["ok"] and s["version"] is None
        assert c.post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200
        assert c.get("/api/status").json()["version"] == "1.2.3"  # signed in: the version is theirs to see


# ---- S-14
def test_a_query_is_one_round_trip_and_a_transaction_is_still_one():
    sent = []

    def connect():
        con = db.connect()
        real = con._execute_command
        con._execute_command = lambda command, sql: (sent.append(sql if isinstance(sql, str) else sql.decode()), real(command, sql))[1]
        return con

    d = db.Database(connect, size=2)
    d.q("SELECT 1")  # opens the connection
    del sent[:]
    assert d.one("SELECT 2 AS n")["n"] == 2 and d.q("SELECT 3 AS n")[0]["n"] == 3
    assert sent == ["SELECT 2 AS n", "SELECT 3 AS n"]  # no ping, no commit
    del sent[:]
    with d.tx() as con:
        d.ex("INSERT INTO ios_settings (app, name, value) VALUES ('t', 'a', '1')")
        with d.tx() as inner:  # nested: the same connection, the same transaction
            assert inner is con
            d.ex("INSERT INTO ios_settings (app, name, value) VALUES ('t', 'b', '2')")
        assert db.one("SELECT COUNT(*) AS n FROM ios_settings WHERE app = 't'")["n"] == 0  # not committed yet: another connection sees nothing
    assert sent[0] == "BEGIN" and sent[-1] == "COMMIT" and len(sent) == 4
    assert d.one("SELECT COUNT(*) AS n FROM ios_settings WHERE app = 't'")["n"] == 2
    with pytest.raises(RuntimeError):
        with d.tx():
            d.ex("DELETE FROM ios_settings WHERE app = 't'")
            raise RuntimeError("rolled back")
    assert d.one("SELECT COUNT(*) AS n FROM ios_settings WHERE app = 't'")["n"] == 2
    d.many("INSERT INTO ios_settings (app, name, value) VALUES ('t', %s, %s)", [("c", "3"), ("d", "4")])
    assert d.one("SELECT COUNT(*) AS n FROM ios_settings WHERE app = 't'")["n"] == 4
    # a connection that sat unused is pinged before it is lent again
    con, _ = d.pool._kept.get_nowait()
    d.pool._kept.put_nowait((con, 0.0))
    pings = []
    con.ping = lambda reconnect=False: pings.append(1)
    d.q("SELECT 1")
    assert pings == [1]
    d.pool.drain()


def test_a_pool_of_connections_that_commit_themselves_still_works():
    """An app whose `connect` leaves autocommit off: every unit of work is committed at its end, as before."""
    import pymysql
    p = db.params()
    d = db.Database(lambda: pymysql.connect(host=p["host"], port=int(p["port"]), user=p["user"], password=p["password"], database=p["database"],
                                            cursorclass=pymysql.cursors.DictCursor, autocommit=False))
    d.ex("INSERT INTO ios_settings (app, name, value) VALUES ('t', 'a', '1')")
    with d.tx():
        d.ex("INSERT INTO ios_settings (app, name, value) VALUES ('t', 'b', '2')")
    assert db.one("SELECT COUNT(*) AS n FROM ios_settings WHERE app = 't'")["n"] == 2
    d.pool.drain()


# ---- S-15
def test_a_value_error_no_validation_raised_is_logged_with_its_traceback(caplog):
    app, _ = make_app()
    c = TestClient(app, client=LAN)
    with caplog.at_level(logging.INFO, logger="iosuite_shared.iocontacts"):
        r = c.post("/api/checked")
        assert r.status_code == 400 and r.json()["detail"] == "Bad request: A name is needed"
        assert not [x for x in caplog.records if x.exc_info]
        r = c.post("/api/unchecked")
        assert r.status_code == 400 and "invalid literal" in r.json()["detail"]
        assert [x for x in caplog.records if x.levelno == logging.WARNING and x.exc_info]
    assert issubclass(Invalid, ValueError)
    with pytest.raises(ValueError):
        users.clean_name("")


def test_a_chore_runs_again_after_it_failed():
    import asyncio
    from iosuite_shared import chores
    runs = []

    def chore():
        runs.append(1)
        if len(runs) == 1:
            raise RuntimeError("the database was away")

    async def go():
        task = chores.start(chore, every_s=0.01, first_s=0)
        await asyncio.sleep(0.2)
        task.cancel()

    asyncio.run(go())
    assert len(runs) >= 2


# ---- outbound requests
def test_an_outbound_request_goes_only_where_it_may():
    import http.server
    import ipaddress
    import threading
    import urllib.error
    from iosuite_shared import outbound

    assert outbound.public(ipaddress.ip_address("93.184.215.14")) and not outbound.public(ipaddress.ip_address("192.168.1.5"))
    assert outbound.not_this_machine(ipaddress.ip_address("192.168.1.5"))
    assert not outbound.not_this_machine(ipaddress.ip_address("127.0.0.1")) and not outbound.not_this_machine(ipaddress.ip_address("169.254.169.254"))
    with pytest.raises(outbound.NotAllowed):
        outbound.address("127.0.0.1", 80)
    assert outbound.address("127.0.0.1", 80, allowed=lambda ip: True) == "127.0.0.1"
    for url in ("file:///etc/passwd", "ftp://example.com/x", "http://"):
        with pytest.raises(Invalid):
            outbound.check(url)
    assert issubclass(outbound.NotAllowed, Invalid)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/away":
                self.send_response(302)
                self.send_header("Location", "http://169.254.169.254/latest/meta-data")
                self.end_headers()
                return
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"here")

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        with pytest.raises(outbound.NotAllowed):  # the default: the internet only
            outbound.opener().open(base + "/", timeout=5)
        local = lambda ip: ip.is_loopback
        assert outbound.opener(local).open(base + "/", timeout=5).read() == b"here"
        with pytest.raises(outbound.NotAllowed):  # a redirect is checked like the first address, before anything is sent
            outbound.opener(local).open(base + "/away", timeout=5)
        with pytest.raises(urllib.error.HTTPError) as e:  # redirects off: the 302 is the answer
            outbound.opener(local, redirects=False).open(base + "/away", timeout=5)
        assert e.value.code == 302
    finally:
        srv.shutdown()
        srv.server_close()
