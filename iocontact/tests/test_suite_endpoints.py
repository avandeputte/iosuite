"""The suite's standard endpoints (/api/suite/*), answered through ioContact's own API as the viewer."""


def test_search_and_tile(client):
    assert client.get("/api/suite/search", params={"q": "nobody here"}).json() == {"items": [], "more": False}
    tile = client.get("/api/suite/tile").json()
    assert tile["items"] == [] and tile["more"] == 0
    assert client.get("/api/suite/items/contact/999999").status_code == 404
