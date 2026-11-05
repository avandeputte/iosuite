"""Command line: python -m app.cli <command>

  migrate                         create or update the tables
  check                           connect to the databases and say what is there

Accounts are the suite's: `iosuite-shared --config . admin NAME --app iosuite` makes an admin (setup.sh does),
`iosuite-shared --config . password NAME` sets a password.
"""
import sys

from app import apps, db, users


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    db.migrate()
    if cmd == "migrate":
        print("ok: tables ready")
    elif cmd == "check":
        users.ensure_admin_from_env()
        u = len(users.all_users())
        print(f"ok: {u} account(s), {len(apps.CATALOGUE)} app(s) on the page")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
