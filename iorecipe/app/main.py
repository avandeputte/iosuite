"""ioRecipe: the application (start-up, who is asking, the routes and the web app).

Who may call a route is declared on the route (app/access.py); iosuite-shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from iosuite_shared import mcp as shared_mcp
from iosuite_shared.updates import setup_log

from app import __version__, ai, api, config, db, mcp, model, users
from app.auth import auth, updater

setup_log(config.LOG_FILE)  # the server log that Settings › Server shows; the app runs without it
log = logging.getLogger("iorecipe")


# what a visitor may still fetch when sign-in is required: the app shell and its files, the API docs and the MCP
# endpoint (its gate below)
OPEN_PATHS = ("/", "/manifest.webmanifest", "/api/docs", "/api/openapi.json")
OPEN_PREFIXES = ("/static/", "/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(db.migrate)
    await run_in_threadpool(users.init)
    ai.start()              # the AI model on its way, where it is wanted and not there yet
    updater.start_daily()   # the daily "is there a newer version" check, while the setting allows it
    log.info("ioRecipe %s started, database %s:%s/%s", __version__, config.DB_HOST, config.DB_PORT, config.DB_NAME)
    async with shared_mcp.running(mcp.server):  # the MCP endpoint (/mcp) lives in this process
        yield


app = FastAPI(title="ioRecipe", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="The family's recipes: ingredients, steps, a photo, and import from a web page. Also served "
                          "to AI assistants over MCP (/mcp).")


def mcp_enabled() -> bool:
    """Settings › Server › MCP server: off until an admin turns it on (or MCP=1 in the environment)."""
    return shared_mcp.enabled(db.get_setting, config.MCP_FORCED)


# who is asking, whether sign-in is required at all, the cross-site check on writes, and the MCP endpoint's gate (the
# switch; an app password or session; every tool acts as that account): iosuite-shared's middleware
app.middleware("http")(auth.middleware(open_paths=OPEN_PATHS, open_prefixes=OPEN_PREFIXES,
                                       before=auth.mcp_gate(mcp_enabled, on_user=mcp.current_user.set)))


def _limit_for(path: str, ctype: str) -> int:
    if path == "/api/import/file":
        return config.MAX_IMPORT_BYTES
    return config.MAX_PHOTO_BYTES if path.endswith(("/photos", "/import/photo")) else config.MAX_JSON_BYTES


# 400 for bad input, the headers, no-store on the API, the body cap: the same in every app of the suite
auth.install(app, limit_for=_limit_for, not_found=(model.NotFound,))


@app.exception_handler(model.Forbidden)
async def _forbidden(request, e):
    return JSONResponse({"detail": str(e)}, status_code=403)


def _status_extra(request) -> dict:
    """ioRecipe's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"mcp": mcp_enabled() if u else None}


def _server_info() -> dict:
    """What Settings › Server shows beside the updater's own fields: the MCP box."""
    return {"mcpEnabled": mcp_enabled(), "mcpLocked": config.MCP_FORCED,
            "mcpAbout": "Lets an AI assistant look recipes up, add them and import them from the web, as you."}


def _server_apply(body: dict) -> None:
    """The MCP switch, sent to POST /api/server as {mcpEnabled: bool}."""
    if "mcpEnabled" in body:
        shared_mcp.set_enabled(db.set_setting, bool(body["mcpEnabled"]), config.MCP_FORCED)


app.include_router(auth.router())        # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords, suite
app.include_router(auth.users_router())  # /api/users: accounts and their role here (admins)
app.include_router(auth.admin_router())  # /api/suite-admin (+ ui.js, the panel of Settings › Security and Global settings): the whole suite (suite admins)
app.include_router(auth.related_router())  # /api/related (+ ui.js, the "Linked" panel): items linked across the apps
app.include_router(auth.status_router(updater, extra=_status_extra))  # /api/status: public, the same shape in every app
app.include_router(auth.server_router(updater, log_file=config.LOG_FILE, info=_server_info, apply=_server_apply))  # /api/server, /api/log (admins)
app.include_router(api.router)
shared_mcp.mount(app, mcp.server)  # MCP over streamable HTTP at /mcp, ahead of everything else


@app.get("/", include_in_schema=False)
def index():
    """The page, with the version stamped on the script and stylesheet: after an update the browser (and Cloudflare,
    which caches .js and .css at the edge) fetches the new ones instead of serving what it kept."""
    html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for f in ("static/app.js", "static/app.css", "static/js/theme.js"):
        html = html.replace(f'"{f}"', f'"{f}?v={__version__}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(config.STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
