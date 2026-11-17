"""A transaction split over categories: one charge (a warehouse club's, an online order) whose parts belong to
different categories. The transaction stays as it is (its amount, its payee, its place in the account); its parts
(mny_splits), each with its share, a category and a note, are what the spending by category counts in its place, and
what a search by category finds. A split transaction counts as changed by hand: the rules and the syncs leave its
category alone."""
from decimal import Decimal

from iosuite_shared.errors import Invalid

from app import db, model

MAX_PARTS = 30


def of(ids: list) -> dict:
    """{transaction id: its parts, in order: [{id, amount, category, group, notes}]} for the transactions given."""
    ids = [int(i) for i in ids]
    out: dict = {}
    if not ids:
        return out
    for r in db.q(f"SELECT * FROM mny_splits WHERE transaction_id IN ({db.marks(len(ids))}) ORDER BY transaction_id, position, id", ids):
        out.setdefault(r["transaction_id"], []).append({"id": r["id"], "amount": model.n2(r["amount"]), "category": r["category"],
                                                        "group": r["category_group"], "notes": r["notes"]})
    return out


def mark(items: list[dict]) -> list[dict]:
    """Each transaction (as tx_public gives it) with splits: its parts, or [] when it is whole."""
    got = of([t["id"] for t in items])
    for t in items:
        t["splits"] = got.get(t["id"], [])
    return items


def _words(t: dict, parts: list[dict], tags: list = ()) -> str:
    return model.words(t["merchant"], t["description"], t["category"], t["category_group"], t["notes"], t["account_name"],
                       *[x for p in parts for x in (p["category"], p["category_group"], p["notes"])], *tags)


def rewords(tid: int) -> None:
    """The words a search looks in, with the parts' categories and notes, and the tags (Monarch's and its own)."""
    from app import tags
    t = model.tx_row(tid)
    if not t:
        return
    parts = db.q("SELECT category, category_group, notes FROM mny_splits WHERE transaction_id = %s", (tid,))
    own = [r["tag"] for r in db.q("SELECT tag FROM mny_tags WHERE transaction_id = %s", (tid,))]
    db.ex("UPDATE mny_transactions SET words = %s, updated_at = updated_at WHERE id = %s", (_words(t, parts, tags.monarch(t) + own), tid))


def put(u: dict, t: dict, parts) -> dict:
    """Split the transaction into parts [{amount, category?, notes?}] (two and more; each amount its share, as a
    positive number or signed as the transaction; together the whole amount), or make it whole again with none."""
    model._need(model.can_write(u, t))
    if not isinstance(parts, list):
        raise Invalid("The parts: a list of {amount, category, notes}")
    if len(parts) == 1:
        raise Invalid("A split has two parts or more")
    if len(parts) > MAX_PARTS:
        raise Invalid(f"At most {MAX_PARTS} parts")
    total = Decimal(t["amount"])
    sign = -1 if total < 0 else 1
    rows, left = [], abs(total)
    for n, p in enumerate(parts):
        if not isinstance(p, dict):
            raise Invalid("Each part: {amount, category, notes}")
        amt = model.money(p.get("amount"), "The part's amount")
        if not amt:
            raise Invalid("Give each part an amount")
        amt = abs(amt)
        cat = model.text(p.get("category"), 128, "The category")
        rows.append((t["id"], n, sign * amt, cat, model._group_of_category(cat) if cat else None, model.text(p.get("notes"), 255, "The note")))
        left -= amt
    if parts and left != 0:
        raise Invalid(f"The parts add up to {abs(total) - left}, not {abs(total)}")
    with db.tx():
        db.ex("DELETE FROM mny_splits WHERE transaction_id = %s", (t["id"],))
        if rows:
            db.many("INSERT INTO mny_splits (transaction_id, position, amount, category, category_group, notes) VALUES (%s, %s, %s, %s, %s, %s)", rows)
            db.ex("UPDATE mny_transactions SET edited = 1 WHERE id = %s", (t["id"],))
    rewords(t["id"])
    return model.tx_row(t["id"])


def by_category(where: str, args: list) -> list[dict]:
    """For the spending by category: the parts of the split transactions that where keeps (a filter on t and a, as
    model._tx_filter gives it), and what each one's parts do not add up to under its own category: [{category, grp,
    currency, amount}]."""
    base = f"FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE {where}"
    parts = db.q(f"SELECT s.category, s.category_group AS grp, a.currency, s.amount FROM mny_splits s "
                 f"JOIN mny_transactions t ON t.id = s.transaction_id JOIN mny_accounts a ON a.id = t.account_id WHERE {where}", args)
    rest = db.q(f"SELECT t.category, t.category_group AS grp, a.currency, "
                f"t.amount - (SELECT SUM(s.amount) FROM mny_splits s WHERE s.transaction_id = t.id) AS amount {base} "
                f"AND EXISTS (SELECT 1 FROM mny_splits s WHERE s.transaction_id = t.id) HAVING amount <> 0", args)
    return list(parts) + list(rest)


WHOLE = "NOT EXISTS (SELECT 1 FROM mny_splits s WHERE s.transaction_id = t.id)"  # a transaction that is not split
