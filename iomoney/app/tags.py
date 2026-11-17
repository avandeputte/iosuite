"""Tags on transactions: the ones Monarch Money sends (kept with the transaction, refreshed by every sync, not changed
here) and the household's own (mny_tags), set here: "trip", "reimbursable", "tax". A transaction shows both; a search
by tag finds either. Own tags are short (TAG_LIMIT), a few to a transaction, and the same tag whatever its capitals."""
import json
import re

from iosuite_shared import users as shared_users
from iosuite_shared.errors import Invalid

from app import db, model

TAG_LIMIT = 64
MAX_TAGS = 20  # of one transaction


def clean(v) -> str | None:
    s = re.sub(r"\s+", " ", str(v or "").replace(",", " ")).strip().lstrip("#").strip()
    if len(s) > TAG_LIMIT:
        raise Invalid(f"A tag is at most {TAG_LIMIT} characters")
    return s or None


def listed(v) -> list[str]:
    """Tags as they come in (a list, or one text with commas): cleaned, each once (whatever its capitals)."""
    if v is None:
        return []
    parts = v if isinstance(v, (list, tuple)) else str(v).split(",")
    out, seen = [], set()
    for p in parts:
        t = clean(p)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    if len(out) > MAX_TAGS:
        raise Invalid(f"At most {MAX_TAGS} tags on a transaction")
    return out


def monarch(t: dict) -> list[str]:
    """The tags Monarch Money sent with a transaction (a row of mny_transactions)."""
    try:
        got = json.loads(t["tags"]) if t.get("tags") else []
    except ValueError:
        got = []
    return [str(x) for x in got if x] if isinstance(got, list) else []


def of(ids: list) -> dict:
    """{transaction id: its own tags, by name}."""
    ids = [int(i) for i in ids]
    out: dict = {}
    if not ids:
        return out
    for r in db.q(f"SELECT transaction_id, tag FROM mny_tags WHERE transaction_id IN ({db.marks(len(ids))}) ORDER BY tag", ids):
        out.setdefault(r["transaction_id"], []).append(r["tag"])
    return out


def mark(items: list[dict]) -> list[dict]:
    """Each transaction (as tx_public gives it, tags: Monarch's) with ownTags, and tags: Monarch's and its own."""
    got = of([t["id"] for t in items])
    for t in items:
        own = got.get(t["id"], [])
        have = {x.lower() for x in t.get("tags") or []}
        t["ownTags"] = own
        t["tags"] = list(t.get("tags") or []) + [x for x in own if x.lower() not in have]
    return items


def put(t: dict, tags) -> bool:
    """The transaction's own tags become these (the ones Monarch sends with it are not kept twice); whether they changed."""
    theirs = {x.lower() for x in monarch(t)}
    want = [x for x in listed(tags) if x.lower() not in theirs]
    have = of([t["id"]]).get(t["id"], [])
    if sorted(x.lower() for x in want) == sorted(x.lower() for x in have):
        return False
    with db.tx():
        db.ex("DELETE FROM mny_tags WHERE transaction_id = %s", (t["id"],))
        if want:
            db.many("INSERT INTO mny_tags (transaction_id, tag) VALUES (%s, %s)", [(t["id"], x) for x in want])
    return True


def where(tag: str) -> tuple[str, list]:
    """SQL for the transactions (t) that have a tag, Monarch's or their own."""
    return ("(EXISTS (SELECT 1 FROM mny_tags g WHERE g.transaction_id = t.id AND g.tag = %s) "
            "OR (t.tags IS NOT NULL AND LOWER(t.tags) LIKE %s))",
            [tag, "%" + json.dumps(tag.lower()).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"])


def items(u: dict) -> list[dict]:
    """Every tag the transactions this person sees have: [{tag, count, total, own: whether it is one set here}], by name
    (hidden transactions left out)."""
    if model.role_rank(u) < 1:
        return []
    vis, args = model._visible(u)
    base = f"FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE {vis} AND a.track = 'transactions' AND t.hidden = 0"
    out: dict = {}
    for r in db.q(f"SELECT g.tag, count(*) AS n, COALESCE(SUM(t.amount), 0) AS s FROM mny_tags g JOIN mny_transactions t ON t.id = g.transaction_id "
                  f"JOIN mny_accounts a ON a.id = t.account_id WHERE {vis} AND a.track = 'transactions' AND t.hidden = 0 GROUP BY g.tag", args):
        out[r["tag"].lower()] = {"tag": r["tag"], "count": r["n"], "total": model.n2(r["s"]), "own": True}
    for r in db.q(f"SELECT t.tags, t.amount {base} AND t.tags IS NOT NULL", args):
        for x in monarch(r):
            c = out.setdefault(x.lower(), {"tag": x, "count": 0, "total": 0.0, "own": False})
            if not c["own"]:
                c["count"] += 1
                c["total"] = round(c["total"] + float(r["amount"]), 2)
    return sorted(out.values(), key=lambda c: c["tag"].lower())


def _rewords(tag: str) -> None:
    from app import splits
    for r in db.q("SELECT transaction_id FROM mny_tags WHERE tag = %s", (tag,)):
        splits.rewords(r["transaction_id"])


def rename(u: dict, b: dict) -> dict:
    """{name, newName}: one of the household's own tags under another name (into one there is: the two are one)."""
    model._need(shared_users.can_write(u), "Only editors change the tags")
    old, new = clean(b.get("name")), clean(b.get("newName"))
    if not old or not new:
        raise Invalid("Give the tag and its new name")
    ids = [r["transaction_id"] for r in db.q("SELECT transaction_id FROM mny_tags WHERE tag = %s", (old,))]
    with db.tx():
        db.ex("DELETE FROM mny_tags WHERE tag = %s", (old,))
        if ids:
            db.many("INSERT IGNORE INTO mny_tags (transaction_id, tag) VALUES (%s, %s)", [(i, new) for i in ids])
    _rewords(new)
    return {"ok": True, "moved": len(ids)}


def delete(u: dict, b: dict) -> dict:
    """{name}: one of the household's own tags off every transaction."""
    model._need(shared_users.can_write(u), "Only editors change the tags")
    old = clean(b.get("name"))
    ids = [r["transaction_id"] for r in db.q("SELECT transaction_id FROM mny_tags WHERE tag = %s", (old,))]
    db.ex("DELETE FROM mny_tags WHERE tag = %s", (old,))
    from app import splits
    for i in ids:
        splits.rewords(i)
    return {"ok": True, "removed": len(ids)}
