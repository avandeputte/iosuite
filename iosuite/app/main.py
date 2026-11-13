"""ioSuite: the application (start-up, who is asking, the routes and the web app).

Who may call a route is declared on the route (app/access.py); iosuite-shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from iosuite_shared import mcp as shared_mcp, users
from iosuite_shared.updates import setup_log

from app import __version__, api, bookmarkdav, bookmarkext, bookmarks, config, db, keys, mcp, ncbookmarks
from app.auth import auth, updater

setup_log(config.LOG_FILE)  # the server log that Settings › Server shows; the app runs without it
log = logging.getLogger("iosuite")

# what a visitor may still fetch when sign-in is required: the app shell and its files, and the API docs
OPEN_PATHS = ("/", "/bookmarks", "/manifest.webmanifest", "/bookmarks.webmanifest", "/api/docs", "/api/openapi.json")
# /mcp signs in on its own (Auth.mcp_gate); the sync protocols under /dav answer 401 with a Basic challenge themselves
# (a sync app shows that as "wrong password"), and the Nextcloud sign-in flow starts before anyone is signed in
OPEN_PREFIXES = ("/static/", "/mcp", "/dav/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(db.migrate)
    await run_in_threadpool(bookmarks.carry_over)  # once: the bookmarks of before the tree (goes away next version)
    await run_in_threadpool(users.init)
    await run_in_threadpool(keys.declare)  # the Home Assistant token and AccuWeather key live with the suite's keys and tokens
    updater.start_daily()   # the daily "is there a newer version" check, while the setting allows it
    log.info("ioSuite %s started, database %s:%s/%s", __version__, config.DB_HOST, config.DB_PORT, config.DB_NAME)
    async with shared_mcp.running(mcp.server):  # the MCP endpoint (/mcp) lives in this process
        yield


app = FastAPI(title="ioSuite", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="The start page of the ioThing suite: one place with every io app, and the accounts they share.")

def mcp_enabled() -> bool:
    """Settings › Server › MCP server: off until an admin turns it on (or MCP=1 in the environment)."""
    return shared_mcp.enabled(db.get_setting, config.MCP_FORCED)


# who is asking, whether sign-in is required at all, the cross-site check on writes, and the MCP endpoint's gate (the
# switch; an app password or session; every tool acts as that account): iosuite-shared's middleware
app.middleware("http")(auth.middleware(open_paths=OPEN_PATHS, open_prefixes=OPEN_PREFIXES,
                                       before=auth.mcp_gate(mcp_enabled, on_user=mcp.current_user.set)))


def _limit_for(path: str, ctype: str) -> int:
    return config.MAX_IMPORT_BYTES if "/import" in path or path.startswith("/dav/") else config.MAX_JSON_BYTES


# 400 for bad input, the headers, no-store on the API, the body cap: the same in every app of the suite
auth.install(app, limit_for=_limit_for)


def _server_info() -> dict:
    """What Settings › Server shows beside the updater's own fields: the MCP box."""
    return {"mcpEnabled": mcp_enabled(), "mcpLocked": config.MCP_FORCED,
            "mcpAbout": "Lets an AI assistant check and update every app of the suite at once (suite admins)."}


def _server_apply(body: dict) -> None:
    """The MCP switch, sent to POST /api/server as {mcpEnabled: bool}."""
    if "mcpEnabled" in body:
        shared_mcp.set_enabled(db.set_setting, bool(body["mcpEnabled"]), config.MCP_FORCED)


app.include_router(auth.router())        # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords, suite
app.include_router(auth.users_router())  # /api/users: accounts and their role here (admins)
app.include_router(auth.admin_router())  # /api/suite-admin: every account, role, app password, session and app of the suite (suite admins; Settings › Security and Global settings)
app.include_router(auth.status_router(updater))  # /api/status: public, the same shape in every app
app.include_router(auth.server_router(updater, log_file=config.LOG_FILE, info=_server_info, apply=_server_apply))  # /api/server, /api/log (admins)
app.include_router(api.router)
app.include_router(ncbookmarks.router)  # /dav/nextcloud: the Nextcloud Bookmarks API, for Floccus and other sync apps
app.include_router(bookmarkdav.router)  # /dav/bookmarks: the bookmarks as a file over WebDAV
app.include_router(bookmarkext.router)  # /dav/ext: the ioSuite Bookmarks browser extension (static/extension/)
shared_mcp.mount(app, mcp.server)  # MCP over streamable HTTP at /mcp, ahead of everything else


def _page(swap: dict[str, str] | None = None) -> HTMLResponse:
    """The page, with the version stamped on the script and stylesheet: after an update the browser (and Cloudflare,
    which caches .js and .css at the edge) fetches the new ones instead of serving what it kept."""
    html = (config.STATIC_DIR / "index.html").read_text(encoding="utf-8")
    for f in ("static/app.js", "static/app.css", "static/js/theme.js"):
        html = html.replace(f'"{f}"', f'"{f}?v={__version__}"')
    for a, b in (swap or {}).items():
        html = html.replace(a, b)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/", include_in_schema=False)
def index():
    return _page()


@app.get("/bookmarks", include_in_schema=False)
def bookmarks_app():
    """The Bookmarks page as an app of its own: the same page, opening on the bookmarks, with its own name, icon and
    manifest, so "Add to Home Screen" (iPhone, iPad) or "Install" (desktop, Android) makes a Bookmarks icon that opens
    straight on them, without the browser around it."""
    return _page({
        "<title>ioSuite</title>": "<title>Bookmarks</title>",
        '<meta name="apple-mobile-web-app-capable" content="yes">':
            '<meta name="apple-mobile-web-app-capable" content="yes">\n<meta name="apple-mobile-web-app-title" content="Bookmarks">',
        'href="static/icons/apple-touch-icon.png"': 'href="static/icons/bookmarks-180.png"',
        'href="static/icons/mark.svg" type="image/svg+xml"': 'href="static/icons/bookmarks.svg" type="image/svg+xml"',
        'href="manifest.webmanifest"': 'href="bookmarks.webmanifest"',
    })


def _manifest(name: str):
    return FileResponse(config.STATIC_DIR / name, media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return _manifest("manifest.webmanifest")


@app.get("/bookmarks.webmanifest", include_in_schema=False)
def bookmarks_manifest():
    return _manifest("bookmarks.webmanifest")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
