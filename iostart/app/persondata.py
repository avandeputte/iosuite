"""What a person keeps on the start page, counted or removed when their account is deleted (iosuite_shared.persondata):
their own bookmarks (with what is in their own folders), their choices of shared bookmarks for their start page,
their home page layout, and the copies of their bookmarks file a browser synced with (/dav/bookmarks). Shared
bookmarks stay, whoever added them: they are everyone's."""
from app import db

FILES = ("bookmarkfile", "bookmarkfile-base", "bookmarkfile-temp")  # bookmarkdav._key: "<what>:<user id>:<file name>"


def of(user_id: int, remove: bool) -> list:
    own = db.one("SELECT count(*) AS n FROM prt_bookmark_nodes WHERE owner = %s AND shared = 0", (user_id,))["n"]
    starts = db.one("SELECT count(*) AS n FROM prt_bookmark_starts WHERE user_id = %s", (user_id,))["n"]
    layout = db.one("SELECT count(*) AS n FROM prt_settings WHERE name LIKE %s", (f"user:{int(user_id)}:%",))["n"]
    shared = db.one("SELECT count(*) AS n FROM prt_bookmark_nodes WHERE owner = %s AND shared = 1", (user_id,))["n"]
    files = [f"{what}:{int(user_id)}:%" for what in FILES]
    synced = db.one("SELECT count(*) AS n FROM prt_settings WHERE name LIKE %s", (files[0],))["n"]
    if remove:
        with db.tx():
            # children first is not needed: a folder of theirs only holds their own (ON DELETE CASCADE does the rest)
            db.ex("DELETE FROM prt_bookmark_nodes WHERE owner = %s AND shared = 0", (user_id,))
            db.ex("DELETE FROM prt_bookmark_starts WHERE user_id = %s", (user_id,))
            db.ex("DELETE FROM prt_settings WHERE name LIKE %s", (f"user:{int(user_id)}:%",))
            for like in files:
                db.ex("DELETE FROM prt_settings WHERE name LIKE %s", (like,))
    return [{"what": "own bookmarks and folders", "one": "own bookmark or folder", "count": own},
            {"what": "start page choices", "one": "start page choice", "count": starts},
            {"what": "home page layout", "count": layout},
            {"what": "synced bookmarks files", "one": "synced bookmarks file", "count": synced},
            {"what": "shared bookmarks they added", "one": "shared bookmark they added", "count": shared, "kept": True}]
