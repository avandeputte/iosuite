"""The MCP server at /mcp: off until switched on, signed in with an app password, acting as that account."""
import base64
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
    if not content:
        return []
    if len(content) > 1:
        return [json.loads(x["text"]) for x in content]
    return json.loads(content[0]["text"]) if content[0]["type"] == "text" else content[0]


def app_password(client):
    secret = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    return {"Authorization": f"Bearer {secret}"}, secret


def test_mcp_switch_and_sign_in(client):
    auth, secret = app_password(client)
    assert rpc(client, "tools/list", auth=auth)[0] == 404  # off on a fresh install
    assert client.post("/api/server", json={"mcpEnabled": True}).json()["mcpEnabled"] is True
    client.cookies.clear()
    assert rpc(client, "tools/list")[0] == 401  # nobody
    code, msg = rpc(client, "tools/list", auth=auth)
    names = {t["name"] for t in msg["result"]["tools"]}
    assert {"overview", "list_calendars", "agenda", "search_events", "get_event", "get_ics", "free_busy", "create_event", "update_event",
            "delete_event", "move_event", "create_calendar", "import_ics", "diagnostics", "check_for_update", "update_server"} <= names
    basic = {"Authorization": "Basic " + base64.b64encode(f"alex:{secret}".encode()).decode()}
    assert call(client, basic, "overview")["you"]["name"] == "alex"


def test_mcp_events(client, family_id):
    auth, _ = app_password(client)
    client.post("/api/server", json={"mcpEnabled": True})
    ev = call(client, auth, "create_event", title="Swim lessons", start="2026-11-02T16:00", end="2026-11-02T17:00", calendar="Family",
              location="City pool", repeat="FREQ=WEEKLY;COUNT=4", people=["Sam"], reminders=[30])
    assert ev["title"] == "Swim lessons" and ev["calendar"] == "Family" and ev["rrule"] == "FREQ=WEEKLY;COUNT=4"
    assert ev["start"] == "2026-11-02T16:00:00-05:00" and ev["reminders"] == [30] and ev["people"][0]["name"] == "Sam"
    ag = call(client, auth, "agenda", start="2026-11-01", end="2026-12-01")
    items = ag["items"] if isinstance(ag, dict) else ag
    swims = [o for o in items if o["title"] == "Swim lessons"]
    assert len(swims) == 4
    # the third one only, moved an hour later
    third = swims[2]
    ch = call(client, auth, "update_event", event=str(ev["id"]), occurrence=third["recurrenceId"], scope="this", start="2026-11-16T17:00",
              end="2026-11-16T18:00")
    assert "error" not in ch
    ag = call(client, auth, "agenda", start="2026-11-01", end="2026-12-01", text="swim")
    items = ag["items"] if isinstance(ag, dict) else ag
    assert [o["start"][11:16] for o in items] == ["16:00", "16:00", "17:00", "16:00"]
    fb = call(client, auth, "free_busy", start="2026-11-02", end="2026-11-03")
    assert fb["busy"] and fb["busy"][0]["start"].startswith("2026-11-02T21:00")
    assert "BEGIN:VEVENT" in call(client, auth, "get_ics", event=str(ev["id"]))
    found = call(client, auth, "search_events", text="pool")
    assert [x["title"] for x in (found if isinstance(found, list) else [found])] == ["Swim lessons"]
    assert "error" not in call(client, auth, "delete_event", event=str(ev["id"]), occurrence=items[3]["recurrenceId"], scope="this")
    ag = call(client, auth, "agenda", start="2026-11-01", end="2026-12-01", text="swim")
    assert len(ag["items"] if isinstance(ag, dict) else ag) == 3


def test_mcp_viewer_cannot_change_shared(client, family_id):
    client.post("/api/server", json={"mcpEnabled": True})
    client.post("/api/users", json={"name": "kid", "password": "kidpass123", "role": "viewer"})
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "kid", "password": "kidpass123"}).status_code == 200
    auth, _ = app_password(client)
    r = call(client, auth, "create_event", title="Party", start="2026-11-20T18:00", calendar="Family")
    assert "error" in r
    mine = call(client, auth, "create_event", title="Homework", start="2026-11-20T18:00")
    assert mine["calendar"] == "Personal"
