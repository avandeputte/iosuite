"""Settings: the switches admins set, the change log, export and import. Sign-in at a proxy is set for the whole suite (Settings › Security, suite admins: iosuite_shared's routers). The status, the version, updates, restart and the server log are iosuite_shared's routers (/api/status,
/api/server, /api/log), mounted in app/main.py."""
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app import access, backup, db, notes, users
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
