"""The REST API: status and sign-in, the tiles and where they point, the admin settings."""


def test_status_and_signin(client):
    s = client.get("/api/status").json()
    assert s["app"] == "ioSuite" and s["usersExist"] and s["user"]["name"] == "alex" and s["user"]["role"] == "admin"
    # the page itself is open; the API is not
    assert client.get("/").status_code == 200
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as anon:
        assert anon.get("/").status_code == 200
        assert anon.get("/api/status").json()["user"] is None
        assert anon.get("/api/apps").status_code == 401


def test_tiles_are_the_registered_apps(client):
    items = client.get("/api/apps", headers={"host": "home.lan:8630"}).json()["items"]
    assert [t["key"] for t in items] == ["iopix", "iohealth", "iocalendar", "iocontacts", "ionotes"]
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
