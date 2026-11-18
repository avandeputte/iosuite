"""The suite's standard endpoints (/api/suite/*), answered through ioCalendar's own API as the viewer."""


def test_search_item_and_tiles(client):
    r = client.post("/api/events", json={"title": "Dentist", "start": "2099-01-01T10:00", "location": "Town"})
    assert r.status_code in (200, 201), r.text
    eid = r.json()["id"]
    got = client.get("/api/suite/search", params={"q": "dentist", "tz": "Europe/Brussels"}).json()
    x = got["items"][0]
    assert (x["kind"], x["id"], x["title"], x["text"], x["done"]) == ("event", str(eid), "Dentist", "Town", False)
    assert x["href"].startswith(f"#/event/{eid}") and x["when"].startswith("2099-01-01") and x["color"]
    assert client.get(f"/api/suite/items/event/{eid}").json()["title"] == "Dentist"
    assert client.get("/api/suite/items/event/999999").status_code == 404
    assert set(client.get("/api/suite/tile", params={"tz": "Europe/Brussels"}).json()) == {"today", "more", "next"}
    assert set(client.get("/api/suite/tile", params={"kind": "week"}).json()) == {"days", "more"}
