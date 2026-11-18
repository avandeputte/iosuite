"""The suite's standard endpoints (/api/suite/*), answered through ioThings' own API as the viewer."""


def test_search_and_item(client):
    r = client.post("/api/items", json={"name": "Dentist chair", "location": "House / Attic", "warrantyExpires": "2030-01-01"})
    assert r.status_code == 201, r.text
    iid = r.json()["id"]
    x = client.get("/api/suite/search", params={"q": "dentist"}).json()["items"][0]
    assert (x["kind"], x["id"], x["title"], x["href"]) == ("item", str(iid), "Dentist chair", f"#/item/{iid}")
    assert "Attic" in x["text"] and "warranty to 2030-01-01" in x["text"]
    assert client.get(f"/api/suite/items/item/{iid}").json()["title"] == "Dentist chair"
