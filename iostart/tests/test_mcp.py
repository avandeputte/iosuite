"""The MCP server at /mcp: off until switched on, signed in with an app password; updating every app at once (suite admins)."""
import json

H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, method, params=None, auth=None, id=1):
    r = client.post("/mcp", headers={**H, **(auth or {})}, json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}})
    if r.status_code != 200:
        return r.status_code, r.text
    text = r.text
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        text = next(line[5:].strip() for line in text.splitlines() if line.startswith("data:"))
    return 200, json.loads(text)


def call(client, auth, name, **args):
    code, msg = rpc(client, "tools/call", {"name": name, "arguments": args}, auth)
    assert code == 200, msg
    res = msg["result"]
    if res.get("isError"):
        return {"error": res["content"][0]["text"]}
    if res.get("structuredContent") is not None:
        sc = res["structuredContent"]
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    content = res["content"]
    return json.loads(content[0]["text"]) if content else []


def test_mcp_updates_every_app(client):
    from iosuite_shared import db as shared_db, users
    secret = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    auth = {"Authorization": f"Bearer {secret}"}
    assert rpc(client, "tools/list", auth=auth)[0] == 404  # off on a fresh install
    assert client.post("/api/server", json={"mcpEnabled": True}).status_code == 200
    assert client.get("/api/server").json()["mcpEnabled"] is True
    client.cookies.clear()
    assert rpc(client, "tools/list")[0] == 401
    names = {t["name"] for t in rpc(client, "tools/list", auth=auth)[1]["result"]["tools"]}
    assert {"suite_versions", "update_suite_apps"} <= names
    out = call(client, auth, "suite_versions", check=False)
    assert {a["app"] for a in out["apps"]} >= {"iocalendar", "ionote"}
    out = call(client, auth, "update_suite_apps", apps=["iocalendar"])
    assert out["asked"] == ["iocalendar"]
    assert shared_db.one("SELECT action, requested_by FROM ios_updates WHERE app = 'iocalendar'") == {"action": "update", "requested_by": "alex"}
    assert "error" in call(client, auth, "update_suite_apps", apps=["nope"])

    # an admin of the start page who is not a suite admin cannot
    ed = users.create("ed", "secret123", "admin", "iostart")
    from iosuite_shared import apppasswords
    pw = apppasswords.create(ed["id"], "iostart", "phone")
    assert "error" in call(client, {"Authorization": f"Bearer {pw}"}, "update_suite_apps", apps=["iocalendar"])
