"""Settings › Server through iosuite_shared's server_router (/api/server): the installed commit is known and the server
log answers. Updating is the suite's (Settings › Global settings › Updates): the app has no update action of its own.
The updater itself is tested in iosuite-shared."""
from app.auth import updater


def test_status_and_no_update_of_its_own(client, monkeypatch):
    monkeypatch.setattr(updater, "local_commit", lambda: "abcdef1234567890")
    s = client.get("/api/server").json()
    assert s["installed"] == "abcdef1" and "canRun" in s and "docker" in s and "mcpEnabled" in s
    assert "check" not in s and "autoCheck" not in s
    assert "update" not in client.get("/api/status").json()
    for action in ("check", "update"):
        assert client.post("/api/server", json={"action": action}).status_code == 400


def test_server_log_endpoint_filters(client):
    import logging
    logging.getLogger("app.sync").warning("probe-warning for the log test")
    r = client.get("/api/log", params={"level": "warning", "contains": "probe-warning"})
    assert r.status_code == 200
    j = r.json()
    if j["lines"]:  # the file handler is installed by the app's start; present in the test client
        assert all("probe-warning" in l for l in j["lines"])
    assert client.get("/api/log", params={"requests": 0}).status_code == 200
