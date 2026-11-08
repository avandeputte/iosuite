"""Settings: the switches admins set, sign-in at a proxy, the change log, export and import. The status, the version, updates, restart and the server log are iosuite_shared's routers (/api/status,
/api/server, /api/log), mounted in app/main.py."""
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app import access, backup, config, db, notes, users
from iosuite_shared import proxyauth
from app.auth import auth as auth_shared
from app.http import json_body, user_name

router = APIRouter()
SWITCHES = ("require_login",)  # the MCP switch is Settings › Server (POST /api/server {mcpEnabled})
TEXTS = ("app_name",)


@router.get("/api/settings", dependencies=[access.public])
def api_settings(request: Request):
    out = {"app_name": db.get_setting("app_name", "") or "ionotes", "require_login": users.require_login(),
           "colors": list(notes.COLORS)}
    if users.is_admin(request.state.user):
        out.update({k: db.get_setting(k, "0") == "1" for k in SWITCHES})
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


# ---- the change log, export and import
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
