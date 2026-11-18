"""The suite's standard endpoints (/api/suite/*), answered through ioNote's own API as the viewer."""


def test_search_and_item(client, admin):
    n = client.post("/api/notes", json={"title": "", "body": "# Dentist\n\nDr. Molar, 02 555 01 23"}).json()
    got = client.get("/api/suite/search", params={"q": "molar"}).json()
    assert [(x["kind"], x["id"], x["title"], x["text"], x["href"]) for x in got["items"]] == [
        ("note", n["id"], "Dentist", "Dr. Molar, 02 555 01 23", f"#/note/{n['id']}")]
    assert client.get(f"/api/suite/items/note/{n['id']}").json()["title"] == "Dentist"
    assert client.get("/api/suite/items/note/not-a-uuid").status_code == 404
    assert client.get("/api/suite/tile").status_code == 404  # no tile of its own
