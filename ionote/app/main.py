"""ioNote: the web app, the API the Mac and iPhone apps use, and the MCP endpoint, on one port (8610).

Who may call a route is declared on the route (app/access.py); iosuite-shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite. What is ioNote's own: whose notes a request works on (notes are private to each account).
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from iosuite_shared import chores, demo as suite_demo, mcp as shared_mcp, pages, users
from iosuite_shared.updates import setup_log

from app import __version__, config, db, mcp, suitedb, suiteitems
from app import notes as notes_mod
from app.auth import auth, updater
from app.routes import auth as auth_routes, notes as notes_routes, settings

setup_log(config.LOG_FILE)  # the server log that Settings › Server shows; the app runs without it
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
    suite_demo.at_start(config.APP)  # the demo data while the suite's demo switch is on (iosuite_shared.demo fetches the iosuite_demo package)
    updater.start_daily()
    purge = chores.start(notes_mod.housekeeping, every_s=6 * 3600, name="purge of the trash and of what deletions left behind")
    c = db.settings()
    log.info("ioNote %s started on %s (%s)", __version__,
             f"MariaDB/MySQL {c['host']}:{c['port']}/{c['database']}",
             "accounts exist" if users.any_users() else "no accounts yet: open to everyone until one is made")
    sd = suitedb.public()
    log.info("Shared ioSuite database (accounts, suite settings): %s@%s:%s/%s", sd["user"], sd["host"], sd["port"], sd["database"])
    async with shared_mcp.running(mcp.server):  # the MCP endpoint (/mcp) lives in this process
        yield
    purge.cancel()


app = FastAPI(title="ioNote", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="Notes for the family, private to each account. The API the Mac and iPhone apps use, and an MCP "
                          "endpoint (/mcp) for AI assistants.")


# Settings › Server › MCP server: off until an admin turns it on (or MCP=1 in the environment); the MCP box of the panel
mcp_switch = shared_mcp.Switch(db.get_setting, db.set_setting, config.MCP_FORCED,
                               "Lets an AI assistant search, read and write your notes, as you.")
mcp_enabled = mcp_switch.enabled


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


_mcp_gate = auth.mcp_gate(mcp_enabled, on_user=_mcp_user)


def _before(request: Request):
    """Once the user is known: whose notes the request works on, and the MCP endpoint's gate (the switch; an app
    password or session, as in every app of the suite)."""
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
    if "/attachments" in path:
        return config.MAX_IMAGE_BYTES
    if ctype.startswith("image/") or ctype in ("multipart/form-data", "application/octet-stream", "application/zip"):
        return config.MAX_IMAGE_BYTES
    return config.MAX_JSON_BYTES


# 400 for bad input, the headers, no-store on the API, the body cap (counted as the body arrives, so nothing large is
# ever held in memory), and the same 404 for another account's note as for none at all: iosuite-shared
auth.install(app, limit_for=_limit_for, not_found=(notes_mod.NotFound,))


def _status_extra(request: Request) -> dict:
    """ioNote's own fields of GET /api/status, beside the suite's: the name an admin gave the app and,
    signed in, the account's change counter (the page polls it to learn of changes made elsewhere)."""
    out = {"appName": db.get_setting("app_name", "") or "ionote"}
    if users.is_signed_in(request.state.user):
        out["rev"] = notes_mod.owner_rev()
    return out


app.include_router(auth_routes.router)   # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords, suite
app.include_router(auth.admin_router())  # /api/suite-admin (+ ui.js, the Settings › Security panel): the whole suite (suite admins)
app.include_router(auth.related_router())  # /api/related (+ ui.js, the "Linked" panel): items linked across the apps
app.include_router(auth.suite_router(suiteitems.PROVIDER))  # /api/suite: search, items, tile, as every app answers them (app.json)
app.include_router(auth.status_router(updater, extra=_status_extra))  # /api/status: public, the same shape in every app
app.include_router(auth.server_router(updater, log_file=config.LOG_FILE, info=mcp_switch.info, apply=mcp_switch.apply))  # /api/server, /api/log (admins)
app.include_router(notes_routes.router)
app.include_router(settings.router)
shared_mcp.mount(app, mcp.server)  # MCP over streamable HTTP at /mcp, ahead of everything else


pages.mount(app, config.STATIC_DIR, __version__, service_worker=True)  # /, the manifest, /sw.js and /static
