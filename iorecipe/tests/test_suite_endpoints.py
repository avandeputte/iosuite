"""The suite's standard endpoints (/api/suite/*), answered through ioRecipe's own API as the viewer."""


def test_search_and_item(client):
    r = client.post("/api/recipes", json={"title": "Oat cookies", "prepMinutes": 15, "cookMinutes": 12, "ingredients": ["200 g oats"],
                                          "steps": ["Mix."], "tags": ["Dessert"]})
    assert r.status_code in (200, 201), r.text
    rid = r.json()["id"]
    got = client.get("/api/suite/search", params={"q": "oat"}).json()
    x = got["items"][0]
    assert (x["kind"], x["id"], x["title"], x["href"], x["image"]) == ("recipe", str(rid), "Oat cookies", f"#/recipe/{rid}", None)
    assert x["text"] == "27 min"
    assert client.get(f"/api/suite/items/recipe/{rid}").json()["title"] == "Oat cookies"
    assert client.get(f"/api/suite/items/recipe/{rid}/image").status_code == 404  # no picture
