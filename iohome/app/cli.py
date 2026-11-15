"""Command line: python -m app.cli <command>

  migrate                      create or update the tables
  check                        connect to the databases and say what is there
  import-homebox FILE [NAME]   the things in a Homebox CSV export, added as NAME (or the first admin)

Accounts are the suite's: `iosuite-shared --config . admin NAME --app iohome` makes an admin (setup.sh does),
`iosuite-shared --config . password NAME` sets a password.
"""
import sys
from pathlib import Path

from app import db, users


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    db.migrate()
    if cmd == "migrate":
        print("ok: tables ready")
    elif cmd == "check":
        n = db.one("SELECT count(*) AS n FROM hom_items")["n"]
        users.init()
        u = len(users.all_users())
        print(f"ok: {u} account(s), {n} thing(s)")
    elif cmd == "import-homebox":
        if not args or len(args) > 2:
            print("import-homebox FILE [NAME]", file=sys.stderr)
            return 2
        from app import homebox
        users.init()
        u = users.find(args[1]) if len(args) == 2 else next((x for x in users.all_users() if x["role"] == "admin"), None)
        if not u:
            print("no such account (or no admin to add them as)", file=sys.stderr)
            return 2
        r = homebox.keep(u, homebox.read(Path(args[0]).read_bytes()))
        print(f"ok: {r['added']} added, {r['changed']} changed, {len(r['skipped'])} skipped, {r['locations']} new places, {r['labels']} new labels")
        for s in r["skipped"]:
            print("  " + s)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
