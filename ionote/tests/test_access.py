"""Who may do what: the same rules as iopix (open until an account exists, then roles; require sign-in; read-only;
cross-site writes refused; every API route declares its access)."""
from helpers import NID


def test_open_until_the_first_account_exists(client):
    assert client.put(f"/api/notes/{NID}", json={"title": "x"}).status_code == 200


def test_writes_need_an_editor_once_accounts_exist(client, admin):
    client.post("/api/users", json={"name": "vic", "password": "viewerpw1", "role": "viewer"})
    client.post("/api/auth/logout")
    assert client.get("/api/notes").status_code == 200  # reading stays open, as in iopix
    assert client.put(f"/api/notes/{NID}", json={"title": "x"}).status_code == 401
    assert client.post("/api/auth/login", json={"name": "vic", "password": "viewerpw1"}).status_code == 200
    assert client.put(f"/api/notes/{NID}", json={"title": "x"}).status_code == 403
    assert client.get("/api/users").status_code == 403


def test_require_sign_in_closes_everything_but_the_shell(client, admin):
    assert client.post("/api/settings", json={"require_login": True}).status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/notes").status_code == 401
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/auth/accounts").json()["accounts"][0]["name"] == "alex"
    assert client.get("/").status_code == 200


def test_read_only_refuses_changes_for_everyone(client, admin):
    client.post("/api/settings", json={"read_only": True})
    assert client.put(f"/api/notes/{NID}", json={"title": "x"}).status_code == 403


def test_cross_site_writes_are_refused(client, admin):
    r = client.put(f"/api/notes/{NID}", json={"title": "x"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403


def test_wrong_passwords_cost_a_growing_wait(client, admin):
    client.post("/api/auth/logout")
    codes = [client.post("/api/auth/login", json={"name": "alex", "password": "nope"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and 429 in codes


def test_every_api_route_declares_who_may_call_it(app):
    from app import access
    from fastapi.routing import APIRoute
    missing = [r.path for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/") and not access.declared(r)
               and r.path not in ("/api/openapi.json", "/api/docs")]
    assert not missing, missing


def test_the_account_tables_match_iopix(client):
    """ionotes keeps users and settings exactly as iopix does, so the two can share them later."""
    from app import db
    with db.connect() as con:
        cols = [d for d in con.execute("SELECT * FROM user_accounts LIMIT 0").cur.description]
    assert [c[0] for c in cols] == ["id", "name", "hash", "role", "settings", "created", "last_login", "person", "email", "session_gen", "listed"]


def test_cloudflare_access_needs_the_team_and_aud_before_any_header_is_believed(client, admin):
    client.post("/api/settings/proxy", json={"AUTH_PROXY": "cloudflare"})
    client.post("/api/auth/logout")
    r = client.get("/api/auth/me", headers={"Cf-Access-Authenticated-User-Email": "alex@example.com"})
    assert r.json()["user"] is None


def test_a_header_proxy_signs_in_only_from_a_trusted_address(client, admin):
    client.post("/api/users/1", json={"email": "alex@example.com"})
    client.post("/api/settings/proxy", json={"AUTH_PROXY": "header", "AUTH_PROXY_TRUSTED": "10.9.9.9"})
    client.post("/api/auth/logout")
    r = client.get("/api/auth/me", headers={"Remote-User": "alex@example.com"})
    assert r.json()["user"] is None  # the test client is not 10.9.9.9


def test_status_tells_admins_of_a_newer_version_while_the_daily_check_is_on(client, admin, monkeypatch):
    from app import config, updates
    monkeypatch.setattr(config, "UPDATE_CHECK", True)  # the tests never start the daily check itself
    updates._checked.clear()
    updates._checked.update(status="update", remote="abc1234", remoteVersion="9.9.9", remoteMessage="v9.9.9: new", remoteDate="2026-11-03")
    try:
        s = client.get("/api/status").json()
        assert s["update"]["version"] == "9.9.9" and "canRun" in s["update"] and s["commit"]
        client.post("/api/settings", json={"update_check": False})
        assert client.get("/api/status").json()["update"] is None
        client.post("/api/settings", json={"update_check": True})
        client.post("/api/auth/logout")
        assert "update" not in client.get("/api/status").json()
    finally:
        updates._checked.clear()
