"""Face metadata quality: problems in the face regions digiKam's database holds, and the clean-up of the one
that can be fixed safely without a person looking.

Near-duplicates are the same person's face stored twice on a photo, a few pixels apart (each coordinate within
NEAR pixels). They come from a rounding round trip in digiKam: regions live in files as fractions of the image
size and in the database as pixels; a rescan read a region back one pixel off, an older digiKam added it next to
the one it had, and from then on both were written to the file and read back on every rescan
(ItemScanner::commitFaces keeps two regions that differ). On screen they look like one box; in the people list
the person appears twice.

The clean-up keeps one region of each such group and removes the others from digiKam's database, then rewrites
the photo's sidecar regions from the database (not the image files) and records the photo's new file date (as
digiKam does after writing metadata), so digiKam does not import the pair again. One full database backup is
taken first; every photo gets a change-log entry with a copy of its sidecar from before.

Reported, not changed: the same person in two clearly separate places on one photo (usually a misnamed face),
and rectangles that are empty or fall outside the image.
"""
import logging
import threading
import time
from pathlib import Path

from . import dbsync, dkdb, index

log = logging.getLogger("app.facequality")
NEAR = 3          # pixels: regions of one person this close on every coordinate are the same face
MARGIN = 5        # pixels a rectangle may stick out of the image before it counts as outside
progress = {"running": False, "done": 0, "total": 0, "removed": 0, "photos": 0, "errors": 0, "started": None, "finished": None, "error": None, "backup": None}
_lock = threading.Lock()


def _rect(value):
    m = index.RECT_RE.search(value or "")
    return tuple(map(int, m.groups())) if m else None


def _near(a, b) -> bool:
    return all(abs(a[k] - b[k]) <= NEAR for k in range(4))


def _groups(rects: list) -> list:
    """rects: [(value, rect)] of one person on one photo -> lists of near-identical ones (single-member groups too)."""
    groups = []
    for v, r in rects:
        for g in groups:
            if any(_near(r, r2) for _v, r2 in g):
                g.append((v, r))
                break
        else:
            groups.append([(v, r)])
    return groups


def scan() -> dict:
    """Every face region in digiKam's database (or the library with sync off), checked."""
    con = dkdb.connect()
    try:
        tags = dkdb.tag_tree(con)
        rows = con.execute(
            "SELECT p.imageid, p.tagid, p.property, p.value, ii.width, ii.height, ii.orientation FROM ImageTagProperties p "
            "JOIN Images i ON i.id = p.imageid AND i.status = 1 LEFT JOIN ImageInformation ii ON ii.imageid = p.imageid "
            "WHERE p.property IN ('tagRegion', 'autodetectedFace', 'autodetectedPerson', 'ignoredFace')").fetchall()
    finally:
        con.close()
    by, invalid = {}, []
    for img, tag, prop, val, w, h, orient in rows:
        r = _rect(val)
        up_w, up_h = ((h, w) if (orient or 1) in (5, 6, 7, 8) else (w, h))
        if r is None or r[2] <= 0 or r[3] <= 0 or (up_w and up_h and (r[0] < -MARGIN or r[1] < -MARGIN or r[0] + r[2] > up_w + MARGIN or r[1] + r[3] > up_h + MARGIN)):
            invalid.append({"photo": img, "name": tags.get(tag, (0, "?"))[1] if tag in tags else "?", "rect": list(r) if r else None, "size": [up_w, up_h]})
            continue
        if prop == "tagRegion":
            by.setdefault((img, tag), []).append((val, r))
    near, separate = [], []
    for (img, tag), rects in by.items():
        if len(rects) < 2:
            continue
        groups = _groups(rects)
        name = dkdb.tag_path(tags, tag).split("/")[-1] if tag in tags else "?"
        for g in groups:
            if len(g) > 1:
                near.append({"photo": img, "tag": tag, "name": name, "keep": g[0][0], "drop": [v for v, _r in g[1:]],
                             "apart": max(abs(a[k] - b[k]) for _va, a in g for _vb, b in g for k in range(4))})
        if len(groups) > 1:
            separate.append({"photo": img, "name": name, "rects": [list(g[0][1]) for g in groups]})
    return {"checked": len(rows), "near": near, "separate": separate, "invalid": invalid, "at": int(time.time())}


def summary(s: dict = None, limit: int = 120) -> dict:
    s = s or scan()
    photos = sorted({n["photo"] for n in s["near"]})
    return {"checked": s["checked"], "at": s["at"],
            "near": {"photos": len(photos), "groups": len(s["near"]), "extra": sum(len(n["drop"]) for n in s["near"]),
                     "examples": [{"photo": n["photo"], "name": n["name"], "apart": n["apart"]} for n in s["near"][:limit]]},
            "separate": {"count": len(s["separate"]), "items": s["separate"][:limit]},
            "invalid": {"count": len(s["invalid"]), "items": s["invalid"][:limit]},
            "progress": dict(progress)}


def fix_near_duplicates(after=None, check_running: bool = True) -> int:
    """Start the clean-up in the background. Returns how many photos it will touch."""
    if progress["running"]:
        raise dbsync.SyncError("The clean-up is already running.")
    s = scan()
    todo = {}
    for n in s["near"]:
        todo.setdefault(n["photo"], []).append(n)
    if not todo:
        return 0
    db_path = Path(dkdb.sqlite_path())
    dbsync.preflight(db_path, check_running, "faces")
    progress.update(running=True, done=0, total=len(todo), removed=0, photos=0, errors=0, started=int(time.time()), finished=None, error=None, backup=None)

    def job():
        try:
            _run(todo, db_path, check_running)
        except Exception as e:
            log.warning("face clean-up stopped: %s", e, exc_info=True)
            progress["error"] = str(e)[:300]
        finally:
            progress.update(running=False, finished=int(time.time()))
            if after:
                after()
    threading.Thread(target=job, name="face-cleanup", daemon=True).start()
    return len(todo)


def _run(todo: dict, db_path: Path, check_running: bool):
    from . import edits, facemgr, history
    backup = dkdb.backup(db_path, force=True)  # thousands of regions removed in one go: one full copy first
    progress["backup"] = str(backup) if backup else None
    photos = list(todo)
    paths = dict(dbsync._photo_paths(photos))
    for i in range(0, len(photos), 100):
        batch = photos[i:i + 100]
        snaps = {pid: history.snapshot(pid, paths[pid] + ".xmp") for pid in batch if pid in paths}
        removed = {}
        with facemgr._lock:
            with dbsync.write_transaction(db_path, check_running) as con:
                for pid in batch:
                    for n in todo[pid]:
                        gone = 0
                        for v in dict.fromkeys(n["drop"]):
                            if v == n["keep"]:
                                continue
                            con.execute("DELETE FROM ImageTagProperties WHERE imageid = ? AND tagid = ? AND property = 'tagRegion' AND value = ?", (pid, n["tag"], v))
                            gone += 1
                        # exact copies of the kept value: remove them all, put one back
                        same = sum(1 for v in n["drop"] if v == n["keep"])
                        if same:
                            con.execute("DELETE FROM ImageTagProperties WHERE imageid = ? AND tagid = ? AND property = 'tagRegion' AND value = ?", (pid, n["tag"], n["keep"]))
                            con.execute("INSERT INTO ImageTagProperties (imageid, tagid, property, value) VALUES (?,?,?,?)", (pid, n["tag"], "tagRegion", n["keep"]))
                            gone += same
                        removed.setdefault(pid, []).append((n["name"], gone, n["apart"], n["keep"]))
        status = facemgr.write_regions_many(batch, db_path, files=False)
        rows = []
        for pid in batch:
            done = removed.get(pid, [])
            k = sum(g for _n, g, _a, _v in done)
            progress["removed"] += k
            if status.get(pid) != "written":
                progress["errors"] += 1
            rows.append({"photo_id": pid, "action": "face", "path": paths.get(pid), "sidecar": snaps.get(pid),
                         "summary": "Duplicate face regions removed: " + ", ".join(f"{n} ({a} px apart)" for n, _g, a, _v in done),
                         "details": {"removed": k, "kept": {n: v for n, _g, _a, v in done}, "sidecar": status.get(pid)}})
        history.record(rows)
        progress["photos"] += len(batch)
        progress["done"] += len(batch)
    log.info("face clean-up: %d duplicate regions removed on %d photos (%d sidecars not rewritten)", progress["removed"], progress["photos"], progress["errors"])
    _ = edits
