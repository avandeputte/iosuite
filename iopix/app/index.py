"""Builds the app's own search index from the digiKam database.

The digiKam database is opened read-only (see dkdb) and read inside a single
transaction; nothing is ever written to it. The result is a small denormalised
SQLite file with a full-text table, stored in the app's data folder and swapped
in atomically. Bump SCHEMA_VERSION whenever the tables, indexes or the meaning
of a column change, so running viewers rebuild.
"""
import calendar
import json
import os
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from . import analysis, config, dkdb, edits, moments, places

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
    npeople INTEGER, objects TEXT, ocr TEXT, burst INTEGER, burst_best INTEGER, caption_ai TEXT
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
                     caption TEXT, n INTEGER, n_all INTEGER, cover INTEGER, ts_min INTEGER, ts_max INTEGER);
CREATE TABLE album_closure (anc INTEGER, album INTEGER, PRIMARY KEY (anc, album)) WITHOUT ROWID;
CREATE TABLE faces (photo_id INTEGER, tag_id INTEGER, x INTEGER, y INTEGER, w INTEGER, h INTEGER, kind TEXT DEFAULT 'confirmed');
CREATE INDEX faces_kind ON faces (kind);
CREATE INDEX faces_photo ON faces (photo_id);
CREATE INDEX faces_tag ON faces (tag_id);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE fts USING fts5(
    name, album, title, caption, tags, people, camera, misc, ocr, caption_ai,
    tokenize = "unicode61 remove_diacritics 2", prefix = '1 2 3'
);
"""

PICK = {"Pick Label None": 0, "Pick Label Rejected": 1, "Pick Label Pending": 2, "Pick Label Accepted": 3}
COLORS = ["None", "Red", "Orange", "Yellow", "Green", "Blue", "Magenta", "Gray", "Black", "White"]
COLOR = {f"Color Label {n}": i for i, n in enumerate(COLORS)}
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
SPECIAL_PERSON_PROPS = ("unknownPerson", "ignoredPerson", "unconfirmedPerson")
SCHEMA_VERSION = "9"
RECT_RE = re.compile(r'x="(-?\d+)" y="(-?\d+)" width="(\d+)" height="(\d+)"')


def source_version() -> str:
    """Changes whenever digiKam writes to its database."""
    return dkdb.source_version()


def open_index(path: Path = config.INDEX_DB) -> sqlite3.Connection:
    """A read-only connection to the index (plain tuples; callers wanting rows set row_factory)."""
    return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)


def _parse_dt(s):
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


def build(dst_path: Path = config.INDEX_DB) -> dict:
    """Read everything from digiKam's database in one snapshot, then write a fresh index
    file and swap it in. Returns the stats also stored in the index's meta table."""
    t0 = time.time()
    version = expected_version()
    geo = places.geocoder()
    src = dkdb.connect(write=False)
    try:
        src.begin_read()  # one consistent snapshot for all reads below
        q = src.execute

        # ---- album roots and albums
        roots = {r[0]: r[1] for r in q("SELECT id, label FROM AlbumRoots")}
        single_root = len(roots) == 1
        root_path = dkdb.root_paths(src)
        albums = {}
        for aid, root, rel, caption in q("SELECT id, albumRoot, relativePath, caption FROM Albums"):
            if root in roots:
                albums[aid] = {"id": aid, "root": root, "rel": rel, "caption": caption or None, "label": roots[root]}
        by_path = {(a["root"], a["rel"]): aid for aid, a in albums.items()}
        for a in albums.values():
            rel = a["rel"]
            if rel == "/":
                a["pid"], a["name"] = None, a["label"] or "Library"
            else:
                parent = rel.rsplit("/", 1)[0] or "/"
                a["pid"], a["name"] = by_path.get((a["root"], parent)), rel.rsplit("/", 1)[1]
            a["path"] = rel if single_root else f"/{a['label']}{'' if rel == '/' else rel}"

        # ---- tags
        # icon: the photo digiKam shows for the tag ("Set as Tag Thumbnail"); for people it is the face on that photo
        tags = {tid: {"id": tid, "pid": pid, "name": name, "icon": icon} for tid, pid, name, icon in q("SELECT id, pid, name, icon FROM Tags")
                if tid != 0}  # MySQL's "_Digikam_root_tag_" row; pid 0 means "no parent" on both backends
        props = defaultdict(set)
        for tid, prop in q("SELECT tagid, property FROM TagProperties"):
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

        # ---- per-image side tables
        img_tags, pick, color = defaultdict(list), {}, {}
        for iid, tid in q("SELECT imageid, tagid FROM ImageTags"):
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
        for iid, tid, prop, val in q("SELECT imageid, tagid, property, value FROM ImageTagProperties "
                                      "WHERE property IN ('tagRegion', 'autodetectedFace', 'ignoredFace')"):
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

        title, caption = {}, {}
        for iid, typ, text in q("SELECT imageid, type, comment FROM ImageComments ORDER BY id"):
            if text and text.strip():
                (title if typ == 3 else caption).setdefault(iid, text.strip())
        copyright_ = defaultdict(dict)
        for iid, prop, val in q("SELECT imageid, property, value FROM ImageCopyright"):
            if val and val.strip():
                copyright_[iid].setdefault(prop, val.strip())
        iprops = defaultdict(dict)
        for iid, prop, val in q("SELECT imageid, property, value FROM ImageProperties"):
            if val and val.strip() and set(val) - set("?, "):
                iprops[iid][prop] = val.strip()

        # ---- photos
        rows = q("""
            SELECT i.id, i.album, i.name, i.fileSize, i.uniqueHash, i.modificationDate, i.category,
                   ii.rating, ii.creationDate, ii.orientation, ii.width, ii.height, ii.format,
                   m.make, m.model, m.lens, m.aperture, m.focalLength, m.focalLength35, m.exposureTime,
                   m.sensitivity, m.flash, m.whiteBalance, m.meteringMode, m.exposureProgram,
                   p.latitudeNumber, p.longitudeNumber, p.altitude, p.orientation AS gpsOrientation,
                   v.duration, v.videoCodec, v.frameRate, v.audioCompressor, v.aspectRatio
            FROM Images i
            LEFT JOIN ImageInformation ii ON ii.imageid = i.id
            LEFT JOIN ImageMetadata m ON m.imageid = i.id
            LEFT JOIN ImagePositions p ON p.imageid = i.id
            LEFT JOIN VideoMetadata v ON v.imageid = i.id
            WHERE i.status = 1 AND i.album IS NOT NULL AND i.category IN (1, 2)
        """).fetchall()
    finally:
        src.rollback()
        src.close()

    photos, fts_rows, photo_tag_rows = [], [], []
    # edits made in the viewer live in sidecars; show them until digiKam's database catches up
    pending, resolved = edits.pending(), []
    seen = analysis.results()  # sharpness, OCR text, objects... from the app's own analysis
    burst_rows = []
    tag_by_full = {t["full"]: tid for tid, t in tags.items() if tid not in hidden}
    tag_direct, tag_all = defaultdict(set), defaultdict(set)
    album_n = defaultdict(int)
    for (iid, album_id, name, size, uhash, mod, category, rating, created, orient, w, h, fmt,
         make, model, lens, aperture, focal, focal35, exposure, iso, flash, wb, metering, program,
         lat, lon, alt, gps_orientation, duration, vcodec, fps, acodec, aspect) in rows:
        album = albums.get(album_id)
        if not album:
            continue
        created_db, lat_db, lon_db = created, lat, lon  # digiKam's own values, before any pending edit is overlaid
        e0 = pending.get(iid)
        if e0 and "taken" in e0:
            created = e0["taken"]
        if e0 and "gps" in e0:
            lat, lon, alt = (e0["gps"]["lat"], e0["gps"]["lon"], e0["gps"].get("alt")) if e0["gps"] else (None, None, None)
        mdt = _parse_dt(mod)
        ts, y, mo, d = _parse_dt(created) or mdt or (0, 1970, 1, 1)
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
            dbcr = copyright_.get(iid, {})
            same = (("rating" not in e or e["rating"] == rating)
                    and ("taken" not in e or e["taken"] == (created_db or "")[:19])
                    and ("gps" not in e or (e["gps"] is None and lat_db is None) or
                         (e["gps"] is not None and lat_db is not None and abs(e["gps"]["lat"] - lat_db) < 1e-6 and abs(e["gps"]["lon"] - lon_db) < 1e-6))
                    and ("template" not in e or all((dbcr.get(k) or "") == (v or "") for k, v in e["template"].items()))
                    and ("pick" not in e or e["pick"] == p_pick) and ("color" not in e or e["color"] == p_color)
                    and ("title" not in e or (e["title"] or None) == p_title)
                    and ("caption" not in e or (e["caption"] or None) == p_caption)
                    and all(t in tids for t in add) and not any(t in tids for t in rem))
            if same:
                resolved.append(iid)
            else:
                edited = 1
                rating = e.get("rating", rating)
                p_pick, p_color = e.get("pick", p_pick), e.get("color", p_color)
                p_title = (e["title"] or None) if "title" in e else p_title
                p_caption = (e["caption"] or None) if "caption" in e else p_caption
                tids = [t for t in tids if t not in rem] + [t for t in add if t not in tids]
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
        for k, v in (("whiteBalance", wb), ("metering", metering), ("program", program), ("orientation", orient)):
            if v is not None:
                extra[k] = v
        rel = album["rel"].rstrip("/") + "/" + name
        an = seen.get(iid, {})
        burst_rows.append((iid, ts, name, f"{cam}|{w}x{h}", an.get("sharp"), an.get("faceq"), video))
        photos.append((
            iid, album_id, name, root_path[album["root"]] + rel,
            (created or mod or "")[:19], ts, f"{y:04d}-{mo:02d}-{d:02d}", y, mo, f"{mo:02d}-{d:02d}",
            w, h, fmt, video, dur, size, rating,
            p_pick, p_color, cam, (make or "").strip() or None, (model or "").strip() or None,
            lens, aperture, focal, focal35, exposure, iso, flash, lat, lon, alt,
            p_title, p_caption, cr.get("creator"), cr.get("copyrightNotice"),
            *(loc or (None, None, None)),
            uhash, (mod or "")[:19], mdt[0] if mdt else ts, len(tids), json.dumps(extra) if extra else None, edited,
            an.get("sharp"), None, an.get("bright"), an.get("clip_lo"), an.get("clip_hi"), an.get("faceq"),
            an.get("npeople"), ("," + ",".join(sorted(an["objects"])) + ",") if an.get("objects") else None,
            an.get("ocr"), None, None, an.get("caption_ai"),
        ))
        album_n[album_id] += 1
        people_names, tag_names = [], []
        for tid in tids:
            t = tags[tid]
            photo_tag_rows.append((tid, iid))
            tag_direct[tid].add(iid)
            tag_all[tid].add(iid)
            for a in t["anc"]:
                tag_all[a].add(iid)
            (people_names if t["person"] else tag_names).append(t["full"].replace("/", " "))
        extra_words = " ".join(an["objects"]) if an.get("objects") else ""
        misc = extra_words + " " + " ".join(str(x) for x in (
            y, MONTHS[mo], fmt, "video" if video else "photo", lens, cr.get("creator"),
            cr.get("copyrightNotice"), " ".join(iprops.get(iid, {}).values()), *(loc or ())) if x)
        fts_rows.append((iid, name, album["path"], p_title, p_caption,
                         " ; ".join(tag_names), " ; ".join(people_names), cam, misc, an.get("ocr"), an.get("caption_ai")))

    # ---- write the new index next to the old one, then swap
    dst_path = Path(dst_path)
    tmp = dst_path.with_suffix(f".{os.getpid()}.tmp")  # the web app and MCP server may both rebuild
    for p in (tmp, Path(str(tmp) + "-journal")):
        p.unlink(missing_ok=True)
    dst = sqlite3.connect(tmp)
    try:
        dst.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;" + SCHEMA)
        dst.executemany(f"INSERT INTO photos VALUES ({','.join('?' * 57)})", photos)
        dst.executemany("INSERT INTO fts (rowid, name, album, title, caption, tags, people, camera, misc, ocr, caption_ai) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", fts_rows)
        # sharpness as a 0..1 rank across the library, so "blurry" means the same everywhere
        ranked = sorted((r[4], r[0]) for r in burst_rows if r[4] is not None)
        if ranked:
            dst.executemany("UPDATE photos SET sharpn = ? WHERE id = ?",
                            [(round(i / max(1, len(ranked) - 1), 4), pid) for i, (_, pid) in enumerate(ranked)])
        try:
            bursts = moments.find_bursts(burst_rows)
        except Exception:
            bursts = {}
        dst.executemany("UPDATE photos SET burst = ?, burst_best = ? WHERE id = ?", [(b, best, pid) for pid, (b, best) in bursts.items()])
        dst.execute("CREATE INDEX photos_burst ON photos (burst)")
        dst.executemany("INSERT OR IGNORE INTO photo_tags VALUES (?,?)", photo_tag_rows)
        present = {r[0] for r in photos}
        dst.executemany("INSERT INTO faces VALUES (?,?,?,?,?,?,?)", [f for f in faces if f[0] in present])
        dst.executemany("INSERT INTO tags VALUES (?,?,?,?,?,?,?,?)", [
            (tid, t["pid"] if t["pid"] in tags and t["pid"] not in hidden else None, t["name"], t["full"],
             t["person"], len(tag_direct[tid]), len(tag_all[tid]), t["icon"] if t["icon"] in present else None)
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
        dst.executemany("INSERT INTO albums (id, pid, path, name, root, caption, n) VALUES (?,?,?,?,?,?,?)", [
            (aid, a["pid"], a["path"], a["name"], root_path[a["root"]], a["caption"], album_n[aid])
            for aid, a in albums.items()])
        dst.execute("""
            UPDATE albums SET
              n_all  = (SELECT count(*) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
              ts_min = (SELECT min(ts) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
              ts_max = (SELECT max(ts) FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id),
              cover  = (SELECT p.id FROM photos p JOIN album_closure c ON c.album = p.album_id WHERE c.anc = albums.id
                        ORDER BY p.video, (p.pick = 1), p.rating DESC, p.ts LIMIT 1)
        """)
        dst.execute("DELETE FROM albums WHERE n_all = 0")
        stats = {"version": version, "built": int(time.time()), "photos": len(photos), "resolved_edits": resolved,
                 "build_seconds": round(time.time() - t0, 2)}
        dst.executemany("INSERT INTO meta VALUES (?,?)", [(k, str(v)) for k, v in stats.items()])
        dst.commit()
        dst.execute("INSERT INTO fts(fts) VALUES ('optimize')")
        dst.commit()
    except BaseException:
        dst.close()
        tmp.unlink(missing_ok=True)  # never leave a half-written index behind
        raise
    dst.close()
    os.replace(tmp, dst_path)
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


def _embed_signature() -> str:
    """Bursts use the content embeddings, so rebuild when that file changes."""
    try:
        from .semantic import semantic
        st = os.stat(semantic.active.file)
        return f"v{semantic.active.name}{int(st.st_mtime)}"
    except OSError:
        return "v0"


def expected_version() -> str:
    return f"{SCHEMA_VERSION}:{source_version()}:{places.signature()}:{edits.signature()}:{analysis.signature()}:{_embed_signature()}"


def ensure_fresh() -> bool:
    """Rebuild the index when anything it is built from changed: digiKam's database, the
    viewer's remembered edits, analysis results, embeddings, or this schema. True if rebuilt."""
    if current_version() == expected_version():
        return False
    stats = build()
    if stats["resolved_edits"]:  # digiKam now agrees with these edits; stop tracking them
        edits.resolved(stats["resolved_edits"])
    return True


if __name__ == "__main__":
    print(build())
