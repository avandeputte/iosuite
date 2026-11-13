"""The behaviours the second code review (2026-11-10) asked for: what an admin of one app may do to an account, the
"no accounts yet: open" rule kept to the network the server is on, a reverse proxy that is not listed counting as
outside, the app's address taken from an admin's request only, and a name-wide wait that does not lock its owner out."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import apppasswords, db, links, proxyauth, suite, users
from iosuite_shared.fastapi import Auth

LAN = ("192.168.1.20", 50000)       # a browser on the network
PROXY = ("192.168.1.5", 50001)      # a reverse proxy on another machine of the network


def make_app(name="iocontact", register=False, **kw):
    auth = Auth(name, register=register, **kw)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_paths=("/",), open_prefixes=("/static/",)))
    app.include_router(auth.router())
    app.include_router(auth.users_router())
    app.include_router(auth.admin_router())

    @app.get("/")
    def shell():
        return {"shell": True}

    @app.get("/api/data", dependencies=[auth.access.public])
    def data():
        return {"ok": True}

    @app.post("/api/change", dependencies=[auth.access.admin])
    def change():
        return {"ok": True}

    auth.install(app)
    return app, auth


def signed_in(app, name, password="secret123", client=LAN):
    c = TestClient(app, base_url="http://contacts.lan:8640", client=client)
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


@pytest.fixture(autouse=True)
def clean():
    users._attempts.clear()
    users._known.clear()
    apppasswords.forget()
    yield
    users._attempts.clear()
    users._known.clear()


# ---- an admin of one app and the suite's accounts
def test_an_app_admin_sets_roles_here_and_nothing_beyond():
    app, _ = make_app()
    boss = users.create("alex", "secret123", suite_admin=True, email="alex@example.com")
    users.create("bob", "secret123", "admin", "iocontact")
    ann = users.create("ann", "secret123", "viewer", "iocontact", email="ann@example.com")
    bob = signed_in(app, "bob")
    # the role here: his to give
    assert bob.patch(f"/api/users/{ann['id']}", json={"role": "editor"}).status_code == 200
    assert users.get(ann["id"], "iocontact")["role"] == "editor"
    # a form that sends the other fields back unchanged is fine
    assert bob.patch(f"/api/users/{ann['id']}", json={"role": "viewer", "name": "ann", "email": "ann@example.com"}).status_code == 200
    # the account itself is the suite's: sign-in at a proxy finds it by email and name, a password opens every app
    for body in ({"email": "alex@example.com"}, {"name": "ann2"}, {"password": "another-secret"}, {"displayName": "X"},
                 {"listed": False}, {"suiteAdmin": True}, {"roles": {"iopix": "admin"}}):
        r = bob.patch(f"/api/users/{ann['id']}", json=body)
        assert r.status_code == 403 and "suite admin" in r.json()["detail"], body
    for body in ({"name": "bob2"}, {"email": "bob@example.com"}, {"role": "viewer"}):
        assert bob.patch(f"/api/users/{boss['id']}", json=body).status_code == 403, body
    again = users.get(ann["id"], "iocontact")
    assert (again["name"], again["email"], again["suiteAdmin"]) == ("ann", "ann@example.com", False)
    assert users.get(boss["id"])["name"] == "alex" and users.authenticate("ann", "secret123")
    # nor its sessions, nor deleting it
    assert bob.get(f"/api/users/{ann['id']}/sessions").status_code == 403
    assert bob.delete(f"/api/users/{ann['id']}/sessions").status_code == 403
    assert bob.delete(f"/api/users/{ann['id']}").status_code == 403 and users.get(ann["id"])
    # a suite admin does all of it
    alex = signed_in(app, "alex")
    assert alex.patch(f"/api/users/{ann['id']}", json={"email": "ann@new.example.com", "role": "editor"}).status_code == 200
    assert users.get(ann["id"])["email"] == "ann@new.example.com"
    assert alex.get(f"/api/users/{ann['id']}/sessions").status_code == 200
    assert alex.delete(f"/api/users/{ann['id']}").status_code == 200 and not users.get(ann["id"])


def test_an_app_admin_cannot_name_himself_the_proxy():
    """The path the review ran: save AUTH_PROXY=header with one's own address, then send Remote-User: <a suite admin>."""
    app, _ = make_app()
    users.create("alex", "secret123", suite_admin=True)
    users.create("bob", "secret123", "admin", "iocontact")
    bob = signed_in(app, "bob", client=("10.0.0.5", 4444))
    body = {"AUTH_PROXY": "header", "AUTH_PROXY_TRUSTED": "10.0.0.5"}
    assert bob.post("/api/auth/proxy", json=body).status_code in (404, 405)
    assert bob.put("/api/suite-admin/proxy", json=body).status_code == 403
    assert not db.settings_of("").get("auth_proxy")
    anyone = TestClient(app, base_url="http://contacts.lan:8640", client=("10.0.0.5", 4445))
    assert anyone.get("/api/auth/me", headers={"Remote-User": "alex"}).json()["user"] is None


# ---- no accounts yet: open, but only to the network
def test_no_accounts_is_open_inside_and_shut_outside():
    app, _ = make_app()
    inside = TestClient(app, base_url="http://contacts.lan:8640", client=LAN)
    assert inside.get("/api/data").status_code == 200 and inside.post("/api/change").status_code == 200
    me = inside.get("/api/auth/me").json()
    assert me["isAdmin"] and me["isSuiteAdmin"] and not me["unclaimed"] and not me["requireLogin"]

    for client, headers in ((("8.8.8.8", 40000), {}),                                  # reached directly from the internet
                            (PROXY, {"x-forwarded-for": "8.8.8.8"}),                   # through a proxy nobody listed
                            (PROXY, {"x-forwarded-proto": "https"}),                   # (whatever it adds)
                            (LAN, {"cf-connecting-ip": "8.8.8.8"})):                   # through Cloudflare
        out = TestClient(app, base_url="http://contacts.lan:8640", client=client, headers=headers)
        assert out.get("/").status_code == 200, "the shell is served, so the page can say what to do"
        r = out.get("/api/data")
        assert r.status_code == 403 and r.json()["unclaimed"] and "inside your network" in r.json()["detail"]
        assert out.post("/api/change").status_code == 403
        assert out.post("/api/users", json={"name": "mallory", "password": "secret123", "suiteAdmin": True}).status_code == 403
        assert out.post("/api/suite-admin/users", json={"name": "mallory", "password": "secret123", "suiteAdmin": True}).status_code == 403
        assert out.put("/api/suite-admin/proxy", json={"AUTH_PROXY": "header", "AUTH_PROXY_TRUSTED": "8.8.8.8"}).status_code == 403
        assert out.delete("/api/auth/suite/iopix").status_code == 403           # under /api/auth/, which the middleware lets through
        assert out.get("/api/auth/app-passwords").status_code == 403
        assert out.post("/api/auth/setup", json={"name": "mallory", "password": "secret123"}).status_code == 403
        me = out.get("/api/auth/me").json()
        assert me["unclaimed"] and me["requireLogin"] and not (me["isAdmin"] or me["isSuiteAdmin"] or me["canWrite"] or me["signedIn"])
    assert not users.any_users()

    assert inside.post("/api/auth/setup", json={"name": "alex", "password": "secret123"}).status_code == 200
    users.invalidate()
    out = TestClient(app, base_url="http://contacts.lan:8640", client=("8.8.8.8", 40000))
    assert out.get("/api/data").status_code == 401, "with an account sign-in is required (the default)"
    db.set_setting("require_login", "0", "iocontact")
    assert out.get("/api/data").status_code == 200, "and with it turned off the usual rules apply again"
    assert out.post("/api/change").status_code == 401


# ---- inside or outside
def test_a_proxy_that_is_not_listed_counts_as_outside():
    pr = proxyauth.Proxy("iocontact")
    assert not pr.external({}, "192.168.1.20")
    assert pr.external({}, "8.8.8.8")
    # a reverse proxy on another machine: a private address, so only what it adds gives it away
    for h in ({"x-forwarded-for": "8.8.8.8"}, {"x-forwarded-for": "192.168.1.20"}, {"x-real-ip": "8.8.8.8"},
              {"forwarded": "for=8.8.8.8"}, {"x-forwarded-host": "contacts.example.com"}, {"via": "1.1 caddy"}):
        assert pr.external(h, "192.168.1.5"), h
    db.set_setting("auth_proxy_trusted", "192.168.1.5, 127.0.0.1", "")
    db.settings_cache.clear()
    assert pr.external({"x-forwarded-for": "8.8.8.8"}, "192.168.1.5")
    assert not pr.external({"x-forwarded-for": "192.168.1.20"}, "192.168.1.5")
    assert not pr.external({"x-forwarded-proto": "https"}, "192.168.1.5")
    # what the visitor sent himself stands left of what the proxy appended, and is not believed
    assert pr.external({"x-forwarded-for": "192.168.1.20, 8.8.8.8"}, "192.168.1.5")
    assert pr.forwarded_for({"x-forwarded-for": "192.168.1.20, 8.8.8.8, 127.0.0.1"}) == "8.8.8.8"
    assert not pr.external({"x-forwarded-for": "8.8.8.8, 192.168.1.20"}, "192.168.1.5")  # the proxy saw a LAN address


def test_one_click_and_setup_through_an_unlisted_proxy():
    app, _ = make_app()
    users.create("alex", "secret123", suite_admin=True)
    users.create("kid", "", "viewer", "iocontact")
    via = TestClient(app, base_url="http://contacts.lan:8640", client=PROXY, headers={"x-forwarded-for": "8.8.8.8"})
    assert [a["name"] for a in via.get("/api/auth/accounts").json()["accounts"] if a["passwordless"]] == []
    assert via.post("/api/auth/login", json={"name": "kid", "password": ""}).status_code == 403
    lan = TestClient(app, base_url="http://contacts.lan:8640", client=LAN)
    assert lan.post("/api/auth/login", json={"name": "kid", "password": ""}).status_code == 200


def test_the_throttle_counts_by_the_address_the_proxy_saw():
    db.set_setting("auth_proxy_trusted", "192.168.1.5", "")
    db.settings_cache.clear()
    app, auth = make_app()

    class R:
        scope = {"iothing.peer": "192.168.1.5"}
        client = None
        headers = {"x-forwarded-for": "1.2.3.4, 8.8.8.8"}  # 1.2.3.4: sent by the visitor, a new one for every guess
    assert auth.proxy.visitor_of(R) == "8.8.8.8 via 192.168.1.5"


# ---- the app's address
def test_only_an_admin_request_sets_the_address(monkeypatch):
    monkeypatch.setattr("iosuite_shared.config.COOKIE_DOMAIN", "example.com")
    suite.invalidate()
    app, _ = make_app("iocalendar", register=True, app_label="ioCalendar")
    users.create("alex", "secret123", "admin", "iocalendar")
    users.create("vic", "secret123", "viewer", "iocalendar")
    evil = {"host": "evil.example.net", "x-forwarded-host": "evil.example.net"}
    TestClient(app, base_url="http://192.168.1.89:8620", client=LAN).get("/api/data")
    assert suite.get("iocalendar")["seenUrl"] is None, "a visitor's request names no address"
    TestClient(app, base_url="https://evil.example.net", client=LAN).get("/api/data")
    vic = signed_in(app, "vic")
    vic.get("/api/data", headers=evil)
    assert suite.get("iocalendar")["seenUrl"] is None, "nor does an account's that is not an admin"
    assert suite.get("iocalendar")["lastSeen"], "that the app is up is noted all the same"
    alex = signed_in(app, "alex")
    alex.get("/api/data")
    assert suite.get("iocalendar")["seenUrl"] == "http://contacts.lan:8640"


def test_links_never_call_the_address_an_app_was_merely_reached_at():
    suite.register("iocontact", "ioContact")
    db.ex("UPDATE ios_apps SET seen_url = 'https://evil.example.net' WHERE app = 'iocontact'")
    assert links.url("iocontact") == "https://evil.example.net"  # for links people click
    assert links.addresses("iocontact") == [] and not links.available("iocontact")
    with pytest.raises(RuntimeError):
        links.get("iocalendar", "iocontact", "/api/contacts")
    suite.register("iocontact", "ioContact", url="https://contacts.example.com", internal_url="http://192.168.1.10:8640")
    db.ex("UPDATE ios_apps SET seen_url = 'https://evil.example.net' WHERE app = 'iocontact'")
    assert links.addresses("iocontact")[-2:] == ["http://192.168.1.10:8640", "https://contacts.example.com"]


# ---- the name-wide wait
def test_guesses_at_a_name_do_not_lock_its_owner_out():
    home, stranger = "192.168.1.20", "203.0.113.7"
    users.attempt_succeeded(home, "alex")  # the owner's laptop signed in before
    for i in range(users.LOCK_AFTER_NAME + 3):
        users.attempt_failed(f"203.0.113.{i}", "alex")  # a distributed guess: a new address each time
    assert users.attempt_wait(stranger, "alex") > 0, "anyone new waits"
    assert users.attempt_wait(home, "alex") == 0, "the owner, from where he signed in before, does not"
    for _ in range(users.LOCK_AFTER + 1):
        users.attempt_failed(home, "alex")
    assert users.attempt_wait(home, "alex") > 0, "its own wrong passwords still cost a wait"


def test_bearer_tokens_share_no_name_counter():
    for i in range(users.LOCK_AFTER_NAME + 3):
        users.attempt_failed(f"203.0.113.{i}", "")  # wrong bearer tokens from all over
    assert users.attempt_wait("192.168.1.20", "") == 0, "another client's token is not held up by them"
    assert users.attempt_keys("192.168.1.20", "")[1] is None


def test_a_counter_starts_over_after_a_quiet_quarter_of_an_hour(monkeypatch):
    for _ in range(users.LOCK_AFTER + 2):
        users.login_failed("k")
    assert users.login_wait("k") > 0
    now = users.time.time()
    monkeypatch.setattr(users.time, "time", lambda: now + users.LOCK_BASE * 2 + users.LOCK_MAX + 5)
    assert users.login_wait("k") == 0 and users.login_failed("k") == 0, "the first failure after the quiet time is free again"
