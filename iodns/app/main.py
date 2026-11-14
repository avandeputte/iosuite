"""ioDNS: the application (start-up, who is asking, the routes and the web app).

Who may call a route is declared on the route (app/access.py); iosuite-shared's middleware works out who is asking
(the shared session cookie, the identity a reverse proxy such as Cloudflare Access vouches for, HTTP Basic or a bearer
app password), whether sign-in is required at all, and refuses cross-site writes. The same scheme as every app of the
suite.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from iosuite_shared import pages, users as shared_users
from iosuite_shared.updates import setup_log

from app import __version__, api, config, db, ddns, model, sync
from app.auth import auth, updater
from app.providers import ProviderError

setup_log(config.LOG_FILE)  # the server log that Settings › Server shows; the app runs without it
log = logging.getLogger("iodns")

# what a visitor may still fetch when sign-in is required: the app shell and its files, the API docs
OPEN_PATHS = ("/", "/manifest.webmanifest", "/api/docs", "/api/openapi.json")
OPEN_PREFIXES = ("/static/",)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await run_in_threadpool(db.migrate)
    await run_in_threadpool(shared_users.init)
    updater.start_daily()             # the daily "is there a newer version" check, while the setting allows it
    if config.env_flag("BACKGROUND", True):
        sync.start_checks(config.CHECK_MINUTES)   # every server compared with the master list now and then
        ddns.start()                  # the public address, every few minutes
    log.info("ioDNS %s started, database %s:%s/%s", __version__, config.DB_HOST, config.DB_PORT, config.DB_NAME)
    yield


app = FastAPI(title="ioDNS", version=__version__, lifespan=lifespan, docs_url="/api/docs", redoc_url=None,
              openapi_url="/api/openapi.json",
              description="One master list of local DNS records, per view (Internal, External, Tailscale…), kept in sync on "
                          "AdGuard Home, Pi-hole, UniFi and Cloudflare, with dynamic DNS and Tailscale device addresses.")

app.middleware("http")(auth.middleware(open_paths=OPEN_PATHS, open_prefixes=OPEN_PREFIXES))

# 400 for bad input, the headers, no-store on the API, the body cap: the same in every app of the suite
auth.install(app, limit_for=lambda path, ctype: config.MAX_JSON_BYTES, not_found=(model.NotFound,))


@app.exception_handler(ProviderError)
async def provider_error(request: Request, e: ProviderError):
    """A DNS server that answered with an error or could not be reached: 502, with what it said."""
    return JSONResponse({"detail": str(e)}, status_code=502)


app.include_router(auth.router())        # /api/auth/*: sign-in, accounts, me, settings, password, sessions, app passwords, suite
app.include_router(auth.admin_router())  # /api/suite-admin (+ ui.js): the whole suite (suite admins)
app.include_router(auth.status_router(updater))  # /api/status: public, the same shape in every app
app.include_router(auth.server_router(updater, log_file=config.LOG_FILE))  # /api/server, /api/log (admins)
app.include_router(api.router)


pages.mount(app, config.STATIC_DIR, __version__)  # /, the manifest and /static
