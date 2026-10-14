"""The MCP server is part of the app: the streamable-HTTP endpoint at /mcp answers JSON-RPC
(initialize, tools/list, a tool call) on the viewer's own port, read-only, without sign-in."""
import json

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def _rpc(client, method, params=None, id=1):
    body = {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}
    r = client.post("/mcp", json=body, headers=HEADERS)
    assert r.status_code == 200, (method, r.status_code, r.text[:300])
    text = r.text
    if "text/event-stream" in r.headers.get("content-type", ""):  # one event per response
        text = "\n".join(l[5:].strip() for l in text.splitlines() if l.startswith("data:"))
    return json.loads(text)


def test_initialize_and_tools(client):
    init = _rpc(client, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}})
    assert init["result"]["serverInfo"]["name"]
    assert "tools" in init["result"]["capabilities"]
    tools = _rpc(client, "tools/list", id=2)["result"]["tools"]
    names = {t["name"] for t in tools}
    assert len(names) >= 5 and any("search" in n or "photos" in n for n in names), names


def test_a_read_only_tool_call_works_anonymously(client, lib):
    tools = _rpc(client, "tools/list", id=3)["result"]["tools"]
    name = next((t["name"] for t in tools if t["name"] in ("library_summary", "summary", "stats", "library_stats")), None)
    if name is None:
        name = next(t["name"] for t in tools if not t.get("inputSchema", {}).get("required"))
    out = _rpc(client, "tools/call", {"name": name, "arguments": {}}, id=4)
    assert "result" in out and not out["result"].get("isError"), out
