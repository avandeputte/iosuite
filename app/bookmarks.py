"""Bookmarks on the start page, as homepage (gethomepage.dev) lays them out: groups of links, each link with a name, a
two-letter abbreviation or an icon, the address and a line under it (the host name unless a description is given).
One set for the whole family; editors and admins change it, in Settings › Bookmarks, or by importing a homepage
bookmarks.yaml. An icon is an address or a dashboard-icons name in the link's icon field, or an SVG uploaded for the
link and kept in the database (prt_bookmark_icons), which the page serves itself.
"""
import hashlib
import re
import xml.etree.ElementTree as ET

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_xml  # an uploaded file: no entity expansion or external entities
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


def _public(r: dict) -> dict:
    return {"id": r["id"], "groupId": r["group_id"], "name": r["name"], "abbr": r["abbr"], "href": r["url"],
            "description": r["description"] or (urlsplit(r["url"]).hostname or ""), "customDescription": r["description"] or "",
            "icon": r["icon"] or "", "iconUrl": f"api/bookmarks/links/{r['id']}/icon.svg?v={r['etag']}" if r.get("etag") else ""}


_LINK = "SELECT b.*, i.etag FROM prt_bookmarks b LEFT JOIN prt_bookmark_icons i ON i.bookmark_id = b.id"


def groups() -> list[dict]:
    """Every group with its links, in order."""
    gs = db.q("SELECT * FROM prt_bookmark_groups ORDER BY position, id")
    links = db.q(_LINK + " ORDER BY b.group_id, b.position, b.id")
    by: dict[int, list] = {}
    for r in links:
        by.setdefault(r["group_id"], []).append(_public(r))
    return [{"id": g["id"], "name": g["name"], "links": by.get(g["id"], [])} for g in gs]


def _group(gid: int) -> dict:
    g = db.one("SELECT * FROM prt_bookmark_groups WHERE id = %s", (gid,))
    if not g:
        raise BadBookmark("No such group")
    return g


def add_group(name: str) -> dict:
    name = (name or "").strip()[:128]
    if not name:
        raise BadBookmark("A name for the group, please")
    sort = (db.one("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM prt_bookmark_groups") or {}).get("n", 0)
    gid = db.ex("INSERT INTO prt_bookmark_groups (name, position) VALUES (%s, %s)", (name, sort))
    return {"id": gid, "name": name, "links": []}


def rename_group(gid: int, name: str) -> None:
    _group(gid)
    name = (name or "").strip()[:128]
    if not name:
        raise BadBookmark("A name for the group, please")
    db.ex("UPDATE prt_bookmark_groups SET name = %s WHERE id = %s", (name, gid))


def delete_group(gid: int) -> None:
    _group(gid)
    db.ex("DELETE FROM prt_bookmark_groups WHERE id = %s", (gid,))


def order_groups(ids: list[int]) -> None:
    """The groups in this order (ids left out keep their place after these)."""
    with db.tx():
        for i, gid in enumerate(ids):
            db.ex("UPDATE prt_bookmark_groups SET position = %s WHERE id = %s", (i, int(gid)))
        rest = [g["id"] for g in db.q("SELECT id FROM prt_bookmark_groups ORDER BY position, id") if g["id"] not in [int(x) for x in ids]]
        for i, gid in enumerate(rest, start=len(ids)):
            db.ex("UPDATE prt_bookmark_groups SET position = %s WHERE id = %s", (i, gid))


def add_link(gid: int, name: str, href: str, abbr: str | None = None, description: str | None = None, icon: str | None = None) -> dict:
    _group(gid)
    name = (name or "").strip()[:128]
    if not name:
        raise BadBookmark("A name for the link, please")
    href = _href(href)
    sort = (db.one("SELECT COALESCE(MAX(position), -1) + 1 AS n FROM prt_bookmarks WHERE group_id = %s", (gid,)) or {}).get("n", 0)
    lid = db.ex("INSERT INTO prt_bookmarks (group_id, name, abbr, url, description, icon, position) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (gid, name, _abbr(name, abbr), href, (description or "").strip()[:512] or None, (icon or "").strip()[:1024] or None, sort))
    return _public(db.one(_LINK + " WHERE b.id = %s", (lid,)))


def update_link(lid: int, changes: dict) -> dict:
    r = db.one("SELECT * FROM prt_bookmarks WHERE id = %s", (lid,))
    if not r:
        raise BadBookmark("No such link")
    name = (changes.get("name") if "name" in changes else r["name"]) or ""
    name = name.strip()[:128]
    if not name:
        raise BadBookmark("A name for the link, please")
    href = _href(changes["href"]) if "href" in changes else r["url"]
    abbr = _abbr(name, changes.get("abbr")) if ("abbr" in changes or "name" in changes) else r["abbr"]
    desc = ((changes.get("description") or "").strip()[:512] or None) if "description" in changes else r["description"]
    icon = ((changes.get("icon") or "").strip()[:1024] or None) if "icon" in changes else r["icon"]
    gid = int(changes["groupId"]) if changes.get("groupId") else r["group_id"]
    if gid != r["group_id"]:
        _group(gid)
    db.ex("UPDATE prt_bookmarks SET name = %s, url = %s, abbr = %s, description = %s, icon = %s, group_id = %s WHERE id = %s",
          (name, href, abbr, desc, icon, gid, lid))
    return _public(db.one(_LINK + " WHERE b.id = %s", (lid,)))


def delete_link(lid: int) -> None:
    if not db.ex("DELETE FROM prt_bookmarks WHERE id = %s", (lid,)):
        raise BadBookmark("No such link")


def order_links(gid: int, ids: list[int]) -> None:
    """The links of a group in this order; a link named from another group moves into this one."""
    _group(gid)
    with db.tx():
        for i, lid in enumerate(ids):
            db.ex("UPDATE prt_bookmarks SET position = %s, group_id = %s WHERE id = %s", (i, gid, int(lid)))
        rest = [r["id"] for r in db.q("SELECT id FROM prt_bookmarks WHERE group_id = %s ORDER BY position, id", (gid,)) if r["id"] not in [int(x) for x in ids]]
        for i, lid in enumerate(rest, start=len(ids)):
            db.ex("UPDATE prt_bookmarks SET position = %s WHERE id = %s", (i, lid))


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
            db.ex("DELETE FROM prt_bookmark_groups")
        existing = {g["name"].lower(): g["id"] for g in db.q("SELECT id, name FROM prt_bookmark_groups")}
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


# ------------------------------------------------------------------ uploaded icons

ICON_MAX = 256 * 1024
_SVG_NS = "{http://www.w3.org/2000/svg}svg"
_UNSAFE = re.compile(r"<\s*(script|foreignObject|iframe|embed|object)\b|\bon[a-z]+\s*=|javascript:|<!ENTITY", re.I)


def clean_svg(data: bytes) -> str:
    """The SVG as it will be stored, or BadBookmark: well-formed XML with an <svg> root, no script, event handlers,
    external entities or embedded documents (it is shown in an <img>, which runs none of these, but the file is
    served from this origin, so a stray script never gets a chance)."""
    if not data:
        raise BadBookmark("Choose an .svg file")
    if len(data) > ICON_MAX:
        raise BadBookmark(f"The icon is over {ICON_MAX // 1024} KB")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise BadBookmark("Not an SVG file (not UTF-8 text)")
    if _UNSAFE.search(text):
        raise BadBookmark("The SVG contains a script, an event handler or an entity: those are not allowed")
    try:
        root = parse_xml(text)
    except (ET.ParseError, DefusedXmlException) as e:
        raise BadBookmark(f"Not a valid SVG: {str(e)[:120]}")
    if root.tag not in (_SVG_NS, "svg"):
        raise BadBookmark("Not an SVG file (the root element is not <svg>)")
    return text.strip()


def set_icon(lid: int, data: bytes) -> dict:
    """Store the uploaded SVG for a link; returns the link."""
    if not db.one("SELECT id FROM prt_bookmarks WHERE id = %s", (lid,)):
        raise BadBookmark("No such link")
    svg = clean_svg(data)
    etag = hashlib.sha256(svg.encode("utf-8")).hexdigest()[:16]
    db.ex("INSERT INTO prt_bookmark_icons (bookmark_id, svg, etag) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE svg = VALUES(svg), etag = VALUES(etag)",
          (lid, svg, etag))
    return _public(db.one(_LINK + " WHERE b.id = %s", (lid,)))


def clear_icon(lid: int) -> dict:
    if not db.one("SELECT id FROM prt_bookmarks WHERE id = %s", (lid,)):
        raise BadBookmark("No such link")
    db.ex("DELETE FROM prt_bookmark_icons WHERE bookmark_id = %s", (lid,))
    return _public(db.one(_LINK + " WHERE b.id = %s", (lid,)))


def icon(lid: int) -> dict | None:
    """{svg, etag} of the uploaded icon, or None."""
    return db.one("SELECT svg, etag FROM prt_bookmark_icons WHERE bookmark_id = %s", (lid,))
