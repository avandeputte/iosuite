"""The bookmarks: one tree of folders and links, as a browser keeps them.

Each bookmark is someone's own (`owner`: only they see it and change it) or shared (`shared`: everyone sees it, and
only an admin of the start page changes it, the Shared toggle on the Bookmarks page included). One tree holds both: a
person sees the shared bookmarks and their own, in the same folders (their own links can sit in a shared folder; a
shared bookmark is only ever in a shared folder or at the top). Who is asking is `viewer()`, which each request sets
with `as_user()`; every read below is that person's tree and every change is checked against what they may do. Someone
who is not an admin may still take a shared folder or link off their own start page (prt_bookmark_starts).

Browsers sync with it (app/ncbookmarks.py: the Nextcloud Bookmarks API, which Floccus and
other clients speak; app/bookmarkdav.py: a bookmarks file over WebDAV), and the start page shows the part picked for
it: a folder marked for the start page is a group there with its links, and a single link can be shown or hidden on
its own (`start`: None follows the folder). Editors and admins change the tree in the Bookmarks page.

A link on the start page has a name, a two-letter abbreviation or an icon, the address and a line under it (the host
name unless a description is given). An icon is an address or a dashboard-icons name in the link's icon field, or an
SVG (or a PNG) uploaded for the link and kept in the database (prt_bookmark_node_icons), which the page serves itself.

Sync clients may keep any address a browser can (javascript:, file:, about:…); the start page only ever shows web and
mailto: addresses, and what is typed in Settings must be one. Ids are handed out here and never reused (clients
remember them); every change moves the store's revision on (`revision()`), which is how a client's copy is known to
be current.
"""
import base64
import hashlib
import re
import xml.etree.ElementTree as ET

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_xml  # an uploaded file: no entity expansion or external entities
from urllib.parse import urlsplit

from app import db, siteicons


class BadBookmark(ValueError):
    pass


def _abbr(name: str, abbr: str | None) -> str:
    a = (abbr or "").strip()[:4]
    if a:
        return a
    words = re.findall(r"[A-Za-z0-9]+", name or "")
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    return (words[0][:2] if words else "?").upper()


def _href(href: str) -> str:
    """A link's address: a web address (https:// is added to a bare one) or a mailto:. Nothing else: the page puts it
    in an <a href>, where javascript: and data: addresses would run in the page."""
    h = (href or "").strip()
    if re.match(r"^mailto:[^\s@]+@[^\s@]+$", h, re.I):
        return h[:2048]
    if not re.match(r"^[a-z][a-z0-9+.-]*:", h, re.I) or re.match(r"^[^/:]+:\d+(/|$)", h):  # no scheme, or host:port
        h = "https://" + h if h else ""
    try:
        u = urlsplit(h)
    except ValueError:
        u = None
    if not u or u.scheme.lower() not in ("http", "https") or not u.netloc:
        raise BadBookmark("The link needs a web address, like https://example.com, or a mailto: address")
    return h[:2048]



import threading
from contextlib import contextmanager
from contextvars import ContextVar

NAME_MAX, URL_MAX = 1024, 60000
_SHOWN = re.compile(r"^(https?://|mailto:)", re.I)  # what the start page puts in an <a href>
_w = threading.local()


class NotFound(BadBookmark):
    pass


class NotAllowed(BadBookmark):
    pass


# ------------------------------------------------------------------ who is asking

class Viewer:
    """Whose tree it is: the account's id (`uid`), whether it may keep and change bookmarks of its own (`member`: a
    member, editor or admin of the start page) and whether it manages the shared ones (`admin`)."""

    def __init__(self, uid, member: bool, admin: bool):
        self.uid, self.member, self.admin = uid, bool(member), bool(admin)


_viewer: ContextVar = ContextVar("bookmarks_viewer", default=None)  # None: the server itself, which sees everything


def as_user(u: dict | None) -> Viewer:
    """The bookmarks read and changed from here on (this request) are this account's."""
    from iosuite_shared import users
    v = Viewer(u["id"] if u else None, users.is_member(u), users.is_admin(u))
    _viewer.set(v)
    return v


def viewer() -> Viewer | None:
    return _viewer.get()


def sees(r: dict, v: Viewer | None = None) -> bool:
    v = v or viewer()
    return v is None or bool(r["shared"]) or r["owner"] == v.uid


def may_change(r: dict, v: Viewer | None = None) -> bool:
    v = v or viewer()
    if v is None:
        return True
    return v.admin if r["shared"] else (v.member and r["owner"] == v.uid)


def _need(r: dict) -> None:
    if not may_change(r):
        raise NotAllowed("Only an admin of the start page changes the shared bookmarks" if r["shared"] else "This account can only read the bookmarks")


def _need_member() -> None:
    v = viewer()
    if v is not None and not v.member:
        raise NotAllowed("This account can only read the bookmarks")


# ------------------------------------------------------------------ the revision, the ids

@contextmanager
def writing():
    """One change to the tree: a transaction that moves the revision on (and, holding its row, keeps two writers from
    running at once). Nested calls share it. Yields the new revision."""
    if getattr(_w, "rev", None) is not None:
        yield _w.rev
        return
    with db.tx():
        db.ex("INSERT INTO prt_settings (name, value) VALUES ('bookmarks_rev', '1') ON DUPLICATE KEY UPDATE value = CAST(value AS UNSIGNED) + 1")
        _w.rev = int(db.one("SELECT value FROM prt_settings WHERE name = 'bookmarks_rev'")["value"])
        try:
            yield _w.rev
        finally:
            _w.rev = None


def revision() -> int:
    return int(db.get_setting("bookmarks_rev") or 0)


def highest_id() -> int:
    """The highest id ever handed out or seen from a sync client."""
    return int(db.get_setting("bookmarks_highest_id") or 0)


def saw_id(n: int) -> None:
    """A sync client used ids up to n: ours start after it."""
    db.ex("INSERT INTO prt_settings (name, value) VALUES ('bookmarks_highest_id', %s) ON DUPLICATE KEY UPDATE value = GREATEST(CAST(value AS UNSIGNED), %s)", (str(int(n)), int(n)))


def _new_id() -> int:
    db.ex("INSERT INTO prt_settings (name, value) VALUES ('bookmarks_highest_id', '1') ON DUPLICATE KEY UPDATE value = CAST(value AS UNSIGNED) + 1")
    return highest_id()


# ------------------------------------------------------------------ reading

_NODE = "SELECT n.*, i.etag FROM prt_bookmark_nodes n LEFT JOIN prt_bookmark_node_icons i ON i.node_id = n.id"


def tags_of(r: dict) -> list[str]:
    return [t for t in (r.get("tags") or "").split("\n") if t]


def clean_tags(tags) -> list[str]:
    out = []
    for t in tags or []:
        t = str(t).replace("\n", " ").strip()[:128]
        if t and t not in out:
            out.append(t)
    return out


def _own_starts(rows: list[dict], v: Viewer | None) -> list[dict]:
    """The shared rows with the viewer's own start page choice in `start` (and `ownStart` set) where they made one."""
    if v is None or v.uid is None or not any(r["shared"] for r in rows):
        return rows
    own = {r["node_id"]: r["start"] for r in db.q("SELECT node_id, start FROM prt_bookmark_starts WHERE user_id = %s", (v.uid,))}
    for r in rows:
        if r["shared"] and r["id"] in own:
            r["start"], r["ownStart"] = own[r["id"]], True
    return rows


class Tree:
    """The viewer's nodes (`everything`: all of them, whoever's), read once: `by` id, `kids` of a parent (None: the
    top) in order."""

    def __init__(self, everything: bool = False):
        v = None if everything else viewer()
        if v is None:
            self.rows = db.q(_NODE + " ORDER BY n.position, n.id")
        else:
            self.rows = _own_starts(db.q(_NODE + " WHERE n.shared = 1 OR n.owner <=> %s ORDER BY n.position, n.id", (v.uid,)), v)
        self.by = {r["id"]: r for r in self.rows}
        self.kids: dict = {}
        for r in self.rows:
            self.kids.setdefault(r["parent_id"] if r["parent_id"] in self.by else None, []).append(r)

    def children(self, pid) -> list[dict]:
        return self.kids.get(pid, [])

    def shown(self, r: dict) -> bool:
        """Whether a link is on the start page: its own choice, else its folder's; and only an address a page may link to."""
        if not _SHOWN.match(r["url"] or ""):
            return False
        if r["start"] is not None:
            return bool(r["start"])
        p = self.by.get(r["parent_id"])
        return bool(p and p["start"])

    def path(self, r: dict) -> list[str]:
        out = []
        while r:
            out.append(r["name"])
            r = self.by.get(r["parent_id"])
        return out[::-1]

    def below(self, nid: int) -> set:
        """The ids under a folder (itself included)."""
        out, todo = {nid}, [nid]
        while todo:
            for c in self.children(todo.pop()):
                out.add(c["id"])
                if c["folder"]:
                    todo.append(c["id"])
        return out


def _link(r: dict, shown: bool | None = None, sites: dict | None = None) -> dict:
    """A link as the page gets it. Its icon: the SVG uploaded for it (iconUrl), else its icon field, else the site's
    own (siteIcon, app/siteicons.py; `sites` is siteicons.known() when many links are read)."""
    d = {"id": r["id"], "groupId": r["parent_id"] or 0, "name": r["name"], "abbr": r["abbr"] or _abbr(r["name"], None), "href": r["url"],
         "description": r["description"] or (_host(r["url"])), "customDescription": r["description"] or "",
         "icon": r["icon"] or "", "iconUrl": f"api/bookmarks/links/{r['id']}/icon.svg?v={r['etag']}" if r.get("etag") else "",
         "tags": tags_of(r), "start": None if r["start"] is None else bool(r["start"]), "shared": bool(r["shared"]), "canChange": may_change(r)}
    d.update(siteicons.of(r["url"], sites) if not (d["iconUrl"] or d["icon"]) else {"siteIcon": "", "iconPending": False})
    if shown is not None:
        d["onStart"], d["linkable"] = shown, bool(_SHOWN.match(r["url"] or ""))
    return d


def _host(url: str) -> str:
    try:
        return urlsplit(url or "").hostname or ""
    except ValueError:
        return ""


def groups() -> list[dict]:
    """What the start page shows: every folder picked for it (and every folder holding a link picked on its own), in
    the tree's order, with the links shown. Links at the top level come first, as "Bookmarks"."""
    t, sites = Tree(), siteicons.known()
    out = []

    def walk(pid, folder):
        links = [_link(r, None, sites) for r in t.children(pid) if not r["folder"] and t.shown(r)]
        if links or (folder and folder["start"]):
            out.append({"id": folder["id"] if folder else 0, "name": folder["name"] if folder else "Bookmarks",
                        "path": t.path(folder) if folder else [], "links": links})
        for r in t.children(pid):
            if r["folder"]:
                walk(r["id"], r)

    walk(None, None)
    return out


def tree() -> dict:
    """Everything, nested, for the Bookmarks page: {rev, items: [folder {id, type, name, start, items} | link]}."""
    t, sites = Tree(), siteicons.known()

    def level(pid):
        return [{"id": r["id"], "type": "folder", "parentId": r["parent_id"] or 0, "name": r["name"], "start": bool(r["start"]),
                 "shared": bool(r["shared"]), "canChange": may_change(r), "items": level(r["id"])}
                if r["folder"] else {"type": "bookmark", **_link(r, t.shown(r), sites)} for r in t.children(pid)]

    v = viewer()
    return {"rev": revision(), "items": level(None), "count": sum(1 for r in t.rows if not r["folder"]),
            "canEdit": v is None or v.member, "canShare": v is None or v.admin}


def node(nid: int) -> dict:
    """A node the viewer sees (with their own start page choice on a shared one), or NotFound."""
    r = db.one(_NODE + " WHERE n.id = %s", (int(nid),))
    if not r or not sees(r):
        raise NotFound("No such bookmark or folder")
    return _own_starts([r], viewer())[0]


def _folder(pid) -> int | None:
    """The folder a parent id names (None, 0 and -1: the top), or NotFound."""
    if pid in (None, "", 0, -1, "0", "-1"):
        return None
    try:
        r = node(int(pid))
    except (TypeError, ValueError):
        raise NotFound("No such folder")
    if not r["folder"]:
        raise NotFound("No such folder")
    return r["id"]


def _to_top(nid: int, rev: int) -> None:
    db.ex("UPDATE prt_bookmark_nodes SET parent_id = NULL, position = %s, rev = %s WHERE id = %s", (_next_position(None), rev, nid))


def _others_inside(t: Tree, nid: int, v: Viewer | None) -> list[int]:
    """Under a shared folder: the topmost bookmarks of other people (their own, in it), which must not go with it."""
    if v is None:
        return []
    return [i for i in t.below(nid) if i != nid and not t.by[i]["shared"] and t.by[i]["owner"] != v.uid
            and t.by.get(t.by[i]["parent_id"], {}).get("shared")]


def _share(nid: int, rev: int) -> None:
    """Shared: the node, what of the viewer's is in it, and the folders it is in (a shared bookmark is only ever in a
    shared folder)."""
    v, t = viewer(), Tree(everything=True)
    mine = [i for i in t.below(nid) if t.by[i]["shared"] or v is None or t.by[i]["owner"] == v.uid]
    r = t.by.get(t.by[nid]["parent_id"])
    while r is not None:
        mine.append(r["id"])
        r = t.by.get(r["parent_id"])
    todo = [i for i in mine if not t.by[i]["shared"]]
    if todo:
        db.ex(f"UPDATE prt_bookmark_nodes SET shared = 1, rev = %s WHERE id IN ({', '.join(['%s'] * len(todo))})", (rev, *todo))


def _unshare(nid: int, rev: int) -> None:
    """The viewer's own again (an admin's): the node and the shared bookmarks in it. Other people's own bookmarks in
    it go to the top of their tree, where they still see them."""
    v, t = viewer(), Tree(everything=True)
    for i in _others_inside(t, nid, v):
        _to_top(i, rev)
    todo = [i for i in t.below(nid) if t.by[i]["shared"]]
    if todo:
        db.ex(f"UPDATE prt_bookmark_nodes SET shared = 0, owner = %s, rev = %s WHERE id IN ({', '.join(['%s'] * len(todo))})",
              (v.uid if v else None, rev, *todo))


def _set_own_start(r: dict, start) -> None:
    """Someone who does not manage the shared bookmarks takes a shared folder or link on or off their own start page."""
    v = viewer()
    if v is None or v.uid is None:
        raise NotAllowed("Sign in to choose what is on your start page")
    val = (1 if start else 0) if r["folder"] or start is not None else None
    db.ex("INSERT INTO prt_bookmark_starts (user_id, node_id, start) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE start = VALUES(start)",
          (v.uid, r["id"], val))


# ------------------------------------------------------------------ changing (the web app and the sync clients alike)

def _url(url: str, strict: bool) -> str:
    """strict: what is typed in Settings (a web or mailto: address). A sync client's: anything a browser keeps."""
    if strict:
        return _href(url)
    u = (url or "").strip()
    if not u:
        raise BadBookmark("A bookmark needs an address")
    if len(u) > URL_MAX:
        raise BadBookmark("That address is too long to keep")
    return u


def _next_position(pid) -> int:
    r = db.one("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM prt_bookmark_nodes WHERE parent_id <=> %s", (pid,))
    return int(r["n"])


def create(parent, folder: bool, name: str, url: str | None = None, *, tags=None, start=None, strict: bool = False,
           abbr=None, description=None, icon=None, nid: int | None = None) -> dict:
    """A new folder or link at the end of `parent` (None: the top). `nid`: the id a sync client's file gave it. It is
    the viewer's own; an admin's in a shared folder is shared, as the folder is."""
    v = viewer()
    with writing() as rev:
        pid = _folder(parent)
        _need_member()
        shared = 1 if pid is not None and node(pid)["shared"] and (v is None or v.admin) else 0
        name = (name or "").strip()[:NAME_MAX]
        if strict and not name:
            raise BadBookmark("A name for the group, please" if folder else "A name for the link, please")
        url = None if folder else _url(url, strict)
        if nid is None:
            nid = _new_id()
        else:
            saw_id(nid)
        db.ex("INSERT INTO prt_bookmark_nodes (id, parent_id, folder, name, url, abbr, description, icon, tags, start, position, rev, created_rev, owner, shared) "
              "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
              (nid, pid, 1 if folder else 0, name, url, None if folder else ((abbr or "").strip()[:4] or None),
               (description or "").strip()[:512] or None, (icon or "").strip()[:1024] or None, "\n".join(clean_tags(tags)) or None,
               (1 if start else 0) if folder else (None if start is None else (1 if start else 0)), _next_position(pid), rev, rev,
               v.uid if v else None, shared))
        return node(nid)


def change(nid: int, c: dict, strict: bool = False) -> dict:
    """Any of name, url, parent (a folder id; None: the top), tags, start, abbr, description, icon, shared (admins).
    A shared bookmark moved into a folder that is not shared is no longer shared."""
    v = viewer()
    r = node(nid)
    if c and set(c) <= {"start"} and r["shared"] and v is not None and not v.admin:
        _set_own_start(r, c["start"])  # their own start page; the tree itself does not change
        return node(nid)
    with writing() as rev:
        r = node(nid)
        _need(r)
        if "shared" in c and v is not None and not v.admin:
            raise NotAllowed("Only an admin of the start page shares bookmarks")
        share = None if "shared" not in c else bool(c["shared"])
        sets, args = ["rev = %s"], [rev]
        if "name" in c:
            name = (c["name"] or "").strip()[:NAME_MAX]
            if strict and not name:
                raise BadBookmark("A name for the group, please" if r["folder"] else "A name for the link, please")
            sets.append("name = %s"); args.append(name)
        if "url" in c and not r["folder"]:
            sets.append("url = %s"); args.append(_url(c["url"], strict))
        if "tags" in c and not r["folder"]:
            sets.append("tags = %s"); args.append("\n".join(clean_tags(c["tags"])) or None)
        if "start" in c:
            v = c["start"]
            sets.append("start = %s"); args.append((1 if v else 0) if r["folder"] or v is not None else None)
        for k, n in (("abbr", 4), ("description", 512), ("icon", 1024)):
            if k in c and not r["folder"]:
                sets.append(f"{k} = %s"); args.append((c[k] or "").strip()[:n] or None)
        if "parent" in c:
            pid = _folder(c["parent"])
            if pid != r["parent_id"]:
                if r["folder"] and pid is not None and pid in Tree().below(nid):
                    raise BadBookmark("A folder cannot go inside itself")
                sets += ["parent_id = %s", "position = %s"]; args += [pid, _next_position(pid)]
                if r["shared"] and pid is not None and not node(pid)["shared"] and share is None:
                    share = False
        db.ex(f"UPDATE prt_bookmark_nodes SET {', '.join(sets)} WHERE id = %s", (*args, nid))
        if share is True:
            _share(nid, rev)
        elif share is False and r["shared"]:
            _unshare(nid, rev)
        return node(nid)


def remove(nid: int) -> None:
    """A link, or a folder with everything in it (but other people's own bookmarks in a shared folder: those go to the
    top of their tree)."""
    with writing() as rev:
        r = node(nid)
        _need(r)
        if r["shared"] and r["folder"]:
            for i in _others_inside(Tree(everything=True), r["id"], viewer()):
                _to_top(i, rev)
        if not db.ex("DELETE FROM prt_bookmark_nodes WHERE id = %s", (int(nid),)):
            raise NotFound("No such bookmark or folder")


def order(parent, ids: list[int]) -> None:
    """The children of `parent` named in `ids` in that order, in the places they held; the children not named stay
    where they are. A node named from elsewhere moves in, after the last one named. What the viewer may not change (a
    shared bookmark, for someone who is not an admin) is left where it is, and so is what they do not see."""
    with writing() as rev:
        pid = _folder(parent)
        mine = Tree()
        ids = [int(i) for i in dict.fromkeys(ids) if int(i) in mine.by and may_change(mine.by[int(i)])]
        for i in ids:
            if pid is not None and mine.by[i]["folder"] and pid in mine.below(i):
                raise BadBookmark("A folder cannot go inside itself")
        moved = [i for i in ids if mine.by[i]["parent_id"] != pid]
        for i in moved:
            change(i, {"parent": pid})  # the rules of a move (a shared one into a folder that is not), at the end for now
        t = Tree(everything=True)
        now = [r["id"] for r in t.children(pid) if r["id"] not in moved]
        named, queue = set(ids), list(ids)
        out = []
        last = max((k for k, i in enumerate(now) if i in named), default=len(now) - 1)
        for k, i in enumerate(now):
            out.append(queue.pop(0) if i in named else i)
            if k == last:
                out += queue  # the ones that came from elsewhere (and whatever is left)
                queue = []
        out += queue
        for pos, i in enumerate(out):
            r = t.by[i]
            if r["position"] != pos or r["parent_id"] != pid:
                db.ex("UPDATE prt_bookmark_nodes SET position = %s, parent_id = %s, rev = %s WHERE id = %s", (pos, pid, rev, i))


# ------------------------------------------------------------------ the web app's calls (the Bookmarks page)

def _group_public(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "parentId": r["parent_id"] or 0, "start": bool(r["start"]), "links": [],
            "shared": bool(r["shared"]), "canChange": may_change(r)}


def add_group(name: str, parent=None, start: bool = True) -> dict:
    return _group_public(create(parent, True, name, start=start, strict=True))


def update_group(gid: int, c: dict) -> dict:
    if not node(gid)["folder"]:
        raise NotFound("No such group")
    ch = {k: c[k] for k in ("name", "start", "shared") if k in c}
    if "parentId" in c:
        ch["parent"] = c["parentId"]
    return _group_public(change(gid, ch, strict=True))


def delete_group(gid: int) -> None:
    if not node(gid)["folder"]:
        raise NotFound("No such group")
    remove(gid)


def add_link(gid, name: str, href: str, abbr: str | None = None, description: str | None = None, icon: str | None = None,
             start=None, tags=None) -> dict:
    name = (name or "").strip()
    r = create(gid, False, name, href, strict=True, abbr=_abbr(name, abbr) if name else None, description=description, icon=icon, start=start, tags=tags)
    return _link(r, Tree().shown(r))


def update_link(lid: int, changes: dict) -> dict:
    r = node(lid)
    if r["folder"]:
        raise NotFound("No such link")
    c = {}
    if "name" in changes:
        c["name"] = changes["name"]
    if "href" in changes and changes["href"] != r["url"]:  # an address a browser synced (javascript:…) may stay as it is
        c["url"] = changes["href"]
    if "abbr" in changes or "name" in changes:
        c["abbr"] = _abbr((changes.get("name") if "name" in changes else r["name"]) or "", changes.get("abbr") if "abbr" in changes else None)
    for k in ("description", "icon", "tags", "start", "shared"):
        if k in changes:
            c[k] = changes[k]
    if "groupId" in changes and changes["groupId"] is not None:
        c["parent"] = changes["groupId"]
    r = change(lid, c, strict=True)
    return _link(r, Tree().shown(r))


def delete_link(lid: int) -> None:
    if node(lid)["folder"]:
        raise NotFound("No such link")
    remove(lid)


def import_yaml(text: str, replace: bool = False) -> dict:
    """A homepage bookmarks.yaml: a list of {Group: [{Name: [{abbr, href, icon, description}]}]}. Groups with a name
    already at the top get the links added; replace=True empties the bookmarks first. Returns {groups, links} counts.
    What comes in is for the start page."""
    import yaml
    try:
        doc = yaml.safe_load(text or "")
    except yaml.YAMLError as e:
        raise BadBookmark(f"Not valid YAML: {str(e)[:200]}")
    if not isinstance(doc, list):
        raise BadBookmark("A homepage bookmarks.yaml is a list of groups")
    ng = nl = 0
    with writing():
        _need_member()
        if replace:  # the viewer's own, at the top (and what is in it)
            for r in Tree().children(None):
                if not r["shared"] and may_change(r):
                    remove(r["id"])
        existing = {g["name"].lower(): g["id"] for g in Tree().children(None) if g["folder"] and may_change(g)}
        for group in doc:
            if not isinstance(group, dict) or len(group) != 1:
                continue
            (gname, items), = group.items()
            gid = existing.get(str(gname).lower())
            if gid is None:
                gid = add_group(str(gname))["id"]
                existing[str(gname).lower()] = gid
                ng += 1
            else:
                change(gid, {"start": True})
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict) or len(item) != 1:
                    continue
                (lname, props), = item.items()
                p = props[0] if isinstance(props, list) and props and isinstance(props[0], dict) else props if isinstance(props, dict) else {}
                if not p.get("href"):
                    continue
                try:
                    add_link(gid, str(lname), str(p["href"]), p.get("abbr"), p.get("description"), p.get("icon"))
                    nl += 1
                except BadBookmark:
                    continue
    return {"groups": ng, "links": nl}


def add_items(parent, items: list[dict], start=None) -> list[dict]:
    """A parsed bookmarks file (app/bookmarkfiles.py: [{type, title, url?, tags?, children?}]) added under `parent`.
    Returns the same shape with the ids made. An address that cannot be kept is skipped."""
    out = []
    with writing():
        for it in items:
            try:
                if it["type"] == "folder":
                    r = create(parent, True, it.get("title") or "", start=bool(start))
                    out.append({"type": "folder", "id": r["id"], "title": r["name"], "children": add_items(r["id"], it.get("children") or [], start)})
                else:
                    r = create(parent, False, it.get("title") or "", it.get("url"), tags=it.get("tags"))
                    out.append({"type": "bookmark", "id": r["id"], "title": r["name"], "url": r["url"], "tags": tags_of(r)})
            except BadBookmark:
                continue
    return out


def claim_unowned() -> None:
    """Bookmarks nobody owns (made while there was no account) become the first admin's
    own: an admin shares what everyone should see."""
    if not db.one("SELECT id FROM prt_bookmark_nodes WHERE owner IS NULL AND shared = 0 LIMIT 1"):
        return
    from iosuite_shared import users
    from app import config
    admin = next((u for u in users.list_users(config.APP) if u.get("role") == "admin"), None)
    if admin:
        with writing():
            db.ex("UPDATE prt_bookmark_nodes SET owner = %s WHERE owner IS NULL AND shared = 0", (admin["id"],))


# ------------------------------------------------------------------ uploaded icons

ICON_MAX = 256 * 1024
_SVG_NS = "{http://www.w3.org/2000/svg}svg"
_UNSAFE = re.compile(r"<\s*(script|foreignObject|iframe|embed|object)\b|\bon[a-z]+\s*=|javascript:|<!ENTITY", re.I)


def clean_svg(data: bytes) -> str:
    """The SVG as it will be stored, or BadBookmark: well-formed XML with an <svg> root, no script, event handlers,
    external entities or embedded documents (it is shown in an <img>, which runs none of these, but the file is
    served from this origin, so a stray script never gets a chance)."""
    if not data:
        raise BadBookmark("Choose an .svg or .png file")
    if len(data) > ICON_MAX:
        raise BadBookmark(f"The icon is over {ICON_MAX // 1024} KB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise BadBookmark("Not an SVG or PNG file")
    if _UNSAFE.search(text):
        raise BadBookmark("The SVG contains a script, an event handler or an entity: those are not allowed")
    try:
        root = parse_xml(text)
    except (ET.ParseError, DefusedXmlException) as e:
        raise BadBookmark(f"Not a valid SVG: {str(e)[:120]}")
    if root.tag not in (_SVG_NS, "svg"):
        raise BadBookmark("Not an SVG file (the root element is not <svg>)")
    return text.strip()


_PNG = b"\x89PNG\r\n\x1a\n"


def png_as_svg(data: bytes) -> str:
    """An uploaded PNG as the SVG that is stored: the picture, inside an <svg> of its size. One kind of file is kept
    and served for a link's own icon (an SVG, which stays the better choice: sharp at any size), and a PNG rides in it."""
    if len(data) > ICON_MAX:
        raise BadBookmark(f"The icon is over {ICON_MAX // 1024} KB")
    if len(data) < 45 or data[12:16] != b"IHDR" or b"IEND" not in data[-16:]:
        raise BadBookmark("Not a valid PNG file")
    w, h = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if not (0 < w <= 4096 and 0 < h <= 4096):
        raise BadBookmark("The PNG is larger than 4096 px")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<image width="{w}" height="{h}" href="data:image/png;base64,{base64.b64encode(data).decode("ascii")}"/></svg>')


def set_icon(lid: int, data: bytes) -> dict:
    """Store the icon uploaded for a link (an SVG, or a PNG); returns the link."""
    _need(node(lid))
    if node(lid)["folder"]:
        raise NotFound("No such link")
    svg = png_as_svg(data) if data[:8] == _PNG else clean_svg(data)
    etag = hashlib.sha256(svg.encode("utf-8")).hexdigest()[:16]
    db.ex("INSERT INTO prt_bookmark_node_icons (node_id, svg, etag) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE svg = VALUES(svg), etag = VALUES(etag)",
          (lid, svg, etag))
    return _link(node(lid))


def clear_icon(lid: int) -> dict:
    _need(node(lid))
    db.ex("DELETE FROM prt_bookmark_node_icons WHERE node_id = %s", (lid,))
    return _link(node(lid))


def icon(lid: int) -> dict | None:
    """{svg, etag} of the uploaded icon, or None."""
    node(lid)
    return db.one("SELECT svg, etag FROM prt_bookmark_node_icons WHERE node_id = %s", (lid,))
