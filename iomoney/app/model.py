"""The household's money: accounts (the house and the cars among them), their value day by day, transactions, holdings,
the net worth, and who sees and changes what.

Everything hangs off an account. An account is the household's (owner_id NULL: everyone with a role here sees it;
editors and admins change it) or the private one of one person (only they see it; members and more keep their own).
A viewer only looks. Nobody without a role here sees anything (ioMoney's default role is none: app/users.py).

Amounts are kept as DECIMAL and worked with as Decimal; the API gives them as numbers rounded to the cent. An account
has a currency; totals are in the household's currency (Settings › Money; app/quotes.py converts).
"""
import datetime as dt
import json
import re
from decimal import Decimal, InvalidOperation

from iosuite_shared import related, users as shared_users
from iosuite_shared.errors import Invalid

from app import db


class NotFound(Exception):
    """No such thing (or not one this account sees)."""


class Forbidden(Exception):
    """The account sees it but may not do this."""


# kind -> (label, an asset or something owed, Monarch Money's account types that are this kind)
KINDS = {
    "cash": ("Cash", True, ("depository",)),
    "investment": ("Investments", True, ("brokerage",)),
    "property": ("Real estate", True, ("real_estate",)),
    "vehicle": ("Vehicles", True, ("vehicle",)),
    "other_asset": ("Other assets", True, ("valuables", "other_asset")),
    "credit": ("Credit cards", False, ("credit",)),
    "loan": ("Loans", False, ("loan",)),
    "other_liability": ("Other liabilities", False, ("other_liability",)),
}
THINGS = ("property", "vehicle", "other_asset")  # what has a value rather than a balance: valued, linked to a loan
# how the accounts are grouped on the pages, in this order: (group, its name, the kinds in it)
GROUPS = (("cash", "Cash", ("cash",)), ("investment", "Investments", ("investment",)), ("credit", "Credit cards", ("credit",)),
          ("loan", "Loans", ("loan", "other_liability")), ("asset", "Assets", THINGS))
GROUP_OF = {k: g for g, _n, kinds in GROUPS for k in kinds}
# what is followed for an account: its value alone (a balance or a value now and then), or its transactions too
TRACKS = ("value", "transactions")
TRACK_DEFAULT = {"cash": "transactions", "credit": "transactions"}  # every other kind: the value alone
HOLDING_KINDS = ("stock", "etf", "fund", "bond", "crypto", "cash", "option", "other")
CURRENCY = re.compile(r"^[A-Z]{3}$")
SYMBOL = re.compile(r"^[A-Za-z0-9.\-=^]{1,32}$")
CENT = Decimal("0.01")
MAX_AMOUNT = Decimal("999999999999.99")
DETAIL_FIELDS = {"address": 255, "year": 4, "make": 64, "model": 64, "vin": 32, "mileage": 12, "boughtOn": 10,
                 "boughtFor": 20, "yearlyRate": 8, "notes": 2000,
                 "floor": 20}  # a cash account: the balance it should not go under (app/forecast.py warns)
# what is kept to deal with an account's bank (mny_account_info), and how long each may be
INFO_FIELDS = {"accountNumber": 64, "routingNumber": 32, "iban": 42, "swift": 11, "phone": 40, "phoneAbroad": 40,
               "website": 255, "email": 255, "address": 1000, "username": 128, "openedOn": 10, "notes": 4000}
INFO_SECRET = ("accountNumber", "routingNumber", "iban")  # shown hidden until asked, and never to an MCP client
TRANSFERS = ("transfers", "transfer")  # a category group (Monarch's "Transfers") that is not spending or income


def kind_of_monarch(type_name: str, is_asset: bool) -> str:
    for k, (_l, _a, monarch) in KINDS.items():
        if type_name in monarch:
            return k
    return "other_asset" if is_asset else "other_liability"


# ---- who may

def role_rank(u: dict | None) -> int:
    return shared_users.RANK.get((u or {}).get("role") or "none", 0)


def can_read(u: dict | None, a: dict | None) -> bool:
    if not u or not a or role_rank(u) < 1:
        return False
    return a["owner_id"] is None or a["owner_id"] == u["id"]


def can_write(u: dict | None, a: dict | None) -> bool:
    """The household's: editors and admins. One's own private account: members and more (a viewer only looks)."""
    if not can_read(u, a):
        return False
    return shared_users.can_write(u) if a["owner_id"] is None else shared_users.is_member(u)


def may_add(u: dict, household: bool) -> bool:
    return shared_users.can_write(u) if household else shared_users.is_member(u)


def is_admin(u: dict | None) -> bool:
    return (u or {}).get("role") == "admin"


def _need(ok: bool, why: str = "You may not change this") -> None:
    if not ok:
        raise Forbidden(why)


# ---- the fields, as they come in

def text(v, limit: int, name: str) -> str | None:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip() if limit <= 512 else str(v).replace("\r\n", "\n").strip()
    if len(s) > limit:
        raise Invalid(f"{name} is too long (at most {limit} characters)")
    return s or None


def money(v, name: str = "The amount", required: bool = True) -> Decimal | None:
    """A number of the currency, to the cent ('1,234.50', 1234.5, '-12')."""
    if v in (None, ""):
        if required:
            raise Invalid(f"{name}: a number is expected")
        return None
    try:
        d = Decimal(str(v).replace(",", "").replace(" ", "").replace("$", "").replace("€", "").replace("£", ""))
    except InvalidOperation:
        raise Invalid(f"{name}: a number is expected")
    if not d.is_finite() or abs(d) > MAX_AMOUNT:
        raise Invalid(f"{name}: a number is expected")
    return d.quantize(CENT)


def number(v, name: str, places: int = 8, required: bool = False) -> Decimal | None:
    if v in (None, ""):
        if required:
            raise Invalid(f"{name}: a number is expected")
        return None
    try:
        d = Decimal(str(v).replace(",", ""))
    except InvalidOperation:
        raise Invalid(f"{name}: a number is expected")
    if not d.is_finite() or abs(d) > Decimal("1e15"):
        raise Invalid(f"{name}: a number is expected")
    return d.quantize(Decimal(1).scaleb(-places))


def day(v, name: str = "The date", required: bool = True) -> dt.date | None:
    if v in (None, ""):
        if required:
            raise Invalid(f"{name}: a date is expected (YYYY-MM-DD)")
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        raise Invalid(f"{name}: a date is expected (YYYY-MM-DD)")


def currency(v) -> str:
    s = str(v or "").strip().upper()
    if not CURRENCY.match(s):
        raise Invalid("The currency: a three-letter code such as USD or EUR")
    return s


def symbol(v) -> str | None:
    s = str(v or "").strip().upper()
    if not s:
        return None
    if not SYMBOL.match(s):
        raise Invalid("The symbol: as Yahoo Finance writes it, e.g. AAPL, VWCE.DE or BTC-USD")
    return s


def flag(v) -> int:
    return 1 if v in (True, 1, "1", "true", "yes", "on") else 0


def _details(v, old: dict | None = None) -> dict:
    """What a house or a car is: known fields only, short texts."""
    if v is None:
        return old or {}
    if not isinstance(v, dict):
        raise Invalid("details: an object is expected")
    out = dict(old or {})
    for k, n in DETAIL_FIELDS.items():
        if k not in v:
            continue
        x = v[k]
        if x in (None, ""):
            out.pop(k, None)
            continue
        if k == "yearlyRate":
            r = number(x, "The yearly change", 3)
            if not Decimal(-90) <= r <= Decimal(90):
                raise Invalid("The yearly change: a percentage between -90 and 90")
            out[k] = float(r)
        elif k == "boughtFor":
            out[k] = float(money(x, "The price paid"))
        elif k == "floor":
            out[k] = float(money(x, "The lowest balance"))
        elif k == "boughtOn":
            out[k] = day(x, "Bought on").isoformat()
        else:
            out[k] = text(x, n, k)
    return {k: v for k, v in out.items() if v is not None}


def n2(d) -> float | None:
    """A Decimal (or None) as the API gives it: a number rounded to the cent."""
    return None if d is None else float(Decimal(d).quantize(CENT))


# ---- the household's currency, and other settings of the app

def setting(name: str, default: str = "") -> str:
    return db.get_setting(name, default) or default


def home_currency() -> str:
    return setting("currency", "USD")


def rate(cur: str | None) -> Decimal:
    """How many of the household's currency one of `cur` is (1 for the same, or when not known yet)."""
    from app import quotes
    return quotes.fx(cur or home_currency(), home_currency())


# ---- accounts

def _acct(r: dict | None) -> dict | None:
    if not r:
        return None
    r = dict(r)
    try:
        r["details"] = json.loads(r["details"]) if r.get("details") else {}
    except ValueError:
        r["details"] = {}
    return r


def account_row(aid) -> dict | None:
    try:
        aid = int(aid)
    except (TypeError, ValueError):
        return None
    return _acct(db.one("SELECT * FROM mny_accounts WHERE id = %s", (aid,)))


def account(u: dict, aid) -> dict:
    a = account_row(aid)
    if not can_read(u, a):
        raise NotFound("No such account")
    return a


def _visible(u: dict, alias: str = "a") -> tuple[str, list]:
    """The SQL that keeps the accounts this person sees."""
    if role_rank(u) < 1:
        return "0 = 1", []
    return f"({alias}.owner_id IS NULL OR {alias}.owner_id = %s)", [u["id"]]


def accounts(u: dict, hidden: bool = False, kind: str = None) -> list[dict]:
    where, args = _visible(u)
    if not hidden:
        where += " AND a.hidden = 0"
    if kind:
        where += " AND a.kind = %s"
        args.append(kind)
    rows = db.q(f"SELECT a.* FROM mny_accounts a WHERE {where} ORDER BY a.position, a.kind, a.name", args)
    return [_acct(r) for r in rows]


def signed(a: dict, balance=None) -> Decimal:
    """What the account adds to the net worth, in its own currency: its value, or minus what is owed."""
    b = Decimal(a["balance"] if balance is None else balance)
    return b if a["is_asset"] else -abs(b)


def estimate(a: dict, on: dt.date = None) -> Decimal | None:
    """A house's or a car's value today from its last valuation and its yearly change (details.yearlyRate), when it
    has both; None otherwise."""
    r = (a.get("details") or {}).get("yearlyRate")
    if r in (None, 0) or a["source"] != "manual":
        return None
    last = db.one("SELECT day, balance FROM mny_balances WHERE account_id = %s AND source IN ('manual', 'sync') "
                  "ORDER BY day DESC LIMIT 1", (a["id"],))
    if not last:
        return None
    years = Decimal(((on or dt.date.today()) - last["day"]).days) / Decimal("365.25")
    if years <= 0:
        return None
    return (Decimal(last["balance"]) * _growth(Decimal(str(r)), years)).quantize(CENT)


def _growth(pct: Decimal, years: Decimal) -> Decimal:
    """(1 + pct/100) ** years, for a fractional number of years."""
    import math
    return Decimal(str(math.pow(float(1 + pct / 100), float(years))))


# an account Monarch Money has not heard from its bank about for longer than this is flagged: its link to the bank
# may be broken (a changed password, a new security question, the bank's own outage)
STALE_HOURS = 48
STALE_WHY = {"disconnected": "Monarch Money's link to the bank was cut", "update": "Monarch Money needs the bank sign-in fixed",
             "old": "Monarch Money has not heard from the bank in over two days"}


def bank_links(aids) -> dict:
    """{account id: its mny_bank_links row} for the accounts given."""
    aids = [int(x) for x in aids]
    if not aids:
        return {}
    return {r["account_id"]: r for r in db.q(f"SELECT * FROM mny_bank_links WHERE account_id IN ({db.marks(len(aids))})", aids)}


def _utc_iso(t) -> str | None:
    return t.isoformat() + "Z" if t else None


def bank_link(a: dict, r: dict | None) -> dict | None:
    """An account from Monarch Money's link to its bank, as Monarch reported it at the last sync: when Monarch last
    heard from the bank (refreshedAt, UTC), and stale: why it is flagged (disconnected, update: the bank sign-in needs
    fixing in Monarch, old: not heard from in over STALE_HOURS by the time of that sync), or None. Not flagged: closed,
    not linked to a bank (typed in at Monarch, a value Monarch looks up, its updates turned off) or asked to be quiet."""
    if a["source"] != "monarch" or not r:
        return None
    hours = None
    if r["refreshed_at"]:
        hours = max(0, int((r["seen_at"] - r["refreshed_at"]).total_seconds() // 3600))
    why = None
    if r["linked"] and not a["closed"] and not r["quiet"]:
        why = ("disconnected" if r["disconnected_at"] else "update" if r["update_required"]
               else "old" if hours is not None and hours > STALE_HOURS else None)
    return {"linked": bool(r["linked"]), "refreshedAt": _utc_iso(r["refreshed_at"]), "checkedAt": _utc_iso(r["seen_at"]),
            "hoursBehind": hours, "updateRequired": bool(r["update_required"]),
            "disconnectedAt": _utc_iso(r["disconnected_at"]), "institutionStatus": r["institution_status"],
            "quiet": bool(r["quiet"]), "stale": why, "why": STALE_WHY.get(why)}


def stale_accounts(u: dict) -> list[dict]:
    """The accounts this person sees (not hidden) whose link to the bank Monarch Money reports as broken or behind."""
    rows = [a for a in accounts(u) if a["source"] == "monarch" and not a["closed"]]
    links = bank_links([a["id"] for a in rows])
    out = []
    for a in rows:
        b = bank_link(a, links.get(a["id"]))
        if b and b["stale"]:
            out.append({"id": a["id"], "name": a["name"], "institution": a["institution"], "stale": b["stale"],
                        "why": b["why"], "refreshedAt": b["refreshedAt"]})
    return out


def quiet_bank_link(aid: int, quiet: bool) -> None:
    db.ex("UPDATE mny_bank_links SET quiet = %s WHERE account_id = %s", (1 if quiet else 0, aid))


def account_public(a: dict, u: dict, extra: dict = None, links: dict = None) -> dict:
    """links: bank_links() of the accounts listed (otherwise this one's is looked up)."""
    label, _asset, _m = KINDS.get(a["kind"], (a["kind"], a["is_asset"], ()))
    fx = rate(a["currency"])
    loan = None
    if a.get("loan_id"):
        lr = account_row(a["loan_id"])
        if lr and can_read(u, lr):
            loan = {"id": lr["id"], "name": lr["name"], "balance": n2(lr["balance"]), "currency": lr["currency"]}
    out = {
        "id": a["id"], "name": a["name"], "institution": a["institution"], "kind": a["kind"], "kindLabel": label,
        "subtype": a["subtype"], "isAsset": bool(a["is_asset"]), "balance": n2(a["balance"]), "currency": a["currency"],
        "value": n2(signed(a) * fx), "balanceAt": a["balance_at"].isoformat() if a.get("balance_at") else None,
        "inNetWorth": bool(a["in_net_worth"]), "hidden": bool(a["hidden"]), "closed": bool(a["closed"]),
        "mask": a["mask"], "source": a["source"], "household": a["owner_id"] is None, "details": a.get("details") or {},
        "loan": loan, "writable": can_write(u, a), "position": a["position"], "group": GROUP_OF.get(a["kind"], "asset"),
        "track": a.get("track") or "transactions",
    }
    if a["source"] == "monarch":
        out["bank"] = bank_link(a, (links if links is not None else bank_links([a["id"]])).get(a["id"]))
    if a["kind"] in THINGS:
        e = estimate(a)
        out["estimate"] = n2(e)
        if loan:
            owed = abs(Decimal(lr["balance"])) * rate(lr["currency"])
            worth = (e if e is not None else Decimal(a["balance"])) * fx
            out["equity"] = n2(worth - owed)
    if extra:
        out.update(extra)
    return out


ACCOUNT_FIELDS = ("name", "institution", "kind", "subtype", "balance", "currency", "inNetWorth", "hidden", "closed",
                  "mask", "details", "loanId", "position", "household", "track", "flagStale")


def track(v, kind: str) -> str:
    """'value' (the balance or value alone) or 'transactions' (its transactions too); left out, the kind's usual one."""
    if v in (None, ""):
        return TRACK_DEFAULT.get(kind, "value")
    if v not in TRACKS:
        raise Invalid("What to follow: value or transactions")
    return v


def _loan(u: dict, v) -> int | None:
    if v in (None, "", 0):
        return None
    lr = account_row(v)
    if not can_read(u, lr) or lr["kind"] not in ("loan", "other_liability"):
        raise Invalid("The loan: one of the loans you see")
    return lr["id"]


def create_account(u: dict, b: dict) -> dict:
    household = bool(b.get("household", may_add(u, True)))
    _need(may_add(u, household), "You may not add accounts here" if household else "Viewers keep no accounts of their own")
    name = text(b.get("name"), 255, "The name")
    if not name:
        raise Invalid("Give the account a name")
    kind = str(b.get("kind") or "cash")
    if kind not in KINDS:
        raise Invalid("The kind: " + ", ".join(KINDS))
    bal = money(b.get("balance"), "The balance", required=False) or Decimal(0)
    cur = currency(b.get("currency") or home_currency())
    details = _details(b.get("details"))
    aid = db.ex("INSERT INTO mny_accounts (owner_id, source, name, institution, kind, subtype, is_asset, balance, currency, "
                "balance_at, in_net_worth, hidden, mask, details, loan_id, track, created_by) "
                "VALUES (%s, 'manual', %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s, %s)",
                (None if household else u["id"], name, text(b.get("institution"), 255, "The institution"), kind,
                 text(b.get("subtype"), 64, "The subtype"), 1 if KINDS[kind][1] else 0, bal, cur,
                 flag(b.get("inNetWorth", True)), flag(b.get("hidden")), text(b.get("mask"), 8, "The last digits"),
                 json.dumps(details) if details else None, _loan(u, b.get("loanId")), track(b.get("track"), kind), u["id"]))
    set_balance(aid, dt.date.today(), bal, "sync" if kind == "investment" else "manual")  # an investment account: its holdings
    return account_row(aid)


def update_account(u: dict, a: dict, b: dict) -> dict:
    _need(can_write(u, a))
    sets, args = [], []
    monarch = a["source"] == "monarch"

    def put(col, v):
        sets.append(f"{col} = %s")
        args.append(v)
    if "name" in b:
        n = text(b["name"], 255, "The name")
        if not n:
            raise Invalid("Give the account a name")
        put("name", n)
    for k, col, lim in (("institution", "institution", 255), ("subtype", "subtype", 64), ("mask", "mask", 8)):
        if k in b and not monarch:
            put(col, text(b[k], lim, k))
    if "kind" in b and not monarch:
        if b["kind"] not in KINDS:
            raise Invalid("The kind: " + ", ".join(KINDS))
        put("kind", b["kind"])
        put("is_asset", 1 if KINDS[b["kind"]][1] else 0)
    if "currency" in b and not monarch:
        put("currency", currency(b["currency"]))
    for k, col in (("inNetWorth", "in_net_worth"), ("hidden", "hidden"), ("closed", "closed")):
        if k in b:
            put(col, flag(b[k]))
    if "position" in b:
        put("position", int(number(b["position"], "The position", 0) or 0))
    if "details" in b:
        d = _details(b["details"], a.get("details"))
        put("details", json.dumps(d) if d else None)
    if "flagStale" in b and monarch:
        quiet_bank_link(a["id"], not flag(b["flagStale"]))
    if "loanId" in b:
        put("loan_id", _loan(u, b["loanId"]))
    if "track" in b:
        put("track", track(b["track"], b.get("kind") or a["kind"]))
    if "household" in b and bool(b["household"]) != (a["owner_id"] is None):
        to_household = bool(b["household"])
        _need(shared_users.can_write(u), "Only editors move accounts between the household and a person")
        if not to_household and a["owner_id"] is None:
            put("owner_id", u["id"])
        else:
            put("owner_id", None)
    if sets:
        db.ex(f"UPDATE mny_accounts SET {', '.join(sets)} WHERE id = %s", (*args, a["id"]))
    if "balance" in b and not monarch:
        set_balance(a["id"], dt.date.today(), money(b["balance"], "The balance"), "sync" if a["kind"] == "investment" else "manual")
    return account_row(a["id"])


def account_info(u: dict, a: dict) -> dict:
    """What the household keeps to deal with the account's bank (INFO_FIELDS), for whoever sees the account."""
    _need(can_read(u, a))
    r = db.one("SELECT info FROM mny_account_info WHERE account_id = %s", (a["id"],))
    try:
        info = json.loads(r["info"]) if r else {}
    except ValueError:
        info = {}
    return {k: info[k] for k in INFO_FIELDS if info.get(k) not in (None, "")}


def set_account_info(u: dict, a: dict, b: dict) -> dict:
    """Change the fields given (empty: removed), the others stay; any account, one from Monarch Money too."""
    _need(can_write(u, a))
    if not isinstance(b, dict):
        raise Invalid("An object is expected")
    info = account_info(u, a)
    for k, lim in INFO_FIELDS.items():
        if k not in b:
            continue
        v = text(b[k], lim, k)
        if k == "openedOn" and v:
            try:
                v = dt.date.fromisoformat(v).isoformat()
            except ValueError:
                raise Invalid("Opened on: a date like 2020-05-31") from None
        if k == "website" and v and not re.match(r"^https?://", v, re.I):
            v = "https://" + v
        if v:
            info[k] = v
        else:
            info.pop(k, None)
    if info:
        db.ex("INSERT INTO mny_account_info (account_id, info, updated_by) VALUES (%s, %s, %s) "
              "ON DUPLICATE KEY UPDATE info = VALUES(info), updated_by = VALUES(updated_by)", (a["id"], json.dumps(info), u["id"]))
    else:
        db.ex("DELETE FROM mny_account_info WHERE account_id = %s", (a["id"],))
    return info


def delete_account(u: dict, a: dict) -> None:
    _need(can_write(u, a))
    if a["source"] == "monarch":
        raise Forbidden("This account comes from Monarch Money: hide it instead (it would come back with the next sync)")
    db.ex("UPDATE mny_accounts SET loan_id = NULL WHERE loan_id = %s", (a["id"],))
    db.ex("DELETE FROM mny_accounts WHERE id = %s", (a["id"],))  # its balances, transactions and holdings go with it
    related.forget("asset", a["id"])


def set_balance(aid: int, on: dt.date, balance: Decimal, source: str = "sync", note: str = None) -> None:
    """The account's value on a day; the account's own balance follows when it is the latest day it has."""
    db.ex("INSERT INTO mny_balances (account_id, day, balance, source, note) VALUES (%s, %s, %s, %s, %s) "
          "ON DUPLICATE KEY UPDATE balance = VALUES(balance), source = VALUES(source), note = VALUES(note)",
          (aid, on, balance, source, note))
    latest = db.one("SELECT MAX(day) AS d FROM mny_balances WHERE account_id = %s", (aid,))["d"]
    if latest is None or on >= latest:
        db.ex("UPDATE mny_accounts SET balance = %s, balance_at = NOW() WHERE id = %s", (balance, aid))


# ---- a house's or a car's value over time

def valuations(u: dict, a: dict, limit: int = 400) -> list[dict]:
    rows = db.q("SELECT day, balance, source, note FROM mny_balances WHERE account_id = %s ORDER BY day DESC LIMIT %s",
                (a["id"], limit))
    return [{"day": r["day"].isoformat(), "value": n2(r["balance"]), "source": r["source"], "note": r["note"]} for r in rows]


def add_valuation(u: dict, a: dict, b: dict) -> None:
    _need(can_write(u, a))
    if a["source"] == "monarch":
        raise Forbidden("Monarch Money keeps this one's value up to date")
    on = day(b.get("day") or dt.date.today().isoformat())
    if on > dt.date.today():
        raise Invalid("A value is for today or a day before")
    set_balance(a["id"], on, money(b.get("value"), "The value"), "manual", text(b.get("note"), 255, "The note"))


def remove_valuation(u: dict, a: dict, on) -> None:
    _need(can_write(u, a))
    if a["source"] == "monarch":
        raise Forbidden("Monarch Money keeps this one's value up to date")
    db.ex("DELETE FROM mny_balances WHERE account_id = %s AND day = %s", (a["id"], day(on)))
    last = db.one("SELECT balance FROM mny_balances WHERE account_id = %s ORDER BY day DESC LIMIT 1", (a["id"],))
    db.ex("UPDATE mny_accounts SET balance = %s WHERE id = %s", (last["balance"] if last else 0, a["id"]))


# ---- the net worth

def net_worth(u: dict) -> dict:
    """Now: the assets, what is owed and the difference, by kind, in the household's currency."""
    by_kind: dict = {}
    by_group: dict = {}
    assets = owed = Decimal(0)
    for a in accounts(u):
        if not a["in_net_worth"] or a["closed"]:
            continue
        e = estimate(a) if a["kind"] in THINGS else None
        v = signed(a, e) * rate(a["currency"])
        by_kind[a["kind"]] = by_kind.get(a["kind"], Decimal(0)) + v
        g = GROUP_OF.get(a["kind"], "asset")
        by_group[g] = by_group.get(g, Decimal(0)) + v
        if v >= 0:
            assets += v
        else:
            owed += -v
    return {"currency": home_currency(), "assets": n2(assets), "liabilities": n2(owed), "netWorth": n2(assets - owed),
            "byKind": [{"kind": k, "label": KINDS[k][0], "value": n2(v)} for k, v in sorted(by_kind.items(), key=lambda x: -abs(x[1]))],
            "byGroup": [{"group": g, "label": name, "value": n2(by_group[g])} for g, name, _k in GROUPS if g in by_group]}


def history(u: dict, days: int = 365, kind: str = None, account_id: int = None) -> list[dict]:
    """The net worth (or one kind's, or one account's value) day by day: each account's last known value carried
    forward, in the household's currency. Points every day for up to 3 months, then every week, then every month."""
    days = max(7, min(int(days or 365), 3660))
    today = dt.date.today()
    start = today - dt.timedelta(days=days)
    accts = [a for a in accounts(u, hidden=True) if a["in_net_worth"] and (not kind or a["kind"] == kind)
             and (account_id is None or a["id"] == account_id)]
    if account_id is not None:
        accts = [a for a in accounts(u, hidden=True) if a["id"] == account_id]
    if not accts:
        return []
    ids = [a["id"] for a in accts]
    fx = {a["id"]: rate(a["currency"]) for a in accts}
    by_id = {a["id"]: a for a in accts}
    rows = db.q(f"SELECT account_id, day, balance FROM mny_balances WHERE account_id IN ({db.marks(len(ids))}) AND day <= %s "
                f"ORDER BY day", (*ids, today))
    step = 1 if days <= 92 else 7 if days <= 730 else 30
    points, cur, i = [], {}, 0
    rows = list(rows)
    # what each account stood at before the first day shown
    while i < len(rows) and rows[i]["day"] < start:
        cur[rows[i]["account_id"]] = rows[i]["balance"]
        i += 1
    d = start
    while d <= today:
        while i < len(rows) and rows[i]["day"] <= d:
            cur[rows[i]["account_id"]] = rows[i]["balance"]
            i += 1
        if (today - d).days % step == 0:
            total = sum((signed(by_id[k], v) * fx[k] for k, v in cur.items()), Decimal(0))
            points.append({"day": d.isoformat(), "value": n2(total), "known": bool(cur)})
        d += dt.timedelta(days=1)
    first = next((n for n, p in enumerate(points) if p["known"]), len(points))
    return [{"day": p["day"], "value": p["value"]} for p in points[first:]]


# ---- transactions

def tx_row(tid) -> dict | None:
    try:
        tid = int(tid)
    except (TypeError, ValueError):
        return None
    return db.one("SELECT t.*, a.owner_id, a.name AS account_name, a.currency, a.source AS account_source, "
                  "EXISTS (SELECT 1 FROM mny_reconciled r WHERE r.transaction_id = t.id) AS reconciled "
                  "FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE t.id = %s", (tid,))


def transaction(u: dict, tid) -> dict:
    t = tx_row(tid)
    if not t or not can_read(u, t):
        raise NotFound("No such transaction")
    return t


def tx_public(t: dict, u: dict = None) -> dict:
    try:
        tags = json.loads(t["tags"]) if t.get("tags") else []
    except ValueError:
        tags = []
    out = {"id": t["id"], "accountId": t["account_id"], "account": t.get("account_name"), "day": t["day"].isoformat(),
           "amount": n2(t["amount"]), "currency": t.get("currency"), "merchant": t["merchant"], "description": t["description"],
           "category": t["category"], "group": t["category_group"], "notes": t["notes"], "tags": tags,
           "pending": bool(t["pending"]), "hidden": bool(t["hidden"]),
           "edited": bool(t["edited"]), "source": t["source"], "reconciled": bool(t.get("reconciled"))}
    if u is not None:
        out["writable"] = can_write(u, t)
    return out


def words(*parts) -> str:
    return " ".join(str(p) for p in parts if p).lower()[:4000]


_NUM = r"\$?\s*(\d[\d,]*(?:\.\d{1,2})?)"


def amount_range(s: str | None) -> tuple[Decimal | None, Decimal | None] | None:
    """An amount as typed, money out or in alike: "280", "$280.00", "100-200", "100..200", ">500", "<=20". (low,
    high), either None for no bound; None when it is not an amount."""
    s = (s or "").strip().replace(" ", "")
    if not s:
        return None
    num = lambda x: Decimal(x.replace(",", ""))  # noqa: E731
    m = re.fullmatch(_NUM + r"(?:-|\.\.|to)" + _NUM, s, re.I)
    if m:
        lo, hi = sorted((num(m[1]), num(m[2])))
        return lo, hi
    m = re.fullmatch(r"(>=?|<=?)" + _NUM, s)
    if m:
        return (num(m[2]), None) if m[1].startswith(">") else (None, num(m[2]))
    m = re.fullmatch(_NUM, s)
    return (num(m[1]), num(m[1])) if m else None


def _tx_filter(u: dict, q: str = "", account: int = None, category: str = None, start=None, end=None,
               flow: str = None, hidden: bool = False, reconciled: str = None, amount: str = None) -> tuple[str, list]:
    """amount: an amount or a range (amount_range); in q, a word with $ or cents, a range or > < is an amount too, and
    a bare number is an amount or a word (the last digits in the bank's text)."""
    where, args = _visible(u)
    where += " AND a.track = 'transactions'"  # an account followed by its value alone keeps its transactions out of sight
    if not hidden:
        where += " AND t.hidden = 0"
    if account:
        where += " AND t.account_id = %s"
        args.append(int(account))
    if category:
        if category == "-":
            where += " AND (t.category IS NULL OR t.category = '')"
        else:
            where += " AND t.category = %s"
            args.append(category)
    if start:
        where += " AND t.day >= %s"
        args.append(day(start))
    if end:
        where += " AND t.day <= %s"
        args.append(day(end))
    if flow == "out":
        where += " AND t.amount < 0"
    elif flow == "in":
        where += " AND t.amount > 0"
    if reconciled in ("yes", "no"):
        where += f" AND {'' if reconciled == 'yes' else 'NOT '}EXISTS (SELECT 1 FROM mny_reconciled r WHERE r.transaction_id = t.id)"
    if amount not in (None, ""):
        r = amount_range(str(amount))
        if not r:
            raise Invalid("The amount: a number (280.00) or a range (100-200, >500, <20)")
        where, args = _amount_where(where, args, r)
    for w in (q or "").lower().split()[:8]:
        like = "%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        r = amount_range(w)
        if r and re.fullmatch(r"\d+", w):  # 7834: the amount, or the last digits in the bank's text
            where += " AND (ABS(t.amount) = %s OR t.words LIKE %s)"
            args += [r[0], like]
        elif r:
            where, args = _amount_where(where, args, r)
        else:
            where += " AND t.words LIKE %s"
            args.append(like)
    return where, args


def _amount_where(where: str, args: list, r: tuple) -> tuple[str, list]:
    lo, hi = r
    if lo is not None:
        where += " AND ABS(t.amount) >= %s"
        args.append(lo)
    if hi is not None:
        where += " AND ABS(t.amount) <= %s"
        args.append(hi)
    return where, args


def find_transactions(u: dict, q: str = "", account: int = None, category: str = None, start=None, end=None,
                      flow: str = None, limit: int = 100, offset: int = 0, hidden: bool = False, reconciled: str = None,
                      amount: str = None) -> dict:
    where, args = _tx_filter(u, q, account, category, start, end, flow, hidden, reconciled, amount)
    base = f"FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE {where}"
    total = db.one(f"SELECT count(*) AS n, COALESCE(SUM(t.amount), 0) AS s {base}", args)
    rows = db.q(f"SELECT t.*, a.owner_id, a.name AS account_name, a.currency, EXISTS (SELECT 1 FROM mny_reconciled r WHERE r.transaction_id = t.id) AS reconciled {base} ORDER BY t.day DESC, t.id DESC LIMIT %s OFFSET %s",
                (*args, max(1, min(int(limit), 1000)), max(0, int(offset))))
    return {"items": with_transfers([tx_public(r, u) for r in rows], u), "total": total["n"], "sum": n2(total["s"])}


def with_transfers(items: list[dict], u: dict) -> list[dict]:
    """Each transaction that is half of a transfer gets transfer: {id, accountId, account, how} (the other half; its
    account left out when it is someone else's private one); and each gets recurring: the household's recurring
    transaction it is ({id, name, subscription}), or None."""
    from app import recurring, transfers
    recurring.mark(items, u)
    halves = transfers.halves_of([t["id"] for t in items])
    others = {}
    if halves:
        ids = list({o for o, _h in halves.values()})
        for r in db.q(f"SELECT t.id, t.account_id, a.name, a.owner_id FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id "
                      f"WHERE t.id IN ({db.marks(len(ids))})", ids):
            others[r["id"]] = r
    for t in items:
        if t["id"] in halves:
            oid, how = halves[t["id"]]
            o = others.get(oid)
            seen = bool(o) and can_read(u, o)
            t["transfer"] = {"id": oid if seen else None, "accountId": o["account_id"] if seen else None,
                             "account": o["name"] if seen else None, "how": how}
    return items


def _move_balance(aid: int, delta: Decimal) -> None:
    """A manual account that follows its transactions: its balance moves with each one added, changed or deleted."""
    a = account_row(aid)
    if delta and a and a["source"] == "manual" and a.get("track") == "transactions":
        set_balance(aid, dt.date.today(), Decimal(a["balance"]) + delta, "manual")


def create_transaction(u: dict, a: dict, b: dict) -> dict:
    _need(can_write(u, a))
    if a.get("track") != "transactions":
        raise Invalid("This account follows its value alone: change it to follow its transactions first")
    on = day(b.get("day") or dt.date.today().isoformat())
    amt = money(b.get("amount"))
    merchant = text(b.get("merchant"), 255, "The payee")
    cat = text(b.get("category"), 128, "The category")
    notes = text(b.get("notes"), 4000, "The notes")
    grp = text(b.get("group"), 128, "The group")
    # the rules: a payee renamed, and the category and hidden when not given
    ch = _rule_changes(db.q("SELECT * FROM mny_rules WHERE enabled = 1 ORDER BY position, id"),
                       {"account_id": a["id"], "amount": amt, "merchant": merchant, "description": None})
    merchant = ch.get("merchant", merchant)
    if not cat and ch.get("category"):
        cat, grp = ch["category"], _group_of_category(ch["category"])
    hidden = flag(b["hidden"]) if "hidden" in b else ch.get("hidden", 0)
    tid = db.ex("INSERT INTO mny_transactions (account_id, source, day, amount, merchant, category, category_group, notes, hidden, "
                "words, created_by) VALUES (%s, 'manual', %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (a["id"], on, amt, merchant, cat, grp, notes, hidden, words(merchant, cat, notes, a["name"]), u["id"]))
    _move_balance(a["id"], amt)
    from app import transfers
    transfers.link("t.id = %s", (tid,))
    return tx_row(tid)


def update_transaction(u: dict, t: dict, b: dict) -> dict:
    """The category, the notes, hidden (left out of the sums) and the payee's name: kept as changed here, also by
    the next sync. A manual account's transaction also takes a new date and amount."""
    _need(can_write(u, t))
    sets, args = [], []
    for k, col, lim in (("category", "category", 128), ("group", "category_group", 128), ("merchant", "merchant", 255),
                        ("notes", "notes", 4000)):
        if k in b:
            sets.append(f"{col} = %s")
            args.append(text(b[k], lim, k))
    if "hidden" in b:
        sets.append("hidden = %s")
        args.append(flag(b["hidden"]))
    if "reconciled" in b:  # not a change to what the transaction says: it does not make it "edited"
        set_reconciled(u, [t["id"]], flag(b["reconciled"]))
    if t["source"] == "manual":
        if "day" in b:
            sets.append("day = %s")
            args.append(day(b["day"]))
        if "amount" in b:
            sets.append("amount = %s")
            args.append(money(b["amount"]))
    if sets:
        db.ex(f"UPDATE mny_transactions SET {', '.join(sets)}, edited = 1 WHERE id = %s", (*args, t["id"]))
        n = tx_row(t["id"])
        db.ex("UPDATE mny_transactions SET words = %s WHERE id = %s",
              (words(n["merchant"], n["description"], n["category"], n["category_group"], n["notes"], n["account_name"]), t["id"]))
        if t["source"] == "manual":
            _move_balance(t["account_id"], Decimal(n["amount"]) - Decimal(t["amount"]))
    return tx_row(t["id"])


def set_reconciled(u: dict, ids: list, on: bool) -> int:
    """Mark transactions reconciled (checked against the statement) or not; those this person may change. How many."""
    n = 0
    for tid in ids[:1000]:
        t = tx_row(tid)
        if not t or not can_read(u, t) or not can_write(u, t):
            continue
        if on:
            db.ex("INSERT IGNORE INTO mny_reconciled (transaction_id, by_user) VALUES (%s, %s)", (t["id"], u["id"]))
        else:
            db.ex("DELETE FROM mny_reconciled WHERE transaction_id = %s", (t["id"],))
        n += 1
    return n


def delete_transaction(u: dict, t: dict) -> None:
    _need(can_write(u, t))
    if t["source"] != "manual":
        raise Forbidden("This transaction comes from Monarch Money: hide it instead")
    db.ex("DELETE FROM mny_transactions WHERE id = %s", (t["id"],))
    _move_balance(t["account_id"], -Decimal(t["amount"]))


def categories(u: dict) -> list[dict]:
    """Every category (app/categories.py): those the transactions have and those added here."""
    from app import categories as cats
    return cats.items(u)


def _not_transfer() -> str:
    """Neither half of a transfer between the household's own accounts: linked (app/transfers.py), or in Monarch's
    Transfers group."""
    return ("(t.category_group IS NULL OR LOWER(t.category_group) NOT IN ('transfers', 'transfer')) "
            "AND NOT EXISTS (SELECT 1 FROM mny_transfers x WHERE x.out_id = t.id OR x.in_id = t.id)")


def spending(u: dict, start, end) -> dict:
    """Money out and in between two days, by category (transfers between the household's own accounts left out),
    in the household's currency."""
    where, args = _tx_filter(u, start=start, end=end)
    rows = db.q(f"SELECT t.category, MAX(t.category_group) AS grp, a.currency, SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS out_, "
                f"SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) AS in_, count(*) AS n "
                f"FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE {where} AND {_not_transfer()} "
                f"GROUP BY t.category, a.currency", args)
    cats: dict = {}
    for r in rows:
        fx = rate(r["currency"])
        c = cats.setdefault(r["category"] or "", {"category": r["category"], "group": r["grp"], "out": Decimal(0), "in": Decimal(0), "count": 0})
        c["out"] += Decimal(r["out_"]) * fx
        c["in"] += Decimal(r["in_"]) * fx
        c["count"] += r["n"]
    items = sorted(cats.values(), key=lambda c: -(c["out"] - c["in"]))
    spent = sum((c["out"] for c in items), Decimal(0))
    earned = sum((c["in"] for c in items), Decimal(0))
    return {"currency": home_currency(), "from": day(start).isoformat(), "to": day(end).isoformat(),
            "spent": n2(spent), "income": n2(earned), "net": n2(earned - spent),
            "categories": [{"category": c["category"], "group": c["group"], "spent": n2(c["out"]), "income": n2(c["in"]),
                            "count": c["count"]} for c in items]}


def cash_flow(u: dict, months: int = 12) -> list[dict]:
    """Money in and out month by month, the current month last."""
    months = max(1, min(int(months or 12), 60))
    today = dt.date.today()
    first = dt.date(today.year, today.month, 1)
    for _ in range(months - 1):
        first = (first - dt.timedelta(days=1)).replace(day=1)
    where, args = _tx_filter(u, start=first, end=today)
    rows = db.q(f"SELECT DATE_FORMAT(t.day, '%%Y-%%m') AS m, a.currency, SUM(CASE WHEN t.amount < 0 THEN -t.amount ELSE 0 END) AS out_, "
                f"SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) AS in_ FROM mny_transactions t "
                f"JOIN mny_accounts a ON a.id = t.account_id WHERE {where} AND {_not_transfer()} GROUP BY m, a.currency", args)
    by: dict = {}
    for r in rows:
        fx = rate(r["currency"])
        m = by.setdefault(r["m"], [Decimal(0), Decimal(0)])
        m[0] += Decimal(r["out_"]) * fx
        m[1] += Decimal(r["in_"]) * fx
    out, d = [], first
    while d <= today:
        k = d.strftime("%Y-%m")
        o, i = by.get(k, [Decimal(0), Decimal(0)])
        out.append({"month": k, "spent": n2(o), "income": n2(i), "net": n2(i - o)})
        d = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


# ---- holdings and the portfolio

def holding_row(hid) -> dict | None:
    try:
        hid = int(hid)
    except (TypeError, ValueError):
        return None
    return db.one("SELECT h.*, a.owner_id, a.name AS account_name, a.source AS account_source, a.currency AS account_currency "
                  "FROM mny_holdings h JOIN mny_accounts a ON a.id = h.account_id WHERE h.id = %s", (hid,))


def holding(u: dict, hid) -> dict:
    h = holding_row(hid)
    if not h or not can_read(u, h):
        raise NotFound("No such holding")
    return h


def holdings(u: dict, account_id: int = None) -> list[dict]:
    where, args = _visible(u)
    if account_id:
        where += " AND h.account_id = %s"
        args.append(int(account_id))
    return db.q(f"SELECT h.*, a.owner_id, a.name AS account_name, a.source AS account_source, a.currency AS account_currency, "
                f"q.price AS q_price, q.previous_close AS q_prev, q.currency AS q_currency, q.name AS q_name, q.market_time AS q_time, "
                f"q.error AS q_error FROM mny_holdings h JOIN mny_accounts a ON a.id = h.account_id "
                f"LEFT JOIN mny_quotes q ON q.symbol = h.symbol WHERE {where} AND a.hidden = 0 AND a.closed = 0 "
                f"ORDER BY h.symbol, h.name", args)


def priced(h: dict) -> dict:
    """A holding with its price (the quote's, else the one kept with it), value, the day's change and the gain, in
    the currency it is quoted in and in the household's."""
    quoted = h.get("q_price") is not None
    price = Decimal(h["q_price"]) if quoted else (Decimal(h["price"]) if h.get("price") is not None else None)
    cur = (h.get("q_currency") if quoted else None) or h.get("account_currency") or home_currency()
    shares = Decimal(h["shares"])
    if h["kind"] == "cash" and price is None:
        price = Decimal(1)
    value = shares * price if price is not None else None
    fx = rate(cur)
    change = None
    if quoted and h.get("q_prev"):
        change = (Decimal(h["q_price"]) - Decimal(h["q_prev"])) * shares
    basis = Decimal(h["cost_basis"]) if h.get("cost_basis") is not None else None
    return {"id": h["id"], "accountId": h["account_id"], "account": h["account_name"], "symbol": h["symbol"],
            "name": h["name"] or h.get("q_name"), "kind": h["kind"], "shares": float(shares),
            "price": None if price is None else float(price), "currency": cur, "quoted": quoted,
            "quoteError": h.get("q_error"), "value": n2(value), "homeValue": n2(value * fx) if value is not None else None,
            "dayChange": n2(change * fx) if change is not None else None,
            "dayChangePct": float(((Decimal(h["q_price"]) / Decimal(h["q_prev"])) - 1) * 100) if quoted and h.get("q_prev") else None,
            "costBasis": n2(basis), "gain": n2((value - basis) * fx) if value is not None and basis is not None else None,
            "source": h["source"], "writable": None}


def portfolio(u: dict, account_id: int = None) -> dict:
    """Every holding the person sees, priced, with the totals and the same symbol across accounts added up."""
    items = []
    for h in holdings(u, account_id):
        p = priced(h)
        p["writable"] = can_write(u, h) and h["source"] == "manual"
        items.append(p)
    total = sum((Decimal(str(p["homeValue"])) for p in items if p["homeValue"] is not None), Decimal(0))
    change = sum((Decimal(str(p["dayChange"])) for p in items if p["dayChange"] is not None), Decimal(0))
    basis_items = [p for p in items if p["gain"] is not None]
    gain = sum((Decimal(str(p["gain"])) for p in basis_items), Decimal(0))
    by_symbol: dict = {}
    for p in items:
        k = p["symbol"] or f"#{p['id']}"
        s = by_symbol.setdefault(k, {"symbol": p["symbol"], "name": p["name"], "kind": p["kind"], "shares": 0.0, "price": p["price"],
                                     "currency": p["currency"], "homeValue": 0.0, "dayChange": 0.0, "dayChangePct": p["dayChangePct"],
                                     "accounts": []})
        s["shares"] += p["shares"]
        s["homeValue"] = round(s["homeValue"] + (p["homeValue"] or 0), 2)
        s["dayChange"] = round(s["dayChange"] + (p["dayChange"] or 0), 2)
        if p["account"] not in s["accounts"]:
            s["accounts"].append(p["account"])
    alloc: dict = {}
    for p in items:
        alloc[p["kind"]] = alloc.get(p["kind"], 0.0) + (p["homeValue"] or 0)
    prev = total - change
    return {"currency": home_currency(), "value": n2(total), "dayChange": n2(change),
            "dayChangePct": float(change / prev * 100) if prev else None, "gain": n2(gain) if basis_items else None,
            "items": items, "bySymbol": sorted(by_symbol.values(), key=lambda s: -s["homeValue"]),
            "allocation": [{"kind": k, "value": round(v, 2)} for k, v in sorted(alloc.items(), key=lambda x: -x[1])]}


def _holding_fields(b: dict, partial: bool) -> dict:
    out = {}
    if "symbol" in b or not partial:
        out["symbol"] = symbol(b.get("symbol"))
    if "name" in b:
        out["name"] = text(b.get("name"), 255, "The name")
    if "kind" in b or not partial:
        k = str(b.get("kind") or "stock")
        if k not in HOLDING_KINDS:
            raise Invalid("The kind: " + ", ".join(HOLDING_KINDS))
        out["kind"] = k
    if "shares" in b or not partial:
        out["shares"] = number(b.get("shares"), "The number of shares", 8, required=True)
    if "costBasis" in b:
        out["cost_basis"] = money(b.get("costBasis"), "The cost basis", required=False)
    if "price" in b:
        out["price"] = number(b.get("price"), "The price", 6)
        out["price_at"] = dt.datetime.now() if out["price"] is not None else None
    if not partial and not out.get("symbol") and not out.get("name"):
        raise Invalid("Give the symbol (AAPL, VWCE.DE, BTC-USD) or, for something without one, a name and a price")
    return out


def create_holding(u: dict, a: dict, b: dict) -> dict:
    _need(can_write(u, a))
    if a["kind"] != "investment":
        raise Invalid("Holdings go in an investment account")
    if a["source"] == "monarch":
        raise Forbidden("The holdings of a Monarch Money account come from Monarch")
    f = _holding_fields(b, False)
    cols = ", ".join(f)
    hid = db.ex(f"INSERT INTO mny_holdings (account_id, source, {cols}) VALUES (%s, 'manual', {db.marks(len(f))})",
                (a["id"], *f.values()))
    return holding_row(hid)


def update_holding(u: dict, h: dict, b: dict) -> dict:
    _need(can_write(u, h))
    if h["source"] != "manual":
        raise Forbidden("This holding comes from Monarch Money")
    f = _holding_fields(b, True)
    if f:
        db.ex(f"UPDATE mny_holdings SET {', '.join(k + ' = %s' for k in f)} WHERE id = %s", (*f.values(), h["id"]))
    return holding_row(h["id"])


def delete_holding(u: dict, h: dict) -> None:
    _need(can_write(u, h))
    if h["source"] != "manual":
        raise Forbidden("This holding comes from Monarch Money")
    db.ex("DELETE FROM mny_holdings WHERE id = %s", (h["id"],))


def revalue_manual_investments(account_id: int = None) -> int:
    """A manual investment account is worth what it holds: its balance follows the quotes (today's row). One that
    holds nothing keeps the balance typed in, unless it is the account named (its last holding just went)."""
    n = 0
    for a in db.q("SELECT * FROM mny_accounts WHERE kind = 'investment' AND source = 'manual'"):
        rows = db.q("SELECT h.*, a.currency AS account_currency, a.name AS account_name, q.price AS q_price, "
                    "q.previous_close AS q_prev, q.currency AS q_currency, q.name AS q_name, q.error AS q_error "
                    "FROM mny_holdings h JOIN mny_accounts a ON a.id = h.account_id LEFT JOIN mny_quotes q ON q.symbol = h.symbol "
                    "WHERE h.account_id = %s", (a["id"],))
        if not rows and a["id"] != account_id:
            continue
        total = Decimal(0)
        for h in rows:
            p = priced(h)
            if p["value"] is not None:
                total += Decimal(str(p["value"])) * rate(p["currency"]) / rate(a["currency"])
        set_balance(a["id"], dt.date.today(), total.quantize(CENT), "sync")
        n += 1
    return n


def write_estimates() -> int:
    """Today's estimated value of each house and car with a yearly change, as a point of its history."""
    n = 0
    for a in db.q("SELECT * FROM mny_accounts WHERE kind IN ('property', 'vehicle', 'other_asset') AND source = 'manual'"):
        a = _acct(a)
        today = dt.date.today()
        row = db.one("SELECT source FROM mny_balances WHERE account_id = %s AND day = %s", (a["id"], today))
        if row and row["source"] != "estimate":
            continue
        e = estimate(a, today)
        if e is not None:
            set_balance(a["id"], today, e, "estimate")
            n += 1
    return n


# ---- rules: the household's, renaming and categorizing transactions as they come in

RULE_FIELDS = ("either", "merchant", "description")  # what is matched: the payee, the bank's own text, or either
RULE_HOW = ("contains", "is", "starts")
FLOWS = ("out", "in")


def rule_row(rid) -> dict | None:
    try:
        return db.one("SELECT * FROM mny_rules WHERE id = %s", (int(rid),))
    except (TypeError, ValueError):
        return None


def rule(u: dict, rid) -> dict:
    r = rule_row(rid)
    if not r or role_rank(u) < 1:
        raise NotFound("No such rule")
    return r


def rules(u: dict) -> list[dict]:
    """Every rule, in the order they are tried (anyone with a role sees them; editors change them)."""
    if role_rank(u) < 1:
        return []
    return db.q("SELECT * FROM mny_rules ORDER BY position, id")


def rule_public(r: dict, u: dict = None) -> dict:
    a = account_row(r["account_id"]) if r.get("account_id") else None
    out = {"id": r["id"], "position": r["position"], "enabled": bool(r["enabled"]), "field": r["field"], "how": r["how"],
           "pattern": r["pattern"], "accountId": r["account_id"],
           "account": a["name"] if a and (u is None or can_read(u, a)) else None, "flow": r["flow"],
           "amountMin": n2(r["amount_min"]), "amountMax": n2(r["amount_max"]), "setMerchant": r["set_merchant"],
           "setCategory": r["set_category"], "setHidden": None if r["set_hidden"] is None else bool(r["set_hidden"])}
    if u is not None:
        out["writable"] = shared_users.can_write(u)
    return out


def _rule_fields(u: dict, b: dict, old: dict = None) -> dict:
    """The columns of a rule from what came in (only what is in b; all of it for a new rule)."""
    c = {}
    if "pattern" in b or old is None:
        p = text(b.get("pattern"), 255, "The words to look for")
        if not p:
            raise Invalid("Give the words the payee or the bank's text has")
        c["pattern"] = p
    if "field" in b or old is None:
        f = b.get("field") or "either"
        if f not in RULE_FIELDS:
            raise Invalid("Look in: " + ", ".join(RULE_FIELDS))
        c["field"] = f
    if "how" in b or old is None:
        h = b.get("how") or "contains"
        if h not in RULE_HOW:
            raise Invalid("Match: " + ", ".join(RULE_HOW))
        c["how"] = h
    if "accountId" in b:
        aid = b.get("accountId")
        if aid in (None, "", 0):
            c["account_id"] = None
        else:
            a = account_row(aid)
            if not a or not can_read(u, a):
                raise Invalid("No such account")
            c["account_id"] = a["id"]
    if "flow" in b:
        fl = b.get("flow") or None
        if fl is not None and fl not in FLOWS:
            raise Invalid("Money out or in: out, in or nothing")
        c["flow"] = fl
    for k, col in (("amountMin", "amount_min"), ("amountMax", "amount_max")):
        if k in b:
            v = money(b.get(k), "The amount", required=False)
            c[col] = abs(v) if v is not None else None
    if "setMerchant" in b:
        c["set_merchant"] = text(b.get("setMerchant"), 255, "The new payee")
    if "setCategory" in b:
        c["set_category"] = text(b.get("setCategory"), 128, "The category")
    if "setHidden" in b:
        c["set_hidden"] = None if b.get("setHidden") in (None, "") else flag(b.get("setHidden"))
    if "enabled" in b:
        c["enabled"] = flag(b["enabled"])
    if "position" in b:
        c["position"] = int(number(b["position"], "The position", 0) or 0)
    merged = {**(old or {}), **c}
    if not (merged.get("set_merchant") or merged.get("set_category") or merged.get("set_hidden") is not None):
        raise Invalid("Say what the rule does: rename the payee, set the category or hide the transaction")
    lo, hi = merged.get("amount_min"), merged.get("amount_max")
    if lo is not None and hi is not None and lo > hi:
        raise Invalid("The smallest amount is more than the largest")
    return c


def create_rule(u: dict, b: dict) -> dict:
    _need(shared_users.can_write(u), "Only editors change the rules")
    c = _rule_fields(u, b)
    if "position" not in c:
        c["position"] = (db.one("SELECT COALESCE(MAX(position), 0) AS p FROM mny_rules")["p"] or 0) + 1
    c["created_by"] = u["id"]
    cols = list(c)
    rid = db.ex(f"INSERT INTO mny_rules ({', '.join(cols)}) VALUES ({db.marks(len(cols))})", [c[k] for k in cols])
    return rule_row(rid)


def update_rule(u: dict, r: dict, b: dict) -> dict:
    _need(shared_users.can_write(u), "Only editors change the rules")
    c = _rule_fields(u, b, r)
    if c:
        db.ex(f"UPDATE mny_rules SET {', '.join(k + ' = %s' for k in c)} WHERE id = %s", (*c.values(), r["id"]))
    return rule_row(r["id"])


def delete_rule(u: dict, r: dict) -> None:
    _need(shared_users.can_write(u), "Only editors change the rules")
    db.ex("DELETE FROM mny_rules WHERE id = %s", (r["id"],))


def order_rules(u: dict, ids: list) -> list[dict]:
    """The rules in this order (ids; the ones left out keep their place after them)."""
    _need(shared_users.can_write(u), "Only editors change the rules")
    try:
        ids = [int(i) for i in ids or []]
    except (TypeError, ValueError):
        raise Invalid("ids: the rules' ids, in order")
    rest = [r["id"] for r in db.q("SELECT id FROM mny_rules ORDER BY position, id") if r["id"] not in ids]
    with db.tx():
        for n, rid in enumerate(ids + rest, 1):
            db.ex("UPDATE mny_rules SET position = %s WHERE id = %s", (n, rid))
    return rules(u)


def _matches(r: dict, t: dict) -> bool:
    if r.get("account_id") and r["account_id"] != t["account_id"]:
        return False
    amt = Decimal(t["amount"])
    if r.get("flow") == "out" and amt >= 0 or r.get("flow") == "in" and amt <= 0:
        return False
    if r.get("amount_min") is not None and abs(amt) < Decimal(r["amount_min"]):
        return False
    if r.get("amount_max") is not None and abs(amt) > Decimal(r["amount_max"]):
        return False
    p = (r["pattern"] or "").lower()
    texts = {"merchant": [t.get("merchant")], "description": [t.get("description")]}.get(r["field"], [t.get("merchant"), t.get("description")])
    for s in texts:
        s = (s or "").lower().strip()
        if not s:
            continue
        if r["how"] == "is" and s == p or r["how"] == "starts" and s.startswith(p) or r["how"] == "contains" and p in s:
            return True
    return False


def _rule_changes(rs: list[dict], t: dict) -> dict:
    """What the rules make of one transaction: {merchant?, category?, hidden?}, the first rule that sets each winning."""
    out = {}
    for r in rs:
        if not r["enabled"] or not _matches(r, t):
            continue
        if r["set_merchant"] and "merchant" not in out:
            out["merchant"] = r["set_merchant"]
        if r["set_category"] and "category" not in out:
            out["category"] = r["set_category"]
        if r["set_hidden"] is not None and "hidden" not in out:
            out["hidden"] = int(r["set_hidden"])
    return out


def _group_of_category(name: str) -> str | None:
    k = db.one("SELECT grp FROM mny_categories WHERE name = %s", (name,))
    if k and k["grp"]:
        return k["grp"]
    g = db.one("SELECT category_group AS g, count(*) AS n FROM mny_transactions WHERE category = %s AND category_group IS NOT NULL "
               "GROUP BY category_group ORDER BY n DESC LIMIT 1", (name,))
    return g["g"] if g else None


def apply_rules(where: str = "1 = 1", args=(), rs: list[dict] = None) -> int:
    """Run the rules over the transactions that match where (t.*, a.*) and were not changed by hand; how many changed."""
    rs = rs if rs is not None else db.q("SELECT * FROM mny_rules WHERE enabled = 1 ORDER BY position, id")
    if not rs:
        return 0
    rows = db.q("SELECT t.id, t.account_id, t.amount, t.merchant, t.description, t.category, t.category_group, t.hidden, "
                f"t.notes, a.name AS account_name FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id "
                f"WHERE t.edited = 0 AND {where}", tuple(args))
    groups: dict = {}
    n = 0
    for t in rows:
        ch = _rule_changes(rs, t)
        if "category" in ch:
            if ch["category"] not in groups:
                groups[ch["category"]] = _group_of_category(ch["category"])
            ch["category_group"] = groups[ch["category"]] if ch["category"] != t["category"] else t["category_group"]
        ch = {k: v for k, v in ch.items() if t.get(k) != v}
        if not ch:
            continue
        new = {**t, **ch}
        ch["words"] = words(new["merchant"], new["description"], new["category"], new["category_group"], new["notes"], new["account_name"])
        db.ex(f"UPDATE mny_transactions SET {', '.join(k + ' = %s' for k in ch)} WHERE id = %s", (*ch.values(), t["id"]))
        n += 1
    return n


def apply_all_rules(u: dict) -> int:
    """Every rule over every transaction not changed by hand (Apply now, after a new rule)."""
    _need(shared_users.can_write(u), "Only editors change the rules")
    n = apply_rules()
    from app import transfers
    transfers.link()  # a category a rule set can make a transfer plain
    return n


def try_rule(u: dict, b: dict, limit: int = 5) -> dict:
    """The transactions this person sees that a rule (as given, not kept) would change: how many, and a few of them."""
    if not text(b.get("pattern"), 255, "The words to look for"):
        raise Invalid("Give the words the payee or the bank's text has")
    c = _rule_fields(u, b, {"set_merchant": "-"})  # what it would do does not matter here, only what it matches
    r = {"enabled": 1, "field": "either", "how": "contains", "account_id": None, "flow": None, "amount_min": None,
         "amount_max": None, "set_merchant": None, "set_category": None, "set_hidden": None, **c}
    where, args = _visible(u)
    rows = db.q(f"SELECT t.*, a.owner_id, a.name AS account_name, a.currency FROM mny_transactions t "
                f"JOIN mny_accounts a ON a.id = t.account_id WHERE {where} AND a.track = 'transactions' ORDER BY t.day DESC, t.id DESC", args)
    hits = [t for t in rows if _matches(r, t)]
    return {"count": len(hits), "edited": sum(1 for t in hits if t["edited"]), "sample": [tx_public(t, u) for t in hits[:limit]]}


# ---- what one person sees, in a few numbers

def counts(u: dict) -> dict:
    where, args = _visible(u)
    a = db.one(f"SELECT count(*) AS n FROM mny_accounts a WHERE {where} AND a.hidden = 0", args)["n"]
    t = db.one(f"SELECT count(*) AS n FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id WHERE {where} AND a.track = 'transactions'", args)["n"]
    h = db.one(f"SELECT count(*) AS n FROM mny_holdings h JOIN mny_accounts a ON a.id = h.account_id WHERE {where}", args)["n"]
    return {"accounts": a, "transactions": t, "holdings": h}
