"""Favorites are each account's own. While there are no accounts there is one list; once accounts exist, that list
becomes the favorites of the first admin who uses the app; every other account starts with none; a visitor has none."""
from app import users
from app.data import appdb, state
from helpers import login as _login


def _favs(client) -> list:
    return client.get("/api/state").json()["favorites"]


def _count(client) -> int:
    return client.get("/api/photos?fav=1").json()["count"]


def _clear():
    con = state.connect()
    con.execute("DELETE FROM pix_favorite_photos")
    con.commit(); con.close()
    state._taken = False


def test_each_account_keeps_its_own_favorites(client, fresh, lib):
    _clear()
    users.create("alex", "admin-pass1", "admin"); users.create("vi", "viewer-pass", "member")
    p1, p2, p3 = lib["ids"][:3]
    try:
        _login(client, "alex", "admin-pass1")
        assert client.post("/api/favorites", json={"ids": [p1, p2]}).status_code == 200
        assert set(_favs(client)) == {p1, p2} and _count(client) == 2

        _login(client, "vi", "viewer-pass")
        assert _favs(client) == [] and _count(client) == 0, "someone else's favorites are not mine"
        assert client.post("/api/favorites", json={"ids": [p2, p3]}).status_code == 200
        assert set(_favs(client)) == {p2, p3} and _count(client) == 2
        assert client.post("/api/favorites", json={"ids": [p2], "on": False}).status_code == 200
        assert _favs(client) == [p3] and _count(client) == 1

        _login(client, "alex", "admin-pass1")
        assert set(_favs(client)) == {p1, p2} and _count(client) == 2, "and mine are untouched by theirs"
        assert state.is_favorite(p1, users.get(next(u["id"] for u in users.list_users() if u["name"] == "alex")))
        assert not state.is_favorite(p1, users.get(next(u["id"] for u in users.list_users() if u["name"] == "vi")))

        client.cookies.clear()  # a visitor, while accounts exist: no favorites to see or to set
        assert _favs(client) == [] and _count(client) == 0
        assert client.post("/api/favorites", json={"ids": [p1]}).status_code == 401
    finally:
        _clear()


def test_the_one_list_goes_to_one_account(client, fresh, lib):
    _clear()
    p1, p2, p3 = lib["ids"][:3]
    try:
        # no accounts: one list for everyone, as before
        assert client.post("/api/favorites", json={"ids": [p1, p2]}).status_code == 200
        assert set(_favs(client)) == {p1, p2} and _count(client) == 2
        users.create("alex", "admin-pass1", "admin"); users.create("sam", "admin-pass2", "admin"); users.create("vi", "viewer-pass", "member")

        _login(client, "vi", "viewer-pass")  # not an admin: the list is not theirs to take
        assert _favs(client) == [] and _count(client) == 0
        assert client.post("/api/favorites", json={"ids": [p3]}).status_code == 200

        _login(client, "alex", "admin-pass1")  # the first admin to open the app keeps the favorites there were
        assert set(_favs(client)) == {p1, p2} and _count(client) == 2
        assert client.post("/api/favorites", json={"ids": [p1], "on": False}).status_code == 200
        assert _favs(client) == [p2]
        con = state.connect()
        try:
            assert con.execute("SELECT count(*) FROM pix_favorite_photos WHERE user_id = 0").fetchone()[0] == 0, "moved, not copied"
        finally:
            con.close()

        _login(client, "sam", "admin-pass2")  # another admin, afterwards: none, as for everyone else
        assert _favs(client) == [] and _count(client) == 0
        _login(client, "vi", "viewer-pass")
        assert _favs(client) == [p3]

        state._taken = False  # a restart: nothing changes hands again
        _login(client, "sam", "admin-pass2")
        assert _favs(client) == []
        _login(client, "alex", "admin-pass1")
        assert _favs(client) == [p2]
    finally:
        _clear()


def test_a_database_from_before_keeps_its_favorites(client, lib):
    """Before 1.151 the table had one row per photo. The rows stay, and the key becomes (account, photo)."""
    _clear()
    p1, p2 = lib["ids"][:2]
    con = appdb.connect()
    try:
        con.execute("DROP TABLE pix_favorite_photos")
        con.execute("CREATE TABLE pix_favorite_photos (photo_id BIGINT PRIMARY KEY, hash VARCHAR(64), added_at BIGINT)")
        con.execute("INSERT INTO pix_favorite_photos VALUES (?,?,?), (?,?,?)", (p1, "h1", 10, p2, "h2", 20))
        con.commit()
        appdb.ensure_schema(con)
        assert [tuple(r) for r in con.execute("SELECT user_id, photo_id, hash, added_at FROM pix_favorite_photos ORDER BY photo_id")] == [(0, p1, "h1", 10), (0, p2, "h2", 20)]
        con.execute("INSERT INTO pix_favorite_photos (user_id, photo_id, hash, added_at) VALUES (?,?,?,?)", (7, p1, "h1", 30))  # the same photo, another account
        con.commit()
        appdb.ensure_schema(con)  # and again: nothing to do
        assert con.execute("SELECT count(*) FROM pix_favorite_photos").fetchone()[0] == 3
    finally:
        con.close()
    try:
        assert state.summary(None)["favorites"] == [p2, p1], "newest first, as before"
    finally:
        _clear()
