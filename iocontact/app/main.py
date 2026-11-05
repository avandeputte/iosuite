"""ioContacts: the application (start-up, who is asking, the routes and the web app)."""
import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import APP_VERSION, api, carddav, config, db, ldapd, mcp, users
from app.auth import auth as auth_shared, updater

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("iocontacts")
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
    server = None
    if config.LDAP_PORT:
        try:
            server = await ldapd.serve(config.LDAP_HOST, config.LDAP_PORT)
        except OSError as e:
            log.warning("LDAP directory not started on port %s: %s", config.LDAP_PORT, e)
    updater.start_daily()  # the daily "is there a newer version" check, while the setting allows it
    sm = mcp.server.session_manager
    sm._has_started = False  # a second start in the same process (the tests start the app once per test) is allowed
    async with sm.run():  # the MCP endpoint (/mcp) lives in this process
        yield
    if server:
        server.close()


app = FastAPI(title="ioContacts", version=APP_VERSION, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="Contacts for the family. Also served over CardDAV at /dav/ (vCard 3.0 and 4.0), LDAP "
                          "(read-only) and as a birthday calendar (iCalendar). JSON by default; ask for text/vcard or "
                          "application/vcard+json (jCard) with Accept or ?format=vcard|vcard4|jcard.")


OPEN = ("/api/status", "/api/auth/login", "/api/auth/setup", "/api/auth/logout", "/api/docs", "/api/openapi.json")


@app.middleware("http")
async def who(request: Request, call_next):
    """Who is asking (iothing-auth: the shared session cookie, the proxy's sign-in, HTTP Basic or a bearer app
    password). Everything but the web app's files, sign-in and the calendar feed (its own secret link) needs one of them."""
    path = request.url.path
    refused = await auth_shared.resolve(request)
    if refused is not None:
        return refused
    user = request.state.user
    tok = request.cookies.get(users.COOKIE)
    if path == "/mcp" or path.startswith("/mcp/"):
        if not await run_in_threadpool(api.mcp_enabled):
            return JSONResponse({"detail": "The MCP server is switched off (Settings › Server in the web app)."}, status_code=404)
        if not user:
            return JSONResponse({"detail": "Sign in with your user name and an app password (HTTP Basic), or send "
                                           "'Authorization: Bearer <app password>'. Make one in Settings › Apps and devices."},
                                status_code=401, headers={"WWW-Authenticate": 'Basic realm="ioContacts", Bearer realm="ioContacts"'})
        mcp.current_user.set(user)  # every tool acts as this account
    if path.startswith("/api/") and not user and path not in OPEN and not path.startswith("/api/auth/accounts"):
        return JSONResponse({"detail": "Sign in first"}, status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="ioContacts"'} if "authorization" in request.headers else {})
    # a page on another site cannot drive this one with the browser's cookie
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and tok and path.startswith("/api/") and auth_shared.cross_site(request):
        return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    resp = await call_next(request)
    auth_shared.finish(request, resp)  # a proxy sign-in gets a session cookie here too
    if path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp




def _server_info() -> dict:
    """What Maintenance › Updates and logs and Settings › Server show beside the updater's own fields."""
    return {"mcpEnabled": api.mcp_enabled(), "mcpLocked": config.MCP_FORCED,
            "database": f"{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}",
            "ldap": f"{config.LDAP_HOST or '0.0.0.0'}:{config.LDAP_PORT}" if config.LDAP_PORT else None}


def _server_apply(body: dict) -> None:
    """The MCP switch, sent to POST /api/server as {mcpEnabled: bool}."""
    if "mcpEnabled" in body:
        if config.MCP_FORCED and not body["mcpEnabled"]:
            raise ValueError("MCP=1 in the environment keeps the MCP server on")
        db.set_setting("mcp_enabled", "1" if body["mcpEnabled"] else "0")


app.include_router(auth_shared.server_router(updater, log_file=config.LOG_FILE, info=_server_info, apply=_server_apply))  # /api/server, /api/log (admins)
app.include_router(api.router)
app.include_router(carddav.router)

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
        html = html.replace(f'"{f}"', f'"{f}?v={APP_VERSION}"')
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(config.STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
