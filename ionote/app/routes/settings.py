"""Settings: the switches admins set, the change log, export and import. Sign-in at a proxy is set for the whole suite (Settings › Security, suite admins: iosuite_shared's routers). The status, the version, updates, restart and the server log are iosuite_shared's routers (/api/status,
/api/server, /api/log), mounted in app/main.py."""
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from iosuite_shared import admin as suite_admin, users
from iosuite_shared.access import json_body
from starlette.concurrency import run_in_threadpool

from app import access, backup, config, db, notes
from app.http import attachment, user_name

router = APIRouter()
TEXTS = ("app_name",)  # the MCP switch is Settings › Server (POST /api/server {mcpEnabled})


@router.get("/api/settings", dependencies=[access.public])
def api_settings(request: Request):
    return {"app_name": db.get_setting("app_name", "") or "ionote", "require_login": users.require_login(config.APP),
            "colors": list(notes.COLORS)}


@router.post("/api/settings", dependencies=[access.admin])
async def api_settings_set(request: Request):
    body = await json_body(request)
    for k, v in body.items():
        if k == "require_login":  # Settings › Global settings › Apps, in the Shared ioSuite database, per app
            if v and not users.any_users():
                raise HTTPException(400, "Create an account first, or nobody could sign in")
            suite_admin.set_app(config.APP, require_login=bool(v))
        elif k in TEXTS:
            db.set_setting(k, str(v or "").strip()[:40])
    users.invalidate()
    return {"ok": True}


# ---- the change log, export and import
@router.get("/api/changes", dependencies=[access.member])
def api_changes(limit: int = 200, before: int = None):
    """The change log: who created, edited, deleted or recoloured what, newest first."""
    return {"changes": notes.change_log(limit, before)}


@router.get("/api/export.zip", dependencies=[access.signed_in])
async def api_export(trash: int = 0, pictures: int = 1):
    f = await run_in_threadpool(backup.export_zip, bool(trash), bool(pictures))
    return StreamingResponse(backup.pieces(f), media_type="application/zip", headers=attachment(time.strftime("ionote-export-%Y%m%d-%H%M.zip")))


@router.post("/api/import", dependencies=[access.member_write])
async def api_import(request: Request, file: UploadFile = File(...)):
    try:  # the upload is a temporary file (on disk once large): read from there, not into memory
        return await run_in_threadpool(backup.import_zip, file.file, user_name(request))
    except (ValueError, KeyError) as e:
        raise HTTPException(400, f"Could not import: {e}")
