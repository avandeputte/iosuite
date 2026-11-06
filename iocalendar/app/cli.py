"""Command line: python -m app.cli <command>

  migrate                         create or update the tables
  check                           connect to the databases and say what is there
  import CALENDAR-ID FILE.ics     events from an .ics file into a calendar
  sync-birthdays                  bring the Birthdays calendar up to date from ioContacts
  sync-holidays                   bring the Holidays calendar up to date (Settings › Holidays)

Accounts are the suite's: `iosuite-shared --config . admin NAME --app iocalendar` makes an admin (setup.sh does),
`iosuite-shared --config . password NAME` sets a password.
"""
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
        n = db.one("SELECT count(*) AS n FROM cal_events WHERE deleted = 0")["n"]
        c = db.one("SELECT count(*) AS n FROM cal_calendars")["n"]
        users.init()
        u = len(users.all_users())
        print(f"ok: {u} account(s), {c} calendar(s), {n} event(s)")
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
    elif cmd == "sync-holidays":
        from app import holiday
        print(holiday.sync())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
