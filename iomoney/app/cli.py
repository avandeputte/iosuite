"""Command line: python -m app.cli <command>

  migrate        create or update the tables
  check          connect to the databases and say what is there
  sync [--full]  copy Monarch Money in now (--full: the past two years of transactions again)
  quotes         ask Yahoo Finance for every quote now

Accounts are the suite's: `iosuite-shared --config . admin NAME --app iomoney` makes an admin (setup.sh does),
`iosuite-shared --config . password NAME` sets a password. The Monarch sign-in is kept with the suite's keys and
tokens (Settings › Global settings › Keys and tokens).
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
        n = db.one("SELECT count(*) AS n FROM mny_accounts")["n"]
        t = db.one("SELECT count(*) AS n FROM mny_transactions")["n"]
        users.init()
        u = len(users.all_users())
        print(f"ok: {u} account(s), {n} money account(s), {t} transaction(s)")
    elif cmd == "sync":
        from app import monarch
        users.init()
        monarch.declare()
        r = monarch.sync(full="--full" in args)
        print(("ok: " if r["ok"] else "failed: ") + r["message"])
        return 0 if r["ok"] else 1
    elif cmd == "quotes":
        from app import model, quotes
        r = quotes.refresh(force=True)
        model.revalue_manual_investments()
        print(f"ok: {r['asked']} asked, {r['failed']} failed")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
