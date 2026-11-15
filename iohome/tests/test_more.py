"""Homebox import and export, the MCP tools, notifications, and what happens when a person is deleted."""
import csv
import datetime as dt
import io
import json

import pytest
from iosuite_shared import push, users

from app import db, notify
from conftest import sign_in
from test_api import new

# rows as Homebox writes them (Tools › Export inventory): its own columns, a field, labels with ';', a formula-guarded cell
HOMEBOX = (
    "HB.import_ref,HB.location,HB.labels,HB.asset_id,HB.archived,HB.url,HB.name,HB.quantity,HB.description,HB.insured,"
    "HB.notes,HB.purchase_price,HB.purchase_from,HB.purchase_date,HB.manufacturer,HB.model_number,HB.serial_number,"
    "HB.lifetime_warranty,HB.warranty_expires,HB.warranty_details,HB.sold_to,HB.sold_price,HB.sold_date,HB.sold_notes,HB.field.Filter\r\n"
    "ref-1,Home / Kitchen,Appliances;Kitchen,000-001,false,https://example.com/fridge,Fridge,1,Big fridge,true,"
    "Defrost in spring,1299.5,Shop,2023-05-02,Samsung,RB38,SN123,false,2027-05-02,Two years,,0,0001-01-01,,'=water\r\n"
    "ref-2,Home / Garage,Tools,000-000,false,,Ladder,2,,false,,0,,,,,,true,0001-01-01,,,0,0001-01-01,,\r\n"
    ",Home,,,,,,,,,,,,,,,,,,,,,,,\r\n"
)


def test_homebox_import_is_idempotent_and_exports_back(client):
    r = client.post("/api/import/homebox", content=HOMEBOX.encode(), headers={"Content-Type": "text/csv"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["added"] == 2 and got["changed"] == 0 and len(got["skipped"]) == 1 and got["locations"] == 3 and got["labels"] == 3
    fridge = next(x for x in client.get("/api/items").json()["items"] if x["name"] == "Fridge")
    f = client.get(f"/api/items/{fridge['id']}").json()
    assert f["location"]["path"] == "Home / Kitchen" and f["purchasePrice"] == 1299.5 and f["warrantyExpires"] == "2027-05-02"
    assert f["insured"] is True and f["assetId"] == "000-001" and f["fields"] == [{"name": "Filter", "value": "=water"}]
    assert {x["name"] for x in f["labels"]} == {"Appliances", "Kitchen"}
    ladder = next(x for x in client.get("/api/items").json()["items"] if x["name"] == "Ladder")
    assert ladder["quantity"] == 2 and client.get(f"/api/items/{ladder['id']}").json()["lifetimeWarranty"] is True
    again = client.post("/api/import/homebox", content=HOMEBOX.replace("Big fridge", "The big fridge").encode()).json()
    assert again["added"] == 0 and again["changed"] == 2 and again["locations"] == 0
    assert client.get(f"/api/items/{fridge['id']}").json()["description"] == "The big fridge"
    out = client.get("/api/export.csv")
    assert out.status_code == 200 and out.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(out.text)))
    fr = next(x for x in rows if x["HB.name"] == "Fridge")
    assert fr["HB.location"] == "Home / Kitchen" and fr["HB.field.Filter"] == "'=water" and float(fr["HB.purchase_price"]) == 1299.5
    # and that file goes back in as it came out: nothing new
    back = client.post("/api/import/homebox", content=out.content).json()
    assert back["added"] == 0 and back["skipped"] == [], back
    assert client.post("/api/import/homebox", content=b"name,place\nx,y\n").status_code == 400


def test_a_viewer_may_not_import(client, as_user):
    as_user("vic", "viewer")
    assert client.post("/api/import/homebox", content=HOMEBOX.encode()).status_code == 403


H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def rpc(client, method, params=None, auth=None):
    r = client.post("/mcp", headers={**H, **(auth or {})}, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})
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


def rows(res):
    return res if isinstance(res, list) else [res]


def test_mcp_tools(client):
    secret = client.post("/api/auth/app-passwords", json={"label": "claude"}).json()["password"]
    auth = {"Authorization": f"Bearer {secret}"}
    assert rpc(client, "tools/list", auth=auth)[0] == 404  # off on a fresh install
    client.post("/api/server", json={"mcpEnabled": True})
    client.cookies.clear()
    names = {t["name"] for t in rpc(client, "tools/list", auth=auth)[1]["result"]["tools"]}
    assert {"overview", "search_items", "get_item", "create_item", "update_item", "delete_item", "list_locations", "create_location",
            "warranties_ending", "list_upkeep", "add_upkeep", "upkeep_done", "log_maintenance", "diagnostics"} <= names
    soon = (dt.date.today() + dt.timedelta(days=20)).isoformat()
    it = call(client, auth, "create_item", name="Boiler", location="House / Utility room", labels=["Heating"], manufacturer="Vaillant",
              purchase_price=2400, warranty_expires=soon, fields={"Pressure": "1.5 bar"})
    assert it["location"] == "House / Utility room" and it["labels"] == ["Heating"], it
    o = call(client, auth, "overview")
    assert o["counts"]["items"] == 1 and o["youCan"]["add"] is True and {p["path"] for p in o["places"]} == {"House", "House / Utility room"}
    assert [x["name"] for x in rows(call(client, auth, "search_items", query="vaillant"))] == ["Boiler"]
    assert [x["name"] for x in rows(call(client, auth, "warranties_ending", days=30))] == ["Boiler"]
    k = call(client, auth, "add_upkeep", item="boiler", what="Annual service", every=1, unit="year", next_due=dt.date.today().isoformat())
    assert k["title"] == "Annual service"
    due = rows(call(client, auth, "list_upkeep", within_days=7))
    assert due[0]["what"] == "Annual service" and due[0]["inIoTask"] is False
    call(client, auth, "upkeep_done", upkeep_id=due[0]["id"], cost=95, done_by="Heating Ltd")
    assert call(client, auth, "list_upkeep", within_days=7) in ([], {}), "moved on a year"
    call(client, auth, "log_maintenance", item="Boiler", what="New pump", cost=180)
    g = call(client, auth, "get_item", item="Boiler")
    assert {m["title"] for m in g["maintenance"]} == {"Annual service", "New pump"}
    u = call(client, auth, "update_item", item="Boiler", archived=True, sold_to="Neighbour")
    assert u["archived"] is True
    assert "error" in call(client, auth, "get_item", item="nothing like it")
    assert call(client, auth, "delete_item", item=str(it["id"])) == {"deleted": "Boiler"}
    assert call(client, auth, "diagnostics")["database"]["items"] == 0


@pytest.fixture
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(push, "_post", lambda endpoint, body, headers: out.append(endpoint) or 201)
    monkeypatch.setattr(push.outbound, "check", lambda url, allowed=None: "142.250.0.1")
    return out


def device(uid):
    from cryptography.hazmat.primitives.asymmetric import ec
    k = ec.generate_private_key(ec.SECP256R1())
    push.add_device(uid, {"endpoint": f"https://fcm.googleapis.com/fcm/send/{uid}",
                          "keys": {"p256dh": push.b64u(push._raw_public(k.public_key())), "auth": push.b64u(b"0123456789abcdef")}}, "iohome")


def test_morning_message_of_upkeep_and_warranties(client, sent):
    today = dt.date.today()
    it = new(client, name="Boiler", warrantyExpires=(today + dt.timedelta(days=7)).isoformat())
    assert client.post(f"/api/items/{it['id']}/upkeep", json={"title": "Service", "everyN": 1, "everyUnit": "year",
                                                             "nextDue": (today - dt.timedelta(days=2)).isoformat()}).status_code == 201
    new(client, name="Kettle", warrantyExpires=(today + dt.timedelta(days=8)).isoformat())  # not a day worth a word
    texts = [x["text"] for x in notify.today_for(today)]
    assert texts == ["Boiler: Service (2 days late)", "Boiler: the warranty ends in 7 days"]
    assert notify.run() == 0 and sent == [], "nobody has a device"
    alex = users.find("alex")["id"]
    device(alex)
    push.set_prefs(alex, morning="08:00")
    assert notify.run(dt.datetime.combine(today, dt.time(7, 0))) == 0, "not yet morning"
    at = dt.datetime.combine(today, dt.time(8, 1))
    assert notify.run(at) == 1 and len(sent) == 1
    assert notify.run(at) == 0, "once a day"


def test_deleting_someone_keeps_the_house(client, as_user):
    as_user("ann", "member")
    ann = users.find("ann")["id"]
    it = new(client, name="Ann's bike")
    client.post(f"/api/items/{it['id']}/maintenance", json={"title": "New tyre"})
    sign_in(client, "alex")
    got = client.get(f"/api/suite-admin/person-data/{ann}").json()["items"]
    assert {i["what"]: (i["count"], i["kept"]) for i in got} == {
        "thing they added": (1, True), "maintenance log line they wrote": (1, True)}
    assert client.delete(f"/api/suite-admin/users/{ann}").status_code == 200
    row = db.one("SELECT created_by FROM hom_items WHERE id = %s", (it["id"],))
    assert row and row["created_by"] is None
    assert client.get(f"/api/items/{it['id']}").json()["createdBy"] is None


def test_links_to_other_apps(client):
    it = new(client, name="Lawn mower")
    kinds = client.get("/api/related/kinds").json()
    assert "item" in json.dumps(kinds)
    from iosuite_shared import related
    assert related.KINDS["item"]["app"] == "iohome"
    assert related.check("item", it["id"]) == ("item", str(it["id"]))
