"""Builds the app's own search index from the library tables (library.py).

The library tables in the viewer's database carry digiKam's columns. While Sync with digiKam is on
they are copied from digiKam's database whenever it changed (refresh_library); with sync off, or
when digiKam's database is unreachable, they are what the viewer has, and the index is built from
them either way, with one code path. The build also keeps pix_photo_identity, the viewer's stable
identity for a photo (digiKam's uniqueHash and size), through which favorites, albums, edits and
analysis results follow a photo if digiKam ever renumbers it.

The result is a small denormalised SQLite file with a full-text table, stored in the app's data
folder and swapped in atomically. Bump SCHEMA_VERSION whenever the tables, indexes or the meaning
of a column change, so running viewers rebuild.
"""
import calendar
import contextlib
import json
import logging
import os
import re
import sqlite3
import threading
from types import SimpleNamespace
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from app.ai import analysis, jerseys, moments, ocrwords, smartcrop, videos
from app import config, jobs
from app.digikam import dkdb, library
from app.photos import dateprecision, edits
from app.geo import places
from app.data import state as appstate, vdb
from app.digikam.dkdb import chunked, in_chunks

log = logging.getLogger("app.data.index")
SOURCE_ERRORS = (*vdb.Error, OSError, dkdb.SyncError)  # digiKam's database cannot be read right now


class Unavailable(Exception):
    """Neither digiKam's database nor a copy of the library can be read."""

SCHEMA = """
CREATE TABLE photos (
    id INTEGER PRIMARY KEY, album_id INTEGER, name TEXT, path TEXT,
    taken TEXT, ts INTEGER, day TEXT, year INTEGER, month INTEGER, md TEXT,
    w INTEGER, h INTEGER, fmt TEXT, video INTEGER, duration REAL,
    size INTEGER, rating INTEGER, pick INTEGER, color INTEGER,
    camera TEXT, make TEXT, model TEXT, lens TEXT,
    aperture REAL, focal REAL, focal35 REAL, exposure REAL, iso INTEGER, flash INTEGER,
    lat REAL, lon REAL, alt REAL,
    title TEXT, caption TEXT, creator TEXT, copyright TEXT,
    place TEXT, region TEXT, country TEXT,
    hash TEXT, modified TEXT, mts INTEGER, ntags INTEGER, extra TEXT, edited INTEGER,
    sharp REAL, sharpn REAL, bright REAL, clip_lo REAL, clip_hi REAL, faceq REAL,
    npeople INTEGER, objects TEXT, ocr TEXT, burst INTEGER, burst_best INTEGER, caption_ai TEXT,
    dprec INTEGER, aesth REAL, aesthn REAL, focusn REAL, eyes_checked INTEGER, eyes_closed INTEGER, reject TEXT, jerseys TEXT, focus TEXT
);
CREATE INDEX photos_ts ON photos (ts);
CREATE INDEX photos_day ON photos (day);
CREATE INDEX photos_album ON photos (album_id);
CREATE TABLE tags (id INTEGER PRIMARY KEY, pid INTEGER, name TEXT, full TEXT,
                   person INTEGER, n INTEGER, n_all INTEGER, icon INTEGER);
CREATE TABLE tag_closure (anc INTEGER, tag INTEGER, PRIMARY KEY (anc, tag)) WITHOUT ROWID;
CREATE TABLE photo_tags (tag_id INTEGER, photo_id INTEGER, PRIMARY KEY (tag_id, photo_id)) WITHOUT ROWID;
CREATE INDEX photo_tags_photo ON photo_tags (photo_id);
CREATE TABLE albums (id INTEGER PRIMARY KEY, pid INTEGER, path TEXT, name TEXT, root TEXT,
                     caption TEXT, n INTEGER, n_all INTEGER, cover INTEGER, ts_min INTEGER, ts_max INTEGER,
                     adate TEXT, category TEXT, icon INTEGER);
CREATE TABLE album_closure (anc INTEGER, album INTEGER, PRIMARY KEY (anc, album)) WITHOUT ROWID;
CREATE TABLE faces (photo_id INTEGER, tag_id INTEGER, x INTEGER, y INTEGER, w INTEGER, h INTEGER, kind TEXT DEFAULT 'confirmed');
CREATE INDEX faces_kind ON faces (kind);
CREATE INDEX faces_photo ON faces (photo_id);
CREATE INDEX faces_tag ON faces (tag_id);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE pending_seen (photo_id INTEGER PRIMARY KEY, stamp INTEGER);
CREATE VIRTUAL TABLE fts USING fts5(
    name, album, title, caption, tags, people, camera, misc, ocr, caption_ai, speech,
    tokenize = "unicode61 remove_diacritics 2", prefix = '1 2 3'
);
"""

PICK = {"Pick Label None": 0, "Pick Label Rejected": 1, "Pick Label Pending": 2, "Pick Label Accepted": 3}
COLORS = ["None", "Red", "Orange", "Yellow", "Green", "Blue", "Magenta", "Gray", "Black", "White"]
COLOR = {f"Color Label {n}": i for i, n in enumerate(COLORS)}
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
SPECIAL_PERSON_PROPS = ("unknownPerson", "ignoredPerson", "unconfirmedPerson")
SCHEMA_VERSION = "18"  # 10: folder date, category and chosen cover; 11: AI descriptions without filler; 12: dprec (approximate dates); 13: photo quality (aesthetic, focus, eyes, likely rejects); 14: text in photos kept to words (ocrwords); 15: jersey numbers; 16: focus point for cropped thumbnails; 17: speech in videos (fts column); 18: pending_seen (the remembered edits the index reflects) and the version's parts, for updates in place
RECT_RE = re.compile(r'x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)"')


def source_version() -> str:
    """Changes whenever digiKam writes to its database."""
    return dkdb.source_version(quick=True)  # the watcher's 20-second poll: the cheap check first (dkdb)


def sync_enabled() -> bool:
    return dkdb.sync_enabled()


# whether digiKam's database answered the last time it was needed, and what the index was last built from
offline = {"since": None, "error": None, "checked": None}
last_source = {"kind": None, "version": None}
_offline_lock = threading.Lock()


def _set_online():
    with _offline_lock:
        if offline["since"]:
            log.info("digiKam's database is reachable again")
        offline.update(since=None, error=None, checked=int(time.time()))


def _set_offline(err):
    with _offline_lock:
        if not offline["since"]:
            log.warning("digiKam's database is unreachable; working from the viewer's copy of the library: %s", err)
            offline["since"] = int(time.time())
        offline.update(error=str(err)[:jobs.ERROR_TEXT_MAX], checked=int(time.time()))


def mirror_info() -> dict:
    """{source, taken, photos, local_changes} of the library tables, or None when they were never filled."""
    d = library.info()
    if not d.get("taken"):
        return None
    return {"source": d.get("source"), "taken": int(d.get("taken") or 0), "photos": int(d.get("photos") or 0),
            "local_changes": int(d.get("local_changes") or 0), "changed": int(d.get("changed") or 0) or None}


conflict = {"digikam": None}  # digiKam's version while the library holds changes made with sync off


def probe() -> tuple:
    """Where the next build reads from. ('digikam', its version): sync on, digiKam answers, and the library
    holds nothing digiKam lacks; the library tables are refreshed from it first. ('library', their version):
    sync off, digiKam unreachable, or changes made with sync off that a copy would overwrite. With no digiKam
    at all, a library never filled is started fresh first."""
    m = mirror_info()
    if not m and dkdb.no_digikam() and library.start_new():
        m = mirror_info()
    if sync_enabled():
        try:
            v = dkdb.source_version()
            _set_online()
            if m and m["local_changes"]:
                conflict["digikam"] = v
                return "library", library.version()
            conflict["digikam"] = None
            return "digikam", v
        except SOURCE_ERRORS as e:
            _set_offline(e)
    if not m:
        raise Unavailable("digiKam's database cannot be read and the viewer has no copy of the library yet"
                          + (f": {offline['error']}" if offline.get("error") and sync_enabled() else " (Sync with digiKam is off)"))
    return "library", library.version()


def status() -> dict:
    """For /api/status and the banner."""
    m = mirror_info()
    return {"sync": sync_enabled(), "none": dkdb.no_digikam(), "reachable": offline["since"] is None, "since": offline["since"], "error": offline["error"],
            "source": last_source["kind"], "mirror": m, "localChanges": (m or {}).get("local_changes", 0),
            "conflict": bool(conflict["digikam"]) and sync_enabled()}


# ---- the rows the index is built from, read with digiKam's table names (from the library tables)
IMAGE_SQL = """
    SELECT i.id, i.album, i.name, i.fileSize, i.uniqueHash, i.modificationDate, i.category,
           ii.rating, ii.creationDate, ii.orientation, ii.width, ii.height, ii.format,
           m.make, m.model, m.lens, m.aperture, m.focalLength, m.focalLength35, m.exposureTime,
           m.sensitivity, m.flash, m.whiteBalance, m.meteringMode, m.exposureProgram,
           p.latitudeNumber, p.longitudeNumber, p.altitude, p.orientation AS gpsOrientation, p.accuracy AS gpsAccuracy,
           v.duration, v.videoCodec, v.frameRate, v.audioCompressor, v.aspectRatio
    FROM Images i
    LEFT JOIN ImageInformation ii ON ii.imageid = i.id
    LEFT JOIN ImageMetadata m ON m.imageid = i.id
    LEFT JOIN ImagePositions p ON p.imageid = i.id
    LEFT JOIN VideoMetadata v ON v.imageid = i.id
    WHERE i.status = 1 AND i.album IS NOT NULL AND i.category IN (1, 2)
"""


def read_rows(src, ids=None) -> dict:
    """One consistent snapshot of what the index needs, through a connection that speaks digiKam's names. With
    `ids`, the per-photo tables hold only those photos' rows (the index updated in place); the albums and the
    tags are small and always read whole."""
    src.begin_read()
    try:
        q = src.execute

        def per_photo(sql: str) -> list:
            """The rows of a per-photo table: all of them, or those of `ids` ({only} / {also} in the SQL)."""
            if ids is None:
                return [tuple(r) for r in q(sql.format(only="", also=""))]
            out = []
            for part in chunked(sorted(int(i) for i in ids), 500):
                inlist = ",".join(map(str, part))
                col = "i.id" if "FROM Images i" in sql else "imageid"
                out += [tuple(r) for r in q(sql.format(only=f" WHERE {col} IN ({inlist})", also=f" AND {col} IN ({inlist})"))]
            return out

        return {
            "roots": [tuple(r) for r in q("SELECT id, label, specificPath FROM AlbumRoots")],
            "albums": [tuple(r) for r in q("SELECT id, albumRoot, relativePath, caption, date, collection, icon FROM Albums")],
            "tags": [tuple(r) for r in q("SELECT id, pid, name, icon FROM Tags")],
            "tagprops": [tuple(r) for r in q("SELECT tagid, property, value FROM TagProperties")],
            # in one order whichever database answers (digiKam's or the copy): a photo's tags and faces are listed the same
            # by a full build and by an update in place
            "imagetags": sorted(per_photo("SELECT imageid, tagid FROM ImageTags{only}")),
            "regions": sorted(per_photo("SELECT imageid, tagid, property, value FROM ImageTagProperties "
                                        "WHERE property IN ('tagRegion', 'autodetectedFace', 'ignoredFace'){also}"),
                              key=lambda r: (r[0], r[1], r[2], r[3] or "")),
            "comments": sorted(per_photo("SELECT id, imageid, type, comment, language, author FROM ImageComments{only} ORDER BY id"), key=lambda r: r[0]),
            "copyright": per_photo("SELECT imageid, property, value FROM ImageCopyright{only}"),
            "props": per_photo("SELECT imageid, property, value FROM ImageProperties{only}"),
            "images": per_photo(IMAGE_SQL + "{also}"),
        }
    finally:
        src.rollback()


_copy_lock = threading.Lock()
_copy_wanted = threading.Event()


def refresh_library_soon():
    """Bring the viewer's copy of the library up to date in the background, one copy at a time; changes that
    arrive meanwhile are folded into one more copy. Skipped when sync was turned off since, or when the copy
    holds changes made with sync off (those are merged, never overwritten)."""
    _copy_wanted.set()
    if _copy_lock.locked():
        return

    def run():
        with _copy_lock:
            while _copy_wanted.is_set():
                _copy_wanted.clear()
                try:
                    m = mirror_info()
                    if not sync_enabled() or (m and m["local_changes"]):
                        return
                    if m and m["source"] == dkdb.source_version():
                        continue
                    refresh_library()
                except SOURCE_ERRORS as e:
                    log.info("the library copy was not refreshed (digiKam unreachable): %s", e)
                except Exception as e:
                    log.warning("the library copy was not refreshed: %s", e, exc_info=True)
    threading.Thread(target=run, name="library-copy", daemon=True).start()


def refresh_library():
    """Copy digiKam's tables into the library tables (one snapshot, one transaction)."""
    src = dkdb.connect(write=False, real=True)
    try:
        src.begin_read()
        library.copy_from_digikam(src)
    finally:
        src.rollback()
        src.close()


def mirror_tag_paths(photo_ids: list) -> dict:
    """{photo id: [tag paths]} from the library tables (every tag but digiKam's internal ones)."""
    ids = [int(x) for x in photo_ids]
    con = library.connect()
    try:
        tags = dkdb.tag_tree(con)
        internal = {r[0] for r in con.execute("SELECT tagid FROM TagProperties WHERE property = 'internalTag'").fetchall()}
        out = {}
        for iid, tid in in_chunks(con, "SELECT imageid, tagid FROM ImageTags WHERE imageid IN ({ids})", ids):
            if tid in tags and tid not in internal:
                out.setdefault(iid, []).append(dkdb.tag_path(tags, tid))
    finally:
        con.close()
    return {iid: out.get(iid, []) for iid in ids}


# ---- photo_ids: the viewer's identity for a photo, and viewer data following a renumbered photo
REKEY = [("pix_favorite_photos", "photo_id"), ("pix_album_photos", "photo_id"), ("pix_pending_edits", "photo_id"), ("pix_ai_scans", "photo_id"), ("pix_ai_quality", "photo_id"),
         ("pix_ai_text", "photo_id"), ("pix_ai_face_count", "photo_id"), ("pix_ai_objects", "photo_id"), ("pix_ai_descriptions", "photo_id"), ("pix_ai_looks", "photo_id"), ("pix_ai_face_ages", "photo_id"), ("pix_ai_face_embeddings", "photo_id"),
         ("pix_ai_person_references", "photo_id"), ("pix_metadata_check", "photo_id"), ("pix_image_data_checksums", "photo_id"), ("pix_photo_history", "photo_id"), ("pix_quality_accepted", "photo_id"),
         ("pix_ai_similar_photos", "photo_id"), ("pix_ai_similar_photos", "similar_photo_id")]


REJECT_REASONS = {"blur": "Blurry all over", "eyes": "Eyes closed", "burst": "A better frame of the same burst exists", "exposure": "Nearly black or blown out"}


def likely_rejects(con, bursts: dict) -> list:
    """[(reasons, photo id)] for the photos that look like rejects, from the measures already in the index
    (con: the index being built). Reasons, comma-separated (REJECT_REASONS): blurry all over (in the
    least sharp twentieth by focus, or by overall sharpness when focus is not measured yet, and no
    sharp face), closed eyes on most of the faces judged, a clearly worse frame of a burst, or nearly
    black or mostly blown out. Only a suggestion: nothing is marked until the user does it."""
    out = []
    for pid, focusn, sharpn, faceq, judged, closed, bright, clip_lo, clip_hi in con.execute(
            "SELECT id, focusn, sharpn, faceq, eyes_checked, eyes_closed, bright, clip_lo, clip_hi FROM photos WHERE video = 0"):
        why = []
        soft = focusn if focusn is not None else sharpn
        if soft is not None and soft < 0.05 and (faceq is None or faceq < 0.35):
            why.append("blur")
        if judged and closed and closed * 2 > judged:
            why.append("eyes")
        if pid in bursts and bursts[pid][2]:
            why.append("burst")
        if bright is not None and (bright < 0.06 or (clip_lo or 0) > 0.75 or (clip_hi or 0) > 0.5):
            why.append("exposure")
        if why:
            out.append((",".join(why), pid))
    return out


def sync_photo_ids(images: list, paths: dict) -> dict:
    """images: the raw image rows just read from digiKam; paths: {digiKam id: full path}. Gives every
    photo a viewer id once, and when a file (same uniqueHash and size) comes back under another digiKam
    id, moves the viewer's rows about it to the new id. Returns {old digiKam id: new} for what moved."""
    now = int(time.time())
    current = {}
    for r in images:
        iid, name, size, uhash = r[0], r[2], r[3], r[4]
        if uhash:
            current[iid] = (uhash, size, paths.get(iid), name)
    with appstate.lock:
        con = appstate.connect()
        try:
            rows = con.execute("SELECT id, dk_id, hash, size, path, name, last_seen_at FROM pix_photo_identity").fetchall()
            by_key, by_dk, stored = {}, {}, {}
            for vid, dk, h, sz, pth, nm, seen in rows:
                by_key.setdefault((h, sz), []).append((vid, dk))
                stored[vid] = (dk, pth, nm, seen or 0)
                if dk is not None:
                    by_dk[dk] = (vid, h, sz)
            inserts, updates, rewritten, touched, remap = [], [], [], [], {}
            # only what changed is written: on MySQL every statement is a round trip, and a statement per photo
            # on every build (30,000 of them) made each rebuild seconds slower. last_seen is refreshed daily.
            for dk, (h, sz, path, name) in current.items():
                known = by_key.get((h, sz))
                match = next(((v, d) for v, d in known if d == dk), None) if known else None
                if match is None and known:
                    # the same bytes under another number: that photo's row follows it only when its old number is
                    # gone (digiKam renumbered it); while both numbers exist they are two copies, each its own photo
                    match = next(((v, d) for v, d in known if d is None or d not in current), None)
                if match:
                    vid, old = match
                    if old != dk and old is not None and old not in current:
                        remap[old] = dk  # the same file under a new number
                    was = stored.get(vid)
                    if not was or was[0] != dk or was[1] != path or was[2] != name:
                        updates.append((dk, path, name, now, vid))
                    elif now - was[3] > 7 * 86400:  # seen again: a weekly touch, in bulk (30,000 single UPDATEs took tens of seconds on MySQL)
                        touched.append(vid)
                elif dk in by_dk and stored[by_dk[dk][0]][1] == path:
                    # the same file under the same number, rewritten in place (metadata written into it, a lossless
                    # rotate or crop, digiKam's rescan after one): the photo keeps its viewer id
                    rewritten.append((h, sz, name, now, by_dk[dk][0]))
                else:  # new, or the number now stands for another file: that is a different photo
                    inserts.append((dk, h, sz, path, name, now, now))
            if remap:
                rekey(con, remap)
            # a number that now belongs to a different file is taken away from the row that had it
            kept = {vid for _h, _s, _n, _t, vid in rewritten}
            taken = [(vid,) for dk, (vid, h, sz) in by_dk.items() if dk in current and (h, sz) != current[dk][:2] and vid not in kept]
            if rewritten:
                con.executemany("UPDATE pix_photo_identity SET hash = ?, size = ?, name = ?, last_seen_at = ? WHERE id = ?", rewritten)
            if taken:
                con.executemany("UPDATE pix_photo_identity SET dk_id = NULL WHERE id = ?", taken)
            if updates:
                con.executemany("UPDATE pix_photo_identity SET dk_id = ?, path = ?, name = ?, last_seen_at = ? WHERE id = ?", updates)
            for part in chunked(touched, 500):
                con.execute(f"UPDATE pix_photo_identity SET last_seen_at = ? WHERE id IN ({','.join('?' * len(part))})", (now, *part))
            if inserts:
                con.executemany("INSERT INTO pix_photo_identity (dk_id, hash, size, path, name, first_seen_at, last_seen_at) VALUES (?,?,?,?,?,?,?)", inserts)
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()
    if remap:
        log.warning("digiKam renumbered %d photos; the viewer's data about them follows: %s", len(remap),
                    ", ".join(f"{a}->{b}" for a, b in list(remap.items())[:10]))
        try:
            from app.ai import semantic  # lazy: ai.semantic -> thumbs -> photos.edits -> data.index would be an import cycle
            semantic.remap_ids(remap)
        except Exception as e:  # the embeddings are recomputed for those photos instead
            log.warning("content-search embeddings were not renumbered (%s); they are recomputed", e)
    return remap


def rekey(con, remap: dict):
    """Move the viewer's rows about renumbered photos to their new ids, in two passes through negative
    ids so a swap of two numbers cannot collide. A row already under a new id that belongs to a photo
    which is gone for good is dropped first (its photo no longer exists under any id)."""
    targets = set(remap.values()) - set(remap)
    for table, col in REKEY:
        if targets:
            con.execute(f"DELETE FROM {table} WHERE {col} IN ({','.join(map(str, targets))})")
        con.executemany(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", [(-new, old) for old, new in remap.items()])
        con.execute(f"UPDATE {table} SET {col} = -{col} WHERE {col} < 0")


def open_index(path: Path = config.INDEX_DB) -> sqlite3.Connection:
    """A read-only connection to the index (plain tuples; callers wanting rows set row_factory)."""
    return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)


def parse_dt(s):
    """digiKam stores naive local 'YYYY-MM-DDTHH:MM:SS.mmm'. The timestamp we
    keep is that wall-clock time as if it were UTC, so it sorts and displays
    as the time on the camera."""
    if not s:
        return None
    try:
        y, mo, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        hh, mi, ss = (int(s[11:13]), int(s[14:16]), int(s[17:19])) if len(s) >= 19 else (0, 0, 0)
        return calendar.timegm((y, mo, d, hh, mi, ss)), y, mo, d
    except (ValueError, IndexError):
        return None


def _camera(make, model):
    make, model = (make or "").strip(), (model or "").strip()
    if not model:
        return make or None
    first = make.split(" ")[0].lower() if make else ""
    if not make or model.lower().startswith(first):
        return model
    short = {"OLYMPUS CORPORATION": "Olympus", "OM Digital Solutions": "OM System",
             "NIKON CORPORATION": "Nikon", "EASTMAN KODAK COMPANY": "Kodak"}.get(make, make)
    return f"{short} {model}"


_build_lock = threading.Lock()  # one build at a time in this process: the watcher, a request and the MCP server can all ask
class _Hidden:
    """Photos on their way to the trash: out of the index at once (drop_photos), and out of every build until a build
    that STARTED after their move finished has been swapped in. Letting go as soon as the move was done was a gap: a
    build that had read digiKam's rows before the move, and finished after it, put the photo back until the next build.
    Behaves as the set it used to be (add, discard, update, difference_update, in, iteration) plus release() and let_go()."""

    def __init__(self):
        self._t: dict = {}  # id -> None while the move runs, else the time the move finished

    def add(self, i): self._t[int(i)] = None
    def discard(self, i): self._t.pop(int(i), None)
    def update(self, ids):
        for i in ids:
            self.add(i)
    def difference_update(self, ids):
        for i in ids:
            self.discard(i)
    def release(self, ids):
        """The move of these photos is done: the first build that starts from now on reads rows that know it."""
        now = time.time()
        for i in ids:
            if int(i) in self._t:
                self._t[int(i)] = now
    def let_go(self, started: float):
        """Called by a build that started at `started`, once it is in: photos released before that are no longer hidden."""
        for i, t in list(self._t.items()):
            if t is not None and t < started:
                self._t.pop(i, None)
    def __contains__(self, i): return int(i) in self._t
    def __iter__(self): return iter(list(self._t))
    def __len__(self): return len(self._t)
    def __bool__(self): return bool(self._t)


HIDDEN = _Hidden()


def _drop(con, ids):
    """Delete these photos from an index database (the photo rows, their tags, faces and text)."""
    ids = sorted(int(i) for i in ids)
    for part in chunked(ids, 900):
        q = ",".join("?" * len(part))
        for table, col in (("photos", "id"), ("photo_tags", "photo_id"), ("faces", "photo_id"), ("fts", "rowid")):
            con.execute(f"DELETE FROM {table} WHERE {col} IN ({q})", part)


def drop_photos(ids, dst_path: Path = config.INDEX_DB):
    """Take photos out of the live index now (moved to the trash in the background); builds leave them out
    too until HIDDEN lets go of them, once digiKam's rows say where they are."""
    if not dst_path.exists():
        raise RuntimeError("the index is not built yet")
    con = sqlite3.connect(str(dst_path), timeout=15)
    try:
        con.execute("PRAGMA journal_mode = MEMORY")  # no journal file beside an index that readers open read-only and a build replaces
        _drop(con, ids)
        con.commit()
    finally:
        con.close()
    HIDDEN.update(int(i) for i in ids)  # only once they are out: a failed drop hides nothing


def build(dst_path: Path = config.INDEX_DB, source: tuple = None) -> dict:
    """Read everything the index needs, from digiKam's database (and refresh the viewer's copy of it)
    or from that copy when digiKam cannot be read, then write a fresh index file and swap it in.
    Returns the stats also stored in the index's meta table."""
    with _build_lock:
        stats = _build(dst_path, source)
    if stats["resolved_edits"] and Path(dst_path) == config.INDEX_DB:  # digiKam now agrees with these edits; stop tracking them
        _settle(Path(dst_path), stats)
    return stats


def _settle(dst_path: Path, stats: dict):
    """After a build or an update in place that found edits digiKam has caught up with: they are forgotten, which
    changes the edits' signature, a part of the version the index was just stamped with. The stamp and the edits
    the index says it reflects (pending_seen) follow, or ensure_fresh would do the same work once more. Outside
    the build lock: forgetting an edit takes the edits' lock, which a caller of build() may hold."""
    edits.resolved(stats["resolved_edits"], stats.get("resolved_snapshot"))
    stamps, now = stats["stamps"], edits.pending_stamps()
    gone = [i for i, st in stamps.items() if now.get(i) != st]  # forgotten, or edited again meanwhile (then seen as changed)
    parts = {**stats["parts"], "edits": edits.signature_of(now)}
    try:
        con = sqlite3.connect(str(dst_path), timeout=15, isolation_level=None)
        try:
            con.execute("PRAGMA journal_mode = MEMORY")
            con.execute("BEGIN IMMEDIATE")
            if con.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()[0] == stats["version"]:  # still the index this is about
                con.executemany("DELETE FROM pending_seen WHERE photo_id = ?", [(i,) for i in gone])
                if all(stamps.get(i) == st for i, st in now.items()):  # nothing new since: the index reflects exactly the edits there are now
                    con.execute("UPDATE meta SET value = ? WHERE key = 'version'", (":".join(parts.values()),))
                    con.execute("UPDATE meta SET value = ? WHERE key = 'parts'", (json.dumps(parts),))
            con.execute("COMMIT")
        finally:
            con.close()
    except sqlite3.Error as e:
        log.warning("the index version was not restamped after resolving edits (%s); one more update follows", e)


def _read_source(source: tuple):
    """The rows the index is built from. Returns (kind, version, raw rows, {root id: path}, read straight from digiKam)."""
    kind, ver = source or probe()
    raw = root_path = None
    if kind == "digikam":
        m = mirror_info()
        try:
            if not m:  # the very first copy: taken now, and the index is read from it
                refresh_library()
            elif m["source"] != ver:
                # digiKam changed (often a change made here a moment ago): the index is read from digiKam
                # itself, and the viewer's copy of the library follows in the background. Copying first put
                # several seconds (on MariaDB) between a change and its showing up.
                src = dkdb.connect(write=False, real=True)
                try:
                    raw = read_rows(src)
                    root_path = dkdb.root_paths(src)
                finally:
                    src.close()
                refresh_library_soon()
        except SOURCE_ERRORS as e:
            _set_offline(e)
            if not m:
                raise Unavailable(f"digiKam's database cannot be read and the viewer has no copy of the library yet: {e}") from e
            kind, ver, raw = "library", library.version(), None
    direct = raw is not None  # read straight from digiKam (the copy follows), or from the copy
    if raw is None:
        con = library.connect()
        try:
            raw = read_rows(con)
            root_path = dkdb.root_paths(con)
        finally:
            con.close()
    return kind, ver, raw, root_path, direct


def _album_rows(raw: dict) -> dict:
    """{album id: {id, root, rel, caption, label, date, category, icon, pid, name, path}} for the albums under a known root."""
    roots = {r[0]: r[1] for r in raw["roots"]}
    single_root = len(roots) == 1
    albums = {}
    for aid, root, rel, caption, adate, collection, icon in raw["albums"]:
        if root in roots:
            albums[aid] = {"id": aid, "root": root, "rel": rel, "caption": caption or None, "label": roots[root],
                           "date": str(adate)[:10] if adate else None, "category": collection or None, "icon": icon}
    by_path = {(a["root"], a["rel"]): aid for aid, a in albums.items()}
    for a in albums.values():
        rel = a["rel"]
        if rel == "/":
            a["pid"], a["name"] = None, a["label"] or "Library"
        else:
            parent = rel.rsplit("/", 1)[0] or "/"
            a["pid"], a["name"] = by_path.get((a["root"], parent)), rel.rsplit("/", 1)[1]
        a["path"] = rel if single_root else f"/{a['label']}{'' if rel == '/' else rel}"
    return albums


def _tag_rows(raw: dict):
    """Every tag with its ancestors, full path and person flag. Returns (tags, props, internal, special, hidden):
    hidden tags (digiKam's internal ones and the special face tags) are kept out of the index."""
    # icon: the photo digiKam shows for the tag ("Set as Tag Thumbnail"); for people it is the face on that photo
    tags = {tid: {"id": tid, "pid": pid, "name": name, "icon": icon} for tid, pid, name, icon in raw["tags"]
            if tid != 0}  # MySQL's "_Digikam_root_tag_" row; pid 0 means "no parent" on both backends
    props = defaultdict(set)
    for tid, prop, _ in raw["tagprops"]:
        props[tid].add(prop)

    def ancestors(tid):
        out, seen = [], set()
        cur = tags.get(tid, {}).get("pid")
        while cur and cur in tags and cur not in seen:
            seen.add(cur)
            out.append(cur)
            cur = tags[cur]["pid"]
        return out

    internal_roots = {tid for tid, t in tags.items()
                      if t["name"] == "_Digikam_Internal_Tags_" and not t["pid"]}
    internal = {tid for tid in tags if tid in internal_roots or internal_roots & set(ancestors(tid))
                or "internalTag" in props[tid]}
    special = {tid for tid in tags if props[tid] & set(SPECIAL_PERSON_PROPS)}
    hidden = internal | special
    for tid, t in tags.items():
        t["anc"] = ancestors(tid)
        t["full"] = "/".join(tags[x]["name"] for x in reversed([tid] + t["anc"]))
        t["person"] = 1 if "person" in props[tid] and tid not in hidden else 0
    return tags, props, internal, special, hidden


def _side_tables(raw: dict, tags: dict, props: dict, internal: set, special: set, hidden: set) -> dict:
    """What digiKam keeps in side tables, keyed by image id: tags, pick and color labels, faces, title and caption,
    copyright fields and the other properties."""
    img_tags, pick, color = defaultdict(list), {}, {}
    for iid, tid in raw["imagetags"]:
        t = tags.get(tid)
        if not t:
            continue
        if t["name"] in PICK and tid in internal:
            pick[iid] = PICK[t["name"]]
        elif t["name"] in COLOR and tid in internal:
            color[iid] = COLOR[t["name"]]
        elif tid not in hidden:
            img_tags[iid].append(tid)

    faces = []
    # every kind of face digiKam knows: confirmed regions, faces it found but could not name
    # (on its "Unknown" tag), suggestions it is not sure about, and faces told to ignore
    unknown_tag = next((tid for tid in special if "unknownPerson" in props[tid]), None)
    ignored_tag = next((tid for tid in special if "ignoredPerson" in props[tid]), None)
    for iid, tid, prop, val in raw["regions"]:
        m = RECT_RE.search(val or "")
        if not m or tid not in tags:
            continue
        rect = tuple(map(int, m.groups()))
        if prop == "tagRegion" and tid not in hidden:
            faces.append((iid, tid, *rect, "confirmed"))
            if tid not in img_tags[iid]:
                img_tags[iid].append(tid)
            tags[tid]["person"] = 1
        elif prop == "autodetectedFace" and tid == unknown_tag:
            faces.append((iid, tid, *rect, "unknown"))
        elif prop == "autodetectedFace" and tid not in hidden:
            faces.append((iid, tid, *rect, "suggested"))
        elif prop == "ignoredFace" and tid == ignored_tag:
            faces.append((iid, tid, *rect, "ignored"))

    # digiKam's caption is type 1 and its title type 3 (2 is a headline, not shown); the x-default entry (the one the
    # viewer edits and digiKam shows first), the authorless one if there are several; other languages are not shown
    title, caption, rank = {}, {}, {}
    for row in raw["comments"]:
        _, iid, typ, text = row[:4]
        lang, author = (row[4] if len(row) > 4 else "x-default"), (row[5] if len(row) > 5 else None)
        if typ not in (1, 3) or not (text and text.strip()) or lang != "x-default":
            continue
        r = 0 if not author else 1
        key = (iid, typ)
        if key not in rank or r < rank[key]:
            rank[key] = r
            (title if typ == 3 else caption)[iid] = text.strip()
    copyright_ = defaultdict(dict)
    for iid, prop, val in raw["copyright"]:
        if val and val.strip():
            copyright_[iid].setdefault(prop, val.strip())
    iprops = defaultdict(dict)
    for iid, prop, val in raw["props"]:
        if val and val.strip() and set(val) - set("?, "):
            iprops[iid][prop] = val.strip()
    return {"img_tags": img_tags, "pick": pick, "color": color, "faces": faces, "title": title, "caption": caption,
            "copyright": copyright_, "iprops": iprops}


def _edit_done(e: dict, db: dict, add: list, rem: list, unknown_tags: bool) -> bool:
    """Whether digiKam's database already holds everything a pending edit asked for (then the edit is resolved)."""
    g = e.get("gps")
    lat_db, lon_db, alt_db = db["lat"], db["lon"], db["alt"]
    gps_same = ("gps" not in e or (g is None and lat_db is None)
                or (g is not None and lat_db is not None and abs(g["lat"] - lat_db) < 1e-6 and abs(g["lon"] - lon_db) < 1e-6
                    and ((g.get("alt") is None and alt_db is None)
                         or (g.get("alt") is not None and alt_db is not None and abs(float(g["alt"]) - float(alt_db)) < 0.05))))
    dbcr, tids = db["copyright"], db["tids"]
    return (("rating" not in e or e["rating"] == db["rating"])
            and ("taken" not in e or e["taken"] == (db["taken"] or "")[:19])
            and gps_same
            and ("template" not in e or all((dbcr.get(k) or "") == (v or "") for k, v in e["template"].items()))
            and ("pick" not in e or e["pick"] == db["pick"]) and ("color" not in e or e["color"] == db["color"])
            and ("title" not in e or (e["title"] or None) == db["title"])
            and ("caption" not in e or (e["caption"] or None) == db["caption"])
            and all(t in tids for t in add) and not any(t in tids for t in rem) and not unknown_tags)


def _photo_rows(raw: dict, albums: dict, root_path: dict, tags: dict, hidden: set, side: dict, geo, phases: dict, ids=None):
    """One row per photo for the photos, fts and photo_tags tables, with the viewer's pending edits overlaid
    (edits made here live in sidecars; they show until digiKam's database catches up). Returns a namespace with
    the rows, the per-tag and per-album counts, and the edits digiKam has caught up with. `ids`: the photos `raw`
    was read for (an update in place), so the analysis results are read for those only."""
    out = SimpleNamespace(photos=[], fts_rows=[], photo_tag_rows=[], burst_rows=[], resolved=[], resolved_snapshot={},
                          tag_direct=defaultdict(set), tag_all=defaultdict(set), album_n=defaultdict(int))
    img_tags, pick, color, title, caption, copyright_, iprops = (side[k] for k in ("img_tags", "pick", "color", "title", "caption", "copyright", "iprops"))
    t1 = time.time()
    pending = edits.pending()
    seen = analysis.results(ids)  # sharpness, OCR text, objects... from the app's own analysis
    for pid, nums in jerseys.results(ids).items():  # the numbers read on shirts, searchable as jersey=10
        seen.setdefault(pid, {})["jerseys"] = nums
    for pid, text in videos.transcripts(ids).items():  # what is said in videos, searchable
        seen.setdefault(pid, {})["speech"] = text
    phases["analysis"] = time.time() - t1
    faces_by = defaultdict(list)  # the faces that place a cropped thumbnail (smartcrop.py): not the ones marked ignored
    for f in side["faces"]:
        if f[6] != "ignored":
            faces_by[f[0]].append(f[2:6])
    tag_by_full = {t["full"]: tid for tid, t in tags.items() if tid not in hidden}
    # approximate dates (dateprecision.py): the tag that says how much of a photo's date is known
    prec_tags = {tag_by_full[full]: dateprecision.LEVELS[k] for k, full in dateprecision.TAGS.items() if full in tag_by_full}
    for (iid, album_id, name, size, uhash, mod, category, rating, created, orient, w, h, fmt,
         make, model, lens, aperture, focal, focal35, exposure, iso, flash, wb, metering, program,
         lat, lon, alt, gps_orientation, gps_accuracy, duration, vcodec, fps, acodec, aspect) in raw["images"]:
        album = albums.get(album_id)
        if not album:
            continue
        created_db, lat_db, lon_db, alt_db = created, lat, lon, alt  # digiKam's own values, before any pending edit is overlaid
        e0 = pending.get(iid)
        if e0 and "taken" in e0:
            created = e0["taken"]
        if e0 and "gps" in e0:
            lat, lon, alt = (e0["gps"]["lat"], e0["gps"]["lon"], e0["gps"].get("alt")) if e0["gps"] else (None, None, None)
            gps_accuracy = (e0["gps"] or {}).get("accuracy")
        mdt = parse_dt(mod)
        ts, y, mo, d = parse_dt(created) or mdt or (0, 1970, 1, 1)
        if not w or not h:
            w, h = 4, 3
        if orient in (5, 6, 7, 8):  # stored size is unrotated; keep the displayed size
            w, h = h, w
        video = 1 if category == 2 else 0
        try:
            dur = float(duration) / 1000.0 if duration not in (None, "") else None
        except ValueError:
            dur = None
        if lat is not None and lon is not None and lat == 0 and lon == 0:
            lat = lon = None
        loc = geo.lookup(lat, lon) if geo and lat is not None else None
        cam = _camera(make, model)
        lens = (lens or "").strip() or None
        tids = img_tags.get(iid, [])
        rating = rating if rating is not None else -1
        p_pick, p_color, p_title, p_caption, edited = pick.get(iid, 0), color.get(iid, 0), title.get(iid), caption.get(iid), 0
        e = pending.get(iid)
        if e:
            add = [tag_by_full[t] for t in e.get("add_tags", []) if t in tag_by_full]
            rem = [tag_by_full[t] for t in e.get("remove_tags", []) if t in tag_by_full]
            # a tag path digiKam does not have (yet): the edit is not done, whatever the rest says
            unknown_tags = any(t not in tag_by_full for t in e.get("add_tags", []))  # (removing a tag digiKam lacks is done)
            db = {"rating": rating, "taken": created_db, "lat": lat_db, "lon": lon_db, "alt": alt_db, "copyright": copyright_.get(iid, {}),
                  "pick": p_pick, "color": p_color, "title": p_title, "caption": p_caption, "tids": tids}
            if _edit_done(e, db, add, rem, unknown_tags):
                out.resolved.append(iid)
                out.resolved_snapshot[iid] = e
            else:
                edited = 1
                rating = e.get("rating", rating)
                p_pick, p_color = e.get("pick", p_pick), e.get("color", p_color)
                p_title = (e["title"] or None) if "title" in e else p_title
                p_caption = (e["caption"] or None) if "caption" in e else p_caption
                tids = [t for t in tids if t not in rem] + [t for t in add if t not in tids]
        dprec = max((prec_tags[t] for t in tids if t in prec_tags), default=None)
        cr = dict(copyright_.get(iid, {}))
        if e0 and "template" in e0:
            for k, v in e0["template"].items():
                if v:
                    cr[k] = v
                else:
                    cr.pop(k, None)
        extra = {}
        if cr:
            extra["copyright"] = cr
        if iid in iprops:
            extra["properties"] = iprops[iid]
        if video:
            extra["video"] = {k: v for k, v in (("codec", vcodec), ("fps", fps), ("audio", acodec)) if v}
        if gps_orientation is not None:
            extra["orientationGps"] = gps_orientation  # compass direction the camera faced, when the file records it
        if gps_accuracy and lat is not None:
            extra["gpsAccuracy"] = gps_accuracy  # metres: an approximate position (only the town known, say)
        for k, v in (("whiteBalance", wb), ("metering", metering), ("program", program), ("orientation", orient)):
            if v is not None:
                extra[k] = v
        rel = album["rel"].rstrip("/") + "/" + name
        an = seen.get(iid, {})
        # a placeholder date is shared by many photos: no bursts among them (left out like videos)
        out.burst_rows.append((iid, ts, name, f"{cam}|{w}x{h}", an.get("sharp"), an.get("faceq"), video or dprec,
                               an.get("focus"), an.get("aesth"), an.get("eyes_checked"), an.get("eyes_closed")))
        out.photos.append((
            iid, album_id, name, root_path[album["root"]] + rel,
            # an approximate date has no day of the year to show On this day
            (created or mod or "")[:19], ts, f"{y:04d}-{mo:02d}-{d:02d}", y, mo, None if dprec else f"{mo:02d}-{d:02d}",
            w, h, fmt, video, dur, size, rating,
            p_pick, p_color, cam, (make or "").strip() or None, (model or "").strip() or None,
            lens, aperture, focal, focal35, exposure, iso, flash, lat, lon, alt,
            p_title, p_caption, cr.get("creator"), cr.get("copyrightNotice"),
            *(loc or (None, None, None)),
            uhash, (mod or "")[:19], mdt[0] if mdt else ts, len(tids), json.dumps(extra) if extra else None, edited,
            an.get("sharp"), None, an.get("bright"), an.get("clip_lo"), an.get("clip_hi"), an.get("faceq"),
            an.get("npeople"), ("," + ",".join(sorted(an["objects"])) + ",") if an.get("objects") else None,
            an.get("ocr"), None, None, an.get("caption_ai"), dprec,
            an.get("aesth"), None, None, an.get("eyes_checked"), an.get("eyes_closed"), None, an.get("jerseys"),
            "%s,%s" % smartcrop.focus(w, h, faces_by.get(iid, ()), an.get("persons", ())) if (faces_by.get(iid) or an.get("persons")) else None,
        ))
        out.album_n[album_id] += 1
        people_names, tag_names = [], []
        for tid in tids:
            t = tags[tid]
            out.photo_tag_rows.append((tid, iid))
            out.tag_direct[tid].add(iid)
            out.tag_all[tid].add(iid)
            for a in t["anc"]:
                out.tag_all[a].add(iid)
            (people_names if t["person"] else tag_names).append(t["full"].replace("/", " "))
        extra_words = " ".join(an["objects"]) if an.get("objects") else ""
        misc = extra_words + " " + " ".join(str(x) for x in (
            # only the known part of the date is searchable
            y if (dprec or 0) < 3 else None, MONTHS[mo] if (dprec or 0) < 2 else None, fmt, "video" if video else "photo", lens, cr.get("creator"),
            cr.get("copyrightNotice"), " ".join(iprops.get(iid, {}).values()), *(loc or ())) if x)
        out.fts_rows.append((iid, name, album["path"], p_title, p_caption,
                             " ; ".join(tag_names), " ; ".join(people_names), cam, misc, an.get("ocr"), an.get("caption_ai"), an.get("speech")))
    _clean_ocr(out, tags, albums)
    return out


_COLS = [c.split()[0] for c in re.sub(r"\s+", " ", SCHEMA[SCHEMA.index("(") + 1:SCHEMA.index(");")]).split(",")]  # the photos table's columns, in order
_OCR_COL = _COLS.index("ocr")


def _clean_ocr(out: SimpleNamespace, tags: dict, albums: dict):
    """Text read in photos, kept to what reads as words (ocrwords.py): the library's names, titles and places count
    as words, as does a word read in several photos. The stored text is untouched."""
    texts = [r[_OCR_COL] for r in out.photos]
    if not any(texts) or not ocrwords.dictionary():  # without the word lists (pyspellchecker missing) the text stays as read
        return
    named = [t["name"] for t in tags.values()] + [a.get("name") for a in albums.values()] + [a.get("path") for a in albums.values()]
    named += [x for r in out.photos for x in (r[32], r[33], r[36], r[37], r[38])]  # title, caption, place, region, country
    known = ocrwords.known_words(ocrwords.words_of(named) | ocrwords.corpus(texts))
    cleaned = {r[0]: ocrwords.clean(r[_OCR_COL], known) for r in out.photos if r[_OCR_COL]}
    out.photos[:] = [r if r[0] not in cleaned else (*r[:_OCR_COL], cleaned[r[0]], *r[_OCR_COL + 1:]) for r in out.photos]
    out.fts_rows[:] = [f if f[0] not in cleaned else (*f[:9], cleaned[f[0]], *f[10:]) for f in out.fts_rows]


def _rank(dst, rows: SimpleNamespace, col: str, k: int):
    """A 0..1 rank across the library for an analysis score, so "blurry" means the same everywhere."""
    ranked = sorted((r[k], r[0]) for r in rows.burst_rows if r[k] is not None)
    if ranked:
        dst.executemany(f"UPDATE photos SET {col} = ? WHERE id = ?",
                        [(round(i / max(1, len(ranked) - 1), 4), pid) for i, (_, pid) in enumerate(ranked)])


def _fill(dst, rows: SimpleNamespace, albums: dict, root_path: dict, tags: dict, hidden: set, faces: list):
    """Every table of a new index file, from the rows computed above."""
    dst.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;" + SCHEMA)
    dst.executemany(f"INSERT INTO photos VALUES ({','.join('?' * 66)})", rows.photos)
    dst.executemany("INSERT INTO fts (rowid, name, album, title, caption, tags, people, camera, misc, ocr, caption_ai, speech) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows.fts_rows)
    _rank(dst, rows, "sharpn", 4)
    _rank(dst, rows, "focusn", 7)
    _rank(dst, rows, "aesthn", 8)
    try:
        bursts = moments.find_bursts(rows.burst_rows)
    except Exception:
        bursts = {}
    dst.executemany("UPDATE photos SET burst = ?, burst_best = ? WHERE id = ?", [(b, best, pid) for pid, (b, best, _w) in bursts.items()])
    dst.execute("CREATE INDEX photos_burst ON photos (burst)")
    dst.executemany("UPDATE photos SET reject = ? WHERE id = ?", likely_rejects(dst, bursts))
    dst.executemany("INSERT OR IGNORE INTO photo_tags VALUES (?,?)", rows.photo_tag_rows)
    present = {r[0] for r in rows.photos}
    dst.executemany("INSERT INTO faces VALUES (?,?,?,?,?,?,?)", [f for f in faces if f[0] in present])
    dst.executemany("INSERT INTO tags VALUES (?,?,?,?,?,?,?,?)", [
        (tid, t["pid"] if t["pid"] in tags and t["pid"] not in hidden else None, t["name"], t["full"],
         t["person"], len(rows.tag_direct[tid]), len(rows.tag_all[tid]), t["icon"] if t["icon"] in present else None)
        for tid, t in tags.items() if tid not in hidden])
    dst.executemany("INSERT OR IGNORE INTO tag_closure VALUES (?,?)", [
        (a, tid) for tid, t in tags.items() if tid not in hidden for a in [tid] + t["anc"]])

    # album totals including sub-albums, plus a cover photo
    closure = []
    for aid, a in albums.items():
        cur, seen = aid, set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            closure.append((cur, aid))
            cur = albums[cur]["pid"]
    dst.executemany("INSERT OR IGNORE INTO album_closure VALUES (?,?)", closure)
    dst.executemany("INSERT INTO albums (id, pid, path, name, root, caption, n, adate, category, icon) VALUES (?,?,?,?,?,?,?,?,?,?)", [
        (aid, a["pid"], a["path"], a["name"], root_path[a["root"]], a["caption"], rows.album_n[aid], a["date"], a["category"], a["icon"])
        for aid, a in albums.items()])
    if HIDDEN:  # added to the trash while this build ran: out of the tables too (the counts follow at the next build)
        _drop(dst, set(HIDDEN))
    dst.execute("""
        UPDATE albums SET
          n_all  = (SELECT count(*) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
          ts_min = (SELECT min(ts) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
          ts_max = (SELECT max(ts) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
          cover  = coalesce((SELECT p.id FROM photos p WHERE p.id = albums.icon),  -- the cover chosen in digiKam or here
                            (SELECT p.id FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id
                             ORDER BY p.video, (p.pick = 1), p.rating DESC, p.ts LIMIT 1))
    """)
    dst.execute("DELETE FROM albums WHERE n_all = 0")


def _swap_in(dst_path: Path, fill) -> None:
    """Write a new index file next to the old one (fill(connection) puts the tables in), then swap it in."""
    tmp = dst_path.with_suffix(f".{os.getpid()}-{threading.get_ident()}.tmp")  # another process (the MCP server) may build too
    for p in (tmp, Path(str(tmp) + "-journal")):
        p.unlink(missing_ok=True)
    dst = sqlite3.connect(tmp)
    try:
        fill(dst)
        dst.commit()
        dst.execute("INSERT INTO fts(fts) VALUES ('optimize')")
        dst.commit()
    except BaseException:
        dst.close()
        tmp.unlink(missing_ok=True)  # never leave a half-written index behind
        raise
    dst.close()
    for tail in ("-journal", "-wal", "-shm"):  # a journal left by a crash would be applied to the new file
        try:
            os.unlink(str(dst_path) + tail)
        except OSError:
            pass
    os.replace(tmp, dst_path)


def _build(dst_path: Path, source: tuple) -> dict:
    t0 = time.time()
    geo = places.geocoder()
    with _own_lock:
        own = list(_own)  # the viewer's writes named so far (writing): what they wrote is in the rows read now
    kind, ver, raw, root_path, direct = _read_source(source)
    all_images = raw["images"]  # the renumbering check below sees every photo, hidden ones included (a photo queued for the trash is not "gone")
    if HIDDEN:  # on their way to the trash: left out before anything is counted (digiKam's rows may not say so yet)
        hidden_ids = set(HIDDEN)
        raw["images"] = [r for r in all_images if r[0] not in hidden_ids]
    stamps = edits.pending_stamps()  # before the edits themselves are read: one made meanwhile is seen as changed, never missed
    parts = {**_parts(ver), "edits": edits.signature_of(stamps)}
    version = ":".join(parts.values())
    last_source.update(kind=kind, version=ver)
    phases = {"read": time.time() - t0}

    all_albums = _album_rows(raw)
    if kind == "digikam":
        full_paths = {r[0]: root_path[all_albums[r[1]]["root"]] + all_albums[r[1]]["rel"].rstrip("/") + "/" + r[2]
                      for r in all_images if r[1] in all_albums and all_albums[r[1]]["root"] in root_path}
        try:
            sync_photo_ids(all_images, full_paths)
        except Exception as e:  # bookkeeping only; the index must still be built
            log.warning("photo_ids were not updated: %s", e)
    # sync tools' folders (GoodSync's _gsdata_ backups, a NAS's @eaDir...) are not the library: left out with their photos
    albums = {aid: a for aid, a in all_albums.items() if not config.is_system_folder(a["rel"])}
    tags, props, internal, special, hidden = _tag_rows(raw)
    side = _side_tables(raw, tags, props, internal, special, hidden)
    rows = _photo_rows(raw, albums, root_path, tags, hidden, side, geo, phases)

    phases["compute"] = time.time() - t0 - sum(phases.values())
    t2 = time.time()
    stats = {"version": version, "photos": len(rows.photos), "resolved_edits": rows.resolved, "resolved_snapshot": rows.resolved_snapshot,
             "kind": kind, "parts": parts, "stamps": stamps}

    def fill(dst):
        _fill(dst, rows, albums, root_path, tags, hidden, side["faces"])
        dst.executemany("INSERT INTO pending_seen VALUES (?,?)", list(stamps.items()))
        stats.update(built=int(time.time()), build_seconds=round(time.time() - t0, 2))
        dst.executemany("INSERT INTO meta VALUES (?,?)", [(k, json.dumps(v) if k == "parts" else str(v)) for k, v in stats.items()
                                                          if k not in ("resolved_snapshot", "stamps")])

    _swap_in(Path(dst_path), fill)
    if Path(dst_path) == config.INDEX_DB:  # the index the app answers from: nothing updated in place is left to make up for
        _marker(Path(dst_path)).unlink(missing_ok=True)
        _patched.update(n=0, at=0.0, first=0.0, soon=False)
        with _own_lock:
            _own[:] = [r for r in _own if not any(r is o for o in own)]
    HIDDEN.let_go(t0)  # this build read rows that know about every move finished before it started
    phases["write"] = time.time() - t2
    log.info("index built from %s in %.1fs: %d photos (%s)", "digiKam's database" if direct else "the library copy", time.time() - t0, len(rows.photos),
             ", ".join(f"{k} {v:.1f}s" for k, v in phases.items()))
    return stats


def current_version(path: Path = config.INDEX_DB):
    if not path.exists():
        return None
    try:
        con = open_index(path)
        try:
            row = con.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()
        finally:
            con.close()
        return row[0] if row else None
    except sqlite3.Error:
        return None


_embed_last = {"v": "v0"}


def _embed_signature() -> str:
    """Bursts use the content embeddings, so rebuild when that file changes; not at each save while the job runs
    (one a minute), only once it is done (its end bumps the analysis epoch)."""
    try:
        from app.ai.semantic import semantic  # lazy: ai.semantic -> thumbs -> photos.edits -> data.index would be an import cycle
        if semantic.running:
            return _embed_last["v"]
        st = os.stat(semantic.active.file)
        _embed_last["v"] = f"v{semantic.active.name}{int(st.st_mtime)}"
    except OSError:
        _embed_last["v"] = "v0"
    return _embed_last["v"]


_WHOLE = ("schema", "places", "analysis", "videos", "embed")  # the parts of the version that concern every photo


def _parts(source: str) -> dict:
    """What the index is made from, by name; joined, the version it is stamped with."""
    return {"schema": SCHEMA_VERSION, "source": source, "places": places.signature(), "edits": edits.signature(),
            "analysis": analysis.signature(), "videos": videos.signature(), "embed": _embed_signature()}


def _version_for(source: str) -> str:
    return ":".join(_parts(source).values())


# ---- the index updated in place -----------------------------------------------------------------------------------
# A change to a few photos (a rating, a tag, a title, a face named, the edits written into digiKam's database) used to
# rebuild the whole index: every row of the library read and written again, seconds on a large one, for each change.
# Now the rows of those photos are rewritten in the index file as it stands, with the counts and covers of the tags
# and folders they are or were in. Which photos, the index knows two ways: the remembered edits carry a stamp each
# (pending_seen keeps the stamps the index reflects), and the viewer's own writers name the photos they write
# (writing()). Anything else is a full build, as before: a change digiKam made, a tag or folder renamed, moved or
# removed, new analysis results, more than PATCH_MAX photos. And a full build follows the last update in place once
# things are quiet (_full_build_due): what is ranked or grouped across the library (bursts, the sharpness ranks,
# the words read in several photos) is carried over as it was for a photo updated in place, and made right then.
PATCH_MAX = 500           # more photos than this: the full build is as quick, and simpler
RECONCILE_S = 600         # a full build this long after the last update in place
RECONCILE_SOON_S = 60     # ... or this long, when a photo's date, camera or size changed, or a photo came or went (bursts are found from those)
RECONCILE_MAX_S = 3600    # ... and at least this often while the updates in place keep coming
_CARRIED = ("sharpn", "focusn", "aesthn", "burst", "burst_best", "reject", "ocr")  # ranked, grouped or cleaned across the library: kept as the last full build left them
_BURST_KEYS = ("ts", "name", "camera", "w", "h", "video", "dprec")
_own_lock = threading.Lock()
_own: list = []  # the viewer's own writes the index has not taken in yet, oldest first: {"before", "after", "ids"}
_patched = {"n": None, "at": 0.0, "first": 0.0, "soon": False}  # updates in place since the last full build (n None: not read from the index yet)


def _marker(dst_path: Path) -> Path:
    """Exists while the index file is being written in place: found at a start, the process ended in the middle and
    the file cannot be trusted (its journal is in memory, see drop_photos), so the index is built anew."""
    return Path(str(dst_path) + ".patching")


def _source_now():
    if not config.INDEX_PATCH:
        return None
    try:
        return probe()[1]
    except (Unavailable, *SOURCE_ERRORS):
        return None


@contextlib.contextmanager
def writing(ids):
    """Around a write of the viewer's to digiKam's database (or the library tables) that changes rows of these
    photos and nothing else. `ids` may be a list the caller fills while it writes. The index then rewrites those
    photos' rows instead of everything, as long as the database's version went from the one the index was made
    from to the one before this write, and is still the one after it: a change by anyone else in between (digiKam,
    a writer that names no photos) means a full build."""
    before = _source_now()
    try:
        yield
    finally:
        reg = {"before": before, "after": _source_now() if before is not None else None, "ids": frozenset(int(i) for i in ids)}
        if reg["ids"]:
            with _own_lock:
                _own.append(reg)


def _full_build_due() -> bool:
    """Whether the full build that follows updates in place is due."""
    p = _patched
    if p["n"] is None:  # after a restart: what the index file says
        try:
            con = open_index()
            try:
                meta = dict(con.execute("SELECT key, value FROM meta WHERE key IN ('patches', 'patched', 'patch_first', 'patch_soon')"))
            finally:
                con.close()
            p.update(n=int(meta.get("patches") or 0), at=float(meta.get("patched") or 0), first=float(meta.get("patch_first") or 0),
                     soon=meta.get("patch_soon") == "1")
        except (sqlite3.Error, ValueError):
            p.update(n=0)
    if not p["n"]:
        return False
    now = time.time()
    return now - p["at"] > (RECONCILE_SOON_S if p["soon"] else RECONCILE_S) or now - p["first"] > RECONCILE_MAX_S


def _patch(src: tuple, parts: dict, dst_path: Path = config.INDEX_DB) -> bool:
    """Update the index in place for the photos that changed. False when it cannot be done that way (the caller
    builds the whole index then), True when the index is up to date."""
    if not config.INDEX_PATCH:
        return False
    try:
        with _build_lock:
            stats = _patch_locked(src, parts, Path(dst_path))
    except Unavailable:
        raise
    except SOURCE_ERRORS as e:  # the build deals with a database that cannot be read (and says so)
        log.info("the index was not updated in place (%s)", e)
        return False
    except Exception as e:  # a full build is always right: the index is never left as it is over a fault here
        log.warning("the index could not be updated in place (%s); building it", e, exc_info=True)
        return False
    if not stats:
        return False
    if stats["resolved_edits"]:
        _settle(Path(dst_path), stats)
    return True


def _patch_locked(src: tuple, parts: dict, dst_path: Path):
    t0 = time.time()
    kind, ver = src
    marker = _marker(dst_path)
    if not dst_path.exists() or marker.exists():
        return None
    con = open_index(dst_path)
    try:
        meta = dict(con.execute("SELECT key, value FROM meta"))
        stored = json.loads(meta["parts"]) if meta.get("parts") else None
        if not stored or meta.get("kind") != kind or any(stored.get(k) != parts[k] for k in _WHOLE):
            return None
        seen = dict(con.execute("SELECT photo_id, stamp FROM pending_seen"))
        tags_idx = {r[0]: r[1:] for r in con.execute("SELECT id, pid, name, full, person, icon FROM tags")}
        albums_idx = {r[0]: r[1:] for r in con.execute("SELECT id, pid, path, name, root, caption, adate, category, icon FROM albums")}
    finally:
        con.close()
    with _own_lock:
        own = list(_own)
    if stored["source"] != ver:
        # the database changed: only by the writes that named their photos? (index's version -> before the first,
        # after each -> before the next, after the last -> now)
        chain = [stored["source"], *(v for r in own for v in (r["before"], r["after"])), ver]
        if not own or None in chain or any(chain[i] != chain[i + 1] for i in range(0, len(chain), 2)):
            return None
    stamps = edits.pending_stamps()  # before the rows are read: an edit made meanwhile is seen as changed, never missed
    ids = {i for r in own for i in r["ids"]} | {i for i in set(seen) | set(stamps) if seen.get(i) != stamps.get(i)}
    if len(ids) > PATCH_MAX:
        return None
    m = mirror_info()
    if kind == "digikam" and not m:
        return None  # the first copy of the library is taken by a build
    direct = kind == "digikam" and m["source"] != ver  # as in _read_source: digiKam itself, and the copy follows
    con = dkdb.connect(write=False, real=True) if direct else library.connect()
    try:
        raw = read_rows(con, ids)
        root_path = dkdb.root_paths(con)
    finally:
        con.close()
    if HIDDEN:
        hidden_ids = set(HIDDEN)
        raw["images"] = [r for r in raw["images"] if r[0] not in hidden_ids]
    albums = {aid: a for aid, a in _album_rows(raw).items() if not config.is_system_folder(a["rel"])}
    tags, props, internal, special, hidden = _tag_rows(raw)

    def parent(t):
        return t["pid"] if t["pid"] in tags and t["pid"] not in hidden else None

    # the tags and folders the index has must be where and what they were: the text and counts of photos not read here hang on them
    for tid, (pid, name, full, person, _icon) in tags_idx.items():
        t = tags.get(tid)
        if not t or tid in hidden or (parent(t), t["name"], t["full"]) != (pid, name, full):
            return None
        if person:
            t["person"] = 1  # a person by a face on a photo not read here stays one
    for aid, (pid, path, name, root, *_rest) in albums_idx.items():
        a = albums.get(aid)
        if not a or (a["pid"], a["path"], a["name"], root_path.get(a["root"])) != (pid, path, name, root):
            return None
    side = _side_tables(raw, tags, props, internal, special, hidden)
    if any(tags[tid]["person"] != row[3] for tid, row in tags_idx.items()):
        return None  # a tag became a person: every photo carrying it lists it among the people from now on
    phases = {}
    rows = _photo_rows(raw, albums, root_path, tags, hidden, side, places.geocoder(), phases, ids=ids)
    present = {r[0] for r in rows.photos}
    version = ":".join({**parts, "edits": edits.signature_of(stamps)}.values())
    stats = {"version": version, "parts": {**parts, "edits": edits.signature_of(stamps)}, "stamps": stamps, "photos": len(present),
             "resolved_edits": rows.resolved, "resolved_snapshot": rows.resolved_snapshot}
    idl = sorted(ids)

    def chain_of(aid):
        out, cur = [], aid
        while cur is not None and cur in albums and cur not in out:
            out.append(cur)
            cur = albums[cur]["pid"]
        return out

    def inlist(values):
        return ",".join(str(int(v)) for v in values)

    marker.touch()
    dst = sqlite3.connect(str(dst_path), timeout=15, isolation_level=None)
    try:
        dst.execute("PRAGMA journal_mode = MEMORY")  # no journal file beside an index that readers open read-only and a build replaces
        dst.execute("BEGIN IMMEDIATE")
        if dst.execute("SELECT value FROM meta WHERE key = 'version'").fetchone()[0] != meta["version"]:
            raise sqlite3.OperationalError("the index was replaced meanwhile")
        old, old_tags = {}, set()
        for part in chunked(idl, 900):
            old.update((r[0], r) for r in dst.execute(f"SELECT * FROM photos WHERE id IN ({inlist(part)})"))
            old_tags.update(r[0] for r in dst.execute(f"SELECT DISTINCT tag_id FROM photo_tags WHERE photo_id IN ({inlist(part)})"))
        _drop(dst, idl)
        carried = [_COLS.index(c) for c in _CARRIED]
        photos = []
        for r in rows.photos:
            was = old.get(r[0])
            if was:
                r = list(r)
                for k in carried:
                    r[k] = was[k]
            photos.append(tuple(r))
        dst.executemany(f"INSERT INTO photos VALUES ({','.join('?' * len(_COLS))})", photos)
        ocr = {r[0]: r[_OCR_COL] for r in photos}
        dst.executemany("INSERT INTO fts (rowid, name, album, title, caption, tags, people, camera, misc, ocr, caption_ai, speech) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [(*f[:9], ocr.get(f[0]), *f[10:]) for f in rows.fts_rows])
        dst.executemany("INSERT OR IGNORE INTO photo_tags VALUES (?,?)", rows.photo_tag_rows)
        dst.executemany("INSERT INTO faces VALUES (?,?,?,?,?,?,?)", [f for f in side["faces"] if f[0] in present])

        # tags: the new ones, the badge pictures, and the counts of every tag these photos carry or carried (and of what is above them)
        new_tags = [tid for tid in tags if tid not in hidden and tid not in tags_idx]
        dst.executemany("INSERT INTO tags VALUES (?,?,?,?,?,0,0,NULL)", [(tid, parent(tags[tid]), tags[tid]["name"], tags[tid]["full"], tags[tid]["person"]) for tid in new_tags])
        dst.executemany("INSERT OR IGNORE INTO tag_closure VALUES (?,?)", [(a, tid) for tid in new_tags for a in [tid] + tags[tid]["anc"]])
        gone = sorted(set(old) - present)
        if gone:
            dst.execute(f"UPDATE tags SET icon = NULL WHERE icon IN ({inlist(gone)})")
        dst.executemany("UPDATE tags SET icon = (SELECT id FROM photos WHERE id = ?) WHERE id = ?",
                        [(t["icon"], tid) for tid, t in tags.items() if tid not in hidden and (t["icon"] or None) != (tags_idx.get(tid) or (None,) * 5)[4]])
        touched = sorted(old_tags | {t for t, _i in rows.photo_tag_rows} | set(new_tags))
        for part in chunked(touched, 900):
            dst.execute(f"""UPDATE tags SET
                  n = (SELECT count(*) FROM photo_tags pt WHERE pt.tag_id = tags.id),
                  n_all = (SELECT count(DISTINCT pt.photo_id) FROM photo_tags pt JOIN tag_closure c ON c.tag = pt.tag_id WHERE c.anc = tags.id)
                WHERE id IN (SELECT anc FROM tag_closure WHERE tag IN ({inlist(part)}))""")

        # folders: the ones that were empty until now, what digiKam says about each, and the counts, dates and covers of
        # every folder these photos are or were in (and of what is above them)
        scope = set()
        for aid in {r[1] for r in old.values()} | {r[1] for r in photos}:
            scope.update(chain_of(aid))
        for aid, (_pid, _path, _name, _root, caption, adate, category, icon) in albums_idx.items():
            a = albums[aid]
            if (a["caption"], a["date"], a["category"], a["icon"]) != (caption, adate, category, icon):
                dst.execute("UPDATE albums SET caption = ?, adate = ?, category = ?, icon = ? WHERE id = ?", (a["caption"], a["date"], a["category"], a["icon"], aid))
                scope.add(aid)  # its cover may be another photo now
        for aid in sorted(scope - set(albums_idx)):
            a = albums[aid]
            dst.execute("DELETE FROM album_closure WHERE album = ?", (aid,))
            dst.executemany("INSERT OR IGNORE INTO album_closure VALUES (?,?)", [(anc, aid) for anc in chain_of(aid)])
            dst.execute("INSERT INTO albums (id, pid, path, name, root, caption, n, adate, category, icon) VALUES (?,?,?,?,?,?,0,?,?,?)",
                        (aid, a["pid"], a["path"], a["name"], root_path[a["root"]], a["caption"], a["date"], a["category"], a["icon"]))
        for part in chunked(sorted(scope), 900):
            dst.execute(f"""
                UPDATE albums SET
                  n      = (SELECT count(*) FROM photos p WHERE p.album_id = albums.id),
                  n_all  = (SELECT count(*) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
                  ts_min = (SELECT min(ts) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
                  ts_max = (SELECT max(ts) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
                  cover  = coalesce((SELECT p.id FROM photos p WHERE p.id = albums.icon),
                                    (SELECT p.id FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id
                                     ORDER BY p.video, (p.pick = 1), p.rating DESC, p.ts LIMIT 1))
                WHERE id IN ({inlist(part)})""")
            dst.execute(f"DELETE FROM albums WHERE n_all = 0 AND id IN ({inlist(part)})")

        for part in chunked(idl, 900):
            dst.execute(f"DELETE FROM pending_seen WHERE photo_id IN ({inlist(part)})")
        dst.executemany("INSERT INTO pending_seen VALUES (?,?)", [(i, stamps[i]) for i in idl if i in stamps])

        # what bursts are found from changed, or a photo came or went: the full build follows sooner
        keys = [_COLS.index(c) for c in _BURST_KEYS]
        soon = set(old) != present or any(tuple(r[k] for k in keys) != tuple(old[r[0]][k] for k in keys) for r in photos)
        now = time.time()
        first = float(meta.get("patch_first") or 0) if int(meta.get("patches") or 0) else now
        soon = soon or (meta.get("patch_soon") == "1" and int(meta.get("patches") or 0) > 0)
        done = {"version": version, "parts": json.dumps(stats["parts"]), "photos": dst.execute("SELECT count(*) FROM photos").fetchone()[0],
                "patches": int(meta.get("patches") or 0) + 1, "patched": round(now, 3), "patch_first": round(first, 3), "patch_soon": int(soon)}
        dst.executemany("INSERT OR REPLACE INTO meta VALUES (?,?)", [(k, str(v)) for k, v in done.items()])
        dst.execute("COMMIT")
    except BaseException:
        try:
            dst.execute("ROLLBACK")
            marker.unlink(missing_ok=True)  # the file is as it was
        except sqlite3.Error:
            pass  # the marker stays: the next look builds the index anew
        raise
    finally:
        dst.close()
    marker.unlink(missing_ok=True)
    last_source.update(kind=kind, version=ver)
    _patched.update(n=done["patches"], at=now, first=first, soon=soon)
    with _own_lock:
        _own[:] = [r for r in _own if not any(r is o for o in own)]
    if direct:
        refresh_library_soon()
    log.info("index updated in place in %.2fs: %d photos", time.time() - t0, len(ids))
    return stats


def ensure_fresh() -> bool:
    """Bring the index up to date when anything it is made from changed: digiKam's database (or the viewer's copy
    of it), the viewer's remembered edits, analysis results, embeddings, or this schema. A change to a few photos
    is written into the index in place (_patch); anything else builds it anew. True if the index changed."""
    src = probe()
    parts = _parts(src[1])
    with _own_lock:
        own = bool(_own)
    if (current_version() == ":".join(parts.values()) and not own and not _marker(config.INDEX_DB).exists()
            and not (src[0] == "digikam" and not mirror_info())):
        # (a readable digiKam with no copy taken yet, as right after this version's first start, builds once to take it)
        last_source.update(kind=src[0], version=src[1])
        if not _full_build_due():
            return False
    elif not _full_build_due() and _patch(src, parts):
        return True
    build(source=src)
    return True


if __name__ == "__main__":
    print(build())
