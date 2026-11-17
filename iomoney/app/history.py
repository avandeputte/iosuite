"""What was changed by hand on a transaction, and the way back.

Each change a person makes to a transaction (its payee, category, notes, tags, hidden; in an account kept by hand its
date and amount) is kept (mny_changes) with the fields as they were and as they became, who made it and when; the
changes made to many transactions at once share a batch. A change can be taken back (undo: the fields as they were,
kept as a change of its own), one at a time or a whole batch. A transaction from Monarch Money that was changed here
can go back to Monarch's own: the fields as they were before the first change kept, and the next sync that reaches its
date is let in again. The rules and the syncs are not people: what they change is not kept here."""
import datetime as dt
import json
import uuid
from decimal import Decimal

from iosuite_shared import users as shared_users
from iosuite_shared.errors import Invalid

from app import db, model

FIELDS = ("merchant", "category", "category_group", "notes", "hidden", "day", "amount")  # columns of mny_transactions
NAMES = {"merchant": "payee", "category": "category", "category_group": "group", "notes": "notes", "hidden": "hidden",
         "day": "date", "amount": "amount", "tags": "tags"}
KEEP_DAYS = 400


def batch_id() -> str:
    return uuid.uuid4().hex


def _plain(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()[:10]
    return v


def snapshot(t: dict, tags: list = None) -> dict:
    """The fields of a transaction (a row of mny_transactions) a person can change, as plain values."""
    out = {k: _plain(t.get(k)) for k in FIELDS}
    out["hidden"] = int(out["hidden"] or 0)
    if tags is not None:
        out["tags"] = sorted(tags, key=str.lower)
    return out


def record(u: dict | None, tid: int, before: dict, after: dict, what: str = "hand", batch: str = None) -> int | None:
    """Keep what changed between two snapshots (nothing when they are the same); the change's id."""
    diff = [k for k in after if before.get(k) != after.get(k)]
    if not diff:
        return None
    return db.ex("INSERT INTO mny_changes (transaction_id, batch, what, by_user, before_json, after_json) VALUES (%s, %s, %s, %s, %s, %s)",
                 (tid, batch, what, (u or {}).get("id"), json.dumps({k: before.get(k) for k in diff}), json.dumps({k: after.get(k) for k in diff})))


def _names() -> dict:
    try:
        return {x["id"]: x.get("displayName") or x["name"] for x in shared_users.list_users()}
    except Exception:  # noqa: BLE001 - a name is a nicety
        return {}


def _public(r: dict, names: dict) -> dict:
    before, after = json.loads(r["before_json"]), json.loads(r["after_json"])
    return {"id": r["id"], "transactionId": r["transaction_id"], "batch": r["batch"], "what": r["what"], "by": names.get(r["by_user"]),
            "at": r["at"].isoformat() if r.get("at") else None, "secondsAgo": r.get("age"), "undone": bool(r["undone"]),
            # a category's group follows it: said once
            "fields": [{"field": NAMES.get(k, k), "before": before.get(k), "after": after.get(k)} for k in after
                       if not (k == "category_group" and "category" in after)]}


def of(u: dict, t: dict, limit: int = 50) -> list[dict]:
    """The changes kept for one transaction, the latest first."""
    names = _names()
    return [_public(r, names) for r in db.q("SELECT *, TIMESTAMPDIFF(SECOND, at, NOW()) AS age FROM mny_changes WHERE transaction_id = %s ORDER BY id DESC LIMIT %s", (t["id"], limit))]


def recent(u: dict, limit: int = 100) -> list[dict]:
    """The latest changes to the transactions this person sees, the changes made together as one: [{batch, what, by,
    at, count, undone, canUndo, changes: a few of them, each with its transaction}]."""
    if model.role_rank(u) < 1:
        return []
    vis, args = model._visible(u)
    rows = db.q(f"SELECT c.*, TIMESTAMPDIFF(SECOND, c.at, NOW()) AS age, t.merchant, t.description, t.day, t.amount, t.account_id, a.name AS account_name, a.currency, a.owner_id "
                f"FROM mny_changes c JOIN mny_transactions t ON t.id = c.transaction_id JOIN mny_accounts a ON a.id = t.account_id "
                f"WHERE {vis} ORDER BY c.id DESC LIMIT 2000", args)
    names = _names()
    out, seen = [], {}
    for r in rows:
        key = r["batch"] or f"one:{r['id']}"
        g = seen.get(key)
        if g is None:
            if len(out) >= limit:
                continue
            g = seen[key] = {"batch": r["batch"], "id": None if r["batch"] else r["id"], "what": r["what"], "by": names.get(r["by_user"]),
                             "at": r["at"].isoformat(), "secondsAgo": r["age"], "count": 0, "undone": True, "canUndo": True, "changes": []}
            out.append(g)
        g["count"] += 1
        g["undone"] = g["undone"] and bool(r["undone"])
        g["canUndo"] = g["canUndo"] and model.can_write(u, r)
        if len(g["changes"]) < 5:
            c = _public(r, names)
            c["transaction"] = {"id": r["transaction_id"], "payee": r["merchant"] or r["description"], "day": r["day"].isoformat(),
                                "amount": model.n2(r["amount"]), "account": r["account_name"], "currency": r["currency"]}
            g["changes"].append(c)
    for g in out:
        g["canUndo"] = g["canUndo"] and not g["undone"] and g["what"] != "undo"
    return out


def _restore(u: dict, t: dict, values: dict, what: str, batch: str = None) -> None:
    """Put fields of a transaction back to values (as a snapshot has them), kept as a change of its own."""
    from app import splits, tags
    own = tags.of([t["id"]]).get(t["id"], [])
    before = snapshot(t, own)
    sets, args = [], []
    for k in FIELDS:
        if k in values and (t["source"] == "manual" or k not in ("day", "amount")):
            sets.append(f"{k} = %s")
            args.append(values[k])
    if sets:
        db.ex(f"UPDATE mny_transactions SET {', '.join(sets)} WHERE id = %s", (*args, t["id"]))
    if "tags" in values:
        tags.put(t, values["tags"] or [])
    splits.rewords(t["id"])
    n = model.tx_row(t["id"])
    if t["source"] == "manual" and Decimal(n["amount"]) != Decimal(t["amount"]):
        model._move_balance(t["account_id"], Decimal(n["amount"]) - Decimal(t["amount"]))
    record(u, t["id"], before, snapshot(n, tags.of([t["id"]]).get(t["id"], [])), what, batch)


def undo(u: dict, change_id=None, batch: str = None) -> dict:
    """Take back one change, or every change of a batch: the fields as they were before it. How many transactions."""
    if batch:
        rows = db.q("SELECT * FROM mny_changes WHERE batch = %s AND undone = 0 AND what <> 'undo' ORDER BY id DESC", (str(batch),))
    else:
        try:
            rows = db.q("SELECT * FROM mny_changes WHERE id = %s AND undone = 0 AND what <> 'undo'", (int(change_id),))
        except (TypeError, ValueError):
            rows = []
    if not rows:
        raise model.NotFound("No such change, or it was taken back already")
    new_batch = batch_id() if len(rows) > 1 else None
    n = 0
    for r in rows:
        t = model.tx_row(r["transaction_id"])
        if not t or not model.can_write(u, t):
            continue
        _restore(u, t, json.loads(r["before_json"]), "undo", new_batch)
        db.ex("UPDATE mny_changes SET undone = 1 WHERE id = %s", (r["id"],))
        n += 1
    if not n:
        raise model.Forbidden("You may not change these transactions")
    return {"ok": True, "undone": n}


def reset(u: dict, t: dict) -> dict:
    """A transaction from Monarch Money back to Monarch's own: the fields as they were before the first change kept
    here, and no longer counted as changed by hand, so the next sync that reaches its date refreshes it (and the
    rules apply to it again). Its own tags and its split go."""
    model._need(model.can_write(u, t))
    if t["source"] != "monarch":
        raise Invalid("This transaction was added here: there is nothing of Monarch Money's to go back to")
    first: dict = {}
    for r in db.q("SELECT before_json FROM mny_changes WHERE transaction_id = %s ORDER BY id", (t["id"],)):
        for k, v in json.loads(r["before_json"]).items():
            first.setdefault(k, v)
    first["tags"] = []
    db.ex("DELETE FROM mny_splits WHERE transaction_id = %s", (t["id"],))
    _restore(u, t, first, "reset")
    db.ex("UPDATE mny_transactions SET edited = 0 WHERE id = %s", (t["id"],))
    model.apply_rules("t.id = %s", (t["id"],))
    return {"ok": True, "restored": sorted(NAMES.get(k, k) for k in first if k != "tags")}


def prune() -> None:
    """Changes older than KEEP_DAYS go (a chore)."""
    db.ex("DELETE FROM mny_changes WHERE at < DATE_SUB(NOW(), INTERVAL %s DAY)", (KEEP_DAYS,))
