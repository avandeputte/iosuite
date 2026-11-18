"""The balance check: does what the bank says an account holds agree with the transactions kept here?

Monarch Money reports each account's balance day by day, and its transactions. Over a stretch of days the balance
should move by exactly what the transactions add up to. Where it does not, something is missing or there twice: a
transaction the bank link dropped, one kept twice, one hidden in Monarch (those are not kept here), an account whose
link was cut for a while. This looks at the cash accounts and the cards from Monarch Money that have a bank behind
them and follow their transactions, and says for each whether it agrees, and if not by how much and in which week
the gap appeared. Every transaction counts alike: what Monarch calls pending is not kept (it says so of payments
the bank took weeks ago). A card's purchase of the past days may not be in the bank's balance yet, though: where
the gap is exactly what some of the past week's transactions add up to, those are named as not in the balance yet
(waiting) and the account is not flagged. A day's balance may not hold that day's transactions yet, so the check
starts a few days earlier or later where its first week then agrees. A transaction dated a day before or after the
balance moved shows as a gap in one week and its opposite in a later one: weeks that cancel out are left out of
where the gap appeared. A gap a person looked at and accepts is not flagged again while it stays the same."""
import datetime as dt
import itertools
from decimal import Decimal

from iosuite_shared.errors import Invalid

from app import db, model

DAYS = 90
EDGE_DAYS = 3    # the day the check starts on may be a few days earlier or later, where that makes its first week agree
WAIT_DAYS = 7    # a transaction this recent may not be in the bank's balance yet
RUN_DAYS = 45    # weeks whose changes cancel out within this many days are a matter of dates, not a gap
MAX_TRIED = 14   # of the latest ones, every combination is tried
CENT = Decimal("0.01")
OK = "balance_ok:"  # mny_settings: balance_ok:<account id> = the gap a person accepted


def _accounts(u: dict) -> list[dict]:
    rows = [a for a in model.accounts(u) if a["source"] == "monarch" and not a["closed"] and a.get("track") == "transactions"
            and model.GROUP_OF.get(a["kind"]) in ("cash", "credit")]
    links = model.bank_links([a["id"] for a in rows])
    return [a for a in rows if (links.get(a["id"]) or {}).get("linked")]


def _start(first: dict, bal: list[dict], tx: list[dict], sign: Decimal, today: dt.date, now: Decimal) -> dict:
    """The balance the check starts from. A day's balance may or may not hold that day's transactions yet (a payment
    dated the 19th that the balance shows on the 20th), which at the first day looks like a gap that is none. So
    where the first week does not agree from the day asked for, but does from a day up to EDGE_DAYS before or after,
    the check starts there."""
    end = next(((b["day"], Decimal(b["balance"])) for b in bal if b["day"] >= first["day"] + dt.timedelta(days=7) and b["day"] < today), (today, now))

    def off(b: dict) -> Decimal:
        moved = sum((Decimal(t["amount"]) for t in tx if b["day"] < t["day"] <= end[0]), Decimal(0))
        return abs((end[1] - Decimal(b["balance"])) - sign * moved)
    if off(first) <= CENT:
        return first
    near = sorted((b for b in bal if b["day"] != first["day"] and abs((b["day"] - first["day"]).days) <= EDGE_DAYS),
                  key=lambda b: (abs((b["day"] - first["day"]).days), b["day"]))
    return next((b for b in near if off(b) <= CENT), first)


def _waiting(recent: list[dict], gap: Decimal, sign: Decimal) -> list[dict]:
    """Which of the past week's transactions the bank's balance does not show yet: the ones that add up to exactly
    the gap, to the cent. The latest ones first (as many as it takes), then any of the latest MAX_TRIED. None when
    nothing of the past week explains it: then it is a gap."""
    items = sorted(recent, key=lambda t: (t["day"], t["id"]), reverse=True)
    target, run = -gap, Decimal(0)
    for n, t in enumerate(items):
        run += sign * Decimal(t["amount"])
        if abs(run - target) <= CENT:
            return items[:n + 1]
    few = items[:MAX_TRIED]
    for n in range(1, len(few) + 1):
        for some in itertools.combinations(few, n):
            if abs(sign * sum((Decimal(t["amount"]) for t in some), Decimal(0)) - target) <= CENT:
                return list(some)
    return []


def _check(a: dict, days: int) -> dict:
    today = dt.date.today()
    sign = Decimal(1) if a["is_asset"] else Decimal(-1)
    out = {"id": a["id"], "name": a["name"], "institution": a["institution"], "currency": a["currency"], "isAsset": bool(a["is_asset"]), "balance": model.n2(a["balance"]),
           "status": "unknown", "gap": None, "waiting": [], "weeks": [], "from": None, "to": today.isoformat()}
    bal = db.q("SELECT day, balance FROM mny_balances WHERE account_id = %s AND day >= %s AND day <= %s ORDER BY day",
               (a["id"], today - dt.timedelta(days=days + 14), today))
    if len(bal) < 2:
        return out
    start = today - dt.timedelta(days=days)
    first = max((b for b in bal if b["day"] <= start), key=lambda b: b["day"], default=bal[0])
    tx = db.q("SELECT id, day, amount, merchant, description FROM mny_transactions WHERE account_id = %s AND day > %s AND day <= %s "
              "ORDER BY day", (a["id"], first["day"] - dt.timedelta(days=EDGE_DAYS), today))
    first = _start(first, bal, tx, sign, today, Decimal(a["balance"]))
    start = first["day"]
    tx = [t for t in tx if t["day"] > start]
    points = [(x["day"], Decimal(x["balance"])) for x in bal if start < x["day"] < today] + [(today, Decimal(a["balance"]))]

    def gap_at(day: dt.date, balance: Decimal) -> Decimal:
        moved = sum((Decimal(t["amount"]) for t in tx if t["day"] <= day), Decimal(0))
        return (Decimal(balance) - Decimal(first["balance"])) - sign * moved

    def appeared() -> list[dict]:
        """Where the gap appeared: as it stood at each balance kept (one a week at most), so a person sees between
        which days it came."""
        weeks, prev, last, mark = [], Decimal(0), start, start
        for n, (d, b) in enumerate(points):
            if d != today and (d - mark).days < 7 and n + 1 < len(points) and (points[n + 1][0] - mark).days <= 7:
                continue  # a nearer one to the week's end follows
            g = gap_at(d, b)
            if abs(g - prev) > CENT:
                weeks.append({"from": (last + dt.timedelta(days=1)).isoformat(), "to": d.isoformat(), "change": model.n2(g - prev), "gap": model.n2(g)})
            prev, last, mark = g, d, d
        return _settled(weeks)
    gap = gap_at(today, Decimal(a["balance"]))
    accepted = db.get_setting(OK + str(a["id"]))
    # the past week's ones the balance does not show yet, when they are the whole of the gap
    waiting = _waiting([t for t in tx if (today - t["day"]).days <= WAIT_DAYS], gap, sign) if abs(gap) > CENT else []
    if abs(gap) <= CENT:
        status = "ok"
    elif waiting:
        status = "waiting"
    elif accepted is not None and abs(gap - Decimal(accepted)) <= CENT:
        status = "accepted"
    else:
        status = "gap"
    out.update(status=status, gap=model.n2(gap), weeks=appeared() if status == "gap" else [],
               waiting=[{"id": t["id"], "day": t["day"].isoformat(), "amount": model.n2(t["amount"]), "name": t["merchant"] or t["description"] or ""}
                        for t in sorted(waiting, key=lambda t: (t["day"], t["id"]))],
               **{"from": start.isoformat()}, opening=model.n2(first["balance"]),
               moved=model.n2(sum((Decimal(t["amount"]) for t in tx), Decimal(0))), count=len(tx))
    return out


def _settled(weeks: list[dict]) -> list[dict]:
    """The weeks in which the gap appeared, without the runs that cancel out (a transaction dated a day before or
    after the balance moved: a gap one week, its opposite in a later one); the gap after each as it then stands."""
    out, i, total = [], 0, Decimal(0)
    while i < len(weeks):
        run, hit = Decimal(0), None
        for j in range(i, len(weeks)):
            if (dt.date.fromisoformat(weeks[j]["to"]) - dt.date.fromisoformat(weeks[i]["from"])).days > RUN_DAYS:
                break
            run += Decimal(str(weeks[j]["change"]))
            if j > i and abs(run) <= CENT:
                hit = j
                break
        if hit is not None:
            i = hit + 1
            continue
        total += Decimal(str(weeks[i]["change"]))
        out.append({**weeks[i], "gap": model.n2(total)})
        i += 1
    return out


def check(u: dict, days: int = DAYS) -> dict:
    """{items: each account checked ({id, name, status: ok | waiting (the gap is exactly some of the past week's
    transactions, not in the bank's balance yet) | accepted | gap | unknown (too little balance history), gap,
    waiting: those transactions ({id, day, amount, name}), from, to, opening, balance, moved, count, weeks: when a
    gap appeared}), gaps: how many are off}; the ones off first."""
    days = max(14, min(int(days or DAYS), 400))
    items = [_check(a, days) for a in _accounts(u)]
    order = {"gap": 0, "unknown": 1, "accepted": 2, "waiting": 3, "ok": 4}
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
