"""Settings › Name: the viewer brands itself as the admin wishes (status, manifest), iopix by default."""


def test_app_name_setting_brands_status_and_manifest(client):
    assert client.get("/api/status").json()["appName"] == "iopix"
    assert client.post("/api/settings", json={"app_name": "  iothing Photos "}).status_code == 200
    try:
        assert client.get("/api/status").json()["appName"] == "iothing Photos"
        assert client.get("/api/settings").json()["app_name"] == "iothing Photos"
        m = client.get("/manifest.webmanifest").json()
        assert m["name"] == "iothing Photos" and m["short_name"] == "Photos", "a long name keeps the short home-screen label"
        client.post("/api/settings", json={"app_name": "Pix"})
        assert client.get("/manifest.webmanifest").json()["short_name"] == "Pix"
    finally:
        client.post("/api/settings", json={"app_name": ""})
    assert client.get("/api/status").json()["appName"] == "iopix"
