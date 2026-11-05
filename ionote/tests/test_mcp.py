"""The MCP endpoint at /mcp: off until switched on; with the admin token it works on the notes of the chosen account,
a signed-in account without it sees only its own notes, anyone else is refused once accounts exist. Writes take the
admin token as an argument (as in iopix)."""
import calendar
import json
import time

import pytest

from helpers import NID, png

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def _rpc(client, method, params=None, id=1, headers=None):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}, headers={**HEADERS, **(headers or {})})
    assert r.status_code == 200, (method, r.status_code, r.text[:300])
    text = r.text
    if "text/event-stream" in r.headers.get("content-type", ""):
        text = "\n".join(l[5:].strip() for l in text.splitlines() if l.startswith("data:"))
    return json.loads(text)


def _call(client, name, args, headers=None):
    res = _rpc(client, "tools/call", {"name": name, "arguments": args}, headers=headers)["result"]
    if "structuredContent" not in res and not res.get("isError") and res["content"] and res["content"][0]["type"] == "text":
        res["structuredContent"] = json.loads(res["content"][0]["text"])
    return res


@pytest.fixture
def on(client, admin):
    client.post("/api/settings", json={"mcp_enabled": True})
    return client.get("/api/mcp/token").json()["token"]


def test_off_until_switched_on(client, admin):
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS)
    assert r.status_code == 404


def test_tools_are_listed(client, on):
    names = {t["name"] for t in _rpc(client, "tools/list")["result"]["tools"]}
    assert {"notes_overview", "search_notes", "get_note", "view_note_image", "create_note", "update_note", "organize_notes",
            "delete_note", "manage_folder", "manage_tag", "diagnostics", "server_log", "proxy_signin", "update_ionotes"} <= names


def test_read_tools_and_a_picture(client, on):
    client.put(f"/api/notes/{NID}", json={"title": "Budget", "body": "quarterly numbers", "tags": ["work"], "updatedAt": 1})
    client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"})
    res = _call(client, "search_notes", {"text": "quarter"})
    assert not res.get("isError") and res["structuredContent"]["notes"][0]["id"] == NID
    full = _call(client, "get_note", {"note_id": NID})["structuredContent"]
    assert full["text"] == "quarterly numbers" and full["picture"]["width"] == 320
    img = _call(client, "view_note_image", {"note_id": NID})
    assert img["content"][0]["type"] == "image"


def test_writes_need_the_token(client, on):
    bad = _call(client, "create_note", {"token": "nope", "text": "hi"})
    assert bad["isError"]
    ok = _call(client, "create_note", {"token": on, "title": "From Claude", "text": "hello", "tags": ["ai"], "folder": None})
    assert not ok.get("isError"), ok
    nid = ok["structuredContent"]["id"]
    _call(client, "manage_folder", {"token": on, "action": "create", "name": "AI"})
    upd = _call(client, "update_note", {"token": on, "note_id": nid, "append_text": "more", "folder": "AI", "add_tags": ["x"]})
    assert not upd.get("isError"), upd
    n = client.get(f"/api/notes/{nid}").json()
    assert n["body"] == "hello\n\nmore" and n["tags"] == ["ai", "x"] and n["changedBy"] == "MCP" and n["source"] == "mcp"


def test_with_sign_in_required_the_endpoint_wants_the_bearer_token(client, on):
    client.post("/api/settings", json={"require_login": True})
    client.post("/api/auth/logout")
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS)
    assert r.status_code == 401
    assert _rpc(client, "tools/list", headers={"authorization": f"Bearer {on}"})["result"]["tools"]


def test_mcp_works_on_the_chosen_accounts_notes(client, on):
    client.put(f"/api/notes/{NID}", json={"title": "alex's note", "updatedAt": 1})
    sam = client.post("/api/users", json={"name": "sam", "password": "secretpw2", "role": "editor"}).json()
    bearer = {"authorization": f"Bearer {on}"}
    ov = _call(client, "notes_overview", {}, headers=bearer)["structuredContent"]
    assert ov["notes"] == 1 and ov["account"] == "alex"  # the first admin by default
    assert client.post("/api/settings", json={"mcp_user": sam["id"]}).status_code == 200
    assert client.get("/api/settings").json()["mcp_user"] == sam["id"]
    ov = _call(client, "notes_overview", {}, headers=bearer)["structuredContent"]
    assert ov["notes"] == 0 and ov["account"] == "sam"
    assert _call(client, "get_note", {"note_id": NID}, headers=bearer)["isError"]
    made = _call(client, "create_note", {"token": on, "title": "for sam"}, headers=bearer)["structuredContent"]
    client.cookies.clear()
    client.post("/api/auth/login", json={"name": "sam", "password": "secretpw2"})
    assert [n["id"] for n in client.get("/api/notes").json()["notes"]] == [made["id"]]


def test_nobody_reads_another_accounts_notes_through_mcp(client, on):
    """Notes are private: without the admin token, /mcp shows a visitor nothing (even with sign-in not required)
    and a signed-in account only its own notes, whatever account Settings › MCP server names."""
    client.put(f"/api/notes/{NID}", json={"title": "alex's secret", "updatedAt": 1})
    client.post("/api/users", json={"name": "sam", "password": "secretpw2", "role": "editor"})
    client.cookies.clear()
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "search_notes", "arguments": {"text": "secret"}}}, headers=HEADERS)
    assert r.status_code == 401
    client.post("/api/auth/login", json={"name": "sam", "password": "secretpw2"})
    ov = _call(client, "notes_overview", {})["structuredContent"]
    assert ov["notes"] == 0 and ov["account"] == "sam"
    assert _call(client, "get_note", {"note_id": NID})["isError"]
    # the token is what reaches the chosen account's notes (alex's, the first admin's)
    found = _call(client, "search_notes", {"text": "secret"}, headers={"authorization": f"Bearer {on}"})["structuredContent"]
    assert [n["id"] for n in found["notes"]] == [NID]


def test_search_by_date_filters_in_the_database(client, on):
    for i, (uid, day) in enumerate([(NID, "2026-01-05"), ("0F8C6F1E-1D2B-4F3A-9C1A-1234567890AC", "2026-02-05")]):
        ts = calendar.timegm(time.strptime(day, "%Y-%m-%d"))
        client.put(f"/api/notes/{uid}", json={"title": f"n{i}", "createdAt": ts, "updatedAt": ts})
    res = _call(client, "search_notes", {"created_from": "2026-02-01", "created_to": "2026-02-28"})["structuredContent"]
    assert res["total"] == 1 and res["notes"][0]["title"] == "n1"
    res = _call(client, "search_notes", {"created_to": "2026-01-05"})["structuredContent"]
    assert res["total"] == 1 and res["notes"][0]["title"] == "n0"
