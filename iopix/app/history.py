"""The change log: every change the viewer makes to a photo, kept for good in photo_history.

One row per photo and change: when, who, what (a sentence), the details (the values before and after),
and what can bring it back:
- "undo": the values from before the change, applied again through the editing engine;
- "sidecar": a copy of the sidecar as it was just before the change (data/history/), put back in place;
- "original": the image file as it was before the viewer first wrote into it (data/file-backups/);
- "deleted": a deleted photo's files in data/deleted-photos/, put back and registered again.
A restore works as long as its backup is still there; what it did is logged as a change of its own.
"""
import contextvars
import json
import logging
import os
import shutil
import time
from pathlib import Path

from . import config, vdb

log = logging.getLogger("app.history")
SNAP_DIR = config.DATA_DIR / "history"
user = contextvars.ContextVar("history_user", default=None)  # set per request by the server
FIELD_LABEL = {"rating": "Rating", "pick": "Pick label", "color": "Colour label", "title": "Title", "caption": "Caption", "taken": "Date",
               "gps": "Location", "template": "Metadata template", "add_tags": "Tags added", "remove_tags": "Tags removed"}


def _who() -> str:
    return user.get() or "system"


def snapshot(photo_id: int, sidecar: str) -> str:
    """A copy of the sidecar as it is now, for the change about to be made. '' when there is none."""
    if not os.path.isfile(sidecar):
        return ""
    d = SNAP_DIR / f"{int(photo_id) % 256:02x}"
    d.mkdir(parents=True, exist_ok=True)
    dst = d / f"{int(photo_id)}-{time.time_ns()}.xmp"
    try:
        shutil.copy2(sidecar, dst)
    except OSError as e:
        log.warning("history: no sidecar copy for photo %s: %s", photo_id, e)
        return ""
    return str(dst)


def record(rows: list):
    """rows: [{photo_id, action, summary, details?, undo?, sidecar?, path?}], one transaction."""
    if not rows:
        return
    now, who = int(time.time()), _who()
    try:
        con = vdb.connect()
        try:
            con.executemany("INSERT INTO photo_history (photo_id, ts, user_name, action, summary, details, undo, sidecar_copy, path) VALUES (?,?,?,?,?,?,?,?,?)",
                            [(int(r["photo_id"]), now, r.get("user") or who, r["action"], r["summary"][:500],
                              json.dumps(r.get("details")) if r.get("details") is not None else None,
                              json.dumps(r.get("undo")) if r.get("undo") is not None else None,
                              r.get("sidecar") or None, r.get("path")) for r in rows])
            con.commit()
        finally:
            con.close()
    except Exception as e:  # the change itself stands; the log entry is what is lost
        log.warning("history: %d entries were not recorded: %s", len(rows), e)


def _fmt(field, v) -> str:
    if v is None or v == "" or v == []:
        return "none"
    if field == "rating":
        return "★" * int(v) if int(v) > 0 else "none"
    if field == "gps":
        return f"{v['lat']:.5f}, {v['lon']:.5f}" if isinstance(v, dict) else str(v)
    if field in ("add_tags", "remove_tags"):
        return ", ".join(t.split("/")[-1] for t in v)
    if field == "template":
        return "applied"
    s = str(v)
    return f"“{s[:80]}{'…' if len(s) > 80 else ''}”"


def describe_edit(before: dict, ch: dict) -> str:
    parts = []
    for f, v in ch.items():
        if f in ("caption_date", "shift") or f not in FIELD_LABEL:
            continue
        if f in ("add_tags", "remove_tags"):
            if v:
                parts.append(f"{FIELD_LABEL[f]}: {_fmt(f, v)}")
        else:
            parts.append(f"{FIELD_LABEL[f]}: {_fmt(f, before.get(f))} → {_fmt(f, v)}")
    return "; ".join(parts) or "Metadata rewritten"


def entries(photo_id: int = None, limit: int = 100, offset: int = 0, action: str = None) -> dict:
    con = vdb.connect()
    try:
        where, params = [], []
        if photo_id is not None:
            where.append("photo_id = ?"); params.append(int(photo_id))
        if action:
            where.append("action = ?"); params.append(action)
        w = (" WHERE " + " AND ".join(where)) if where else ""
        total = con.execute(f"SELECT count(*) FROM photo_history{w}", params).fetchone()[0]
        rows = con.execute(f"SELECT id, photo_id, ts, user_name, action, summary, details, undo, sidecar_copy, path FROM photo_history{w} "
                           f"ORDER BY id DESC LIMIT ? OFFSET ?", params + [int(limit), int(offset)]).fetchall()
    finally:
        con.close()
    from . import edits
    out = []
    for r in rows:
        d = {"id": r[0], "photo": r[1], "ts": r[2], "user": r[3], "action": r[4], "summary": r[5],
             "details": json.loads(r[6]) if r[6] else None, "path": r[9]}
        restore = []
        if r[7]:
            restore.append("undo")
        if r[8] and os.path.isfile(r[8]):
            restore.append("sidecar")
        if r[4] == "deleted" and r[9] and _deleted_backup(r[6]):
            restore.append("deleted")
        if r[9] and r[4] in ("edit", "sync") and edits.file_backup_path(r[9]).exists():
            restore.append("original")
        d["restore"] = restore
        out.append(d)
    return {"total": total, "entries": out}


def _deleted_backup(details_json):
    try:
        d = json.loads(details_json or "{}")
    except ValueError:
        return None
    b = d.get("backup")
    return b if b and Path(b).is_dir() else None


def get(entry_id: int) -> dict:
    con = vdb.connect()
    try:
        r = con.execute("SELECT id, photo_id, action, details, undo, sidecar_copy, path FROM photo_history WHERE id = ?", (int(entry_id),)).fetchone()
    finally:
        con.close()
    if not r:
        return None
    return {"id": r[0], "photo": r[1], "action": r[2], "details": json.loads(r[3]) if r[3] else {}, "undo": json.loads(r[4]) if r[4] else None,
            "sidecar": r[5], "path": r[6]}


def restore(entry_id: int, kind: str) -> dict:
    """Bring back what a change log entry allows: undo | sidecar | original | deleted."""
    e = get(entry_id)
    if not e:
        raise LookupError("No such change")
    from . import edits, index
    pid = e["photo"]
    if kind == "deleted":
        return _restore_deleted(e)
    photo = _photo(pid)
    if not photo:
        raise LookupError("That photo is not in the library any more")
    if kind == "undo":
        if not e["undo"]:
            raise ValueError("This change has nothing to undo")
        r = edits.apply([photo], e["undo"])
        if r["edited"]:
            record([{"photo_id": pid, "action": "restore", "summary": f"Change #{entry_id} undone", "path": photo["path"]}])
        return r
    if kind == "sidecar":
        if not e["sidecar"] or not os.path.isfile(e["sidecar"]):
            raise FileNotFoundError("The copy of the sidecar from before this change is gone")
        side = photo["path"] + ".xmp"
        mine = snapshot(pid, side)
        edits.ensure_backup(side)
        shutil.copy2(e["sidecar"], side)
        _pending_from_sidecar(photo)
        record([{"photo_id": pid, "action": "restore", "summary": f"Sidecar put back as it was before change #{entry_id}", "sidecar": mine, "path": photo["path"]}])
        return {"restored": "sidecar"}
    if kind == "original":
        b = edits.file_backup_path(photo["path"])
        if not b.exists():
            raise FileNotFoundError("The original of this file is no longer in file-backups")
        shutil.copy2(b, photo["path"])
        record([{"photo_id": pid, "action": "restore", "summary": "Image file put back as it was before the viewer first wrote into it", "path": photo["path"]}])
        index.build()
        return {"restored": "original"}
    raise ValueError("Unknown kind of restore")


def _photo(pid: int):
    from . import index
    con = index.open_index()
    try:
        r = con.execute("SELECT id, path FROM photos WHERE id = ?", (int(pid),)).fetchone()
    finally:
        con.close()
    return {"id": r[0], "path": r[1]} if r else None


def _pending_from_sidecar(photo: dict):
    """After a sidecar was put back: show (and later write to the database) what it says."""
    from . import consistency, edits, state
    side = photo["path"] + ".xmp"
    vals = consistency._exif_read([side]).get(side) or {}
    db_tags = set(edits.digikam_tag_paths([photo["id"]]).get(photo["id"], []))
    want = set(consistency._norm("tags", vals.get("tags")))
    ch = {"rating": int(vals.get("rating") or 0), "title": consistency._norm("title", vals.get("title")) or "",
          "caption": consistency._norm("caption", vals.get("caption")) or "", "add_tags": sorted(want - db_tags), "remove_tags": sorted(db_tags - want)}
    state._write(lambda c: c.execute("INSERT OR REPLACE INTO pending_edits VALUES (?,?,?)", (photo["id"], json.dumps(ch), int(time.time()))))


def _restore_deleted(e: dict) -> dict:
    """Put a deleted photo's files back where they were and add it to the library again, with its
    rating, title, caption and tags (they are in the restored sidecar, and queued as edits)."""
    from . import deletion, edits, folders, vdb as _v
    d = e["details"] or {}
    backup = Path(d.get("backup") or "")
    files = d.get("files") or []
    if not backup.is_dir() or not files:
        raise FileNotFoundError("The copy of this photo is no longer in deleted-photos")
    root = Path(str(config.PHOTOS_ROOT))
    main_file = root / files[0]
    if main_file.exists():
        raise FileExistsError(f"A file is already at {main_file}; move it away first")
    album = folders.album_for_dir(main_file.parent)
    if album is None:
        raise LookupError(f"The folder {main_file.parent} is not in the library any more")
    for f in files:
        src, dst = backup / f, root / f
        if src.exists() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    added = folders.register(album, [folders.staged_entry(main_file)])
    new_id = added[0]["id"]
    con = _v.connect()
    try:  # the photo's history continues under its new id
        con.execute("UPDATE photo_history SET photo_id = ? WHERE photo_id = ?", (new_id, e["photo"]))
        con.commit()
    finally:
        con.close()
    record([{"photo_id": new_id, "action": "restore", "summary": f"Restored from deleted-photos ({backup.name})", "path": str(main_file)}])
    ch = {k: d.get(k) for k in ("rating", "title", "caption") if d.get(k) not in (None, "")}
    if d.get("tags"):
        ch["add_tags"] = d["tags"]
    if ch:
        state_ch = {"rating": max(int(ch.get("rating") or 0), 0), **{k: v for k, v in ch.items() if k != "rating"}}
        from . import state
        state._write(lambda c: c.execute("INSERT OR REPLACE INTO pending_edits VALUES (?,?,?)", (new_id, json.dumps(state_ch), int(time.time()))))
    _ = deletion, edits
    return {"restored": "deleted", "id": new_id}
