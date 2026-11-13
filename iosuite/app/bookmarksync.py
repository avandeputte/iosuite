"""What the two sync protocols share (app/ncbookmarks.py: the Nextcloud Bookmarks API; app/bookmarkdav.py: a
bookmarks file over WebDAV): who is asking, the lock a client holds while it syncs, the tree as the items of a file,
and taking a whole file as the new state of the tree.

A sync client signs in with HTTP Basic: the account's name and an app password (Settings › Account, or the one the
Nextcloud sign-in flow makes), kept in the Shared ioSuite database like every app password. Reading takes an account;
changing takes an editor or admin, as in the Bookmarks page.
"""
import time

from fastapi import HTTPException, Request
from iosuite_shared import users

from app import bookmarks, db
from app.auth import auth

LOCK_TTL = 15 * 60  # a lock nobody refreshed for this long is a client that went away (Floccus: every 2 minutes)
REALM = 'Basic realm="ioSuite bookmarks", charset="UTF-8"'


def user(request: Request, write: bool = False) -> dict:
    """The account asking, or 401 (with the Basic challenge that makes a client send its password) / 403."""
    u = auth.current_user(request)
    if not u:
        raise HTTPException(401, "Sign in with your ioSuite name and an app password.", headers={"WWW-Authenticate": REALM})
    if write and not users.can_write(u):
        raise HTTPException(403, "Only an editor or admin can change the bookmarks; this account can read them.")
    return u


# ------------------------------------------------------------------ the lock

def locked_at() -> float:
    """When the lock was last set, or 0 when nobody holds it (or its holder went away)."""
    try:
        at = float(db.get_setting("bookmarks_lock") or 0)
    except ValueError:
        at = 0
    return at if at and time.time() - at < LOCK_TTL else 0


def lock() -> None:
    db.set_setting("bookmarks_lock", repr(time.time()))


def unlock() -> None:
    db.set_setting("bookmarks_lock", None)


def alive() -> None:
    """A client that is writing still holds its lock."""
    if locked_at():
        lock()


# ------------------------------------------------------------------ the tree as a file's items

def items(t: bookmarks.Tree | None = None, pid=None) -> list[dict]:
    t = t or bookmarks.Tree()
    return [{"type": "folder", "id": r["id"], "title": r["name"], "children": items(t, r["id"])} if r["folder"] else
            {"type": "bookmark", "id": r["id"], "title": r["name"], "url": r["url"], "tags": bookmarks.tags_of(r)} for r in t.children(pid)]


def replace(new: list[dict], base_rev: int) -> bool:
    """The tree becomes what a client's file says (a WebDAV client uploads the whole of it). An item is the node with
    its id (when the client can have known it: made by `base_rev`, the revision its copy was fetched at), else, with
    no id, a node in the same folder with the same address (or folder name); anything else is new, under the id the
    file gives when that is free. What the file leaves out is removed, unless it changed after the client fetched its
    copy (somebody edited the start page meanwhile): that stays, for the client's next sync.
    Returns whether the tree is now exactly the file, ids included (then the file can be served back as it came)."""
    exact = True
    with bookmarks.writing() as rev:
        t = bookmarks.Tree()
        seen: set = set()

        def find(it, pid):
            folder = it["type"] == "folder"
            r = t.by.get(it["id"]) if it["id"] else None
            if r and r["id"] not in seen and bool(r["folder"]) == folder and r["created_rev"] <= base_rev:
                return r
            if it["id"] is None:
                for c in t.children(pid):
                    if c["id"] not in seen and bool(c["folder"]) == folder and (c["name"] == it["title"] if folder else c["url"] == it.get("url")):
                        return c
            return None

        def level(new, pid):
            nonlocal exact
            for pos, it in enumerate(new):
                folder = it["type"] == "folder"
                title = (it.get("title") or "").strip()[:bookmarks.NAME_MAX]
                url = None if folder else (it.get("url") or "").strip()
                if not folder and (not url or len(url) > bookmarks.URL_MAX):
                    exact = False
                    continue
                r = find(it, pid)
                if r:
                    nid = r["id"]
                    if (r["name"], r["url"], r["parent_id"], r["position"]) != (title, url, pid, pos):
                        db.ex("UPDATE prt_bookmark_nodes SET name = %s, url = %s, parent_id = %s, position = %s, rev = %s WHERE id = %s",
                              (title, url, pid, pos, rev, nid))
                    if it["id"] is None:
                        exact = False
                else:
                    free = it["id"] is not None and it["id"] not in t.by and it["id"] not in seen
                    if free:
                        nid = it["id"]
                        bookmarks.saw_id(nid)
                    else:
                        nid, exact = bookmarks._new_id(), False
                    db.ex("INSERT INTO prt_bookmark_nodes (id, parent_id, folder, name, url, tags, start, position, rev, created_rev) "
                          "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                          (nid, pid, 1 if folder else 0, title, url, "\n".join(bookmarks.clean_tags(it.get("tags"))) or None,
                           0 if folder else None, pos, rev, rev))
                seen.add(nid)
                if folder:
                    level(it.get("children") or [], nid)

        level(new, None)
        keep: set = set()
        for r in t.rows:  # what changed since the client's copy stays, with the folders it is in
            if r["id"] not in seen and r["rev"] > base_rev:
                while r and r["id"] not in seen and r["id"] not in keep:
                    keep.add(r["id"])
                    r = t.by.get(r["parent_id"])
        if keep:
            exact = False
        gone = [r["id"] for r in t.rows if r["id"] not in seen and r["id"] not in keep]
        for nid in gone:
            db.ex("DELETE FROM prt_bookmark_nodes WHERE id = %s", (nid,))  # a folder takes what is left in it along
    return exact
