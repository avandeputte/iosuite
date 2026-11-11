"""Command line: python -m app.cli <command>

  migrate                     create or update the tables
  check                       connect to the databases and say what is there
  jobs                        the jobs, with their schedule and next run
  run JOB                     back up now (the job's name or number), here, without the web app; prints the log
  runs                        the last runs

A backup file needs neither the web app nor its database: `python -m app.offline --help` lists, verifies and restores
one on any machine with Python 3 and the MariaDB client (for when the machine that ran ioBackup is gone).

Accounts are the suite's: `iosuite-shared --config . admin NAME --app iobackup` makes an admin (setup.sh does),
`iosuite-shared --config . password NAME` sets a password.
"""
import sys

from app import db


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    db.migrate()
    from iosuite_shared import users
    users.init()
    from app import model, schedule, tasks
    if cmd == "migrate":
        print("ok: tables ready")
    elif cmd == "check":
        print(f"ok: {len(model.servers())} servers, {len(model.destinations())} destinations, {len(model.jobs())} jobs")
    elif cmd == "jobs":
        for j in model.jobs():
            n = schedule.next_after(j["cron"]) if j["enabled"] else None
            print(f"{j['id']:4}  {j['name']:24} {j['cron'] or 'on demand':16} next: {tasks.iso(n) or '-'}")
    elif cmd == "run" and args:
        j = next((x for x in model.jobs() if x["name"] == args[0] or str(x["id"]) == args[0]), None)
        if not j:
            print(f"no job {args[0]!r}", file=sys.stderr)
            return 1
        rid = tasks.enqueue("backup", "Backup: %s" % j["name"], {"job_id": j["id"]}, job_id=j["id"], by="cli")
        tasks.execute(rid)
        r = tasks.run(rid)
        print("\n".join(r["log"]))
        return 0 if r["status"] == "ok" else 1
    elif cmd == "runs":
        for r in tasks.runs(30):
            print(f"{r['id']:5}  {r['status']:9} {r['queued']}  {r['title']}")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
