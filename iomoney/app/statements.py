"""Reconciling an account against the bank's statement.

A statement says: from this day to that day the balance went from the opening balance to the closing one. The
transactions of those days are ticked off against it, one by one; when the ticked ones add up to what the balance
moved by, the difference is zero and the account agrees with the bank up to the statement's last day. The ticked
transactions are marked reconciled (mny_reconciled), and the statement is kept (mny_statements) so that the next one
starts where it ended. An account of what is owed (a card, a loan) keeps its balance as a positive number, so there a
purchase (money out) makes the balance go up."""
import datetime as dt
from decimal import Decimal

from iosuite_shared.errors import Invalid

from app import db, model

EARLIER_DAYS = 45  # transactions from before the statement that were not ticked off on the one before can clear on this one


def _sign(a: dict) -> Decimal:
    return Decimal(1) if a["is_asset"] else Decimal(-1)


def _public(r: dict) -> dict:
    return {"id": r["id"], "start": r["start_day"].isoformat(), "end": r["end_day"].isoformat(), "opening": model.n2(r["opening"]),
            "closing": model.n2(r["closing"]), "difference": model.n2(r["difference"]),
            "at": r["created_at"].isoformat() if r.get("created_at") else None}


def _balance_on(aid: int, day: dt.date) -> Decimal | None:
    r = db.one("SELECT balance FROM mny_balances WHERE account_id = %s AND day <= %s ORDER BY day DESC LIMIT 1", (aid, day))
    return Decimal(r["balance"]) if r else None


def of(u: dict, a: dict) -> dict:
    """{items: the statements the account was reconciled against, the latest first, next: {start, opening} where the
    next one starts (the day after the last one and its closing balance; without one, the account's first
    transaction and the balance kept for the day before, when there is one), writable}."""
    rows = db.q("SELECT * FROM mny_statements WHERE account_id = %s ORDER BY end_day DESC LIMIT 60", (a["id"],))
    if rows:
        start, opening = rows[0]["end_day"] + dt.timedelta(days=1), Decimal(rows[0]["closing"])
    else:
        first = db.one("SELECT MIN(day) AS d FROM mny_transactions WHERE account_id = %s", (a["id"],))["d"]
        start = max(first, dt.date.today() - dt.timedelta(days=31)) if first else None
        opening = _balance_on(a["id"], start - dt.timedelta(days=1)) if start else None
    return {"items": [_public(r) for r in rows], "writable": model.can_write(u, a), "isAsset": bool(a["is_asset"]),
            "next": {"start": start.isoformat() if start else None, "opening": model.n2(opening)}}


def lines(u: dict, a: dict, start, end) -> dict:
    """The transactions to tick off against a statement from start to end: those of these days (the hidden ones too:
    they are on the statement; not the pending ones), and before them the earlier ones not ticked off on the
    statement before (earlier: true). Each as the lists give it."""
    s, e = model.day(start, "The first day"), model.day(end, "The last day")
    if e < s:
        raise Invalid("The statement ends before it starts")
    if (e - s).days > 400:
        raise Invalid("A statement covers at most 400 days")
    before = db.one("SELECT 1 AS x FROM mny_statements WHERE account_id = %s AND end_day < %s LIMIT 1", (a["id"], s))
    cols = ("t.*, a.owner_id, a.name AS account_name, a.currency, "
            "EXISTS (SELECT 1 FROM mny_reconciled r WHERE r.transaction_id = t.id) AS reconciled")
    rows = db.q(f"SELECT {cols} FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id "
                "WHERE t.account_id = %s AND t.pending = 0 AND t.day BETWEEN %s AND %s ORDER BY t.day, t.id", (a["id"], s, e))
    early = db.q(f"SELECT {cols} FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id "
                 "WHERE t.account_id = %s AND t.pending = 0 AND t.day >= %s AND t.day < %s "
                 "AND NOT EXISTS (SELECT 1 FROM mny_reconciled r WHERE r.transaction_id = t.id) ORDER BY t.day, t.id",
                 (a["id"], s - dt.timedelta(days=EARLIER_DAYS), s)) if before else []
    items = model.with_transfers([model.tx_public(t, u) for t in list(early) + list(rows)], u)
    for t, n in zip(items, range(len(items))):
        t["earlier"] = n < len(early)
    return {"items": items, "sign": int(_sign(a)), "writable": model.can_write(u, a)}


def save(u: dict, a: dict, b: dict) -> dict:
    """{start, end, opening, closing, ids: the transactions ticked off, anyway?}: mark them reconciled (the others of
    those days not) and keep the statement. A difference that is not zero is refused, unless anyway."""
    model._need(model.can_write(u, a))
    s, e = model.day(b.get("start"), "The first day"), model.day(b.get("end"), "The last day")
    if e < s:
        raise Invalid("The statement ends before it starts")
    opening = model.money(b.get("opening"), "The opening balance")
    closing = model.money(b.get("closing"), "The closing balance")
    try:
        ids = sorted({int(i) for i in (b.get("ids") or [])})
    except (TypeError, ValueError):
        raise Invalid("ids: the transactions ticked off") from None
    rows = db.q(f"SELECT id, amount FROM mny_transactions WHERE account_id = %s AND pending = 0 AND day <= %s AND id IN ({db.marks(len(ids))})",
                (a["id"], e, *ids)) if ids else []
    if len(rows) != len(ids):
        raise Invalid("Some of the transactions ticked off are not this account's, or are after the statement")
    cleared = sum((Decimal(r["amount"]) for r in rows), Decimal(0))
    diff = (closing - opening) - _sign(a) * cleared
    if diff and not model.flag(b.get("anyway")):
        raise Invalid(f"The transactions ticked off are {abs(diff)} {'short of' if diff * _sign(a) > 0 else 'over'} the statement")
    with db.tx():
        db.ex("DELETE r FROM mny_reconciled r JOIN mny_transactions t ON t.id = r.transaction_id "
              "WHERE t.account_id = %s AND t.day BETWEEN %s AND %s", (a["id"], s, e))
        db.many("INSERT IGNORE INTO mny_reconciled (transaction_id, by_user) VALUES (%s, %s)", [(i, u["id"]) for i in ids])
        db.ex("INSERT INTO mny_statements (account_id, start_day, end_day, opening, closing, difference, by_user) "
              "VALUES (%s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE start_day = VALUES(start_day), opening = VALUES(opening), "
              "closing = VALUES(closing), difference = VALUES(difference), by_user = VALUES(by_user), created_at = NOW()",
              (a["id"], s, e, opening, closing, diff, u["id"]))
    return {**_public(db.one("SELECT * FROM mny_statements WHERE account_id = %s AND end_day = %s", (a["id"], e))), "reconciled": len(ids)}


def remove(u: dict, sid) -> None:
    """Forget a statement (its transactions stay reconciled)."""
    try:
        r = db.one("SELECT * FROM mny_statements WHERE id = %s", (int(sid),))
    except (TypeError, ValueError):
        r = None
    a = model.account_row(r["account_id"]) if r else None
    if not r or not model.can_read(u, a):
        raise model.NotFound("No such statement")
    model._need(model.can_write(u, a))
    db.ex("DELETE FROM mny_statements WHERE id = %s", (r["id"],))
