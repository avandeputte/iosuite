"""ioPix: a web front end for a digiKam library.

Who may call a route is declared on the route (app/access.py); iosuite-shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite. The library (digiKam's database and the photo files) is only read here; the few endpoints that change it
(sidecars, image files, digiKam's database on request) declare access.editor_write or access.admin_write on their route
and go through the modules that own those writes."""
import copy
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi import HTTPException
from iosuite_shared import mcp as shared_mcp
from iosuite_shared.fastapi import public_user
from iosuite_shared.proxyauth import peer_of
from iosuite_shared.updates import setup_log

from app.ai import analysis, models as dlmodels
from app.faces import facedetect, facemgr
from app import access, config, events, jobs as bgjobs, mcp, thumbs, users
from app.auth import auth, updater
from app.photos import consistency, edits, history, lossless, scanner, tagmanager
from app.data import index as photo_index, state as appstate, appdb
from app.digikam import dkdb
from app.geo import maps, places
from app.ai.semantic import enabled as semantic_enabled, semantic
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routes import auth as auth_routes, backup, browse, images, albums, editing, geo, tools, review, organize, faces, settings
from app.runtime import state, kick, refresh, auto, watch, resolve, prewarmer, models_arrived, APP_NAME_DEFAULT, app_name, app_stamp, public_version
from app import __version__ as APP_VERSION

setup_log(config.LOG_FILE)  # the server log that Settings › Server shows; the app runs without it
__all__ = ["app", "state", "kick", "refresh", "auto", "watch", "resolve", "prewarmer"]  # tests and app.mcp reach these through app.main

@asynccontextmanager
async def lifespan(_app):
    appstate.init()
    if not appdb.ready():  # no viewer database (a fresh install, or its server is down): the set-up page only
        logging.getLogger("app.main").error("starting without a viewer database (%s): only the database set-up page answers until one is configured", appdb.error)
        async with shared_mcp.running(mcp.server):
            yield
        return
    users.init()
    maps.declare_keys()  # the Google keys live with the suite's keys and tokens
    edits.init()
    tagmanager.init()
    analysis.init()
    consistency.init()
    analysis.on_progress = kick.set  # fold new analysis results into the index as they arrive
    if tagmanager.pending_jobs():  # finish sidecar updates left over from a previous run
        tagmanager.start_worker()
    facemgr.resume_queue()  # and the face sidecar rewrites a restart interrupted
    refresh(initial=True)
    threading.Thread(target=thumbs.keep_pruned, name="cache-prune", daemon=True).start()  # the previews and the cut-down thumbnails, under their caps
    threading.Thread(target=watch, name="reindex", daemon=True).start()
    scanner.start(events.after_write)  # the file scanner (Settings › Library › File scanner): passes only while it is on
    if dkdb.no_digikam() and scanner.enabled():
        scanner.run_soon()  # no digiKam to have found what was added while iopix was stopped: a pass right after start-up
    updater.start_daily()  # the daily "is there a newer version" check, when the setting allows it
    if config.AUTO_MODELS:  # containers and fresh installs: fetch missing models, then start the jobs that need them
        dlmodels.auto_download(config.AUTO_MODELS, on_done=models_arrived)
    async with shared_mcp.running(mcp.server):  # the MCP endpoint (/mcp) lives in this process
        yield


app = FastAPI(title="ioPix", version=APP_VERSION, lifespan=lifespan, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
              description="A web front end for a digiKam photo library, for the family. Also an MCP endpoint (/mcp) for AI assistants.")

MAX_JSON_BYTES = 4 << 20   # a JSON request larger than this is refused
MAX_UPLOAD_BYTES = 2 << 30  # a multipart upload (photos, a library, a model): what the upload routes accept at most

# what a visitor may still fetch when sign-in is required: the app shell and its files (the map library among them),
# the API docs, a share link, and the MCP endpoint (its gate below)
OPEN_PATHS = ("/", "/sw.js", "/manifest.webmanifest", "/share", "/api/docs", "/api/openapi.json")
OPEN_PREFIXES = ("/static/", "/mcp")


def _open_to_visitors(request: Request) -> bool:
    """What a visitor gets while sign-in is required: the avatars on the sign-in screen. Only the faces accounts are
    linked to, and like the account tiles themselves (/api/auth/accounts) only on the network the server is on."""
    path = request.url.path
    if path.startswith("/face/") and not auth.outside(request):
        tail = path[6:].split("/")[0]
        return tail.isdigit() and int(tail) in users.linked_persons()
    return False


def mcp_enabled() -> bool:
    """Settings › Server › MCP server: off unless an admin turns it on (or MCP=1 in the environment)."""
    return shared_mcp.enabled(appstate.get_setting, config.MCP_FORCED)


def _mcp_user(user):
    """The account an MCP request acts as: its tools see that account's favorites and private albums."""
    mcp.current_user.set(user)
    appstate.viewer.set(user)


_mcp_gate = auth.mcp_gate(mcp_enabled, on_user=_mcp_user)


def _before(request: Request):
    """Once the user is known: who the change history and private albums see, and the MCP endpoint's gate (the switch;
    an app password or session; every tool acts as that account, as in every app of the suite)."""
    user = request.state.user
    history.user.set(user["name"] if user else ("MCP" if request.url.path.startswith("/mcp") else "visitor"))
    appstate.viewer.set(user)  # private albums: seen only by their owner
    return _mcp_gate(request)


# who is asking (the shared session cookie, the proxy's identity, Basic, a bearer app password), whether sign-in is
# required at all, and the cross-site check on writes: iosuite-shared's middleware. What each route needs beyond
# that (an editor, an admin, an account) is declared on the route (app/access.py).
app.middleware("http")(auth.middleware(open_paths=OPEN_PATHS, open_prefixes=OPEN_PREFIXES, is_open=_open_to_visitors, before=_before))


def _outside(request: Request) -> bool:
    """Whether the request comes from outside the network (iosuite-shared's rule: through Cloudflare, from a public
    address, or forwarded by a proxy that is not listed as trusted). When the Shared ioSuite database is away as
    well, the list of trusted proxies cannot be read: only a proxy on this machine is believed then."""
    try:
        return auth.outside(request)
    except Exception:  # noqa: BLE001
        proxy = copy.copy(auth.proxy)
        proxy.opt = lambda name: None
        return proxy.external(request.headers, peer_of(request))


async def _without_database(request: Request, call_next):
    """The viewer has no usable database of its own (appdb.ready() is false): the app shell and the status answer,
    the database set-up endpoints are served here directly, as an admin (there is nobody else yet, as on a fresh
    install; the sign-in middleware and the routes' own checks would need the database), and everything else
    says what is missing. The viewer restarts once a database is chosen. Once a database is configured, only
    Retry stays open (see below). While none is configured, the set-up endpoints answer the network the viewer
    is on and nobody else: they choose the server the viewer connects to, so a visitor from the internet who
    finds a fresh install gets the shell and a 403."""
    path, method = request.url.path, request.method
    if path == "/api/status":
        return JSONResponse({"ok": False, "app": config.APP, "name": APP_NAME_DEFAULT, "version": APP_VERSION, "appName": APP_NAME_DEFAULT,
                             "needsDatabase": True, "databaseError": appdb.error, "databaseConfigured": appdb.configured(), "index": "", "stamp": ""})
    if path.startswith("/api/database"):
        if method not in ("GET", "HEAD", "OPTIONS") and auth.cross_site(request):  # the sign-in middleware's own rule
            return JSONResponse({"detail": "Requests from another site are refused"}, status_code=403)
        # a database is configured but did not answer at start (the server is down, or started after the viewer): nobody is
        # signed in, so nothing here may test another server with the stored password or point the viewer at another
        # database; only Retry, and the error. Changing the connection then is done with DB_* in config.env.
        if appdb.configured():
            if path == "/api/database" and method == "GET":
                return JSONResponse({"configured": True, "locked": True, "error": appdb.error, "type": "mysql"})
            if path == "/api/database/retry" and method == "POST":
                try:
                    return JSONResponse(await settings.api_database_retry())
                except HTTPException as e:
                    return JSONResponse({"detail": e.detail}, status_code=e.status_code)
            if path in ("/api/database/test", "/api/database/switch"):
                return JSONResponse({"detail": f"{APP_NAME_DEFAULT}'s database is configured but not answering ({appdb.error}). "
                                               "Retry once it is up, or change the connection with the DB_* settings in config.env."}, status_code=403)
            return JSONResponse({"detail": "Not found"}, status_code=404)
        if _outside(request):
            return JSONResponse({"detail": f"{APP_NAME_DEFAULT} has no database yet. Choose one from the network the server is on: "
                                           "open the viewer at the server's own address, or put the DB_* settings in config.env."}, status_code=403)
        try:
            if path == "/api/database" and method == "GET":
                return JSONResponse(settings.api_database())
            if path == "/api/database/test" and method == "POST":
                return JSONResponse(await settings.api_database_test(request))
            if path == "/api/database/switch" and method == "POST":
                return JSONResponse(await settings.api_database_switch(request))
            if path == "/api/database/retry" and method == "POST":
                return JSONResponse(await settings.api_database_retry())
        except HTTPException as e:
            return JSONResponse({"detail": e.detail}, status_code=e.status_code)
        return JSONResponse({"detail": "Not found"}, status_code=404)
    if path in OPEN_PATHS or path.startswith("/static/") or path.endswith((".png", ".svg", ".ico")):  # the shell and its files, not the sign-in API
        return await call_next(request)
    return JSONResponse({"detail": f"{APP_NAME_DEFAULT} has no database yet ({appdb.error}); open the viewer to set one up", "needsDatabase": True}, status_code=503)


@app.middleware("http")
async def _database_gate(request: Request, call_next):
    """Registered last, so it runs first: while the viewer has no database of its own, nothing below it runs."""
    if not appdb.ready():
        return await _without_database(request, call_next)
    return await call_next(request)


UPLOAD_PATHS = ("/api/import", "/api/import/stage", "/share")  # and /api/folders/<id>/upload: where photos are sent
MAX_TRACK_BYTES = 64 << 20  # a GPS track to match photos with (/api/gpx/preview)


def _limit_for(path: str, ctype: str) -> int:
    """What BodyCap lets through: JSON and forms a few MiB, and a multipart upload up to MAX_UPLOAD_BYTES on the
    routes that take uploads (which refuse larger files themselves too). Never by the content type alone: a request
    that only calls itself multipart would be read whole by a route that expects JSON, the sign-in among them."""
    if ctype.startswith("multipart/"):
        if path in UPLOAD_PATHS or (path.startswith("/api/folders/") and path.endswith("/upload")):
            return MAX_UPLOAD_BYTES
        if path == "/api/gpx/preview":
            return MAX_TRACK_BYTES
    return MAX_JSON_BYTES


# 400 for bad input, the headers, no-store on the API, the body cap: the same in every app of the suite
auth.install(app, limit_for=_limit_for)


def _status_extra(request: Request) -> dict:
    """ioPix's own fields of GET /api/status, beside the suite's: the index version the page compares to reload, the
    front end's stamp, the jobs, what the viewer may do. On the sign-in screen (sign-in required, nobody signed in):
    only what it needs, nothing about the library or the server."""
    user = request.state.user
    out = {"index": public_version(), "stamp": app_stamp(), "appName": app_name(), "digikamCheck": config.DIGIKAM_CHECK}
    if user is None and users.require_login():
        return {**out, "editing": False, "dbWrite": False, "pendingEdits": 0}
    admin, signed, writer = users.is_admin(user), users.is_signed_in(user), users.can_write(user)
    dk = photo_index.status()
    out.update({
        "error": state["error"] if admin or not state["error"] else "The library could not be read; an admin can see why in Settings › Library.", "rev": appstate.rev,
        "thumbs": {"running": prewarmer.running, "done": prewarmer.done, "total": prewarmer.total, "since": prewarmer.started, "last": prewarmer.last,
                   "current": list(prewarmer.current.values())[:3] if signed else []},  # file paths: not for anonymous clients
        "semantic": {"enabled": semantic_enabled(), "running": semantic.running, "done": semantic.done,
                     "total": semantic.total, "indexed": 0 if semantic.ids is None else int(len(semantic.ids))},
        "places": places.available(), "editing": edits.available() and writer, "pendingEdits": edits.pending_count(),
        "dbWrite": config.DB_WRITE and writer, "writeFiles": edits.writes_files(),
        "user": {**public_user(user), "person": user.get("person")} if user else None,  # the suite's shape, plus the linked person
        "digikam": dk if admin else {k: v for k, v in dk.items() if k != "error"}, "faceDetect": facedetect.available(),
        "lossless": lossless.capabilities() if config.DB_WRITE and edits.available() else None,
        "tagJobs": {**tagmanager.progress, "pending": tagmanager.pending_jobs()},
        "analysis": analysis.progress,
        "jobs": bgjobs.status() if admin else {k: v for k, v in bgjobs.status().items() if k not in ("held", "memory")}})  # the server's memory: for admins
    return out


app.include_router(browse.router)
app.include_router(images.router)
app.include_router(albums.router)
app.include_router(editing.router)
app.include_router(settings.router)
app.include_router(tools.router)
app.include_router(auth.status_router(updater, extra=_status_extra))  # /api/status: public, the same shape in every app
def _server_info() -> dict:
    """What Settings › Server shows beside the updater's own fields: the MCP box."""
    return {"mcpEnabled": mcp_enabled(), "mcpLocked": config.MCP_FORCED,
            "mcpAbout": "Lets an AI assistant search, look at and organize your photos, as you."}


def _server_apply(body: dict) -> None:
    """The MCP switch, sent to POST /api/server as {mcpEnabled: bool}."""
    if "mcpEnabled" in body:
        shared_mcp.set_enabled(appstate.set_setting, bool(body["mcpEnabled"]), config.MCP_FORCED)


app.include_router(auth.server_router(updater, log_file=config.LOG_FILE, info=_server_info, apply=_server_apply))  # /api/server, /api/log: admins
app.include_router(auth_routes.router)
app.include_router(auth.admin_router())  # /api/suite-admin (+ ui.js, the Settings › Security and Global settings panel): the whole suite (suite admins)
app.include_router(geo.router)
app.include_router(backup.router)
app.include_router(review.router)
app.include_router(organize.router)
app.include_router(faces.router)

shared_mcp.mount(app, mcp.server)  # MCP over streamable HTTP at /mcp, ahead of everything else


@app.get("/", include_in_schema=False, dependencies=[access.public])
def index():
    """The page, with the version stamped on the script and stylesheet: after an update the browser (and Cloudflare,
    which caches .js and .css at the edge) fetches the new ones instead of serving what it kept."""
    html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for f in ("static/app.js", "static/app.css"):
        html = html.replace(f'"{f}"', f'"{f}?v={APP_VERSION}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/sw.js", include_in_schema=False, dependencies=[access.public])
def service_worker():
    """At the root, so the service worker's scope is the whole app."""
    return FileResponse(config.STATIC_DIR / "sw.js", media_type="text/javascript")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
