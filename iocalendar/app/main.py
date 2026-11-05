"""ioCalendar: the application (start-up, who is asking, the routes and the web app)."""
import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from app import __version__, api, caldav, config, contacts, db, holiday, ical, mcp, model, users
from app.auth import auth as auth_shared, updater
from iosuite_shared import sessions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("iocalendar")
if config.LOG_FILE:  # the server log that Maintenance › Updates and logs shows; the app runs without it
    try:
        _fh = logging.handlers.RotatingFileHandler(config.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(_fh)
    except OSError as e:
        log.warning("no server log at %s: %s", config.LOG_FILE, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(db.migrate)
    await run_in_threadpool(users.ensure_admin_from_env)
    updater.start_daily()   # the daily "is there a newer version" check, while the setting allows it
    contacts.start_sync()   # the Birthdays calendar from ioContacts, every few hours
    holiday.start_sync()    # the Holidays calendar, every day
    sm = mcp.server.session_manager
    sm._has_started = False  # a second start in the same process (the tests start the app once per test) is allowed
    async with sm.run():  # the MCP endpoint (/mcp) lives in this process
        yield


app = FastAPI(title="ioCalendar", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="Calendars for the family. Also served over CalDAV at /dav/ (iCalendar), as subscription links "
                          "(/ics/<private token>/<calendar>.ics) and to AI assistants over MCP (/mcp). JSON by default; ask "
                          "for text/calendar or application/calendar+json (jCal) with Accept or ?format=ics|jcal.")


OPEN = ("/api/status", "/api/docs", "/api/openapi.json")


@app.middleware("http")
async def who(request: Request, call_next):
    """Who is asking (iosuite-shared: the shared session cookie, the proxy's sign-in, HTTP Basic or a bearer app
    password). Everything but the web app's files, sign-in and the subscription links (their own secret) needs one."""
    path = request.url.path
    refused = await auth_shared.resolve(request)
    if refused is not None:
        return refused
    user = request.state.user
    tok = request.cookies.get(sessions.COOKIE)
    if path == "/mcp" or path.startswith("/mcp/"):
        if not await run_in_threadpool(api.mcp_enabled):
            return JSONResponse({"detail": "The MCP server is switched off (Settings › Server in the web app)."}, status_code=404)
        if not user:
            return JSONResponse({"detail": "Sign in with your user name and an app password (HTTP Basic), or send "
                                           "'Authorization: Bearer <app password>'. Make one in Settings › Apps and devices."},
                                status_code=401, headers={"WWW-Authenticate": 'Basic realm="ioCalendar", Bearer realm="ioCalendar"'})
        mcp.current_user.set(user)  # every tool acts as this account
    if path.startswith("/api/") and not user and path not in OPEN and not path.startswith("/api/auth/"):
        return JSONResponse({"detail": "Sign in first"}, status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="ioCalendar"'} if "authorization" in request.headers else {})
    # a page on another site cannot drive this one with the browser's cookie
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and tok and path.startswith("/api/") and auth_shared.cross_site(request):
        return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    resp = await call_next(request)
    auth_shared.finish(request, resp)  # a proxy sign-in gets a session cookie here too
    if path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


@app.exception_handler(model.NotFound)
async def _not_found(request: Request, e: Exception):
    return JSONResponse({"detail": str(e) or "Not found"}, status_code=404)


app.include_router(auth_shared.router())        # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords
app.include_router(auth_shared.users_router())  # /api/users: accounts and their role here (admins)


def _server_info() -> dict:
    """What Maintenance › Updates and logs and Settings › Server show beside the updater's own fields."""
    return {"mcpEnabled": api.mcp_enabled(), "mcpLocked": config.MCP_FORCED, "timezone": ical.default_tz(),
            "database": f"{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"}


def _server_apply(body: dict) -> None:
    """The MCP switch, sent to POST /api/server as {mcpEnabled: bool}."""
    if "mcpEnabled" in body:
        if config.MCP_FORCED and not body["mcpEnabled"]:
            raise ValueError("MCP=1 in the environment keeps the MCP server on")
        db.set_setting("mcp_enabled", "1" if body["mcpEnabled"] else "0")


app.include_router(auth_shared.server_router(updater, log_file=config.LOG_FILE, info=_server_info, apply=_server_apply))  # /api/server, /api/log (admins)
app.include_router(api.router)
app.include_router(caldav.router)

# MCP over streamable HTTP on the same port: an assistant connects to https://host/mcp with an app password.
# DNS-rebinding protection is off because the server is reached by LAN name, IP or a public name, not localhost only;
# every request is signed in anyway.
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402

_mcp_asgi = mcp.server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True,
                                           transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
app.router.routes[:0] = list(_mcp_asgi.routes)  # the exact path /mcp, ahead of everything else


@app.get("/", include_in_schema=False)
def index():
    """The page, with the version stamped on the script and stylesheet: after an update the browser (and Cloudflare,
    which caches .js and .css at the edge) fetches the new ones instead of serving what it kept."""
    html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for f in ("static/app.js", "static/app.css"):
        html = html.replace(f'"{f}"', f'"{f}?v={__version__}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(config.STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


from fastapi.staticfiles import StaticFiles  # noqa: E402

app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
