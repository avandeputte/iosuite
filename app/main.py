"""ioSuite: the application (start-up, who is asking, the routes and the web app)."""
import logging
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__, api, config, db, users
from app.auth import auth as auth_shared, updater
from iosuite_shared import sessions

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("iosuite")
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
    yield


app = FastAPI(title="ioSuite", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="The start page of the iothing suite: one place with every io app, and the accounts they share.")


OPEN = ("/api/status", "/api/docs", "/api/openapi.json")


@app.middleware("http")
async def who(request: Request, call_next):
    """Who is asking (iosuite-shared: the shared session cookie, the proxy's sign-in, HTTP Basic or a bearer app
    password). Everything but the web app's files and sign-in needs one."""
    path = request.url.path
    refused = await auth_shared.resolve(request)
    if refused is not None:
        return refused
    user = request.state.user
    tok = request.cookies.get(sessions.COOKIE)
    if path.startswith("/api/") and not user and path not in OPEN and not path.startswith("/api/auth/"):
        return JSONResponse({"detail": "Sign in first"}, status_code=401,
                            headers={"WWW-Authenticate": 'Basic realm="ioSuite"'} if "authorization" in request.headers else {})
    # a page on another site cannot drive this one with the browser's cookie
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and tok and path.startswith("/api/") and auth_shared.cross_site(request):
        return JSONResponse({"detail": "Cross-site request refused"}, status_code=403)
    resp = await call_next(request)
    auth_shared.finish(request, resp)  # a proxy sign-in gets a session cookie here too
    if path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
    return resp


app.include_router(auth_shared.router())        # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords
app.include_router(auth_shared.users_router())  # /api/users: accounts and their role here (admins)
app.include_router(api.router)


def _server_info() -> dict:
    """What Maintenance › Updates and logs and Settings › Server show beside the updater's own fields."""
    return {"url": config.PUBLIC_URL or None, "database": f"{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"}


app.include_router(auth_shared.server_router(updater, log_file=config.LOG_FILE, info=_server_info))  # /api/server, /api/log (admins)


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


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
