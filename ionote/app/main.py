"""ionotes: the web app, the API the Mac and iPhone apps use, and the MCP endpoint, on one port (8610).

Who may call a route is declared on the route (app/access.py); the middleware here works out who is asking
(the session cookie, or the identity a reverse proxy such as Cloudflare Access vouches for), whether sign-in is
required at all, and refuses cross-site writes. The same scheme as iopix.
"""
import json
import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, db, mcp, proxyauth, suitedb, updates, users
from app import notes as notes_mod, owners
from app.auth import auth as auth_shared

proxyauth.remember_peer()  # before uvicorn's forwarded-header rewrite runs: proxy sign-in trusts the real peer
from app.routes import auth, notes as notes_routes, settings, users as users_routes  # noqa: E402

log = logging.getLogger("app")
MAX_JSON_BODY = 8 << 20  # a JSON request larger than this is refused before it is read (pictures go as their own body)
MAX_IMAGE_BODY = (config.MAX_IMAGE_MB + 1) << 20

# what a visitor may still fetch when sign-in is required: the app shell and the sign-in endpoints
OPEN_PATHS = ("/", "/index.html", "/app.js", "/app.css", "/sw.js", "/manifest.webmanifest", "/api/status")
OPEN_PREFIXES = ("/icons/", "/static/icons/", "/js/", "/api/auth/")


def setup_file_log():
    """ionotes' own log in data/ionotes.log (5 MB, 3 old copies), for Settings › Server log and the MCP tool."""
    root = logging.getLogger()
    if any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        return
    h = logging.handlers.RotatingFileHandler(config.LOG_FILE, maxBytes=5 << 20, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(h)
    if root.level > logging.INFO or root.level == logging.NOTSET:
        root.setLevel(logging.INFO)
    for name in ("uvicorn.access", "uvicorn.error"):
        logging.getLogger(name).addHandler(h)


@asynccontextmanager
async def lifespan(_app):
    setup_file_log()
    try:
        db.init()
    except Exception as e:
        db.error = str(e)[:300]
        log.error("the database could not be opened: %s", e)
        raise
    users.init()
    if db.get_setting("mcp_enabled", "") == "":
        db.set_setting("mcp_enabled", "0")
    updates.start_daily()
    c = db.settings()
    log.info("ionotes started on %s (%s)", "MariaDB/MySQL " + f"{c['host']}:{c['port']}/{c['database']}" if c["type"] == "mysql" else "SQLite " + str(db.SQLITE_FILE),
             "accounts exist" if users.any_users() else "no accounts yet: open to everyone until one is made")
    sd = suitedb.public()
    log.info("Shared ioSuite database (accounts, suite settings): %s@%s:%s/%s", sd["user"], sd["host"], sd["port"], sd["database"])
    if suitedb.note:
        log.warning(suitedb.note)
    async with mcp.server.session_manager.run():
        yield


app = FastAPI(title="ionotes", lifespan=lifespan, docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json")


def _open_to_visitors(path: str) -> bool:
    return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


def mcp_enabled() -> bool:
    """Settings › MCP server: off unless an admin turns it on (or MCP=1 in the environment)."""
    return config.MCP_FORCED or db.get_setting("mcp_enabled", "0") == "1"


def _mcp_token_ok(request: Request) -> bool:
    auth_h = request.headers.get("authorization", "")
    return auth_h.lower().startswith("bearer ") and updates.token_ok(auth_h[7:].strip())


def _owner_of(request: Request) -> int:
    """Whose notes this request sees: the signed-in account's; before any account exists, the open install's (0);
    a visitor once accounts exist sees none."""
    u = request.state.user
    if u:
        return int(u["id"])
    return 0 if not users.any_users() else notes_mod.NOBODY


def _gate(request: Request):
    """Once the user is known (app/auth.py's middleware): whose notes the request works on, and the MCP endpoint's
    own gates (the switch; with sign-in required, the admin token on every request)."""
    path = request.url.path
    if not notes_mod._claimed and users.any_users():
        notes_mod.claim_unowned(owners.first_admin_id())
    notes_mod.current_owner.set(owners.mcp_owner() if path.startswith("/mcp") else _owner_of(request))
    if path.startswith("/mcp"):
        if not mcp_enabled():
            return JSONResponse({"detail": "The MCP server is switched off (Settings › MCP server)."}, status_code=404)
        mcp.token_given.set(_mcp_token_ok(request))
        if request.state.user is None and users.require_login() and not _mcp_token_ok(request):
            return JSONResponse({"detail": "Sign-in is required; MCP clients send the admin token as 'Authorization: Bearer <token>'"}, status_code=401)
    return None


# who is asking (the shared session cookie, the proxy's identity), whether sign-in is required at all, and the
# cross-site check on writes: iothing-auth's middleware. What each route needs beyond that is declared on the
# route (app/access.py).
app.middleware("http")(auth_shared.middleware(is_open=_open_to_visitors, open_prefixes=("/mcp",), before=_gate))


@app.middleware("http")
async def _limits(request: Request, call_next):
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        try:
            size = int(request.headers.get("content-length") or 0)
        except ValueError:
            return JSONResponse({"detail": "Bad Content-Length"}, status_code=400)
        limit = MAX_IMAGE_BODY if (ctype.startswith("image/") or ctype in ("multipart/form-data", "application/octet-stream", "application/zip")) else MAX_JSON_BODY
        if "/api/import" in request.url.path:
            limit = 4 << 30
        if size > limit:
            return JSONResponse({"detail": "That request is too large"}, status_code=413)
    response = await call_next(request)
    if "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.exception_handler(notes_mod.NotFound)
async def _not_found(request: Request, e: Exception):
    """Another account's note or folder, or none at all: the same 404 either way."""
    return JSONResponse({"detail": str(e) or "Not found"}, status_code=404)


@app.exception_handler(ValueError)
@app.exception_handler(TypeError)
@app.exception_handler(json.JSONDecodeError)
async def _bad_input(request: Request, e: Exception):
    """A body or parameter that is not what a route expects is the client's mistake: a 400 that says so."""
    log.warning("bad input on %s %s: %s: %s", request.method, request.url.path, type(e).__name__, str(e)[:200])
    return JSONResponse({"detail": f"Bad request: {str(e)[:200] or type(e).__name__}"}, status_code=400)


app.include_router(auth.router)
app.include_router(users_routes.router)
app.include_router(notes_routes.router)
app.include_router(settings.router)

# MCP over HTTP on the same port: an assistant connects to http://host:8610/mcp.
# DNS-rebinding protection is off because ionotes is reached by LAN name or IP, not localhost only.
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

_mcp_asgi = mcp.server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                           transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
app.router.routes[:0] = list(_mcp_asgi.routes)
# /static/...: the same files at the path the suite's apps share (the icon in iothing-auth's list: /static/icons/mark.svg)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static-suite")
app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
