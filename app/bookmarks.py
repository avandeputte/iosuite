"""Bookmarks on the start page, as homepage (gethomepage.dev) lays them out: groups of links, each link with a name, a
two-letter abbreviation or an icon, the address and a line under it (the host name unless a description is given).
One set for the whole family; editors and admins change it, in Settings › Bookmarks, or by importing a homepage
bookmarks.yaml.
"""
import re
from urllib.parse import urlsplit

from app import db


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
    h = (href or "").strip()
    if not re.match(r"^[a-z][a-z0-9+.-]*://", h, re.I):
        h = "https://" + h if h else ""
    if not h or not urlsplit(h).netloc:
        raise BadBookmark("The link needs an address, like https://example.com")
    return h[:2048]


def _public(r: dict) -> dict:
    return {"id": r["id"], "groupId": r["group_id"], "name": r["name"], "abbr": r["abbr"], "href": r["href"],
            "description": r["description"] or (urlsplit(r["href"]).hostname or ""), "customDescription": r["description"] or "",
            "icon": r["icon"] or ""}


def groups() -> list[dict]:
    """Every group with its links, in order."""
    gs = db.q("SELECT * FROM bookmark_groups ORDER BY sort, id")
    links = db.q("SELECT * FROM bookmarks ORDER BY group_id, sort, id")
    by: dict[int, list] = {}
    for r in links:
        by.setdefault(r["group_id"], []).append(_public(r))
    return [{"id": g["id"], "name": g["name"], "links": by.get(g["id"], [])} for g in gs]


def _group(gid: int) -> dict:
    g = db.one("SELECT * FROM bookmark_groups WHERE id = %s", (gid,))
    if not g:
        raise BadBookmark("No such group")
    return g


def add_group(name: str) -> dict:
    name = (name or "").strip()[:128]
    if not name:
        raise BadBookmark("A name for the group, please")
    sort = (db.one("SELECT COALESCE(MAX(sort), -1) + 1 AS n FROM bookmark_groups") or {}).get("n", 0)
    gid = db.ex("INSERT INTO bookmark_groups (name, sort) VALUES (%s, %s)", (name, sort))
    return {"id": gid, "name": name, "links": []}


def rename_group(gid: int, name: str) -> None:
    _group(gid)
    name = (name or "").strip()[:128]
    if not name:
        raise BadBookmark("A name for the group, please")
    db.ex("UPDATE bookmark_groups SET name = %s WHERE id = %s", (name, gid))


def delete_group(gid: int) -> None:
    _group(gid)
    db.ex("DELETE FROM bookmark_groups WHERE id = %s", (gid,))


def order_groups(ids: list[int]) -> None:
    """The groups in this order (ids left out keep their place after these)."""
    with db.tx():
        for i, gid in enumerate(ids):
            db.ex("UPDATE bookmark_groups SET sort = %s WHERE id = %s", (i, int(gid)))
        rest = [g["id"] for g in db.q("SELECT id FROM bookmark_groups ORDER BY sort, id") if g["id"] not in [int(x) for x in ids]]
        for i, gid in enumerate(rest, start=len(ids)):
            db.ex("UPDATE bookmark_groups SET sort = %s WHERE id = %s", (i, gid))


def add_link(gid: int, name: str, href: str, abbr: str | None = None, description: str | None = None, icon: str | None = None) -> dict:
    _group(gid)
    name = (name or "").strip()[:128]
    if not name:
        raise BadBookmark("A name for the link, please")
    href = _href(href)
    sort = (db.one("SELECT COALESCE(MAX(sort), -1) + 1 AS n FROM bookmarks WHERE group_id = %s", (gid,)) or {}).get("n", 0)
    lid = db.ex("INSERT INTO bookmarks (group_id, name, abbr, href, description, icon, sort) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (gid, name, _abbr(name, abbr), href, (description or "").strip()[:512] or None, (icon or "").strip()[:1024] or None, sort))
    return _public(db.one("SELECT * FROM bookmarks WHERE id = %s", (lid,)))


def update_link(lid: int, changes: dict) -> dict:
    r = db.one("SELECT * FROM bookmarks WHERE id = %s", (lid,))
    if not r:
        raise BadBookmark("No such link")
    name = (changes.get("name") if "name" in changes else r["name"]) or ""
    name = name.strip()[:128]
    if not name:
        raise BadBookmark("A name for the link, please")
    href = _href(changes["href"]) if "href" in changes else r["href"]
    abbr = _abbr(name, changes.get("abbr")) if ("abbr" in changes or "name" in changes) else r["abbr"]
    desc = ((changes.get("description") or "").strip()[:512] or None) if "description" in changes else r["description"]
    icon = ((changes.get("icon") or "").strip()[:1024] or None) if "icon" in changes else r["icon"]
    gid = int(changes["groupId"]) if changes.get("groupId") else r["group_id"]
    if gid != r["group_id"]:
        _group(gid)
    db.ex("UPDATE bookmarks SET name = %s, href = %s, abbr = %s, description = %s, icon = %s, group_id = %s WHERE id = %s",
          (name, href, abbr, desc, icon, gid, lid))
    return _public(db.one("SELECT * FROM bookmarks WHERE id = %s", (lid,)))


def delete_link(lid: int) -> None:
    if not db.ex("DELETE FROM bookmarks WHERE id = %s", (lid,)):
        raise BadBookmark("No such link")


def order_links(gid: int, ids: list[int]) -> None:
    """The links of a group in this order; a link named from another group moves into this one."""
    _group(gid)
    with db.tx():
        for i, lid in enumerate(ids):
            db.ex("UPDATE bookmarks SET sort = %s, group_id = %s WHERE id = %s", (i, gid, int(lid)))
        rest = [r["id"] for r in db.q("SELECT id FROM bookmarks WHERE group_id = %s ORDER BY sort, id", (gid,)) if r["id"] not in [int(x) for x in ids]]
        for i, lid in enumerate(rest, start=len(ids)):
            db.ex("UPDATE bookmarks SET sort = %s WHERE id = %s", (i, lid))


def import_yaml(text: str, replace: bool = False) -> dict:
    """A homepage bookmarks.yaml: a list of {Group: [{Name: [{abbr, href, icon, description}]}]}. Groups with a name
    already here get the links added; replace=True empties the bookmarks first. Returns {groups, links} counts."""
    import yaml
    try:
        doc = yaml.safe_load(text or "")
    except yaml.YAMLError as e:
        raise BadBookmark(f"Not valid YAML: {str(e)[:200]}")
    if not isinstance(doc, list):
        raise BadBookmark("A homepage bookmarks.yaml is a list of groups")
    ng = nl = 0
    with db.tx():
        if replace:
            db.ex("DELETE FROM bookmark_groups")
        existing = {g["name"].lower(): g["id"] for g in db.q("SELECT id, name FROM bookmark_groups")}
        for group in doc:
            if not isinstance(group, dict) or len(group) != 1:
                continue
            (gname, items), = group.items()
            gid = existing.get(str(gname).lower())
            if gid is None:
                gid = add_group(str(gname))["id"]
                existing[str(gname).lower()] = gid
                ng += 1
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
