"""Recurring transactions: the bills (the power bill, the mortgage, a subscription) and the money that comes in
regularly (a paycheck), found by ioMoney itself in the transactions and kept in a list the household manages
(mny_recurring): what ioCalendar shows on the day each is due (GET /api/bills), paid or not.

Found: the same payee in the same account, money out (or in), at least three times (a yearly one twice) at a steady
pace (weekly, every two weeks, twice a month, monthly, every two months, quarterly, every six months, yearly) with an
amount that mostly stays about the same, the last one recent enough to still be going (see "found in the
transactions" below for how). What is found and not in the list yet is offered (Add, or Not recurring,
which is not offered again); anyone who may change the household's things also adds one by hand, changes it or
removes it.

Each one in the list: a name, the words its payee or bank's text has (the pattern; "a|b" when the payee had more
than one name), the account (or any), money out or
in, the usual amount (approximate: it varies), how often, a day it fell on (the dates follow from it) and a category.
A date is paid when a transaction like it (that account, those words, that way, the amount within reach) is a few
days from it.

Subscriptions (Netflix, Max, YouTube, Spotify, iCloud, a gym...) are recurring transactions too, marked as one: found
by the service's name (or a category like Streaming or Subscriptions), or marked by hand; the Recurring page shows them
in their own section with what they cost a month and a year.
"""
import datetime as dt
import re
import statistics
from decimal import Decimal

from iosuite_shared import users as shared_users
from iosuite_shared.errors import Invalid

from app import db, model

FREQS = ("weekly", "biweekly", "semimonthly", "monthly", "bimonthly", "quarterly", "semiannual", "yearly")
FREQ_LABEL = {"weekly": "Every week", "biweekly": "Every two weeks", "semimonthly": "Twice a month",
              "monthly": "Every month", "bimonthly": "Every two months", "quarterly": "Every three months",
              "semiannual": "Every six months", "yearly": "Every year"}
BANDS = {"weekly": (6, 8), "biweekly": (13, 15), "semimonthly": (12, 19), "monthly": (26, 35), "bimonthly": (55, 66),
         "quarterly": (82, 100), "semiannual": (170, 200), "yearly": (350, 380)}
SPAN = {"weekly": 7, "biweekly": 14, "semimonthly": 15, "monthly": 31, "bimonthly": 62, "quarterly": 92, "semiannual": 183,
        "yearly": 366}
MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "yearly": 12}
LOOK_BACK = 800        # days of transactions looked at to find them: two years and more, so a yearly one is seen twice
NEAR = {"weekly": 2, "biweekly": 3}  # how far from its date a payment still counts (5 days for the rest)
VARIES = Decimal("0.35")  # an approximate amount: a payment within 35% of it is one
PER_MONTH = {"weekly": Decimal(52) / 12, "biweekly": Decimal(26) / 12, "semimonthly": Decimal(2),
             **{f: Decimal(1) / n for f, n in MONTHS.items()}}

# the services people subscribe to, by the words their payee or the bank's text has
SERVICES = re.compile(r"\b(?:" + "|".join([  # a short or common word ends at a word's end; a long name may run on (YouTubePremium)
    r"netflix", r"hbo\b", r"hbo ?max", r"max\.com", r"youtube", r"yt premium", r"spotify", r"pandora\b", r"tidal\b", r"deezer",
    r"sirius ?xm", r"disney ?\+|disneyplus|disney plus", r"hulu\b", r"paramount", r"peacock", r"espn\+", r"apple\.com/bill",
    r"apple (?:tv|music|one|arcade)\b", r"itunes", r"icloud", r"google (?:one|storage|play)\b", r"amazon prime", r"prime video",
    r"amzn prime", r"audible", r"kindle unlimited", r"crunchyroll", r"fubo\b", r"sling\b", r"philo\b", r"starz\b",
    r"showtime", r"mubi\b", r"britbox", r"dazn\b", r"twitch", r"patreon", r"substack", r"nytimes|new york times|nyt\b",
    r"washington post|wapo\b", r"wall street journal|wsj\b", r"the athletic", r"economist", r"medium\.com", r"dropbox",
    r"onedrive", r"microsoft ?365|office ?365", r"adobe", r"chatgpt|openai", r"claude\.ai|anthropic", r"github", r"1password",
    r"lastpass", r"bitwarden", r"nordvpn|expressvpn|surfshark", r"proton ?(?:mail|vpn|ag)\b", r"duolingo", r"headspace",
    r"calm\.com", r"peloton", r"strava", r"xbox", r"playstation|psn\b", r"nintendo", r"ea play", r"discord", r"linkedin premium",
    r"canva\b", r"evernote", r"grammarly", r"backblaze", r"ring\.com|ring (?:plan|protect)", r"nest aware", r"simplisafe",
    r"planet fitness", r"classpass",
]) + r")", re.I)
SUB_CATEGORY = re.compile(r"subscri|streaming|software|membership|dues", re.I)


# ---- the dates

def _add_months(d: dt.date, n: int, dom: int) -> dt.date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    last = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
    return dt.date(y, m, min(dom, last))


def _step(d: dt.date, freq: str, sign: int, dom: int) -> dt.date:
    if freq == "weekly":
        return d + dt.timedelta(days=7 * sign)
    if freq == "biweekly":
        return d + dt.timedelta(days=14 * sign)
    if freq == "semimonthly":  # the anchor's day of the month and fifteen days on (the 1st and the 16th, the 15th and the 30th)
        lo = dom if dom <= 15 else dom - 15
        last = _add_months(d, 0, 31).day
        hi = min(lo + 15, last)
        if sign > 0:
            if d.day < lo:
                return d.replace(day=lo)
            if d.day < hi:
                return d.replace(day=hi)
            return _add_months(d, 1, lo)
        if d.day > hi:
            return d.replace(day=hi)
        if d.day > lo:
            return d.replace(day=lo)
        return _add_months(d, -1, lo + 15)
    return _add_months(d, MONTHS[freq] * sign, dom)


def dates(r: dict, start: dt.date, end: dt.date) -> list[dt.date]:
    """The days it falls on from start to end, both included."""
    d, dom, freq = r["day"], r["day"].day, r["frequency"]
    for _ in range(2000):
        if d < start:
            break
        d = _step(d, freq, -1, dom)
    out = []
    for _ in range(2000):
        if d > end:
            break
        if d >= start:
            out.append(d)
        d = _step(d, freq, 1, dom)
    return out


def next_date(r: dict, today: dt.date = None) -> dt.date | None:
    today = today or dt.date.today()
    got = dates(r, today, today + dt.timedelta(days=SPAN[r["frequency"]] + 31))
    return got[0] if got else None


def looks_subscription(name: str | None, pattern: str | None, category: str | None) -> bool:
    """A subscription to a service, by its name or its category."""
    return any(SERVICES.search(x or "") for x in (name, pattern)) or bool(SUB_CATEGORY.search(category or ""))


def per_month(amount, freq: str) -> Decimal:
    return (Decimal(amount) * PER_MONTH[freq]).quantize(model.CENT)


# ---- what it matches

def _norm(s: str | None) -> str:
    """Words to compare a payee or the bank's text by: lower case, without the words that have a digit (a card's last
    digits, a date, a store's number, a phone number) and without the signs between them."""
    s = (s or "").lower().replace("*", " ").replace("#", " ")
    s = re.sub(r"\S*\d\S*", " ", s)
    s = re.sub(r"[^\w&'.+/ -]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(" -./")


def _label(t: dict) -> str | None:
    """The payee as words to look for: Monarch's payee name, or the bank's text."""
    s = _norm(t.get("merchant") or t.get("description"))
    return s[:120] if len(s) >= 3 else None


def _alts(pattern: str | None) -> list[str]:
    """The pattern's words, one or more ways (a payee Monarch renamed: "aes loan|aes student loans")."""
    return [a for a in (_norm(x) for x in (pattern or "").split("|")) if a]


def _says(r: dict, t: dict) -> bool:
    alts = _alts(r["pattern"])
    texts = [_norm(t.get("merchant")), _norm(t.get("description"))]
    raw = (r["pattern"] or "").lower()
    return any(a in x for a in alts for x in texts if x) or bool(raw) and any(raw in (x or "").lower() for x in (t.get("merchant"), t.get("description")))


def _reach(r: dict) -> Decimal:
    want = Decimal(r["amount"])
    return want * VARIES if r["approximate"] else max(Decimal("1.00"), want * Decimal("0.02"))


def _hits(r: dict, t: dict) -> bool:
    amt = Decimal(t["amount"])
    if (r["flow"] == "out") != (amt < 0) or (r["account_id"] and r["account_id"] != t["account_id"]):
        return False
    if abs(abs(amt) - Decimal(r["amount"])) > _reach(r):
        return False
    return _says(r, t)


def _payments(r: dict, start: dt.date, end: dt.date) -> list[dict]:
    """The transactions that look like this one from start to end (not hidden)."""
    want, reach = Decimal(r["amount"]), _reach(r)
    where = "t.hidden = 0 AND t.day BETWEEN %s AND %s AND ABS(t.amount) BETWEEN %s AND %s AND t.amount " + ("< 0" if r["flow"] == "out" else "> 0")
    args = [start, end, want - reach, want + reach]
    if r["account_id"]:
        where += " AND t.account_id = %s"
        args.append(r["account_id"])
    rows = db.q(f"SELECT t.id, t.account_id, t.day, t.amount, t.merchant, t.description FROM mny_transactions t WHERE {where} "
                "ORDER BY t.day", args)
    return [t for t in rows if _hits(r, t)]


# ---- the list

def _row(rid) -> dict | None:
    try:
        return db.one("SELECT * FROM mny_recurring WHERE id = %s", (int(rid),))
    except (TypeError, ValueError):
        return None


def _sees(u: dict, r: dict) -> bool:
    if model.role_rank(u) < 1:
        return False
    if not r["account_id"]:
        return True
    a = model.account_row(r["account_id"])
    return bool(a) and model.can_read(u, a)


def item(u: dict, rid) -> dict:
    r = _row(rid)
    if not r or not _sees(u, r):
        raise model.NotFound("No such recurring transaction")
    return r


def _may_change(u: dict, account_id) -> bool:
    """The household's: editors and admins; one for a person's own account: that person too."""
    if account_id:
        a = model.account_row(account_id)
        return bool(a) and model.can_write(u, a)
    return shared_users.can_write(u)


def _need_change(u: dict, account_id) -> None:
    model._need(_may_change(u, account_id), "Only editors change the household's recurring transactions")


def public(r: dict, u: dict, today: dt.date = None) -> dict:
    today = today or dt.date.today()
    a = model.account_row(r["account_id"]) if r["account_id"] else None
    paid = _payments(r, today - dt.timedelta(days=LOOK_BACK), today)
    last = paid[-1] if paid else None
    nxt = next_date(r, today)
    sign = -1 if r["flow"] == "out" else 1
    return {"id": r["id"], "name": r["name"], "pattern": r["pattern"], "accountId": r["account_id"],
            "account": a["name"] if a else None, "currency": (a or {}).get("currency") or model.home_currency(),
            "flow": r["flow"], "amount": model.n2(sign * Decimal(r["amount"])), "approximate": bool(r["approximate"]),
            "frequency": r["frequency"], "frequencyLabel": FREQ_LABEL[r["frequency"]], "day": r["day"].isoformat(),
            "next": nxt.isoformat() if nxt else None, "category": r["category"], "source": r["source"],
            "subscription": bool(r["subscription"]), "perMonth": model.n2(sign * per_month(r["amount"], r["frequency"])),
            "last": {"day": last["day"].isoformat(), "amount": model.n2(last["amount"])} if last else None,
            "writable": _may_change(u, r["account_id"])}


def items(u: dict) -> list[dict]:
    """The household's recurring transactions this person sees, the next one due first."""
    rows = [r for r in db.q("SELECT * FROM mny_recurring ORDER BY name") if _sees(u, r)]
    out = [public(r, u) for r in rows]
    out.sort(key=lambda x: (x["next"] or "9999", x["name"].lower()))
    return out


def _fields(u: dict, b: dict, old: dict = None) -> dict:
    c = {}
    if "name" in b or old is None:
        n = model.text(b.get("name"), 255, "The name")
        if not n:
            raise Invalid("Give it a name")
        c["name"] = n
    if "pattern" in b or old is None:
        p = model.text(b.get("pattern") or (b.get("name") if old is None else None), 255, "The words")
        if not p or len(p) < 2:
            raise Invalid("Give the words its payee or the bank's text has")
        c["pattern"] = p.lower()
    if "accountId" in b:
        if b["accountId"] in (None, "", 0):
            c["account_id"] = None
        else:
            a = model.account_row(b["accountId"])
            if not a or not model.can_read(u, a):
                raise Invalid("The account: one of those you see")
            c["account_id"] = a["id"]
    if "flow" in b or old is None:
        f = b.get("flow") or "out"
        if f not in ("out", "in"):
            raise Invalid("Money out or in")
        c["flow"] = f
    if "amount" in b or old is None:
        amt = model.money(b.get("amount"), "The amount")
        if not amt:
            raise Invalid("Give the usual amount")
        c["amount"] = abs(amt)
    if "approximate" in b:
        c["approximate"] = model.flag(b["approximate"])
    if "frequency" in b or old is None:
        f = b.get("frequency") or "monthly"
        if f not in FREQS:
            raise Invalid("How often: " + ", ".join(FREQS))
        c["frequency"] = f
    if "day" in b or old is None:
        c["day"] = model.day(b.get("day") or dt.date.today().isoformat())
    if "category" in b:
        c["category"] = model.text(b["category"], 128, "The category")
    if "subscription" in b:
        c["subscription"] = model.flag(b["subscription"])
    elif old is None:  # one added without saying: a known service is one
        c["subscription"] = int(looks_subscription(c["name"], c["pattern"], c.get("category")))
    return c


def create(u: dict, b: dict, source: str = "hand") -> dict:
    c = _fields(u, b)
    _need_change(u, c.get("account_id"))
    rid = db.ex("INSERT INTO mny_recurring (name, pattern, account_id, flow, amount, approximate, frequency, day, category, "
                "subscription, source, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (c["name"], c["pattern"], c.get("account_id"), c["flow"], c["amount"], c.get("approximate", 0), c["frequency"],
                 c["day"], c.get("category"), c["subscription"], source, u["id"]))
    return _row(rid)


def update(u: dict, r: dict, b: dict) -> dict:
    _need_change(u, r["account_id"])
    c = _fields(u, b, r)
    if "account_id" in c:
        _need_change(u, c["account_id"])
    if c:
        db.ex(f"UPDATE mny_recurring SET {', '.join(k + ' = %s' for k in c)} WHERE id = %s", (*c.values(), r["id"]))
    return _row(r["id"])


def delete(u: dict, r: dict) -> None:
    _need_change(u, r["account_id"])
    db.ex("DELETE FROM mny_recurring WHERE id = %s", (r["id"],))


# ---- from one transaction

def mark(items: list[dict], u: dict) -> list[dict]:
    """Each transaction (as tx_public gives it) with recurring: {id, name, subscription} when it is one of the
    household's recurring transactions this person sees, else None."""
    kept = [r for r in db.q("SELECT * FROM mny_recurring") if _sees(u, r)] if items else []
    for t in items:
        probe = {"account_id": t["accountId"], "amount": t["amount"], "merchant": t["merchant"], "description": t["description"]}
        r = next((r for r in kept if _hits(r, probe)), None)
        t["recurring"] = {"id": r["id"], "name": r["name"], "subscription": bool(r["subscription"])} if r else None
    return items


def for_transaction(u: dict, t: dict, today: dt.date = None) -> dict:
    """{item: the recurring transaction it is (as public), or None; suggestion: one to add from it (name, pattern,
    account, way, amount, how often and whether the amount varies from the transactions like it, its date, category,
    subscription)}."""
    today = today or dt.date.today()
    probe = {"account_id": t["account_id"], "amount": t["amount"], "merchant": t["merchant"], "description": t["description"]}
    r = next((r for r in db.q("SELECT * FROM mny_recurring") if _sees(u, r) and _hits(r, probe)), None)
    if r:
        return {"item": public(r, u, today), "suggestion": None}
    flow = "out" if Decimal(t["amount"]) < 0 else "in"
    rows = db.q("SELECT t.id, t.account_id, t.day, t.amount, t.merchant, t.description, t.category FROM mny_transactions t "
                "WHERE t.account_id = %s AND t.hidden = 0 AND t.day BETWEEN %s AND %s AND t.amount " + ("< 0" if flow == "out" else "> 0"),
                (t["account_id"], today - dt.timedelta(days=LOOK_BACK), today))
    if not any(x["id"] == t["id"] for x in rows):
        rows.append(t)
    comps = _components(rows)
    comp = next((c for c in comps if any(x["id"] == t["id"] for x in c)), [t])
    ser = next((x for x in _series(comp, today, stale=False) if any(y["id"] == t["id"] for y in x["ts"])), None)
    if not ser:  # alone, or not steady: this one's amount, monthly unless the dates say otherwise
        days = sorted({x["day"] for x in comp})
        ser = {"ts": comp, "days": days, "freq": _cadence(days, 0.5) or "monthly", "amount": abs(Decimal(t["amount"])), "approximate": False}
    s = _suggest(ser, flow)
    s["day"] = t["day"].isoformat()
    return {"item": None, "suggestion": s}


# ---- found in the transactions
#
# The transactions of an account one way (out, or in) are put together by payee: the same payee name, or the same
# bank's text (Monarch renames a payee now and then; the bank's text stays), unless that text is one many payees share.
# A payee's transactions are then split by amount (two loans paid to the same bank, a weekly box and a monthly pass):
# first the amounts within 3% of each other, then within a quarter, then whatever is left at a steady pace with an
# amount that varies (a utility). Each group is recurring when its dates come at a steady pace (most of the gaps
# between them in one band, so an extra payment or a late one does not spoil it) and most of its amounts are near
# the usual one (a bonus, a refund or a price change does not either), it still goes on, and it happened three times
# (a yearly one, or a known service, twice). Transfers to a card or between cash accounts are left out; a payment to
# a loan or an investment account (the car loan, the mortgage, a 529) is a bill.

def _key(account_id, flow: str, label: str, amount: Decimal) -> str:
    return f"{account_id or 0}:{flow}:{label}:{int(amount)}"[:300]


def _cadence(days: list, need: float = 0.6) -> str | None:
    gaps = [(b - a).days for a, b in zip(days, days[1:])]
    if not gaps:
        return None
    med = statistics.median(gaps)
    for f in FREQS:
        lo, hi = BANDS[f]
        if f == "semimonthly" and all(13 <= g <= 15 for g in gaps):
            continue  # exactly every two weeks
        if lo <= med <= hi and sum(lo <= g <= hi for g in gaps) >= need * len(gaps):
            return f
    return None


def _components(rows: list[dict]) -> list[list[dict]]:
    """The transactions (of one account, one way) put together by payee name or the bank's text."""
    ms = [_label({"merchant": t.get("merchant")}) for t in rows]
    ds = [_label({"description": t.get("description")}) for t in rows]
    payees: dict = {}
    for m, d in zip(ms, ds):
        if d:
            payees.setdefault(d, set()).add(m)
    parent = list(range(len(rows)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    first: dict = {}
    for i, (m, d) in enumerate(zip(ms, ds)):
        keys = ([("m", m)] if m else []) + ([("d", d)] if d and len(payees[d]) <= 3 else [])
        if not keys:
            parent[i] = -1
            continue
        for k in keys:
            if k in first:
                parent[find(i)] = find(first[k])
            else:
                first[k] = i
    comps: dict = {}
    for i, t in enumerate(rows):
        if parent[i] != -1:
            comps.setdefault(find(i), []).append(t)
    return list(comps.values())


def _clusters(ts: list[dict], step: Decimal) -> list[list[dict]]:
    """Split by amount: sorted, a new cluster where the next amount is more than step above the last."""
    out, cur, last = [], [], None
    for t in sorted(ts, key=lambda t: abs(Decimal(t["amount"]))):
        a = abs(Decimal(t["amount"]))
        if cur and a > last * (1 + step):
            out.append(cur)
            cur = []
        cur.append(t)
        last = a
    return out + ([cur] if cur else [])


def _steady(ts: list[dict], today: dt.date, stale: bool, varies: bool) -> dict | None:
    by_day: dict = {}
    for t in sorted(ts, key=lambda t: t["day"]):
        by_day.setdefault(t["day"], t)
    days = sorted(by_day)
    freq = _cadence(days, 0.7 if varies else 0.6)
    if not freq:
        return None
    last = by_day[days[-1]]
    sub = Decimal(last["amount"]) < 0 and looks_subscription(last.get("merchant"), _label(last), last.get("category"))
    if len(days) < (2 if freq == "yearly" or sub else 5 if varies else 3):
        return None
    if stale and (today - days[-1]).days > BANDS[freq][1] * 1.5 + 5:
        return None  # stopped
    amts = [abs(Decimal(by_day[d]["amount"])) for d in days]
    med = Decimal(statistics.median(amts))
    if med <= 0:
        return None
    near = [a for a in amts if abs(a - med) <= med * Decimal("0.25")]
    if not varies and len(near) < 0.7 * len(amts):
        return None  # the amount is all over the place: shopping, not a bill
    approximate = varies or (max(near) - min(near)) > med * Decimal("0.02")
    return {"ts": list(by_day.values()), "days": days, "freq": freq, "amount": med.quantize(model.CENT), "approximate": approximate}


def _series(comp: list[dict], today: dt.date, stale: bool = True) -> list[dict]:
    """The recurring series in one payee's transactions."""
    out, left = [], list(comp)
    for step, varies in ((Decimal("0.03"), False), (Decimal("0.25"), False), (None, True)):
        rest = []
        for c in (_clusters(left, step) if step is not None else [left]):
            s = _steady(c, today, stale, varies) if c else None
            if s:
                out.append(s)
            else:
                rest.extend(c)
        left = rest
    return out


def _suggest(ser: dict, flow: str) -> dict:
    """What a series would be in the list: its name (the payee's latest), the words (every name it had), the rest."""
    ts = sorted(ser["ts"], key=lambda t: t["day"], reverse=True)
    names, alts = [], []
    for t in ts:
        n = t.get("merchant") or t.get("description")
        if n and n not in names:
            names.append(n)
        lab = _label({"merchant": t.get("merchant")}) or _label({"description": t.get("description")})
        if lab and lab not in alts:
            alts.append(lab)
    pattern = ""
    for a in alts:
        if len(pattern) + len(a) + 1 > 255:
            break
        pattern = f"{pattern}|{a}" if pattern else a
    cat = next((t["category"] for t in ts if t.get("category")), None)
    name = names[0] if names else pattern
    return {"name": name, "pattern": pattern, "accountId": ts[0]["account_id"], "flow": flow, "amount": model.n2(ser["amount"]),
            "approximate": ser["approximate"], "frequency": ser["freq"], "day": ser["days"][-1].isoformat(), "category": cat,
            "subscription": flow == "out" and looks_subscription(name, pattern, cat), "count": len(ser["days"])}


def found(u: dict, today: dt.date = None) -> list[dict]:
    """What looks recurring in the transactions this person sees and is not in the list (nor set aside): each
    {key, name, pattern, accountId, account, flow, amount, approximate, frequency, frequencyLabel, day (the last
    one), next, category, count, subscription, perMonth}, the most regular first."""
    today = today or dt.date.today()
    if model.role_rank(u) < 1:
        return []
    where, args = model._visible(u)
    rows = db.q(f"SELECT t.id, t.account_id, t.day, t.amount, t.merchant, t.description, t.category, a.name AS account_name, "
                f"a.currency, oa.kind AS other_kind, x.out_id AS x_out "
                f"FROM mny_transactions t JOIN mny_accounts a ON a.id = t.account_id "
                f"LEFT JOIN mny_transfers x ON x.out_id = t.id OR x.in_id = t.id "
                f"LEFT JOIN mny_transactions o ON o.id = IF(x.out_id = t.id, x.in_id, x.out_id) "
                f"LEFT JOIN mny_accounts oa ON oa.id = o.account_id "
                f"WHERE {where} AND a.track = 'transactions' AND t.hidden = 0 AND t.amount <> 0 AND t.day BETWEEN %s AND %s",
                (*args, today - dt.timedelta(days=LOOK_BACK), today))
    by: dict = {}
    for t in rows:
        if t["x_out"] is not None and (t["amount"] > 0 or t["other_kind"] in (None, "cash", "credit")):
            continue  # a card's payment, money moved between cash accounts, or money in from one's own account
        by.setdefault((t["account_id"], "out" if t["amount"] < 0 else "in"), []).append(t)
    kept = db.q("SELECT * FROM mny_recurring")
    nots = {r["k"] for r in db.q("SELECT k FROM mny_recurring_nots")}
    out = []
    for (aid, flow), ts in by.items():
        for comp in _components(ts):
            for ser in _series(comp, today):
                f = _suggest(ser, flow)
                last = max(ser["ts"], key=lambda t: t["day"])
                labs = [_label(t) for t in ser["ts"]]
                key = _key(aid, flow, max(set(labs), key=labs.count) or "", ser["amount"])
                if key in nots:
                    continue
                sign = -1 if flow == "out" else 1
                probe = {"account_id": aid, "amount": sign * ser["amount"], "merchant": last["merchant"], "description": last["description"]}
                if any(_hits(r, probe) for r in kept):
                    continue
                nxt = next_date({"day": ser["days"][-1], "frequency": ser["freq"]}, today)
                f.update(key=key, account=last["account_name"], currency=last["currency"], amount=model.n2(sign * ser["amount"]),
                         frequencyLabel=FREQ_LABEL[ser["freq"]], next=nxt.isoformat() if nxt else None,
                         perMonth=model.n2(sign * per_month(ser["amount"], ser["freq"])))
                out.append(f)
    out.sort(key=lambda x: (-x["count"], x["name"].lower()))
    return out


def add_found(u: dict, key: str) -> dict:
    """Add what was found under key to the list."""
    f = next((x for x in found(u) if x["key"] == key), None)
    if not f:
        raise model.NotFound("Nothing found like that any more")
    return create(u, {"name": f["name"], "pattern": f["pattern"], "accountId": f["accountId"], "flow": f["flow"],
                      "amount": abs(f["amount"]), "approximate": f["approximate"], "frequency": f["frequency"],
                      "day": f["day"], "category": f["category"], "subscription": f["subscription"]}, source="found")


def dismiss(u: dict, key: str) -> None:
    """Not recurring: not offered again."""
    model._need(shared_users.is_member(u), "Viewers only look")
    k = model.text(key, 300, "The key")
    if not k:
        raise Invalid("Which one?")
    db.ex("INSERT IGNORE INTO mny_recurring_nots (k) VALUES (%s)", (k,))


# ---- the bills, for ioCalendar

def bills(u: dict, start, end, today: dt.date = None) -> list[dict]:
    """Every date a recurring transaction falls on from start to end, paid or not: [{id, day, merchant, amount (money
    out negative), currency, approximate, frequency, category, accountId, account, subscription, paid}], by day."""
    today = today or dt.date.today()
    s, e = model.day(start), model.day(end)
    out = []
    for r in db.q("SELECT * FROM mny_recurring"):
        if not _sees(u, r):
            continue
        ds = dates(r, s, e)
        if not ds:
            continue
        a = model.account_row(r["account_id"]) if r["account_id"] else None
        near = NEAR.get(r["frequency"], 5)
        pays = _payments(r, s - dt.timedelta(days=near), min(e + dt.timedelta(days=near), today))
        used = set()
        sign = -1 if r["flow"] == "out" else 1
        for d in ds:
            hit = next((p for p in pays if p["id"] not in used and abs((p["day"] - d).days) <= near), None)
            if hit:
                used.add(hit["id"])
            out.append({"id": r["id"], "day": d.isoformat(), "merchant": r["name"],
                        "amount": model.n2(Decimal(hit["amount"]) if hit else sign * Decimal(r["amount"])),
                        "currency": (a or {}).get("currency") or model.home_currency(), "approximate": bool(r["approximate"]) and not hit,
                        "frequency": FREQ_LABEL[r["frequency"]], "category": r["category"], "accountId": r["account_id"],
                        "account": a["name"] if a else None, "subscription": bool(r["subscription"]), "paid": bool(hit)})
    out.sort(key=lambda b: (b["day"], b["merchant"].lower()))
    return out
