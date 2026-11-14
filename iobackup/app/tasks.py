"""Runs (backups and restores), the queue that carries them out one at a time, and the scheduler that starts jobs on
their schedule. Every run and its log are kept in bkp_runs.

Everything runs in one worker thread, in order: two dumps of the same server at once would only compete for its
disks, and a restore must never overlap a backup of the database it is writing. The worker and the scheduler run in
the one process of the app (BACKGROUND=0 turns them off, e.g. for a second copy).
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import queue
import shutil
import threading
import time
import traceback

from app import config, db, engine, model, schedule
from app.destinations import open_destination, prune

log = logging.getLogger("iobackup")

KEEP_RUNS = 500          # the history keeps this many runs
MAX_LOG_LINES = 5000     # lines kept per run; after that only errors and the outcome

_queue: queue.Queue = queue.Queue()
_cancel: dict[int, threading.Event] = {}
_lines: dict[int, int] = {}
_started = False


def _now() -> _dt.datetime:
    return _dt.datetime.now().replace(microsecond=0)


def iso(t) -> str | None:
    """A stored local time as ISO 8601 with the server's offset."""
    return t.astimezone().isoformat(timespec="seconds") if t else None


def _public(r: dict, with_log: bool = False) -> dict:
    lines = (r.get("log") or "").splitlines()
    out = {"id": r["id"], "kind": r["kind"], "title": r["title"], "jobId": r["job_id"], "trigger": r["trigger_kind"],
           "user": r["user_name"], "status": r["status"], "queued": iso(r["queued_at"]), "started": iso(r["started_at"]),
           "finished": iso(r["finished_at"]), "result": json.loads(r["result"]) if r.get("result") else None,
           "last": lines[-1] if lines else ""}
    if with_log:
        out["log"] = lines
    return out


def runs(limit: int = 100, job_id: int | None = None) -> list[dict]:
    limit = max(1, min(int(limit or 100), KEEP_RUNS))
    cols = "id, kind, title, job_id, trigger_kind, user_name, status, queued_at, started_at, finished_at, result, " \
           "SUBSTRING_INDEX(TRIM(TRAILING '\\n' FROM log), '\\n', -1) AS log"
    if job_id:
        rows = db.q(f"SELECT {cols} FROM bkp_runs WHERE job_id = %s ORDER BY id DESC LIMIT %s", (job_id, limit))
    else:
        rows = db.q(f"SELECT {cols} FROM bkp_runs ORDER BY id DESC LIMIT %s", (limit,))
    return [_public(r) for r in rows]


def run(rid: int) -> dict:
    r = db.one("SELECT * FROM bkp_runs WHERE id = %s", (rid,))
    if not r:
        raise model.NotFound("No such run")
    return _public(r, with_log=True)


def last_runs() -> dict[int, dict]:
    """Each job's newest finished run."""
    rows = db.q("SELECT r.id, r.job_id, r.status, r.finished_at, r.result FROM bkp_runs r JOIN "
                "(SELECT job_id, MAX(id) AS id FROM bkp_runs WHERE job_id IS NOT NULL AND status NOT IN ('queued', 'running') "
                "GROUP BY job_id) m ON m.id = r.id")
    return {r["job_id"]: {"id": r["id"], "status": r["status"], "finished": iso(r["finished_at"]),
                          "result": json.loads(r["result"]) if r["result"] else None} for r in rows}


def pending_jobs() -> set[int]:
    return {r["job_id"] for r in db.q("SELECT DISTINCT job_id FROM bkp_runs WHERE status IN ('queued', 'running') AND job_id IS NOT NULL")}


def busy() -> bool:
    return bool(db.one("SELECT 1 AS x FROM bkp_runs WHERE status IN ('queued', 'running') LIMIT 1"))


def _update(rid: int, **fields) -> None:
    if "result" in fields:
        fields["result"] = json.dumps(fields["result"]) if fields["result"] is not None else None
    cols = {"started": "started_at", "finished": "finished_at"}
    sets = ", ".join(f"{cols.get(k, k)} = %s" for k in fields)
    db.ex(f"UPDATE bkp_runs SET {sets} WHERE id = %s", (*fields.values(), rid))


def _logger(rid: int):
    def emit(msg: str) -> None:
        n = _lines.get(rid, 0) + 1
        _lines[rid] = n
        log.info("[run %s] %s", rid, msg)
        if n > MAX_LOG_LINES and not any(w in msg for w in ("FAILED", "error", "Finished", "Cancelled")):
            if n == MAX_LOG_LINES + 1:
                msg = "… (the rest of the log is not kept; errors and the outcome still are)"
            else:
                return
        line = "%s %s\n" % (_dt.datetime.now().strftime("%H:%M:%S"), msg)
        db.ex("UPDATE bkp_runs SET log = CONCAT(log, %s) WHERE id = %s", (line, rid))
    return emit


def enqueue(kind: str, title: str, payload: dict, job_id: int | None = None, trigger: str = "manual", by: str | None = None) -> int:
    rid = db.ex("INSERT INTO bkp_runs (kind, title, job_id, trigger_kind, user_name, status, queued_at, payload, log) "
                "VALUES (%s, %s, %s, %s, %s, 'queued', %s, %s, '')", (kind, title[:255], job_id, trigger, by, _now(), json.dumps(payload)))
    old = db.one("SELECT id FROM bkp_runs ORDER BY id DESC LIMIT 1 OFFSET %s", (KEEP_RUNS,))
    if old:
        db.ex("DELETE FROM bkp_runs WHERE id <= %s AND status NOT IN ('queued', 'running')", (old["id"],))
    _cancel[rid] = threading.Event()
    _queue.put(rid)
    return rid


def cancel(rid: int) -> bool:
    r = run(rid)
    ev = _cancel.get(rid)
    if r["status"] not in ("queued", "running") or ev is None:
        return False
    ev.set()
    if r["status"] == "queued":
        _update(rid, status="cancelled", finished=_now())
    return True


# ---------------------------------------------------------------- what a run does

def _do_backup(p: dict, emit, ev) -> dict:
    job = model.job(p["job_id"])
    server, dest = model.server(job["serverId"]), model.destination(job["destinationId"])
    label = engine.slug(job["name"])
    emit("Backing up %s to %s" % (server["name"], dest["name"]))
    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    tar, manifest = engine.run_backup(
        server, job["databases"] or "all", include_users=job["includeUsers"], workdir=str(config.WORK_DIR), label=label,
        lock_all=job["lockAll"], desync=job["desync"], compress_level=int(job["compressLevel"] or 6),
        log=emit, cancel=ev, source_name=server["name"])
    try:
        size = os.path.getsize(tar)
        d = open_destination(dest)
        emit("Stored as %s" % d.store(tar, emit, ev))
    finally:
        if os.path.exists(tar):
            os.unlink(tar)
    removed = []
    if job["keep"]:
        try:
            removed = prune(d, label, job["keep"], emit)
            if not removed:
                emit("Retention: %d or fewer backups kept, nothing to remove" % job["keep"])
        except Exception as e:  # a failed clean-up does not make a good backup a failed one
            emit("warning: the retention clean-up failed: %s" % e)
    return {"file": os.path.basename(tar), "size": size, "destinationId": dest["id"],
            "databases": [x["name"] for x in manifest["databases"]], "pruned": removed}


def _do_restore(p: dict, emit, ev) -> dict:
    dest, server = model.destination(p["destination_id"]), model.server(p["server_id"])
    d = open_destination(dest)
    path = d.fetch(p["file"], emit) if dest["type"] == "gdrive" else d.fetch(p["file"])
    emit("Restoring %s onto %s" % (p["file"], server["name"]))
    with engine.Archive(path) as a:
        errors = engine.run_restore(server, a, p["plan"], log=emit, cancel=ev)
    if errors:
        raise engine.EngineError("%d error(s) during the restore; see the log" % len(errors))
    return {"file": p["file"], "serverId": server["id"]}


def _dur(s: float) -> str:
    s = int(s)
    return "%dm %02ds" % (s // 60, s % 60) if s >= 60 else "%ds" % s


def execute(rid: int) -> None:
    """Carry out one queued run (the worker calls it; the tests call it directly)."""
    r = db.one("SELECT status, kind, payload FROM bkp_runs WHERE id = %s", (rid,))
    if not r or r["status"] != "queued":
        return
    ev = _cancel.setdefault(rid, threading.Event())
    emit = _logger(rid)
    _update(rid, status="running", started=_now())
    t0 = time.time()
    try:
        fn = _do_backup if r["kind"] == "backup" else _do_restore
        result = fn(json.loads(r["payload"]), emit, ev)
        emit("Finished in %s" % _dur(time.time() - t0))
        _update(rid, status="ok", finished=_now(), result=result)
    except Exception as e:
        if isinstance(e, engine.Cancelled) or ev.is_set():
            emit("Cancelled")
            _update(rid, status="cancelled", finished=_now())
        else:
            emit("FAILED: %s" % e)
            if not isinstance(e, (engine.EngineError, model.NotFound)):
                log.error("run %s crashed:\n%s", rid, traceback.format_exc())
            _update(rid, status="failed", finished=_now())
            _tell_failed(rid, r["kind"], e)
    finally:
        _cancel.pop(rid, None)
        _lines.pop(rid, None)
        if _queue.empty():
            shutil.rmtree(config.WORK_DIR, ignore_errors=True)


def _tell_failed(rid: int, kind: str, e: Exception) -> None:
    """A notification to the suite admins who want it (iosuite_shared.push): a backup or a restore did not finish."""
    try:
        from iosuite_shared import push
        title = db.one("SELECT title FROM bkp_runs WHERE id = %s", (rid,))
        what = "Backup" if kind == "backup" else "Restore"
        push.notify_admins("backups", f"{what} failed: {(title or {}).get('title') or 'run %d' % rid}", str(e)[:300],
                           url=push.link("iobackup", f"#/run/{rid}"), once=f"backup-failed:{rid}", urgency="high")
    except Exception:  # noqa: BLE001 - the run's own outcome is what counts
        log.warning("could not send the notification for run %s", rid, exc_info=True)


def _worker() -> None:
    while True:
        rid = _queue.get()
        try:
            execute(rid)
        except Exception:  # the database went away: the run stays as it was, the worker carries on
            log.exception("run %s could not be carried out", rid)


# ---------------------------------------------------------------- the scheduler

def due(jobs: list[dict], minutes: list[_dt.datetime]) -> list[dict]:
    """The enabled jobs whose schedule fires in any of these minutes."""
    out = []
    for j in jobs:
        if not j["enabled"] or not j["cron"]:
            continue
        try:
            c = schedule.Cron(j["cron"])
        except ValueError:
            continue
        if any(c.matches(m) for m in minutes):
            out.append(j)
    return out


def _scheduler() -> None:
    last = _dt.datetime.now().replace(second=0, microsecond=0)
    while True:
        time.sleep(15)
        now = _dt.datetime.now().replace(second=0, microsecond=0)
        if now <= last:
            last = min(last, now)  # the clock went back: start again from now, firing nothing
            continue
        # every minute since the last look, at most 90 (a host that slept does not fire a day's worth of jobs)
        minutes, t = [], last + _dt.timedelta(minutes=1)
        while t <= now and len(minutes) < 90:
            minutes.append(t)
            t += _dt.timedelta(minutes=1)
        last = now
        try:
            pending = pending_jobs()
            for j in due(model.jobs(), minutes):
                if j["id"] in pending:
                    log.info("job %s is still queued or running: this scheduled start is skipped", j["name"])
                    continue
                enqueue("backup", "Backup: %s" % j["name"], {"job_id": j["id"]}, job_id=j["id"], trigger="schedule")
        except Exception:
            log.exception("the scheduler could not read the jobs")


def start() -> None:
    """At start: what was queued or running when the app stopped did not finish; then the worker and the scheduler."""
    global _started
    if _started:
        return
    _started = True
    for r in db.q("SELECT id FROM bkp_runs WHERE status IN ('queued', 'running')"):
        _logger(r["id"])("Interrupted: the app stopped")
        _update(r["id"], status="failed", finished=_now())
    threading.Thread(target=_worker, name="iobackup-worker", daemon=True).start()
    threading.Thread(target=_scheduler, name="iobackup-scheduler", daemon=True).start()
