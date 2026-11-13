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


def call(client, auth, tool, **args):
    code, msg = rpc(client, "tools/call", {"name": tool, "arguments": args}, auth)
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
            "import_recipe", "mark_recipe", "list_cookbooks", "create_cookbook", "add_to_cookbook", "remove_from_cookbook",
            "delete_cookbook", "diagnostics"} <= names
    assert not {"check_for_update", "update_server"} & names  # updating is the suite's (ioStart: suite_version, update_suite)
    r = call(client, auth, "create_recipe", title="Oat cookies", ingredients=["200 g oats", "1 egg"], steps=["Mix.", "Bake."],
             servings="24", cook_minutes=12, tags=["dessert"])
    assert r["title"] == "Oat cookies" and r["family"] is True and r["youCanChange"] is True and r["cookMinutes"] == 12
    assert call(client, auth, "overview")["recipes"] == {"all": 1, "family": 1, "mine": 0, "favourites": 0}
    m = call(client, auth, "mark_recipe", recipe="Oat cookies", favourite=True, rating=5)
    assert m["favourite"] is True and m["rating"] == 5 and m["ratingAverage"] == 5.0
    assert titles(call(client, auth, "list_recipes", scope="favourites")) == ["Oat cookies"]
    assert "rating" not in call(client, auth, "mark_recipe", recipe="Oat cookies", rating=0)
    assert "error" in call(client, auth, "mark_recipe", recipe="Oat cookies", rating=9)
    b = call(client, auth, "create_cookbook", name="Baking")
    assert b["name"] == "Baking" and b["family"] is True
    assert call(client, auth, "add_to_cookbook", cookbook="baking", recipes=["Oat cookies"]) == {"cookbook": "Baking", "added": ["Oat cookies"]}
    assert call(client, auth, "get_recipe", recipe="Oat cookies")["cookbooks"] == ["Baking"]
    assert titles(call(client, auth, "list_recipes", cookbook=str(b["id"]))) == ["Oat cookies"]
    books = call(client, auth, "list_cookbooks")
    assert (books if isinstance(books, dict) else books[0])["count"] == 1
    assert call(client, auth, "remove_from_cookbook", cookbook="Baking", recipes=["Oat cookies"])["removed"] == ["Oat cookies"]
    assert "error" in call(client, auth, "add_to_cookbook", cookbook="Nope", recipes=["Oat cookies"])
    assert call(client, auth, "delete_cookbook", cookbook="Baking") == {"deleted": "Baking"}
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
    assert i["title"] == "Grandma's cookies" and "photos" not in i and i["sourceUrl"] == "https://example.com/cookies"
    assert call(client, auth, "delete_recipe", recipe="Grandma's cookies") == {"deleted": "Grandma's cookies"}
    assert call(client, auth, "diagnostics")["database"]["recipes"] == 1
