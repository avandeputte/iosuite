"""The start page's wall display can show the viewer's favorites or one album: /api/random takes fav and ualbum, and
the suite tile answers kind favorites, album:<id> and albums (the list to pick from)."""
from app import users
from app.data import state
from helpers import login as _login


def _clear():
    con = state.connect()
    for t in ("pix_favorite_photos", "pix_album_photos", "pix_albums"):
        con.execute(f"DELETE FROM {t}")
    con.commit(); con.close()
    state._taken = False


def _ids(r) -> set:
    return {it["id"] for it in r["items"]}


def test_favorites_and_an_album_for_the_wall(client, fresh, lib):
    _clear()
    users.create("alex", "admin-pass1", "admin"); users.create("vi", "viewer-pass", "member")
    p1, p2, p3 = lib["ids"][:3]
    try:
        _login(client, "alex", "admin-pass1")
        assert client.post("/api/favorites", json={"ids": [p1, p2]}).status_code == 200
        assert set(client.get("/api/random?n=60&fav=1").json()["id"]) == {p1, p2}
        r = client.get("/api/suite/tile?kind=favorites&n=24").json()
        assert r["kind"] == "favorites" and _ids(r) == {p1, p2}

        mine = client.post("/api/ualbums", json={"name": "Wall", "shared": False, "ids": [p3]}).json()["id"]
        assert client.get(f"/api/random?n=60&ualbum={mine}").json()["id"] == [p3]
        r = client.get(f"/api/suite/tile?kind=album:{mine}&n=24").json()
        assert r["kind"] == f"album:{mine}" and _ids(r) == {p3}
        assert {"id": mine, "name": "Wall", "n": 1} in client.get("/api/suite/tile?kind=albums").json()["albums"]

        # someone else: none of alex's favorites, and alex's private album is not theirs to see: the library's photos
        _login(client, "vi", "viewer-pass")
        assert client.get("/api/random?n=60&fav=1").json()["id"] == []
        r = client.get(f"/api/suite/tile?kind=album:{mine}&n=24").json()
        assert r["kind"] == "rediscover" and r["items"]
        assert client.get("/api/suite/tile?kind=favorites&n=24").json()["kind"] == "rediscover"
        assert all(a["id"] != mine for a in client.get("/api/suite/tile?kind=albums").json()["albums"])
    finally:
        _clear()
