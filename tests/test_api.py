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


def test_tiles_default_to_this_host(client):
    items = client.get("/api/apps", headers={"host": "home.lan:8630"}).json()["items"]
    assert [t["key"] for t in items] == ["iopix", "iohealth", "iocalendar", "iocontacts", "ionotes"]
    by = {t["key"]: t for t in items}
    assert by["iopix"]["url"] == "http://home.lan:8600" and by["iohealth"]["url"] == "http://home.lan:47800"
    assert by["iocalendar"]["url"] == "http://home.lan:8620" and by["iocontacts"]["name"] == "ioContacts"
    # behind a proxy the forwarded host counts
    items = client.get("/api/apps", headers={"host": "127.0.0.1:8630", "x-forwarded-host": "home.example.com"}).json()["items"]
    assert items[0]["url"] == "http://home.example.com:8600"


def test_admin_sets_addresses_and_hides(client):
    r = client.post("/api/apps/settings", json={"iopix": {"url": "https://photos.example.com/"}, "ionotes": {"hidden": True}})
    assert r.status_code == 200, r.text
    by = {t["key"]: t for t in r.json()["items"]}
    assert by["iopix"]["url"] == "https://photos.example.com" and by["ionotes"]["hidden"] and by["iopix"]["envUrl"] is None
    items = client.get("/api/apps").json()["items"]
    assert [t["key"] for t in items] == ["iopix", "iohealth", "iocalendar", "iocontacts"]
    assert items[0]["url"] == "https://photos.example.com"
    # back to the default, and shown again
    r = client.post("/api/apps/settings", json={"iopix": {"url": ""}, "ionotes": {"hidden": False}})
    assert r.json()["items"][0]["url"] == "" and len(client.get("/api/apps").json()["items"]) == 5
    # a bad address and an unknown app are refused
    assert client.post("/api/apps/settings", json={"iopix": {"url": "photos.example.com"}}).status_code == 400
    assert client.post("/api/apps/settings", json={"iomail": {"url": "https://x"}}).status_code == 400
    # the photo strip under the tiles: rediscover unless set otherwise
    assert client.get("/api/apps").json()["photoStrip"] == "rediscover"
    assert client.post("/api/apps/settings", json={"photoStrip": "off"}).json()["photoStrip"] == "off"
    assert client.get("/api/apps").json()["photoStrip"] == "off"
    assert client.post("/api/apps/settings", json={"photoStrip": "sideways"}).status_code == 400
    assert client.post("/api/apps/settings", json={"photoStrip": "rediscover"}).json()["photoStrip"] == "rediscover"


def test_viewer_cannot_change_settings(client):
    r = client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    assert r.status_code in (200, 201), r.text
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"name": "kid", "password": "secret123"}).status_code == 200
    assert client.get("/api/apps").status_code == 200
    assert client.get("/api/apps/settings").status_code == 403
    assert client.post("/api/apps/settings", json={"iopix": {"hidden": True}}).status_code == 403
    assert client.get("/api/server").status_code == 403


def test_server_info(client):
    s = client.get("/api/server").json()
    assert s["version"] and "canRun" in s and s["autoCheck"] is False and s["autoCheckLocked"] is True
