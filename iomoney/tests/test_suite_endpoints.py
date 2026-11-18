"""The suite's standard endpoints (/api/suite/*), answered through ioMoney's own API as the viewer."""


def test_search_and_tile(client):
    assert client.get("/api/suite/search", params={"q": "nobody here"}).json()["items"] == []
    assert client.get("/api/suite/search", params={"q": "oak", "kinds": "asset,transaction"}).json()["items"] == []
    tile = client.get("/api/suite/tile", params={"tz": "Europe/Brussels"}).json()
    assert tile["bills"] == [] and tile["more"] == 0
    assert client.get("/api/suite/items/transaction/999999").status_code == 404
