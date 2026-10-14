"""Tag manager: add, rename, move and delete keyword tags, like digiKam's own.

Tag definitions live in digiKam's database, so every operation here writes it
and therefore only runs while digiKam is closed, with the same safeguards as
dbsync (backup first, one transaction, integrity check).

Renaming, moving or deleting a tag also changes the tag path stored in the XMP
sidecar of every photo that carries it (or a tag beneath it). Those sidecar
rewrites are queued in data/state.db and done in the background, resumably,
after each sidecar is copied to data/sidecar-backups/tag-ops/<operation>/.

People tags may be renamed and moved (regions are keyed by tag id) and new
tags may be created under People; deleting a person stays with digiKam, which
turns their faces back into unknown faces, and digiKam's internal and special
face tags are never touched.
"""
import os
import shutil
import sqlite3
import threading
import time
from pathlib import Path

from . import dbsync, dkdb, edits
from . import state as appstate
from .dbsync import SyncError

OPS_BACKUP_DIR = edits.BACKUP_DIR / "tag-ops"
KEEP_OPS = 8
SPECIAL_PROPS = {"internalTag", "unknownPerson", "ignoredPerson", "unconfirmedPerson"}
progress = {"running": False, "done": 0, "total": 0}
_worker_lock = threading.Lock()


def init():
    con = appstate.connect()
    cols = [r[1] for r in con.execute("PRAGMA table_info(tagjobs)")]
    if cols and "image_id" not in cols:  # an early schema without the image id; its rows cannot be replayed
        con.execute("DROP TABLE tagjobs")
    con.execute("CREATE TABLE IF NOT EXISTS tagjobs (id INTEGER PRIMARY KEY AUTOINCREMENT, op TEXT, path TEXT, image_id INTEGER)")
    con.commit()
    con.close()


def pending_jobs() -> int:
    con = appstate.connect()
    try:
        return con.execute("SELECT count(*) FROM tagjobs").fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        con.close()


class _Tree:
    def __init__(self, con):
        self.rows = {tid: {"pid": pid or 0, "name": name} for tid, (pid, name) in dkdb.tag_tree(con).items()}
        props = {}
        for tid, prop in con.execute("SELECT tagid, property FROM TagProperties"):
            props.setdefault(tid, set()).add(prop)
        with_faces = {r[0] for r in con.execute("SELECT DISTINCT tagid FROM ImageTagProperties")}
        self.internal = set()    # digiKam's bookkeeping tags (labels and the like), never user-visible
        self.protected = set()   # never touched here: digiKam's internal and special face tags, and the People root
        self.people = set()      # person tags and their family groups: may be renamed and moved, not deleted
        for tid, t in self.rows.items():
            top = self.rows[self.chain(tid)[-1]]["name"]
            p = props.get(tid, set())
            if top == "_Digikam_Internal_Tags_":
                self.internal.add(tid)
                self.protected.add(tid)
            elif p & SPECIAL_PROPS or (t["name"] == "People" and not t["pid"]):
                self.protected.add(tid)
            elif top == "People" or "person" in p or tid in with_faces:
                self.people.add(tid)

    def chain(self, tid):
        out, seen = [], set()
        while tid in self.rows and tid not in seen:
            seen.add(tid)
            out.append(tid)
            tid = self.rows[tid]["pid"]
        return out  # tag, parent, ..., root

    def full(self, tid):
        return "/".join(self.rows[t]["name"] for t in reversed(self.chain(tid)))

    def subtree(self, tid):
        """tid and all descendants, parents before children."""
        kids = {}
        for t, r in self.rows.items():
            kids.setdefault(r["pid"], []).append(t)
        out, stack = [], [tid]
        while stack:
            t = stack.pop()
            out.append(t)
            stack.extend(kids.get(t, []))
        return out


def _check_name(name: str) -> str:
    name = " ".join(str(name or "").split())
    if not name or "/" in name or "|" in name or len(name) > 120:
        raise SyncError("Tag names must be 1-120 characters and cannot contain / or |.")
    return name


def _photos_with(con, tag_ids, roots):
    """{image id: absolute path} for visible items carrying any of the tags."""
    out = {}
    ids = ",".join(str(int(t)) for t in tag_ids)
    for iid, r, rel, name in con.execute(
            "SELECT DISTINCT i.id, a.albumRoot, a.relativePath, i.name FROM ImageTags it JOIN Images i ON i.id = it.imageid "
            f"JOIN Albums a ON a.id = i.album WHERE it.tagid IN ({ids}) AND i.status = 1"):
        if r in roots:
            out[iid] = roots[r] + rel.rstrip("/") + "/" + name
    return out


def apply(op: dict, db_path: Path = None, check_running: bool = True, queue: bool = True, backup: bool = True) -> dict:
    """op: {op: add, parent, name} | {op: rename, id, name} | {op: move, id, parent} | {op: delete, id}
       | {op: icon, id, photo}. Returns a summary including how many sidecar files will be updated.
    `backup=False` is for callers that run several operations in a row and took one
    database backup themselves before the first."""
    db_path = Path(db_path or dkdb.sqlite_path())
    kind = op.get("op")
    if kind not in ("add", "rename", "move", "delete", "icon"):
        raise SyncError("Unknown tag operation.")
    dbsync.preflight(db_path, check_running, "tags")
    if queue and pending_jobs():
        raise SyncError("Sidecar files from the previous tag change are still being updated. Try again in a moment.")
    backup_file = dkdb.backup(db_path, force=(op.get("op") == "delete")) if backup else None  # deleting a tag is destructive
    stamp = time.strftime("%Y%m%d-%H%M%S")
    jobs, summary = [], {"op": kind}

    with dbsync.write_transaction(db_path, check_running) as con:
        tree = _Tree(con)
        roots = dkdb.root_paths(con)

        def editable(tid, what="tag", allow_people=False):
            if tid not in tree.rows:
                raise SyncError(f"That {what} no longer exists in digiKam.")
            if tid in tree.protected:
                raise SyncError(f"“{tree.full(tid)}” is one of digiKam's own tags; manage it in digiKam.")
            if tid in tree.people and not allow_people:
                raise SyncError(f"“{tree.full(tid)}” is a person. People can be renamed and moved here, but deleting a person "
                                f"(and turning their faces back into unknown faces) is done in digiKam.")

        def free_name(pid, name, ignore=None):
            if any(t != ignore and r["pid"] == pid and r["name"].lower() == name.lower() for t, r in tree.rows.items()):
                raise SyncError(f"A tag named “{name}” already exists there.")

        if kind == "icon":
            # the photo shown for a tag (CoreDB::setTagIcon). Allowed for people too: it changes
            # no tag assignment or face data, only which picture represents the tag.
            tid, photo = int(op.get("id") or 0), int(op.get("photo") or 0)
            if tid not in tree.rows or tid in tree.internal:
                raise SyncError("That tag cannot be changed here.")
            if photo and not con.execute("SELECT 1 FROM Images WHERE id = ? AND status = 1", (photo,)).fetchone():
                raise SyncError("That photo is not in the digiKam database.")
            if photo:
                con.execute("UPDATE Tags SET iconkde = ?, icon = ? WHERE id = ?", ("", photo, tid))
            else:
                con.execute("UPDATE Tags SET iconkde = ?, icon = NULL WHERE id = ?", ("", tid))
            summary.update(id=tid, path=tree.full(tid), photo=photo, photos=0, sidecars=0)
        elif kind == "add":
            pid = int(op.get("parent") or 0)
            # a tag may be created under a family group, and a person directly under the People root
            # (the root is protected only against being renamed, moved or deleted)
            if pid and not (pid in tree.protected and tree.full(pid) == "People"):
                editable(pid, "parent tag", allow_people=True)
            name = _check_name(op.get("name"))
            free_name(pid, name)
            new_id = con.execute("INSERT INTO Tags (pid, name) VALUES (?,?)", (pid, name)).lastrowid
            summary.update(id=new_id, path=(tree.full(pid) + "/" if pid else "") + name)
        else:
            tid = int(op.get("id") or 0)
            # renaming and moving are fine for people (regions are keyed by tag id, and the sidecars'
            # tag paths are rewritten below); deleting a person stays with digiKam
            editable(tid, allow_people=(kind in ("rename", "move")))
            sub = tree.subtree(tid)
            for t in sub:
                editable(t, "sub-tag", allow_people=(kind in ("rename", "move")))
            old_full = {t: tree.full(t) for t in sub}
            photos = _photos_with(con, sub, roots)
            if kind == "rename":
                name = _check_name(op.get("name"))
                free_name(tree.rows[tid]["pid"], name, ignore=tid)
                con.execute("UPDATE Tags SET name = ? WHERE id = ?", (name, tid))
                tree.rows[tid]["name"] = name
            elif kind == "move":
                pid = int(op.get("parent") or 0)
                if pid:
                    editable(pid, "destination tag", allow_people=True)
                    if pid in sub:
                        raise SyncError("A tag cannot be moved into itself or one of its own sub-tags.")
                if pid == tree.rows[tid]["pid"]:
                    raise SyncError("The tag is already there.")
                free_name(pid, tree.rows[tid]["name"], ignore=tid)
                con.execute("UPDATE Tags SET pid = ? WHERE id = ?", (pid, tid))  # digiKam's trigger rebuilds TagsTree
                tree.rows[tid]["pid"] = pid
            else:  # delete, children first so each row's own cleanup trigger fires
                for t in reversed(sub):
                    con.execute("DELETE FROM Tags WHERE id = ?", (t,))
            # like digiKam, rewrite the full tag list of every affected item afterwards
            jobs = [(stamp, path, iid) for iid, path in photos.items()]
            summary.update(id=tid, path=old_full[tid], new_path=None if kind == "delete" else tree.full(tid),
                           tags=len(sub), photos=len(photos))

    summary.update(sidecars=len(jobs), backup=str(backup_file) if backup_file else None)
    if queue and jobs:
        appstate._write(lambda c: c.executemany(
            "INSERT INTO tagjobs (op, path, image_id) VALUES (?,?,?)", jobs))
        start_worker()
    elif not queue:
        summary["jobs"] = jobs
    return summary


def _run_group(op: str, rows: list):
    """rows: [(image id, photo path)]. Keep a copy of each sidecar under this operation's
    folder (on top of edits' own first-change backup), then write each photo's complete
    current tag list (what digiKam does after a tag changes)."""
    for _, p in rows:
        side = p + ".xmp"
        if not os.path.isfile(side):
            continue
        dst = OPS_BACKUP_DIR / op / edits._rel(side)
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(side, dst)
    failed = edits.rewrite_tags([{"id": i, "path": p} for i, p in rows])
    if failed:
        progress.setdefault("failed", []).extend(failed)


def start_worker():
    """Process queued sidecar rewrites in the background (safe to call repeatedly)."""
    if not edits.EXIFTOOL or not _worker_lock.acquire(blocking=False):
        return

    def run():
        try:
            progress.update(running=True, done=0, total=pending_jobs())
            while True:
                con = appstate.connect()
                try:
                    first = con.execute("SELECT op FROM tagjobs ORDER BY id LIMIT 1").fetchone()
                    if not first:
                        break
                    rows = con.execute("SELECT id, path, image_id FROM tagjobs WHERE op = ? ORDER BY id LIMIT 200",
                                       tuple(first)).fetchall()
                finally:
                    con.close()
                try:
                    _run_group(first[0], [(r[2], r[1]) for r in rows])
                except Exception as e:  # leave the rows queued; they are retried on the next start
                    progress["error"] = str(e)
                    break
                appstate._write(lambda c: c.executemany("DELETE FROM tagjobs WHERE id = ?", [(r[0],) for r in rows]))
                progress["done"] += len(rows)
            if OPS_BACKUP_DIR.exists():
                for old in sorted(p for p in OPS_BACKUP_DIR.iterdir() if p.is_dir())[:-KEEP_OPS]:
                    shutil.rmtree(old, ignore_errors=True)
        finally:
            progress["running"] = False
            _worker_lock.release()

    threading.Thread(target=run, name="tag-sidecars", daemon=True).start()
