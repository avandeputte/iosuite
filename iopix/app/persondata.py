"""What a person keeps in ioPix, counted or removed when their account is deleted (iosuite_shared.persondata):
their favourites and their private albums. The photos themselves, shared albums and the library's history stay: they
are the family's (the person they are in photos is a link in the Shared ioSuite database, which goes with the account)."""
from app.data import appdb, state


def of(user_id: int, remove: bool) -> list:
    uid = int(user_id)
    if uid <= 0 or not appdb.configured():  # 0: the one list from before there were accounts
        return []
    if not appdb.ready():
        raise RuntimeError(f"ioPix's database is not reachable ({appdb.error})")
    con = state.connect()
    try:
        n = lambda sql: int(con.execute(sql, (uid,)).fetchone()[0])  # noqa: E731
        out = [{"what": "favourites", "one": "favourite", "count": n("SELECT count(*) FROM pix_favorite_photos WHERE user_id = ?")},
               {"what": "private albums", "one": "private album", "count": n("SELECT count(*) FROM pix_albums WHERE owner_id = ? AND shared = 0")},
               {"what": "shared albums they made", "one": "shared album they made", "count": n("SELECT count(*) FROM pix_albums WHERE owner_id = ? AND shared = 1"), "kept": True}]
    finally:
        con.close()
    if remove:
        def run(c):
            c.execute("DELETE FROM pix_album_photos WHERE album_id IN (SELECT id FROM pix_albums WHERE owner_id = ? AND shared = 0)", (uid,))
            c.execute("DELETE FROM pix_albums WHERE owner_id = ? AND shared = 0", (uid,))
            c.execute("DELETE FROM pix_favorite_photos WHERE user_id = ?", (uid,))
        state.write(run)
    return out
