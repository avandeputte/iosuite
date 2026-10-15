"""Metadata consistency: compares what digiKam's database, the XMP sidecar and
the image file itself say about each photo, and can bring them into line in a
direction you choose.

Compared fields: rating, pick label, color label, title, caption, tags.
Values are read with exiftool from the sidecar and from the file (its embedded
XMP), and straight from digiKam's database (read-only). Results are stored in
data/viewer.db so the report can be browsed without rescanning.

Syncing writes with the same code paths as editing: digiKam's writers for the
sidecar / file (edits.write_args), and dbsync for the database (digiKam closed,
backup first).
"""
import json
import os
import sqlite3
import subprocess
import threading
import time

from . import analysis, dbsync, dkdb, edits, index

FIELDS = ["rating", "pick", "color", "title", "caption", "tags"]
SOURCES = ["db", "sidecar", "file"]
progress = {"running": False, "done": 0, "total": 0, "mismatched": 0, "scanned_at": None, "error": None}
_run = {"gen": 0}
TAGS_XMP = ["XMP-digiKam:TagsList", "XMP-microsoft:LastKeywordXMP", "XMP-lr:HierarchicalSubject", "XMP-mediapro:CatalogSets"]
READ_TAGS = ["-XMP-xmp:Rating", "-XMP-digiKam:PickLabel", "-XMP-digiKam:ColorLabel", "-XMP-dc:Title", "-XMP-dc:Description",
             *["-" + t for t in TAGS_XMP]]
# exiftool's JSON keys for READ_TAGS; the tag lists in the order digiKam prefers them
TAG_KEYS = ("TagsList", "LastKeywordXMP", "HierarchicalSubject", "CatalogSets")
VALUE_KEYS = ("Rating", "PickLabel", "ColorLabel", "Title", "Description", *TAG_KEYS)


def init():
    con = analysis.connect()
    con.execute("CREATE TABLE IF NOT EXISTS consistency (photo_id INTEGER PRIMARY KEY, stamp TEXT, data TEXT, "
                "mismatch INTEGER, has_sidecar INTEGER, file_xmp INTEGER, checked INTEGER)")
    con.commit()
    con.close()


# --------------------------------------------------------------------------
# reading the three sources
# --------------------------------------------------------------------------

def _blank() -> dict:
    """What a photo with no metadata at all looks like (a fresh copy each time: tags is a list)."""
    return {"rating": 0, "pick": 0, "color": 0, "title": "", "caption": "", "tags": []}


def _norm(field: str, v):
    """A comparable form of a value: labels 0/absent/-1 are all 'none', text is stripped,
    tags are a sorted list of paths."""
    if field in ("rating", "pick", "color"):
        try:
            n = int(float(v)) if v not in (None, "") else 0
        except (TypeError, ValueError):
            n = 0
        return max(n, 0)
    if field == "tags":
        items = v if isinstance(v, list) else ([v] if v else [])
        return sorted({str(t).replace("|", "/").strip() for t in items if str(t).strip()})
    return (str(v).strip() if v else "")


def db_values(photo_ids: list) -> dict:
    """{id: {field: value}} from digiKam's database (read-only), as digiKam itself would write them."""
    src = dkdb.connect(write=False)
    out = {}
    try:
        tags = dkdb.tag_tree(src)
        internal = {r[0] for r in src.execute("SELECT tagid FROM TagProperties WHERE property = 'internalTag'")}
        pick_ids = {tid: index.PICK[n] for tid, (_, n) in tags.items() if n in index.PICK and tid in internal}
        color_ids = {tid: index.COLOR[n] for tid, (_, n) in tags.items() if n in index.COLOR and tid in internal}
        for i in range(0, len(photo_ids), 500):
            chunk = ",".join(str(int(x)) for x in photo_ids[i:i + 500])
            for pid, rating in src.execute(f"SELECT imageid, rating FROM ImageInformation WHERE imageid IN ({chunk})"):
                out[pid] = {**_blank(), "rating": rating}
            for pid, tid in src.execute(f"SELECT imageid, tagid FROM ImageTags WHERE imageid IN ({chunk})"):
                d = out.setdefault(pid, _blank())
                if tid in pick_ids:
                    d["pick"] = pick_ids[tid]
                elif tid in color_ids:
                    d["color"] = color_ids[tid]
                elif tid in tags and tid not in internal:
                    d["tags"].append(dkdb.tag_path(tags, tid))
            for pid, typ, text in src.execute(
                    f"SELECT imageid, type, comment FROM ImageComments WHERE language = 'x-default' AND (author IS NULL OR author = '') "
                    f"AND imageid IN ({chunk}) ORDER BY id"):
                d = out.setdefault(pid, _blank())
                key = "title" if typ == 3 else "caption"
                if not d[key]:
                    d[key] = text or ""
    finally:
        src.close()
    return out


def _exif_read(paths: list) -> dict:
    """{path: {field: value}} for every readable path; a path with no XMP block gives {}."""
    if not paths:
        return {}
    res = subprocess.run([*edits.exiftool_cmd(), "-j", "-m", "-q", "-charset", "utf8", "-n", *READ_TAGS, "--", *paths],
                         capture_output=True, text=True, timeout=1800)
    out = {}
    try:
        rows = json.loads(res.stdout or "[]")
    except ValueError:
        rows = []
    for r in rows:
        tags = None
        for key in TAG_KEYS:
            if r.get(key) not in (None, "", []):
                tags = r[key] if isinstance(r[key], list) else [r[key]]
                break
        out[r.get("SourceFile")] = {
            "rating": r.get("Rating"), "pick": r.get("PickLabel"), "color": r.get("ColorLabel"),
            "title": r.get("Title"), "caption": r.get("Description"), "tags": tags if tags is not None else [],
            "_present": any(k in r for k in VALUE_KEYS),
        }
    return out


def _can_hold_metadata(path: str) -> bool:
    """A format digiKam writes into (whether or not this copy is writable right now)."""
    return os.path.splitext(path)[1].lower() in edits.INFILE_EXT


def compare(photos: list) -> list:
    """photos: rows with id, path, hash, size, modified. Returns one record per photo."""
    dbv = db_values([p["id"] for p in photos])
    sidecars = [p["path"] + ".xmp" for p in photos if os.path.isfile(p["path"] + ".xmp")]
    files = [p["path"] for p in photos if _can_hold_metadata(p["path"])]
    read = _exif_read(sidecars + files)
    records = []
    for p in photos:
        side = read.get(p["path"] + ".xmp")
        fil = read.get(p["path"])
        d = dbv.get(p["id"], _blank())
        vals = {"db": d, "sidecar": side, "file": fil if fil and fil.get("_present") else (None if fil is None else {})}
        fields, mism = {}, []
        for f in FIELDS:
            row = {}
            for s in SOURCES:
                v = vals[s]
                row[s] = None if v is None or (s == "file" and not v) else _norm(f, v.get(f))
            present = [row[s] for s in SOURCES if row[s] is not None]
            same = all(x == present[0] for x in present)
            fields[f] = {**row, "ok": same}
            if not same:
                mism.append(f)
        records.append({"id": p["id"], "name": p.get("name"), "path": p["path"], "has_sidecar": side is not None,
                        "file_xmp": bool(fil), "file_editable": edits.can_write_file(p["path"]),
                        "fields": fields, "mismatch": mism})
    return records


# --------------------------------------------------------------------------
# scanning (background) and the stored report
# --------------------------------------------------------------------------

def scan(photos: list, rescan_all: bool = True):
    """Compare every given photo (rows with id, path, name, hash, size, modified) in the background."""
    init()
    _run["gen"] += 1
    gen = _run["gen"]
    todo = [p for p in photos if not p.get("video")]
    if not rescan_all:
        con = analysis.connect()
        try:
            have = dict(con.execute("SELECT photo_id, stamp FROM consistency").fetchall())
        finally:
            con.close()
        todo = [p for p in todo if have.get(p["id"]) != analysis._stamp(p)]
    progress.update(running=True, done=0, total=len(todo), error=None)

    def work():
        try:
            for i in range(0, len(todo), 200):
                if gen != _run["gen"]:
                    return
                batch = todo[i:i + 200]
                try:
                    recs = compare(batch)
                except Exception as e:
                    progress["error"] = str(e)[:200]
                    continue
                now = int(time.time())
                rows = [(r["id"], analysis._stamp(p), json.dumps(r), len(r["mismatch"]), r["has_sidecar"], r["file_xmp"], now)
                        for p, r in zip(batch, recs)]
                with analysis._write_lock:
                    con = analysis.connect()
                    try:
                        con.executemany("INSERT OR REPLACE INTO consistency VALUES (?,?,?,?,?,?,?)", rows)
                        con.commit()
                    finally:
                        con.close()
                progress["done"] += len(batch)
            progress["scanned_at"] = int(time.time())
        finally:
            if gen == _run["gen"]:
                progress["running"] = False
                progress["mismatched"] = summary()["mismatched"]

    threading.Thread(target=work, name="consistency", daemon=True).start()


def summary() -> dict:
    empty = {"scanned": 0, "mismatched": 0, "by_field": {}, "no_sidecar": 0, "scanned_at": None}
    if not analysis.DB.exists():
        return empty
    con = analysis.connect()
    try:
        scanned, mism, no_side, last = con.execute(
            "SELECT count(*), sum(mismatch > 0), sum(has_sidecar = 0), max(checked) FROM consistency").fetchone()
        by_field = {f: 0 for f in FIELDS}
        for (data,) in con.execute("SELECT data FROM consistency WHERE mismatch > 0"):
            for f in json.loads(data)["mismatch"]:
                by_field[f] += 1
        return {"scanned": scanned or 0, "mismatched": mism or 0, "no_sidecar": no_side or 0, "by_field": by_field, "scanned_at": last}
    except sqlite3.Error:
        return empty
    finally:
        con.close()


def report(field: str = None, offset: int = 0, limit: int = 100) -> dict:
    con = analysis.connect()
    try:
        rows = con.execute("SELECT data FROM consistency WHERE mismatch > 0 ORDER BY photo_id DESC").fetchall()
    finally:
        con.close()
    recs = [json.loads(r[0]) for r in rows]
    if field:
        recs = [r for r in recs if field in r["mismatch"]]
    return {"total": len(recs), "offset": offset, "items": recs[offset:offset + limit]}


def forget(photo_ids: list):
    """Drop stored results so those photos are compared again on the next scan."""
    if photo_ids:
        with analysis._write_lock:
            con = analysis.connect()
            try:
                con.executemany("DELETE FROM consistency WHERE photo_id = ?", [(int(i),) for i in photo_ids])
                con.commit()
            finally:
                con.close()


# --------------------------------------------------------------------------
# syncing
# --------------------------------------------------------------------------

def _changes_from(values: dict, fields: list, db_tags: list) -> dict:
    """An edit dict (as edits.apply / dbsync use) that makes a target look like `values`."""
    ch = {}
    for f in fields:
        if f == "tags":
            want = set(_norm("tags", values.get("tags")))
            have = set(db_tags)
            ch["add_tags"] = sorted(want - have)
            ch["remove_tags"] = sorted(have - want)
        else:
            ch[f] = _norm(f, values.get(f))
    return ch


def sync(photo_ids: list, source: str, targets: list, fields: list = None) -> dict:
    """Copy the chosen fields from `source` (db|sidecar|file) to each of `targets`."""
    if source not in SOURCES or any(t not in SOURCES or t == source for t in targets) or not targets:
        raise ValueError("Choose a source and at least one different target")
    fields = [f for f in (fields or FIELDS) if f in FIELDS]
    con = analysis.connect()
    try:
        stored = {}
        for i in range(0, len(photo_ids), 500):
            chunk = ",".join(str(int(x)) for x in photo_ids[i:i + 500])
            for pid, data in con.execute(f"SELECT photo_id, data FROM consistency WHERE photo_id IN ({chunk})"):
                stored[pid] = json.loads(data)
    finally:
        con.close()
    done, skipped = [], []
    # fresh values from the source, not the stored report, in case something changed since the scan
    photos = [{"id": pid, "path": stored[pid]["path"], "name": stored[pid]["name"]} for pid in photo_ids if pid in stored]
    dbv = db_values([p["id"] for p in photos]) if source == "db" or "db" in targets else {}
    suffix = ".xmp" if source == "sidecar" else ""
    read = _exif_read([p["path"] + suffix for p in photos]) if source != "db" else {}

    def source_values(p):
        return dbv.get(p["id"]) if source == "db" else read.get(p["path"] + suffix)

    if "db" in targets:
        pending = {}
        for p in photos:
            src_vals = source_values(p)
            if src_vals is None:
                skipped.append({"id": p["id"], "reason": f"no {source} metadata to copy"})
                continue
            cur = dbv.get(p["id"], {"tags": []})
            ch = _changes_from(src_vals, fields, _norm("tags", cur.get("tags")))
            if "caption" in ch:
                ch["caption_date"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            pending[p["id"]] = ch
        if pending:
            res = dbsync.apply_pending(pending=pending)  # raises SyncError if digiKam is running
            done += [pid for pid in pending if not any(s["id"] == pid for s in res["skipped"])]
            skipped += res["skipped"]

    file_targets = [t for t in targets if t in ("sidecar", "file")]
    if file_targets:
        jobs, owner = [], {}
        for p in photos:
            src_vals = source_values(p)
            if src_vals is None:
                if not any(s["id"] == p["id"] for s in skipped):
                    skipped.append({"id": p["id"], "reason": f"no {source} metadata to copy"})
                continue
            ch = {f: _norm(f, src_vals.get(f)) for f in fields if f != "tags"}
            if "caption" in ch:
                ch["caption_date"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            tag_paths = _norm("tags", src_vals.get("tags")) if "tags" in fields else None
            for t in file_targets:
                if t == "sidecar":
                    try:
                        side = edits._prepare(p["path"])  # backs the sidecar up first
                    except OSError:
                        skipped.append({"id": p["id"], "reason": "cannot create the sidecar"})
                        continue
                    jobs.append((side, edits.write_args(ch, tag_paths, False)))
                    owner[side] = p["id"]
                elif edits.can_write_file(p["path"]):
                    jobs.append((p["path"], edits.write_args(ch, tag_paths, True)))
                    owner[p["path"]] = p["id"]
                else:
                    skipped.append({"id": p["id"], "reason": "this file type cannot hold metadata (sidecar only)"})
        failed = {owner[t] for t in edits.run_exiftool(jobs)}
        skipped += [{"id": i, "reason": "exiftool could not write this file"} for i in failed]
        done += [i for i in dict.fromkeys(owner.values()) if i not in failed]
    done = sorted(set(done))
    forget(done)
    return {"synced": len(done), "skipped": skipped}
