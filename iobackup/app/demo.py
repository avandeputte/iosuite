"""Demo data (iosuite_shared.demo): ioBackup set up the way the Calloways would: the suite's own database server (no
password kept: a suite admin types it to use it), a local folder for the backups, a nightly job for every database
and a weekly one for ioPix, both turned off, and two weeks of past runs (one that failed), so the pages have
something to show. Nothing runs until someone turns a job on."""
import datetime as dt
import json

from app import config, db, model

DEST = "/var/backups/iosuite-demo"


def seed(people: dict) -> None:
    by = people["morgan"]["name"]
    srv = model.save_server({"name": "Suite database", "host": config.DB_HOST or "localhost", "port": config.DB_PORT or 3306,
                             "user": "backup"}, by)
    dest = model.save_destination({"name": "Basement storage box", "kind": "local", "path": DEST}, by)
    nightly = model.save_job({"name": "Every database, nightly", "databases": "all", "includeUsers": True, "keep": 14,
                              "serverId": srv["id"], "destinationId": dest["id"], "enabled": False,
                              "schedule": {"mode": "daily", "time": "02:30"}})
    photos = model.save_job({"name": "ioPix, weekly", "databases": ["iopix"], "includeUsers": False, "keep": 8,
                             "serverId": srv["id"], "destinationId": dest["id"], "enabled": False,
                             "schedule": {"mode": "weekly", "time": "03:00", "days": [0]}})
    now = dt.datetime.now().replace(microsecond=0)
    for back in range(14, 0, -1):
        start = (now - dt.timedelta(days=back)).replace(hour=2, minute=30, second=0)
        failed = back == 6
        end = start + dt.timedelta(minutes=3, seconds=back * 7)
        name = f"every-database-nightly-{start:%Y%m%d-%H%M%S}.tar"
        result = None if failed else {"file": name, "size": 48_000_000 + back * 350_000, "destinationId": dest["id"], "pruned": []}
        log = (f"{start:%H:%M:%S} backing up 13 databases from Suite database\n" +
               (f"{end:%H:%M:%S} error: could not connect to the server (it was restarting for an update)\n" if failed
                else f"{end:%H:%M:%S} stored {name} in Basement storage box\n"))
        db.ex("INSERT INTO bkp_runs (kind, title, job_id, trigger_kind, user_name, status, queued_at, started_at, finished_at, payload, result, log) "
              "VALUES ('backup', %s, %s, 'schedule', NULL, %s, %s, %s, %s, %s, %s, %s)",
              (nightly["name"], nightly["id"], "failed" if failed else "ok", start, start, end, json.dumps({"jobId": nightly["id"]}),
               json.dumps(result) if result else None, log))
    sunday = now - dt.timedelta(days=(now.weekday() + 1) % 7 or 7)
    start = sunday.replace(hour=3, minute=0, second=0)
    db.ex("INSERT INTO bkp_runs (kind, title, job_id, trigger_kind, user_name, status, queued_at, started_at, finished_at, payload, result, log) "
          "VALUES ('backup', %s, %s, 'schedule', NULL, 'ok', %s, %s, %s, %s, %s, %s)",
          (photos["name"], photos["id"], start, start, start + dt.timedelta(minutes=1),
           json.dumps({"jobId": photos["id"]}), json.dumps({"file": f"iopix-weekly-{start:%Y%m%d-%H%M%S}.tar", "size": 21_500_000,
                                                            "destinationId": dest["id"], "pruned": []}),
           f"{start:%H:%M:%S} backing up iopix from Suite database\n"))
