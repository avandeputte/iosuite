"""Needs a look: the transactions nobody looked at yet.

A transaction needs a look when it came in after the household started looking (the first time this page was used:
what was there before counts as seen) or has no category (and is neither split nor half of a transfer), is not
hidden, and nobody marked it reviewed.
Changing a transaction by hand marks it; so does Reviewed on the page, for one, for those ticked, or for all."""
import time

from app import db, model

SINCE = "review_since"  # mny_settings: when the household started looking (epoch seconds)


def since() -> int:
    v = db.get_setting(SINCE)
    if v is None:
        v = str(int(time.time()))
        db.set_setting(SINCE, v)
    return int(v)


def where() -> tuple[str, list]:
    """SQL for the transactions (t) that need a look."""
    return ("t.hidden = 0 AND NOT EXISTS (SELECT 1 FROM mny_reviewed v WHERE v.transaction_id = t.id) "
            "AND (t.created_at >= FROM_UNIXTIME(%s) OR ((t.category IS NULL OR t.category = '') "
            "AND NOT EXISTS (SELECT 1 FROM mny_splits s WHERE s.transaction_id = t.id) "
            "AND NOT EXISTS (SELECT 1 FROM mny_transfers x WHERE x.out_id = t.id OR x.in_id = t.id)))", [since()])


def count(u: dict) -> int:
    if model.role_rank(u) < 1:
        return 0
    vis, args = model._visible(u)
    w, wargs = where()
    return db.one(f"SELECT count(*) AS n FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id "
                  f"WHERE {vis} AND a.track = 'transactions' AND {w}", (*args, *wargs))["n"]


def looked(u: dict | None, tid: int) -> None:
    db.ex("INSERT IGNORE INTO mny_reviewed (transaction_id, by_user) VALUES (%s, %s)", (tid, (u or {}).get("id")))


def mark(u: dict, ids: list, on: bool = True) -> int:
    """Mark transactions reviewed (or not); those this person may change. How many."""
    n = 0
    for tid in ids[:2000]:
        t = model.tx_row(tid)
        if not t or not model.can_write(u, t):
            continue
        if on:
            looked(u, t["id"])
        else:
            db.ex("DELETE FROM mny_reviewed WHERE transaction_id = %s", (t["id"],))
        n += 1
    return n


def mark_all(u: dict) -> int:
    """Everything that needs a look and this person may change: reviewed. How many."""
    vis, args = model._visible(u)
    w, wargs = where()
    rows = db.q(f"SELECT t.id, a.owner_id FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id "
                f"WHERE {vis} AND a.track = 'transactions' AND {w}", (*args, *wargs))
    ids = [r["id"] for r in rows if model.can_write(u, r)]
    if ids:
        db.many("INSERT IGNORE INTO mny_reviewed (transaction_id, by_user) VALUES (%s, %s)", [(i, u["id"]) for i in ids])
    return len(ids)
