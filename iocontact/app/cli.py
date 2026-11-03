"""Command line: python -m app.cli <command>

  migrate                         create or update the tables
  check                           connect to the database and say what is there
  create-user NAME [ROLE]         the password comes from IOCONTACTS_PASSWORD (or is asked for)
  set-password NAME               the same
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
        n = db.one("SELECT count(*) AS n FROM contacts WHERE deleted = 0")["n"]
        u = len(users.all_users())
        print(f"ok: {u} account(s), {n} contact(s)")
    elif cmd in ("create-user", "set-password"):
        if not args:
            print("a user name, please", file=sys.stderr)
            return 2
        pw = os.environ.get("IOCONTACTS_PASSWORD") or getpass.getpass(f"Password for {args[0]}: ")
        try:
            if cmd == "create-user":
                if users.find(args[0]):
                    users.update(users.find(args[0])["id"], password=pw)
                    print(f"ok: {args[0]} exists; password set")
                else:
                    users.create(args[0], pw, args[1] if len(args) > 1 else "admin")
                    print(f"ok: created {args[0]}")
            else:
                u = users.find(args[0])
                if not u:
                    print("no such user", file=sys.stderr)
                    return 1
                users.update(u["id"], password=pw)
                print("ok: password set")
        except ValueError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
