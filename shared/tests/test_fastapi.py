from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import users
from iosuite_shared.fastapi import Auth


def make_app(name="iopix", read_only=False):
    auth = Auth(name, read_only=lambda: read_only)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_paths=("/", "/api/status"), open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.users_router())

    @app.get("/api/status", dependencies=[auth.access.public])
    def status():
        return {"ok": True}

    @app.get("/api/private", dependencies=[auth.access.signed_in])
    def private():
        return {"ok": True}

    @app.post("/api/edit", dependencies=[auth.access.editor_write])
    def edit():
        return {"ok": True}

    @app.get("/api/admin", dependencies=[auth.access.admin])
    def admin():
        return {"ok": True}
    return app, auth


def test_open_until_first_user_then_setup_and_login():
    app, _ = make_app()
    c = TestClient(app, base_url="http://photo.example.com")
    assert c.get("/api/admin").status_code == 200  # no accounts yet: open
    r = c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
    assert r.status_code == 200 and r.json()["user"]["suiteAdmin"]
    assert "iothing_session" in r.cookies
    assert c.get("/api/auth/me").json()["isAdmin"]
    assert c.post("/api/auth/setup", json={"name": "x", "password": "secret123"}).status_code == 409
    c2 = TestClient(app, base_url="http://photo.example.com")
    assert c2.get("/api/admin").status_code == 401
    assert c2.post("/api/auth/login", json={"name": "alex", "password": "nope"}).status_code == 401
    assert c2.post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200
    assert c2.get("/api/admin").status_code == 200
    r = c2.post("/api/auth/logout")
    assert r.status_code == 200
    assert c2.get("/api/admin").status_code == 401
    assert c.get("/api/admin").status_code == 200, "Sign out ends this browser's session only"
    assert c.post("/api/auth/logout_all").status_code in (404, 405), "one kind of sign out: Sign out"


def test_session_shared_between_apps_with_their_own_roles():
    pix, _ = make_app("iopix")
    notes, _ = make_app("ionotes")
    users.create("alex", "secret123", "admin", "iopix", suite_admin=True)
    users.create("bob", "secret123", "editor", "iopix")
    users.set_role(users.find("bob")["id"], "ionotes", "viewer")
    c = TestClient(pix, base_url="http://photo.example.com")
    r = c.post("/api/auth/login", json={"name": "bob", "password": "secret123"})
    cookie = r.cookies["iothing_session"]
    assert c.post("/api/edit").status_code == 200
    n = TestClient(notes, base_url="http://notes.example.com", cookies={"iothing_session": cookie})
    me = n.get("/api/auth/me").json()
    assert me["user"]["name"] == "bob" and me["user"]["role"] == "viewer" and me["signedIn"]
    assert n.post("/api/edit").status_code == 403
    users.set_role(users.find("bob")["id"], "ionotes", "none")
    from iosuite_shared import sessions
    sessions.invalidate()
    assert n.get("/api/private").status_code == 401  # no access there
    assert n.post("/api/auth/login", json={"name": "bob", "password": "secret123"}).status_code == 403


def test_require_login_and_cross_site():
    app, auth = make_app()
    users.create("alex", "secret123", "admin", "iopix", suite_admin=True)
    c = TestClient(app, base_url="http://photo.example.com")
    assert c.get("/api/status").status_code == 200
    users.db.set_setting("require_login", "1", "iopix")
    assert c.get("/api/status").status_code == 200  # open path
    assert c.get("/api/private").status_code == 401
    c.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert c.get("/api/private").status_code == 200
    assert c.post("/api/edit", headers={"origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/edit", headers={"origin": "http://photo.example.com"}).status_code == 200


def test_users_admin_api_and_read_only():
    app, _ = make_app(read_only=True)
    users.create("alex", "secret123", "admin", "iopix", suite_admin=True)
    c = TestClient(app, base_url="http://photo.example.com")
    c.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert c.post("/api/edit").status_code == 403  # read-only
    r = c.post("/api/users", json={"name": "bob", "password": "secret123", "role": "editor"})
    assert r.status_code == 200 and r.json()["role"] == "editor"
    uid = r.json()["id"]
    assert c.patch(f"/api/users/{uid}", json={"role": "viewer", "roles": {"ionotes": "admin"}}).status_code == 200
    lst = c.get("/api/users").json()
    bob = next(u for u in lst["users"] if u["name"] == "bob")
    assert bob["role"] == "viewer" and bob["roles"] == {"iopix": "viewer", "ionotes": "admin"}
    assert c.post("/api/auth/settings", json={"theme": "dark"}).json() == {"theme": "dark"}
    assert c.post("/api/auth/password", json={"current": "wrong", "password": "newpass123"}).status_code == 403
    assert c.post("/api/auth/password", json={"current": "secret123", "password": ""}).status_code == 400  # never removes the password
    assert c.post("/api/auth/password", json={"current": "secret123", "password": "newpass123"}).status_code == 200
    assert c.get("/api/private").status_code == 200  # this session went on
    assert c.post(f"/api/users/{uid}", json={"delete": True}).status_code == 405  # one way to delete: DELETE
    assert c.delete(f"/api/users/{uid}").status_code == 200
    assert users.get(uid) is None


def test_app_password_basic_and_bearer():
    app, _ = make_app("iocontacts")
    u = users.create("alex", "secret123", "editor", "iocontacts")
    from iosuite_shared import apppasswords
    pw = apppasswords.create(u["id"], "iocontacts", "Mac")
    c = TestClient(app, base_url="http://contacts.example.com")
    assert c.get("/api/private").status_code == 401
    assert c.get("/api/private", headers={"authorization": "Bearer " + pw}).status_code == 200
    import base64
    basic = base64.b64encode(f"alex:{pw}".encode()).decode()
    assert c.get("/api/private", headers={"authorization": "Basic " + basic}).status_code == 200
    assert c.get("/api/private", headers={"authorization": "Bearer nope"}).status_code == 401


def test_unreachable_auth_database_answers_503_not_open(monkeypatch):
    from iosuite_shared import db
    app, _ = make_app()
    c = TestClient(app, base_url="http://photo.example.com")
    db._ready = False
    db._retry_at = 0.0
    monkeypatch.setattr(db, "params", lambda: {"host": "203.0.113.1", "port": 1, "database": "x", "user": "x", "password": "x"})
    db._pool.drain()  # the kept connections still reach the test database
    assert c.get("/api/status").status_code == 200  # the open path still answers
    r = c.get("/api/admin")
    assert r.status_code == 503 and "Shared ioSuite database" in r.json()["detail"]
    assert c.post("/api/auth/login", json={"name": "a", "password": "b"}).status_code == 503


def test_sessions_record_where_they_began_and_were_seen():
    from iosuite_shared import sessions
    app, _ = make_app()
    users.create("alex", "secret123", "admin", "iopix", suite_admin=True)
    web = TestClient(app, base_url="http://photo.example.com", headers={"user-agent": "Mozilla/5.0 (Macintosh) Safari/605"})
    web.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    phone = TestClient(app, base_url="http://photo.example.com", headers={"user-agent": "iopix/312 CFNetwork/1498 Darwin/25.0", "cf-ray": "abc", "cf-connecting-ip": "203.0.113.9"})
    phone.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    lst = web.get("/api/auth/sessions").json()["sessions"]
    assert len(lst) == 2
    by = {s["client"]: s for s in lst}
    assert by["web"]["current"] and not by["web"]["cloudflare"] and by["web"]["ip"] == "testclient"
    assert not by["iopix"]["current"] and by["iopix"]["cloudflare"] and by["iopix"]["userAgent"].startswith("iopix/312") and by["iopix"]["lastSeen"]
    assert web.delete(f"/api/auth/sessions/{by['iopix']['id']}").status_code == 200
    assert phone.get("/api/auth/me").json()["user"] is None  # ended
    assert len(web.get("/api/users/1/sessions").json()["sessions"]) == 1  # admins see an account's sessions
    assert web.delete("/api/users/1/sessions").status_code == 200
    sessions.invalidate()
    assert web.get("/api/auth/me").json()["user"] is None
    assert sessions.classify("curl/8.0") == "curl" and sessions.classify("") == "other"


def test_scoped_app_password_reaches_only_its_paths():
    import base64
    from iosuite_shared import apppasswords
    app, auth = make_app("iocalendar")

    @app.api_route("/dav/{rest:path}", methods=["GET", "PROPFIND"], dependencies=[auth.access.signed_in])
    def dav(rest: str):
        return {"ok": True}

    u = users.create("alex", "secret123", "editor", "iocalendar")
    dav_pw = apppasswords.create(u["id"], "iocalendar", "iPhone", apppasswords.DAV)
    full = apppasswords.create(u["id"], "iocalendar", "script")
    c = TestClient(app, base_url="http://calendar.example.com")
    basic = lambda pw: {"authorization": "Basic " + base64.b64encode(f"alex:{pw}".encode()).decode()}
    for _ in range(2):  # the second time from the cache
        assert c.get("/dav/calendars/alex/", headers=basic(dav_pw)).status_code == 200
        assert c.get("/api/private", headers=basic(dav_pw)).status_code == 403
        assert c.get("/api/private", headers={"authorization": "Bearer " + dav_pw}).status_code == 403
        assert c.get("/api/private", headers=basic(full)).status_code == 200
        assert c.get("/dav/x", headers=basic(full)).status_code == 200
    assert apppasswords.authenticate_scoped("alex", dav_pw, "iocalendar")[1] == "dav"
    assert apppasswords.authenticate_scoped("alex", "secret123", "iocalendar")[1] == ""
    assert apppasswords.authenticate_scoped("alex", "nope", "iocalendar") == (None, None)
    # the routes: scope in, scope out, an unknown one refused; set_scope for apps moving their own record here
    c.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    r = c.post("/api/auth/app-passwords", json={"label": "Mac", "scope": "dav"}).json()
    assert r["scope"] == "dav"
    assert c.post("/api/auth/app-passwords", json={"label": "x", "scope": "ldap"}).status_code == 400
    listed = c.get("/api/auth/app-passwords").json()
    assert listed["scopes"] == ["", "dav"]
    assert {p["label"]: p["scope"] for p in listed["items"]} == {"iPhone": "dav", "script": "", "Mac": "dav"}
    assert apppasswords.set_scope("iocalendar", full.split("-")[1], "dav") == 1
    c.cookies.clear()
    assert c.get("/api/private", headers=basic(full)).status_code == 403


def test_settings_account_panel_and_its_own_fields():
    """Settings › Account, the same in every app: the panel module, and the account's display name and email."""
    app, auth = make_app()
    seen = []
    auth.on_update = lambda uid, body: seen.append((uid, sorted(body)))
    c = TestClient(app, base_url="http://photo.example.com")
    c.post("/api/auth/setup", json={"name": "alex", "password": "secret123"})
    ui = c.get("/api/auth/ui.js")
    assert ui.status_code == 200 and "javascript" in ui.headers["content-type"]
    assert "export async function mountAccount" in ui.text and "export async function mountAppPasswords" in ui.text
    r = c.patch("/api/auth/me", json={"displayName": "Alex V", "email": "Alex@Example.com"})
    assert r.status_code == 200 and r.json()["user"]["displayName"] == "Alex V" and r.json()["user"]["email"] == "alex@example.com"
    assert c.get("/api/auth/me").json()["user"]["displayName"] == "Alex V" and seen and seen[-1][1] == ["displayName", "email"]
    assert c.patch("/api/auth/me", json={"displayName": ""}).json()["user"]["displayName"] in (None, "", "alex")
    c.post("/api/auth/logout")
    assert c.patch("/api/auth/me", json={"displayName": "x"}).status_code in (401, 403)


# ---- Apple profiles (iosuite_shared.appleprofile)
def _profile_app(name):
    auth = Auth(name, app_label="ioTasks")
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_paths=("/",), open_prefixes=("/api/auth/", "/profile/")))
    app.include_router(auth.router())
    app.include_router(auth.profile_router(lambda request: "https://tasks.example.com"))
    return app


def _sync_suite(*apps):
    from iosuite_shared import suite
    for a, name, url in (("iocalendar", "ioCalendar", "https://calendar.example.com"), ("iocontacts", "ioContacts", "http://contacts.lan:8640"),
                         ("iotasks", "ioTasks", None), ("iopix", "ioPix", "https://photo.example.com")):
        if a in apps:
            suite.register(a, name=name, url=url)


def test_suite_profile_has_every_sync_app_with_its_own_password():
    import plistlib
    from iosuite_shared import apppasswords
    _sync_suite("iocalendar", "iocontacts", "iotasks", "iopix")
    users.create("alex", "secret123", "admin", "iotasks", suite_admin=True)
    c = TestClient(_profile_app("iotasks"), base_url="https://tasks.example.com")
    assert c.get("/api/apple-profile/suite").status_code == 401
    c.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert [a["app"] for a in c.get("/api/apple-profile/suite").json()["apps"]] == ["iocalendar", "iocontacts", "iotasks"]
    url = c.post("/api/apple-profile/suite/link", json={"label": "Phone", "password": "new"}).json()["url"]
    assert url.endswith("/iosuite-alex.mobileconfig")
    r = TestClient(_profile_app("iotasks"), base_url="https://tasks.example.com").get(url)  # no cookie: the token is the secret
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-apple-aspen-config")
    p = plistlib.loads(r.content)
    assert p["PayloadIdentifier"] == "net.iothing.iosuite.tasks.example.com.alex" and p["PayloadDisplayName"] == "ioSuite for alex"
    cal, con, tsk = p["PayloadContent"]
    assert (cal["PayloadType"], cal["CalDAVHostName"], cal["CalDAVPort"], cal["CalDAVUseSSL"]) == ("com.apple.caldav.account", "calendar.example.com", 443, True)
    assert (con["PayloadType"], con["CardDAVHostName"], con["CardDAVPort"], con["CardDAVUseSSL"]) == ("com.apple.carddav.account", "contacts.lan", 8640, False)
    assert (tsk["CalDAVHostName"], tsk["CalDAVAccountDescription"], tsk["CalDAVPrincipalURL"]) == ("tasks.example.com", "ioTasks", "/dav/principals/alex/")
    uid = users.find("alex")["id"]
    for app, pw in (("iocalendar", cal["CalDAVPassword"]), ("iocontacts", con["CardDAVPassword"]), ("iotasks", tsk["CalDAVPassword"])):
        assert pw.startswith(app + "-"), "each account has an app password of its own app"
        (row,) = apppasswords.list_for(uid, app)
        assert row["scope"] == apppasswords.DAV and row["label"] == "Phone (profile)"
    assert not apppasswords.list_for(uid, "iopix")
    # "ask": no passwords in the file, none made
    r = c.post("/api/apple-profile/suite", data={"label": "Mac", "password": "ask"})
    assert not any(k.endswith("Password") for x in plistlib.loads(r.content)["PayloadContent"] for k in x)
    assert len(apppasswords.list_for(uid, "iotasks")) == 1
    assert c.get("/profile/nope/x.mobileconfig").status_code == 404


def test_suite_profile_only_for_two_or_more_apps_the_account_may_use():
    _sync_suite("iotasks", "iopix")
    users.create("alex", "secret123", "admin", "iotasks", suite_admin=True)
    users.create("bob", "secret123", "member", "iotasks")
    c = TestClient(_profile_app("iotasks"), base_url="https://tasks.example.com")
    c.post("/api/auth/login", json={"name": "alex", "password": "secret123"})
    assert [a["app"] for a in c.get("/api/apple-profile/suite").json()["apps"]] == ["iotasks"]
    assert c.post("/api/apple-profile/suite/link", json={}).status_code == 409
    _sync_suite("iocalendar")
    assert len(c.get("/api/apple-profile/suite").json()["apps"]) == 2
    users.set_role(users.find("bob")["id"], "iocalendar", "none")
    b = TestClient(_profile_app("iotasks"), base_url="https://tasks.example.com")
    b.post("/api/auth/login", json={"name": "bob", "password": "secret123"})
    assert [a["app"] for a in b.get("/api/apple-profile/suite").json()["apps"]] == ["iotasks"], "not an app the account has no role in"
    assert b.post("/api/apple-profile/suite", data={}).status_code == 409
