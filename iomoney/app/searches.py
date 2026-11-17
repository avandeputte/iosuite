"""Saved searches: a search of the transactions a person keeps under a name ("Reimbursable", "Card over $500",
"No category this year") and opens again with one click. Each person has their own. What is kept is the search as
the Transactions page writes it in its address (q=…&account=…&category=…), nothing of what it found."""
from iosuite_shared.errors import Invalid

from app import db, model

MAX_SEARCHES = 40
# the filters as the Transactions page names them in its address (static/app.js showTransactions)
KEYS = ("q", "account", "category", "month", "flow", "rec", "rcp", "amt", "hid", "tag", "rev")


def _query(v) -> str:
    """The search as kept: the known filters only, in a fixed order."""
    from urllib.parse import parse_qsl, urlencode
    got = dict(parse_qsl(str(v or "").lstrip("?#"), keep_blank_values=False))
    q = urlencode([(k, got[k]) for k in KEYS if got.get(k)])
    if not q:
        raise Invalid("There is nothing to keep: search or filter the transactions first")
    if len(q) > 1000:
        raise Invalid("This search is too long to keep")
    return q


def _public(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "query": r["query"], "position": r["position"]}


def items(u: dict) -> list[dict]:
    if model.role_rank(u) < 1:
        return []
    return [_public(r) for r in db.q("SELECT * FROM mny_searches WHERE user_id = %s ORDER BY position, id", (u["id"],))]


def _row(u: dict, sid) -> dict:
    try:
        r = db.one("SELECT * FROM mny_searches WHERE id = %s AND user_id = %s", (int(sid), u["id"]))
    except (TypeError, ValueError):
        r = None
    if not r:
        raise model.NotFound("No such saved search")
    return r


def create(u: dict, b: dict) -> dict:
    """{name, query}: keep a search. A name this person has already: that one now holds this search."""
    model._need(model.role_rank(u) >= 1, "You have no role in ioMoney")
    name = model.text(b.get("name"), 64, "The name")
    if not name:
        raise Invalid("Give the search a name")
    q = _query(b.get("query"))
    had = db.one("SELECT id FROM mny_searches WHERE user_id = %s AND name = %s", (u["id"], name))
    if had:
        db.ex("UPDATE mny_searches SET query = %s WHERE id = %s", (q, had["id"]))
        return _public(_row(u, had["id"]))
    n = db.one("SELECT count(*) AS n, COALESCE(MAX(position), 0) AS p FROM mny_searches WHERE user_id = %s", (u["id"],))
    if n["n"] >= MAX_SEARCHES:
        raise Invalid(f"At most {MAX_SEARCHES} saved searches")
    sid = db.ex("INSERT INTO mny_searches (user_id, name, query, position) VALUES (%s, %s, %s, %s)", (u["id"], name, q, n["p"] + 1))
    return _public(_row(u, sid))


def update(u: dict, sid, b: dict) -> dict:
    """{name?, query?, position?}."""
    r = _row(u, sid)
    sets, args = [], []
    if "name" in b:
        name = model.text(b["name"], 64, "The name")
        if not name:
            raise Invalid("Give the search a name")
        sets.append("name = %s")
        args.append(name)
    if "query" in b:
        sets.append("query = %s")
        args.append(_query(b["query"]))
    if "position" in b:
        sets.append("position = %s")
        args.append(int(model.number(b["position"], "The position", 0) or 0))
    if sets:
        db.ex(f"UPDATE mny_searches SET {', '.join(sets)} WHERE id = %s", (*args, r["id"]))
    return _public(_row(u, r["id"]))


def delete(u: dict, sid) -> None:
    db.ex("DELETE FROM mny_searches WHERE id = %s", (_row(u, sid)["id"],))


def forget(user_id: int) -> int:
    """A person is gone: their saved searches too. How many there were."""
    n = db.one("SELECT count(*) AS n FROM mny_searches WHERE user_id = %s", (user_id,))["n"]
    db.ex("DELETE FROM mny_searches WHERE user_id = %s", (user_id,))
    return n
