"""The household's transaction categories, managed here: added, renamed, moved to another group, merged into another,
deleted (its transactions moved to another category or left without one).

A category is one the transactions have (Monarch's, or one set here) or one added here (mny_categories, with its
group). A rename, a merge or a delete is remembered (mny_category_alias), so what Monarch Money sends later under the
old name comes in under the new one, in its group here; Monarch itself is not changed. The rules and the recurring
transactions that set the old name take the new one too. Editors change the categories; everyone with a role sees them.
"""
from iosuite_shared import users as shared_users
from iosuite_shared.errors import Invalid

from app import db, model

LIMIT = 128


def maps() -> tuple[dict, dict]:
    """({old name: new name or None}, {name: group}): what a sync applies to the categories it brings in."""
    alias = {r["old"]: r["new"] for r in db.q("SELECT old, new FROM mny_category_alias")}
    groups = {r["name"]: r["grp"] for r in db.q("SELECT name, grp FROM mny_categories")}
    return alias, groups


def mapped(name: str | None, group: str | None, alias: dict, groups: dict) -> tuple[str | None, str | None]:
    """A category (and its group) as it is called here."""
    for _ in range(10):  # a chain of renames
        if name in alias:
            name = alias[name]
        else:
            break
    if not name:
        return None, None
    return name, groups.get(name, group)


def items(u: dict) -> list[dict]:
    """Every category, with its group and how many of the transactions this person sees have it: [{category, group,
    count, kept (added or changed here)}], by group and name."""
    if model.role_rank(u) < 1:
        return []
    where, args = model._visible(u)
    rows = db.q(f"SELECT t.category, MAX(t.category_group) AS grp, count(*) AS n FROM mny_transactions t "
                f"JOIN mny_accounts a ON a.id = t.account_id WHERE {where} AND a.track = 'transactions' "
                f"AND t.category IS NOT NULL GROUP BY t.category", args)
    out = {r["category"]: {"category": r["category"], "group": r["grp"], "count": r["n"], "kept": False} for r in rows}
    for r in db.q(f"SELECT s.category, MAX(s.category_group) AS grp, count(*) AS n FROM mny_splits s "
                  f"JOIN mny_transactions t ON t.id = s.transaction_id JOIN mny_accounts a ON a.id = t.account_id "
                  f"WHERE {where} AND a.track = 'transactions' AND s.category IS NOT NULL GROUP BY s.category", args):
        c = out.setdefault(r["category"], {"category": r["category"], "group": r["grp"], "count": 0, "kept": False})
        c["count"] += r["n"]  # the parts of split transactions
    for r in db.q("SELECT name, grp FROM mny_categories"):
        c = out.setdefault(r["name"], {"category": r["name"], "group": None, "count": 0, "kept": True})
        c["kept"] = True
        if r["grp"]:
            c["group"] = r["grp"]
    return sorted(out.values(), key=lambda c: ((c["group"] or "~").lower(), c["category"].lower()))


def _name(v, what: str = "The name") -> str:
    n = model.text(v, LIMIT, what)
    if not n:
        raise Invalid("Give the category a name")
    return n


def _exists(name: str) -> bool:
    return bool(db.one("SELECT 1 AS x FROM mny_categories WHERE name = %s", (name,))
                or db.one("SELECT 1 AS x FROM mny_transactions WHERE category = %s LIMIT 1", (name,))
                or db.one("SELECT 1 AS x FROM mny_splits WHERE category = %s LIMIT 1", (name,)))


def _group_now(name: str) -> str | None:
    r = db.one("SELECT grp FROM mny_categories WHERE name = %s", (name,))
    if r and r["grp"]:
        return r["grp"]
    r = db.one("SELECT category_group AS g, count(*) AS n FROM mny_transactions WHERE category = %s AND category_group IS NOT NULL "
               "GROUP BY category_group ORDER BY n DESC LIMIT 1", (name,))
    return r["g"] if r else None


def _need_editor(u: dict) -> None:
    model._need(shared_users.can_write(u), "Only editors change the categories")


def add(u: dict, b: dict) -> dict:
    _need_editor(u)
    name = _name(b.get("name"))
    if _exists(name):
        raise Invalid("There is a category with that name already")
    grp = model.text(b.get("group"), LIMIT, "The group")
    db.ex("INSERT INTO mny_categories (name, grp) VALUES (%s, %s)", (name, grp))
    db.ex("DELETE FROM mny_category_alias WHERE old = %s", (name,))  # a name given up before, taken again
    return {"category": name, "group": grp}


def _move(old: str, new: str | None, grp: str | None) -> int:
    """Every transaction, rule and recurring transaction with category old takes new (in group grp); how many
    transactions."""
    n = db.one("SELECT count(*) AS n FROM mny_transactions WHERE category = %s", (old,))["n"]
    db.ex("UPDATE mny_transactions SET category = %s, category_group = %s, "
          "words = TRIM(REPLACE(CONCAT(' ', words, ' '), CONCAT(' ', %s, ' '), CONCAT(' ', %s, ' '))) WHERE category = %s",
          (new, grp if new else None, model.words(old), model.words(new) if new else "", old))
    db.ex("UPDATE mny_splits SET category = %s, category_group = %s WHERE category = %s", (new, grp if new else None, old))
    db.ex("UPDATE mny_rules SET set_category = %s WHERE set_category = %s", (new, old))
    db.ex("UPDATE mny_recurring SET category = %s WHERE category = %s", (new, old))
    # what a sync brings in later under the old name (or under a name that became the old one)
    db.ex("UPDATE mny_category_alias SET new = %s WHERE new = %s", (new, old))
    db.ex("INSERT INTO mny_category_alias (old, new) VALUES (%s, %s) ON DUPLICATE KEY UPDATE new = VALUES(new)", (old, new))
    if new:
        db.ex("DELETE FROM mny_category_alias WHERE old = %s", (new,))
    return n


def change(u: dict, b: dict) -> dict:
    """{name, newName?, group?}: rename it (into one there is already: merged), or move it to another group."""
    _need_editor(u)
    old = _name(b.get("name"), "The category")
    if not _exists(old):
        raise model.NotFound("No such category")
    new = _name(b["newName"]) if b.get("newName") else old
    grp = model.text(b["group"], LIMIT, "The group") if "group" in b else (_group_now(new) if new != old and _exists(new) else _group_now(old))
    with db.tx():
        moved = 0
        if new != old:
            moved = _move(old, new, grp)
            db.ex("DELETE FROM mny_categories WHERE name = %s", (old,))
        db.ex("INSERT INTO mny_categories (name, grp) VALUES (%s, %s) ON DUPLICATE KEY UPDATE grp = VALUES(grp)", (new, grp))
        db.ex("UPDATE mny_transactions SET category_group = %s WHERE category = %s", (grp, new))
        db.ex("UPDATE mny_splits SET category_group = %s WHERE category = %s", (grp, new))
    return {"category": new, "group": grp, "moved": moved}


def delete(u: dict, b: dict) -> dict:
    """{name, moveTo?}: its transactions (and rules, recurring transactions) take moveTo, or no category."""
    _need_editor(u)
    old = _name(b.get("name"), "The category")
    if not _exists(old):
        raise model.NotFound("No such category")
    to = model.text(b.get("moveTo"), LIMIT, "The other category")
    if to == old:
        raise Invalid("Move them to another category")
    if to and not _exists(to):
        raise Invalid("Move them to one of the categories")
    with db.tx():
        moved = _move(old, to, _group_now(to) if to else None)
        db.ex("DELETE FROM mny_categories WHERE name = %s", (old,))
    return {"moved": moved}
