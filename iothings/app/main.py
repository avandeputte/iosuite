"""ioThings: the application (start-up, who is asking, the routes and the web app).

Who may call a route is declared on the route (app/access.py); iosuite-shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from iosuite_shared import chores, mcp as shared_mcp, pages
from iosuite_shared import demo as suite_demo
from iosuite_shared.updates import setup_log

from app import __version__, api, config, db, mcp, model, notify, suiteitems, users
from app.auth import auth, updater

setup_log(config.LOG_FILE)  # the server log that Settings › Server shows; the app runs without it
log = logging.getLogger("iothings")


# what a visitor may still fetch when sign-in is required: the app shell and its files, the API docs and the MCP
# endpoint (its gate below)
OPEN_PATHS = ("/", "/manifest.webmanifest", "/api/docs", "/api/openapi.json")
OPEN_PREFIXES = ("/static/", "/mcp")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(db.migrate)
    await run_in_threadpool(users.init)
    await run_in_threadpool(suite_demo.at_start, config.APP)  # the demo data while the suite's demo switch is on (iosuite_shared.demo fetches the iosuite_demo package)
    updater.start_daily()   # the daily "is there a newer version" check, while the setting allows it
    notes = chores.start(notify.run, every_s=60, first_s=20, name="notifications")  # the morning's upkeep and warranties
    log.info("ioThings %s started, database %s:%s/%s", __version__, config.DB_HOST, config.DB_PORT, config.DB_NAME)
    async with shared_mcp.running(mcp.server):  # the MCP endpoint (/mcp) lives in this process
        yield
    notes.cancel()


app = FastAPI(title="ioThings", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="Everything you own: where each thing is, what it cost, its warranty, manuals and "
                          "receipts, and its upkeep (as repeating tasks in ioTask). Imports a Homebox export. Also "
                          "served to AI assistants over MCP (/mcp).")


# Settings › Server › MCP server: off until an admin turns it on (or MCP=1 in the environment); the MCP box of the panel
mcp_switch = shared_mcp.Switch(db.get_setting, db.set_setting, config.MCP_FORCED,
                               "Lets an AI assistant look things up, add them and log their upkeep, as you.")
mcp_enabled = mcp_switch.enabled


# who is asking, whether sign-in is required at all, the cross-site check on writes, and the MCP endpoint's gate (the
# switch; an app password or session; every tool acts as that account): iosuite-shared's middleware
app.middleware("http")(auth.middleware(open_paths=OPEN_PATHS, open_prefixes=OPEN_PREFIXES,
                                       before=auth.mcp_gate(mcp_enabled, on_user=mcp.current_user.set)))


def _limit_for(path: str, ctype: str) -> int:
    if path == "/api/import/homebox":
        return config.MAX_IMPORT_BYTES
    return config.MAX_FILE_BYTES if path.endswith("/files") else config.MAX_JSON_BYTES


# 400 for bad input, the headers, no-store on the API, the body cap: the same in every app of the suite
auth.install(app, limit_for=_limit_for, not_found=(model.NotFound,))


@app.exception_handler(model.Forbidden)
async def _forbidden(request, e):
    return JSONResponse({"detail": str(e)}, status_code=403)


def _status_extra(request) -> dict:
    """ioThings's own fields of GET /api/status, beside the suite's."""
    u = request.state.user
    return {"mcp": mcp_enabled() if u else None}


app.include_router(auth.router())        # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords, suite
app.include_router(auth.admin_router())  # /api/suite-admin (+ ui.js, the panel of Settings › Security and Global settings): the whole suite (suite admins)
app.include_router(auth.related_router())  # /api/related (+ ui.js, the "Linked" panel): items linked across the apps
app.include_router(auth.suite_router(suiteitems.PROVIDER))  # /api/suite: search, items, tile, as every app answers them (app.json)
app.include_router(auth.status_router(updater, extra=_status_extra))  # /api/status: public, the same shape in every app
app.include_router(auth.server_router(updater, log_file=config.LOG_FILE, info=mcp_switch.info, apply=mcp_switch.apply))  # /api/server, /api/log (admins)
app.include_router(api.router)
shared_mcp.mount(app, mcp.server)  # MCP over streamable HTTP at /mcp, ahead of everything else


pages.mount(app, config.STATIC_DIR, __version__)  # /, the manifest and /static
