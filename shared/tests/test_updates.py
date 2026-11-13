"""The shared updater and server router, without a database: GitHub is a stub, update.sh a tiny script that writes
its result file. (The suite's daily-check switch and the rows the apps write are in test_suiteupdates.py.)"""
import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import updates
from iosuite_shared.fastapi import Auth


@pytest.fixture
def fresh_db():
    """Overrides conftest's autouse database fixture: nothing here needs MariaDB."""
    yield


def make_updater(tmp_path, monkeypatch, version="1.2.0", **kw):
    monkeypatch.delenv("UPDATE_CHECK", raising=False)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    u = updates.Updater("iotest", version, tmp_path, repo="someone/iotest", branch="main", **kw)
    u.in_docker = lambda: False
    return u


def github(sha="abcdef0123456789", remote_version="1.3.0", msg="v1.3.0: better", fail=False):
    """GitHub as the Updater asks it: the branch's commit and the suite's version file at that commit
    (shared/iosuite_shared/__init__.py)."""
    def _get(url, accept=""):
        if fail:
            raise OSError("no network")
        if "api.github.com" in url:
            return json.dumps({"sha": sha, "commit": {"committer": {"date": "2026-11-05T01:02:03Z"}, "message": msg + "\n\nmore"}}).encode()
        assert url.endswith("/fedcba9876543210/" + updates.VERSION_FILE), url
        if remote_version is None:
            return b"nothing here"
        return f'__version__ = "{remote_version}"\n'.encode()
    return _get


def test_commit_from_file_and_check_outcomes(tmp_path, monkeypatch):
    u = make_updater(tmp_path, monkeypatch)
    assert u.local_commit() == "unknown" and u.status()["installed"] == "unknown"
    (tmp_path / "COMMIT").write_text("abcdef0123456789\n")
    assert u.local_commit() == "unknown"  # cached, "unknown" too: no git subprocess per status call
    u._commit = None  # as after the restart update.sh does
    assert u.local_commit() == "abcdef0123456789"

    u._get_url = github()
    assert u.check()["status"] == "current"  # the same commit

    u._get_url = github(sha="fedcba9876543210")
    c = u.check()
    assert c["status"] == "update" and c["remoteVersion"] == "1.3.0" and c["remote"] == "fedcba9" and c["remoteDate"] == "2026-11-05"
    assert c["remoteMessage"] == "v1.3.0: better"

    u._get_url = github(sha="fedcba9876543210", remote_version="1.2.0")  # another commit, the same version: nothing to install
    assert u.check()["status"] == "current"
    u._get_url = github(sha="fedcba9876543210", remote_version="1.1.9")  # this install is ahead of the branch
    assert u.check()["status"] == "current"
    u._get_url = github(sha="fedcba9876543210", remote_version=None)  # no version line found: say so, to be safe
    assert u.check()["status"] == "update" and u.check()["remoteVersion"] is None
    u._get_url = github(fail=True)
    c = u.check()
    assert c["status"] == "error" and "no network" in c["error"]


def test_version_line_shapes():
    assert updates.VERSION_RE.search('APP_VERSION = "2.0.1"\n') is None  # one spelling in every app
    assert updates.VERSION_RE.search('"""doc"""\n__version__ = "0.4.2"\n').group(1) == "0.4.2"
    assert updates._version_tuple("1.10.2") > updates._version_tuple("1.9.9")


def test_the_daily_check_and_its_lock(tmp_path, monkeypatch):
    u = make_updater(tmp_path, monkeypatch)
    monkeypatch.setattr(updates, "auto_check_enabled", lambda: True)  # the suite's switch (in the database)
    assert u.auto_check_enabled()
    monkeypatch.setattr(updates, "auto_check_enabled", lambda: False)
    assert not u.auto_check_enabled()
    monkeypatch.setattr(updates, "auto_check_enabled", lambda: True)
    monkeypatch.setenv("UPDATE_CHECK", "0")  # this app never asks GitHub by itself, whatever the switch says
    locked = updates.Updater("iotest", "1", tmp_path)
    assert locked.check_locked and not locked.auto_check_enabled()


def test_env_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("IOCALENDAR_REPO", "me/cal")
    monkeypatch.setenv("IOCALENDAR_BRANCH", "dev")
    u = updates.Updater("iocalendar", "1", tmp_path)
    assert u.repo == "me/cal" and u.branch == "dev" and u.prefix == "IOCALENDAR"
    monkeypatch.delenv("IOCALENDAR_REPO")
    monkeypatch.delenv("IOCALENDAR_BRANCH")
    u = updates.Updater("iocalendar", "1", tmp_path)
    assert u.repo == "avandeputte/iosuite" and u.branch == "main"


def test_run_update_script_and_result(tmp_path, monkeypatch):
    u = make_updater(tmp_path, monkeypatch)
    assert not u.can_run()
    with pytest.raises(RuntimeError, match="cannot update itself"):
        u.run()
    (tmp_path / ".venv").mkdir()
    (tmp_path / "update.sh").write_text('#!/bin/sh\necho "repo=$IOTEST_REPO ref=$IOTEST_REF"\nprintf "ok: updated to v9 now\\n" > "$IOTEST_RESULT"\n')
    assert u.can_run() and u.status()["canRun"]
    monkeypatch.setenv("IOTEST_REF", "0123abc")  # a ref in the service's environment is never passed on: the tip of the branch
    with pytest.raises(TypeError):
        u.run("0123abc")  # and a request cannot name one (a fork's commit is served under the repository's address)
    u.run()
    for _ in range(100):
        if not u.progress["running"]:
            break
        time.sleep(0.05)
    assert not u.progress["running"] and u.progress["error"] is None
    assert "repo=someone/iotest ref=\n" in u.progress["log"]
    assert u.last_result()["ok"] and u.last_result()["text"] == "updated to v9 now"

    (tmp_path / "update.sh").write_text('#!/bin/sh\necho "\\033[1;31merror:\\033[0m packages failed" >&2\nexit 3\n')
    u.run()
    for _ in range(100):
        if not u.progress["running"]:
            break
        time.sleep(0.05)
    assert u.progress["error"] == "error: packages failed"
    assert u.last_result() is None  # the old result file was removed before the run

    u.in_docker = lambda: True
    with pytest.raises(RuntimeError, match="pulling the image"):
        u.run()
    assert u.status()["docker"] and not u.can_run()


def test_log_tail(tmp_path):
    missing = updates.tail(tmp_path / "none.log")
    assert missing["lines"] == [] and "no log file" in missing["note"]
    log = tmp_path / "app.log"
    log.write_text("\n".join([
        "2026-11-05 10:00:00 INFO uvicorn.access: GET / 200",
        "2026-11-05 10:00:01 INFO iosuite_shared.auth: signed in: alex",
        "2026-11-05 10:00:02 WARNING app: slow",
        "2026-11-05 10:00:03 ERROR app: boom",
        "Traceback (most recent call last):",
        "2026-11-05 10:00:04 INFO app: fine",
    ]) + "\n")
    assert updates.tail(log)["returned"] == 6
    assert updates.tail(log, requests=False)["returned"] == 5 and all(" uvicorn.access: " not in l for l in updates.tail(log, requests=False)["lines"])
    errs = updates.tail(log, level="error")["lines"]
    assert len(errs) == 2 and errs[0].endswith("boom") and errs[1].startswith("Traceback")
    assert updates.tail(log, level="warning")["returned"] == 3
    assert updates.tail(log, level="auth")["lines"] == ["2026-11-05 10:00:01 INFO iosuite_shared.auth: signed in: alex"]
    assert updates.tail(log, contains="FINE")["returned"] == 1
    assert updates.tail(log, lines=2)["lines"] == ["Traceback (most recent call last):", "2026-11-05 10:00:04 INFO app: fine"]


def admin_app(auth: Auth, monkeypatch):
    """The router under an admin, without the database: the middleware is replaced by one that signs an admin in."""
    app = FastAPI()
    admin = {"id": 1, "name": "alex", "role": "admin", "suiteAdmin": True, "passwordless": False}

    @app.middleware("http")
    async def as_admin(request, call_next):
        request.state.user = admin
        return await call_next(request)
    monkeypatch.setattr("iosuite_shared.users.is_admin", lambda u: bool(u and u.get("role") == "admin"))
    return app


def test_server_router(tmp_path, monkeypatch):
    u = make_updater(tmp_path, monkeypatch)
    (tmp_path / "COMMIT").write_text("abcdef0123456789\n")
    log = tmp_path / "app.log"
    log.write_text("2026-11-05 10:00:03 ERROR app: boom\n2026-11-05 10:00:04 INFO app: fine\n")
    restarted = []
    monkeypatch.setattr(updates.Updater, "restart", staticmethod(lambda delay=0.5: restarted.append(delay)))
    saved = {}

    def apply(body):
        if "mcpEnabled" in body:
            if body["mcpEnabled"] == "locked":
                raise ValueError("MCP=1 keeps it on")
            saved["mcp"] = body["mcpEnabled"]

    auth = Auth("iotest", register=False)
    app = admin_app(auth, monkeypatch)
    app.include_router(auth.server_router(u, log_file=log, info=lambda: {"mcpEnabled": saved.get("mcp", False), "database": "db:3306/x"}, apply=apply))
    c = TestClient(app)

    ui = c.get("/api/server/ui.js")
    assert ui.status_code == 200 and "javascript" in ui.headers["content-type"] and "export async function mount" in ui.text

    s = c.get("/api/server").json()
    assert s["name"] == auth.label
    assert s["version"] == "1.2.0" and s["installed"] == "abcdef0" and s["repo"] == "someone/iotest"
    assert s["database"] == "db:3306/x" and s["mcpEnabled"] is False and not s["canRun"] and "autoCheck" not in s

    assert c.post("/api/server", json={"mcpEnabled": True}).json()["mcpEnabled"] is True and saved["mcp"] is True
    assert c.post("/api/server", json={"mcpEnabled": "locked"}).status_code == 400
    assert c.post("/api/server", json={"action": "nonsense"}).status_code == 400
    assert c.post("/api/server").status_code == 200  # an empty body: the info
    # updating is the suite's (/api/suite-admin/updates): one app is not updated on its own from here
    assert c.post("/api/server", json={"action": "update"}).status_code == 400
    assert c.post("/api/server", json={"action": "check"}).status_code == 400

    assert c.post("/api/server", json={"action": "restart"}).json() == {"ok": True} and restarted == [0.5]

    lg = c.get("/api/log?level=error").json()
    assert lg["returned"] == 1 and lg["lines"][0].endswith("boom")
    assert c.get("/api/log?level=bogus").json()["returned"] == 2
    d = c.get("/api/log/download")
    assert d.status_code == 200 and "boom" in d.text and "attachment" in d.headers["content-disposition"]
    os.remove(log)
    assert c.get("/api/log/download").status_code == 404
    assert c.get("/api/log").json()["lines"] == []


def test_server_router_is_for_admins_only(tmp_path, monkeypatch):
    u = make_updater(tmp_path, monkeypatch)
    auth = Auth("iotest", register=False)
    app = FastAPI()

    @app.middleware("http")
    async def nobody(request, call_next):
        request.state.user = {"id": 2, "name": "bob", "role": "viewer"}
        return await call_next(request)
    monkeypatch.setattr("iosuite_shared.users.is_admin", lambda user: False)
    app.include_router(auth.server_router(u, log_file=tmp_path / "x.log"))
    c = TestClient(app)
    assert c.get("/api/server").status_code == 403
    assert c.get("/api/server/ui.js").status_code == 403
    assert c.post("/api/server", json={"action": "restart"}).status_code == 403
    assert c.get("/api/log").status_code == 403
