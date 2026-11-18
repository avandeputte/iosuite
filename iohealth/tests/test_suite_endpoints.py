"""The suite's tile endpoint (/api/suite/tile), answered through ioHealth's own API as the viewer."""


def test_tile(client, admin):
    tile = client.get("/api/suite/tile", params={"tz": "Europe/Brussels"}).json()
    assert tile["steps"] is None and len(tile["week"]) == 7
    assert client.get("/api/suite/search", params={"q": "x"}).status_code == 404  # nothing to search
