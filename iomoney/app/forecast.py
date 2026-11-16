"""The cash forecast: where an account's balance goes over the coming weeks, from what is known to come back: the
household's recurring transactions in that account (bills, subscriptions, paychecks: app/recurring.py) and the
transfers it makes at a steady pace (a card paid every month, money moved to savings), each on the days its pace
gives from its last payment. With the balance the account should not go under (its details.floor; zero as left out),
the forecast says whether and when it would.

What it cannot know is left out and said so: recurring transactions kept for "any account", and everyday spending
(groceries, fuel), so the forecast is the most the account will hold, not a promise."""
import datetime as dt
import statistics
from decimal import Decimal

from app import db, model, recurring

DAYS = 60
LOOK = 200          # days of transfers looked at for the ones made at a steady pace
LATE = 5            # one due this many days ago at most, not seen yet, is still expected (today)


def _next_days(last: dt.date | None, r: dict, today: dt.date, end: dt.date) -> list[tuple[dt.date, bool]] | None:
    """The days a recurring transaction (its frequency and day) is still to come from today to end, as (day, late):
    counted on from its last payment when it has one (so a date that drifts does not count a paid one again), a
    payment a few days late expected today. None when its payment did not come for longer than that (missed, flagged
    on the Recurring page): it is not assumed to come back."""
    freq, dom = r["frequency"], r["day"].day
    if not last:
        return [(d, False) for d in recurring.dates(r, today, end)]
    out, d = [], last
    lo = recurring.BANDS[freq][0]
    for _ in range(400):
        d = recurring._step(d, freq, 1, dom if freq in recurring.MONTHS else d.day)
        if d > end:
            break
        if (d - last).days < lo / 2:
            continue  # paid early: this date is the one already paid
        if d >= today:
            out.append((d, False))
        elif (today - d).days <= LATE + recurring.GRACE.get(freq, 5):
            out.append((today, True))
        else:
            return None
    return out


def _recurring(a: dict, today: dt.date, end: dt.date) -> tuple[list[dict], list[dict], list[str]]:
    """(the events of the recurring transactions kept for this account, those rows, the names of those left out:
    their payment did not come)."""
    out, rows, left = [], db.q("SELECT * FROM mny_recurring WHERE account_id = %s ORDER BY name", (a["id"],)), []
    for r in rows:
        paid = recurring._payments(r, today - dt.timedelta(days=recurring.LOOK_BACK), today)
        sign = -1 if r["flow"] == "out" else 1
        ds = _next_days(paid[-1]["day"] if paid else None, r, today, end)
        if ds is None:
            left.append(r["name"])
            continue
        for d, late in ds:
            out.append({"day": d, "name": r["name"], "amount": sign * Decimal(r["amount"]), "approximate": bool(r["approximate"]),
                        "kind": "subscription" if r["subscription"] else "recurring", "late": late, "recurringId": r["id"]})
    return out, rows, left


def _transfers(a: dict, kept: list[dict], today: dt.date, end: dt.date) -> list[dict]:
    """The transfers this account makes or gets at a steady pace (three and more, the last one recent), not already
    among its recurring transactions: the usual amount (the middle one of the last three) on the days their pace gives."""
    rows = db.q("SELECT t.id, t.account_id, t.day, t.amount, t.merchant, t.description, o.account_id AS other_id, oa.name AS other_name "
                "FROM mny_transactions t JOIN mny_transfers x ON x.out_id = t.id OR x.in_id = t.id "
                "JOIN mny_transactions o ON o.id = IF(x.out_id = t.id, x.in_id, x.out_id) JOIN mny_accounts oa ON oa.id = o.account_id "
                "WHERE t.account_id = %s AND t.hidden = 0 AND t.day BETWEEN %s AND %s ORDER BY t.day",
                (a["id"], today - dt.timedelta(days=LOOK), today))
    by: dict = {}
    for t in rows:
        by.setdefault((t["other_id"], t["amount"] < 0), []).append(t)
    out = []
    for (_other, is_out), ts in by.items():
        days = sorted({t["day"] for t in ts})
        freq = recurring._cadence(days) if len(days) >= 3 else None
        if not freq or (today - days[-1]).days > recurring.BANDS[freq][1] * 1.5 + 5:
            continue
        last = ts[-1]
        if any(recurring._hits(r, last) for r in kept):
            continue  # kept as a recurring transaction (a loan's payment): counted there
        amts = [abs(Decimal(t["amount"])) for t in ts[-3:]]
        amount = Decimal(statistics.median(amts)).quantize(model.CENT)
        r = {"frequency": freq, "day": days[-1]}
        for d, late in _next_days(days[-1], r, today, end) or []:
            out.append({"day": d, "name": f"{'To' if is_out else 'From'} {last['other_name']}", "amount": -amount if is_out else amount,
                        "approximate": max(amts) - min(amts) > amount * Decimal("0.02"), "kind": "transfer", "late": late, "recurringId": None})
    return out


def forecast(u: dict, a: dict, days: int = DAYS, today: dt.date = None) -> dict:
    """An account's balance over the coming days (60 as left out, 7 to 366): {accountId, name, currency, start (the
    balance now), days, floor (the balance it should not go under, or None), events: [{day, name, amount, approximate,
    kind (recurring, subscription, transfer), late (due a few days ago, not seen yet: expected today), balance (after
    it)}], points: [{day, value}] (each day's closing balance), low: {day, value} (the lowest point), end, below
    (whether it goes under the floor, or under zero without one, and belowOn: the first day it does), leftOut (the
    names of the recurring transactions whose last payment did not come: not assumed to come back), unassigned (the recurring transactions
    kept for any account: not counted)}. What is owed counts as a negative balance."""
    today = today or dt.date.today()
    days = max(7, min(int(days or DAYS), 366))
    end = today + dt.timedelta(days=days)
    rec, kept, left = _recurring(a, today, end)
    events = sorted(rec + _transfers(a, kept, today, end), key=lambda e: (e["day"], -e["amount"], e["name"].lower()))
    bal = model.signed(a)
    floor = (a.get("details") or {}).get("floor")
    floor = Decimal(str(floor)) if floor is not None else None
    by_day: dict = {}
    for e in events:
        bal += e["amount"]
        e["balance"] = bal
        by_day[e["day"]] = bal
    points, cur, low, below_on = [], model.signed(a), None, None
    for n in range(days + 1):
        d = today + dt.timedelta(days=n)
        cur = by_day.get(d, cur)
        points.append({"day": d.isoformat(), "value": model.n2(cur)})
        if low is None or cur < low[1]:
            low = (d, cur)
        if below_on is None and cur < (floor if floor is not None else 0):
            below_on = d
    return {"accountId": a["id"], "name": a["name"], "currency": a["currency"], "start": model.n2(model.signed(a)), "days": days,
            "floor": model.n2(floor), "end": model.n2(cur),
            "events": [{**e, "day": e["day"].isoformat(), "amount": model.n2(e["amount"]), "balance": model.n2(e["balance"])} for e in events],
            "points": points, "low": {"day": low[0].isoformat(), "value": model.n2(low[1])},
            "below": below_on is not None, "belowOn": below_on.isoformat() if below_on else None,
            "leftOut": left, "unassigned": db.one("SELECT count(*) AS n FROM mny_recurring WHERE account_id IS NULL")["n"]}


def accounts(u: dict) -> list[dict]:
    """The cash accounts this person sees that follow their transactions (not hidden, not closed)."""
    return [a for a in model.accounts(u) if a["kind"] == "cash" and not a["closed"] and (a.get("track") or "transactions") == "transactions"]


def warnings(u: dict, days: int = 30, today: dt.date = None) -> list[dict]:
    """The cash accounts that would go under their floor (under zero without one) in the coming days: [{accountId, name, currency, floor,
    belowOn, low: {day, value}}]."""
    out = []
    for a in accounts(u):
        f = forecast(u, a, days, today)
        if f["below"]:
            out.append({k: f[k] for k in ("accountId", "name", "currency", "floor", "belowOn", "low")})
    return out
