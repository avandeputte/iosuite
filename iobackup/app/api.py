"""The REST API the web app uses (and anyone with an app password: HTTP Basic or a bearer token). JSON in and out.
Who may call each route is on the route (app/access.py)."""
from __future__ import annotations

import datetime as _dt
import threading
import time

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, StreamingResponse

from app import access, config, engine, gdrive, model, schedule, tasks
from app.destinations import open_destination, safe_name

router = APIRouter(prefix="/api")


def who(request: Request) -> str | None:
    u = request.state.user
    return u["name"] if u else None


async def body(request: Request) -> dict:
    if not (await request.body()).strip():
        return {}
    try:
        b = await request.json()
    except ValueError:
        raise ValueError("The body is not JSON") from None
    if not isinstance(b, dict):
        raise ValueError("The body is a JSON object")
    return b


# ---------------------------------------------------------------- overview

def _jobs_now() -> list[dict]:
    last, pending, now = tasks.last_runs(), tasks.pending_jobs(), _dt.datetime.now()
    out = []
    for j in model.jobs():
        n = schedule.next_after(j["cron"], now) if j["enabled"] else None
        out.append({**j, "nextRun": tasks.iso(n), "lastRun": last.get(j["id"]), "pending": j["id"] in pending})
    return out


@router.get("/overview", dependencies=[access.signed_in])
def overview():
    """Everything the web app draws its pages from: the servers (never a password), the destinations, the jobs with
    their next and last run, whether something is running, the server's time (schedules run in its time zone), the
    folder a new local destination suggests and the suite's own database server, offered when adding a server."""
    return {"servers": model.servers(), "destinations": model.destinations(), "jobs": _jobs_now(), "busy": tasks.busy(),
            "now": _dt.datetime.now().astimezone().isoformat(timespec="seconds"), "backupDir": config.BACKUP_DIR,
            "suiteServer": {"host": config.DB_HOST, "port": config.DB_PORT}}


# ---------------------------------------------------------------- servers

@router.post("/servers", dependencies=[access.admin_write])
async def add_server(request: Request):
    return await run_in_threadpool(model.save_server, await body(request), who(request))


@router.put("/servers/{sid}", dependencies=[access.admin_write])
async def change_server(sid: int, request: Request):
    return await run_in_threadpool(model.save_server, await body(request), who(request), sid)


@router.delete("/servers/{sid}", dependencies=[access.admin_write])
def remove_server(sid: int):
    model.delete_server(sid)
    return {"ok": True}


def _info(server: dict) -> dict:
    with engine.Connection(server) as conn:
        return engine.server_info(conn)


@router.post("/servers/test", dependencies=[access.admin_write])
async def test_unsaved(request: Request):
    """Try the server form before saving it: the version, whether it is a Galera node, its databases."""
    return await run_in_threadpool(_info, model.unsaved_server(await body(request)))


@router.get("/servers/{sid}/info", dependencies=[access.admin])
def server_info(sid: int):
    return _info(model.server(sid))


# ---------------------------------------------------------------- destinations

@router.post("/destinations", dependencies=[access.admin_write])
async def add_destination(request: Request):
    return await run_in_threadpool(model.save_destination, await body(request), who(request))


@router.put("/destinations/{did}", dependencies=[access.admin_write])
async def change_destination(did: int, request: Request):
    return await run_in_threadpool(model.save_destination, await body(request), who(request), did)


@router.delete("/destinations/{did}", dependencies=[access.admin_write])
def remove_destination(did: int):
    model.delete_destination(did)
    return {"ok": True}


@router.post("/destinations/{did}/test", dependencies=[access.admin_write])
def test_destination(did: int):
    return {"message": open_destination(model.destination(did)).test()}


_flows: dict[str, dict] = {}


@router.post("/destinations/{did}/google", dependencies=[access.admin_write])
def google_start(did: int, request: Request):
    """Sign in with Google (the device flow): a code to type at Google's address on any device; the app waits for the
    approval in the background and keeps the sign-in with the suite's keys and tokens."""
    d = model.destination(did)
    if d["type"] != "gdrive" or d.get("auth") == "service_account":
        raise ValueError("Only a Google Drive destination with your own Google account signs in")
    if not d.get("client_id") or not d.get("client_secret"):
        raise ValueError("Save the OAuth client ID and secret first")
    info = gdrive.start_device_flow(d["client_id"])
    by = who(request)
    import secrets
    flow = {"id": secrets.token_urlsafe(12), "status": "pending", "error": None, "code": info["user_code"],
            "url": info.get("verification_url") or info.get("verification_uri"), "expires": time.time() + int(info.get("expires_in", 1800))}
    for k in [k for k, f in _flows.items() if f["expires"] < time.time()]:
        _flows.pop(k, None)
    _flows[flow["id"]] = flow

    def poll():
        interval = int(info.get("interval", 5))
        while time.time() < flow["expires"] and flow["status"] == "pending":
            time.sleep(interval)
            try:
                st, data = gdrive.poll_device_flow(d["client_id"], d["client_secret"], info["device_code"])
            except Exception as e:
                flow.update(status="error", error=str(e))
                return
            if st == "slow_down":
                interval += 5
            elif st == "ok":
                model.set_google_account(did, data.get("refresh_token"), None, by)
                gdrive.forget_token(did)
                try:
                    account = gdrive.Drive(model.destination(did)).about().get("emailAddress")
                    model.set_google_account(did, None, account, by)
                except Exception:
                    pass
                flow["status"] = "ok"
                return
            elif st in ("denied", "expired"):
                flow["status"] = st
                return
        if flow["status"] == "pending":
            flow["status"] = "expired"

    threading.Thread(target=poll, daemon=True).start()
    return {"id": flow["id"], "code": flow["code"], "url": flow["url"], "status": flow["status"]}


@router.get("/google/{fid}", dependencies=[access.admin])
def google_flow(fid: str):
    f = _flows.get(fid)
    if not f:
        raise model.NotFound("No such sign-in")
    return {"status": f["status"], "error": f["error"]}


# ---------------------------------------------------------------- jobs

@router.post("/jobs", dependencies=[access.admin_write])
async def add_job(request: Request):
    return model.save_job(await body(request))


@router.put("/jobs/{jid}", dependencies=[access.admin_write])
async def change_job(jid: int, request: Request):
    return model.save_job(await body(request), jid)


@router.delete("/jobs/{jid}", dependencies=[access.admin_write])
def remove_job(jid: int):
    model.delete_job(jid)
    return {"ok": True}


@router.post("/jobs/{jid}/run", dependencies=[access.editor_write])
def run_job(jid: int, request: Request):
    j = model.job(jid)
    if jid in tasks.pending_jobs():
        raise ValueError("This job is already queued or running")
    return {"runId": tasks.enqueue("backup", "Backup: %s" % j["name"], {"job_id": jid}, job_id=jid, by=who(request))}


# ---------------------------------------------------------------- backups and restores

@router.get("/destinations/{did}/backups", dependencies=[access.signed_in])
def list_backups(did: int):
    d = open_destination(model.destination(did))
    return {"items": d.list(), "free": d.free_bytes()}


def _archive(did: int, name: str) -> str:
    dest = model.destination(did)
    d = open_destination(dest)
    safe_name(name)
    return d.fetch(name)


@router.get("/destinations/{did}/backups/{name}", dependencies=[access.admin])
def backup_contents(did: int, name: str):
    """What the backup holds: databases with their tables, views, routines and events, users and roles."""
    with engine.Archive(_archive(did, name)) as a:
        return a.contents()


@router.post("/destinations/{did}/backups/{name}/verify", dependencies=[access.editor_write])
def verify_backup(did: int, name: str):
    with engine.Archive(_archive(did, name)) as a:
        n, problems = a.verify()
    return {"files": n, "problems": problems}


@router.post("/destinations/{did}/backups/{name}/preview", dependencies=[access.admin_write])
async def restore_preview(did: int, name: str, request: Request):
    """What a restore would do on the target server, and what it would overwrite there: {serverId, plan}."""
    b = await body(request)

    def go():
        server = model.server(int(b.get("serverId") or 0))
        with engine.Archive(_archive(did, name)) as a:
            norm = engine.normalize_plan(a, b.get("plan") or {})
            lines = engine.describe(norm)
            with engine.Connection(server) as conn:
                warnings = engine.preflight(conn, norm)
                info = engine.server_info(conn)
        return {"lines": lines, "warnings": warnings, "galera": info["galera"], "version": info["version"]}
    return await run_in_threadpool(go)


@router.post("/destinations/{did}/backups/{name}/restore", dependencies=[access.admin_write])
async def restore(did: int, name: str, request: Request):
    """Queue the restore: {serverId, plan}. The run's log shows how it goes."""
    b = await body(request)
    server = model.server(int(b.get("serverId") or 0))
    with engine.Archive(await run_in_threadpool(_archive, did, name)) as a:
        engine.normalize_plan(a, b.get("plan") or {})
    rid = tasks.enqueue("restore", "Restore: %s onto %s" % (name, server["name"]),
                        {"destination_id": did, "file": name, "server_id": server["id"], "plan": b.get("plan")}, by=who(request))
    return {"runId": rid}


@router.delete("/destinations/{did}/backups/{name}", dependencies=[access.admin_write])
def delete_backup(did: int, name: str):
    open_destination(model.destination(did)).delete(safe_name(name))
    return {"ok": True}


@router.get("/destinations/{did}/backups/{name}/download", dependencies=[access.admin])
def download_backup(did: int, name: str):
    dest = model.destination(did)
    d = open_destination(dest)
    safe_name(name)
    if dest["type"] == "local":
        return FileResponse(d.fetch(name), media_type="application/x-tar", filename=name)
    r = d.stream(name)
    headers = {"Content-Disposition": f'attachment; filename="{name}"'}
    if r.headers.get("Content-Length"):
        headers["Content-Length"] = r.headers["Content-Length"]
    return StreamingResponse(r.iter_content(1 << 20), media_type="application/x-tar", headers=headers)


# ---------------------------------------------------------------- runs

@router.get("/runs", dependencies=[access.signed_in])
def list_runs(limit: int = 100, job: int | None = None):
    return {"items": tasks.runs(limit, job)}


@router.get("/runs/{rid}", dependencies=[access.signed_in])
def get_run(rid: int):
    return tasks.run(rid)


@router.post("/runs/{rid}/cancel", dependencies=[access.editor_write])
def cancel_run(rid: int):
    if not tasks.cancel(rid):
        raise ValueError("That run is not queued or running")
    return {"ok": True}
