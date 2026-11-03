"""Notes, folders and tag colours: everything the web app and the Mac and iPhone apps read and change.

The apps keep an offline copy and send their changes when they can. Conflicts are settled per record by
`updated_at` (the time of the edit on the device that made it): the later edit wins, an older one is answered
with the record as the server has it, so the device takes that instead. Every change gets a new `rev`, and
GET /api/sync?since=<rev> hands a device everything that changed after the last rev it saw, tombstones of
deleted records included.

Every note, folder, tag colour and change-log line belongs to one account (owner: its id in the suite's auth
database); nobody sees or changes another account's notes. Who is asking is set per request (current_owner, by
app/main.py from the signed-in user, or the MCP server's account); every function here works on that account's
records only. Records made before any account existed (owner 0) go to the first admin (claim_unowned).

Text read from an image (OCR) is done on the device where it can be (Apple's Vision on the Mac and the iPhone)
and sent along as ocr_text; the server reads it itself (RapidOCR, app/ocr.py) only for notes made in the web app.
"""
import contextvars
import json
import re
import time
import uuid as uuidlib

from app import db

SOURCES = ("clipboard", "service", "screenshot", "manual", "web", "photo", "import", "share", "mcp")
COLORS = ("red", "orange", "yellow", "green", "mint", "teal", "blue", "indigo", "purple", "pink", "brown", "gray")
NOTE_COLS = ("uuid, title, body, ocr_text, source, source_app, created_at, updated_at, tags, pinned, folder_id, "
             "has_image, image_sha, deleted, rev, changed_by")
SORTS = {"updated": "updated_at DESC", "created": "created_at DESC", "oldest": "created_at ASC", "title": "lower(title) ASC, updated_at DESC"}
MAX_TEXT = 4 << 20  # 4 MB of text per field is more than any note needs
_UUID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


NOBODY = -1  # a visitor while accounts exist: no notes at all
current_owner = contextvars.ContextVar("ionotes_owner", default=0)


def owner() -> int:
    return current_owner.get()


class NotFound(LookupError):
    """No such record for this account (it may be another account's: that is never said)."""


class Stale(Exception):
    """The change is older than what the server has: the caller answers with the server's copy."""

    def __init__(self, current):
        self.current = current


def check_uuid(u: str) -> str:
    u = str(u or "").strip()
    if not _UUID.match(u):
        raise ValueError("A note, folder or tag id is 8 to 64 letters, digits or dashes")
    return u.upper() if len(u) == 36 else u


def new_uuid() -> str:
    return str(uuidlib.uuid4()).upper()  # the format Swift's UUID().uuidString gives, so ids look alike everywhere


def clean_tags(tags) -> list:
    """The same tidying as the apps (Note.cleanTags): trimmed, no leading #, no empties or duplicates (any case)."""
    if isinstance(tags, str):
        tags = [t for t in re.split(r"[,\n]", tags)]
    seen, out = set(), []
    for raw in tags or []:
        t = str(raw).strip()
        while t.startswith("#"):
            t = t[1:]
        t = t.strip()[:100]
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def _text(v, limit=MAX_TEXT) -> str:
    v = "" if v is None else str(v)
    return v[:limit]


def note_dict(r) -> dict:
    return {"id": r["uuid"], "title": r["title"], "body": r["body"], "ocrText": r["ocr_text"], "source": r["source"],
            "sourceApp": r["source_app"], "createdAt": r["created_at"], "updatedAt": r["updated_at"],
            "tags": json.loads(r["tags"] or "[]"), "pinned": bool(r["pinned"]), "folderID": r["folder_id"],
            "hasImage": bool(r["has_image"]), "imageSHA": r["image_sha"], "deleted": bool(r["deleted"]), "rev": r["rev"],
            "changedBy": r["changed_by"]}


def folder_dict(r) -> dict:
    return {"id": r["uuid"], "name": r["name"], "color": r["color"], "createdAt": r["created_at"], "updatedAt": r["updated_at"],
            "deleted": bool(r["deleted"]), "rev": r["rev"]}


def tag_dict(r) -> dict:
    return {"name": r["name"], "color": r["color"], "updatedAt": r["updated_at"], "deleted": bool(r["deleted"]), "rev": r["rev"]}


def log_change(con, user: str, action: str, kind: str, uid: str, summary: str):
    con.execute("INSERT INTO change_log (ts, user_name, action, kind, uuid, summary, owner) VALUES (?,?,?,?,?,?,?)",
                (int(time.time()), user, action, kind, uid, summary[:300], owner()))


_claimed = False


def claim_unowned(first_admin_id) -> int:
    """Records made before any account existed (owner 0) become the first admin's; once accounts exist nothing new
    is made without one. Returns how many notes moved."""
    global _claimed
    if _claimed or not first_admin_id:
        return 0
    with db.tx() as con:
        n = con.execute("SELECT count(*) FROM notes WHERE owner = 0").fetchone()[0]
        for t in ("notes", "folders", "tag_colors", "change_log"):
            con.execute(f"UPDATE {t} SET owner = ? WHERE owner = 0", (int(first_admin_id),))
    _claimed = True
    return int(n)


def display_title(n: dict) -> str:
    """What the apps show as a note's title (Note.displayTitle)."""
    for text in (n.get("title"), n.get("body"), n.get("ocrText")):
        line = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), None)
        if line:
            return line[:80]
    return "Image" if n.get("hasImage") else "Untitled"


# ---- notes
def get_note(uid: str, con=None):
    own = con is None
    con = con or db.connect()
    try:
        r = con.execute(f"SELECT {NOTE_COLS} FROM notes WHERE uuid = ? AND owner = ?", (check_uuid(uid), owner())).fetchone()
        return note_dict(r) if r else None
    finally:
        if own:
            con.close()


def _search_clause(con, q: str):
    """(sql, params) matching every word of q (prefix match) in the title, text, text in the image or tags.
    MariaDB: its FULLTEXT index in boolean mode; words shorter than InnoDB's smallest indexed token, and
    SQLite, fall back to LIKE."""
    words = [w for w in re.findall(r"[\w'’.@-]+", q.lower()) if w.strip("'’.@-")]
    if not words:
        return "", []
    clauses, params, ft = [], [], []
    for w in words[:12]:
        core = re.sub(r"[^\w]", " ", w).split()
        if con.mysql and core and all(len(c) >= 3 for c in core):
            ft.extend("+" + c + "*" for c in core)
        else:
            like = "%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            clauses.append("(lower(title) LIKE ? ESCAPE '\\\\' OR lower(body) LIKE ? ESCAPE '\\\\' OR lower(ocr_text) LIKE ? ESCAPE '\\\\' OR lower(tags) LIKE ? ESCAPE '\\\\')"
                           if con.mysql else
                           "(lower(title) LIKE ? ESCAPE '\\' OR lower(body) LIKE ? ESCAPE '\\' OR lower(ocr_text) LIKE ? ESCAPE '\\' OR lower(tags) LIKE ? ESCAPE '\\')")
            params += [like] * 4
    if ft:
        clauses.insert(0, "MATCH (title, body, ocr_text, tags) AGAINST (? IN BOOLEAN MODE)")
        params.insert(0, " ".join(ft))
    return " AND ".join(clauses), params


def list_notes(q: str = "", folder: str = None, tag: str = None, pinned: bool = None, image: bool = None,
               sort: str = "updated", limit: int = 200, offset: int = 0, source: str = None) -> dict:
    """A page of notes, pinned first, then by sort. folder: an id, or "none" for notes in no folder."""
    where, params = ["owner = ?", "deleted = 0"], [owner()]
    with db.connect() as con:
        if q and q.strip():
            s, p = _search_clause(con, q)
            if s:
                where.append(s)
                params += p
        if folder == "none":
            where.append("folder_id IS NULL")
        elif folder:
            where.append("folder_id = ?")
            params.append(check_uuid(folder))
        if tag:
            # tags is a JSON list: the quoted name, matched without case
            where.append("lower(tags) LIKE ?")
            params.append('%"' + json.dumps(tag.strip().lower())[1:-1].replace("%", "") + '"%')
        if pinned is not None:
            where.append("pinned = ?")
            params.append(1 if pinned else 0)
        if image is not None:
            where.append("has_image = ?")
            params.append(1 if image else 0)
        if source:
            where.append("source = ?")
            params.append(source)
        w = " AND ".join(where)
        total = con.execute(f"SELECT count(*) FROM notes WHERE {w}", params).fetchone()[0]
        order = SORTS.get(sort, SORTS["updated"])
        rows = con.execute(f"SELECT {NOTE_COLS} FROM notes WHERE {w} ORDER BY pinned DESC, {order} LIMIT ? OFFSET ?",
                           params + [max(1, min(int(limit), 1000)), max(0, int(offset))]).fetchall()
    out = [note_dict(r) for r in rows]
    if tag:  # the LIKE above is a prefilter; exact (case-insensitive) membership here
        t = tag.strip().lower()
        out = [n for n in out if t in (x.lower() for x in n["tags"])]
    return {"notes": out, "total": total}


def save_note(uid: str, data: dict, user: str, force: bool = False) -> dict:
    """Create or update a note from the fields given (camelCase as the API serves them). The edit's time is
    data["updatedAt"] (a device's own clock) or now; an edit older than the stored one raises Stale."""
    uid = check_uuid(uid) if uid else new_uuid()
    now = time.time()
    with db.tx() as con:
        cur = con.execute(f"SELECT {NOTE_COLS}, owner FROM notes WHERE uuid = ?", (uid,)).fetchone()
        if cur and cur["owner"] != owner():
            raise NotFound("No such note")  # another account's id: refused without saying so
        old = note_dict(cur) if cur else None
        ts = float(data.get("updatedAt") or now)
        if old and not force and ts < old["updatedAt"]:
            raise Stale(old)
        base = old or {"title": "", "body": "", "ocrText": "", "source": "manual", "sourceApp": None, "createdAt": now,
                       "tags": [], "pinned": False, "folderID": None, "hasImage": False, "imageSHA": None, "deleted": False}
        n = dict(base)
        for k in ("title", "body", "sourceApp"):
            if k in data:
                n[k] = _text(data[k], 1000 if k != "body" else MAX_TEXT) if data[k] is not None else (None if k == "sourceApp" else "")
        if "ocrText" in data and (data["ocrText"] or not base.get("ocrText")):  # an empty ocrText never erases text read earlier
            n["ocrText"] = _text(data["ocrText"])
        if "source" in data:
            n["source"] = str(data["source"] or "manual")[:32]
        if "createdAt" in data and data["createdAt"]:
            n["createdAt"] = float(data["createdAt"])
        if "tags" in data:
            n["tags"] = clean_tags(data["tags"])
        if "pinned" in data:
            n["pinned"] = bool(data["pinned"])
        if "folderID" in data:
            n["folderID"] = check_uuid(data["folderID"]) if data["folderID"] else None
            if n["folderID"] and not con.execute("SELECT 1 FROM folders WHERE uuid = ? AND owner = ?", (n["folderID"], owner())).fetchone():
                # a folder this account doesn't have (yet: a device may send the note before its folder) stays as sent
                # only when no other account owns that id
                if con.execute("SELECT 1 FROM folders WHERE uuid = ?", (n["folderID"],)).fetchone():
                    n["folderID"] = None
        if "deleted" in data:
            n["deleted"] = bool(data["deleted"])
        rev = db.next_rev(con)
        vals = (n["title"], n["body"], n["ocrText"], n["source"], n["sourceApp"], n["createdAt"], ts, json.dumps(n["tags"], ensure_ascii=False),
                1 if n["pinned"] else 0, n["folderID"], 1 if n["hasImage"] else 0, n["imageSHA"], 1 if n["deleted"] else 0, rev, user)
        if old:
            con.execute("UPDATE notes SET title=?, body=?, ocr_text=?, source=?, source_app=?, created_at=?, updated_at=?, tags=?, pinned=?, "
                        "folder_id=?, has_image=?, image_sha=?, deleted=?, rev=?, changed_by=? WHERE uuid=?", vals + (uid,))
        else:
            con.execute(f"INSERT INTO notes ({NOTE_COLS}, owner) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (uid,) + vals + (owner(),))
        if n["deleted"] and n["hasImage"]:
            con.execute("DELETE FROM note_images WHERE uuid = ?", (uid,))
            con.execute("UPDATE notes SET has_image = 0, image_sha = NULL WHERE uuid = ?", (uid,))
        action = "delete" if n["deleted"] and not (old and old["deleted"]) else ("create" if not old or old["deleted"] else "edit")
        log_change(con, user, action, "note", uid, display_title(n))
        return get_note(uid, con)


def delete_note(uid: str, user: str, ts: float = None) -> dict:
    return save_note(uid, {"deleted": True, "updatedAt": ts or time.time()}, user, force=ts is None)


def restore_note(uid: str, user: str) -> dict:
    return save_note(uid, {"deleted": False, "updatedAt": time.time()}, user, force=True)


def trash(limit: int = 200) -> list:
    """Notes deleted in the last 30 days (their text is kept; an image goes with the delete)."""
    with db.connect() as con:
        rows = con.execute(f"SELECT {NOTE_COLS} FROM notes WHERE owner = ? AND deleted = 1 AND updated_at > ? ORDER BY updated_at DESC LIMIT ?",
                           (owner(), time.time() - 30 * 86400, limit)).fetchall()
    return [note_dict(r) for r in rows]


def set_ocr_text(uid: str, text: str):
    """Text the server read from a web note's image: stored with a new rev, the note's edit time unchanged."""
    with db.tx() as con:
        con.execute("UPDATE notes SET ocr_text = ?, rev = ? WHERE uuid = ? AND (ocr_text = '' OR ocr_text IS NULL)",
                    (_text(text), db.next_rev(con), uid))


# ---- folders
def list_folders(include_deleted: bool = False) -> list:
    with db.connect() as con:
        rows = con.execute("SELECT f.uuid, f.name, f.color, f.created_at, f.updated_at, f.deleted, f.rev, "
                           "(SELECT count(*) FROM notes n WHERE n.folder_id = f.uuid AND n.deleted = 0 AND n.owner = f.owner) AS count "
                           f"FROM folders f WHERE f.owner = ? {'' if include_deleted else 'AND f.deleted = 0'} ORDER BY lower(f.name)", (owner(),)).fetchall()
    return [{**folder_dict(r), "count": r["count"]} for r in rows]


def save_folder(uid: str, data: dict, user: str, force: bool = False) -> dict:
    uid = check_uuid(uid) if uid else new_uuid()
    now = time.time()
    with db.tx() as con:
        r = con.execute("SELECT uuid, name, color, created_at, updated_at, deleted, rev, owner FROM folders WHERE uuid = ?", (uid,)).fetchone()
        if r and r["owner"] != owner():
            raise NotFound("No such folder")
        old = folder_dict(r) if r else None
        ts = float(data.get("updatedAt") or now)
        if old and not force and ts < old["updatedAt"]:
            raise Stale(old)
        f = dict(old or {"name": "", "color": None, "createdAt": now, "deleted": False})
        if "name" in data:
            f["name"] = _text(data["name"], 255).strip()
        if "color" in data:
            f["color"] = data["color"] if data["color"] in COLORS else None
        if "createdAt" in data and data["createdAt"]:
            f["createdAt"] = float(data["createdAt"])
        if "deleted" in data:
            f["deleted"] = bool(data["deleted"])
        if not f["deleted"] and not f["name"]:
            raise ValueError("A folder needs a name")
        rev = db.next_rev(con)
        if old:
            con.execute("UPDATE folders SET name=?, color=?, created_at=?, updated_at=?, deleted=?, rev=? WHERE uuid=?",
                        (f["name"], f["color"], f["createdAt"], ts, 1 if f["deleted"] else 0, rev, uid))
        else:
            con.execute("INSERT INTO folders (uuid, name, color, created_at, updated_at, deleted, rev, owner) VALUES (?,?,?,?,?,?,?,?)",
                        (uid, f["name"], f["color"], f["createdAt"], ts, 1 if f["deleted"] else 0, rev, owner()))
        if f["deleted"] and not (old and old["deleted"]):
            # its notes stay, in no folder (what the apps do when a folder is deleted)
            for (nid,) in con.execute("SELECT uuid FROM notes WHERE folder_id = ? AND owner = ?", (uid, owner())).fetchall():
                con.execute("UPDATE notes SET folder_id = NULL, rev = ?, updated_at = ? WHERE uuid = ?", (db.next_rev(con), max(ts, now), nid))
        log_change(con, user, "delete" if f["deleted"] else ("create" if not old else "edit"), "folder", uid, f["name"])
        r = con.execute("SELECT uuid, name, color, created_at, updated_at, deleted, rev FROM folders WHERE uuid = ?", (uid,)).fetchone()
        return folder_dict(r)


# ---- tags
def tag_key(name: str) -> str:
    return name.strip().lower()[:191]


def list_tags() -> list:
    """Every tag on a note, with its count and colour, by name."""
    counts, names = {}, {}
    with db.connect() as con:
        for (tags,) in con.execute("SELECT tags FROM notes WHERE owner = ? AND deleted = 0 AND tags != '[]'", (owner(),)).fetchall():
            for t in json.loads(tags or "[]"):
                k = tag_key(t)
                counts[k] = counts.get(k, 0) + 1
                names.setdefault(k, t)
        colors = {r["tag_key"]: r for r in con.execute("SELECT tag_key, name, color FROM tag_colors WHERE owner = ? AND deleted = 0", (owner(),)).fetchall()}
    return sorted([{"name": names[k], "count": c, "color": colors[k]["color"] if k in colors else None} for k, c in counts.items()],
                  key=lambda t: t["name"].lower())


def tag_colors(include_deleted: bool = False) -> list:
    with db.connect() as con:
        rows = con.execute(f"SELECT tag_key, name, color, updated_at, deleted, rev FROM tag_colors WHERE owner = ? {'' if include_deleted else 'AND deleted = 0'}",
                           (owner(),)).fetchall()
    return [tag_dict(r) for r in rows]


def set_tag_color(name: str, color, user: str, ts: float = None, force: bool = False) -> dict:
    name = _text(name, 191).strip().lstrip("#").strip()
    if not name:
        raise ValueError("A tag needs a name")
    k = tag_key(name)
    ts = float(ts or time.time())
    color = color if color in COLORS else None
    with db.tx() as con:
        r = con.execute("SELECT tag_key, name, color, updated_at, deleted, rev FROM tag_colors WHERE owner = ? AND tag_key = ?", (owner(), k)).fetchone()
        if r and not force and ts < r["updated_at"]:
            raise Stale(tag_dict(r))
        rev = db.next_rev(con)
        con.execute("INSERT OR REPLACE INTO tag_colors (owner, tag_key, name, color, updated_at, deleted, rev) VALUES (?,?,?,?,?,?,?)",
                    (owner(), k, name, color, ts, 0 if color else 1, rev))
        log_change(con, user, "color", "tag", k, f"{name}: {color or 'no colour'}")
        r = con.execute("SELECT tag_key, name, color, updated_at, deleted, rev FROM tag_colors WHERE owner = ? AND tag_key = ?", (owner(), k)).fetchone()
        return tag_dict(r)


def rename_tag(old: str, new: str, user: str) -> int:
    """Rename a tag on every note (merging into an existing one of that name); returns how many notes changed."""
    ok, new = tag_key(old), clean_tags([new])
    if not new:
        raise ValueError("The new name is empty")
    new = new[0]
    now, changed = time.time(), 0
    with db.tx() as con:
        for r in con.execute("SELECT uuid, tags FROM notes WHERE owner = ? AND deleted = 0 AND lower(tags) LIKE ?", (owner(), '%' + json.dumps(ok)[1:-1] + '%')).fetchall():
            tags = json.loads(r["tags"] or "[]")
            if not any(tag_key(t) == ok for t in tags):
                continue
            tags = clean_tags([new if tag_key(t) == ok else t for t in tags])
            con.execute("UPDATE notes SET tags = ?, updated_at = ?, rev = ?, changed_by = ? WHERE uuid = ?",
                        (json.dumps(tags, ensure_ascii=False), now, db.next_rev(con), user, r["uuid"]))
            changed += 1
        log_change(con, user, "rename", "tag", ok, f"{old} → {new} ({changed} notes)")
    return changed


def remove_tag(name: str, user: str) -> int:
    """Take a tag off every note."""
    k, now, changed = tag_key(name), time.time(), 0
    with db.tx() as con:
        for r in con.execute("SELECT uuid, tags FROM notes WHERE owner = ? AND deleted = 0 AND lower(tags) LIKE ?", (owner(), '%' + json.dumps(k)[1:-1] + '%')).fetchall():
            tags = json.loads(r["tags"] or "[]")
            keep = [t for t in tags if tag_key(t) != k]
            if len(keep) == len(tags):
                continue
            con.execute("UPDATE notes SET tags = ?, updated_at = ?, rev = ?, changed_by = ? WHERE uuid = ?",
                        (json.dumps(keep, ensure_ascii=False), now, db.next_rev(con), user, r["uuid"]))
            changed += 1
        log_change(con, user, "remove", "tag", k, f"{name} ({changed} notes)")
    return changed


# ---- overview and sync
def meta() -> dict:
    """What the sidebar shows: counts, folders, tags, and the current rev."""
    with db.connect() as con:
        o = owner()
        total, pinned, images = con.execute("SELECT count(*), coalesce(sum(pinned), 0), coalesce(sum(has_image), 0) FROM notes WHERE owner = ? AND deleted = 0", (o,)).fetchone()
        nofolder = con.execute("SELECT count(*) FROM notes WHERE owner = ? AND deleted = 0 AND folder_id IS NULL", (o,)).fetchone()[0]
        trashed = con.execute("SELECT count(*) FROM notes WHERE owner = ? AND deleted = 1 AND updated_at > ?", (o, time.time() - 30 * 86400)).fetchone()[0]
    return {"total": int(total), "pinned": int(pinned), "images": int(images), "noFolder": int(nofolder), "trash": int(trashed),
            "folders": list_folders(), "tags": list_tags(), "rev": db.current_rev()}


def changes(since: int, limit: int = 500) -> dict:
    """Everything changed after rev `since`, oldest change first, at most `limit` notes per call; `more` says to
    ask again with since=rev. Image bytes are fetched separately (imageSHA tells a device when to)."""
    since = max(0, int(since))
    limit = max(1, min(int(limit), 2000))
    with db.connect() as con:
        o = owner()
        rows = con.execute(f"SELECT {NOTE_COLS} FROM notes WHERE owner = ? AND rev > ? ORDER BY rev LIMIT ?", (o, since, limit + 1)).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        upto = rows[-1]["rev"] if more else None
        fq = "SELECT uuid, name, color, created_at, updated_at, deleted, rev FROM folders WHERE owner = ? AND rev > ?"
        tq = "SELECT tag_key, name, color, updated_at, deleted, rev FROM tag_colors WHERE owner = ? AND rev > ?"
        fp, tp = [o, since], [o, since]
        if upto is not None:
            fq += " AND rev <= ?"
            tq += " AND rev <= ?"
            fp.append(upto)
            tp.append(upto)
        folders = [folder_dict(r) for r in con.execute(fq + " ORDER BY rev", fp).fetchall()]
        tags = [tag_dict(r) for r in con.execute(tq + " ORDER BY rev", tp).fetchall()]
        rev = upto if upto is not None else int(con.execute("SELECT max(rev) FROM change_counter").fetchone()[0] or 0)
    return {"rev": rev, "more": more, "notes": [note_dict(r) for r in rows], "folders": folders, "tags": tags, "serverTime": time.time()}


def change_log(limit: int = 200, before: int = None) -> list:
    with db.connect() as con:
        q, p = "SELECT id, ts, user_name, action, kind, uuid, summary FROM change_log WHERE owner = ?", [owner()]
        if before:
            q += " AND id < ?"
            p.append(int(before))
        rows = con.execute(q + " ORDER BY id DESC LIMIT ?", p + [max(1, min(int(limit), 1000))]).fetchall()
    return [{"id": r[0], "ts": r[1], "user": r[2], "action": r[3], "kind": r[4], "uuid": r[5], "summary": r[6]} for r in rows]
