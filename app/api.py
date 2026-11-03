"""The REST API (JSON) the start page uses. OpenAPI docs at /api/docs.

Clients authenticate with the web session cookie (the suite's, shared by every io app on the domain), HTTP Basic or
`Authorization: Bearer <app password>`, as in the other io apps."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app import APP_VERSION, apps, config, db, updates, users

router = APIRouter()


def me(request: Request) -> dict:
    u = request.state.user
    if not u:
        raise HTTPException(401, "Sign in first")
    return u


def admin(request: Request) -> dict:
    u = me(request)
    if not users.is_admin(u):
        raise HTTPException(403, "Admins only")
    return u


def _base(request: Request) -> str:
    """The page's own address, for links: PUBLIC_URL, else as reached (through the proxy's headers)."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    return f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', request.url.netloc)}"


@router.get("/api/status")
def status(request: Request):
    u = request.state.user
    adm = users.is_admin(u)
    return {"app": "ioSuite", "version": APP_VERSION, "commit": updates.local_commit()[:7] if u else None,
            "usersExist": users.any_users(), "user": users.public(u), "viaProxy": getattr(request.state, "via_proxy", False),
            "updateAvailable": updates.available() if adm and updates.auto_check_enabled() else None}


# ------------------------------------------------------------------ the apps

@router.get("/api/apps")
def list_apps(request: Request):
    """The tiles: every app with its name, icon, colour and address. Hidden ones are left out (Settings lists them)."""
    me(request)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return {"items": [t for t in apps.tiles(host) if not t["hidden"]]}


@router.get("/api/apps/settings")
def apps_settings(request: Request):
    admin(request)
    return {"items": apps.settings()}


@router.post("/api/apps/settings")
async def apps_save(request: Request):
    """Admins. Body: {iopix: {url?: str, hidden?: bool}, iohealth: {...}, ...}."""
    admin(request)
    b = await request.json()
    if not isinstance(b, dict):
        raise HTTPException(400, "An object of apps, please")
    try:
        apps.save(b)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"items": apps.settings()}


# ------------------------------------------------------------------ the server: version, updates

@router.get("/api/server")
def server_info(request: Request):
    """Admins: the installed version, the last update check, whether update.sh can run here, and the switches."""
    admin(request)
    return {**updates.status(), "url": _base(request), "database": f"{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"}


@router.post("/api/server")
async def server_action(request: Request):
    """Admins. Body: {action: check | update, ref?} or {autoCheck: bool}."""
    admin(request)
    b = await request.json()
    if "autoCheck" in b:
        if config.UPDATE_CHECK_LOCKED and b["autoCheck"]:
            raise HTTPException(400, "UPDATE_CHECK=0 in the environment keeps the daily check off")
        db.set_setting("update_check", "1" if b["autoCheck"] else "0")
        if not b["autoCheck"]:
            updates.forget_check()
    action = b.get("action")
    if action == "check":
        return await run_in_threadpool(updates.check)
    if action == "update":
        try:
            updates.run(str(b.get("ref") or ""))
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return {"started": True}
    return server_info(request)
