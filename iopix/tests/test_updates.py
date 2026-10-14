"""Self-update: the installed commit is known, GitHub's main branch is compared with it
(network stubbed), the run is refused in Docker, and only admins may trigger it."""
from app import updates


def test_status_and_check(client, monkeypatch):
    monkeypatch.setattr(updates, "local_commit", lambda: "abcdef1234567890")
    s = client.get("/api/update").json()
    assert s["installed"] == "abcdef1" and "canRun" in s and "docker" in s
    monkeypatch.setattr(updates, "_fetch", lambda url: {"sha": "abcdef1234567890", "commit": {"committer": {"date": "2026-10-14T20:00:00Z"}, "message": "same\n\nbody"}})
    c = client.post("/api/update", json={"action": "check"}).json()
    assert c["status"] == "current" and c["remoteMessage"] == "same"
    monkeypatch.setattr(updates, "_fetch", lambda url: {"sha": "ffffff1234567890", "commit": {"committer": {"date": "2026-10-15T00:00:00Z"}, "message": "newer"}})
    c = client.post("/api/update", json={"action": "check"}).json()
    assert c["status"] == "update" and c["remote"] == "ffffff1" and c["remoteDate"] == "2026-10-15"
    assert client.get("/api/update").json()["check"]["status"] == "update"
    def boom(url):
        raise OSError("offline")
    monkeypatch.setattr(updates, "_fetch", boom)
    assert client.post("/api/update", json={"action": "check"}).json()["status"] == "error"


def test_run_refused_in_docker_and_bad_action(client, monkeypatch):
    monkeypatch.setattr(updates, "in_docker", lambda: True)
    r = client.post("/api/update", json={"action": "run"})
    assert r.status_code == 409 and "pull" in r.json()["detail"]
    assert client.post("/api/update", json={"action": "nope"}).status_code == 400


def test_run_starts_update_script(client, monkeypatch, tmp_path):
    monkeypatch.setattr(updates, "in_docker", lambda: False)
    (tmp_path / "update.sh").write_text("#!/bin/sh\necho updated\n")
    monkeypatch.setattr(updates.config, "APP_DIR", tmp_path)
    assert client.post("/api/update", json={"action": "run"}).status_code == 200
    import time
    for _ in range(50):
        if not updates.progress["running"]:
            break
        time.sleep(0.1)
    assert updates.progress["error"] is None and "updated" in updates.progress["log"]
