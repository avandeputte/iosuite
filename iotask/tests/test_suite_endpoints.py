"""The suite's standard endpoints (/api/suite/*, iosuite_shared.suiteitems), answered through ioTask's own API as the
viewer: what the start page's search box and tile and the linked-items panel read."""


def test_search_item_and_tile(client, family_id):
    t = client.post("/api/tasks", json={"title": "Call the dentist", "due": "2000-01-03", "listId": family_id}).json()
    done = client.post("/api/tasks", json={"title": "Dentist last year", "listId": family_id}).json()
    assert client.post(f"/api/tasks/{done['id']}/complete", json={"done": True}).status_code == 200
    got = client.get("/api/suite/search", params={"q": "dentist"}).json()
    assert [(x["title"], x["done"]) for x in got["items"]] == [("Call the dentist", False), ("Dentist last year", True)]
    x = got["items"][0]
    assert x["kind"] == "task" and x["id"] == str(t["id"]) and x["href"] == f"#/task/{t['id']}" and x["when"].startswith("2000-01-03") and x["color"]
    assert client.get("/api/suite/search", params={"q": "dentist", "kinds": "note"}).json()["items"] == []
    one = client.get(f"/api/suite/items/task/{t['id']}").json()
    assert one["title"] == "Call the dentist" and not one["done"]
    assert client.get("/api/suite/items/task/999999").status_code == 404
    assert client.get("/api/suite/items/note/1").status_code == 404
    tile = client.get("/api/suite/tile", params={"tz": "Europe/Brussels"}).json()
    assert tile["overdue"] >= 1 and tile["today"][0]["title"] == "Call the dentist" and tile["today"][0]["late"]
    client.cookies.clear()
    assert client.get("/api/suite/search", params={"q": "dentist"}).status_code == 401
