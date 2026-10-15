"""digiKam Viewer: a Google-Photos-style web front end for a digiKam library.

The library (digiKam's database and the photo files) is only read here; the
few endpoints that change it (sidecars, image files, digiKam's database on
request) are listed in WRITE_PATHS and go through the modules that own those
writes."""
import gzip
import json
import mimetypes
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
import traceback
import zipfile
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from functools import lru_cache
from urllib.parse import parse_qsl, quote

import orjson
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from . import (analysis, caption, concepts, config, consistency, dbsync, detector, dkdb, edits, facemgr, gpx, index,
               moments, places, placetags, tagmanager, thumbs)
from . import state as appstate
from . import jobs as bgjobs
from . import geocode, maps, users
from . import mcp_server, updates
from . import __version__ as APP_VERSION
from . import models as dlmodels
from .semantic import ENGINES, semantic, enabled as semantic_enabled, _ready as semantic_ready
from .query import SORTS, build_where

THUMB_COLS = "id, path, video, duration, w, h, hash, size, modified"
IMG_CACHE = {"Cache-Control": "private, max-age=86400"}

# version: the index build the API answers from; source: digiKam's database as of
# that build (background jobs restart only when this changes)
state = {"version": None, "error": None, "source": None}
prewarmer = thumbs.Prewarmer()


def db() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{quote(str(config.INDEX_DB))}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    # favorites and app albums live in the app's own database
    con.execute("ATTACH DATABASE ? AS st", (f"file:{quote(str(appstate.STATE_DB))}?mode=ro",))
    return con


def resolve(items) -> tuple[str, list, dict | None]:
    """Filter parameters to SQL. Content search ("sem") and "more like this"
    ("like") are answered by the embedding index and become an id list plus a
    ranking."""
    items = list(items)
    d = dict(items)
    rank = None
    if semantic_enabled():  # a plain search also covers the detected concepts of the same name
        for key, text in list(items):
            if key == "q" and text:
                try:
                    items.append(("qids", ",".join(map(str, concepts.photos_matching(text))) or "0"))
                except Exception:
                    traceback.print_exc()
    if d.get("sem") or d.get("like") or d.get("concept"):
        ids = []
        if semantic_enabled():
            try:
                k = max(1, min(int(d.get("sem_k") or 300), 2000))
                ids = (concepts.photos_for(d["concept"]) if d.get("concept") else
                       semantic.search_text(d["sem"], k) if d.get("sem") else semantic.similar(int(d["like"]), k))
            except Exception:  # an empty result rather than a failed page; the cause goes to the log
                traceback.print_exc()
                ids = []
        items.append(("ids", ",".join(map(str, ids)) or "0"))
        rank = {pid: i for i, pid in enumerate(ids)}
    where, params = build_where(items)
    return where, params, rank


def _start_prewarm():
    con = db()
    try:
        rows = [dict(r) for r in con.execute(f"SELECT {THUMB_COLS} FROM photos ORDER BY ts DESC")]
    finally:
        con.close()
    if config.PREWARM:
        prewarmer.start(rows)  # first: its cache scan is slow over a mount, and thumbnails come first in the queue
    analysis.start(rows)
    semantic.start(rows)


_kick = threading.Event()  # set after an edit so the index is rebuilt right away


def _public_version() -> str:
    """What browsers compare to decide whether to reload: steady while analysis
    is still trickling results in, so the page is not refreshed every minute."""
    v = state["version"] or ""
    if any(j["running"] for j in analysis.progress.values()) or semantic.running:
        parts = v.split(":")
        return ":".join(parts[:4] + ["analysing"])
    return v


def _refresh(initial=False):
    """Rebuild the index when digiKam's database (or the viewer's own edits) changed."""
    try:
        if not initial and dkdb.busy_recently():
            return  # digiKam is writing right now; pick it up on the next pass
        rebuilt = index.ensure_fresh()
        state["error"] = None
        version = index.current_version()
        if rebuilt or version != state["version"]:
            state["version"] = version
            _meta.cache_clear()
            _photos_cached.cache_clear()
            _events.cache_clear()
            # background jobs restart only when the library itself changed, not each
            # time their own results are folded into the index
            source = index.source_version()
            if source != state.get("source"):
                state["source"] = source
                _start_prewarm()
                threading.Thread(target=_compute_tag_covers, args=(source,), daemon=True).start()
    except (sqlite3.Error, OSError) as e:  # e.g. database busy; try again later
        state["error"] = str(e)
        if initial and not config.INDEX_DB.exists():
            raise


def _watch():
    while True:
        kicked = _kick.wait(timeout=config.REINDEX_POLL)
        _kick.clear()
        _refresh(initial=kicked)


def _models_arrived(keys: list):
    """After a first-start download: pick the search model that just arrived if none is chosen, and kick the jobs."""
    if keys:
        for k in ("siglip2", "clip"):
            if k in keys and not appstate.get_setting("search_model"):
                appstate.set_setting("search_model", k)
                break
        _start_prewarm()
        _kick.set()


def _setup_file_log():
    """A rotating log in the data folder, with uvicorn's lines, readable from Maintenance and the MCP
    diagnostics whatever the platform logs to (journald, launchd, docker)."""
    import logging
    from logging.handlers import RotatingFileHandler
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        h = RotatingFileHandler(config.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    except OSError:
        return
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    for name in ("", "uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        if not any(isinstance(x, RotatingFileHandler) and getattr(x, "baseFilename", "") == str(config.LOG_FILE) for x in lg.handlers):
            lg.addHandler(h)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(_app):
    _setup_file_log()
    appstate.init()
    users.init()
    edits.init()
    tagmanager.init()
    analysis.init()
    consistency.init()
    analysis.on_progress = _kick.set  # fold new analysis results into the index as they arrive
    if tagmanager.pending_jobs():  # finish sidecar updates left over from a previous run
        tagmanager.start_worker()
    _refresh(initial=True)
    threading.Thread(target=thumbs.prune_previews, daemon=True).start()
    threading.Thread(target=_watch, name="reindex", daemon=True).start()
    if config.AUTO_MODELS:  # containers and fresh installs: fetch missing models, then start the jobs that need them
        dlmodels.auto_download(config.AUTO_MODELS, on_done=_models_arrived)
    async with mcp_server.server.session_manager.run():  # the MCP endpoint (/mcp) lives in this process
        yield


app = FastAPI(title="digiKam Viewer", lifespan=lifespan, docs_url=None, redoc_url=None)

# every endpoint that changes the library (sidecars, files, digiKam's database); refused in read-only mode
WRITE_PATHS = ("/api/edit", "/api/edits/db", "/api/consistency/sync", "/api/gpx/apply", "/api/faces/op", "/api/faces/batch",
               "/api/faces/person", "/api/placetags", "/api/tags/op")


ADMIN_PATHS = ("/api/settings", "/api/maintenance", "/api/analysis/run", "/api/models/check", "/api/models/download", "/api/restart", "/api/users", "/api/update")
SIGNED_IN_PATHS = ("/api/favorites", "/api/ualbums", "/api/tags/recent", "/api/auth/settings", "/api/auth/password")


def _hits(path: str, paths) -> bool:
    return any(path == p or path.startswith(p + "/") for p in paths)


@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    """Who is asking (session cookie), and may they do this? Library writes need an editor
    or admin, settings and maintenance an admin, favorites and albums a signed-in user; all
    of that only once a user exists. Read-only mode refuses library writes for everyone."""
    user = users.user_from_token(request.cookies.get(users.COOKIE, "")) if request.cookies.get(users.COOKIE) else None
    request.state.user = user
    if request.method == "POST":
        path = request.url.path
        if _hits(path, WRITE_PATHS) and appstate.read_only():
            return JSONResponse({"detail": "The viewer is in read-only mode; nothing in the library can be changed."}, status_code=403)
        if _hits(path, WRITE_PATHS) and not users.can_write(user):
            return JSONResponse({"detail": "Sign in as an editor to change the library."}, status_code=403 if user else 401)
        if _hits(path, ADMIN_PATHS) and not users.is_admin(user):
            return JSONResponse({"detail": "Only an admin can change settings or run maintenance."}, status_code=403 if user else 401)
        if _hits(path, SIGNED_IN_PATHS) and not users.is_signed_in(user):
            return JSONResponse({"detail": "Sign in to keep favorites and albums."}, status_code=401)
    return await call_next(request)


def jresp(request: Request, data) -> Response:
    body = orjson.dumps(data)
    headers = {"Cache-Control": "no-store"}
    if len(body) > 2048 and "gzip" in request.headers.get("accept-encoding", ""):
        body = gzip.compress(body, compresslevel=3)
        headers["Content-Encoding"] = "gzip"
    return Response(body, media_type="application/json", headers=headers)


async def _form_items(request: Request) -> list:
    """(key, value) pairs of a form-encoded body: the same filters the URL carries,
    for selections too long for a URL."""
    return parse_qsl((await request.body()).decode("utf-8", "replace"), keep_blank_values=True)


# --------------------------------------------------------------------------
# Browsing: photos, metadata, facets, map, events
# --------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _photos_cached(version: str, key: str) -> bytes:
    items = parse_qsl(key.split("|", 1)[1], keep_blank_values=True)
    where, params, rank = resolve(items)
    d = dict(items)
    sort = SORTS.get(d.get("sort", "new"), SORTS["new"])
    con = db()
    try:
        rows = con.execute(
            f"SELECT id, ts, w, h, video, duration, lat IS NOT NULL, "
            f"EXISTS (SELECT 1 FROM faces f WHERE f.photo_id = photos.id AND f.kind = 'confirmed') FROM photos WHERE {where} ORDER BY {sort}", params).fetchall()
    finally:
        con.close()
    if rank and "sort" not in d:
        rows.sort(key=lambda r: rank.get(r[0], 1 << 30))
    data = {
        "version": version, "count": len(rows), "ranked": bool(rank),
        "id": [r[0] for r in rows], "ts": [r[1] for r in rows],
        "w": [r[2] for r in rows], "h": [r[3] for r in rows],
        # videos only, as {index: seconds}, to keep the payload small
        "video": {str(i): (round(r[5]) if r[5] else 0) for i, r in enumerate(rows) if r[4]},
        # positions of photos that carry GPS coordinates, for the badge on their tiles
        "geo": [i for i, r in enumerate(rows) if r[6]],
        "faces": [i for i, r in enumerate(rows) if r[7]],
    }
    return gzip.compress(orjson.dumps(data), compresslevel=3)


@app.get("/api/photos")
def api_photos(request: Request):
    """The whole result set in compact column form; the browser lays it out and
    fetches thumbnails lazily, so scrolling never waits on the server."""
    try:
        # the prefix makes cached results expire when favorites, albums or embeddings change
        body = _photos_cached(state["version"], f"{appstate.rev}.{semantic.key}|{request.url.query}")
    except sqlite3.OperationalError as e:
        raise HTTPException(400, f"Bad query: {e}")
    if "gzip" in request.headers.get("accept-encoding", ""):
        return Response(body, media_type="application/json",
                        headers={"Content-Encoding": "gzip", "Cache-Control": "no-store"})
    return Response(gzip.decompress(body), media_type="application/json")


_tag_covers: dict = {}  # tag id -> the most typical photo of that tag (filled in the background)


def _compute_tag_covers(version: str):
    """Pick a cover for each keyword tag that actually looks like the tag: the photo
    closest to the average of the tag's photos, nudged toward the tag's name."""
    if not semantic_enabled():
        return
    con = db()
    try:
        tags = con.execute("SELECT id, name FROM tags WHERE person = 0 AND n_all > 0").fetchall()
        found = {}
        for t in tags:
            if state.get("source") != version:
                return
            ids = [r[0] for r in con.execute(
                "SELECT DISTINCT pt.photo_id FROM photo_tags pt JOIN tag_closure c ON c.tag = pt.tag_id "
                "JOIN photos p ON p.id = pt.photo_id WHERE c.anc = ? AND p.video = 0 AND p.pick != 1", (t["id"],))]
            best = concepts.representative(ids, t["name"])
            if best:
                found[t["id"]] = best
    except Exception:  # keep the previous covers; the cause goes to the log
        traceback.print_exc()
        return
    finally:
        con.close()
    _tag_covers.clear()
    _tag_covers.update(found)
    _meta.cache_clear()


@lru_cache(maxsize=2)
def _meta(version: str) -> dict:
    con = db()
    try:
        q = con.execute
        covers = {r[0]: r[1] for r in q(
            "SELECT c.anc, p.id, max(p.rating * 1e11 + p.ts - (p.pick = 1) * 1e13) FROM tag_closure c "
            "JOIN photo_tags pt ON pt.tag_id = c.tag JOIN photos p ON p.id = pt.photo_id "
            "WHERE p.video = 0 GROUP BY c.anc")}
        covers.update(_tag_covers)
        # a thumbnail chosen in digiKam (or here) beats the automatic pick
        covers.update({r[0]: r[1] for r in q("SELECT id, icon FROM tags WHERE icon IS NOT NULL")})
        # whose face to show for a people tag: its own, or its most-photographed member's
        faces = {r[0]: r[1] for r in q(
            "SELECT c.anc, f.tag_id, max(cnt) FROM tag_closure c JOIN (SELECT tag_id, count(*) AS cnt FROM faces "
            "GROUP BY tag_id) f ON f.tag_id = c.tag GROUP BY c.anc")}
        own = {r[0] for r in q("SELECT DISTINCT tag_id FROM faces")}
        tags = [{"id": r["id"], "pid": r["pid"], "name": r["name"], "full": r["full"], "person": r["person"],
                 "n": r["n"], "nAll": r["n_all"], "cover": covers.get(r["id"]), "icon": r["icon"],
                 "face": r["id"] if r["id"] in own else (faces.get(r["id"]) if r["full"].split("/")[0] == "People" else None)}
                for r in q("SELECT * FROM tags ORDER BY name COLLATE NOCASE")]
        albums = [{"id": r["id"], "pid": r["pid"], "path": r["path"], "name": r["name"], "caption": r["caption"],
                   "n": r["n"], "nAll": r["n_all"], "cover": r["cover"], "tsMin": r["ts_min"], "tsMax": r["ts_max"]}
                  for r in q("SELECT * FROM albums ORDER BY path COLLATE NOCASE")]

        def counts(col, where="1"):
            return [[r[0], r[1]] for r in q(
                f"SELECT {col}, count(*) FROM photos WHERE {where} GROUP BY 1 ORDER BY 2 DESC")]
        tot = q("SELECT count(*), sum(video), sum(lat IS NOT NULL), min(ts), max(ts), sum(size) FROM photos").fetchone()
        return {
            "version": version, "tags": tags, "albums": albums,
            "cameras": counts("camera", "camera IS NOT NULL"), "lenses": counts("lens", "lens IS NOT NULL"),
            "formats": counts("fmt"), "creators": counts("creator", "creator IS NOT NULL"),
            "years": sorted(counts("year"), reverse=True), "ratings": counts("rating"),
            "picks": counts("pick"), "colors": counts("color"),
            "total": tot[0], "videos": tot[1] or 0, "geotagged": tot[2] or 0,
            "tsMin": tot[3], "tsMax": tot[4], "bytes": tot[5] or 0,
            "colorNames": index.COLORS,
            "places": [[r[0], r[1], r[2], r[3], r[4]] for r in q(
                "SELECT place, region, country, count(*), id, max(ts - (pick = 1) * 1e11 - video * 1e11) FROM photos "
                "WHERE place IS NOT NULL GROUP BY place, region, country ORDER BY 4 DESC")],
            "countries": counts("country", "country IS NOT NULL"),
        }
    finally:
        con.close()


@app.get("/api/meta")
def api_meta(request: Request):
    return jresp(request, {**_meta(state["version"]), "version": _public_version()})


def _app_stamp() -> str:
    """Changes whenever the front-end files change, so an open tab can tell it is stale."""
    try:
        return str(max(int(os.stat(config.STATIC_DIR / f).st_mtime) for f in ("app.js", "app.css", "index.html")))
    except OSError:
        return "0"


@app.get("/api/status")
def api_status(request: Request):
    user = request.state.user
    return {"version": _public_version(), "error": state["error"], "rev": appstate.rev, "app": _app_stamp(),
            "thumbs": {"running": prewarmer.running, "done": prewarmer.done, "total": prewarmer.total, "since": prewarmer.started, "last": prewarmer.last, "current": list(prewarmer.current.values())[:3]},
            "semantic": {"enabled": semantic_enabled(), "running": semantic.running, "done": semantic.done,
                         "total": semantic.total, "indexed": 0 if semantic.ids is None else int(len(semantic.ids))},
            "places": places.available(), "editing": edits.available() and users.can_write(user), "pendingEdits": len(edits.pending()),
            "dbWrite": config.DB_WRITE and not appstate.read_only() and users.can_write(user), "writeFiles": edits.writes_files(),
            "user": ({"id": user["id"], "name": user["name"], "role": user["role"], "person": user.get("person")} if user else None), "usersExist": users.any_users(),
            "isAdmin": users.is_admin(user), "signedIn": users.is_signed_in(user),
            "readOnly": appstate.read_only(), "readOnlyLocked": config.READ_ONLY, "digikamCheck": config.DIGIKAM_CHECK,
            "appVersion": APP_VERSION, "commit": updates.local_commit()[:7],
            "tagJobs": {**tagmanager.progress, "pending": tagmanager.pending_jobs()},
            "analysis": analysis.progress, "jobs": bgjobs.status()}


@app.get("/api/facets")
def api_facets(request: Request):
    """Counts of every metadata value within the current result set."""
    where, params, _ = resolve(request.query_params.multi_items())
    con = db()
    try:
        # keyed, so the twenty "id IN (SELECT id FROM sel)" probes below use the b-tree
        # instead of each building its own (halves the time on the whole library)
        con.execute("CREATE TEMP TABLE sel (id INTEGER PRIMARY KEY)")
        con.execute(f"INSERT INTO sel SELECT id FROM photos WHERE {where}", params)
        q = con.execute

        def counts(col, limit=60):
            return [[r[0], r[1]] for r in q(
                f"SELECT {col}, count(*) FROM photos WHERE id IN (SELECT id FROM sel) GROUP BY 1 "
                f"ORDER BY 2 DESC LIMIT {limit}")]
        tag_counts = [[r[0], r[1]] for r in q(
            "SELECT pt.tag_id, count(*) FROM photo_tags pt WHERE pt.photo_id IN (SELECT id FROM sel) "
            "GROUP BY 1 ORDER BY 2 DESC")]
        rng = q("SELECT count(*), min(ts), max(ts), sum(size), sum(video), sum(lat IS NOT NULL), "
                "min(iso), max(iso), min(aperture), max(aperture), "
                "min(coalesce(focal35, focal)), max(coalesce(focal35, focal)) "
                "FROM photos WHERE id IN (SELECT id FROM sel)").fetchone()
        return jresp(request, {
            "count": rng[0], "tsMin": rng[1], "tsMax": rng[2], "bytes": rng[3] or 0,
            "videos": rng[4] or 0, "geotagged": rng[5] or 0,
            "iso": [rng[6], rng[7]], "aperture": [rng[8], rng[9]], "focal": [rng[10], rng[11]],
            "tags": tag_counts, "years": sorted(counts("year", 300), reverse=True),
            "cameras": counts("camera"), "lenses": counts("lens"), "formats": counts("fmt"),
            "ratings": counts("rating"), "picks": counts("pick"), "colors": counts("color"),
            "albums": counts("album_id", 400), "creators": counts("creator"),
            "objects": _object_counts(q), "npeople": [c for c in counts("npeople") if c[0] is not None],
            "extras": dict(q("SELECT 'blurry', count(*) FROM photos WHERE sharpn < 0.1 AND id IN (SELECT id FROM sel) UNION ALL "
                             "SELECT 'sharpest', count(*) FROM photos WHERE sharpn >= 0.8 AND id IN (SELECT id FROM sel) UNION ALL "
                             "SELECT 'hastext', count(*) FROM photos WHERE length(ocr) >= 3 AND id IN (SELECT id FROM sel) UNION ALL "
                             "SELECT 'bursts', count(*) FROM photos WHERE burst IS NOT NULL AND id IN (SELECT id FROM sel) UNION ALL "
                             "SELECT 'dark', count(*) FROM photos WHERE (bright < 0.2 OR clip_lo > 0.5) AND id IN (SELECT id FROM sel) UNION ALL "
                             "SELECT 'bright', count(*) FROM photos WHERE (bright > 0.8 OR clip_hi > 0.3) AND id IN (SELECT id FROM sel)").fetchall()),
            "places": [[r[0], r[1], r[2], r[3]] for r in q(
                "SELECT place, region, country, count(*) FROM photos WHERE place IS NOT NULL AND id IN (SELECT id FROM sel) "
                "GROUP BY 1, 2, 3 ORDER BY 4 DESC LIMIT 200")],
            "countries": [c for c in counts("country") if c[0]],
        })
    except sqlite3.OperationalError as e:
        raise HTTPException(400, f"Bad query: {e}")
    finally:
        con.close()


def _object_counts(q) -> list:
    c = Counter()
    for (objs,) in q("SELECT objects FROM photos WHERE objects IS NOT NULL AND id IN (SELECT id FROM sel)"):
        c.update(o for o in objs.split(",") if o)
    return [[k, v] for k, v in c.most_common(80)]


@lru_cache(maxsize=2)
def _events(version: str) -> list:
    con = db()
    try:
        return moments.events_and_trips(con)
    finally:
        con.close()


@app.get("/api/events")
def api_events(request: Request):
    """Trips (runs of days away from home) and busy days, worked out from dates, places and titles."""
    return jresp(request, {"events": _events(state["version"])})


@app.get("/api/bursts")
def api_bursts(request: Request, offset: int = 0, limit: int = 40):
    """Bursts within the current filters, newest first, each with its frames and best pick."""
    items = [(k, v) for k, v in request.query_params.multi_items() if k not in ("offset", "limit")]
    where, params, _ = resolve(items)
    con = db()
    try:
        ids = [r[0] for r in con.execute(
            f"SELECT burst FROM photos WHERE burst IS NOT NULL AND {where} GROUP BY burst ORDER BY max(ts) DESC", params)]
        page = ids[max(0, offset):max(0, offset) + max(1, min(limit, 200))]
        rows = con.execute(
            f"SELECT id, burst, burst_best, w, h, ts, sharpn, faceq, pick, rating FROM photos "
            f"WHERE burst IN ({','.join(map(str, page)) or 'NULL'}) ORDER BY ts, name").fetchall()
        total_photos = con.execute(f"SELECT count(*) FROM photos WHERE burst IS NOT NULL AND {where}", params).fetchone()[0]
    except sqlite3.OperationalError as e:
        raise HTTPException(400, f"Bad query: {e}")
    finally:
        con.close()
    groups = {b: [] for b in page}
    for r in rows:
        groups[r["burst"]].append({"id": r["id"], "best": r["burst_best"], "w": r["w"], "h": r["h"], "ts": r["ts"],
                                   "sharpn": r["sharpn"], "faceq": r["faceq"], "pick": r["pick"], "rating": r["rating"]})
    return jresp(request, {"bursts": len(ids), "photos": total_photos, "offset": offset,
                           "groups": [{"burst": b, "items": groups[b]} for b in page]})


@app.get("/api/trail")
def api_trail(request: Request, day: str):
    """The day's geotagged photos in time order, to draw the route taken."""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day):
        raise HTTPException(400, "day must be YYYY-MM-DD")
    con = db()
    try:
        rows = con.execute("SELECT id, ts, lat, lon, alt FROM photos WHERE day = ? AND lat IS NOT NULL ORDER BY ts", (day,)).fetchall()
    finally:
        con.close()
    return jresp(request, {"day": day, "id": [r[0] for r in rows], "ts": [r[1] for r in rows],
                           "lat": [round(r[2], 6) for r in rows], "lon": [round(r[3], 6) for r in rows], "alt": [r[4] for r in rows]})


@app.get("/api/map")
def api_map(request: Request):
    where, params, _ = resolve(request.query_params.multi_items())
    con = db()
    try:
        rows = con.execute(
            f"SELECT id, lat, lon FROM photos WHERE lat IS NOT NULL AND {where} ORDER BY ts DESC", params).fetchall()
    except sqlite3.OperationalError as e:
        raise HTTPException(400, f"Bad query: {e}")
    finally:
        con.close()
    return jresp(request, {"id": [r[0] for r in rows], "lat": [round(r[1], 5) for r in rows],
                           "lon": [round(r[2], 5) for r in rows]})


@app.get("/api/photo/{photo_id}")
def api_photo(photo_id: int, request: Request):
    con = db()
    try:
        row = con.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
        if not row:
            raise HTTPException(404)
        d = dict(row)
        d["extra"] = json.loads(d["extra"]) if d["extra"] else {}
        album = con.execute("SELECT id, path, name FROM albums WHERE id = ?", (d["album_id"],)).fetchone()
        d["album"] = {"id": album["id"], "path": album["path"], "name": album["name"]} if album else None
        d["tags"] = [dict(r) for r in con.execute(
            "SELECT t.id, t.name, t.full, t.person FROM photo_tags pt JOIN tags t ON t.id = pt.tag_id "
            "WHERE pt.photo_id = ? ORDER BY t.person DESC, t.full COLLATE NOCASE", (photo_id,))]
        d["faces"] = [dict(r) for r in con.execute(
            "SELECT f.tag_id AS tag, t.name, f.x, f.y, f.w, f.h FROM faces f JOIN tags t ON t.id = f.tag_id "
            "WHERE f.photo_id = ? AND f.kind = 'confirmed' ORDER BY f.x", (photo_id,))]
        d["faces_other"] = [dict(r) for r in con.execute(
            "SELECT f.tag_id AS tag, f.kind, f.x, f.y, f.w, f.h, (SELECT name FROM tags t WHERE t.id = f.tag_id) AS name "
            "FROM faces f WHERE f.photo_id = ? AND f.kind != 'confirmed' ORDER BY f.x", (photo_id,))]
        d.pop("hash", None)
        d["ualbums"] = [r[0] for r in con.execute("SELECT album_id FROM st.ualbum_items WHERE photo_id = ?", (photo_id,))]
        d["similar"] = semantic_enabled()
        d["concepts"] = concepts.for_photo(photo_id) if semantic_enabled() else []
        d["boxes"] = analysis.boxes(photo_id)
        if d.get("burst"):
            d["burst_size"] = con.execute("SELECT count(*) FROM photos WHERE burst = ?", (d["burst"],)).fetchone()[0]
            best = con.execute("SELECT id, name FROM photos WHERE burst = ? AND burst_best = 1", (d["burst"],)).fetchone()
            d["burst_best_id"], d["burst_best_name"] = (best[0], best[1]) if best else (None, None)
        return jresp(request, d)
    finally:
        con.close()


# --------------------------------------------------------------------------
# Images
# --------------------------------------------------------------------------

def _photo_row(photo_id: int, cols: str = THUMB_COLS) -> dict:
    con = db()
    try:
        row = con.execute(f"SELECT {cols} FROM photos WHERE id = ?", (photo_id,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404)
    return dict(row)


def _cached_image(kind: str, photo_id: int, dl: bool = False) -> FileResponse:
    row = _photo_row(photo_id)
    try:
        path = thumbs.make(kind, row)
    except FileNotFoundError:
        raise HTTPException(404, "Original file is not available")
    if dl:  # a download of the resized JPEG, named after the photo (sharing a smaller file)
        return FileResponse(path, media_type="image/jpeg", filename=os.path.splitext(row["name"])[0] + "-preview.jpg",
                            content_disposition_type="attachment", headers=IMG_CACHE)
    return FileResponse(path, media_type="image/jpeg", headers=IMG_CACHE)


@app.get("/thumb/{photo_id}")
def thumb(photo_id: int):
    return _cached_image("t", photo_id)


@app.get("/preview/{photo_id}")
def preview(photo_id: int, dl: int = 0):
    """The screen-size JPEG; dl=1 downloads it under the photo's name (Share > Download preview)."""
    return _cached_image("p", photo_id, dl=bool(dl))


@app.get("/face/{tag_id}")
def face(tag_id: int):
    """A face crop to use as a person's avatar."""
    con = db()
    try:
        row = con.execute(
            f"SELECT f.x, f.y, f.w AS fw, f.h AS fh, {', '.join('p.' + c.strip() for c in THUMB_COLS.split(','))} "
            "FROM faces f JOIN photos p ON p.id = f.photo_id JOIN tags t ON t.id = f.tag_id "
            "WHERE f.tag_id = ? AND f.kind = 'confirmed' AND p.video = 0 "
            # the photo chosen in digiKam (or here) wins; otherwise a good, large, recent face
            "ORDER BY (p.id = t.icon) DESC, (p.pick = 1), (min(f.w, f.h) >= 160) DESC, p.rating DESC, p.ts DESC LIMIT 1",
            (tag_id,)).fetchone()
    finally:
        con.close()
    if not row:
        raise HTTPException(404)
    d = dict(row)
    try:
        path = thumbs.make_face(tag_id, d, (d["x"], d["y"], d["fw"], d["fh"]))
    except Exception:
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg", headers=IMG_CACHE)


@app.get("/orig/{photo_id}")
def original(photo_id: int, dl: int = 0):
    """The untouched original file (supports range requests for video)."""
    row = _photo_row(photo_id, "path, name")
    if not os.path.isfile(row["path"]):
        raise HTTPException(404, "Original file is not available")
    mime = mimetypes.guess_type(row["name"])[0] or "application/octet-stream"
    return FileResponse(row["path"], media_type=mime, filename=row["name"],
                        content_disposition_type="attachment" if dl else "inline",
                        headers={"Cache-Control": "private, max-age=3600"})


class _Sink:
    """Write-only buffer so zipfile can stream straight into the HTTP response."""

    def __init__(self):
        self.buf = bytearray()

    def write(self, data):
        self.buf += data
        return len(data)

    def flush(self):
        pass

    def take(self) -> bytes:
        data = bytes(self.buf)
        self.buf.clear()
        return data


def _zip_stream(entries):
    """Yield a zip of (absolute path, name in archive) pairs without ever holding
    more than a chunk in memory. Stored, not deflated: photos don't compress."""
    sink = _Sink()
    with zipfile.ZipFile(sink, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        for path, arc in entries:
            try:
                info = zipfile.ZipInfo.from_file(path, arc)
                src = open(path, "rb")
            except OSError:
                continue  # file missing on disk; skip it
            info.compress_type = zipfile.ZIP_STORED
            with src, zf.open(info, "w", force_zip64=True) as dst:
                while chunk := src.read(1 << 20):
                    dst.write(chunk)
                    yield sink.take()
            yield sink.take()
    yield sink.take()


@app.post("/api/zip")
async def api_zip_post(request: Request):
    """Same as GET /api/zip, for selections too long for a URL (form-encoded body)."""
    items = await _form_items(request)
    d = dict(items)
    return _zip_response(items, 1 if d.get("sidecars") == "1" else 0, d.get("name") or "photos")


@app.get("/api/zip")
def api_zip(request: Request, sidecars: int = 0, name: str = "photos"):
    return _zip_response(request.query_params.multi_items(), sidecars, name)


FILTER_KEYS_IGNORED = {"sort", "name", "sidecars", "part", "part_mb", "sem_k"}


def _zip_parts(items, part_mb: int):
    """The files for a download, split into parts of at most part_mb megabytes each.
    The split is by album order, so the parts are stable between calls."""
    if not any(k not in FILTER_KEYS_IGNORED and v != "" for k, v in items):
        raise HTTPException(400, "Choose an album, a search or a selection first; the whole library is not offered as one download.")
    where, params, _ = resolve(items)
    con = db()
    try:
        rows = con.execute(
            f"SELECT p.path, a.path, p.name, p.size FROM photos p JOIN albums a ON a.id = p.album_id "
            f"WHERE p.id IN (SELECT id FROM photos WHERE {where}) ORDER BY a.path, p.name", params).fetchall()
    except sqlite3.OperationalError as e:
        raise HTTPException(400, f"Bad query: {e}")
    finally:
        con.close()
    limit = max(100, min(int(part_mb or 2000), 16000)) * 1024 * 1024
    parts, cur, cur_bytes = [], [], 0
    for r in rows:
        size = r[3] or 0
        if cur and cur_bytes + size > limit:
            parts.append(cur)
            cur, cur_bytes = [], 0
        cur.append(r)
        cur_bytes += size
    if cur:
        parts.append(cur)
    return parts


@app.post("/api/zip/plan")
async def api_zip_plan(request: Request):
    """How a download would be split. Body: the filters, form-encoded, plus part_mb."""
    items = await _form_items(request)
    parts = _zip_parts(items, int(dict(items).get("part_mb") or 2000))
    return {"files": sum(len(p) for p in parts), "bytes": sum(r[3] or 0 for p in parts for r in p),
            "parts": [{"files": len(p), "bytes": sum(r[3] or 0 for r in p),
                       "first": p[0][1].strip("/"), "last": p[-1][1].strip("/")} for p in parts]}


def _zip_response(items, sidecars: int, name: str):
    """Download the originals matching the filters as a zip (or one part of a split
    download), keeping the album folder structure. Optionally includes XMP sidecars."""
    d = dict(items)
    parts = _zip_parts(items, int(d.get("part_mb") or 2000))
    if not parts:
        raise HTTPException(404, "Nothing matches")
    part = int(d.get("part") or 0)
    if part < 0 or part >= len(parts):
        raise HTTPException(404, "No such part")
    rows = parts[part]

    def entries():
        for path, album, fname, _size in rows:
            arc = f"{album.strip('/')}/{fname}".lstrip("/")
            yield path, arc
            if sidecars and os.path.isfile(path + ".xmp"):
                yield path + ".xmp", arc + ".xmp"

    safe = re.sub(r"[^\w .()+-]+", "_", name).strip(" ._")[:80] or "photos"
    if len(parts) > 1:
        safe += f" (part {part + 1} of {len(parts)})"
    return StreamingResponse(_zip_stream(entries()), media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename=\"{safe}.zip\"", "Cache-Control": "no-store"})


# --------------------------------------------------------------------------
# Favorites and app albums (app-side state; digiKam is not touched)
# --------------------------------------------------------------------------

def _with_hashes(ids) -> list:
    ids = [int(i) for i in ids][:50000]
    if not ids:
        return []
    con = db()
    try:
        return [(r[0], r[1]) for r in con.execute(f"SELECT id, hash FROM photos WHERE id IN ({','.join(map(str, ids))})")]
    finally:
        con.close()


@app.get("/api/state")
def api_state(request: Request):
    return jresp(request, {"rev": appstate.rev, **appstate.summary()})


@app.post("/api/favorites")
async def api_favorites(request: Request):
    body = await request.json()
    appstate.set_favorites(_with_hashes(body.get("ids", [])), bool(body.get("on", True)))
    return {"ok": True}


@app.post("/api/ualbums")
async def api_ualbum_create(request: Request):
    body = await request.json()
    name = str(body.get("name", "")).strip()[:200]
    if not name:
        raise HTTPException(400, "Album name is required")
    album_id = appstate.create_album(name)
    if body.get("ids"):
        appstate.set_album_items(album_id, _with_hashes(body["ids"]), True)
    return {"id": album_id}


@app.post("/api/ualbums/{album_id}")
async def api_ualbum_update(album_id: int, request: Request):
    """Body: {name} to rename, {ids, on} to add or remove photos, {delete: true} to remove the album."""
    body = await request.json()
    if body.get("delete"):
        appstate.delete_album(album_id)
    if body.get("name"):
        appstate.rename_album(album_id, str(body["name"]).strip()[:200])
    if "ids" in body:
        appstate.set_album_items(album_id, _with_hashes(body["ids"]), bool(body.get("on", True)))
    return {"ok": True}


# --------------------------------------------------------------------------
# Metadata editing (sidecars, image files when enabled, digiKam's database on request)
# --------------------------------------------------------------------------

@app.post("/api/edit")
async def api_edit(request: Request):
    """Change metadata for one or more photos. Written to XMP sidecars (and into the image
    files when that setting is on); digiKam's database only on a later explicit apply.
    Body: {ids: [...], changes: {rating, pick, color, title, caption, taken, shift, gps, template,
    add_tags: [tag ids], remove_tags: [tag ids]}}"""
    if not edits.available():
        raise HTTPException(503, "Editing is not available")
    body = await request.json()
    ids = [int(i) for i in body.get("ids", [])][:20000]
    raw = body.get("changes") or {}
    ch = {}
    if "rating" in raw:
        ch["rating"] = max(0, min(5, int(raw["rating"])))
    if "pick" in raw:
        ch["pick"] = max(0, min(3, int(raw["pick"])))
    if "color" in raw:
        ch["color"] = max(0, min(9, int(raw["color"])))
    for k in ("title", "caption"):
        if k in raw:
            ch[k] = str(raw[k] or "").strip()[:4000]
    per_photo = {}
    if raw.get("taken"):
        t = str(raw["taken"])[:19]
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", t):
            raise HTTPException(400, "Date must be YYYY-MM-DDTHH:MM:SS")
        ch["taken"] = t
    if raw.get("shift"):  # seconds, applied to each photo's own date
        try:
            delta = timedelta(seconds=int(raw["shift"]))
        except (TypeError, ValueError):
            raise HTTPException(400, "Shift must be a number of seconds")
        con0 = db()
        try:
            for r in con0.execute(f"SELECT id, taken FROM photos WHERE id IN ({','.join(map(str, ids)) or 'NULL'})"):
                try:
                    per_photo[r["id"]] = {"taken": (datetime.fromisoformat(r["taken"][:19]) + delta).strftime("%Y-%m-%dT%H:%M:%S")}
                except ValueError:
                    pass
        finally:
            con0.close()
        if not per_photo:
            raise HTTPException(400, "None of these photos has a date to shift")
    if "gps" in raw:
        g = raw["gps"]
        if g:
            try:
                lat, lon = float(g["lat"]), float(g["lon"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(400, "Location needs lat and lon")
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise HTTPException(400, "Latitude or longitude out of range")
            alt = g.get("alt")
            ch["gps"] = {"lat": round(lat, 7), "lon": round(lon, 7), "alt": (round(float(alt), 1) if alt not in (None, "") else None)}
        else:
            ch["gps"] = None
    if isinstance(raw.get("template"), dict):
        ch["template"] = {k: str(v or "").strip()[:1000] for k, v in raw["template"].items() if k in edits.TEMPLATE_FIELDS}
    con = db()
    try:
        for k in ("add_tags", "remove_tags"):
            tag_ids = [int(t) for t in raw.get(k, [])]
            if tag_ids:
                rows = con.execute(f"SELECT full FROM tags WHERE person = 0 AND id IN ({','.join(map(str, tag_ids))})").fetchall()
                if len(rows) != len(set(tag_ids)):
                    raise HTTPException(400, "Only existing keyword tags can be edited here (people tags stay in digiKam)")
                ch[k] = [r[0] for r in rows]
        photos = [dict(r) for r in con.execute(
            f"SELECT id, path FROM photos WHERE id IN ({','.join(map(str, ids)) or 'NULL'})")]
    finally:
        con.close()
    if not (ch or per_photo) or not photos:
        raise HTTPException(400, "Nothing to change")
    result = await run_in_threadpool(edits.apply, photos, ch, per_photo)
    _kick.set()
    return result


@app.post("/api/edit/revert")
async def api_edit_revert(request: Request):
    """Undo the viewer's edits to these photos by restoring the sidecar backup."""
    body = await request.json()
    ids = [int(i) for i in body.get("ids", [])][:20000]
    con = db()
    try:
        photos = [dict(r) for r in con.execute(
            f"SELECT id, path FROM photos WHERE edited = 1 AND id IN ({','.join(map(str, ids)) or 'NULL'})")]
    finally:
        con.close()
    result = await run_in_threadpool(edits.revert, photos)  # runs exiftool; keep the event loop free
    _kick.set()
    return result


# --------------------------------------------------------------------------
# Settings, background analysis, models, maintenance
# --------------------------------------------------------------------------

def _settings_public() -> dict:
    return {"write_files": edits.writes_files(), "search_model": semantic.chosen(), "bg_threads": bgjobs.threads(), "read_only": appstate.read_only(), "database": _db_settings_public(), "album_roots": dkdb.root_overrides(), "map_provider": appstate.get_setting("map_provider", "osm"), "google_maps_key_set": bool(maps.key()), "templates": json.loads(appstate.get_setting("templates", "[]"))}


@app.get("/api/settings")
def api_settings_get():
    """The settings the Settings page shows (admin values are read-only here; secrets are never included)."""
    return _settings_public()


@app.post("/api/settings")
async def api_settings(request: Request):
    """Body: {write_files: bool} - also write metadata into image files (JPEG, PNG, TIFF, WebP), not just sidecars."""
    body = await request.json()
    if "write_files" in body:
        appstate.set_setting("write_files", "1" if body["write_files"] else "0")
    if "read_only" in body:  # browse only: every library-changing endpoint is refused while it is on
        if config.READ_ONLY and not body["read_only"]:
            raise HTTPException(400, "Read-only mode is locked on by READ_ONLY=1 in the environment")
        appstate.set_setting("read_only", "1" if body["read_only"] else "0")
    if body.get("digikam_closed"):  # Docker: the owner vouches that digiKam is closed, for 10 minutes
        appstate.set_setting("digikam_closed_until", str(time.time() + 600))
    if "templates" in body:  # metadata templates: [{name, fields}]
        tpls = [{"name": str(t.get("name", ""))[:80], "fields": {k: str(v or "")[:1000] for k, v in (t.get("fields") or {}).items() if k in edits.TEMPLATE_FIELDS}}
                for t in body["templates"] if isinstance(t, dict) and t.get("name")]
        appstate.set_setting("templates", json.dumps(tpls))
    if "database" in body:  # admin: the digiKam database connection; applies at once (the index rebuilds)
        d = body["database"] or {}
        for k in dkdb.KEYS:
            if k == "password" and not d.get("password"):
                continue  # an empty password field means "keep the stored one"
            if k in d:
                appstate.set_setting("db_" + k, str(d[k]).strip() if d[k] is not None else "")
        _kick.set()
    if "album_roots" in body:  # admin: {digiKam path: local path}; empty value removes an override
        d = body["album_roots"] or {}
        if not isinstance(d, dict):
            raise HTTPException(400, "album_roots must be an object")
        appstate.set_setting("album_roots", json.dumps({str(k): str(v).strip() for k, v in d.items() if str(v).strip()}))
        _kick.set()
    if "map_provider" in body:  # osm or google; google needs a key (setting or GOOGLE_MAPS_API_KEY)
        if body["map_provider"] not in ("osm", "google"):
            raise HTTPException(400, "Unknown map provider")
        appstate.set_setting("map_provider", body["map_provider"])
        maps.reset_session()
        geocode._cache.clear()
    if "google_maps_key" in body:  # stored, never shown back
        appstate.set_setting("google_maps_key", str(body["google_maps_key"]).strip())
        maps.reset_session()
    if "bg_threads" in body:  # cores one background job may use; takes effect when the next job starts
        n = int(body["bg_threads"])
        if not 1 <= n < (os.cpu_count() or 4):
            raise HTTPException(400, "Choose between 1 and the number of cores minus one")
        appstate.set_setting("bg_threads", str(n))
    if "search_model" in body:
        name = str(body["search_model"])
        if name not in ENGINES or not semantic_ready(name):
            raise HTTPException(400, "That search model is not installed")
        appstate.set_setting("search_model", name)
        _photos_cached.cache_clear()
        await run_in_threadpool(_start_prewarm)  # starts indexing for the newly chosen model if needed
    return _settings_public()


def nf(n) -> str:
    return f"{n:,}"


def _dir_size(path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.stat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


@app.get("/api/analysis")
def api_analysis():
    """Status of every background analysis, for the AI analysis page."""
    con = db()
    try:
        total, stills = con.execute("SELECT count(*), sum(video = 0) FROM photos").fetchone()
    finally:
        con.close()
    cov = analysis.coverage()
    up = semantic.upgrade
    act = semantic.active if semantic_enabled() else None
    if act is not None:
        act.load()
    names = {k: dlmodels.REGISTRY[k]["label"] for k in ENGINES}
    models = [{"key": k, "label": names[k], "installed": semantic_ready(k), "chosen": semantic.chosen() == k,
               "active": act is not None and act.name == k} for k in ENGINES]
    jobs = [
        {"key": "thumbs", "label": "Thumbnails", "detail": "Small previews for the grid.",
         "done": total - (prewarmer.total - prewarmer.done if prewarmer.running else 0), "total": total,
         "running": prewarmer.running, "enabled": True, "rerun": False, "since": prewarmer.started, "last": prewarmer.last, "current": list(prewarmer.current.values())[:3]},
        {"key": "embeddings", "label": "Content search", "enabled": act is not None, "rerun": True,
         "detail": (f"Model: {names[act.name]}." + (("" if act is up else f" Switching to {names[up.name]}: ") + f"{nf(len(up.ids) if up.ids is not None else 0)} of {nf(total)} indexed" + ("; results come from the photos indexed so far." if act is up else f"; search stays on {names[act.name]} until it finishes.") if up else "")
                    + (f" {nf(len(act.failed))} could not be embedded (no thumbnail; see the server log)." if act is not None and act.failed else "")) if act else "Not installed (see README).",
         "done": int(len(act.ids)) if act is not None and act.ids is not None else 0, "total": total, "running": semantic.running},
        {"key": "quality", "label": "Sharpness and exposure", "detail": "Used for the Blurry / Sharpest filters and for picking the best frame of a burst. Computed in the same pass as object detection (one decode per photo), so the two rows advance together.",
         "done": cov["quality"], "total": stills, "running": analysis.progress["quality"]["running"], "enabled": config.ANALYSIS, "rerun": True},
        {"key": "vision", "label": "Text in photos and face quality", "detail": "Text recognition (RapidOCR) makes signs, jerseys, documents and screenshots searchable; face quality is measured on each face region.",
         "done": cov["vision"], "total": stills, "running": analysis.progress["vision"]["running"],
         "enabled": config.ANALYSIS and analysis.vision_available(), "rerun": True},
        {"key": "objects", "label": "Object detection", "detail": "YOLOX-S: people, balls, animals, vehicles and other everyday objects, with boxes. Computed in the same pass as sharpness and exposure, so the two rows advance together.",
         "done": cov["objects"], "total": stills, "running": analysis.progress["objects"]["running"],
         "enabled": config.ANALYSIS and detector.MODEL.exists(), "rerun": True},
        {"key": "captions", "label": "Photo descriptions", "detail": "A one-sentence description of each photo (BLIP), searchable from the search box and shown in the info panel.",
         "done": cov["captions"], "total": stills, "running": analysis.progress["captions"]["running"],
         "enabled": config.ANALYSIS and caption.available(), "rerun": True},
    ]
    queue_key = {"thumbs": "thumbs", "embeddings": "embeddings", "quality": "pixels", "objects": "pixels", "vision": "vision", "captions": "captions"}
    for j in jobs:
        j["queued"] = bgjobs.is_queued(queue_key[j["key"]])
    return {"jobs": jobs, "photos": total, "models": models if act is not None else [], "queue": bgjobs.status()}


@app.post("/api/auth/login")
async def api_login(request: Request):
    body = await request.json()
    u = users.authenticate(str(body.get("name", "")), str(body.get("password", "")))
    if not u:
        raise HTTPException(401, "Wrong user name or password")
    resp = JSONResponse({"user": u, "settings": users.get_settings(u["id"])})
    resp.set_cookie(users.COOKIE, users.make_token(u["id"]), max_age=users.SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/")
    return resp


@app.get("/api/auth/accounts")
def api_accounts():
    """The account picker (public): names, and whether a password is needed."""
    return {"accounts": users.accounts() if users.any_users() else []}


@app.post("/api/auth/logout")
def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(users.COOKIE, path="/")
    return resp


@app.get("/api/auth/me")
def api_me(request: Request):
    u = request.state.user
    return {"user": u, "settings": users.get_settings(u["id"]) if u else {}, "usersExist": users.any_users(),
            "isAdmin": users.is_admin(u), "canWrite": users.can_write(u), "signedIn": users.is_signed_in(u)}


@app.post("/api/auth/settings")
async def api_my_settings(request: Request):
    """Per-user display settings: {key: value, …}; null removes a key."""
    u = request.state.user
    if not u:
        raise HTTPException(401, "Sign in first")
    return users.set_settings(u["id"], await request.json())


@app.post("/api/auth/password")
async def api_my_password(request: Request):
    u = request.state.user
    if not u:
        raise HTTPException(401, "Sign in first")
    body = await request.json()
    if not u.get("passwordless") and not users.authenticate(u["name"], str(body.get("current", ""))):
        raise HTTPException(403, "The current password is wrong")
    try:
        users.update(u["id"], password=str(body.get("password", "")))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


@app.post("/api/auth/setup")
async def api_setup(request: Request):
    """First admin, allowed only while no user exists."""
    if users.any_users():
        raise HTTPException(409, "Users already exist; sign in as an admin")
    body = await request.json()
    try:
        u = users.create(str(body.get("name", "")), str(body.get("password", "")), "admin")
    except ValueError as e:
        raise HTTPException(400, str(e))
    resp = JSONResponse({"user": u})
    resp.set_cookie(users.COOKIE, users.make_token(u["id"]), max_age=users.SESSION_DAYS * 86400, httponly=True, samesite="lax", path="/")
    return resp


def _person_tag(tag_id) -> bool:
    """Is this a person tag in the index (a tag under People with digiKam's person property)?"""
    if not tag_id:
        return True
    con = db()
    try:
        r = con.execute("SELECT person FROM tags WHERE id = ?", (int(tag_id),)).fetchone()
        return bool(r and r[0])
    finally:
        con.close()


@app.post("/api/auth/person")
async def api_my_person(request: Request):
    """Link the signed-in account to a person from People: {person: tag id or null}."""
    u = request.state.user
    if not u:
        raise HTTPException(401, "Sign in first")
    body = await request.json()
    if not _person_tag(body.get("person")):
        raise HTTPException(400, "That tag is not a person")
    users.set_person(u["id"], body.get("person"))
    return users.get(u["id"])


@app.get("/api/users")
def api_users(request: Request):
    if not users.is_admin(request.state.user):
        raise HTTPException(403, "Admins only")
    return {"users": users.list_users(), "roles": list(users.ROLES)}


@app.post("/api/users")
async def api_users_create(request: Request):
    body = await request.json()
    try:
        return users.create(str(body.get("name", "")), str(body.get("password", "")), str(body.get("role", "viewer")), str(body.get("email") or ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/users/{user_id}")
async def api_users_update(user_id: int, request: Request):
    """{role} and/or {password} and/or {name} and/or {email} (optional; "" clears it); {delete: true} removes the user."""
    body = await request.json()
    if not users.get(user_id):
        raise HTTPException(404, "No such user")
    try:
        if body.get("delete"):
            if request.state.user and request.state.user["id"] == user_id:
                raise ValueError("You cannot delete your own account while signed in")
            users.delete(user_id)
        else:
            users.update(user_id, role=body.get("role"), password=body.get("password"), name=body.get("name"), email=body.get("email"))
            if "person" in body:
                if not _person_tag(body["person"]):
                    raise ValueError("That tag is not a person")
                users.set_person(user_id, body["person"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True}


def _db_settings_public() -> dict:
    c = dkdb.settings()
    return {k: c[k] for k in dkdb.KEYS if k != "password"} | {"password_set": bool(c["password"]), "env_type": dkdb.ENV["type"]}


@app.get("/api/roots")
async def api_roots(request: Request):
    """Album roots from digiKam with the local folder each one maps to (admin)."""
    if not users.is_admin(request.state.user):
        raise HTTPException(403, "Admins only")
    return {"roots": await run_in_threadpool(dkdb.album_roots), "photosRoot": str(config.PHOTOS_ROOT)}


@app.post("/api/db/test")
async def api_db_test(request: Request):
    """Try connection settings without saving them (admin). Body: the database fields; an empty password keeps the stored one."""
    if not users.is_admin(request.state.user):
        raise HTTPException(403, "Admins only")
    d = await request.json()
    try:
        return await run_in_threadpool(dkdb.test_connection, d)
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {str(e)[:200]}")


@app.get("/api/maps")
def api_maps():
    """Tile provider for the browser: OpenStreetMap, or Google Maps with the owner's key (session created here)."""
    return maps.config()


@app.get("/api/geocode")
async def api_geocode(q: str = ""):
    """Address or landmark search for the location dialog: OpenStreetMap's Nominatim (the same
    project the map tiles come from), with the offline GeoNames towns as a fallback."""
    q = q.strip()
    if len(q) < 2:
        return {"results": [], "source": None}
    return await run_in_threadpool(geocode.search, q)


@app.get("/api/models")
def api_models():
    """The downloadable models and data: what is installed, and the last update check."""
    return dlmodels.listing()


@app.post("/api/models/check")
async def api_models_check():
    """Ask each source whether the installed files have changed since they were downloaded (network)."""
    await run_in_threadpool(dlmodels.check_all)
    return dlmodels.listing()


@app.post("/api/models/download")
async def api_models_download(request: Request):
    """Body: {key}. Downloads (again) in the background; the server itself stays offline."""
    key = (await request.json()).get("key")
    if key not in dlmodels.REGISTRY:
        raise HTTPException(400, "Unknown model")
    try:
        dlmodels.download(key)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.get("/api/update")
def api_update():
    """Installed commit, the last GitHub check, and whether update.sh can run here."""
    return updates.status()


@app.post("/api/update")
async def api_update_run(request: Request):
    """Body: {action: check | run, ref?}. check asks GitHub (network); run starts update.sh
    (admin), optionally for a given commit or branch."""
    body = await request.json()
    action = body.get("action")
    if action == "check":
        return await run_in_threadpool(updates.check)
    if action == "run":
        try:
            updates.run(str(body.get("ref") or ""))
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return {"ok": True}
    if action == "token":  # admin: the MCP update token (shown once here, never in /api/update)
        return {"token": updates.admin_token(), "fromEnv": bool(os.environ.get("MCP_ADMIN_TOKEN"))}
    if action == "regenerate_token":
        if os.environ.get("MCP_ADMIN_TOKEN"):
            raise HTTPException(400, "The token comes from MCP_ADMIN_TOKEN in the environment; change it there")
        return {"token": updates.regenerate_token()}
    raise HTTPException(400, "action must be check, run, token or regenerate_token")


@app.post("/api/restart")
def api_restart():
    """Exit; launchd (KeepAlive) or Docker (restart: unless-stopped) starts the viewer again."""
    threading.Timer(0.5, lambda: os._exit(0)).start()
    return {"ok": True}


@app.get("/api/maintenance")
def api_maintenance():
    """Library and storage facts for the Settings page."""
    con = db()
    try:
        built = con.execute("SELECT value FROM meta WHERE key = 'built'").fetchone()
        n = con.execute("SELECT count(*) FROM photos").fetchone()[0]
    finally:
        con.close()
    dk_mtime = dkdb.last_change_time()
    free = shutil.disk_usage(str(config.DATA_DIR)).free
    return {
        "photos": n, "indexBuilt": int(built[0]) if built else None, "digikamSaved": dk_mtime,
        "digikamRunning": dbsync.digikam_running(), "pendingEdits": len(edits.pending()),
        "paths": {"library": str(config.PHOTOS_ROOT), "digikamDb": dkdb.describe(), "data": str(config.DATA_DIR)},
        "storage": {k: _dir_size(config.DATA_DIR / v) for k, v in (
            ("thumbnails", "cache/t"), ("previews", "cache/p"), ("faces", "cache/f"), ("models", "models"),
            ("backups", "sidecar-backups"), ("fileBackups", "file-backups"), ("dbBackups", "db-backups"))} | {
            "index": config.INDEX_DB.stat().st_size if config.INDEX_DB.exists() else 0,
            "analysis": analysis.DB.stat().st_size if analysis.DB.exists() else 0,
            "embeddings": sum(e.file.stat().st_size for e in semantic.engines.values() if e.file.exists()),
            "free": free},
        "writeFiles": edits.writes_files(), "readOnly": appstate.read_only(), "readOnlyLocked": config.READ_ONLY, "database": _db_settings_public(), "mapProvider": appstate.get_setting("map_provider", "osm"), "googleMapsKeySet": bool(maps.key()), "searchModel": semantic.chosen(),
        "templates": json.loads(appstate.get_setting("templates", "[]")), "templateFields": list(edits.TEMPLATE_FIELDS),
        "recentTags": json.loads(appstate.get_setting("recent_tags", "[]")),
    }


@app.post("/api/maintenance")
async def api_maintenance_run(request: Request):
    """Body: {action}. reindex: rebuild the search index from digiKam's database now.
    thumbs: throw away all grid thumbnails and rebuild. previews / faces: clear those caches.
    covers: pick tag cover photos again."""
    body = await request.json()
    action = body.get("action")
    if action == "reindex":
        await run_in_threadpool(index.build)
        state["version"] = None  # so _refresh treats the new index as a change
        _kick.set()
    elif action in ("thumbs", "previews", "faces"):
        await run_in_threadpool(shutil.rmtree, config.CACHE_DIR / {"thumbs": "t", "previews": "p", "faces": "f"}[action], ignore_errors=True)
        if action == "thumbs":
            await run_in_threadpool(_start_prewarm)
    elif action == "covers":
        threading.Thread(target=_compute_tag_covers, args=(state.get("source"),), daemon=True).start()
    else:
        raise HTTPException(400, "Unknown action")
    return {"ok": True}


@app.post("/api/analysis/run")
async def api_analysis_run(request: Request):
    """Body: {job: all|embeddings|quality|vision|objects, reset: bool}. Without reset it only
    picks up photos that are new or changed; with reset that analysis starts over."""
    body = await request.json()
    job, reset = body.get("job", "all"), bool(body.get("reset"))
    if reset:
        if job == "embeddings" and semantic_enabled():
            (semantic.upgrade or semantic.active).reset()
        elif job in ("quality", "vision", "objects", "captions"):
            analysis.reset(job)
        else:
            raise HTTPException(400, "Choose one analysis to run again from scratch")
    await run_in_threadpool(_start_prewarm)
    _kick.set()
    return {"ok": True}


# --------------------------------------------------------------------------
# Consistency report and writing pending edits to digiKam's database
# --------------------------------------------------------------------------

@app.get("/api/consistency")
def api_consistency(field: str = None, offset: int = 0, limit: int = 100):
    """The metadata consistency report: photos whose database, sidecar and file disagree."""
    return {"progress": consistency.progress, "summary": consistency.summary(),
            **consistency.report(field or None, max(0, offset), max(1, min(limit, 500)))}


@app.post("/api/consistency/scan")
async def api_consistency_scan(request: Request):
    """Body: the usual filters (form-encoded) to scan a subset, or nothing for the whole library;
    rescan_all=0 only compares photos not checked since they last changed."""
    items = await _form_items(request)
    d = dict(items)
    where, params, _ = resolve([(k, v) for k, v in items if k != "rescan_all"])
    con = db()
    try:
        rows = [dict(r) for r in con.execute(
            f"SELECT id, path, name, video, hash, size, modified FROM photos WHERE {where} ORDER BY ts DESC", params)]
    finally:
        con.close()
    consistency.scan(rows, rescan_all=d.get("rescan_all", "1") != "0")
    return {"queued": len(rows)}


@app.post("/api/consistency/sync")
async def api_consistency_sync(request: Request):
    """Body: {ids, source: db|sidecar|file, targets: [...], fields: [...]}."""
    body = await request.json()
    ids = [int(i) for i in body.get("ids", [])][:20000]
    try:
        res = await run_in_threadpool(consistency.sync, ids, body.get("source"), body.get("targets") or [], body.get("fields"))
    except dbsync.SyncError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    _kick.set()
    return res


@app.get("/api/edits/db")
def api_edits_db_status():
    return {"pending": len(edits.pending()), "digikamRunning": dbsync.digikam_running(), "enabled": config.DB_WRITE,
            "ask": config.DIGIKAM_CHECK == "ask"}


@app.post("/api/edits/db")
def api_edits_db_apply():
    """Write the pending edits into digiKam's database. Refused while digiKam is running."""
    if not config.DB_WRITE:
        raise HTTPException(403, "Writing to the digiKam database is turned off (DB_WRITE=0)")
    try:
        result = dbsync.apply_pending()
    except dbsync.SyncError as e:
        raise HTTPException(409, str(e))
    except (sqlite3.Error, OSError) as e:
        raise HTTPException(500, f"The update failed and was rolled back: {e}")
    _kick.set()
    return result


# --------------------------------------------------------------------------
# Positions from GPX tracks
# --------------------------------------------------------------------------

_gpx_tracks: dict = {}  # token -> parsed points, kept in memory for this server run


@app.post("/api/gpx/preview")
async def api_gpx_preview(request: Request):
    """Multipart: file (.gpx), ids (comma-separated), utc_offset, clock_shift, max_gap (seconds),
    only_missing (1 = skip photos that already have a position). Returns matches without writing."""
    form = await request.form()
    up = form.get("file")
    if up is None:
        raise HTTPException(400, "Upload a .gpx file")
    data = await up.read()
    if len(data) > 50 * 1024 * 1024:
        raise HTTPException(400, "GPX file is larger than 50 MB")
    try:
        points = await run_in_threadpool(gpx.parse, data)  # up to 50 MB of XML; keep the event loop free
    except Exception as e:
        raise HTTPException(400, f"Could not read the GPX file: {e}")
    if not points:
        raise HTTPException(400, "The GPX file has no timed track points")
    ids = [int(x) for x in str(form.get("ids", "")).split(",") if x.strip().isdigit()][:20000]
    utc_offset, clock_shift = int(form.get("utc_offset") or 0), int(form.get("clock_shift") or 0)
    max_gap = max(10, min(int(form.get("max_gap") or 600), 86400))
    only_missing = str(form.get("only_missing", "1")) == "1"
    con = db()
    try:
        rows = con.execute(f"SELECT id, ts, lat, name FROM photos WHERE video = 0 AND id IN ({','.join(map(str, ids)) or 'NULL'})").fetchall()
    finally:
        con.close()
    photos = [{"id": r["id"], "ts": r["ts"], "name": r["name"]} for r in rows if not (only_missing and r["lat"] is not None)]
    matches = gpx.correlate(points, photos, utc_offset, clock_shift, max_gap)
    token = secrets.token_hex(8)
    if len(_gpx_tracks) > 20:
        _gpx_tracks.clear()
    _gpx_tracks[token] = points
    names = {p["id"]: p["name"] for p in photos}
    matched = [dict(m, name=names[m["id"]]) for m in matches if m["matched"]]
    return {"token": token, "track": gpx.summary(points), "considered": len(photos), "skipped_with_position": len(rows) - len(photos),
            "matched": len(matched), "matches": matched[:2000], "unmatched": len(matches) - len(matched)}


@app.post("/api/gpx/apply")
async def api_gpx_apply(request: Request):
    """Body: {token, ids, utc_offset, clock_shift, max_gap, only_missing}. Writes the matched
    positions as GPS edits (sidecar, file if enabled; database on the next apply)."""
    body = await request.json()
    points = _gpx_tracks.get(str(body.get("token")))
    if not points:
        raise HTTPException(409, "The track preview has expired; load the GPX file again")
    ids = [int(i) for i in body.get("ids", [])][:20000]
    con = db()
    try:
        rows = con.execute(f"SELECT id, ts, lat, path FROM photos WHERE video = 0 AND id IN ({','.join(map(str, ids)) or 'NULL'})").fetchall()
    finally:
        con.close()
    only_missing = bool(body.get("only_missing", True))
    photos = [{"id": r["id"], "ts": r["ts"], "path": r["path"]} for r in rows if not (only_missing and r["lat"] is not None)]
    matches = gpx.correlate(points, photos, int(body.get("utc_offset") or 0), int(body.get("clock_shift") or 0), max(10, min(int(body.get("max_gap") or 600), 86400)))
    per_photo = {m["id"]: {"gps": {"lat": m["lat"], "lon": m["lon"], "alt": m["alt"]}} for m in matches if m["matched"]}
    targets = [p for p in photos if p["id"] in per_photo]
    if not targets:
        raise HTTPException(400, "No photo matches the track")
    result = await run_in_threadpool(edits.apply, targets, {}, per_photo)
    _kick.set()
    return result


# --------------------------------------------------------------------------
# Faces (digiKam's database; digiKam must be closed)
# --------------------------------------------------------------------------

@app.post("/api/faces/op")
async def api_face_op(request: Request):
    """One face change (see facemgr.apply). Writes digiKam's database; digiKam must be closed."""
    if not (config.DB_WRITE and edits.available()):
        raise HTTPException(403, "Face management needs editing and database writes enabled")
    op = await request.json()
    try:
        res = await run_in_threadpool(facemgr.apply, op)
    except dbsync.SyncError as e:
        raise HTTPException(409, str(e))
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as e:
        raise HTTPException(500, f"The change failed and was rolled back: {e}")
    _kick.set()
    return res


@app.post("/api/faces/batch")
async def api_face_batch(request: Request):
    """Many face changes in one transaction with one backup: {ops: [...]} (see facemgr.apply_many)."""
    if not (config.DB_WRITE and edits.available()):
        raise HTTPException(403, "Face management needs editing and database writes enabled")
    body = await request.json()
    ops = [o for o in (body.get("ops") or []) if isinstance(o, dict)][:2000]
    if not ops:
        raise HTTPException(400, "No operations")
    try:
        res = await run_in_threadpool(facemgr.apply_many, ops)
    except dbsync.SyncError as e:
        raise HTTPException(409, str(e))
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError) as e:
        raise HTTPException(500, f"The change failed and was rolled back: {e}")
    _kick.set()
    return {"results": res, "done": sum(1 for r in res if "error" not in r), "failed": [r for r in res if "error" in r]}


@app.get("/api/faces/queue")
def api_faces_queue(kind: str = "suggested", tag: int = None, offset: int = 0, limit: int = 200):
    """Faces waiting for a decision: suggestions grouped by the suggested person, or unnamed faces."""
    if kind not in ("suggested", "unknown", "ignored"):
        raise HTTPException(400, "kind must be suggested, unknown or ignored")
    con = db()
    try:
        where, params = "f.kind = ?", [kind]
        if tag:
            where += " AND f.tag_id = ?"
            params.append(tag)
        total = con.execute(f"SELECT count(*) FROM faces f WHERE {where}", params).fetchone()[0]
        rows = con.execute(
            f"SELECT f.photo_id, f.tag_id, f.x, f.y, f.w, f.h, p.ts, p.name AS photo, p.w AS pw, p.h AS ph, "
            f"(SELECT name FROM tags t WHERE t.id = f.tag_id) AS name FROM faces f JOIN photos p ON p.id = f.photo_id "
            f"WHERE {where} ORDER BY f.tag_id, p.ts DESC, f.x LIMIT ? OFFSET ?", params + [max(1, min(limit, 500)), max(0, offset)]).fetchall()
        groups = [[r["tag_id"], r["name"], r["c"]] for r in con.execute(
            "SELECT f.tag_id, (SELECT name FROM tags t WHERE t.id = f.tag_id) AS name, count(*) AS c FROM faces f "
            "WHERE f.kind = ? GROUP BY f.tag_id ORDER BY c DESC", (kind,))] if kind == "suggested" else []
        return {"total": total, "offset": offset, "groups": groups,
                "faces": [{"photo": r["photo_id"], "tag": r["tag_id"], "name": r["name"], "x": r["x"], "y": r["y"], "w": r["w"], "h": r["h"],
                           "ts": r["ts"], "file": r["photo"], "pw": r["pw"], "ph": r["ph"]} for r in rows]}
    finally:
        con.close()


@app.get("/facecrop/{photo_id}/{x}/{y}/{w}/{h}.jpg")
def facecrop(photo_id: int, x: int, y: int, w: int, h: int):
    """A square crop around any face rectangle (upright pixels), for the face queues."""
    row = _photo_row(photo_id)
    try:
        path = thumbs.make_face(0, row, (x, y, w, h))
    except Exception:
        raise HTTPException(404)
    return FileResponse(path, media_type="image/jpeg", headers=IMG_CACHE)


@app.post("/api/faces/person")
async def api_face_person(request: Request):
    """Create a new person tag: {name, parent} (parent = a People family tag id, or 0)."""
    if not (config.DB_WRITE and edits.available()):
        raise HTTPException(403, "Needs editing and database writes enabled")
    body = await request.json()
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "A name is needed")
    try:
        tid = await run_in_threadpool(facemgr.create_person, name, int(body.get("parent") or 0))
    except dbsync.SyncError as e:
        raise HTTPException(409, str(e))
    _kick.set()
    return {"id": tid}


@app.get("/api/faces/summary")
def api_faces_summary():
    con = db()
    try:
        return {k: list(con.execute("SELECT count(DISTINCT photo_id), count(*) FROM faces WHERE kind = ?", (k,)).fetchone())
                for k in ("unknown", "suggested", "ignored")}  # [photos, faces]
    finally:
        con.close()


# --------------------------------------------------------------------------
# Place tags and keyword tags (digiKam's database; digiKam must be closed)
# --------------------------------------------------------------------------

@app.get("/api/placetags")
def api_placetags_plan(ids: str = None):
    """What creating place tags would do, for the whole library or a comma-separated id list."""
    sel = [int(x) for x in ids.split(",") if x.strip().isdigit()] if ids else None
    p = placetags.plan(sel)
    p.pop("_todo", None)
    return {**p, "progress": placetags.progress, "digikamRunning": dbsync.digikam_running(), "root": placetags.ROOT}


@app.post("/api/placetags")
async def api_placetags_run(request: Request):
    """Create missing Places/Country/Region/Town tags (digiKam closed) and assign them."""
    if not (config.DB_WRITE and edits.available()):
        raise HTTPException(403, "Needs editing and database writes enabled")
    if placetags.progress["running"]:
        raise HTTPException(409, "Already running")
    body = await request.json()
    sel = [int(i) for i in body.get("ids", [])] or None
    p = await run_in_threadpool(placetags.plan, sel)
    if p["missing_tags"] and dbsync.digikam_running():
        raise HTTPException(409, "digiKam is running. Quit digiKam first; new place tags are created in its database.")
    placetags.run(sel)
    return {"to_tag": p["to_tag"], "creating": len(p["missing_tags"])}


@app.post("/api/tags/recent")
async def api_tags_recent(request: Request):
    """Remember the tags just assigned, newest first (shown as a quick row like digiKam's)."""
    body = await request.json()
    ids = [int(i) for i in body.get("ids", [])][:20]
    old = [int(i) for i in json.loads(appstate.get_setting("recent_tags", "[]"))]
    new = ids + [i for i in old if i not in ids]
    appstate.set_setting("recent_tags", json.dumps(new[:12]))
    return {"recent": new[:12]}


@app.post("/api/tags/op")
def api_tag_op(op: dict):
    """Add, rename, move or delete a keyword tag (writes digiKam's database; digiKam must be closed)."""
    if not (config.DB_WRITE and edits.available()):
        raise HTTPException(403, "Tag management is turned off (needs DB_WRITE and EDITING)")
    try:
        result = tagmanager.apply(op)
    except dbsync.SyncError as e:
        raise HTTPException(409, str(e))
    except (sqlite3.Error, OSError, ValueError) as e:
        raise HTTPException(500, f"The change failed and was rolled back: {e}")
    _kick.set()
    return result


# --------------------------------------------------------------------------
# Detected content and duplicates
# --------------------------------------------------------------------------

@app.get("/api/concepts")
def api_concepts(request: Request):
    """What the content-search model sees: everyday subjects with how many photos match each."""
    if not semantic_enabled():
        return jresp(request, {"enabled": False, "concepts": []})
    con = db()
    try:
        valid = [r[0] for r in con.execute("SELECT id FROM photos")]
    finally:
        con.close()
    return jresp(request, {"enabled": True, "indexing": semantic.running, "concepts": concepts.summary(valid)})


@app.get("/api/duplicates")
def api_duplicates(request: Request):
    """Groups of files with identical content (same digiKam file hash and size)."""
    con = db()
    try:
        rows = con.execute(
            "SELECT p.id, p.hash, p.size, p.w, p.h, p.video, p.ts, p.name, a.path FROM photos p "
            "JOIN albums a ON a.id = p.album_id WHERE (p.hash, p.size) IN (SELECT hash, size FROM photos "
            "WHERE hash IS NOT NULL AND hash != '' GROUP BY hash, size HAVING count(*) > 1) "
            "ORDER BY p.size DESC, p.hash, a.path, p.name").fetchall()
    finally:
        con.close()
    groups, cur = [], None
    for r in rows:
        if cur is None or cur["key"] != (r[1], r[2]):
            cur = {"key": (r[1], r[2]), "size": r[2], "items": []}
            groups.append(cur)
        cur["items"].append({"id": r[0], "w": r[3], "h": r[4], "video": r[5], "ts": r[6], "name": r[7], "album": r[8]})
    for g in groups:
        del g["key"]
    return jresp(request, {"groups": groups, "wasted": sum(g["size"] * (len(g["items"]) - 1) for g in groups)})


@app.middleware("http")
async def static_revalidate(request: Request, call_next):
    response = await call_next(request)
    if "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache"
    return response


# MCP over HTTP on the same port: an assistant connects to http://host:8600/mcp (read-only tools).
# DNS-rebinding protection is off because the viewer is reached by LAN name or IP, not localhost only.
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

_mcp_asgi = mcp_server.server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                                   transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
# its route handles the exact path /mcp; placed first so the static root mount never sees it
app.router.routes[:0] = list(_mcp_asgi.routes)
app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
