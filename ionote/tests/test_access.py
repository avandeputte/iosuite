"""Who may do what: the same rules as iopix (open until an account exists, then roles; require sign-in; read-only;
cross-site writes refused; every API route declares its access)."""
import json

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
    from iosuite_shared import testing
    testing.check_access_declared(app, access.declared)  # through the included routers (FastAPI 0.162 hides them in app.routes)


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
    from app.auth import updater
    monkeypatch.setattr(updater, "check_locked", False)  # UPDATE_CHECK=0 in the tests' environment: never start the daily check itself
    updater._checked.clear()
    updater._checked.update(status="update", remote="abc1234", remoteVersion="9.9.9", remoteMessage="v9.9.9: new", remoteDate="2026-11-03")
    try:
        s = client.get("/api/status").json()
        assert s["update"]["version"] == "9.9.9" and "canRun" in s["update"] and s["commit"]
        client.post("/api/server", json={"autoCheck": False})
        assert client.get("/api/status").json()["update"] is None
        client.post("/api/server", json={"autoCheck": True})
        client.post("/api/auth/logout")
        assert "update" not in client.get("/api/status").json()
    finally:
        updater._checked.clear()


def test_ionotes_registers_in_the_suites_list_of_apps(client):
    from iosuite_shared import suite
    from app import __version__
    client.get("/api/notes")
    row = suite.get("ionotes")
    assert row["name"] == "ioNotes" and row["version"] == __version__
    assert row["description"] == "Notes" and row["color"] == "#1c5a5e" and row["icon"] == "/static/icons/mark.svg"


def test_the_suite_icon_is_served_to_visitors_even_with_sign_in_required(client, admin):
    assert client.post("/api/settings", json={"require_login": True}).status_code == 200
    client.post("/api/auth/logout")
    r = client.get("/static/icons/mark.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")


def test_the_shell_its_files_and_the_icon_are_public(client, admin):
    """The suite's layout: the page at /, every file it names under /static/, the mark at suite.ICON."""
    import re
    from iosuite_shared import suite
    assert client.post("/api/settings", json={"require_login": True}).status_code == 200
    client.post("/api/auth/logout")
    html = client.get("/").text
    paths = re.findall(r'(?:src|href)="(static/[^"?]+)', html)
    paths += [i["src"] for i in json.loads(client.get("/manifest.webmanifest").content)["icons"]]
    assert paths and all(p.startswith("static/") for p in paths)
    for p in ["/" + p for p in paths] + [suite.ICON, "/static/icons/apple-touch-icon.png", "/sw.js"]:
        assert client.get(p).status_code == 200, p


def test_suite_apps_for_the_app_switcher(client):
    """The app mark becomes a menu of the suite's other apps (as ioContacts'): the page has the phone's button, may show
    their icons (other origins), and /api/auth/suite lists them with an address and an absolute icon."""
    from iosuite_shared import suite
    html = client.get("/").text
    assert 'id="suitebtn"' in html and "img-src 'self' data: blob: https:" in html
    assert client.get("/static/js/suite.js").status_code == 200
    client.get("/api/notes")
    suite.register("iopix", name="ioPix", url="https://photo.example.net", color="#123456")
    r = client.get("/api/auth/suite").json()
    assert r["app"] == "ionotes"
    other = [a for a in r["items"] if a["app"] != r["app"]]
    assert [(a["name"], a["url"], a["icon"]) for a in other] == [("ioPix", "https://photo.example.net", "https://photo.example.net/static/icons/mark.svg")]
