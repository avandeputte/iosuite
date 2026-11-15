"""Command line: python -m app.cli <command>

  migrate                         create or update the tables
  check                           connect to the databases and say what is there

Accounts are the suite's: `iosuite-shared --config . admin NAME --app ionote` makes an admin (setup.sh does),
`iosuite-shared --config . password NAME` sets a password.
"""
import sys

from iosuite_shared import users

from app import config, db


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    db.init()  # the database (created when missing and the user may) and its tables
    if cmd == "migrate":
        print("ok: tables ready")
    elif cmd == "check":
        with db.connect() as con:
            n = con.execute("SELECT count(*) FROM nts_notes WHERE deleted = 0").fetchone()[0]
        users.init()  # the Shared ioSuite database's tables (created when missing), as the other apps do
        u = len(users.list_users(config.APP))
        print(f"ok: {u} account(s), {n} note(s)")
        warning = db.test({}).get("warning")  # pictures are kept in the database: max_allowed_packet must be large enough
        if warning:
            print("note: " + warning)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
