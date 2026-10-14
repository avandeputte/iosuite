"""Users and permissions: open until the first user exists; then anonymous is read-only,
viewers keep settings and favorites on the server, editors write the library, admins
manage settings, maintenance and users; sessions are signed cookies."""
import pytest

from app import state, users


@pytest.fixture
def fresh(client):
    con = state.connect(); con.execute("DELETE FROM users"); con.commit(); con.close()
    client.cookies.clear()
    yield
    con = state.connect(); con.execute("DELETE FROM users"); con.commit(); con.close()
    client.cookies.clear()


def _login(client, name, pw):
    client.cookies.clear()
    r = client.post("/api/auth/login", json={"name": name, "password": pw})
    assert r.status_code == 200, r.text
    return r.json()


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
    _login(client, "ed", "editor-pass")
    s = client.get("/api/status").json()
    assert s["editing"] is True and s["isAdmin"] is False
    assert client.post("/api/settings", json={"bg_threads": 2}).status_code == 403
    assert client.post("/api/users", json={"name": "z", "password": "password1", "role": "viewer"}).status_code == 403
    _login(client, "alex", "correct horse")
    assert client.get("/api/status").json()["isAdmin"] is True
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
