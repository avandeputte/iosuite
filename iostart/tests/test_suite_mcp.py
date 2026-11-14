"""The suite's one MCP server: the start page's /mcp offers every other app's tools, passed on to that app's own /mcp
as the same person with the same ioStart app password, so each app still decides what that person may do there.

A small app of the suite (ioTask's key, its own Auth, the shared MCP pieces) runs on a real port beside the start page.
"""
import socket
import threading
import time

import pytest
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from iosuite_shared import apppasswords, mcp as shared_mcp, suite, users
from iosuite_shared.fastapi import Auth

from test_mcp import H, call, rpc

STATE = {"on": True, "added": []}


def _fake_app():
    auth = Auth("iotask", app_label="ioTask", register=False)
    server = shared_mcp.make_server("iotask", "ioTask", "1.0", instructions="ioTask: tasks. add_task adds one.")

    @server.tool(annotations=shared_mcp.READ_ONLY)
    def whoami() -> dict:
        """Who is asking, and their role here."""
        u = shared_mcp.who()
        return {"name": u["name"], "role": u["role"]}

    @server.tool(annotations=shared_mcp.ADDS)
    def add_task(title: str) -> dict:
        """Add a task."""
        u = shared_mcp.need_member()
        STATE["added"].append((u["name"], title))
        return {"added": title}

    @asynccontextmanager
    async def lifespan(app):
        async with shared_mcp.running(server):
            yield

    app = FastAPI(lifespan=lifespan)
    app.middleware("http")(auth.middleware(open_prefixes=("/mcp",), before=auth.mcp_gate(lambda: STATE["on"], on_user=shared_mcp.current_user.set)))

    @app.get("/api/whoami")
    def whoami_route(request: Request):
        u = auth.current_user(request)
        return {"name": u["name"] if u else None}

    shared_mcp.mount(app, server)
    return app


@pytest.fixture(scope="module")
def task_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(_fake_app(), host="127.0.0.1", port=port, log_level="warning", lifespan="on"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield port
    srv.should_exit = True
    t.join(5)


@pytest.fixture()
def suite_mcp(client, task_port):
    from app import mcp
    from app.apps import ORDER
    for key in ORDER:
        if key not in ("iostart", "iotask", "iocalendar"):
            suite.forget(key)
    suite.register("iotask", "ioTask", url="https://task.example.com", internal_url=f"http://127.0.0.1:{task_port}")
    suite.register("iocalendar", "ioCalendar", url=None, internal_url="http://127.0.0.1:1")  # nothing listens there
    assert client.post("/api/server", json={"mcpEnabled": True}).status_code == 200
    STATE.update(on=True, added=[])
    mcp.forget()
    secret = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    client.cookies.clear()
    return {"Authorization": f"Bearer {secret}"}


def names(auth, client):
    return {t["name"] for t in rpc(client, "tools/list", auth=auth)[1]["result"]["tools"]}


def test_other_apps_tools_are_listed_and_passed_on(client, suite_mcp):
    auth = suite_mcp
    got = names(auth, client)
    assert {"suite_version", "update_suite", "suite_apps", "iotask_whoami", "iotask_add_task"} <= got
    assert not any(n.startswith("iocalendar_") for n in got)  # it does not answer
    assert call(client, auth, "iotask_whoami") == {"name": "alex", "role": "admin"}
    assert call(client, auth, "iotask_add_task", title="Buy flour") == {"added": "Buy flour"}
    assert STATE["added"] == [("alex", "Buy flour")]
    apps = {a["app"]: a for a in call(client, auth, "suite_apps")["apps"]}
    assert apps["iotask"]["status"] == "ok" and apps["iotask"]["tools"] == 2 and "add_task" in apps["iotask"]["instructions"]
    assert apps["iocalendar"]["status"] == "unreachable"
    assert "error" in call(client, auth, "iotask_nonsense")
    assert "error" in call(client, auth, "nosuchapp_whoami")


def test_each_app_keeps_its_own_permissions(client, suite_mcp):
    from app import mcp
    # a viewer in ioTask sees its tools, but ioTask refuses the change
    vi = users.create("vi", "secret123", "member", "iostart")
    users.set_role(vi["id"], "iotask", "viewer")
    auth = {"Authorization": f"Bearer {apppasswords.create(vi['id'], 'iostart', 'claude')}"}
    assert call(client, auth, "iotask_whoami") == {"name": "vi", "role": "viewer"}
    assert "error" in call(client, auth, "iotask_add_task", title="x") and STATE["added"] == []
    # somebody with no role in ioTask gets none of its tools, and cannot call them
    no = users.create("no", "secret123", "member", "iostart")
    users.set_role(no["id"], "iotask", "none")
    auth = {"Authorization": f"Bearer {apppasswords.create(no['id'], 'iostart', 'claude')}"}
    mcp.forget()
    assert not any(n.startswith("iotask_") for n in names(auth, client))
    assert "error" in call(client, auth, "iotask_whoami")


def test_switched_off_app_offers_nothing(client, suite_mcp):
    STATE["on"] = False
    apps = {a["app"]: a for a in call(client, suite_mcp, "suite_apps")["apps"]}
    assert apps["iotask"]["status"] == "off" and apps["iotask"]["tools"] == 0
    assert not any(n.startswith("iotask_") for n in names(suite_mcp, client))


def test_hub_password_rules(client, suite_mcp, task_port):
    """Only an ioStart app password without a limit reaches another app's /mcp; nothing else of that app."""
    import httpx
    alex = users.find("alex")
    full = apppasswords.create(alex["id"], "iostart", "x")
    dav = apppasswords.create(alex["id"], "iostart", "phone", apppasswords.DAV)
    base = f"http://127.0.0.1:{task_port}"
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    assert httpx.post(base + "/mcp", headers={**H, "Authorization": f"Bearer {full}"}, json=body).status_code == 200
    assert httpx.post(base + "/mcp", headers={**H, "Authorization": f"Bearer {dav}"}, json=body).status_code == 401
    assert httpx.post(base + "/mcp", headers={**H, "Authorization": "Bearer iostart-00000000-nope"}, json=body).status_code == 401
    assert apppasswords.authenticate_hub(None, full, "iostart") is None  # the start page checks its own the usual way
    # outside /mcp an ioStart password is nothing to ioTask
    assert httpx.get(base + "/api/whoami", headers={"Authorization": f"Bearer {full}"}).status_code == 401
