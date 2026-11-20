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


def test_tile_events_carry_their_details(client):
    """What the wall display shows of a tapped event: who of the family it is for, its calendar, its notes."""
    import datetime as dt
    # two days on, not one: the tile's week starts tomorrow in its own zone, which in the evening in the Americas is
    # already the day after the test process's tomorrow
    day = dt.date.today() + dt.timedelta(days=2)
    r = client.post("/api/events", json={"title": "Swimming", "start": f"{day.isoformat()}T10:00", "notes": "Bring goggles"})
    assert r.status_code in (200, 201), r.text
    ev = client.get("/api/suite/tile", params={"kind": "week"}).json()["days"][0]["items"][0]
    assert ev["title"] == "Swimming" and ev["notes"] == "Bring goggles" and ev["calendar"]
    assert "who" not in ev and "people" not in ev  # nobody on it
    start, end = day.isoformat(), (day + dt.timedelta(days=1)).isoformat()
    assert "notes" not in client.get("/api/occurrences", params={"start": start, "end": end}).json()["items"][0]
    assert client.get("/api/occurrences", params={"start": start, "end": end, "notes": 1}).json()["items"][0]["notes"] == "Bring goggles"
