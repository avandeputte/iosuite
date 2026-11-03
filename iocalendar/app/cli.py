"""Command line: python -m app.cli <command>

  migrate                         create or update the tables
  check                           connect to the databases and say what is there
  create-user NAME [ROLE]         the password comes from IOCALENDAR_PASSWORD (or is asked for)
  set-password NAME               the same
  import CALENDAR-ID FILE.ics     events from an .ics file into a calendar
  sync-birthdays                  bring the Birthdays calendar up to date from ioContacts
"""
import getpass
import os
import sys

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
        n = db.one("SELECT count(*) AS n FROM events WHERE deleted = 0")["n"]
        c = db.one("SELECT count(*) AS n FROM calendars")["n"]
        users.ensure_admin_from_env()
        u = len(users.all_users())
        print(f"ok: {u} account(s), {c} calendar(s), {n} event(s)")
    elif cmd in ("create-user", "set-password"):
        if not args:
            print("a user name, please", file=sys.stderr)
            return 2
        users.ensure_admin_from_env()
        pw = os.environ.get("IOCALENDAR_PASSWORD") or getpass.getpass(f"Password for {args[0]}: ")
        try:
            u = users.find(args[0])
            if cmd == "create-user":
                if u:
                    users.update(u["id"], password=pw, role=args[1] if len(args) > 1 else None)
                    print(f"ok: {args[0]} exists; password set")
                else:
                    from iothing_auth import users as shared
                    first = not users.any_users()
                    shared.create(args[0], pw, args[1] if len(args) > 1 else "admin", "iocalendar", suite_admin=first)
                    print(f"ok: created {args[0]}" + (" (suite admin)" if first else ""))
            else:
                if not u:
                    print("no such user", file=sys.stderr)
                    return 1
                users.update(u["id"], password=pw)
                print("ok: password set")
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    elif cmd == "import":
        if len(args) != 2:
            print("import CALENDAR-ID FILE.ics", file=sys.stderr)
            return 2
        from app import model
        with open(args[1], encoding="utf-8", errors="replace") as f:
            print(model.import_text(int(args[0]), f.read()))
    elif cmd == "sync-birthdays":
        from app import contacts
        print(contacts.sync_birthdays())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
