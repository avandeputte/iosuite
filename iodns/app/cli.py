"""Command line: python -m app.cli <command>

  migrate                     create or update the tables
  check                       connect to the databases and say what is there
  compare VIEW                compare the servers of a view (internal, external…) with the master list
  push VIEW [--prune]         make every server of the view hold the master list (--prune: also remove what only they hold)
  import SERVER-ID [MODE]     the master list from one server (MODE: merge, overwrite or replace; default merge)
  ddns [--push]               find the public address now and update the records that follow it
  export                      the master list as JSON, on standard output

Accounts are the suite's: `iosuite-shared --config . admin NAME --app iodns` makes an admin (setup.sh does),
`iosuite-shared --config . password NAME` sets a password.
"""
import json
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
    from app import ddns, model, sync
    if cmd == "migrate":
        print("ok: tables ready")
    elif cmd == "check":
        print(f"ok: {len(model.entries())} entries, {len(model.views())} views, {len(model.servers())} servers")
    elif cmd == "compare" and args:
        st = sync.status(args[0], by="cli")
        for s in st["servers"]:
            print(f"{s['name']:24} {'ok' if s['ok'] else 'unreachable':12} {s['count']:5} records  {s['differences'] if s['ok'] else s['error']} differences")
        for r in st["rows"]:
            if r["state"] != "ok":
                print(f"  {r['state']:10} {r['name']}")
    elif cmd == "push" and args:
        r = sync.push_all(args[0], "cli", prune="--prune" in args)
        print(json.dumps(r, indent=2))
    elif cmd == "import" and args:
        print(json.dumps(sync.import_from(int(args[0]), args[1] if len(args) > 1 else "merge", "cli"), indent=2))
    elif cmd == "ddns":
        print(json.dumps(ddns.run("cli", "--push" in args), indent=2, default=str))
    elif cmd == "export":
        print(json.dumps(model.export(), indent=2))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
