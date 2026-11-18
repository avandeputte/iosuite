"""ioMoney's answers to the suite's standard endpoints (iosuite_shared.suiteitems): payees and transactions found
(houses and cars for the linked-items picker), one house, car or transaction, and the start page's tile (the week's
bills). Only what this person sees in ioMoney: their own accounts and the household's."""
import datetime as dt
import urllib.parse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from iosuite_shared.suiteitems import Provider, item


def _zone(tz: str):
    try:
        return ZoneInfo(tz) if tz else dt.timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return dt.timezone.utc


def _asset(a: dict) -> dict:
    """A house, a car or another thing of value (an account of ioMoney): its kind and what it is worth."""
    v = a.get("estimate") if a.get("estimate") is not None else a.get("balance")
    worth = f"{a.get('currency') or ''} {float(v):,.0f}".strip() if isinstance(v, (int, float)) else ""
    return item("iomoney", "asset", a.get("id"), a.get("name"), " · ".join(x for x in (a.get("kindLabel"), worth) if x), icon="money")


def _transaction(t: dict) -> dict:
    """The payee, its day, and the amount, the category and the account."""
    return item("iomoney", "transaction", t.get("id"), t.get("merchant") or t.get("description") or "Transaction",
                " · ".join(x for x in (t.get("category"), t.get("account")) if x), t.get("day"), all_day=True, icon="receipt",
                amount=t.get("amount"), currency=t.get("currency"))


def search(local, q, n, tz, kinds):
    """The search box: the payees whose name has every word of q (the two most used: all their transactions), then
    the transactions ioMoney finds for q (the payee, the bank's text, the category, the notes; "$280" or "100-200" are
    amounts), the newest first, n rows in all. With kinds (the linked-items picker): its houses and cars, its
    transactions."""
    if kinds:
        out = []
        if "asset" in kinds:
            out += [_asset(a) for a in local.get("/api/accounts", {"things": "true", "q": q}).get("items", [])[:n]]
        if "transaction" in kinds:
            out += [_transaction(t) for t in local.get("/api/transactions", {"q": q, "limit": n}).get("items", [])[:n]]
        return out
    payees, found = local.together(lambda: local.get("/api/payees", {"q": q, "limit": 2}),
                                   lambda: local.get("/api/transactions", {"q": q, "limit": n}))
    if isinstance(found, Exception):
        raise found
    rows = [_transaction(t) for t in found.get("items", [])]
    who = []
    for p in ([] if isinstance(payees, Exception) else payees.get("items", [])[:2]):
        name = p.get("payee")
        if not name or (p.get("count") or 0) <= 1:
            continue
        # a payee's total is in the money of its transactions
        cur = next((t.get("currency") for t in rows if t["title"] == name and t.get("currency")), rows[0].get("currency") if rows else None)
        who.append(item("iomoney", "payee", name, name, f"all {p.get('count')}", p.get("last"), all_day=True, icon="money",
                        href="#/transactions?" + urllib.parse.urlencode({"q": name}), amount=p.get("total"), currency=cur,
                        category=p.get("category")))
    items = (who + rows)[:n]
    return {"items": items, "more": int(found.get("total") or 0) > len([x for x in items if x["kind"] == "transaction"])}


def get(local, kind, item_id):
    if not item_id.isdigit():
        return None
    if kind == "asset":
        return _asset(local.get(f"/api/accounts/{item_id}"))
    if kind == "transaction":
        return _transaction(local.get(f"/api/transactions/{item_id}"))
    return None


def tile(local, tz, n, kind, days: int = 7):
    """{currency, bills: [{day, name, amount, currency, approximate, account, subscription}], more, total, low:
    [{name, currency, floor, belowOn, value}], behind: [{name, institution}]}: the recurring payments not paid yet
    that fall due from the viewer's today through the next `days` days (the soonest first, up to n; more: how many are
    left out; total: what they all come to, when they are in one currency), the cash accounts the forecast sees going
    under their lowest balance in the coming 30 days, and the accounts whose link to the bank is behind."""
    n = n or 3
    today = dt.datetime.now(_zone(tz)).date()
    bills, low, summary = local.together(
        lambda: local.get("/api/bills", {"start": today.isoformat(), "end": (today + dt.timedelta(days=days)).isoformat()}),
        lambda: local.get("/api/forecast", {"days": 30}), lambda: local.get("/api/summary"))
    if isinstance(bills, Exception):
        raise bills
    due = [b for b in bills.get("items", []) if not b.get("paid") and (b.get("amount") or 0) < 0]
    monies = {b.get("currency") for b in due}
    out = {"currency": bills.get("currency"),
           "bills": [{"day": b.get("day"), "name": b.get("merchant") or "(no name)", "amount": b.get("amount"), "currency": b.get("currency"),
                      "approximate": bool(b.get("approximate")), "account": b.get("account"), "subscription": bool(b.get("subscription"))} for b in due[:n]],
           "more": max(0, len(due) - n),
           "total": round(sum(b.get("amount") or 0 for b in due), 2) if len(monies) == 1 else None,
           "low": [], "behind": []}
    if len(monies) == 1:
        out["currency"] = monies.pop() or out["currency"]
    if not isinstance(low, Exception):  # the forecast or the summary not answering leaves the bills as they are
        out["low"] = [{"name": a.get("name"), "currency": a.get("currency"), "floor": a.get("floor"), "belowOn": a.get("belowOn"),
                       "value": (a.get("low") or {}).get("value")} for a in low.get("items", [])]
    if not isinstance(summary, Exception):
        stale = ((summary.get("monarch") or {}).get("stale")) or []
        out["behind"] = [{"name": a.get("name"), "institution": a.get("institution")} for a in stale]
    return out


PROVIDER = Provider(search=search, get=get, tile=tile)
