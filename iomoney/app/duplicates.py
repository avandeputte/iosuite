"""Likely duplicates: the same transaction kept twice.

It happens when a transaction typed in by hand also comes from Monarch Money, when a file is imported over what was
there, or when a pending transaction stays beside the one that posted. Two transactions look like one when they are
in the same account, of the same amount, at most DAYS apart, and alike: the same payee or bank's text, or one typed in
(or imported) and the other from Monarch, or one pending and the other not. Nothing is removed by itself: a person
keeps one and hides (or, typed in here, deletes) the other, or says they are two (mny_duplicate_nots)."""
import datetime as dt
import re

from iosuite_shared.errors import Invalid

from app import db, model

DAYS = 3        # how far apart the two may be
BACK_DAYS = 400  # how far back to look
LIMIT = 100     # groups shown


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _alike(a: dict, b: dict) -> str | None:
    """Why two transactions of the same account and amount look like one, or None."""
    if a["pending"] != b["pending"]:
        return "pending"
    if a["source"] != b["source"]:
        return "typed"
    names = lambda t: {x for x in (_norm(t["merchant"]), _norm(t["description"])) if x}  # noqa: E731
    return "same" if names(a) & names(b) else None


WHY = {"pending": "One is pending, the other posted", "typed": "One was added here, the other came from Monarch Money",
       "same": "The same payee, amount and nearly the same day"}


def groups(u: dict, limit: int = LIMIT) -> list[dict]:
    """[{why, whyText, items: the transactions (as the lists give them), the oldest first}], the latest first."""
    if model.role_rank(u) < 1:
        return []
    vis, args = model._visible(u)
    rows = db.q(f"SELECT t.*, a.owner_id, a.name AS account_name, a.currency, "
                f"EXISTS (SELECT 1 FROM mny_reconciled r WHERE r.transaction_id = t.id) AS reconciled "
                f"FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE {vis} AND a.track = 'transactions' "
                f"AND t.hidden = 0 AND t.day >= %s ORDER BY t.account_id, t.amount, t.day, t.id",
                (*args, dt.date.today() - dt.timedelta(days=BACK_DAYS)))
    nots = {(r["a_id"], r["b_id"]) for r in db.q("SELECT a_id, b_id FROM mny_duplicate_nots")}
    halves = {x for r in db.q("SELECT out_id, in_id FROM mny_transfers") for x in (r["out_id"], r["in_id"])}
    out, i = [], 0
    while i < len(rows):
        j = i + 1
        while j < len(rows) and rows[j]["account_id"] == rows[i]["account_id"] and rows[j]["amount"] == rows[i]["amount"]:
            j += 1
        same = rows[i:j]  # one account, one amount, by day
        i = j
        if len(same) < 2 or not same[0]["amount"]:
            continue
        used: set = set()
        for n, a in enumerate(same):
            if a["id"] in used:
                continue
            group, why = [a], None
            for b in same[n + 1:]:
                if (b["day"] - group[-1]["day"]).days > DAYS:
                    break
                if b["id"] in used or (min(a["id"], b["id"]), max(a["id"], b["id"])) in nots:
                    continue
                w = _alike(a, b)
                # two halves of transfers, each linked to its own other half, are two transfers of the same amount
                if w and not (a["id"] in halves and b["id"] in halves):
                    group.append(b)
                    why = why or w
            if len(group) > 1:
                used.update(t["id"] for t in group)
                out.append({"why": why, "whyText": WHY[why], "_day": group[-1]["day"], "items": group})
    out.sort(key=lambda g: g["_day"], reverse=True)
    out = out[:max(1, min(int(limit), 500))]
    flat = model.with_transfers([model.tx_public(t, u) for g in out for t in g["items"]], u)
    by_id = {t["id"]: t for t in flat}
    return [{"why": g["why"], "whyText": g["whyText"], "items": [by_id[t["id"]] for t in g["items"]]} for g in out]


def count(u: dict) -> int:
    return len(groups(u, 500))


def dismiss(u: dict, ids) -> dict:
    """{ids: [...]}: these transactions are not one kept twice; not offered again."""
    if not isinstance(ids, list) or len(ids) < 2 or len(ids) > 20:
        raise Invalid("ids: the transactions that are not duplicates (two and more)")
    ts = [model.transaction(u, i) for i in ids]
    model._need(all(model.can_write(u, t) for t in ts))
    got = sorted(t["id"] for t in ts)
    db.many("INSERT IGNORE INTO mny_duplicate_nots (a_id, b_id) VALUES (%s, %s)",
            [(a, b) for n, a in enumerate(got) for b in got[n + 1:]])
    return {"ok": True}
