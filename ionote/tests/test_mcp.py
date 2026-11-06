"""The MCP endpoint at /mcp: off until switched on; a client signs in with an app password (or a session) and works
on that account's own notes; anyone else is refused. Writes take an editor's account, the server tools an admin's (the
same as in every app of the suite)."""
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


def app_password(client, label="claude") -> dict:
    """A bearer header with a new app password of the signed-in account."""
    pw = client.post("/api/auth/app-passwords", json={"label": label}).json()["password"]
    return {"authorization": f"Bearer {pw}"}


def anon():
    """A client without a session cookie (the bearer header alone says who is asking); no lifespan: the session's app is running."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def signed_in(name, password):
    c = anon()
    assert c.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return c


@pytest.fixture
def on(client, admin):
    """The switch on, and alex's app password as a bearer header (the session cookie works too)."""
    client.post("/api/settings", json={"mcp_enabled": True})
    return app_password(client)


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


def test_writes_need_an_editor(client, on):
    client.post("/api/users", json={"name": "vic", "password": "viewerpw1", "role": "viewer"})
    bad = _call(anon(), "create_note", {"text": "hi"}, headers=app_password(signed_in("vic", "viewerpw1"), "vic's"))
    assert bad["isError"] and "editor" in bad["content"][0]["text"]
    ok = _call(client, "create_note", {"title": "From Claude", "text": "hello", "tags": ["ai"], "folder": None}, headers=on)
    assert not ok.get("isError"), ok
    nid = ok["structuredContent"]["id"]
    _call(client, "manage_folder", {"action": "create", "name": "AI"}, headers=on)
    upd = _call(client, "update_note", {"note_id": nid, "append_text": "more", "folder": "AI", "add_tags": ["x"]}, headers=on)
    assert not upd.get("isError"), upd
    n = client.get(f"/api/notes/{nid}").json()
    assert n["body"] == "hello\n\nmore" and n["tags"] == ["ai", "x"] and n["changedBy"] == "MCP" and n["source"] == "mcp"


def test_the_server_tools_need_an_admin(client, on):
    sam = client.post("/api/users", json={"name": "sam", "password": "secretpw2", "role": "editor"}).json()
    assert sam["id"]
    assert _call(anon(), "diagnostics", {}, headers=app_password(signed_in("sam", "secretpw2"), "sam's"))["isError"]
    assert _call(client, "diagnostics", {}, headers=on)["structuredContent"]["version"]


def test_with_sign_in_required_the_endpoint_wants_an_app_password(client, on):
    client.post("/api/settings", json={"require_login": True})
    client.post("/api/auth/logout")
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS)
    assert r.status_code == 401 and "app password" in r.text
    assert _rpc(client, "tools/list", headers=on)["result"]["tools"]


def test_each_account_works_on_its_own_notes(client, on):
    client.put(f"/api/notes/{NID}", json={"title": "alex's note", "updatedAt": 1})
    client.post("/api/users", json={"name": "sam", "password": "secretpw2", "role": "editor"})
    ov = _call(client, "notes_overview", {}, headers=on)["structuredContent"]
    assert ov["notes"] == 1 and ov["account"] == "alex"
    s = signed_in("sam", "secretpw2")
    sam, a = app_password(s, "sam's"), anon()
    ov = _call(a, "notes_overview", {}, headers=sam)["structuredContent"]
    assert ov["notes"] == 0 and ov["account"] == "sam"
    assert _call(a, "get_note", {"note_id": NID}, headers=sam)["isError"]  # alex's note does not exist for sam
    made = _call(a, "create_note", {"title": "for sam"}, headers=sam)["structuredContent"]
    assert [n["id"] for n in s.get("/api/notes").json()["notes"]] == [made["id"]]
    assert [n["id"] for n in client.get("/api/notes").json()["notes"]] == [NID]


def test_nobody_reads_notes_through_mcp_without_signing_in(client, on):
    """Notes are private: /mcp shows a visitor nothing (even with sign-in not required), and the session cookie of a
    signed-in browser reaches only that account's notes."""
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
    found = _call(anon(), "search_notes", {"text": "secret"}, headers=on)["structuredContent"]  # alex's app password: alex's notes
    assert [n["id"] for n in found["notes"]] == [NID]


def test_search_by_date_filters_in_the_database(client, on):
    for i, (uid, day) in enumerate([(NID, "2026-01-05"), ("0F8C6F1E-1D2B-4F3A-9C1A-1234567890AC", "2026-02-05")]):
        ts = calendar.timegm(time.strptime(day, "%Y-%m-%d"))
        client.put(f"/api/notes/{uid}", json={"title": f"n{i}", "createdAt": ts, "updatedAt": ts})
    res = _call(client, "search_notes", {"created_from": "2026-02-01", "created_to": "2026-02-28"})["structuredContent"]
    assert res["total"] == 1 and res["notes"][0]["title"] == "n1"
    res = _call(client, "search_notes", {"created_to": "2026-01-05"})["structuredContent"]
    assert res["total"] == 1 and res["notes"][0]["title"] == "n0"
