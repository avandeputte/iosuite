"""Settings, maintenance and status: the switches admins set, sign-in at a proxy, the database, the server log,
the change log, export and import, and updating ionotes."""
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app import __version__, access, backup, config, db, images, logs, notes, ocr, proxyauth, updates, users
from app.http import json_body, user_name

router = APIRouter()
SWITCHES = ("require_login", "read_only", "mcp_enabled", "update_check")
TEXTS = ("app_name",)


@router.get("/api/status", dependencies=[access.public])
def api_status(request: Request):
    """Open even when sign-in is required (the container's health check and the apps' first look use it)."""
    out = {"ok": True, "app": "ionotes", "version": __version__, "requireLogin": users.require_login(), "usersExist": users.any_users(),
           "appName": db.get_setting("app_name", "") or "ionotes", "readOnly": db.read_only()}
    if users.is_signed_in(request.state.user):
        out["rev"] = db.current_rev()
        if users.is_admin(request.state.user):
            out["update"] = updates.available()
    return out


@router.get("/api/settings", dependencies=[access.public])
def api_settings(request: Request):
    out = {"app_name": db.get_setting("app_name", "") or "ionotes", "read_only": db.read_only(), "require_login": users.require_login(),
           "colors": list(notes.COLORS)}
    if users.is_admin(request.state.user):
        out.update({k: db.get_setting(k, "1" if k == "update_check" else "0") == "1" for k in SWITCHES})
        out["read_only_env"] = config.READ_ONLY
        out["mcp_forced"] = config.MCP_FORCED
        out["database"] = db.public_settings()
        out["ocr"] = ocr.status()
        out["images"] = images.stats()
        out["appUrl"] = config.APP_URL
    return out


@router.post("/api/settings", dependencies=[access.admin])
async def api_settings_set(request: Request):
    body = await json_body(request)
    for k, v in body.items():
        if k in SWITCHES:
            if k == "require_login" and v and not users.any_users():
                raise HTTPException(400, "Create an account first, or nobody could sign in")
            db.set_setting(k, "1" if v else "0")
        elif k in TEXTS:
            db.set_setting(k, str(v or "").strip()[:40])
    users.invalidate()
    return {"ok": True}


@router.get("/api/settings/proxy", dependencies=[access.admin])
def api_proxy_get():
    """Sign-in at a reverse proxy (Cloudflare Access...): its settings, which of them ionotes.env fixes, and the
    Cloudflare Access team and application last seen in requests. Admins only."""
    return proxyauth.status()


@router.post("/api/settings/proxy", dependencies=[access.admin])
async def api_proxy_set(request: Request):
    """Body: any of proxyauth.KEYS (an empty string clears one). Settings in ionotes.env cannot be changed here."""
    body = await json_body(request)
    changes = {k: str(v or "").strip() for k, v in body.items() if k in proxyauth.KEYS}
    fixed = [k for k in changes if config.proxy_env(k) is not None]
    if fixed:
        raise HTTPException(400, f"Set in ionotes.env, change it there: {', '.join(fixed)}")
    m = changes.get("AUTH_PROXY")
    if m is not None and m.lower() not in ("", "off", *proxyauth.PRESETS):
        raise HTTPException(400, "Unknown proxy")
    if changes.get("AUTH_PROXY_CREATE", "").lower() not in ("", "viewer", "editor", "deny"):
        raise HTTPException(400, "Someone with no account: the sign-in screen, deny, or a viewer or editor account")
    if (m or proxyauth.mode()).lower() == "cloudflare" and ("CF_ACCESS_TEAM" in changes or "CF_ACCESS_AUD" in changes or m):
        team = changes.get("CF_ACCESS_TEAM", proxyauth.opt("CF_ACCESS_TEAM") or "")
        aud = changes.get("CF_ACCESS_AUD", proxyauth.opt("CF_ACCESS_AUD") or "")
        if bool(team) != bool(aud):
            raise HTTPException(400, "Cloudflare needs both the team domain and the AUD tag (or neither)")
    proxyauth.save(changes)
    return proxyauth.status()


@router.post("/api/db/test", dependencies=[access.admin])
async def api_db_test(request: Request):
    """Try a MySQL/MariaDB connection: {host, port, database, user, password}."""
    body = await json_body(request)
    return await run_in_threadpool(db.test, body)


@router.post("/api/db/save", dependencies=[access.admin])
async def api_db_save(request: Request):
    """Write data/db.json; ionotes uses it from its next start (restart the service)."""
    body = await json_body(request)
    c = {**db.settings(), **{k: body[k] for k in db.KEYS if k in body}}
    if not body.get("password"):
        c["password"] = db.settings()["password"]
    if c.get("type") == "mysql":
        t = await run_in_threadpool(db.test, c)
        if not t["ok"]:
            raise HTTPException(400, t["error"])
    db.save_settings(c)
    return {"ok": True, "restartNeeded": True}


# ---- maintenance
@router.get("/api/log", dependencies=[access.admin])
def api_log(lines: int = 300, contains: str = "", level: str = "any", requests: int = 0):
    return logs.tail(lines, contains, level, bool(requests))


@router.get("/api/changes", dependencies=[access.editor])
def api_changes(limit: int = 200, before: int = None):
    """The change log: who created, edited, deleted or recoloured what, newest first."""
    return {"changes": notes.change_log(limit, before)}


@router.get("/api/export.zip", dependencies=[access.signed_in])
async def api_export(trash: int = 0, pictures: int = 1):
    data = await run_in_threadpool(backup.export_zip, bool(trash), bool(pictures))
    name = time.strftime("ionotes-export-%Y%m%d-%H%M.zip")
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/api/import", dependencies=[access.admin_write])
async def api_import(request: Request, file: UploadFile = File(...)):
    data = await file.read()
    try:
        return await run_in_threadpool(backup.import_zip, data, user_name(request))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"Could not import: {e}")


@router.get("/api/update", dependencies=[access.admin])
def api_update_status():
    return updates.status()


@router.post("/api/update/check", dependencies=[access.admin])
def api_update_check():
    return updates.check()


@router.post("/api/update/run", dependencies=[access.admin])
async def api_update_run(request: Request):
    body = await json_body(request)
    try:
        updates.run(str(body.get("ref") or ""))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@router.get("/api/mcp/token", dependencies=[access.admin])
def api_mcp_token():
    return {"token": updates.admin_token(), "fromEnv": bool(config.MCP_ADMIN_TOKEN), "url": config.APP_URL + "/mcp"}


@router.post("/api/mcp/token", dependencies=[access.admin])
def api_mcp_token_new():
    if config.MCP_ADMIN_TOKEN:
        raise HTTPException(400, "MCP_ADMIN_TOKEN is set in ionotes.env; change it there")
    return {"token": updates.regenerate_token()}
