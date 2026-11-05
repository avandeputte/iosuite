"""Settings, maintenance and status: the switches admins set, sign-in at a proxy, the database, the change log, export
and import. The version, updates, restart, the MCP admin token and the server log are iosuite_shared's server_router
(/api/server, /api/log), mounted in app/main.py."""
import logging
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app import __version__, access, owners, backup, config, db, images, notes, ocr, suitedb, users
from iosuite_shared import proxyauth
from app.auth import auth as auth_shared, updater
from app.http import json_body, user_name

router = APIRouter()
SWITCHES = ("require_login", "read_only", "mcp_enabled")
TEXTS = ("app_name",)


@router.get("/api/status", dependencies=[access.public])
def api_status(request: Request):
    """Open even when sign-in is required (the container's health check and the apps' first look use it)."""
    out = {"ok": True, "app": "ionotes", "version": __version__, "requireLogin": users.require_login(), "usersExist": users.any_users(),
           "appName": db.get_setting("app_name", "") or "ionotes", "readOnly": db.read_only()}
    if users.is_signed_in(request.state.user):
        out["rev"] = notes.owner_rev()
        out["commit"] = updater.local_commit()[:7]
        if users.is_admin(request.state.user):
            u = updater.available() if updater.auto_check_enabled() else None
            if u:
                u.update(canRun=updater.can_run(), docker=updater.in_docker())
            out["update"] = u
    return out


@router.get("/api/settings", dependencies=[access.public])
def api_settings(request: Request):
    out = {"app_name": db.get_setting("app_name", "") or "ionotes", "read_only": db.read_only(), "require_login": users.require_login(),
           "colors": list(notes.COLORS)}
    if users.is_admin(request.state.user):
        out.update({k: db.get_setting(k, "0") == "1" for k in SWITCHES})
        out["read_only_env"] = config.READ_ONLY
        out["mcp_forced"] = config.MCP_FORCED
        out["database"] = db.public_settings()
        out["suite_database"] = suitedb.public()
        out["ocr"] = ocr.status()
        out["images"] = images.stats()
        out["appUrl"] = config.BASE_URL
        out["mcp_user"] = owners.mcp_owner()
        out["accounts"] = [{"id": u["id"], "name": u["name"], "role": u.get("role")} for u in users.list_users()]
    return out


@router.post("/api/settings", dependencies=[access.admin])
async def api_settings_set(request: Request):
    body = await json_body(request)
    for k, v in body.items():
        if k in SWITCHES:
            if k == "require_login":
                if v and not users.any_users():
                    raise HTTPException(400, "Create an account first, or nobody could sign in")
                users.set_require_login(bool(v))  # in the Shared ioSuite database, per app
                continue
            db.set_setting(k, "1" if v else "0")
        elif k in TEXTS:
            db.set_setting(k, str(v or "").strip()[:40])
        elif k == "mcp_user":  # whose notes the MCP tools work on
            if v and not users.get(int(v)):
                raise HTTPException(400, "No such account")
            db.set_setting("mcp_user", str(int(v or 0)))
    users.invalidate()
    return {"ok": True}


@router.get("/api/settings/proxy", dependencies=[access.admin])
def api_proxy_get():
    """Sign-in at a reverse proxy (Cloudflare Access...): its settings, which of them config.env fixes, and the
    Cloudflare Access team and application last seen in requests. Admins only."""
    return auth_shared.proxy.status()


@router.post("/api/settings/proxy", dependencies=[access.admin])
async def api_proxy_set(request: Request):
    """Body: any of proxyauth.KEYS (an empty string clears one). Settings in config.env cannot be changed here."""
    body = await json_body(request)
    changes = {k: str(v or "").strip() for k, v in body.items() if k in proxyauth.KEYS}
    fixed = [k for k in changes if config.proxy_env(k) is not None]
    if fixed:
        raise HTTPException(400, f"Set in config.env, change it there: {', '.join(fixed)}")
    m = changes.get("AUTH_PROXY")
    if m is not None and m.lower() not in ("", "off", *proxyauth.PRESETS):
        raise HTTPException(400, "Unknown proxy")
    if changes.get("AUTH_PROXY_CREATE", "").lower() not in ("", "viewer", "editor", "deny"):
        raise HTTPException(400, "Someone with no account: the sign-in screen, deny, or a viewer or editor account")
    if (m or auth_shared.proxy.mode()).lower() == "cloudflare" and ("CF_ACCESS_TEAM" in changes or "CF_ACCESS_AUD" in changes or m):
        team = changes.get("CF_ACCESS_TEAM", auth_shared.proxy.opt("CF_ACCESS_TEAM") or "")
        aud = changes.get("CF_ACCESS_AUD", auth_shared.proxy.opt("CF_ACCESS_AUD") or "")
        if bool(team) != bool(aud):
            raise HTTPException(400, "Cloudflare needs both the team domain and the AUD tag (or neither)")
    auth_shared.proxy.save(changes)
    return auth_shared.proxy.status()


@router.post("/api/db/test", dependencies=[access.admin])
async def api_db_test(request: Request):
    """Try a MySQL/MariaDB connection: {host, port, database, user, password}."""
    body = await json_body(request)
    return await run_in_threadpool(db.test, body)


@router.post("/api/db/save", dependencies=[access.admin])
async def api_db_save(request: Request):
    """Write data/db.json; ionotes uses it from its next start (restart the service)."""
    body = await json_body(request)
    fixed = db.public_settings()["fromEnv"]
    if fixed:
        raise HTTPException(400, f"Set in config.env, change it there: {', '.join(config.DB_ENV[k] for k in fixed)}")
    c = {**db.settings(), **{k: body[k] for k in db.KEYS if k in body}}
    if not body.get("password"):
        if c.get("type") == "mysql" and not db.same_server(c):
            raise HTTPException(400, "Enter the password: the saved one is only used for the server and user it belongs to")
        c["password"] = db.settings()["password"]
    if c.get("type") == "mysql":
        t = await run_in_threadpool(db.test, c)
        if not t["ok"]:
            raise HTTPException(400, t["error"])
    db.save_settings(c)
    return {"ok": True, "restartNeeded": True}


# ---- maintenance
@router.get("/api/changes", dependencies=[access.editor])
def api_changes(limit: int = 200, before: int = None):
    """The change log: who created, edited, deleted or recoloured what, newest first."""
    return {"changes": notes.change_log(limit, before)}


@router.get("/api/export.zip", dependencies=[access.signed_in])
async def api_export(trash: int = 0, pictures: int = 1):
    data = await run_in_threadpool(backup.export_zip, bool(trash), bool(pictures))
    name = time.strftime("ionotes-export-%Y%m%d-%H%M.zip")
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/api/import", dependencies=[access.editor_write])
async def api_import(request: Request, file: UploadFile = File(...)):
    try:  # the upload is a temporary file (on disk once large): read from there, not into memory
        return await run_in_threadpool(backup.import_zip, file.file, user_name(request))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"Could not import: {e}")


@router.get("/api/owners", dependencies=[access.admin])
def note_owners():
    """Maintenance › Who owns the notes: each owner id with its note count and account name (if the id is an account
    of ionotes), and the accounts notes can be given to."""
    accounts = {u["id"]: u["name"] for u in users.list_users()}
    counts = notes.owner_counts()
    return {"owners": [{"id": o, "name": accounts.get(o), "notes": n} for o, n in sorted(counts.items())],
            "accounts": [{"id": i, "name": n} for i, n in accounts.items()]}


@router.post("/api/owners/move", dependencies=[access.admin])
async def move_notes(request: Request):
    """Give all of one owner's notes (with their folders and tag colours) to an account."""
    body = await json_body(request)
    try:
        src, dst = int(body.get("from")), int(body.get("to"))
    except (TypeError, ValueError):
        raise HTTPException(400, "from and to are account ids")
    if not users.get(dst):
        raise HTTPException(400, "No such account")
    moved = await run_in_threadpool(notes.reassign, src, dst)
    logging.getLogger("app").info("%s gave the notes of owner %s to account %s (%d notes)", user_name(request), src, dst, moved)
    return {"moved": moved}
