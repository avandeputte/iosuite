"""ioTask: the application (start-up, who is asking, the routes and the web app).

Who may call a route is declared on the route (app/access.py); iosuite-shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from iosuite_shared import chores, mcp as shared_mcp, pages
from iosuite_shared.updates import setup_log

from app import __version__, api, caldav, config, db, ical, mcp, model, notify, users
from app.auth import auth, updater

setup_log(config.LOG_FILE)  # the server log that Settings › Server shows; the app runs without it
log = logging.getLogger("iotask")


# what a visitor may still fetch when sign-in is required: the app shell and its files, the API docs, CalDAV (its own
# sign-in), the profile links (their own secret) and the MCP endpoint (its gate below)
OPEN_PATHS = ("/", "/manifest.webmanifest", "/api/docs", "/api/openapi.json")
OPEN_PREFIXES = ("/static/", "/dav", "/.well-known/", "/mcp", "/profile/")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(db.migrate)
    await run_in_threadpool(users.init)
    updater.start_daily()   # the daily "is there a newer version" check, while the setting allows it
    purge = chores.start(model.purge_deleted, name="purge of old deletion markers")  # once a day: KEEP_DELETED_DAYS
    notes = chores.start(notify.run, every_s=60, first_s=20, name="notifications")  # tasks falling due, the morning summary
    log.info("ioTask %s started, database %s:%s/%s", __version__, config.DB_HOST, config.DB_PORT, config.DB_NAME)
    async with shared_mcp.running(mcp.server):  # the MCP endpoint (/mcp) lives in this process
        yield
    purge.cancel()
    notes.cancel()


app = FastAPI(title="ioTask", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="Task lists for the family. Also served over CalDAV at /dav/ (to-dos, for Apple Reminders and "
                          "other reminders apps) and to AI assistants over MCP (/mcp). JSON by default; ask for "
                          "text/calendar with Accept or ?format=ics.")


# Settings › Server › MCP server: off until an admin turns it on (or MCP=1 in the environment); the MCP box of the panel
mcp_switch = shared_mcp.Switch(db.get_setting, db.set_setting, config.MCP_FORCED,
                               "Lets an AI assistant read the lists, add tasks and tick them off, as you.")
mcp_enabled = mcp_switch.enabled


# who is asking, whether sign-in is required at all, the cross-site check on writes, and the MCP endpoint's gate (the
# switch; an app password or session; every tool acts as that account): iosuite-shared's middleware
app.middleware("http")(auth.middleware(open_paths=OPEN_PATHS, open_prefixes=OPEN_PREFIXES,
                                       before=auth.mcp_gate(mcp_enabled, on_user=mcp.current_user.set)))


def _limit_for(path: str, ctype: str) -> int:
    if "/import" in path:  # an .ics file to import
        return config.MAX_IMPORT_BYTES
    if path.startswith("/dav"):  # CalDAV checks its own PUTs (max-resource-size)
        return config.MAX_TASK_BYTES
    return config.MAX_JSON_BYTES


# 400 for bad input, the headers, no-store on the API, the body cap: the same in every app of the suite
auth.install(app, limit_for=_limit_for, not_found=(model.NotFound,))


def _status_extra(request) -> dict:
    """ioTask's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"timezone": ical.default_tz(), "mcp": mcp_enabled() if u else None}


app.include_router(auth.router())        # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords, suite
app.include_router(auth.admin_router())  # /api/suite-admin (+ ui.js, the panel of Settings › Security and Global settings): the whole suite (suite admins)
app.include_router(auth.related_router())  # /api/related (+ ui.js, the "Linked" panel): items linked across the apps
app.include_router(auth.status_router(updater, extra=_status_extra))  # /api/status: public, the same shape in every app
app.include_router(auth.server_router(updater, log_file=config.LOG_FILE, info=mcp_switch.info, apply=mcp_switch.apply))  # /api/server, /api/log (admins)
app.include_router(auth.profile_router(api.base_url))  # /profile/<token>/<file> and the profile for all the apps that sync
app.include_router(api.router)
app.include_router(caldav.router)
shared_mcp.mount(app, mcp.server)  # MCP over streamable HTTP at /mcp, ahead of everything else


pages.mount(app, config.STATIC_DIR, __version__)  # /, the manifest and /static
