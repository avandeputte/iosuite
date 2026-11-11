"""The REST API: status and sign-in, the tiles and where they point, the admin settings."""


def test_status_and_signin(client):
    s = client.get("/api/status").json()
    assert s["app"] == "iosuite" and s["name"] == "ioSuite" and s["usersExist"] and s["user"]["name"] == "alex" and s["user"]["role"] == "admin"
    # the page itself is open; the API is not
    assert client.get("/").status_code == 200
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)  # no `with`: the app is started once per process (the MCP session manager)
    assert anon.get("/").status_code == 200
    assert anon.get("/api/status").json()["user"] is None
    assert anon.get("/api/apps").status_code == 401


def test_tiles_are_the_registered_apps(client):
    items = client.get("/api/apps", headers={"host": "home.lan:8630"}).json()["items"]
    assert [t["key"] for t in items] == ["iopix", "iohealth", "iocalendar", "iotasks", "iocontacts", "ionotes"]
    by = {t["key"]: t for t in items}
    assert by["iopix"]["url"] == "https://pix.example.com" and by["iocontacts"]["name"] == "ioContacts"
    assert "hidden" not in by["iopix"] and "port" not in by["iopix"]


def test_home_settings_photo_strip(client):
    assert client.get("/api/apps").json()["photoStrip"] == "rediscover"
    assert client.get("/api/home/settings").json() == {"photoStrip": "rediscover"}
    assert client.post("/api/home/settings", json={"photoStrip": "off"}).json()["photoStrip"] == "off"
    assert client.get("/api/apps").json()["photoStrip"] == "off"
    assert client.post("/api/home/settings", json={"photoStrip": "sideways"}).status_code == 400
    assert client.post("/api/home/settings", json={"photoStrip": "rediscover"}).json()["photoStrip"] == "rediscover"
    assert client.get("/api/apps/settings").status_code in (404, 405)  # Settings › Apps is gone


def test_viewer_cannot_change_settings(client):
    r = client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    assert r.status_code in (200, 201), r.text
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"name": "kid", "password": "secret123"}).status_code == 200
    assert client.get("/api/apps").status_code == 200
    assert client.get("/api/home/settings").status_code == 403
    assert client.post("/api/home/settings", json={"photoStrip": "off"}).status_code == 403
    assert client.get("/api/server").status_code == 403


def test_server_info(client):
    s = client.get("/api/server").json()
    assert s["version"] and "canRun" in s and s["autoCheck"] is False and s["autoCheckLocked"] is True
    assert "about" not in s and "progress" in s and s["repo"] and s["branch"]
    assert client.get("/api/log").status_code in (200, 404)  # the server log, when there is one


def test_the_server_log_is_for_admins_only(client):
    client.post("/api/users", json={"name": "kid2", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"name": "kid2", "password": "secret123"}).status_code == 200
    assert client.get("/api/log").status_code in (403, 404)  # 404: the tests run without a log file, so the route is not there
    assert client.post("/api/server", json={"action": "check"}).status_code == 403


def test_the_shell_its_files_and_the_icon_are_public(client):
    """The suite's layout: the page at /, every file it names under /static/, the mark at suite.ICON."""
    import re
    from iosuite_shared import suite
    html = client.get("/").text
    paths = re.findall(r'(?:src|href)="(static/[^"?]+)', html)
    paths += [i["src"] for i in client.get("/manifest.webmanifest").json()["icons"]]
    assert paths and all(p.startswith("static/") for p in paths)
    for p in ["/" + p for p in paths] + [suite.ICON, "/static/icons/apple-touch-icon.png"]:
        assert client.get(p).status_code == 200, p


def test_suite_admin_screen(client):
    """Settings › Security: every account, its role in every app, app passwords with their scope, the apps' access."""
    o = client.get("/api/suite-admin").json()
    assert {a["app"] for a in o["apps"]} >= {"iopix", "iocalendar", "iocontacts"} and [u["name"] for u in o["users"]] == ["alex"]
    r = client.post("/api/suite-admin/users", json={"name": "ann", "password": "secret123", "roles": {"iopix": "editor", "iosuite": "admin"}})
    assert r.status_code == 200, r.text
    ann = r.json()["id"]
    pw = client.post("/api/suite-admin/app-passwords", json={"userId": ann, "app": "iocontacts", "label": "Phone", "scope": "dav"}).json()
    assert pw["scope"] == "dav"
    items = client.get("/api/suite-admin/app-passwords").json()["items"]
    assert [(i["userName"], i["scope"]) for i in items] == [("ann", "dav")]
    assert client.patch("/api/suite-admin/apps/iocalendar", json={"defaultRole": "none"}).json()["defaultRole"] == "none"
    # ann administers ioSuite, but not the suite: Settings › Security is not hers
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"name": "ann", "password": "secret123"}).status_code == 200
    assert client.get("/api/users").status_code == 200
    assert client.get("/api/suite-admin").status_code == 403
    assert client.post("/api/suite-admin/users", json={"name": "x", "password": "secret123"}).status_code == 403


def test_tiles_are_the_apps_each_person_may_use(client):
    from iosuite_shared import db as shared_db, suite
    from app import apps
    suite.register("iodns", "ioDNS", url="https://dns.example.com", admin_tool=True)
    shared_db.set_setting("default_role", "none", "iohealth")   # ioHealth: only the accounts given a role there
    apps.forget_registry()
    assert client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"}).status_code in (200, 201)
    by = {t["key"]: t for t in client.get("/api/apps").json()["items"]}
    assert "iohealth" in by and by["iodns"]["adminTool"] is True and by["iopix"]["adminTool"] is False  # alex: a suite admin
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    shared_db.settings_cache.clear()
    keys = [t["key"] for t in client.get("/api/apps").json()["items"]]
    assert keys == ["iopix", "iocalendar", "iotasks", "iocontacts", "ionotes"]   # neither ioHealth nor the admin tool
