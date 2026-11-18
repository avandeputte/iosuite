"""The balance check: does what the bank says an account holds agree with the transactions kept here?

Monarch Money reports each account's balance day by day, and its transactions. Over a stretch of days the balance
should move by exactly what the transactions add up to. Where it does not, something is missing or there twice: a
transaction the bank link dropped, one kept twice, one hidden in Monarch (those are not kept here), an account whose
link was cut for a while. This looks at the cash accounts and the cards from Monarch Money that have a bank behind
them and follow their transactions, and says for each whether it agrees, and if not by how much and in which week
the gap appeared. Pending transactions explain a gap of exactly their sum (some banks count them in the balance,
some do not). A day's balance may not hold that day's transactions yet, so the check starts a few days earlier or
later where its first week then agrees. One Monarch still calls pending after more than a week is no longer a hold:
the bank took it long ago (Monarch never marked it posted) or it is the leftover of one that posted under another
id. Which of the two, the balance tells: it is counted with the posted ones where that explains the gap, or what the
gap grew by in its week, to the cent, and named either way (stale). A transaction dated a day before or after the
balance moved shows as a gap in one week and its opposite in a later one: weeks that cancel out are left out of
where the gap appeared. A gap a person looked at and accepts is not flagged again while it stays the same."""
import datetime as dt
import itertools
from decimal import Decimal

from iosuite_shared.errors import Invalid

from app import db, model

DAYS = 90
EDGE_DAYS = 3    # the day the check starts on may be a few days earlier or later, where that makes its first week agree
STALE_DAYS = 7   # pending for longer than this: no longer a hold
RUN_DAYS = 45    # weeks whose changes cancel out within this many days are a matter of dates, not a gap
MAX_STALE = 12   # of them are looked at (every combination of them is tried)
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
        moved = sum((Decimal(t["amount"]) for t in tx if not t["pending"] and b["day"] < t["day"] <= end[0]), Decimal(0))
        return abs((end[1] - Decimal(b["balance"])) - sign * moved)
    if off(first) <= CENT:
        return first
    near = sorted((b for b in bal if b["day"] != first["day"] and abs((b["day"] - first["day"]).days) <= EDGE_DAYS),
                  key=lambda b: (abs((b["day"] - first["day"]).days), b["day"]))
    return next((b for b in near if off(b) <= CENT), first)


def _taken(old: list[dict], gap: Decimal, sign: Decimal, weeks: list[dict]) -> list[dict]:
    """Which of the transactions still called pending after more than a week the bank took: those that add up to
    exactly the gap, or else to exactly what the gap grew by in the week of their day (or the one after). One that
    explains nothing to the cent is left out: what is left of one that posted under another entry, or a hold let go."""
    def exactly(items: list[dict], target: Decimal) -> list[dict]:
        for n in range(1, len(items) + 1):
            for some in itertools.combinations(items, n):
                if abs(sign * sum((Decimal(t["amount"]) for t in some), Decimal(0)) - target) <= CENT:
                    return list(some)
        return []
    items = sorted(old, key=lambda t: -abs(Decimal(t["amount"])))[:MAX_STALE]
    if abs(gap) <= CENT:
        return []
    out = exactly(items, gap)
    if out:
        return out
    for w in weeks:
        lo, hi = dt.date.fromisoformat(w["from"]) - dt.timedelta(days=7), dt.date.fromisoformat(w["to"])
        out += exactly([t for t in items if lo <= t["day"] <= hi and not any(t is x for x in out)], Decimal(str(w["change"])))
    return out


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
    tx = db.q("SELECT id, day, amount, pending, merchant, description FROM mny_transactions WHERE account_id = %s AND day > %s AND day <= %s "
              "ORDER BY day", (a["id"], first["day"] - dt.timedelta(days=EDGE_DAYS), today))
    first = _start(first, bal, tx, sign, today, Decimal(a["balance"]))
    start = first["day"]
    tx = [t for t in tx if t["day"] > start]
    posted = [t for t in tx if not t["pending"]]
    old = [t for t in tx if t["pending"] and (today - t["day"]).days > STALE_DAYS]
    pending = sum((Decimal(t["amount"]) for t in tx if t["pending"] and (today - t["day"]).days <= STALE_DAYS), Decimal(0))
    points = [(x["day"], Decimal(x["balance"])) for x in bal if start < x["day"] < today] + [(today, Decimal(a["balance"]))]

    def gap_at(day: dt.date, balance: Decimal) -> Decimal:
        moved = sum((Decimal(t["amount"]) for t in posted if t["day"] <= day), Decimal(0))
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
    # the ones still called pending after more than a week: counted where the balance says the bank took them
    taken = _taken(old, gap_at(today, Decimal(a["balance"])), sign, appeared()) if old else []
    posted += taken
    stale = [{"id": t["id"], "day": t["day"].isoformat(), "amount": model.n2(t["amount"]), "name": t["merchant"] or t["description"] or "",
              "days": (today - t["day"]).days, "counted": any(t is x for x in taken)} for t in old]
    gap = gap_at(today, Decimal(a["balance"]))
    weeks = appeared()
    accepted = db.get_setting(OK + str(a["id"]))
    if abs(gap) <= CENT:
        status = "ok"
    elif pending and abs(gap - sign * pending) <= CENT:
        status = "pending"
    elif accepted is not None and abs(gap - Decimal(accepted)) <= CENT:
        status = "accepted"
    else:
        status = "gap"
    out.update(status=status, gap=model.n2(gap), pending=model.n2(pending), weeks=weeks if status == "gap" else [], stale=stale[:MAX_STALE],
               **{"from": start.isoformat()}, opening=model.n2(first["balance"]),
               moved=model.n2(sum((Decimal(t["amount"]) for t in posted), Decimal(0))), count=len(posted))
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
    """{items: each account checked ({id, name, status: ok | pending (the pending ones of the past week explain it) |
    accepted | gap | unknown (too little balance history), gap, pending: what is pending from the past week, stale:
    the ones still called pending after more than a week ({id, day, amount, name, days, counted: with the posted
    ones, as the balance says the bank took it}), from, to, opening, balance, moved, count, weeks: when a gap
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
