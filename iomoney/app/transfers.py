"""Transfers between the household's own accounts: the money that leaves one account and arrives in another (to
savings, a credit card's payment, a loan's payment) is one movement, not spending and income. Its two halves are
linked here (mny_transfers), so the spending and the cash flow leave them out, and each shows where the money went.

Two transactions are the halves of one transfer when:
- they are in two different accounts, one out and one in, of exactly the same amount;
- they are a few days apart at most (a transfer can take days to arrive);
- something says it is a transfer: a transfer rule of the household (mny_transfer_rules: in this account, a payee
  like this one is a transfer with that account), the category of either half (Monarch's Transfers group, a credit
  card payment), the payee or the bank's text saying so ("Payment - thank you", "autopay", "ACH"), or naming the other
  account: its name, its bank ("Ally Bank" in the checking account, the other half in the Ally account) or its last
  digits ("ONLINE PAYMENT TO *2530", "XXXXXX7081").
Each transaction goes with at most one other: the best pairs first, nearer days first, so that payments of the same
amount every month pair up with the nearest; when two are equally good and would link different accounts, neither is taken (a person links it by hand); between the same two accounts either is right.
A transfer whose text names the other account teaches a rule (source 'learned'), so the next one is found more surely,
also a few days further apart. Two transactions unlinked by hand are never linked again by themselves.
"""
import datetime as dt
import re
from decimal import Decimal

from iosuite_shared import users as shared_users
from iosuite_shared.errors import Invalid

from app import db, model

DAYS = 7  # how many days apart the two halves can be, without a rule (a transfer to another bank takes days)
MAX_DAYS = 31
LEARN_DAYS = 10  # the window of a learned rule: a known transfer may take longer to arrive
STOP = {"bank", "the", "and", "of", "na", "inc", "llc", "co", "corp", "financial", "account", "accounts", "checking",
        "savings", "saving", "card", "cards", "credit", "debit", "online", "transfer", "transfers", "payment", "payments",
        "pymt", "pmt", "ach", "from", "to", "xfer", "web", "id", "ppd", "des", "co.", "my", "joint", "visa", "mastercard",
        "amex", "loan", "mortgage", "deposit", "withdrawal", "auto", "autopay", "epay", "us", "usa", "fund", "funds"}
TRANSFERISH = re.compile(r"transfer|credit card payment|payment|xfer|autopay|deposit to|withdrawal to", re.I)
# a payee or bank's text that says money moved between accounts: a card's payment ("Payment - thank you", "Chase
# autopay"), a loan's or mortgage's payment, a transfer ("Online transfer to", "XFER", "ACH")
PAYEE_HINT = re.compile(r"\b(transfer|xfer|trnsfr|payment|pymt|pmt|autopay|auto pay|auto-pay|e-?pay|thank you|"
                        r"online banking|bill ?pay|loan|mortgage|ach (?:debit|credit|pmt)|crcardpmt|card ?pmt)\b", re.I)


def _words(*texts) -> set:
    out = set()
    for s in texts:
        for w in re.findall(r"[a-z0-9]+", (s or "").lower()):
            if len(w) >= 3 and w not in STOP and not w.isdigit():
                out.add(w)
    return out


def _is_transferish(t: dict) -> bool:
    grp = (t.get("category_group") or "").lower()
    return grp in model.TRANSFERS or bool(TRANSFERISH.search(t.get("category") or ""))


def _hinted(t: dict) -> bool:
    return any(PAYEE_HINT.search(x or "") for x in (t.get("merchant"), t.get("description")))


PAYS_INTO = ("credit", "loan", "other_liability")  # money in there is (nearly always) a payment
PAYS_FROM = ("cash", "investment")


LOANISH = re.compile(r"mortgage|loan|auto payment|car payment|student", re.I)


def _no_spending(t: dict) -> bool:
    """t has no category, or one a payment has (a transfer, a card's or a loan's payment): not a purchase or a refund."""
    return not t.get("category") or _is_transferish(t) or bool(LOANISH.search(t.get("category") or ""))


def _pays(o: dict, i: dict, accts: dict) -> bool:
    """Money out of a bank account and into a card or a loan, neither half a purchase or a refund by its category:
    a payment, the way a card's or a loan's is."""
    return ((accts.get(o["account_id"]) or {}).get("kind") in PAYS_FROM and (accts.get(i["account_id"]) or {}).get("kind") in PAYS_INTO
            and _no_spending(o) and _no_spending(i))


def _names(t: dict, other: dict) -> bool:
    """The payee or the bank's text of t names the other account: its name, its institution or its last digits."""
    mine = _words(t.get("merchant"), t.get("description"))
    theirs = _words(other.get("name"), other.get("institution"))
    return bool(mine & theirs) or _masked(t, other)


def _masked(t: dict, other: dict) -> bool:
    """The text of t has the other account's last digits (at least four), as banks write them: "*2530", "XXXX2530",
    "ending in 2530", "608921068"."""
    m = re.sub(r"\D", "", other.get("mask") or "")
    if len(m) < 4:
        return False
    return any(re.search(rf"{m}(?!\d)", x or "") for x in (t.get("merchant"), t.get("description")))


def _pattern_hits(pattern: str, t: dict) -> bool:
    p = (pattern or "").lower().strip()
    return bool(p) and any(p in (s or "").lower() for s in (t.get("merchant"), t.get("description")))


def _pattern_of(t: dict) -> str | None:
    """What a learned rule looks for: the bank's text (or the payee), in lower case, without what changes each time
    (dates, numbers, masked account numbers); None when too little is left to go by."""
    s = (t.get("description") or t.get("merchant") or "").lower()
    s = re.sub(r"\S*\d\S*", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -*#/.:")
    return s[:255] if len(s) >= 5 else None


def _rows(where: str = "1 = 1", args=()) -> list[dict]:
    return db.q("SELECT t.id, t.account_id, t.day, t.amount, t.merchant, t.description, t.category, t.category_group, "
                "a.name AS account_name, a.institution, a.owner_id FROM mny_transactions t "
                "JOIN mny_accounts a ON a.id = t.account_id "
                "WHERE t.amount <> 0 AND t.hidden = 0 AND NOT EXISTS (SELECT 1 FROM mny_transfers x WHERE x.out_id = t.id OR x.in_id = t.id) "
                f"AND {where}", tuple(args))


def _score(o: dict, i: dict, accts: dict, rules: list, nots: set) -> tuple[int, str, bool] | None:
    """How surely o (money out) and i (money in) are one transfer, what said so (a rule or the rest), and whether one
    names the other's account; None: they are not."""
    if o["account_id"] == i["account_id"] or (o["id"], i["id"]) in nots:
        return None
    gap = abs((o["day"] - i["day"]).days)
    ruled = any(r["account_id"] == a["account_id"] and r["other_id"] == b["account_id"] and gap <= r["days"]
                and _pattern_hits(r["pattern"], a) for r in rules for a, b in ((o, i), (i, o)))
    if gap > (MAX_DAYS if ruled else DAYS):
        return None
    named = _names(o, accts[i["account_id"]]) or _names(i, accts[o["account_id"]])
    transferish = _is_transferish(o) or _is_transferish(i)
    hinted = _hinted(o) or _hinted(i)
    pays = _pays(o, i, accts)
    if not (ruled or named or transferish or hinted):  # money into a card or a loan alone is not enough: a refund is too
        return None
    # a rule weighs most, yet a nearer pair that names the other account can still win over it
    score = 50 + (30 if ruled else 0) + (20 if named else 0) + (10 if transferish else 0) + (5 if hinted else 0) + (10 if pays else 0) - 3 * gap
    return score, "rule" if ruled else "auto", named


def link(where: str = "1 = 1", args=(), learn: bool = True, unsure: list = None) -> int:
    """Find the transfers among the transactions not linked yet (those that match where may pair with any other) and
    link them; how many were linked."""
    news = {t["id"]: t for t in _rows(where, args)}
    if not news:
        return 0
    pool = {t["id"]: t for t in _rows()}
    pool.update(news)
    accts = {a["id"]: a for a in db.q("SELECT id, name, institution, kind, mask FROM mny_accounts")}
    rules = db.q("SELECT * FROM mny_transfer_rules")
    nots = {(r["out_id"], r["in_id"]) for r in db.q("SELECT out_id, in_id FROM mny_transfer_nots")}
    by_amount: dict = {}
    for t in pool.values():
        by_amount.setdefault(abs(Decimal(t["amount"])), []).append(t)
    pairs: dict = {}  # (out id, in id): (score, how, out, in), each pair once (both halves may be new)
    for t in news.values():
        amt = Decimal(t["amount"])
        for c in by_amount.get(abs(amt), []):
            if Decimal(c["amount"]) != -amt:
                continue
            o, i = (t, c) if amt < 0 else (c, t)
            if (o["id"], i["id"]) in pairs:
                continue
            s = _score(o, i, accts, rules, nots)
            if s:
                pairs[(o["id"], i["id"])] = (s[0], s[1], o, i, s[2])
    of: dict = {}  # transaction id: its pairs
    for p in pairs.values():
        for x in (p[2]["id"], p[3]["id"]):
            of.setdefault(x, []).append(p)
    # the best first, each transaction in one pair at most; one with another partner as good, itself still free, is
    # left for a person
    used, n = set(), 0
    for score, how, o, i, named in sorted(pairs.values(), key=lambda p: -p[0]):
        if o["id"] in used or i["id"] in used:
            continue
        # a rival as good, still free, makes it a guess, unless it is between the same two accounts: then either way
        # is the same (two payments of the same amount from the checking account to the card, a day apart)
        rivals = [p for x in (o["id"], i["id"]) for p in of[x]
                  if p[0] == score and (p[2]["id"], p[3]["id"]) != (o["id"], i["id"])
                  and p[2]["id"] not in used and p[3]["id"] not in used
                  and (p[2]["account_id"], p[3]["account_id"]) != (o["account_id"], i["account_id"])]
        if rivals:
            if unsure is not None:
                unsure.append((o, i))
            continue  # as likely as another: not a guess to make
        db.ex("INSERT IGNORE INTO mny_transfers (out_id, in_id, how) VALUES (%s, %s, %s)", (o["id"], i["id"], how))
        used.update((o["id"], i["id"]))
        n += 1
        if learn and how == "auto" and named:  # only what surely is one teaches a rule
            for a, b in ((o, i), (i, o)):
                p = _pattern_of(a)
                if p:
                    db.ex("INSERT IGNORE INTO mny_transfer_rules (account_id, pattern, other_id, days, source) "
                          "VALUES (%s, %s, %s, %s, 'learned')", (a["account_id"], p, b["account_id"], LEARN_DAYS))
    return n


# ---- one transaction's transfer, as people see and change it

def pair_of(tid: int) -> dict | None:
    """{out_id, in_id, how} of the transfer this transaction is a half of."""
    return db.one("SELECT * FROM mny_transfers WHERE out_id = %s OR in_id = %s", (tid, tid))


def other_half(u: dict, t: dict) -> dict | None:
    """The other half of t's transfer, as the transaction list shows it: {id, accountId, account, day, how}; the
    account is left out when it is someone else's private one."""
    p = pair_of(t["id"])
    if not p:
        return None
    o = model.tx_row(p["in_id"] if p["out_id"] == t["id"] else p["out_id"])
    if not o:
        return None
    seen = model.can_read(u, o)
    return {"id": o["id"] if seen else None, "accountId": o["account_id"] if seen else None,
            "account": o["account_name"] if seen else None, "day": o["day"].isoformat(), "how": p["how"]}


def halves_of(ids: list) -> dict:
    """For many transactions at once: {id: (other id, how)}."""
    if not ids:
        return {}
    m = db.marks(len(ids))
    out = {}
    for r in db.q(f"SELECT * FROM mny_transfers WHERE out_id IN ({m}) OR in_id IN ({m})", (*ids, *ids)):
        out[r["out_id"]] = (r["in_id"], r["how"])
        out[r["in_id"]] = (r["out_id"], r["how"])
    return out


def candidates(u: dict, t: dict, days: int = 14) -> list[dict]:
    """The transactions this person sees that could be the other half of t: the same amount the other way, in
    another account, nearest days first."""
    where, args = model._visible(u)
    rows = db.q(f"SELECT t.*, a.owner_id, a.name AS account_name, a.currency FROM mny_transactions t "
                f"JOIN mny_accounts a ON a.id = t.account_id WHERE {where} AND t.hidden = 0 AND t.amount = %s AND t.account_id <> %s "
                f"AND t.day BETWEEN %s AND %s AND NOT EXISTS (SELECT 1 FROM mny_transfers x WHERE x.out_id = t.id OR x.in_id = t.id)",
                (*args, -Decimal(t["amount"]), t["account_id"], t["day"] - dt.timedelta(days=days), t["day"] + dt.timedelta(days=days)))
    rows.sort(key=lambda r: abs((r["day"] - t["day"]).days))
    return [model.tx_public(r, u) for r in rows[:20]]


def connect(u: dict, t: dict, other_id) -> None:
    """Link t and another transaction by hand (both changed by whoever may change them)."""
    o = model.transaction(u, other_id)
    model._need(model.can_write(u, t) and model.can_write(u, o))
    if o["account_id"] == t["account_id"] or Decimal(o["amount"]) != -Decimal(t["amount"]) or not Decimal(t["amount"]):
        raise Invalid("A transfer is the same amount out of one account and into another")
    if pair_of(t["id"]) or pair_of(o["id"]):
        raise Invalid("One of them is linked to another transfer already: unlink it first")
    out_, in_ = (t, o) if Decimal(t["amount"]) < 0 else (o, t)
    db.ex("DELETE FROM mny_transfer_nots WHERE out_id = %s AND in_id = %s", (out_["id"], in_["id"]))
    db.ex("INSERT INTO mny_transfers (out_id, in_id, how, created_by) VALUES (%s, %s, 'hand', %s)", (out_["id"], in_["id"], u["id"]))


def dismiss(u: dict, out_id, in_id) -> None:
    """Say these two are not one transfer (the list of what to check stops showing them, and they are never linked
    by themselves); neither may be linked to the other already."""
    o, i = model.transaction(u, out_id), model.transaction(u, in_id)
    model._need(model.can_write(u, o) and model.can_write(u, i))
    if Decimal(o["amount"]) >= 0 or Decimal(i["amount"]) <= 0:
        raise Invalid("The first is the money out, the second the money in")
    p = pair_of(o["id"])
    if p and p["in_id"] == i["id"]:
        raise Invalid("They are linked: unlink them instead")
    db.ex("INSERT IGNORE INTO mny_transfer_nots (out_id, in_id) VALUES (%s, %s)", (o["id"], i["id"]))


def disconnect(u: dict, t: dict) -> None:
    """Unlink t's transfer, for good: the two are not linked again by themselves."""
    p = pair_of(t["id"])
    if not p:
        return
    o = model.tx_row(p["in_id"] if p["out_id"] == t["id"] else p["out_id"])
    model._need(model.can_write(u, t) and (o is None or model.can_write(u, o)))
    db.ex("DELETE FROM mny_transfers WHERE out_id = %s", (p["out_id"],))
    db.ex("INSERT IGNORE INTO mny_transfer_nots (out_id, in_id) VALUES (%s, %s)", (p["out_id"], p["in_id"]))


LOOK_DAYS = 14  # how far apart the maintenance still shows a debit and a credit of the same amount as a possible transfer


def link_all(u: dict) -> dict:
    """Go through every transaction not linked yet and link the transfers (Link transfers now, the maintenance in
    Settings › Money): {linked, learned (transfer rules), possible: what is still not linked though it could be a
    transfer (the same amount out of one account and into another, at most LOOK_DAYS apart), each {out, in, why}, the
    nearest days first; why: as likely as another, nothing says it is a transfer, too many days apart}."""
    model._need(shared_users.can_write(u), "Only editors link the household's transfers")
    rules_before = db.one("SELECT COUNT(*) AS n FROM mny_transfer_rules")["n"]
    ties: list = []
    n = link(unsure=ties)
    tied = {(o["id"], i["id"]) for o, i in ties}
    return {"linked": n, "learned": db.one("SELECT COUNT(*) AS n FROM mny_transfer_rules")["n"] - rules_before,
            "possible": possible(u, tied)}


def possible(u: dict, tied: set = frozenset(), limit: int = 1000) -> list[dict]:
    """The debits and credits of the same amount in two accounts, at most LOOK_DAYS apart, neither linked yet nor
    unlinked by a person: what a person may want to link, with why it was not linked by itself."""
    rows = [t for t in _rows() if model.can_read(u, t)]
    accts = {a["id"]: a for a in db.q("SELECT id, name, institution, kind, mask FROM mny_accounts")}
    rules = db.q("SELECT * FROM mny_transfer_rules")
    nots = {(r["out_id"], r["in_id"]) for r in db.q("SELECT out_id, in_id FROM mny_transfer_nots")}
    ins: dict = {}
    for t in rows:
        if Decimal(t["amount"]) > 0:
            ins.setdefault(Decimal(t["amount"]), []).append(t)
    found = []
    for o in rows:
        amt = -Decimal(o["amount"])
        if amt <= 0:
            continue
        for i in ins.get(amt, []):
            gap = abs((o["day"] - i["day"]).days)
            if i["account_id"] == o["account_id"] or gap > LOOK_DAYS or (o["id"], i["id"]) in nots:
                continue
            if (o["id"], i["id"]) in tied:
                why = "as likely as another transaction of the same amount"
            elif gap > DAYS and not _score(o, i, accts, rules, nots):
                why = f"{gap} days apart"
            elif not _score(o, i, accts, rules, nots):
                why = "nothing says it is a transfer"
            else:
                why = "as likely as another transaction of the same amount"
            found.append((gap, -amt, o, i, why))
    found.sort(key=lambda f: (f[0], f[1]))
    out = []
    for _gap, _a, o, i, why in found[:limit]:
        a, b = model.tx_row(o["id"]), model.tx_row(i["id"])
        if a and b:
            out.append({"out": model.tx_public(a, u), "in": model.tx_public(b, u), "why": why})
    return out


# ---- transfer rules

def _sees_rule(u: dict, r: dict) -> bool:
    """A rule names two accounts and words from their transactions: it is for whoever sees both (a rule learned from
    someone's private account would otherwise show that account's payees)."""
    return all(model.can_read(u, model.account_row(x)) for x in (r["account_id"], r["other_id"]))


def rules(u: dict) -> list[dict]:
    if model.role_rank(u) < 1:
        return []
    return [r for r in db.q("SELECT * FROM mny_transfer_rules ORDER BY account_id, pattern") if _sees_rule(u, r)]


def rule_public(r: dict, u: dict) -> dict:
    a, o = model.account_row(r["account_id"]), model.account_row(r["other_id"])
    name = lambda x: x["name"] if x and model.can_read(u, x) else None  # noqa: E731
    return {"id": r["id"], "accountId": r["account_id"], "account": name(a), "pattern": r["pattern"], "otherId": r["other_id"],
            "other": name(o), "days": r["days"], "source": r["source"], "writable": shared_users.can_write(u)}


def _rule_fields(u: dict, b: dict, old: dict = None) -> dict:
    c = {}
    for k, col in (("accountId", "account_id"), ("otherId", "other_id")):
        if k in b or old is None:
            a = model.account_row(b.get(k))
            if not a or not model.can_read(u, a):
                raise Invalid("Choose the two accounts")
            c[col] = a["id"]
    if (c.get("account_id") or old["account_id"]) == (c.get("other_id") or old["other_id"]):
        raise Invalid("A transfer goes between two different accounts")
    if "pattern" in b or old is None:
        p = model.text(b.get("pattern"), 255, "The words")
        if not p:
            raise Invalid("Give the words the payee or the bank's text has")
        c["pattern"] = p.lower()
    if "days" in b:
        d = int(model.number(b.get("days"), "The days", 0) or DAYS)
        if not 0 <= d <= MAX_DAYS:
            raise Invalid(f"The days: 0 to {MAX_DAYS}")
        c["days"] = d
    return c


def create_rule(u: dict, b: dict) -> dict:
    model._need(shared_users.can_write(u), "Only editors change the rules")
    c = _rule_fields(u, b)
    if db.one("SELECT id FROM mny_transfer_rules WHERE account_id = %s AND other_id = %s AND pattern = %s",
              (c["account_id"], c["other_id"], c["pattern"])):
        raise Invalid("That rule is there already")
    rid = db.ex("INSERT INTO mny_transfer_rules (account_id, pattern, other_id, days, source, created_by) VALUES (%s, %s, %s, %s, 'hand', %s)",
                (c["account_id"], c["pattern"], c["other_id"], c.get("days", DAYS), u["id"]))
    return db.one("SELECT * FROM mny_transfer_rules WHERE id = %s", (rid,))


def rule(u: dict, rid) -> dict:
    try:
        r = db.one("SELECT * FROM mny_transfer_rules WHERE id = %s", (int(rid),))
    except (TypeError, ValueError):
        r = None
    if not r or model.role_rank(u) < 1 or not _sees_rule(u, r):
        raise model.NotFound("No such transfer rule")
    return r


def update_rule(u: dict, r: dict, b: dict) -> dict:
    model._need(shared_users.can_write(u), "Only editors change the rules")
    c = _rule_fields(u, b, r)
    if c:
        db.ex(f"UPDATE mny_transfer_rules SET {', '.join(k + ' = %s' for k in c)}, source = 'hand' WHERE id = %s", (*c.values(), r["id"]))
    return db.one("SELECT * FROM mny_transfer_rules WHERE id = %s", (r["id"],))


def delete_rule(u: dict, r: dict) -> None:
    model._need(shared_users.can_write(u), "Only editors change the rules")
    db.ex("DELETE FROM mny_transfer_rules WHERE id = %s", (r["id"],))
