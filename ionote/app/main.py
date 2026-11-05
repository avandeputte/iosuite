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
MAX_IMPORT_BODY = 4 << 30  # an export with every picture; spooled to disk as it arrives, never held in memory

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
    own gates (the switch, and who may read through it)."""
    path = request.url.path
    if not notes_mod._claimed and users.any_users():
        notes_mod.claim_unowned(owners.first_admin_id())
    if not path.startswith("/mcp"):
        notes_mod.current_owner.set(_owner_of(request))
        return None
    if not mcp_enabled():
        return JSONResponse({"detail": "The MCP server is switched off (Settings › MCP server)."}, status_code=404)
    # Notes are private to each account (unlike iopix's shared library), so the MCP endpoint is too: with the admin
    # token it works on the notes of Settings › MCP server › Notes of; a signed-in account without the token sees
    # only its own notes; once accounts exist, anyone else is refused, whether or not sign-in is required.
    tok = _mcp_token_ok(request)
    mcp.token_given.set(tok)
    if tok:
        notes_mod.current_owner.set(owners.mcp_owner())
    elif request.state.user:
        notes_mod.current_owner.set(int(request.state.user["id"]))
    elif users.any_users():
        return JSONResponse({"detail": "MCP clients send the admin token as 'Authorization: Bearer <token>' "
                                       "(Settings › MCP server shows it to an admin)"}, status_code=401)
    else:
        notes_mod.current_owner.set(0)  # no accounts yet: the open install's notes, as in the web app
    return None


# who is asking (the shared session cookie, the proxy's identity), whether sign-in is required at all, and the
# cross-site check on writes: iothing-auth's middleware. What each route needs beyond that is declared on the
# route (app/access.py).
app.middleware("http")(auth_shared.middleware(is_open=_open_to_visitors, open_prefixes=("/mcp",), before=_gate))


class _TooLarge(Exception):
    pass


def _has_too_large(e: BaseException) -> bool:
    if isinstance(e, _TooLarge):
        return True
    return any(_has_too_large(x) for x in getattr(e, "exceptions", ()))  # inside an ExceptionGroup (task groups)


class _BodyCap:
    """The size limits below, for a body that comes without a Content-Length (chunked) or longer than it said:
    counted as it is read, refused (413) once past the limit, so nothing large is ever held in memory. The
    outermost layer, so the refusal reaches it through every middleware."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        ctype = headers.get(b"content-type", b"").decode("latin-1").split(";")[0].strip().lower()
        limit = _limit_for(scope["path"], ctype)
        seen, started = 0, False

        async def capped():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body") or b"")
                if seen > limit:
                    raise _TooLarge()
            return msg

        async def sending(msg):
            nonlocal started
            started = started or msg["type"] == "http.response.start"
            await send(msg)

        try:
            await self.app(scope, capped, sending)
        except BaseException as e:
            if not _has_too_large(e) or started:
                raise
            await JSONResponse({"detail": "That request is too large"}, status_code=413)(scope, receive, send)


def _limit_for(path: str, ctype: str) -> int:
    if "/api/import" in path:
        return MAX_IMPORT_BODY
    if ctype.startswith("image/") or ctype in ("multipart/form-data", "application/octet-stream", "application/zip"):
        return MAX_IMAGE_BODY
    return MAX_JSON_BODY



@app.middleware("http")
async def _limits(request: Request, call_next):
    ctype = (request.headers.get("content-type") or "").split(";")[0].strip().lower()
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        try:
            size = int(request.headers.get("content-length") or 0)
        except ValueError:
            return JSONResponse({"detail": "Bad Content-Length"}, status_code=400)
        if size > _limit_for(request.url.path, ctype):
            return JSONResponse({"detail": "That request is too large"}, status_code=413)
    response = await call_next(request)
    if "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache"
    return response


app.add_middleware(_BodyCap)  # added last: the outermost layer


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
