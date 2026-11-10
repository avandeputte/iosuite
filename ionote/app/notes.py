"""Notes, folders and tag colours: everything the web app and the Mac and iPhone apps read and change.

The apps keep an offline copy and send their changes when they can. Conflicts are settled per record by
`updated_at` (the time of the edit on the device that made it, never later than the server's clock): the later edit
wins, an older one is answered with the record as the server has it, so the device takes that instead. Every change gets a new `rev`, and
GET /api/sync?since=<rev> hands a device everything that changed after the last rev it saw, tombstones of
deleted records included.

Every note, folder, tag colour and change-log line belongs to one account (user_id: its id in the suite's auth
database); nobody sees or changes another account's notes. Who is asking is set per request (current_owner, by
app/main.py from the signed-in user, or the MCP server's account); every function here works on that account's
records only. Records made while the install was open, before any account existed, have user_id 0.

Text read from an image (OCR) is done on the device where it can be (Apple's Vision on the Mac and the iPhone)
and sent along as ocr_text; the server reads it itself (RapidOCR, app/ocr.py) only for notes made in the web app.

A note in the trash (deleted = 1) is kept for 30 days, then purged (deleted = 2): its text, tags, picture and
attachments go, and only the tombstone stays, so a device that has not synced since still learns it was deleted.
"""
import contextvars
import json
import logging
import re
import time
import uuid as uuidlib
from datetime import datetime, timedelta

from app import config, db
from iosuite_shared.errors import Invalid

SOURCES = ("clipboard", "service", "screenshot", "manual", "web", "photo", "import", "share", "mcp")
COLORS = ("red", "orange", "yellow", "green", "mint", "teal", "blue", "indigo", "purple", "pink", "brown", "gray")
NOTE_COLS = ("uuid, title, body, ocr_text, source, source_app, created_at, updated_at, tags, pinned, folder_id, "
             "has_image, image_sha, deleted, rev, changed_by")
SORTS = {"updated": "updated_at DESC", "created": "created_at DESC", "oldest": "created_at ASC", "title": "lower(title) ASC, updated_at DESC"}
MAX_TEXT = 4 << 20  # 4 MB of text per field is more than any note needs
_UUID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
TRASH_DAYS = 30
PURGED = 2  # nts_notes.deleted: 1 in the trash, 2 purged (a tombstone with nothing in it)
log = logging.getLogger("app.notes")


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
        raise Invalid("A note, folder or tag id is 8 to 64 letters, digits or dashes")
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
    con.execute("INSERT INTO nts_change_log (created_at, user_name, action, kind, uuid, summary, user_id) VALUES (?,?,?,?,?,?,?)",
                (int(time.time()), user, action, kind, uid, summary[:300], owner()))


def display_title(n: dict) -> str:
    """What the apps show as a note's title (Note.displayTitle)."""
    for text in (n.get("title"), n.get("body"), n.get("ocrText")):
        line = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), None)
        if line:
            return line[:80]
    return "Image" if n.get("hasImage") else "Untitled"


def edit_time(value, now: float) -> float:
    """When an edit was made: the device's own clock (updatedAt), never later than the server's. A device whose clock
    runs ahead would otherwise win every conflict, for as long as its clock is ahead."""
    try:
        ts = float(value or now)
    except (TypeError, ValueError):
        return now
    return ts if 0 < ts <= now else now  # not a number, or infinite: now as well


# ---- notes
def get_note(uid: str, con=None):
    own = con is None
    con = con or db.connect()
    try:
        r = con.execute(f"SELECT {NOTE_COLS} FROM nts_notes WHERE uuid = ? AND user_id = ?", (check_uuid(uid), owner())).fetchone()
        return with_attachments(con, [note_dict(r)])[0] if r else None
    finally:
        if own:
            con.close()


ATTACHMENT_COLS = "uuid, note_uuid, name, mime, size_bytes, sha, width, height, created_at"


def attachment_dict(r) -> dict:
    return {"id": r["uuid"], "name": r["name"], "mime": r["mime"], "bytes": r["size_bytes"], "sha": r["sha"],
            "width": r["width"], "height": r["height"], "createdAt": r["created_at"]}


def with_attachments(con, out: list) -> list:
    """Each note with the list of its attachments (no bytes: GET /api/notes/<id>/attachments/<aid> has those)."""
    if not out:
        return out
    by = {n["id"]: n for n in out}
    for n in out:
        n["attachments"] = []
    ids = list(by)
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        rows = con.execute(f"SELECT {ATTACHMENT_COLS} FROM nts_attachments WHERE note_uuid IN ({','.join('?' * len(part))}) AND user_id = ? "
                           "ORDER BY created_at, uuid", part + [owner()]).fetchall()
        for r in rows:
            by[r["note_uuid"]]["attachments"].append(attachment_dict(r))
    return out


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
    # or every word in one of its attachments (a PDF's text, its file name)
    aclauses, aparams = [], []
    for w in words[:12]:
        core = re.sub(r"[^\w]", " ", w).split()
        if con.mysql and core and all(len(c) >= 3 for c in core):
            aclauses.append("MATCH (a.name, a.text) AGAINST (? IN BOOLEAN MODE)")
            aparams.append(" ".join("+" + c + "*" for c in core))
        else:
            like = "%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            esc = "'\\\\'" if con.mysql else "'\\'"
            aclauses.append(f"(lower(a.name) LIKE ? ESCAPE {esc} OR lower(a.text) LIKE ? ESCAPE {esc})")
            aparams += [like, like]
    sql = ("((" + " AND ".join(clauses) + ") OR EXISTS (SELECT 1 FROM nts_attachments a WHERE a.note_uuid = nts_notes.uuid AND a.user_id = nts_notes.user_id AND "
           + " AND ".join(aclauses) + "))")
    return sql, params + aparams


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _tag_clause(con, name: str):
    """(sql, param) for notes whose tags (a JSON list) hold this tag, without case: a prefilter that never misses
    one and, with % _ and \\ escaped, takes in no other tag either, so counts are right."""
    quoted = json.dumps(tag_key(name), ensure_ascii=False)  # as the tags are stored: "café", "a\\b"
    return ("lower(tags) LIKE ? ESCAPE '\\\\'" if con.mysql else "lower(tags) LIKE ? ESCAPE '\\'"), "%" + _like_escape(quoted) + "%"


def list_notes(q: str = "", folder: str = None, tag: str = None, pinned: bool = None, image: bool = None,
               sort: str = "updated", limit: int = 200, offset: int = 0, source: str = None,
               created_from: float = None, created_before: float = None) -> dict:
    """A page of notes, pinned first, then by sort. folder: an id, or "none" for notes in no folder;
    created_from / created_before: a range of creation times (seconds; the end left out)."""
    where, params = ["user_id = ?", "deleted = 0"], [owner()]
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
            c, p = _tag_clause(con, tag)
            where.append(c)
            params.append(p)
        if pinned is not None:
            where.append("pinned = ?")
            params.append(1 if pinned else 0)
        if image is not None:
            where.append("has_image = ?")
            params.append(1 if image else 0)
        if source:
            where.append("source = ?")
            params.append(source)
        if created_from is not None:
            where.append("created_at >= ?")
            params.append(float(created_from))
        if created_before is not None:
            where.append("created_at < ?")
            params.append(float(created_before))
        w = " AND ".join(where)
        total = con.execute(f"SELECT count(*) FROM nts_notes WHERE {w}", params).fetchone()[0]
        order = SORTS.get(sort, SORTS["updated"])
        rows = con.execute(f"SELECT {NOTE_COLS} FROM nts_notes WHERE {w} ORDER BY pinned DESC, {order} LIMIT ? OFFSET ?",
                           params + [max(1, min(int(limit), 1000)), max(0, int(offset))]).fetchall()
        out = with_attachments(con, [note_dict(r) for r in rows])
    if tag:  # the LIKE above is a prefilter; exact (case-insensitive) membership here
        t = tag.strip().lower()
        out = [n for n in out if t in (x.lower() for x in n["tags"])]
    return {"notes": out, "total": total}


def save_note(uid: str, data: dict, user: str, force: bool = False) -> dict:
    """Create or update a note from the fields given (camelCase as the API serves them). The edit's time is
    data["updatedAt"] (a device's own clock, see edit_time) or now; an edit older than the stored one raises Stale."""
    uid = check_uuid(uid) if uid else new_uuid()
    now = time.time()
    with db.tx() as con:
        cur = con.execute(f"SELECT {NOTE_COLS}, user_id FROM nts_notes WHERE uuid = ?", (uid,)).fetchone()
        if cur and cur["user_id"] != owner():
            raise NotFound("No such note")  # another account's id: refused without saying so
        old = note_dict(cur) if cur else None
        ts = edit_time(data.get("updatedAt"), now)
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
            if n["folderID"] and not con.execute("SELECT 1 FROM nts_folders WHERE uuid = ? AND user_id = ?", (n["folderID"], owner())).fetchone():
                # a folder this account doesn't have (yet: a device may send the note before its folder) stays as sent
                # only when no other account owns that id
                if con.execute("SELECT 1 FROM nts_folders WHERE uuid = ?", (n["folderID"],)).fetchone():
                    n["folderID"] = None
        if "deleted" in data:
            n["deleted"] = bool(data["deleted"])
        rev = db.next_rev(con)
        # a purged tombstone stays purged unless the edit brings the note back
        dval = (PURGED if cur and cur["deleted"] == PURGED else 1) if n["deleted"] else 0
        vals = (n["title"], n["body"], n["ocrText"], n["source"], n["sourceApp"], n["createdAt"], ts, json.dumps(n["tags"], ensure_ascii=False),
                1 if n["pinned"] else 0, n["folderID"], 1 if n["hasImage"] else 0, n["imageSHA"], dval, rev, user)
        if old:
            con.execute("UPDATE nts_notes SET title=?, body=?, ocr_text=?, source=?, source_app=?, created_at=?, updated_at=?, tags=?, pinned=?, "
                        "folder_id=?, has_image=?, image_sha=?, deleted=?, rev=?, changed_by=? WHERE uuid=?", vals + (uid,))
        else:
            con.execute(f"INSERT INTO nts_notes ({NOTE_COLS}, user_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (uid,) + vals + (owner(),))
        if n["deleted"] and n["hasImage"]:
            con.execute("DELETE FROM nts_note_images WHERE uuid = ?", (uid,))
            con.execute("UPDATE nts_notes SET has_image = 0, image_sha = NULL WHERE uuid = ?", (uid,))
        action = "delete" if n["deleted"] and not (old and old["deleted"]) else ("create" if not old or old["deleted"] else "edit")
        log_change(con, user, action, "note", uid, display_title(n))
        return get_note(uid, con)


def delete_note(uid: str, user: str, ts: float = None) -> dict:
    return save_note(uid, {"deleted": True, "updatedAt": ts or time.time()}, user, force=ts is None)


def restore_note(uid: str, user: str) -> dict:
    with db.connect() as con:
        r = con.execute("SELECT deleted FROM nts_notes WHERE uuid = ? AND user_id = ?", (check_uuid(uid), owner())).fetchone()
    if not r or r[0] == PURGED:
        raise NotFound("No such note (notes are kept in the trash for 30 days)")
    return save_note(uid, {"deleted": False, "updatedAt": time.time()}, user, force=True)


def trash(limit: int = 200) -> list:
    """The notes in the trash, newest delete first (their text is kept; an image goes with the delete, attachments
    stay until the note is purged)."""
    with db.connect() as con:
        rows = con.execute(f"SELECT {NOTE_COLS} FROM nts_notes WHERE user_id = ? AND deleted = 1 ORDER BY updated_at DESC LIMIT ?",
                           (owner(), limit)).fetchall()
        return with_attachments(con, [note_dict(r) for r in rows])


def _purge_rows(con, uids: list) -> int:
    """Empty these notes out for good: text, tags, picture and attachments go, the tombstone stays (deleted = 2) with
    a new rev, so every device drops the note too."""
    for uid in uids:
        con.execute("DELETE FROM nts_note_images WHERE uuid = ?", (uid,))
        con.execute("DELETE FROM nts_attachments WHERE note_uuid = ?", (uid,))
        con.execute("UPDATE nts_notes SET title = '', body = '', ocr_text = '', tags = '[]', pinned = 0, folder_id = NULL, has_image = 0, "
                    "image_sha = NULL, source_app = NULL, deleted = ?, rev = ? WHERE uuid = ?", (PURGED, db.next_rev(con), uid))
    return len(uids)


def empty_trash(user: str, uid: str = None) -> int:
    """Delete forever: every note in this account's trash, or the one with this id. Returns how many went."""
    with db.tx() as con:
        if uid:
            rows = con.execute("SELECT uuid, title, body FROM nts_notes WHERE uuid = ? AND user_id = ? AND deleted = 1", (check_uuid(uid), owner())).fetchall()
            if not rows:
                raise NotFound("That note is not in the trash")
        else:
            rows = con.execute("SELECT uuid, title, body FROM nts_notes WHERE user_id = ? AND deleted = 1", (owner(),)).fetchall()
        n = _purge_rows(con, [r["uuid"] for r in rows])
        if n:
            log_change(con, user, "purge", "note", uid or "", display_title({"title": rows[0]["title"], "body": rows[0]["body"]}) if uid else f"emptied the trash ({n} notes)")
        return n


def purge_expired(days: int = TRASH_DAYS) -> int:
    """Every account's notes that have been in the trash longer than `days`: purged (the background job, daily)."""
    with db.tx() as con:
        rows = con.execute("SELECT uuid FROM nts_notes WHERE deleted = 1 AND updated_at < ?", (time.time() - days * 86400,)).fetchall()
        return _purge_rows(con, [r[0] for r in rows])


def housekeeping() -> None:
    """What the server does on its own, a few times a day: the notes that have been in the trash for TRASH_DAYS are
    purged, and what deletions left behind KEEP_DELETED_DAYS ago goes."""
    n = purge_expired()
    if n:
        log.info("purged %d notes that were in the trash for more than %d days", n, TRASH_DAYS)
    purge_deleted()


def set_ocr_text(uid: str, text: str, sha: str):
    """Text the server read from a web note's picture (the one with this sha: not one replaced since), stored with
    a new rev and the note's edit time unchanged. Runs on the OCR thread, for whichever account owns the note."""
    with db.tx() as con:
        if con.execute("SELECT 1 FROM nts_notes WHERE uuid = ? AND image_sha = ? AND (ocr_text = '' OR ocr_text IS NULL)", (uid, sha)).fetchone():
            con.execute("UPDATE nts_notes SET ocr_text = ?, rev = ? WHERE uuid = ?", (_text(text), db.next_rev(con), uid))


# ---- folders
def list_folders(include_deleted: bool = False) -> list:
    with db.connect() as con:
        rows = con.execute("SELECT f.uuid, f.name, f.color, f.created_at, f.updated_at, f.deleted, f.rev, "
                           "(SELECT count(*) FROM nts_notes n WHERE n.folder_id = f.uuid AND n.deleted = 0 AND n.user_id = f.user_id) AS count "
                           f"FROM nts_folders f WHERE f.user_id = ? {'' if include_deleted else 'AND f.deleted = 0'} ORDER BY lower(f.name)", (owner(),)).fetchall()
    return [{**folder_dict(r), "count": r["count"]} for r in rows]


def save_folder(uid: str, data: dict, user: str, force: bool = False) -> dict:
    uid = check_uuid(uid) if uid else new_uuid()
    now = time.time()
    with db.tx() as con:
        r = con.execute("SELECT uuid, name, color, created_at, updated_at, deleted, rev, user_id FROM nts_folders WHERE uuid = ?", (uid,)).fetchone()
        if r and r["user_id"] != owner():
            raise NotFound("No such folder")
        old = folder_dict(r) if r else None
        ts = edit_time(data.get("updatedAt"), now)
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
            raise Invalid("A folder needs a name")
        rev = db.next_rev(con)
        if old:
            con.execute("UPDATE nts_folders SET name=?, color=?, created_at=?, updated_at=?, deleted=?, rev=? WHERE uuid=?",
                        (f["name"], f["color"], f["createdAt"], ts, 1 if f["deleted"] else 0, rev, uid))
        else:
            con.execute("INSERT INTO nts_folders (uuid, name, color, created_at, updated_at, deleted, rev, user_id) VALUES (?,?,?,?,?,?,?,?)",
                        (uid, f["name"], f["color"], f["createdAt"], ts, 1 if f["deleted"] else 0, rev, owner()))
        if f["deleted"] and not (old and old["deleted"]):
            # its notes stay, in no folder (what the apps do when a folder is deleted)
            for (nid,) in con.execute("SELECT uuid FROM nts_notes WHERE folder_id = ? AND user_id = ?", (uid, owner())).fetchall():
                con.execute("UPDATE nts_notes SET folder_id = NULL, rev = ?, updated_at = ? WHERE uuid = ?", (db.next_rev(con), max(ts, now), nid))
        log_change(con, user, "delete" if f["deleted"] else ("create" if not old else "edit"), "folder", uid, f["name"])
        r = con.execute("SELECT uuid, name, color, created_at, updated_at, deleted, rev FROM nts_folders WHERE uuid = ?", (uid,)).fetchone()
        return folder_dict(r)


# ---- tags
def tag_key(name: str) -> str:
    return name.strip().lower()[:191]


_tags_seen = {}  # account -> (its rev, its tags): the sidebar asks on every refresh, the answer changes with a rev


def list_tags(rev: int = None) -> list:
    """Every tag on a note, with its count and colour, by name. rev: the account's rev as the caller just read it
    (owner_rev); while that has not moved, the tags counted for it are still the answer."""
    hit = _tags_seen.get(owner())
    if rev is not None and hit and hit[0] == rev:
        return [dict(t) for t in hit[1]]
    out = _count_tags()
    if rev is not None:
        _tags_seen[owner()] = (rev, [dict(t) for t in out])
    return out


def _count_tags() -> list:
    counts, names = {}, {}
    with db.connect() as con:
        for (tags,) in con.execute("SELECT tags FROM nts_notes WHERE user_id = ? AND deleted = 0 AND tags != '[]'", (owner(),)).fetchall():
            for t in json.loads(tags or "[]"):
                k = tag_key(t)
                counts[k] = counts.get(k, 0) + 1
                names.setdefault(k, t)
        colors = {r["tag_key"]: r for r in con.execute("SELECT tag_key, name, color FROM nts_tag_colors WHERE user_id = ? AND deleted = 0", (owner(),)).fetchall()}
    return sorted([{"name": names[k], "count": c, "color": colors[k]["color"] if k in colors else None} for k, c in counts.items()],
                  key=lambda t: t["name"].lower())


def tag_colors(include_deleted: bool = False) -> list:
    with db.connect() as con:
        rows = con.execute(f"SELECT tag_key, name, color, updated_at, deleted, rev FROM nts_tag_colors WHERE user_id = ? {'' if include_deleted else 'AND deleted = 0'}",
                           (owner(),)).fetchall()
    return [tag_dict(r) for r in rows]


def set_tag_color(name: str, color, user: str, ts: float = None, force: bool = False) -> dict:
    name = _text(name, 191).strip().lstrip("#").strip()
    if not name:
        raise Invalid("A tag needs a name")
    k = tag_key(name)
    ts = edit_time(ts, time.time())
    color = color if color in COLORS else None
    with db.tx() as con:
        r = con.execute("SELECT tag_key, name, color, updated_at, deleted, rev FROM nts_tag_colors WHERE user_id = ? AND tag_key = ?", (owner(), k)).fetchone()
        if r and not force and ts < r["updated_at"]:
            raise Stale(tag_dict(r))
        rev = db.next_rev(con)
        con.execute("INSERT OR REPLACE INTO nts_tag_colors (user_id, tag_key, name, color, updated_at, deleted, rev) VALUES (?,?,?,?,?,?,?)",
                    (owner(), k, name, color, ts, 0 if color else 1, rev))
        log_change(con, user, "color", "tag", k, f"{name}: {color or 'no colour'}")
        r = con.execute("SELECT tag_key, name, color, updated_at, deleted, rev FROM nts_tag_colors WHERE user_id = ? AND tag_key = ?", (owner(), k)).fetchone()
        return tag_dict(r)


def rename_tag(old: str, new: str, user: str) -> int:
    """Rename a tag on every note (merging into an existing one of that name); returns how many notes changed."""
    ok, new = tag_key(old), clean_tags([new])
    if not new:
        raise Invalid("The new name is empty")
    new = new[0]
    now, changed = time.time(), 0
    with db.tx() as con:
        c, p = _tag_clause(con, ok)
        for r in con.execute(f"SELECT uuid, tags FROM nts_notes WHERE user_id = ? AND deleted = 0 AND {c}", (owner(), p)).fetchall():
            tags = json.loads(r["tags"] or "[]")
            if not any(tag_key(t) == ok for t in tags):
                continue
            tags = clean_tags([new if tag_key(t) == ok else t for t in tags])
            con.execute("UPDATE nts_notes SET tags = ?, updated_at = ?, rev = ?, changed_by = ? WHERE uuid = ?",
                        (json.dumps(tags, ensure_ascii=False), now, db.next_rev(con), user, r["uuid"]))
            changed += 1
        nk = tag_key(new)
        if nk != ok:  # the colour goes with the name, unless the tag it merges into has one of its own
            mine = con.execute("SELECT color FROM nts_tag_colors WHERE user_id = ? AND tag_key = ? AND deleted = 0", (owner(), ok)).fetchone()
            if mine:
                if not con.execute("SELECT 1 FROM nts_tag_colors WHERE user_id = ? AND tag_key = ? AND deleted = 0", (owner(), nk)).fetchone():
                    con.execute("INSERT OR REPLACE INTO nts_tag_colors (user_id, tag_key, name, color, updated_at, deleted, rev) VALUES (?,?,?,?,?,0,?)",
                                (owner(), nk, new, mine["color"], now, db.next_rev(con)))
                _drop_tag_color(con, ok, now)
        log_change(con, user, "rename", "tag", ok, f"{old} → {new} ({changed} notes)")
    return changed


def _drop_tag_color(con, k: str, now: float):
    """A tag colour as a tombstone (the devices sync that too)."""
    con.execute("UPDATE nts_tag_colors SET color = NULL, deleted = 1, updated_at = ?, rev = ? WHERE user_id = ? AND tag_key = ? AND deleted = 0",
                (now, db.next_rev(con), owner(), k))


def remove_tag(name: str, user: str) -> int:
    """Take a tag off every note."""
    k, now, changed = tag_key(name), time.time(), 0
    with db.tx() as con:
        c, p = _tag_clause(con, k)
        for r in con.execute(f"SELECT uuid, tags FROM nts_notes WHERE user_id = ? AND deleted = 0 AND {c}", (owner(), p)).fetchall():
            tags = json.loads(r["tags"] or "[]")
            keep = [t for t in tags if tag_key(t) != k]
            if len(keep) == len(tags):
                continue
            con.execute("UPDATE nts_notes SET tags = ?, updated_at = ?, rev = ?, changed_by = ? WHERE uuid = ?",
                        (json.dumps(keep, ensure_ascii=False), now, db.next_rev(con), user, r["uuid"]))
            changed += 1
        _drop_tag_color(con, k, now)
        log_change(con, user, "remove", "tag", k, f"{name} ({changed} notes)")
    return changed


# ---- overview and sync
def meta() -> dict:
    """What the sidebar shows: counts, folders, tags, and the current rev."""
    with db.connect() as con:
        o = owner()
        total, pinned, images = con.execute("SELECT count(*), coalesce(sum(pinned), 0), coalesce(sum(has_image), 0) FROM nts_notes WHERE user_id = ? AND deleted = 0", (o,)).fetchone()
        nofolder = con.execute("SELECT count(*) FROM nts_notes WHERE user_id = ? AND deleted = 0 AND folder_id IS NULL", (o,)).fetchone()[0]
        trashed = con.execute("SELECT count(*) FROM nts_notes WHERE user_id = ? AND deleted = 1", (o,)).fetchone()[0]
    rev = owner_rev()
    return {"total": int(total), "pinned": int(pinned), "images": int(images), "noFolder": int(nofolder), "trash": int(trashed),
            "folders": list_folders(), "tags": list_tags(rev), "templates": list_templates(), "rev": rev}


def owner_rev() -> int:
    """The latest rev among this account's notes, folders and tag colours: it moves when (and only when) something
    this account sees changes; the server-wide counter would also tell of other accounts' edits."""
    with db.connect() as con:
        return max(int(con.execute(f"SELECT coalesce(max(rev), 0) FROM {t} WHERE user_id = ?", (owner(),)).fetchone()[0])
                   for t in ("nts_notes", "nts_folders", "nts_tag_colors", "nts_templates"))


def changes(since: int, limit: int = 500) -> dict:
    """Everything changed after rev `since`, oldest change first, at most `limit` notes per call; `more` says to
    ask again with since=rev. Image bytes are fetched separately (imageSHA tells a device when to)."""
    since = max(0, int(since))
    limit = max(1, min(int(limit), 2000))
    with db.connect() as con:
        o = owner()
        # the head first, and nothing past it: a change committed while this runs is left for the next call, not
        # skipped (each statement may see a newer database than the one before; writers commit in rev order)
        head = int(con.execute("SELECT max(rev) FROM nts_change_counter").fetchone()[0] or 0)
        rows = con.execute(f"SELECT {NOTE_COLS} FROM nts_notes WHERE user_id = ? AND rev > ? AND rev <= ? ORDER BY rev LIMIT ?",
                           (o, since, head, limit + 1)).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        upto = rows[-1]["rev"] if more else head
        p = (o, since, upto)
        folders = [folder_dict(r) for r in con.execute("SELECT uuid, name, color, created_at, updated_at, deleted, rev FROM nts_folders "
                                                       "WHERE user_id = ? AND rev > ? AND rev <= ? ORDER BY rev", p).fetchall()]
        tags = [tag_dict(r) for r in con.execute("SELECT tag_key, name, color, updated_at, deleted, rev FROM nts_tag_colors "
                                                 "WHERE user_id = ? AND rev > ? AND rev <= ? ORDER BY rev", p).fetchall()]
        templates = [template_dict(r) for r in con.execute(f"SELECT {TEMPLATE_COLS} FROM nts_templates WHERE user_id = ? AND rev > ? AND rev <= ? ORDER BY rev", p).fetchall()]
        rev = upto
        out = with_attachments(con, [note_dict(r) for r in rows])
    return {"rev": rev, "more": more, "notes": out, "folders": folders, "tags": tags, "templates": templates, "serverTime": time.time()}


def purge_deleted(days: int = None) -> dict:
    """What a deletion leaves behind, removed once it is older than `days` (KEEP_DELETED_DAYS): the names of deleted
    folders (the markers stay, empty, so a device that syncs later still learns of the deletion), the change log's
    entries of that age, and the change counter's used numbers. All accounts at once. A deleted note's text goes
    sooner, with the trash (purge_expired)."""
    before = time.time() - (config.KEEP_DELETED_DAYS if days is None else days) * 86400
    with db.tx() as con:
        f = con.execute("UPDATE nts_folders SET name = '', color = NULL WHERE deleted = 1 AND updated_at < ? AND name != ''", (before,)).rowcount
        c = con.execute("DELETE FROM nts_change_log WHERE created_at < ?", (int(before),)).rowcount
        head = con.execute("SELECT max(rev) FROM nts_change_counter").fetchone()[0]
        if head:  # the counter only ever needs its newest row (the next rev follows it)
            con.execute("DELETE FROM nts_change_counter WHERE rev < ?", (head,))
    return {"folders": f, "changes": c}


def change_log(limit: int = 200, before: int = None) -> list:
    with db.connect() as con:
        q, p = "SELECT id, created_at, user_name, action, kind, uuid, summary FROM nts_change_log WHERE user_id = ?", [owner()]
        if before:
            q += " AND id < ?"
            p.append(int(before))
        rows = con.execute(q + " ORDER BY id DESC LIMIT ?", p + [max(1, min(int(limit), 1000))]).fetchall()
    return [{"id": r[0], "ts": r[1], "user": r[2], "action": r[3], "kind": r[4], "uuid": r[5], "summary": r[6]} for r in rows]


# ---- templates
TEMPLATE_COLS = "uuid, name, title, body, tags, folder_id, created_at, updated_at, deleted, rev"


def template_dict(r) -> dict:
    return {"id": r["uuid"], "name": r["name"], "title": r["title"], "body": r["body"], "tags": json.loads(r["tags"] or "[]"),
            "folderID": r["folder_id"], "createdAt": r["created_at"], "updatedAt": r["updated_at"], "deleted": bool(r["deleted"]), "rev": r["rev"]}


def list_templates(include_deleted: bool = False) -> list:
    with db.connect() as con:
        rows = con.execute(f"SELECT {TEMPLATE_COLS} FROM nts_templates WHERE user_id = ? {'' if include_deleted else 'AND deleted = 0'} ORDER BY lower(name)",
                           (owner(),)).fetchall()
    return [template_dict(r) for r in rows]


def get_template(uid: str):
    with db.connect() as con:
        r = con.execute(f"SELECT {TEMPLATE_COLS} FROM nts_templates WHERE uuid = ? AND user_id = ?", (check_uuid(uid), owner())).fetchone()
    return template_dict(r) if r else None


def save_template(uid: str, data: dict, user: str, force: bool = False) -> dict:
    """Create or change a template ({name, title, body, tags, folderID, updatedAt}; {deleted: true} deletes it)."""
    uid = check_uuid(uid) if uid else new_uuid()
    now = time.time()
    with db.tx() as con:
        r = con.execute(f"SELECT {TEMPLATE_COLS}, user_id FROM nts_templates WHERE uuid = ?", (uid,)).fetchone()
        if r and r["user_id"] != owner():
            raise NotFound("No such template")
        old = template_dict(r) if r else None
        ts = edit_time(data.get("updatedAt"), now)
        if old and not force and ts < old["updatedAt"]:
            raise Stale(old)
        t = dict(old or {"name": "", "title": "", "body": "", "tags": [], "folderID": None, "createdAt": now, "deleted": False})
        for k, limit in (("name", 255), ("title", 1000), ("body", MAX_TEXT)):
            if k in data:
                t[k] = _text(data[k], limit)
        t["name"] = t["name"].strip()
        if "tags" in data:
            t["tags"] = clean_tags(data["tags"])
        if "folderID" in data:
            t["folderID"] = check_uuid(data["folderID"]) if data["folderID"] else None
        if "createdAt" in data and data["createdAt"]:
            t["createdAt"] = float(data["createdAt"])
        if "deleted" in data:
            t["deleted"] = bool(data["deleted"])
        if not t["deleted"] and not t["name"]:
            raise Invalid("A template needs a name")
        rev = db.next_rev(con)
        vals = (t["name"], t["title"], t["body"], json.dumps(t["tags"], ensure_ascii=False), t["folderID"], t["createdAt"], ts, 1 if t["deleted"] else 0, rev)
        if old:
            con.execute("UPDATE nts_templates SET name=?, title=?, body=?, tags=?, folder_id=?, created_at=?, updated_at=?, deleted=?, rev=? WHERE uuid=?", vals + (uid,))
        else:
            con.execute("INSERT INTO nts_templates (name, title, body, tags, folder_id, created_at, updated_at, deleted, rev, uuid, user_id) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", vals + (uid, owner()))
        log_change(con, user, "delete" if t["deleted"] else ("create" if not old else "edit"), "template", uid, t["name"])
        r = con.execute(f"SELECT {TEMPLATE_COLS} FROM nts_templates WHERE uuid = ?", (uid,)).fetchone()
        return template_dict(r)


_PLACEHOLDER = re.compile(r"\{\{\s*(date|time|datetime|weekday|month|year|tomorrow|yesterday)\s*\}\}", re.I)


def expand(text: str, now: datetime = None) -> str:
    """Fill in a template's placeholders: {{date}} 2026-11-10, {{time}} 14:05, {{datetime}}, {{weekday}} Tuesday,
    {{month}} November, {{year}}, {{tomorrow}} / {{yesterday}} (dates). The apps and the web app do the same, with
    the device's own clock and time zone."""
    now = now or datetime.now()

    def one(m):
        k = m.group(1).lower()
        return {"date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M"), "datetime": now.strftime("%Y-%m-%d %H:%M"),
                "weekday": now.strftime("%A"), "month": now.strftime("%B"), "year": now.strftime("%Y"),
                "tomorrow": (now + timedelta(days=1)).strftime("%Y-%m-%d"), "yesterday": (now - timedelta(days=1)).strftime("%Y-%m-%d")}[k]
    return _PLACEHOLDER.sub(one, text or "")


def note_from_template(uid: str, now: datetime = None) -> dict:
    """The fields of a new note made from a template (placeholders filled in), to pass to save_note."""
    t = get_template(uid)
    if not t or t["deleted"]:
        raise NotFound("No such template")
    return {"title": expand(t["title"], now), "body": expand(t["body"], now), "tags": list(t["tags"]), "folderID": t["folderID"]}


# ---- related notes and suggestions
_STOP = set("""a an and are as at be but by for from has have i in is it its of on or that the this to was were will with you your
not no yes can just about into than then them they there their what when where which who why how all any our out over
also some more most such only own same so too very de het een en van ik je dat die niet op te met voor""".split())


def _keywords(text: str, n: int = 12) -> list:
    """The words that say most about a text: the most frequent ones that are not stop words, longest first on ties."""
    counts = {}
    for w in re.findall(r"[^\W\d_][\w'-]{2,}", (text or "").lower()):
        w = w.strip("'-")
        if len(w) >= 3 and w not in _STOP:
            counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], -len(kv[0]), kv[0]))[:n]]


def related(uid: str, limit: int = 8) -> list:
    """Notes like this one, best first: words in common (MariaDB's full-text relevance; a keyword count on SQLite)
    plus tags in common. Each comes with "score"."""
    n = get_note(uid)
    if not n:
        raise NotFound("No such note")
    text = " ".join([n["title"], n["body"][:4000], n["ocrText"][:2000], " ".join(n["tags"])])
    words = _keywords(text)
    mine = {t.lower() for t in n["tags"]}
    scores = {}
    with db.connect() as con:
        if words:
            if con.mysql:
                rows = con.execute(f"SELECT {NOTE_COLS}, MATCH (title, body, ocr_text, tags) AGAINST (?) AS score FROM nts_notes "
                                   "WHERE user_id = ? AND deleted = 0 AND uuid != ? AND MATCH (title, body, ocr_text, tags) AGAINST (?) "
                                   "ORDER BY score DESC LIMIT 60", (" ".join(words), owner(), n["id"], " ".join(words))).fetchall()
            else:
                hay = "lower(title || ' ' || body || ' ' || ocr_text || ' ' || tags)"
                expr = " + ".join(f"(CASE WHEN instr({hay}, ?) > 0 THEN 1 ELSE 0 END)" for _ in words)
                rows = con.execute(f"SELECT {NOTE_COLS}, ({expr}) AS score FROM nts_notes WHERE user_id = ? AND deleted = 0 AND uuid != ? "
                                   f"AND ({expr}) > 0 ORDER BY score DESC LIMIT 60", words + [owner(), n["id"]] + words).fetchall()
            for r in rows:
                scores[r["uuid"]] = [note_dict(r), float(r["score"] or 0)]
        if mine:  # tags in common count too, even with no words in common
            for t in list(mine)[:8]:
                c, p = _tag_clause(con, t)
                for r in con.execute(f"SELECT {NOTE_COLS} FROM nts_notes WHERE user_id = ? AND deleted = 0 AND uuid != ? AND {c} LIMIT 60",
                                     (owner(), n["id"], p)).fetchall():
                    scores.setdefault(r["uuid"], [note_dict(r), 0.0])
        top = scores and max(s for _, s in scores.values()) or 1.0
        out = []
        for d, s in scores.values():
            common = len(mine & {t.lower() for t in d["tags"]})
            score = (s / top if top else 0) + 0.5 * common
            if score > 0:
                out.append({**d, "score": round(score, 3)})
        out.sort(key=lambda d: -d["score"])
        return with_attachments(con, out[:max(1, min(int(limit), 50))])


def suggestions(uid: str) -> dict:
    """Tags and a folder this note may want, from the notes most like it (and tags whose name is a word in it):
    {"tags": [names, best first], "folder": {id, name} or None, "related": [notes]}."""
    n = get_note(uid)
    if not n:
        raise NotFound("No such note")
    rel = related(uid, 10)
    have = {t.lower() for t in n["tags"]}
    tag_votes, folder_votes = {}, {}
    for d in rel:
        for t in d["tags"]:
            if t.lower() not in have:
                tag_votes[t] = tag_votes.get(t, 0) + d["score"]
        if d["folderID"]:
            folder_votes[d["folderID"]] = folder_votes.get(d["folderID"], 0) + d["score"]
    words = set(re.findall(r"\w+", " ".join([n["title"], n["body"][:8000], n["ocrText"][:4000]]).lower()))
    for t in list_tags():
        if t["name"].lower() not in have and t["name"].lower() in words:
            tag_votes[t["name"]] = tag_votes.get(t["name"], 0) + 1.0
    tags = [t for t, v in sorted(tag_votes.items(), key=lambda kv: -kv[1]) if v >= 0.5][:5]
    folder = None
    if folder_votes and not n["folderID"]:
        fid, votes = max(folder_votes.items(), key=lambda kv: kv[1])
        f = next((f for f in list_folders() if f["id"] == fid), None)
        if f and votes >= 0.8:
            folder = {"id": f["id"], "name": f["name"]}
    return {"tags": tags, "folder": folder, "related": rel}
