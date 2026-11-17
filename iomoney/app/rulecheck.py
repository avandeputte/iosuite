"""Keeping the rules in order: what each one does to the transactions there are, the ones that do nothing, and the
rules a person seems to be missing.

For every rule: how many transactions it is for, for how many of them it is the rule that decides something (the first
one that renames, categorizes or hides wins), and the last day it was for one. A rule that is for nothing, or always
behind an earlier one, says so. And when a person gave the same payee the same category by hand several times and no
rule does that, the rule is suggested (once: one turned down is not offered again, mny_rule_nots)."""
import datetime as dt

from iosuite_shared import users as shared_users

from app import db, model

BACK_DAYS = 730
SUGGEST_AT = 3     # this many hand-categorized transactions of one payee in one category
SUGGEST_SHARE = 0.8  # and that share of the payee's hand-categorized ones
NEVER, BEHIND, OFF = "never", "behind", "off"
NOTES = {NEVER: "Matches none of the transactions of the past two years", BEHIND: "An earlier rule always decides first",
         OFF: "Turned off"}


def _key(payee: str, cat: str) -> str:
    return f"{payee.lower()}|{cat.lower()}"[:400]


def _made(r: dict, t: dict) -> bool:
    """Whether a transaction carries the name a rule gives: the rule renamed it (a rule that looks at the payee no
    longer matches the name it replaced, and would look as if it did nothing)."""
    return bool(r["set_merchant"]) and model._matches({**r, "field": "merchant", "how": "is", "pattern": r["set_merchant"].strip()}, t)


def upkeep(u: dict) -> dict:
    """{rules: [{id, matched, decides, last, note: never | behind | off, noteText}], suggestions: [{key, payee,
    category, count, wouldChange}], days}."""
    if model.role_rank(u) < 1:
        return {"rules": [], "suggestions": [], "days": BACK_DAYS}
    rs = db.q("SELECT * FROM mny_rules ORDER BY position, id")
    vis, args = model._visible(u)
    rows = db.q("SELECT t.id, t.account_id, t.day, t.amount, t.merchant, t.description, t.category, t.edited, "
                "EXISTS (SELECT 1 FROM mny_splits s WHERE s.transaction_id = t.id) AS split, "
                "EXISTS (SELECT 1 FROM mny_transfers x WHERE x.out_id = t.id OR x.in_id = t.id) AS transfer "
                f"FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE {vis} AND a.track = 'transactions' AND t.day >= %s",
                (*args, dt.date.today() - dt.timedelta(days=BACK_DAYS)))
    stat = {r["id"]: {"matched": 0, "decides": 0, "last": None} for r in rs}
    on = [r for r in rs if r["enabled"]]
    for t in rows:
        renamed = next((r for r in on if r["set_merchant"] and (model._matches(r, t) or _made(r, t))), None)
        name = renamed["set_merchant"] if renamed else None
        done = {"category": False, "hidden": False}
        for r in on:
            if not (model._matches(r, t, name) or _made(r, t)):
                continue
            s = stat[r["id"]]
            s["matched"] += 1
            if s["last"] is None or t["day"] > s["last"]:
                s["last"] = t["day"]
            decides = r is renamed
            if r["set_category"] and not done["category"]:
                done["category"] = decides = True
            if r["set_hidden"] is not None and not done["hidden"]:
                done["hidden"] = decides = True
            if decides:
                s["decides"] += 1
    out = []
    for r in rs:
        s = stat[r["id"]]
        note = OFF if not r["enabled"] else NEVER if not s["matched"] else BEHIND if not s["decides"] else None
        out.append({"id": r["id"], "matched": s["matched"], "decides": s["decides"], "last": s["last"].isoformat() if s["last"] else None,
                    "note": note, "noteText": NOTES.get(note)})
    # the rules a person seems to be missing: the same payee given the same category by hand, again and again
    nots = {r["k"] for r in db.q("SELECT k FROM mny_rule_nots")}
    by: dict = {}
    for t in rows:
        payee = (t["merchant"] or t["description"] or "").strip()
        if payee:
            by.setdefault(payee.lower(), {"payee": payee, "rows": []})["rows"].append(t)
    sug = []
    for p in by.values():
        hand: dict = {}
        for t in p["rows"]:
            if t["edited"] and t["category"] and not t["split"] and not t["transfer"]:
                hand[t["category"]] = hand.get(t["category"], 0) + 1
        if not hand:
            continue
        cat, n = max(hand.items(), key=lambda x: x[1])
        if n < SUGGEST_AT or n < SUGGEST_SHARE * sum(hand.values()) or _key(p["payee"], cat) in nots:
            continue
        if model._rule_changes(on, p["rows"][0]).get("category") == cat:
            continue  # a rule does that already
        sug.append({"key": _key(p["payee"], cat), "payee": p["payee"], "category": cat, "count": n,
                    "wouldChange": sum(1 for t in p["rows"] if not t["edited"] and t["category"] != cat)})
    sug.sort(key=lambda x: (-x["count"], x["payee"].lower()))
    return {"rules": out, "suggestions": sug[:30], "days": BACK_DAYS, "writable": shared_users.can_write(u)}


def dismiss(u: dict, key) -> dict:
    """{key}: a suggested rule is not wanted; not offered again."""
    model._need(shared_users.can_write(u), "Only editors change the rules")
    k = model.text(key, 400, "key")
    if k:
        db.ex("INSERT IGNORE INTO mny_rule_nots (k) VALUES (%s)", (k,))
    return {"ok": True}
