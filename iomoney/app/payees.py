"""The payees: every name the transactions were paid to or came from, with how many and how much, and the way to put
them in order.

A payee renamed here (or merged into another: the same thing) is renamed in every transaction that has it, and a rule
is kept ("the payee is Old: call it New") so that what Monarch Money sends later under the old name comes in under the
new one. A payee's usual category is a rule too ("the payee is Name: its category is Groceries"), tried before the
other rules. Both are the household's rules (app/model.py): editors make them, and they show on the Rules page."""
from iosuite_shared import users as shared_users
from iosuite_shared.errors import Invalid

from app import db, model

LIMIT = 500


def items(u: dict, q: str = "", limit: int = LIMIT) -> dict:
    """{items: [{payee, field: merchant or description (which of the two the name is), count, total, last,
    category: its most common one, categories: how many different ones, rule: the rule that sets its category}],
    total: how many payees}, the most used first. q: words in the name."""
    if model.role_rank(u) < 1:
        return {"items": [], "total": 0}
    vis, args = model._visible(u)
    name = "COALESCE(NULLIF(t.merchant, ''), t.description)"
    base = (f"FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE {vis} AND a.track = 'transactions' "
            f"AND t.hidden = 0 AND {name} IS NOT NULL AND {name} <> ''")
    for w in (q or "").lower().split()[:6]:
        base += f" AND LOWER({name}) LIKE %s"
        args.append("%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    total = db.one(f"SELECT count(DISTINCT {name}) AS n {base}", args)["n"]
    rows = db.q(f"SELECT {name} AS payee, MAX(t.merchant IS NOT NULL AND t.merchant <> '') AS named, count(*) AS n, "
                f"COALESCE(SUM(t.amount), 0) AS s, MAX(t.day) AS last {base} GROUP BY payee ORDER BY n DESC, payee LIMIT %s",
                (*args, max(1, min(int(limit), 2000))))
    cats: dict = {}
    for r in db.q(f"SELECT {name} AS payee, t.category, count(*) AS n {base} GROUP BY payee, t.category", args):
        cats.setdefault(r["payee"].lower(), []).append((r["n"], r["category"]))
    rules = {(r["pattern"] or "").lower(): r for r in db.q("SELECT * FROM mny_rules WHERE enabled = 1 AND how = 'is' AND set_category IS NOT NULL "
                                                            "AND account_id IS NULL AND flow IS NULL AND amount_min IS NULL AND amount_max IS NULL ORDER BY position DESC, id DESC")}
    out = []
    for r in rows:
        c = sorted(cats.get(r["payee"].lower(), []), key=lambda x: (-x[0], x[1] or ""))
        rule = rules.get(r["payee"].lower())
        out.append({"payee": r["payee"], "field": "merchant" if r["named"] else "description", "count": r["n"], "total": model.n2(r["s"]),
                    "last": r["last"].isoformat(), "category": c[0][1] if c else None, "categories": len(c),
                    "rule": {"id": rule["id"], "category": rule["set_category"]} if rule else None})
    return {"items": out, "total": total}


def _editors(u: dict) -> None:
    model._need(shared_users.can_write(u), "Only editors put the payees in order")


def _first_position() -> int:
    return (db.one("SELECT COALESCE(MIN(position), 1) AS p FROM mny_rules")["p"] or 1) - 1


def _ids(name: str) -> list[int]:
    """The transactions whose payee is name (the payee's name, or the bank's text when it has none)."""
    return [r["id"] for r in db.q("SELECT id FROM mny_transactions WHERE merchant = %s OR ((merchant IS NULL OR merchant = '') AND description = %s)", (name, name))]


def rename(u: dict, b: dict) -> dict:
    """{name, newName}: the payee under another name, in every transaction that has it (those changed by hand too),
    and from now on (a rule). A name another payee has: the two are one. {changed, rule}."""
    from app import splits
    _editors(u)
    old, new = model.text(b.get("name"), 255, "The payee"), model.text(b.get("newName"), 255, "The new name")
    if not old or not new:
        raise Invalid("Give the payee and its new name")
    if old == new:
        raise Invalid("That is its name already")
    ids = _ids(old)
    field = "merchant" if db.one("SELECT 1 AS x FROM mny_transactions WHERE merchant = %s LIMIT 1", (old,)) else "description"
    with db.tx():
        # the rules that already made something into this payee now make it into the new name
        db.ex("UPDATE mny_rules SET set_merchant = %s WHERE set_merchant = %s", (new, old))
        r = db.one("SELECT id FROM mny_rules WHERE field = %s AND how = 'is' AND pattern = %s AND set_merchant IS NOT NULL "
                   "AND account_id IS NULL AND flow IS NULL AND amount_min IS NULL AND amount_max IS NULL", (field, old))
        if r:
            db.ex("UPDATE mny_rules SET set_merchant = %s, enabled = 1 WHERE id = %s", (new, r["id"]))
            rid = r["id"]
        else:
            rid = db.ex("INSERT INTO mny_rules (position, field, how, pattern, set_merchant, created_by) VALUES (%s, %s, 'is', %s, %s, %s)",
                        (_first_position(), field, old, new, u["id"]))
        # a rule that renames the new name back to the old one would undo this at once
        db.ex("DELETE FROM mny_rules WHERE how = 'is' AND pattern = %s AND set_merchant = %s AND set_category IS NULL AND set_hidden IS NULL", (new, new))
        if ids:
            db.ex(f"UPDATE mny_transactions SET merchant = %s WHERE id IN ({db.marks(len(ids))})", (new, *ids))
    for i in ids:
        splits.rewords(i)
    return {"changed": len(ids), "rule": rid}


def set_category(u: dict, b: dict) -> dict:
    """{name, category, all?}: the payee's usual category, from now on (a rule, tried before the others) and for its
    transactions there are: those not changed by hand, or all of them with all. {changed, rule}."""
    from app import splits, transfers
    _editors(u)
    name, cat = model.text(b.get("name"), 255, "The payee"), model.text(b.get("category"), 128, "The category")
    if not name or not cat:
        raise Invalid("Give the payee and its category")
    ids = _ids(name)
    field = "merchant" if db.one("SELECT 1 AS x FROM mny_transactions WHERE merchant = %s LIMIT 1", (name,)) else "description"
    r = db.one("SELECT id FROM mny_rules WHERE field IN (%s, 'either') AND how = 'is' AND pattern = %s AND set_category IS NOT NULL "
               "AND account_id IS NULL AND flow IS NULL AND amount_min IS NULL AND amount_max IS NULL ORDER BY position LIMIT 1", (field, name))
    if r:
        db.ex("UPDATE mny_rules SET set_category = %s, enabled = 1, position = %s WHERE id = %s", (cat, _first_position(), r["id"]))
        rid = r["id"]
    else:
        rid = db.ex("INSERT INTO mny_rules (position, field, how, pattern, set_category, created_by) VALUES (%s, %s, 'is', %s, %s, %s)",
                    (_first_position(), field, name, cat, u["id"]))
    changed = 0
    if ids:
        marks = db.marks(len(ids))
        grp = model._group_of_category(cat)
        if model.flag(b.get("all")):  # those changed by hand too, unless they are split
            changed = db.ex(f"UPDATE mny_transactions t SET t.category = %s, t.category_group = %s WHERE t.id IN ({marks}) "
                            f"AND (t.category IS NULL OR t.category <> %s) AND {splits.WHOLE}", (cat, grp, *ids, cat)) or 0
        else:
            changed = model.apply_rules(f"t.id IN ({marks})", ids)
        for i in ids:
            splits.rewords(i)
        transfers.link(f"t.id IN ({marks})", ids)
    return {"changed": changed, "rule": rid}
