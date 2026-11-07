"""ioNotes: the web app, the API the Mac and iPhone apps use, and the MCP endpoint, on one port (8610).

Who may call a route is declared on the route (app/access.py); iosuite-shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite. What is ioNotes' own: whose notes a request works on (notes are private to each account).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from iosuite_shared import mcp as shared_mcp
from iosuite_shared.updates import setup_log

from app import __version__, config, db, mcp, suitedb, users
from app import notes as notes_mod, owners
from app.auth import auth, updater
from app.routes import auth as auth_routes, notes as notes_routes, settings, users as users_routes

setup_log(config.LOG_FILE)  # the server log that Maintenance › Updates and logs shows; the app runs without it
log = logging.getLogger("app")

# what a visitor may still fetch when sign-in is required: the app shell and its files, the API docs, and the MCP
# endpoint (its gate below)
OPEN_PATHS = ("/", "/sw.js", "/manifest.webmanifest", "/api/docs", "/api/openapi.json")
OPEN_PREFIXES = ("/static/", "/mcp")


@asynccontextmanager
async def lifespan(_app):
    try:
        db.init()
    except Exception as e:
        db.error = str(e)[:300]
        log.error("the database could not be opened: %s", e)
        raise
    users.init()
    updater.start_daily()
    c = db.settings()
    log.info("ioNotes %s started on %s (%s)", __version__,
             "MariaDB/MySQL " + f"{c['host']}:{c['port']}/{c['database']}" if c["type"] == "mysql" else "SQLite " + str(db.SQLITE_FILE),
             "accounts exist" if users.any_users() else "no accounts yet: open to everyone until one is made")
    sd = suitedb.public()
    log.info("Shared ioSuite database (accounts, suite settings): %s@%s:%s/%s", sd["user"], sd["host"], sd["port"], sd["database"])
    async with shared_mcp.running(mcp.server):  # the MCP endpoint (/mcp) lives in this process
        yield


app = FastAPI(title="ioNotes", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="Notes for the family, private to each account. The API the Mac and iPhone apps use, and an MCP "
                          "endpoint (/mcp) for AI assistants.")


def mcp_enabled() -> bool:
    """Maintenance › MCP server: off until an admin turns it on (or MCP=1 in the environment)."""
    return shared_mcp.enabled(db.get_setting, config.MCP_FORCED)


def _owner_of(request: Request) -> int:
    """Whose notes this request sees: the signed-in account's; before any account exists, the open install's (0);
    a visitor once accounts exist sees none."""
    u = request.state.user
    if u:
        return int(u["id"])
    return 0 if not users.any_users() else notes_mod.NOBODY


def _mcp_user(u: dict) -> None:
    """The MCP endpoint, once its gate let the request through: every tool acts as this account, on its own notes."""
    mcp.current_user.set(u)
    notes_mod.current_owner.set(int(u["id"]))


_mcp_gate = auth.mcp_gate(mcp_enabled, on_user=_mcp_user, settings_page="Maintenance › MCP server")


def _before(request: Request):
    """Once the user is known: whose notes the request works on, and the MCP endpoint's gate (the switch; an app
    password or session, as in every app of the suite)."""
    if not notes_mod._claimed and users.any_users():
        notes_mod.claim_unowned(owners.first_admin_id())
    refused = _mcp_gate(request)
    if refused is not None:
        return refused
    if not request.url.path.startswith("/mcp"):
        notes_mod.current_owner.set(_owner_of(request))
    return None


# who is asking, whether sign-in is required at all, the cross-site check on writes, and whose notes: iosuite-shared's
# middleware. What each route needs beyond that is declared on the route (app/access.py).
app.middleware("http")(auth.middleware(open_paths=OPEN_PATHS, open_prefixes=OPEN_PREFIXES, before=_before))


def _limit_for(path: str, ctype: str) -> int:
    if "/api/import" in path:
        return config.MAX_IMPORT_BYTES
    if ctype.startswith("image/") or ctype in ("multipart/form-data", "application/octet-stream", "application/zip"):
        return config.MAX_IMAGE_BYTES
    return config.MAX_JSON_BYTES


# 400 for bad input, the headers, no-store on the API, the body cap (counted as the body arrives, so nothing large is
# ever held in memory), and the same 404 for another account's note as for none at all: iosuite-shared
auth.install(app, limit_for=_limit_for, not_found=(notes_mod.NotFound,))


def _status_extra(request: Request) -> dict:
    """ioNotes' own fields of GET /api/status, beside the suite's: the name an admin gave the app, read-only mode and,
    signed in, the account's change counter (the page polls it to learn of changes made elsewhere)."""
    out = {"appName": db.get_setting("app_name", "") or "ionotes", "readOnly": db.read_only()}
    if users.is_signed_in(request.state.user):
        out["rev"] = notes_mod.owner_rev()
    return out


app.include_router(auth_routes.router)   # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords, suite
app.include_router(users_routes.router)  # /api/users: accounts and their role here (admins)
app.include_router(auth.admin_router())  # /api/suite-admin (+ ui.js, the Settings › Suite panel): the whole suite (suite admins)
app.include_router(auth.status_router(updater, extra=_status_extra))  # /api/status: public, the same shape in every app
app.include_router(auth.server_router(updater, log_file=config.LOG_FILE, info=lambda: {"appUrl": config.BASE_URL}))  # /api/server, /api/log (admins)
app.include_router(notes_routes.router)
app.include_router(settings.router)
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


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """At the root, so the service worker's scope is the whole app."""
    return FileResponse(config.STATIC_DIR / "sw.js", media_type="text/javascript")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
