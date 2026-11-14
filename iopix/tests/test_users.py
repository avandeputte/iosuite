"""Users and permissions: open until the first user exists; then anonymous is read-only,
viewers keep settings on the server, members also favorites, editors write the library, admins
manage settings, maintenance and users; sessions are signed cookies."""
from app import users
from helpers import login as _login


def test_open_until_first_user(client, fresh):
    s = client.get("/api/status").json()
    assert s["usersExist"] is False and s["isAdmin"] is True and s["editing"] is True
    assert client.post("/api/favorites", json={"ids": [], "on": True}).status_code == 200
    assert client.post("/api/users", json={"name": "x", "password": "password1", "role": "viewer"}).status_code == 200, "open mode: anyone may create (that is how the first admin gets made)"


def test_setup_creates_the_admin_once(client, fresh):
    r = client.post("/api/auth/setup", json={"name": "alex", "password": "correct horse"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin" and users.COOKIE in r.cookies
    assert client.post("/api/auth/setup", json={"name": "eve", "password": "hackhackhack"}).status_code == 409
    me = client.get("/api/auth/me").json()
    assert me["user"]["name"] == "alex" and me["isAdmin"]


def test_anonymous_is_read_only_once_users_exist(client, fresh, lib):
    users.create("alex", "correct horse", "admin")
    client.cookies.clear()
    s = client.get("/api/status").json()
    assert s["user"] is None and s["editing"] is False and s["dbWrite"] is False and s["isAdmin"] is False
    assert client.post("/api/edit", json={"ids": [lib["ids"][0]], "rating": 3}).status_code == 401
    assert client.post("/api/settings", json={"bg_threads": 2}).status_code == 401
    assert client.post("/api/favorites", json={"ids": [], "on": True}).status_code == 401
    assert client.get("/api/photos").status_code == 200, "browsing stays open"


def test_roles(client, fresh, lib):
    users.create("alex", "correct horse", "admin"); users.create("ed", "editor-pass", "editor"); users.create("vi", "viewer-pass", "viewer")
    _login(client, "vi", "viewer-pass")
    s = client.get("/api/status").json()
    assert s["user"]["role"] == "viewer" and s["editing"] is False and s["signedIn"] is True
    assert client.post("/api/favorites", json={"ids": [lib["ids"][0]], "on": True}).status_code == 200
    assert client.post("/api/edit", json={"ids": [lib["ids"][0]], "rating": 3}).status_code == 403
    assert client.post("/api/settings", json={"bg_threads": 2}).status_code == 403
    assert client.get("/api/users").status_code == 403
    # reads that are not for everyone: the server log and the merge plan (admins), the change log and the elevation lookup (editors)
    assert client.get("/api/log").status_code == 403 and client.get("/api/log/download").status_code == 403
    assert client.get("/api/library/merge").status_code == 403
    assert client.get("/api/history").status_code == 403 and client.get("/api/elevation?lat=1&lon=1").status_code == 403
    assert "database" not in client.get("/api/settings").json() and "paths" not in client.get("/api/tools").json()
    _login(client, "ed", "editor-pass")
    s = client.get("/api/status").json()
    assert s["editing"] is True and s["isAdmin"] is False
    assert client.post("/api/settings", json={"bg_threads": 2}).status_code == 403
    assert client.get("/api/history").status_code == 200 and client.get("/api/log").status_code == 403
    assert client.post("/api/users", json={"name": "z", "password": "password1", "role": "viewer"}).status_code == 403
    _login(client, "alex", "correct horse")
    assert client.get("/api/status").json()["isAdmin"] is True
    assert client.get("/api/log").status_code == 200 and "paths" in client.get("/api/tools").json()
    assert client.post("/api/settings", json={"bg_threads": 2}).status_code == 200
    assert client.get("/api/users").status_code == 200 and len(client.get("/api/users").json()["users"]) == 3


def test_wrong_password_and_bad_cookie(client, fresh):
    users.create("alex", "correct horse", "admin")
    assert client.post("/api/auth/login", json={"name": "alex", "password": "nope"}).status_code == 401
    client.cookies.set(users.COOKIE, "1.9999999999.deadbeef")
    assert client.get("/api/auth/me").json()["user"] is None


def test_per_user_settings_roundtrip(client, fresh):
    users.create("vi", "viewer-pass", "viewer")
    _login(client, "vi", "viewer-pass")
    assert client.post("/api/auth/settings", json={"badges": "0", "tile": "L"}).json() == {"badges": "0", "tile": "L"}
    assert client.get("/api/auth/me").json()["settings"] == {"badges": "0", "tile": "L"}
    assert client.post("/api/auth/settings", json={"badges": None}).json() == {"tile": "L"}


def test_admin_manages_users_and_cannot_remove_the_last_admin(client, fresh):
    users.create("alex", "correct horse", "admin")
    _login(client, "alex", "correct horse")
    u = client.post("/api/users", json={"name": "ed", "password": "editor-pass", "role": "editor"}).json()
    assert client.post(f"/api/users/{u['id']}", json={"role": "admin"}).status_code == 200
    assert client.post(f"/api/users/{u['id']}", json={"password": "new-password-1"}).status_code == 200
    client.cookies.clear(); _login(client, "ed", "new-password-1")
    me = client.get("/api/auth/me").json()["user"]
    assert client.post(f"/api/users/{me['id']}", json={"delete": True}).status_code == 400, "not while signed in as that user"
    alex = next(x for x in client.get("/api/users").json()["users"] if x["name"] == "alex")
    assert client.post(f"/api/users/{alex['id']}", json={"role": "viewer"}).status_code == 200
    assert client.post(f"/api/users/{me['id']}", json={"role": "viewer"}).status_code == 400, "the only admin left"
    assert client.post("/api/users", json={"name": "ed", "password": "password1", "role": "viewer"}).status_code == 400, "name taken"
    assert client.post("/api/users", json={"name": "short", "password": "short", "role": "viewer"}).status_code == 400


def test_own_password_change(client, fresh):
    users.create("vi", "viewer-pass", "viewer")
    _login(client, "vi", "viewer-pass")
    assert client.post("/api/auth/password", json={"current": "wrong", "password": "another-pass"}).status_code == 403
    assert client.post("/api/auth/password", json={"current": "viewer-pass", "password": "another-pass"}).status_code == 200
    _login(client, "vi", "another-pass")


def test_passwordless_viewer_one_click_and_limits(client, fresh):
    users.create("alex", "correct horse", "admin")
    _login(client, "alex", "correct horse")
    assert client.post("/api/users", json={"name": "kid", "password": "", "role": "editor"}).status_code == 400, "no password means a member at most"
    kid = client.post("/api/users", json={"name": "kid", "password": "", "role": "viewer"}).json()
    assert kid["passwordless"] is True
    assert client.post(f"/api/users/{kid['id']}", json={"role": "editor"}).status_code == 400, "cannot be promoted without a password"
    alex = next(x for x in client.get("/api/users").json()["users"] if x["name"] == "alex")
    assert client.post(f"/api/users/{alex['id']}", json={"password": ""}).status_code == 400, "an admin keeps a password"
    client.cookies.clear()
    acc = client.get("/api/auth/accounts").json()["accounts"]
    assert [(a["name"], a["passwordless"]) for a in acc] == [("alex", False), ("kid", True)]
    r = client.post("/api/auth/login", json={"name": "kid"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "viewer"
    s = client.get("/api/status").json()
    assert s["user"]["name"] == "kid" and s["editing"] is False and s["signedIn"] is True
    assert client.post("/api/favorites", json={"ids": [], "on": True}).status_code == 403, "a viewer only looks"
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "alex"}).status_code == 401, "a protected account still needs its password"
    _login(client, "alex", "correct horse")
    assert client.post(f"/api/users/{kid['id']}", json={"password": "now-protected"}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "kid"}).status_code == 401


def test_account_linked_to_a_person(client, fresh):
    users.create("alex", "correct horse", "admin")
    _login(client, "alex", "correct horse")
    tags = client.get("/api/meta").json()["tags"]
    person = next(t for t in tags if t.get("person") and t["full"] != "People")
    plain = next(t for t in tags if not t.get("person"))
    me = client.get("/api/auth/me").json()["user"]
    assert client.post(f"/api/users/{me['id']}", json={"person": plain["id"]}).status_code == 400, "only a person tag"
    assert client.post("/api/auth/person", json={"person": person["id"]}).json()["person"] == person["id"]
    assert client.get("/api/status").json()["user"]["person"] == person["id"]
    assert client.get("/api/users").json()["users"][0]["person"] == person["id"]
    client.cookies.clear()
    assert client.get("/api/auth/accounts").json()["accounts"][0]["person"] == person["id"], "the picker can show the face"
    _login(client, "alex", "correct horse")
    assert client.post("/api/auth/person", json={"person": None}).json()["person"] is None
    # only an admin links accounts to people: an editor or viewer cannot link themselves
    users.create("ed", "editor-pass", "editor")
    _login(client, "ed", "editor-pass")
    assert client.post("/api/auth/person", json={"person": person["id"]}).status_code == 403
    _login(client, "alex", "correct horse")
    ed = next(u for u in client.get("/api/users").json()["users"] if u["name"] == "ed")
    assert client.post(f"/api/users/{ed['id']}", json={"person": person["id"]}).status_code == 200


def test_optional_email_on_accounts(client, fresh):
    """An account may carry an email address (for a proxy to identify users by later): set at
    creation or afterwards, validated, unique, clearable, and shown in the admin's list."""
    users.create("alex", "correct horse", "admin")
    _login(client, "alex", "correct horse")
    u = client.post("/api/users", json={"name": "ed", "password": "editor-pass", "role": "editor", "email": " Ed@Example.com "}).json()
    assert u["email"] == "ed@example.com", "trimmed and lower-cased"
    assert client.post("/api/users", json={"name": "ann", "password": "", "role": "viewer", "email": "not-an-address"}).status_code == 400
    assert client.post("/api/users", json={"name": "ann", "password": "", "role": "viewer", "email": "ed@example.com"}).status_code == 400, "unique"
    ann = client.post("/api/users", json={"name": "ann", "password": "", "role": "viewer"}).json()
    assert ann["email"] == ""
    assert client.post(f"/api/users/{ann['id']}", json={"email": "ann@example.com"}).status_code == 200
    assert client.post(f"/api/users/{ann['id']}", json={"email": "ed@example.com"}).status_code == 400
    listed = {x["name"]: x["email"] for x in client.get("/api/users").json()["users"]}
    assert listed == {"alex": "", "ed": "ed@example.com", "ann": "ann@example.com"}
    assert client.post(f"/api/users/{ann['id']}", json={"email": ""}).status_code == 200
    assert next(x for x in client.get("/api/users").json()["users"] if x["name"] == "ann")["email"] == ""
    assert "email" not in client.get("/api/auth/accounts").json()["accounts"][0], "the public picker shows no addresses"


def test_require_login_locks_everything_but_the_sign_in(client, fresh, lib):
    assert client.post("/api/settings", json={"require_login": True}).status_code == 400, "no account yet: nobody could sign in"
    users.create("alex", "correct horse", "admin")
    _login(client, "alex", "correct horse")
    assert client.post("/api/settings", json={"require_login": True}).status_code == 200
    assert client.get("/api/status").json()["requireLogin"] is True
    client.cookies.clear()
    # a visitor: the shell and the sign-in endpoints work, nothing else does
    for path in ("/", "/static/app.js", "/static/app.css", "/manifest.webmanifest", "/api/status", "/api/auth/me", "/api/auth/accounts"):
        assert client.get(path).status_code == 200, path
    assert client.get("/api/auth/me").json()["requireLogin"] is True
    pid = lib["ids"][0] if isinstance(lib, dict) and "ids" in lib else client.get("/api/photos", cookies={}).json().get("id", [None])[0]
    for path in ("/api/meta", "/api/photos", "/api/users", "/api/tags", "/api/concepts"):
        assert client.get(path).status_code == 401, path
    if pid:
        for path in (f"/thumb/{pid}", f"/preview/{pid}", f"/orig/{pid}", f"/api/photo/{pid}"):
            assert client.get(path).status_code == 401, path
    # the account picker's avatars: the face badge of a linked person is served, other faces are not
    _login(client, "alex", "correct horse")
    tags = client.get("/api/meta").json()["tags"]
    people = [t for t in tags if t.get("person") and t["full"] != "People"]
    if len(people) >= 2:
        assert client.post("/api/auth/person", json={"person": people[0]["id"]}).status_code == 200
        client.cookies.clear()
        assert client.get(f"/face/{people[0]['id']}").status_code != 401
        assert client.get(f"/face/{people[1]['id']}").status_code == 401
        assert client.get(f"/face/{people[0]['id']}", headers={"cf-ray": "1"}).status_code == 401, "from outside: no faces, as no tiles"
    client.cookies.clear()
    from app.data import state as _st
    _st.set_setting("mcp_enabled", "1")  # the endpoint itself is off by default
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"accept": "application/json, text/event-stream"})
    assert r.status_code == 401, "MCP needs an app password (or a session)"
    _login(client, "alex", "correct horse")
    pw = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    client.cookies.clear()
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                    headers={"accept": "application/json, text/event-stream", "authorization": "Bearer " + pw})
    assert r.status_code == 200
    _st.set_setting("mcp_enabled", "0")
    # signed in again: everything is back
    _login(client, "alex", "correct horse")
    assert client.get("/api/meta").status_code == 200
    assert client.post("/api/settings", json={"require_login": False}).status_code == 200
    client.cookies.clear()
    assert client.get("/api/meta").status_code == 200, "open browsing again"


def test_backup_downloads_are_for_admins(client, fresh, lib):
    users.create("alex", "correct horse", "admin")
    users.create("vi", "", "viewer")
    client.cookies.clear()
    assert client.post("/api/backup/app").status_code == 401, "once accounts exist, a visitor gets nothing"
    _login(client, "vi", "")
    assert client.post("/api/backup/app").status_code == 403
    _login(client, "alex", "correct horse")
    r = client.post("/api/backup/app")
    assert r.status_code == 200 and r.content.startswith(b"PK") and r.headers["content-disposition"].endswith('.zip"')
    import io, zipfile
    names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert "iopix.sql" in names and "README.txt" in names and "viewer.db" not in names, names
    r = client.post("/api/backup/digikam")
    assert r.status_code == 200 and r.content.startswith(b"SQLite format 3") and "digikam4-" in r.headers["content-disposition"]
    assert client.post("/api/backup/other").status_code == 404
    assert client.get("/api/backup/app").status_code == 405, "making a backup is a POST: no link starts one"
    assert client.post("/api/backup/app", headers={"Origin": "https://evil.example"}).status_code == 403


def test_an_account_can_be_left_off_the_sign_in_list(client, fresh):
    """Settings › Users › Sign-in list: an unticked account is not offered on the sign-in screen; "Other" with
    its name (and password) still signs it in."""
    users.create("alex", "correct horse", "admin")
    _login(client, "alex", "correct horse")
    kid = client.post("/api/users", json={"name": "kid", "password": "", "role": "viewer"}).json()
    alex = next(x for x in client.get("/api/users").json()["users"] if x["name"] == "alex")
    assert alex["listed"] is True and kid["listed"] is True
    assert client.post(f"/api/users/{alex['id']}", json={"listed": False}).status_code == 200
    assert next(x for x in client.get("/api/users").json()["users"] if x["name"] == "alex")["listed"] is False
    client.cookies.clear()
    assert [a["name"] for a in client.get("/api/auth/accounts").json()["accounts"]] == ["kid"], "the picker leaves the account out"
    _login(client, "alex", "correct horse")  # "Other": the name and password still sign in
    assert client.get("/api/status").json()["user"]["name"] == "alex"
    assert client.post(f"/api/users/{alex['id']}", json={"listed": True}).status_code == 200
    client.cookies.clear()
    assert [a["name"] for a in client.get("/api/auth/accounts").json()["accounts"]] == ["alex", "kid"]


def test_a_session_in_use_is_renewed(client, fresh):
    """A device that uses its session gets a fresh 30 days (at most once a day): the iPhone app stays signed in."""
    import time as _time
    from iosuite_shared import db as authdb, sessions
    users.create("alex", "correct horse", "admin")
    _login(client, "alex", "correct horse")
    assert "set-cookie" not in client.get("/api/auth/me").headers, "a session from today is not renewed"
    now = int(_time.time())
    authdb.ex("UPDATE ios_sessions SET renewed_at = %s, expires_at = %s", (now - 20 * 86400, now + 10 * 86400))  # renewed 20 days ago: 10 days left
    sessions.invalidate()
    r = client.get("/api/auth/me")
    assert r.json()["user"]["name"] == "alex"
    assert r.cookies.get(users.COOKIE) == client.cookies.get(users.COOKIE), r.headers.get("set-cookie")  # the cookie is set again, for another 30 days
    assert authdb.one("SELECT expires_at FROM ios_sessions")["expires_at"] > now + 29 * 86400

def test_registers_in_the_suite(client, fresh):
    """The first request lists iopix in the suite's apps (suite_apps), with its name and version, for the start page."""
    from iosuite_shared import suite
    from app import __version__
    assert suite.get("iopix") is None
    client.get("/api/status")
    app = suite.get("iopix")
    assert app["name"] == "ioPix" and app["version"] == __version__ and app["color"] == "#3b4a8c"


def test_the_sign_in_screens_faces_are_for_the_network_only(monkeypatch):
    """What a visitor gets while sign-in is required (main._open_to_visitors): the face of a person an account is
    linked to, and like the account tiles only on the network the server is on. Needs no library."""
    from starlette.requests import Request
    from app import main

    def visitor(path, peer, **headers):
        return Request({"type": "http", "method": "GET", "path": path, "query_string": b"", "scheme": "http", "server": ("pix.lan", 8610),
                        "client": (peer, 50000), "headers": [(k.replace("_", "-").encode(), v.encode()) for k, v in headers.items()]})
    monkeypatch.setattr(users, "linked_persons", lambda: {7})
    assert main._open_to_visitors(visitor("/face/7", "192.168.1.20"))
    assert not main._open_to_visitors(visitor("/face/8", "192.168.1.20")), "a face no account is linked to"
    assert not main._open_to_visitors(visitor("/thumb/7", "192.168.1.20"))
    assert not main._open_to_visitors(visitor("/face/7", "8.8.8.8")), "from the internet"
    assert not main._open_to_visitors(visitor("/face/7", "192.168.1.20", cf_ray="1")), "through Cloudflare"
    assert not main._open_to_visitors(visitor("/face/7", "192.168.1.5", x_forwarded_for="8.8.8.8")), "through a reverse proxy"


def test_only_the_upload_routes_take_a_large_body():
    """The body cap is by route, not by what the request calls itself: 2 GiB for the routes that take photos, a few
    MiB for the rest (a "multipart" body sent to the sign-in would otherwise be read whole). Needs no library."""
    from app import main
    big, small = main.MAX_UPLOAD_BYTES, main.MAX_JSON_BYTES
    for path in ("/api/import", "/api/import/stage", "/share", "/api/folders/12/upload"):
        assert main._limit_for(path, "multipart/form-data; boundary=x") == big, path
        assert main._limit_for(path, "application/json") == small, path
    assert small < main._limit_for("/api/gpx/preview", "multipart/form-data") < big
    for path in ("/api/auth/login", "/api/photos", "/api/zip", "/mcp", "/api/folders/12", "/api/import/abc/run"):
        assert main._limit_for(path, "multipart/form-data; boundary=x") == small, path


def test_an_answer_that_depends_on_the_viewer_is_kept_per_account():
    """The cached photo lists and counts are kept per account as soon as a filter depends on who asks (favourites, an
    album of the app), whatever way the filter's name is written in the address. Needs no library."""
    from starlette.requests import Request
    from app.routes import browse

    def asked(query):
        return Request({"type": "http", "method": "GET", "path": "/api/facets", "query_string": query.encode(), "headers": []})
    for q in ("fav=1", "tag=3&fav=1", "ualbum=7", "f%61v=1", "u%61lbum=7"):
        assert browse._by_viewer(asked(q)), q
    for q in ("", "tag=3", "q=favourites", "album=7"):
        assert not browse._by_viewer(asked(q)), q
