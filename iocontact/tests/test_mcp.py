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
    if len(content) > 1:  # a list comes back one item per content block
        return [json.loads(x["text"]) for x in content]
    return json.loads(content[0]["text"]) if content[0]["type"] == "text" else content[0]


def app_password(client, name="alex"):
    secret = client.post("/api/app-passwords", json={"label": "claude"}).json()["password"]
    return {"Authorization": f"Bearer {secret}"}, secret


def test_mcp_switch_and_sign_in(client):
    auth, secret = app_password(client)
    assert rpc(client, "tools/list", auth=auth)[0] == 404  # off on a fresh install
    assert client.post("/api/server", json={"mcpEnabled": True}).json()["mcpEnabled"] is True
    client.cookies.clear()
    assert rpc(client, "tools/list")[0] == 401  # nobody
    code, msg = rpc(client, "tools/list", auth=auth)
    names = {t["name"] for t in msg["result"]["tools"]}
    assert {"overview", "search_contacts", "get_contact", "create_contact", "update_contact", "add_relation", "family_tree",
            "upcoming_dates", "import_contacts", "export_contacts", "check_for_update", "update_server", "diagnostics"} <= names
    basic = {"Authorization": "Basic " + base64.b64encode(f"alex:{secret}".encode()).decode()}
    assert call(client, basic, "overview")["you"]["name"] == "alex"


def test_mcp_contacts_relations_and_permissions(client, family_id):
    auth, _ = app_password(client)
    client.post("/api/server", json={"mcpEnabled": True})
    mary = call(client, auth, "create_contact", contact={"fn": "Mary Ray", "gender": "F", "birthday": "1960-03-04",
                                                         "emails": ["mary@example.com"], "phones": [{"value": "+1 555 0100", "label": "mobile"}]})
    assert mary["name"]["family"] == "Ray" and mary["birthday"] == {"year": 1960, "month": 3, "day": 4} and mary["book"] == "Family"
    assert mary["birthdayRemind"] is True and "Mary Ray" in str(call(client, auth, "birthdays_in_month", month=3))
    assert call(client, auth, "update_contact", contact="Mary", changes={"birthdayRemind": False})["birthdayRemind"] is False
    assert "Mary Ray" not in str(call(client, auth, "birthdays_in_month", month=3)) and call(client, auth, "get_contact", contact="Mary")["birthday"]["day"] == 4
    call(client, auth, "update_contact", contact="Mary", changes={"birthdayRemind": True})
    # a partial birthday: the year, the year and month, or the month and day
    assert call(client, auth, "update_contact", contact="Mary", changes={"birthday": "1960"})["birthday"] == {"year": 1960, "month": None, "day": None}
    assert "Mary Ray" not in str(call(client, auth, "birthdays_in_month", month=3))  # no day to list her by
    assert call(client, auth, "update_contact", contact="Mary", changes={"birthday": "1960-03"})["birthday"] == {"year": 1960, "month": 3, "day": None}
    assert call(client, auth, "update_contact", contact="Mary", changes={"birthday": {"month": 3, "day": 4}})["birthday"] == {"year": None, "month": 3, "day": 4}
    assert call(client, auth, "update_contact", contact="Mary", changes={"birthday": "1960-03-04"})["birthday"] == {"year": 1960, "month": 3, "day": 4}
    tim = call(client, auth, "create_contact", contact={"name": {"given": "Tim", "family": "Ray"}, "gender": "M"})
    out = call(client, auth, "add_relation", contact="Mary Ray", related="Tim Ray", relation="son")
    assert out["relations"][0]["typeLabel"] == "Son"
    assert call(client, auth, "get_relatives", contact=str(tim["id"]))["relations"][0]["typeLabel"] == "Mother"
    found = call(client, auth, "search_contacts", text="555 0100")
    assert found["total"] == 1 and found["contacts"][0]["name"] == "Mary Ray"
    upd = call(client, auth, "update_contact", contact="Mary", changes={"emails": [{"value": "mary@work.example", "label": "work"}],
                                                                        "org": "Acme", "tags": ["family"]})
    assert len(upd["emails"]) == 2 and upd["org"] == "Acme" and upd["tags"] == ["family"]
    upd = call(client, auth, "update_contact", contact="Mary", changes={"emails": []}, lists="replace")
    assert "emails" not in upd
    tree = call(client, auth, "family_tree", contact="Tim Ray")
    assert {n["fn"] for n in tree["nodes"]} == {"Tim Ray", "Mary Ray"}
    assert "Mary" in call(client, auth, "export_contacts", format="vcf", contacts=["Mary Ray"])
    imp = call(client, auth, "import_contacts", data="BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Bob Lee\r\nN:Lee;Bob;;;\r\nEND:VCARD\r\n")
    assert imp["created"] == 1
    assert "matches several" in call(client, auth, "get_contact", contact="Ray")["error"]
    assert call(client, auth, "remove_relation", contact="Mary Ray", related="Tim Ray")["relations"] in (None, [])
    assert not call(client, auth, "get_contact", contact="Tim Ray").get("relations")
    assert call(client, auth, "delete_contact", contact="Bob Lee")["deleted"] == "Bob Lee"
    # a viewer: reads the family book, changes only their own
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    kid, _ = app_password(client)
    client.cookies.clear()
    assert call(client, kid, "get_contact", contact="Mary Ray")["fn"] == "Mary Ray"
    assert "not change" in call(client, kid, "update_contact", contact="Mary Ray", changes={"notes": "x"})["error"]
    mine = call(client, kid, "create_contact", contact={"fn": "Best Friend"})
    assert mine["book"] == "Personal"
    assert "admin" in call(client, kid, "update_server")["error"]
    assert "admin" in call(client, kid, "diagnostics")["error"]
    # alex does not see kid's private contact
    assert "No contact" in call(client, auth, "get_contact", contact=str(mine["id"]))["error"]


def test_server_status_for_admins(client):
    s = client.get("/api/server").json()
    assert s["version"] and "canRun" in s and s["mcpEnabled"] is False
    client.post("/api/server", json={"autoCheck": False})
    assert client.get("/api/server").json()["autoCheck"] is False
    assert client.get("/api/status").json()["updateAvailable"] is None
