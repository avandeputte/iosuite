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


def titles(res):
    """A list tool's answer: one text per row, so a single row comes back as itself."""
    return [x["title"] for x in (res if isinstance(res, list) else [res])]


def test_mcp_recipes(client, monkeypatch):
    secret = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    auth = {"Authorization": f"Bearer {secret}"}
    assert rpc(client, "tools/list", auth=auth)[0] == 404  # off on a fresh install
    client.post("/api/server", json={"mcpEnabled": True})
    client.cookies.clear()
    assert rpc(client, "tools/list")[0] == 401
    names = {t["name"] for t in rpc(client, "tools/list", auth=auth)[1]["result"]["tools"]}
    assert {"overview", "list_recipes", "search_recipes", "get_recipe", "create_recipe", "update_recipe", "delete_recipe",
            "import_recipe", "diagnostics", "check_for_update"} <= names
    r = call(client, auth, "create_recipe", title="Oat cookies", ingredients=["200 g oats", "1 egg"], steps=["Mix.", "Bake."],
             servings="24", cook_minutes=12, tags=["dessert"])
    assert r["title"] == "Oat cookies" and r["family"] is True and r["youCanChange"] is True and r["cookMinutes"] == 12
    assert call(client, auth, "overview")["recipes"] == {"all": 1, "family": 1, "mine": 0}
    assert titles(call(client, auth, "search_recipes", query="oats egg")) == ["Oat cookies"]
    assert call(client, auth, "get_recipe", recipe="oat cookies")["ingredients"] == ["200 g oats", "1 egg"]
    u = call(client, auth, "update_recipe", recipe=str(r["id"]), steps=["Mix.", "Chill.", "Bake."], family=False)
    assert u["steps"] == ["Mix.", "Chill.", "Bake."] and u["family"] is False and u["ingredients"] == ["200 g oats", "1 egg"]
    assert titles(call(client, auth, "list_recipes", scope="mine")) == ["Oat cookies"]
    assert "error" in call(client, auth, "get_recipe", recipe="nothing like it")
    from app import scrape
    from test_import import LD, page
    monkeypatch.setattr(scrape, "fetch", lambda url, limit, accept="", allowed=None: (page({**LD, "image": None}).encode(), "text/html", url))
    i = call(client, auth, "import_recipe", url="https://example.com/cookies")
    assert i["title"] == "Grandma's cookies" and i["hasPhoto"] is False and i["sourceUrl"] == "https://example.com/cookies"
    assert call(client, auth, "delete_recipe", recipe="Grandma's cookies") == {"deleted": "Grandma's cookies"}
    assert call(client, auth, "diagnostics")["database"]["recipes"] == 1
