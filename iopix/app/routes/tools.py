"""Settings › Tools and Library: the library facts, background analysis and models, the file scanner and the library merge. The version, updates, restart and the
server log (Settings › Server) are iosuite_shared's server_router (/api/server, /api/log), mounted in app/main.py."""
import json
import shutil
import threading

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from starlette.concurrency import run_in_threadpool

from app.ai import analysis, clothing, jerseys, jobs_meta, models as dlmodels, rotation, videos
from app import access, config, events, jobs as bgjobs, users
from app.digikam import dbsync, dkdb, merge
from app.faces import ages, facedetect, facevecs
from app.photos import edits, paths, scanner
from app.data import index, state as appstate
from app.geo import maps
from app.ai.semantic import ready as semantic_ready, enabled as semantic_enabled, ENGINES, semantic
from app.guards import face_detect_allowed
from app.http import json_body
from app.runtime import DB_ERRORS, app_name, compute_tag_covers, db, start_prewarm, state

from app.routes.settings import db_settings_public

router = APIRouter()


@router.get("/api/analysis", dependencies=[access.public])
def api_analysis(request: Request):
    """Status of every background analysis, for Settings › AI."""
    con = db()
    try:
        total, stills = con.execute("SELECT count(*), coalesce(sum(video = 0), 0) FROM photos").fetchone()  # an empty library sums to NULL
    finally:
        con.close()
    act = semantic.active if semantic_enabled() else None
    if act is not None:
        act.load()
    names = {k: dlmodels.REGISTRY[k]["label"] for k in ENGINES}
    models = [{"key": k, "label": names[k], "installed": semantic_ready(k), "chosen": semantic.chosen() == k,
               "active": act is not None and act.name == k} for k in ENGINES]
    jobs = jobs_meta.rows(total, stills, signed_in=users.is_signed_in(request.state.user))
    queue = bgjobs.status()
    if not users.is_admin(request.state.user):  # how much memory the server has, and what ran out of it: for admins
        queue = {k: v for k, v in queue.items() if k not in ("held", "memory")}
        for j in jobs:
            j["held"] = None
    return {"jobs": jobs, "photos": total, "models": models if act is not None else [], "queue": queue, "progress": bgjobs.progress_all()}


@router.get("/api/models", dependencies=[access.public])
def api_models():
    """The downloadable models and data: what is installed, and the last update check."""
    return dlmodels.listing()


@router.post("/api/models/check", dependencies=[access.admin])
async def api_models_check():
    """Ask each source whether the installed files have changed since they were downloaded (network)."""
    await run_in_threadpool(dlmodels.check_all)
    return dlmodels.listing()


@router.post("/api/models/download", dependencies=[access.admin])
async def api_models_download(request: Request):
    """Body: {key}. Downloads (again) in the background; the server itself stays offline."""
    key = (await json_body(request)).get("key")
    if key not in dlmodels.REGISTRY:
        raise HTTPException(400, "Unknown model")
    try:
        dlmodels.download(key)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@router.get("/api/tools", dependencies=[access.public])
def api_tools(request: Request):
    """Library facts for Settings and Tools (paths and databases for admins only)."""
    con = db()
    try:
        built = con.execute("SELECT value FROM meta WHERE key = 'built'").fetchone()
        n = con.execute("SELECT count(*) FROM photos").fetchone()[0]
    finally:
        con.close()
    dk_mtime = dkdb.last_change_time()
    out = {
        "photos": n, "indexBuilt": int(built[0]) if built else None, "digikamSaved": dk_mtime,
        "digikamRunning": dbsync.digikam_running(), "pendingEdits": edits.pending_count(),
        "paths": {"library": str(config.PHOTOS_ROOT), "digikamDb": dkdb.describe(), "data": str(config.DATA_DIR)},
        "writeFiles": edits.writes_files(), "digikam": index.status(), "appName": app_name(), "appNameSet": appstate.get_setting("app_name", ""),
        "database": db_settings_public(), "mapProvider": appstate.get_setting("map_provider", "osm"), "googleMapsKeySet": bool(maps.key()), "googleServerKeySet": maps.server_key_set(), "sidecarCompat": paths.compat_naming(), "searchModel": semantic.chosen(),
        "templates": json.loads(appstate.get_setting("templates", "[]")), "templateFields": list(edits.TEMPLATE_FIELDS),
        "recentTags": json.loads(appstate.get_setting("recent_tags", "[]")),
        "scanner": _scanner_state(),
    }
    if not users.is_admin(request.state.user):
        for k in ("paths", "database", "albumRoots", "album_roots"):
            out.pop(k, None)
        out["digikam"] = {k: v for k, v in out["digikam"].items() if k != "error"}  # the error names hosts and paths
    if not users.can_write(request.state.user):
        out["templates"], out["recentTags"] = [], []
    return out


def _scanner_state() -> dict:
    return {"enabled": scanner.enabled(), "interval": scanner.interval(), "running": scanner.progress["running"], "last": scanner.progress["last"]}


@router.get("/api/scan", dependencies=[access.public])
def api_scan_status():
    return _scanner_state()


@router.post("/api/scan", dependencies=[access.admin_write])
async def api_scan_run():
    """Scan the album folders now (also when the setting is off): new, changed and vanished files and folders."""
    if not config.DB_WRITE:
        raise HTTPException(403, "Writing to digiKam's database is turned off (DB_WRITE=0)")
    if scanner.progress["running"]:
        raise HTTPException(409, "A scan is already running")
    scanner.run_soon()
    return {"started": True}


@router.post("/api/tools", dependencies=[access.admin])
async def api_tools_run(request: Request):
    """Body: {action}. reindex: rebuild the search index from digiKam's database now.
    thumbs: throw away all grid thumbnails and rebuild. previews / faces: clear those caches.
    covers: pick tag cover photos again."""
    body = await json_body(request)
    action = body.get("action")
    if action == "reindex":
        await run_in_threadpool(index.build)
        state["version"] = None  # so runtime.refresh treats the new index as a change
        events.kick()
    elif action in ("thumbs", "previews", "faces"):
        await run_in_threadpool(shutil.rmtree, config.CACHE_DIR / {"thumbs": "t", "previews": "p", "faces": "f"}[action], ignore_errors=True)
        if action == "thumbs":
            await run_in_threadpool(start_prewarm)
    elif action == "covers":
        threading.Thread(target=compute_tag_covers, args=(state.get("source"),), daemon=True).start()
    else:
        raise HTTPException(400, "Unknown action")
    return {"ok": True}


@router.get("/api/library/merge", dependencies=[access.admin])
def api_library_merge_plan():
    """What merging the changes made with sync off into digiKam's database would do (admins)."""
    try:
        return merge.plan()
    except dbsync.SyncError as e:
        raise HTTPException(409, str(e))


@router.post("/api/library/merge", dependencies=[access.admin_write])
async def api_library_merge():
    """Merge the changes made with sync off into digiKam's database (backup first), then copy the library from digiKam again."""
    if not config.DB_WRITE:
        raise HTTPException(403, "Writing to digiKam's database is turned off")
    try:
        r = await run_in_threadpool(merge.apply)
    except dbsync.SyncError as e:
        raise HTTPException(409, str(e))
    except DB_ERRORS as e:
        raise HTTPException(500, f"The merge failed and was rolled back: {e}")
    await run_in_threadpool(events.after_write)
    return r


@router.post("/api/analysis/run", dependencies=[access.admin])
async def api_analysis_run(request: Request):
    """Body: {job: all|embeddings|quality|vision|objects, reset: bool}. Without reset it only
    picks up photos that are new or changed; with reset that analysis starts over."""
    body = await json_body(request)
    return await run_in_threadpool(start_analysis, body.get("job", "all"), bool(body.get("reset")))


def start_analysis(job: str = "all", reset: bool = False) -> dict:
    """What the Run / Run again / Try again buttons do (and the MCP tool run_analysis): queue one analysis, or all of
    them. Asking is also what lets a job that was paused (stopped twice for memory, jobs.py) run again."""
    if job == "all":
        bgjobs.release()
    elif job in jobs_meta.QUEUE_KEY:
        bgjobs.release(jobs_meta.QUEUE_KEY[job])
    if job == "facedetect":  # writes faces into digiKam's database, so only ever on request
        face_detect_allowed()
        if reset:
            facedetect.reset()
        n = facedetect.start(after=events.after_write)
        return {"ok": True, "queued": n}
    if reset:
        if job == "embeddings" and semantic_enabled():
            (semantic.upgrade or semantic.active).reset()
        elif job in ("quality", "vision", "objects", "captions", "looks"):
            analysis.reset(job)
        elif job == "faces":
            facevecs.reset()
        elif job == "ages":
            ages.reset()
        elif job == "jerseys":
            jerseys.reset()
        elif job == "clothing":
            clothing.reset()
        elif job == "rotation":
            rotation.reset()
        elif job == "videos":
            videos.reset()
        else:
            raise HTTPException(400, "Choose one analysis to run again from scratch")
    start_prewarm()
    events.kick()
    return {"ok": True}
