"""A loan's payoff: with its yearly interest (details.rate, in percent) and what is paid a month (details.payment, or
worked out from how its balance went down), when it is paid off, the interest still to pay, and what paying more a
month would save. Interest is counted by the month on what is still owed, as mortgages, car and student loans do."""
import datetime as dt
from decimal import Decimal

from app import db, model, recurring

MAX_MONTHS = 1200


def schedule(balance: Decimal, rate: Decimal, payment: Decimal) -> dict | None:
    """Paying payment a month on balance at rate percent a year: {months, interest (to pay in all), last (the last
    payment)}; None when the payment does not cover the interest (it is never paid off)."""
    bal, r, interest, months = Decimal(balance), Decimal(rate) / 1200, Decimal(0), 0
    if bal <= 0:
        return {"months": 0, "interest": Decimal(0), "last": Decimal(0)}
    if payment <= 0 or payment <= bal * r:
        return None
    last = payment
    while bal > 0 and months < MAX_MONTHS:
        i = (bal * r).quantize(model.CENT)
        interest += i
        last = min(payment, bal + i)
        bal = bal + i - last
        months += 1
    return None if bal > 0 else {"months": months, "interest": interest, "last": last}


def estimated_payment(a: dict, rate: Decimal, today: dt.date) -> Decimal | None:
    """What is paid a month, from how the balance went down over the past three months (as far back as its history
    goes, a month at least) plus the interest of a month; None without that history or when it did not go down."""
    rows = db.q("SELECT day, balance FROM mny_balances WHERE account_id = %s AND day BETWEEN %s AND %s ORDER BY day",
                (a["id"], today - dt.timedelta(days=100), today))
    if not rows or (today - rows[0]["day"]).days < 25:
        return None
    first, now = abs(Decimal(rows[0]["balance"])), abs(Decimal(a["balance"]))
    months = Decimal((today - rows[0]["day"]).days) / Decimal("30.44")
    down = (first - now) / months
    if down <= 0:
        return None
    return (down + (first + now) / 2 * Decimal(rate) / 1200).quantize(model.CENT)


def _plan(balance: Decimal, rate: Decimal, payment: Decimal, today: dt.date) -> dict:
    s = schedule(balance, rate, payment)
    if not s:
        return {"payment": model.n2(payment), "never": True, "months": None, "payoff": None, "interest": None, "total": None}
    end = recurring._add_months(today, s["months"], today.day)
    return {"payment": model.n2(payment), "never": False, "months": s["months"], "payoff": end.isoformat(),
            "interest": model.n2(s["interest"]), "total": model.n2(Decimal(balance) + s["interest"])}


def payoff(u: dict, a: dict, extra=None, today: dt.date = None) -> dict:
    """{accountId, name, currency, balance (what is owed), rate, payment, paymentEstimated (worked out from the
    balance's history, not given), needs: what is missing to say more (rate, payment), never (the payment does not
    cover the interest), months, payoff (the day it is paid off), interest (still to pay), total (what is owed plus
    that interest); with extra (more paid a month): extra: {amount, payment, months, payoff, interest, total,
    savedMonths, savedInterest}}."""
    today = today or dt.date.today()
    d = a.get("details") or {}
    bal = abs(Decimal(a["balance"]))
    out = {"accountId": a["id"], "name": a["name"], "currency": a["currency"], "balance": model.n2(bal),
           "rate": d.get("rate"), "payment": d.get("payment"), "paymentEstimated": False, "needs": [], "extra": None}
    if d.get("rate") is None:
        out["needs"].append("rate")
        return out
    rate = Decimal(str(d["rate"]))
    pay = Decimal(str(d["payment"])) if d.get("payment") is not None else estimated_payment(a, rate, today)
    if pay is None:
        out["needs"].append("payment")
        return out
    out["paymentEstimated"] = d.get("payment") is None
    out.update(_plan(bal, rate, pay, today))
    more = model.money(extra, "The extra payment") if extra not in (None, "", 0, "0") else None
    if more and more > 0:
        x = _plan(bal, rate, pay + more, today)
        x["amount"] = model.n2(more)
        x["savedMonths"] = out["months"] - x["months"] if out["months"] is not None and x["months"] is not None else None
        x["savedInterest"] = model.n2(Decimal(str(out["interest"])) - Decimal(str(x["interest"]))) if out["interest"] is not None and x["interest"] is not None else None
        out["extra"] = x
    return out
