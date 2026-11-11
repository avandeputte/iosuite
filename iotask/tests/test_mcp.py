"""The MCP server at /mcp: off until switched on, signed in with an app password, acting as that account."""
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


def test_mcp_tasks(client):
    secret = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    auth = {"Authorization": f"Bearer {secret}"}
    assert rpc(client, "tools/list", auth=auth)[0] == 404  # off on a fresh install
    client.post("/api/server", json={"mcpEnabled": True})
    client.cookies.clear()
    assert rpc(client, "tools/list")[0] == 401
    names = {t["name"] for t in rpc(client, "tools/list", auth=auth)[1]["result"]["tools"]}
    assert {"overview", "list_lists", "list_tasks", "search_tasks", "get_task", "create_task", "update_task", "complete_task",
            "delete_task", "move_task", "create_list", "import_ics", "diagnostics", "check_for_update"} <= names
    t = call(client, auth, "create_task", title="Buy milk", due="2026-11-12", priority="medium")
    assert t["title"] == "Buy milk" and t["list"] == "Family" and t["priority"] == "medium"
    sub = call(client, auth, "create_task", title="Oat milk", parent=str(t["id"]))
    assert sub["list"] == "Family"
    assert call(client, auth, "get_task", task="Buy milk")["children"][0]["title"] == "Oat milk"
    assert call(client, auth, "update_task", task=str(t["id"]), due="")["title"] == "Buy milk"
    r = call(client, auth, "complete_task", task="Oat milk")
    assert r["done"] is True
    assert [x["title"] for x in call(client, auth, "list_tasks")["items"]] == ["Buy milk"]
    ov = call(client, auth, "overview")
    assert ov["you"]["name"] == "alex" and {c["name"] for c in ov["lists"]} == {"Family", "Personal"}
    assert call(client, auth, "delete_task", task="Buy milk")["count"] == 2
    assert "diagnostics" and call(client, auth, "diagnostics")["database"]["tasks"] == 0
