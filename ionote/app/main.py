"""ionotes: the web app, the API the Mac and iPhone apps use, and the MCP endpoint, on one port (8610).

Who may call a route is declared on the route (app/access.py); the middleware here works out who is asking
(the session cookie, or the identity a reverse proxy such as Cloudflare Access vouches for), whether sign-in is
required at all, and refuses cross-site writes. The same scheme as iopix.
"""
import json
import logging
import logging.handlers
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app import config, db, mcp, proxyauth, updates, users

proxyauth.remember_peer()  # before uvicorn's forwarded-header rewrite runs: proxy sign-in trusts the real peer
from app.routes import auth, notes as notes_routes, settings, users as users_routes  # noqa: E402

log = logging.getLogger("app")
MAX_JSON_BODY = 8 << 20  # a JSON request larger than this is refused before it is read (pictures go as their own body)
MAX_IMAGE_BODY = (config.MAX_IMAGE_MB + 1) << 20

# what a visitor may still fetch when sign-in is required: the app shell and the sign-in endpoints
OPEN_PATHS = ("/", "/index.html", "/app.js", "/app.css", "/sw.js", "/manifest.webmanifest", "/api/status")
OPEN_PREFIXES = ("/icons/", "/js/", "/api/auth/")


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


def _no_access(request: Request, ident: str):
    msg = f"{ident} has no account on these notes. Ask their owner for access."
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": msg, "noAccess": True}, status_code=403)
    from html import escape
    out = "/cdn-cgi/access/logout" if proxyauth.external(request.headers, proxyauth.peer_of(request)) else None
    return HTMLResponse(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>No access</title><style>body{{font:16px system-ui,sans-serif;max-width:520px;margin:15vh auto;padding:0 16px;color:#222;background:#fff}}
@media (prefers-color-scheme:dark){{body{{color:#eee;background:#111}}a{{color:#78d9ec}}}}</style>
<h1>No access</h1><p>{escape(msg)}</p>{f'<p><a href="{out}">Sign in with another account</a></p>' if out else ''}""", status_code=403)


@app.middleware("http")
async def _auth_guard(request: Request, call_next):
    """Who is asking (session cookie or the proxy's identity), whether sign-in is required at all, and the
    cross-site check on writes. What each route needs beyond that is declared on the route (app/access.py)."""
    session = request.cookies.get(users.COOKIE)
    user = (await run_in_threadpool(users.user_from_token, session)) if session else None
    cookie_uid = user["id"] if user else None
    request.state.via_proxy = False
    if "cf-access-jwt-assertion" in request.headers and time.time() - proxyauth.seen.get("at", 0) > 60:
        proxyauth.note(request.headers, proxyauth.peer_of(request))
    if proxyauth.mode() != "off":
        pu = await run_in_threadpool(proxyauth.user, request)
        if pu:
            user, request.state.via_proxy = pu, True
        elif getattr(request.state, "proxy_ident", None) and proxyauth.deny_unknown() and not request.url.path.startswith("/mcp"):
            return _no_access(request, request.state.proxy_ident)
    if user and not request.state.via_proxy and user.get("passwordless") and proxyauth.external(request.headers, proxyauth.peer_of(request)):
        user = None  # a passwordless account's session (begun on the LAN) does not work from outside
    request.state.user = user
    path = request.url.path
    if path.startswith("/mcp"):
        if not await run_in_threadpool(mcp_enabled):
            return JSONResponse({"detail": "The MCP server is switched off (Settings › MCP server)."}, status_code=404)
        mcp.token_given.set(_mcp_token_ok(request))
    if user is None and await run_in_threadpool(users.require_login):
        if path.startswith("/mcp"):
            if not _mcp_token_ok(request):
                return JSONResponse({"detail": "Sign-in is required; MCP clients send the admin token as 'Authorization: Bearer <token>'"}, status_code=401)
        elif not _open_to_visitors(path):
            return JSONResponse({"detail": "Sign in to use ionotes."}, status_code=401)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        # a page on another site cannot drive this one with the browser's cookies (the apps send no Origin)
        origin, site = request.headers.get("origin"), request.headers.get("sec-fetch-site")
        if site == "cross-site" or (origin and (origin == "null" or urlsplit(origin).netloc.lower() != (request.headers.get("host") or "").lower())):
            return JSONResponse({"detail": "Requests from another site are refused"}, status_code=403)
    response = await call_next(request)
    if (user and not request.state.via_proxy and cookie_uid == user["id"] and path not in ("/api/auth/logout", "/api/auth/logout_all", "/api/auth/password")
            and users.renew_due(session) and "set-cookie" not in response.headers):
        users.set_session(response, user["id"], request.cookies.get(users.VIA_COOKIE) or "password", users.over_https(request))
    if request.state.via_proxy and user and cookie_uid != user["id"] and path != "/api/auth/logout":
        # signed in at the proxy (Cloudflare Access): a session here too, so the same browser or app stays signed in
        # on the home network, where requests reach ionotes directly
        users.set_session(response, user["id"], "cloudflare" if proxyauth.mode() == "cloudflare" else "proxy", users.over_https(request))
    return response


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
app.mount("/", StaticFiles(directory=config.STATIC_DIR, html=True), name="static")
