"""The balance check: does what the bank says an account holds agree with the transactions kept here?

Monarch Money reports each account's balance day by day, and its transactions. Over a stretch of days the balance
should move by exactly what the transactions add up to. Where it does not, something is missing or there twice: a
transaction the bank link dropped, one kept twice, one hidden in Monarch (those are not kept here), an account whose
link was cut for a while. This looks at the cash accounts and the cards from Monarch Money that have a bank behind
them and follow their transactions, and says for each whether it agrees, and if not by how much and in which week
the gap appeared. Pending transactions explain a gap of exactly their sum (some banks count them in the balance,
some do not). A gap a person looked at and accepts is not flagged again while it stays the same."""
import datetime as dt
from decimal import Decimal

from iosuite_shared.errors import Invalid

from app import db, model

DAYS = 90
CENT = Decimal("0.01")
OK = "balance_ok:"  # mny_settings: balance_ok:<account id> = the gap a person accepted


def _accounts(u: dict) -> list[dict]:
    rows = [a for a in model.accounts(u) if a["source"] == "monarch" and not a["closed"] and a.get("track") == "transactions"
            and model.GROUP_OF.get(a["kind"]) in ("cash", "credit")]
    links = model.bank_links([a["id"] for a in rows])
    return [a for a in rows if (links.get(a["id"]) or {}).get("linked")]


def _check(a: dict, days: int) -> dict:
    today = dt.date.today()
    sign = Decimal(1) if a["is_asset"] else Decimal(-1)
    out = {"id": a["id"], "name": a["name"], "institution": a["institution"], "currency": a["currency"], "isAsset": bool(a["is_asset"]), "balance": model.n2(a["balance"]),
           "status": "unknown", "gap": None, "pending": 0.0, "weeks": [], "from": None, "to": today.isoformat()}
    bal = db.q("SELECT day, balance FROM mny_balances WHERE account_id = %s AND day >= %s AND day <= %s ORDER BY day",
               (a["id"], today - dt.timedelta(days=days + 14), today))
    if len(bal) < 2:
        return out
    start = today - dt.timedelta(days=days)
    first = max((b for b in bal if b["day"] <= start), key=lambda b: b["day"], default=bal[0])
    start = first["day"]
    tx = db.q("SELECT day, amount, pending FROM mny_transactions WHERE account_id = %s AND day > %s AND day <= %s ORDER BY day",
              (a["id"], start, today))
    pending = sum((Decimal(t["amount"]) for t in tx if t["pending"]), Decimal(0))
    posted = [t for t in tx if not t["pending"]]

    def gap_at(day: dt.date, balance: Decimal) -> Decimal:
        moved = sum((Decimal(t["amount"]) for t in posted if t["day"] <= day), Decimal(0))
        return (Decimal(balance) - Decimal(first["balance"])) - sign * moved
    gap = gap_at(today, Decimal(a["balance"]))
    # where it appeared: the gap as it stood at each balance kept (one a week at most), so a person sees between which
    # days it came
    weeks, prev, last, mark = [], Decimal(0), start, start
    points = [(x["day"], Decimal(x["balance"])) for x in bal if start < x["day"] < today] + [(today, Decimal(a["balance"]))]
    for n, (d, b) in enumerate(points):
        if d != today and (d - mark).days < 7 and n + 1 < len(points) and (points[n + 1][0] - mark).days <= 7:
            continue  # a nearer one to the week's end follows
        g = gap_at(d, b)
        if abs(g - prev) > CENT:
            weeks.append({"from": (last + dt.timedelta(days=1)).isoformat(), "to": d.isoformat(), "change": model.n2(g - prev), "gap": model.n2(g)})
        prev, last, mark = g, d, d
    accepted = db.get_setting(OK + str(a["id"]))
    if abs(gap) <= CENT:
        status = "ok"
    elif pending and abs(gap - sign * pending) <= CENT:
        status = "pending"
    elif accepted is not None and abs(gap - Decimal(accepted)) <= CENT:
        status = "accepted"
    else:
        status = "gap"
    out.update(status=status, gap=model.n2(gap), pending=model.n2(pending), weeks=weeks if status == "gap" else [],
               **{"from": start.isoformat()}, opening=model.n2(first["balance"]),
               moved=model.n2(sum((Decimal(t["amount"]) for t in posted), Decimal(0))), count=len(posted))
    return out


def check(u: dict, days: int = DAYS) -> dict:
    """{items: each account checked ({id, name, status: ok | pending (the pending ones explain it) | accepted | gap |
    unknown (too little balance history), gap, pending, from, to, opening, balance, moved, count, weeks: when a gap
    appeared}), gaps: how many are off}; the ones off first."""
    days = max(14, min(int(days or DAYS), 400))
    items = [_check(a, days) for a in _accounts(u)]
    order = {"gap": 0, "unknown": 1, "accepted": 2, "pending": 3, "ok": 4}
    items.sort(key=lambda x: (order[x["status"]], x["name"].lower()))
    return {"items": items, "gaps": sum(1 for x in items if x["status"] == "gap"), "days": days}


def accept(u: dict, a: dict, b: dict) -> dict:
    """{gap}: this account's gap was looked at and is fine as it is (null: flag it again)."""
    model._need(model.can_write(u, a))
    if b.get("gap") is None:
        db.set_setting(OK + str(a["id"]), None)
    else:
        g = model.money(b.get("gap"), "The gap")
        if not g:
            raise Invalid("There is no gap to accept")
        db.set_setting(OK + str(a["id"]), str(g))
    return {"ok": True}
