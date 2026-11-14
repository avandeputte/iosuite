"""Deleting someone in Settings › Security removes their favourites and private albums here; shared albums and
everybody else's stay (app/persondata.py, which the suite admin panel calls; the route itself is the shared library's)."""
from iosuite_shared import persondata as shared_persondata

from app import persondata
from app.data import state


def _n(sql, *a):
    con = state.connect()
    try:
        return con.execute(sql, a).fetchone()[0]
    finally:
        con.close()


def test_deleting_someone_removes_their_favourites_and_private_albums():
    def setup(c):
        for uid in (7, 8):
            c.executemany("INSERT INTO pix_favorite_photos (user_id, photo_id, hash, added_at) VALUES (?,?,?,?)", [(uid, 1, "a", 1), (uid, 2, "b", 1)])
        mine = c.execute("INSERT INTO pix_albums (name, created_at, owner_id, shared) VALUES ('Mine', 1, 7, 0)").lastrowid
        team = c.execute("INSERT INTO pix_albums (name, created_at, owner_id, shared) VALUES ('Team', 1, 7, 1)").lastrowid
        theirs = c.execute("INSERT INTO pix_albums (name, created_at, owner_id, shared) VALUES ('Theirs', 1, 8, 0)").lastrowid
        c.executemany("INSERT INTO pix_album_photos (album_id, photo_id, hash, added_at) VALUES (?,?,?,?)", [(a, 1, "a", 1) for a in (mine, team, theirs)])
        return mine, team, theirs
    mine, team, theirs = state.write(setup)
    try:
        got = {i["what"]: (i["count"], i["kept"]) for i in shared_persondata.clean(persondata.of(7, False))}
        assert got == {"favourites": (2, False), "private album": (1, False), "shared album they made": (1, True)}
        persondata.of(7, True)
        assert _n("SELECT count(*) FROM pix_favorite_photos WHERE user_id = 7") == 0
        assert _n("SELECT count(*) FROM pix_favorite_photos WHERE user_id = 8") == 2
        assert _n("SELECT count(*) FROM pix_albums WHERE id = ?", mine) == 0 and _n("SELECT count(*) FROM pix_album_photos WHERE album_id = ?", mine) == 0
        assert _n("SELECT count(*) FROM pix_albums WHERE id IN (?, ?)", team, theirs) == 2
    finally:
        def clear(c):
            c.execute("DELETE FROM pix_album_photos"); c.execute("DELETE FROM pix_albums"); c.execute("DELETE FROM pix_favorite_photos")
        state.write(clear)
