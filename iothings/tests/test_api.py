"""The REST API: things, places, labels, files, upkeep and the log, and who may do what."""
import datetime as dt
import io

from PIL import Image

from app import db, files, upkeep
from conftest import sign_in


def new(client, **kw):
    r = client.post("/api/items", json={"name": "Boiler", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def png(w=40, h=30) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (200, 80, 20)).save(out, "PNG")
    return out.getvalue()


def test_things_places_and_labels(client):
    garage = client.post("/api/locations", json={"name": "Garage"}).json()
    shelf = client.post("/api/locations", json={"name": "Shelf", "parentId": garage["id"]}).json()
    assert shelf["path"] == "Garage / Shelf" and shelf["depth"] == 1
    it = new(client, name="Cordless drill", manufacturer="Makita", modelNumber="DHP482", serialNumber="SN-1",
             locationId=shelf["id"], labels=["Tools", "Power tools"], purchaseDate="2024-03-01", purchasePrice="€ 1.299,50",
             warrantyExpires=(dt.date.today() + dt.timedelta(days=10)).isoformat(), fields=[{"name": "Battery", "value": "18V"}])
    assert it["location"]["path"] == "Garage / Shelf" and {x["name"] for x in it["labels"]} == {"Tools", "Power tools"}
    assert it["purchasePrice"] == 1299.5 and it["warranty"]["state"] == "soon" and it["fields"] == [{"name": "Battery", "value": "18V"}]
    # a path makes the places it names
    car = new(client, name="Car", location="Driveway / Left", lifetimeWarranty=True)
    assert car["location"]["path"] == "Driveway / Left" and car["warranty"]["state"] == "lifetime"
    # the search looks in the maker, the place, the labels and the own fields
    for q in ("makita", "garage shelf", "power", "18v"):
        assert [x["name"] for x in client.get("/api/items", params={"q": q}).json()["items"]] == ["Cordless drill"], q
    assert [x["name"] for x in client.get("/api/items", params={"location": garage["id"]}).json()["items"]] == ["Cordless drill"]
    tools = next(x for x in client.get("/api/labels").json()["items"] if x["name"] == "Tools")
    assert tools["count"] == 1 and len(client.get("/api/items", params={"label": tools["id"]}).json()["items"]) == 1
    assert [x["name"] for x in client.get("/api/items", params={"warranty": "soon"}).json()["items"]] == ["Cordless drill"]
    s = client.get("/api/summary").json()
    assert s["counts"]["items"] == 2 and s["counts"]["warrantySoon"] == 1 and s["counts"]["worth"] == 1299.5
    # renaming a place: the things in it are found by its new name
    client.patch(f"/api/locations/{garage['id']}", json={"name": "Workshop"})
    assert client.get("/api/items", params={"q": "workshop"}).json()["items"][0]["name"] == "Cordless drill"
    assert client.patch(f"/api/locations/{garage['id']}", json={"parentId": shelf["id"]}).status_code == 400  # not inside itself
    # deleting a place: what was in it moves up
    assert client.delete(f"/api/locations/{shelf['id']}").status_code == 200
    assert client.get(f"/api/items/{it['id']}").json()["location"]["path"] == "Workshop"
    # archive, then change and the labels replaced
    ch = client.patch(f"/api/items/{it['id']}", json={"archived": True, "soldTo": "Neighbour", "soldPrice": 40, "labels": ["Tools"]}).json()
    assert ch["archived"] and ch["soldTo"] == "Neighbour" and [x["name"] for x in ch["labels"]] == ["Tools"]
    assert [x["name"] for x in client.get("/api/items").json()["items"]] == ["Car"]
    assert [x["name"] for x in client.get("/api/items", params={"archived": "only"}).json()["items"]] == ["Cordless drill"]
    dup = client.post(f"/api/items/{car['id']}/duplicate").json()
    assert dup["name"] == "Car (copy)" and dup["location"]["path"] == "Driveway / Left"
    assert client.delete(f"/api/items/{dup['id']}").status_code == 200
    assert client.get(f"/api/items/{dup['id']}").status_code == 404
    assert client.post("/api/items", json={"name": " "}).status_code == 400
    assert client.post("/api/items", json={"name": "X", "purchaseDate": "yesterday"}).status_code == 400


def test_files_photos_and_large_manuals(client):
    it = new(client)
    r = client.post(f"/api/items/{it['id']}/files", params={"name": "front.png"}, content=png(), headers={"Content-Type": "image/png"})
    assert r.status_code == 201 and r.json()["kind"] == "photo" and r.json()["thumb"]
    photo = r.json()
    got = client.get(f"/api/items/{it['id']}").json()
    assert got["photo"] == f"api/items/{it['id']}/files/{photo['id']}"
    small = client.get(f"/api/items/{it['id']}/files/{photo['id']}", params={"size": "small"})
    assert small.status_code == 200 and small.headers["content-type"] == "image/jpeg"
    # a manual larger than one part of the database comes back whole
    big = b"%PDF-1.4\n" + bytes(range(256)) * ((files.PART_BYTES * 2) // 256 + 100)
    m = client.post(f"/api/items/{it['id']}/files", params={"name": "manual.pdf"}, content=big, headers={"Content-Type": "application/octet-stream"}).json()
    assert m["kind"] == "manual" and m["mime"] == "application/pdf" and m["size"] == len(big)
    assert db.one("SELECT COUNT(*) AS n FROM thg_file_parts WHERE file_id = %s", (m["id"],))["n"] == 3
    d = client.get(f"/api/items/{it['id']}/files/{m['id']}")
    assert d.content == big and d.headers["content-disposition"].startswith("inline") and "sandbox" not in d.headers.get("content-security-policy", "")
    # a page that could run is a download
    h = client.post(f"/api/items/{it['id']}/files", params={"name": "x.html", "kind": "receipt"}, content=b"<script>1</script>", headers={"Content-Type": "text/html"}).json()
    hd = client.get(f"/api/items/{it['id']}/files/{h['id']}")
    assert hd.headers["content-type"] == "application/octet-stream" and hd.headers["content-disposition"].startswith("attachment")
    assert client.post(f"/api/items/{it['id']}/files", params={"kind": "photo"}, content=b"nope", headers={"Content-Type": "image/png"}).status_code == 400
    # another photo put first is the one the cards show
    p2 = client.post(f"/api/items/{it['id']}/files", content=png(10, 10), headers={"Content-Type": "image/png"}).json()
    client.patch(f"/api/items/{it['id']}/files/{p2['id']}", json={"first": True, "name": "side"})
    assert client.get(f"/api/items/{it['id']}").json()["photo"].endswith(f"/{p2['id']}")
    assert client.delete(f"/api/items/{it['id']}/files/{p2['id']}").status_code == 200
    assert client.get(f"/api/items/{it['id']}").json()["photo"].endswith(f"/{photo['id']}")
    assert [f["kind"] for f in client.get(f"/api/items/{it['id']}").json()["files"]] == ["photo", "manual", "receipt"]


def test_upkeep_and_the_log_without_iotask(client):
    it = new(client)
    due = dt.date(2026, 1, 31)
    k = client.post(f"/api/items/{it['id']}/upkeep", json={"title": "Service", "everyN": 1, "everyUnit": "month", "nextDue": due.isoformat()}).json()
    assert k["every"] == "every month" and k["task"] is None
    done = client.post(f"/api/upkeep/{k['id']}/done", json={"date": "2026-01-31", "cost": "85,00", "doneBy": "Heating Co"}).json()
    assert done["upkeep"]["nextDue"] == "2026-02-28" and done["logged"]["cost"] == 85.0 and done["logged"]["upkeepId"] == k["id"]
    client.post(f"/api/items/{it['id']}/maintenance", json={"title": "Replaced the pump", "date": "2026-02-10", "cost": 240})
    got = client.get(f"/api/items/{it['id']}").json()
    assert [x["title"] for x in got["maintenance"]] == ["Replaced the pump", "Service"]
    assert got["upkeep"][0]["nextDue"] == "2026-02-28"
    assert [x["title"] for x in client.get("/api/upkeep").json()["items"]] == ["Service"]
    assert client.get("/api/upkeep", params={"within": 0}).json()["items"][0]["item"]["name"] == "Boiler"
    ch = client.patch(f"/api/upkeep/{k['id']}", json={"everyN": 2, "everyUnit": "years"}).json()
    assert ch["every"] == "every 2 years"
    mid = got["maintenance"][0]["id"]
    assert client.patch(f"/api/maintenance/{mid}", json={"notes": "Under warranty"}).json()["notes"] == "Under warranty"
    assert client.delete(f"/api/maintenance/{mid}").status_code == 200
    assert client.delete(f"/api/upkeep/{k['id']}").status_code == 200
    assert client.get("/api/upkeep").json()["items"] == []
    assert client.get("/api/upkeep/lists").json() == {"available": False, "url": "", "lists": []}
    assert upkeep.step(dt.date(2024, 2, 29), 1, "year") == dt.date(2025, 2, 28)


def test_upkeep_as_a_repeating_task_in_iotask(client, monkeypatch):
    asked = []

    def fake(request, path, params=None, body=None, method=None):
        asked.append((method or ("POST" if body is not None else "GET"), path, params, body))
        if path == "/api/lists":
            return {"items": [{"id": 4, "name": "House", "writable": True, "shared": True}, {"id": 5, "name": "Read-only", "writable": False}]}
        if path == "/api/tasks":
            return {"id": 77, "title": body["title"]}
        if path == "/api/tasks/77" and method is None:
            return {"id": 77, "due": "2027-03-01"}  # ticked off in ioTask: it moved on there
        return {"ok": True}
    monkeypatch.setattr(upkeep, "tasks_enabled", lambda: True)
    monkeypatch.setattr(upkeep, "tasks_url", lambda: "https://tasks.example.com")
    monkeypatch.setattr(upkeep, "ask", fake)
    monkeypatch.setattr(upkeep.links, "resting", lambda app: 0)
    it = new(client, name="Car")
    assert client.get("/api/upkeep/lists").json()["lists"] == [{"id": 4, "name": "House", "shared": True}]
    k = client.post(f"/api/items/{it['id']}/upkeep", json={"title": "MOT", "everyN": 1, "everyUnit": "year", "nextDue": "2026-03-01", "listId": 4}).json()
    post = next(a for a in asked if a[1] == "/api/tasks")
    assert post[2] == {"list": "4"} and post[3]["title"] == "Car: MOT" and post[3]["rrule"] == "FREQ=YEARLY;INTERVAL=1" and post[3]["due"] == "2026-03-01"
    assert k["task"]["id"] == "77" and k["task"]["url"] == "https://tasks.example.com/#/task/77"
    # the next due day is ioTask's
    assert client.get(f"/api/items/{it['id']}").json()["upkeep"][0]["nextDue"] == "2027-03-01"
    client.post(f"/api/upkeep/{k['id']}/done", json={"date": "2027-02-20"})
    assert ("PATCH", "/api/tasks/77", None, {"due": "2028-02-20"}) in asked
    client.delete(f"/api/items/{it['id']}")
    assert ("DELETE", "/api/tasks/77", None, None) in asked


def test_who_may_do_what(client, as_user):
    it = new(client, name="Fridge")
    loc = client.post("/api/locations", json={"name": "Kitchen"}).json()
    as_user("val", "viewer")
    assert client.get(f"/api/items/{it['id']}").json()["writable"] is False
    assert client.post("/api/items", json={"name": "Mine"}).status_code == 403
    assert client.post(f"/api/items/{it['id']}/maintenance", json={"title": "x"}).status_code == 403
    sign_in(client, "alex")
    as_user("mia", "member")
    mine = new(client, name="Bike")
    assert mine["writable"] is True
    assert client.patch(f"/api/items/{it['id']}", json={"name": "Not mine"}).status_code == 403
    assert client.post(f"/api/items/{it['id']}/maintenance", json={"title": "Defrosted"}).status_code == 201  # anyone may log
    assert client.patch(f"/api/locations/{loc['id']}", json={"name": "x"}).status_code == 403
    assert client.post("/api/locations", json={"name": "Shed"}).status_code == 201
    assert client.delete(f"/api/items/{mine['id']}").status_code == 200
    sign_in(client, "alex")
    as_user("ed", "editor")
    assert client.patch(f"/api/items/{it['id']}", json={"name": "Big fridge"}).status_code == 200
    assert client.put("/api/things-settings", json={"currency": "USD"}).status_code == 403


def test_settings_currency(client):
    assert client.get("/api/things-settings").json()["currency"] == "EUR"
    assert client.put("/api/things-settings", json={"currency": "usd"}).json()["currency"] == "USD"
    assert client.get("/api/summary").json()["currency"] == "USD"
    assert client.put("/api/things-settings", json={"currency": "dollars"}).status_code == 400
