"""Updating every app from one place: the request in ios_updates, each app's Updater picking it up and saying how it
went, the suite admin routes and the MCP tools."""
import asyncio
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import db, mcp as shared_mcp, suite, suiteupdates, updates, users
from iosuite_shared.fastapi import Auth


def updater(tmp_path, monkeypatch, app="iocalendar", version="1.0.0", remote="1.1.0", script=None):
    monkeypatch.delenv("UPDATE_CHECK", raising=False)
    monkeypatch.delenv("INVOCATION_ID", raising=False)
    root = tmp_path / app
    root.mkdir()
    store = {}
    u = updates.Updater(app, version, root, repo=f"someone/{app}", settings=(store.get, store.__setitem__))
    u.in_docker = lambda: False

    def get(url, accept=""):
        if "api.github.com" in url:
            return json.dumps({"sha": "abcdef0123456789", "commit": {"committer": {"date": "2026-11-11T01:02:03Z"}, "message": "new"}}).encode()
        return f'__version__ = "{remote}"\n'.encode()
    u._get_url = get
    if script is not None:
        (root / "update.sh").write_text(script)
        (root / ".venv").mkdir()
    return u


def test_request_claim_and_overview(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar", version="1.0.0")
    suite.register("ionotes", name="ioNotes", version="2.0.0")
    cal = updater(tmp_path, monkeypatch)
    cal._said_hello()
    by = {a["app"]: a for a in suiteupdates.overview()}
    assert by["iocalendar"]["watching"] and by["iocalendar"]["version"] == "1.0.0" and not by["iocalendar"]["canUpdate"]
    assert not by["ionotes"]["watching"] and by["ionotes"]["version"] == "2.0.0"  # never wrote its row

    assert suiteupdates.request("check", None, by="alex") == ["iocalendar", "ionotes"]
    assert suiteupdates.claim("iocalendar") == "check" and suiteupdates.claim("iocalendar") is None  # taken once
    cal.serve("check")
    a = {a["app"]: a for a in suiteupdates.overview()}["iocalendar"]
    assert a["latest"] == "1.1.0" and a["status"] == "update" and a["checked"] and a["commit"]
    assert {a["app"]: a for a in suiteupdates.overview()}["ionotes"]["pending"] == "check"

    assert suiteupdates.request("update", None) == ["iocalendar"]  # only the apps with an update waiting
    assert suiteupdates.request("update", ["ionotes", "IONOTES"]) == ["ionotes"]
    with pytest.raises(ValueError):
        suiteupdates.request("update", ["nope"])
    with pytest.raises(ValueError):
        suiteupdates.request("reboot", None)


def test_an_update_that_cannot_run_says_why(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar")
    cal = updater(tmp_path, monkeypatch)
    suiteupdates.request("update", ["iocalendar"], by="alex")
    cal.serve(suiteupdates.claim("iocalendar"))
    a = suiteupdates.overview()[0]
    assert a["state"] == "failed" and "cannot update itself" in a["message"] and not a["pending"]


def test_an_update_runs_and_the_next_start_says_how_it_went(tmp_path, monkeypatch):
    suite.register("iocalendar", name="ioCalendar")
    # update.sh writes its result and (here) does not restart anything
    cal = updater(tmp_path, monkeypatch, script='printf "ok: updated to 1.1.0" > "$IOCALENDAR_RESULT"\n')
    cal._said_hello()
    assert suiteupdates.overview()[0]["canUpdate"]
    cal.serve("update")
    for _ in range(100):
        if not cal.progress["running"]:
            break
        time.sleep(0.05)
    a = suiteupdates.overview()[0]
    assert a["state"] == "ok" and a["message"] == "updated to 1.1.0"

    # a restart in the middle of update.sh leaves "running": the next start reads the result file
    suiteupdates.publish("iocalendar", state="running", latest="1.1.0", status="update")
    (tmp_path / "next").mkdir()
    new = updater(tmp_path / "next", monkeypatch, version="1.1.0")
    new.result_file = cal.result_file
    new._said_hello()
    a = suiteupdates.overview()[0]
    assert a["state"] == "ok" and a["version"] == "1.1.0" and a["status"] == "current"


def make_app():
    auth = Auth("iosuite", register=False)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.admin_router())
    return app


def signed_in(app, name, password):
    c = TestClient(app, base_url="http://home.example.com")
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


def test_the_admin_routes():
    suite.register("iocalendar", name="ioCalendar")
    users.create("alex", "secret123", suite_admin=True)
    users.create("ed", "secret123", "admin", "iosuite")
    app = make_app()
    ed = signed_in(app, "ed", "secret123")
    assert ed.get("/api/suite-admin/updates").status_code == 403  # an app admin is not a suite admin
    c = signed_in(app, "alex", "secret123")
    assert c.get("/api/suite-admin/updates").json()["apps"][0]["app"] == "iocalendar"
    r = c.post("/api/suite-admin/updates", json={"action": "check"}).json()
    assert r["asked"] == ["iocalendar"] and r["apps"][0]["pending"] == "check" and r["apps"][0]["requestedBy"] == "alex"
    assert c.post("/api/suite-admin/updates", json={"action": "update", "apps": "iocalendar"}).status_code == 400
    assert c.post("/api/suite-admin/updates", json={"action": "update", "apps": ["nope"]}).status_code == 400


def test_the_mcp_tools():
    from mcp.server.mcpserver.exceptions import ToolError
    suite.register("iocalendar", name="ioCalendar")
    server = shared_mcp.make_server("iosuite", "ioSuite", "1.0", instructions="")
    shared_mcp.add_suite_update_tools(server)
    alex = users.create("alex", "secret123", suite_admin=True)
    ed = users.create("ed", "secret123", "admin", "iosuite")

    def call(user, name, args):
        tok = shared_mcp.current_user.set(user)
        try:
            return asyncio.run(server.call_tool(name, args))
        finally:
            shared_mcp.current_user.reset(tok)
    with pytest.raises(ToolError):
        call(users.get(ed["id"], "iosuite"), "update_suite_apps", {})
    out = call(users.get(alex["id"], "iosuite"), "update_suite_apps", {"apps": ["iocalendar"]})
    assert "iocalendar" in str(out)
    assert db.one("SELECT action FROM ios_updates WHERE app = 'iocalendar'")["action"] == "update"
    out = call(users.get(alex["id"], "iosuite"), "suite_versions", {"check": False})
    assert "iocalendar" in str(out)


def test_the_restart_that_ends_update_sh_is_not_a_failure(tmp_path, monkeypatch):
    """update.sh writes ok, then restarts the service, which ends the script too (a signal): the update went through."""
    suite.register("iocalendar", name="ioCalendar")
    cal = updater(tmp_path, monkeypatch, script='printf "ok: updated to 1.1.0" > "$IOCALENDAR_RESULT"\necho "==> Restarting the service"\nkill -TERM $$\n')
    cal.serve("update")
    for _ in range(100):
        if not cal.progress["running"]:
            break
        time.sleep(0.05)
    assert cal.progress["error"] is None
    a = suiteupdates.overview()[0]
    assert a["state"] == "ok" and a["message"] == "updated to 1.1.0"

    # a row an older version marked failed that way is put right by the next start
    suiteupdates.publish("iocalendar", state="failed", message="==> Restarting the service")
    cal._said_hello()
    assert suiteupdates.overview()[0]["state"] == "ok"
