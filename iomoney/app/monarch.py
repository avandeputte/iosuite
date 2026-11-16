"""Monarch Money: the household's accounts, balances, transactions and holdings, copied in.

Monarch has no public API; the community's Python library (`monarchmoneycommunity`, the maintained fork of
`monarchmoney`) speaks to the same GraphQL API Monarch's web app uses. Nothing goes the other way: ioMoney only reads.

The sign-in is kept with the suite's keys and tokens (Settings › Global settings › Keys and tokens, ioMoney), never in
a config file: the Monarch email, the password and the authenticator key (the text under the QR code Monarch shows when
the authenticator app is set up; with it ioMoney makes the six-digit code itself). On the first sync ioMoney signs in
and keeps the long-lived session Monarch gives a trusted device (monarch_token, also there); later syncs use that and
sign in again only when Monarch no longer takes it. A one-time code can also be given by hand (Settings › Money).

What a sync does (sync(); every SYNC_HOURS hours from the chores in app/main.py, and Sync now):
- accounts: each Monarch account is an account here (source monarch), with its balance today; a new one brings its
  balance history. Real estate (Zillow) and vehicles are accounts too: the house's and the cars' values come from there.
  Name, hidden and "in the net worth" stay as changed here; Monarch decides the rest.
- transactions: those since the last sync (two weeks back, for late changes, and back to the oldest one still pending
  here, so it is seen to post), or the past INITIAL_DAYS the first time.
  A transaction whose category, notes or hidden was changed here keeps those. One that disappeared from Monarch inside
  the window (a pending one that posted under another id, one deleted there) goes here too, and so does one hidden in
  Monarch ("Hide from reports": a duplicate, or one a person or a Monarch rule left out): it is not brought in at all.
- an account Monarch reports that is not here, after the first sync, is held (mny_monarch_new) with its transactions
  until an admin says whether it is new or an account here that was deleted and made again in Monarch (when its bank
  link broke). An existing one takes the new id, and the next sync matches the transactions Monarch sends under it
  with those kept (same amount, a few days apart): none is there twice, and what was changed here stays.
- holdings of the investment accounts, with Monarch's last price (used while there is no quote).
Monarch's recurring transactions (its bills) are not taken: ioMoney finds them itself (app/recurring.py).
A category renamed, merged or regrouped here (app/categories.py) stays so: what Monarch sends under its old name
comes in under the new one, in its group here.
"""
import asyncio
import datetime as dt
import json
import logging
import re
import threading
from decimal import Decimal

from iosuite_shared import credentials
from iosuite_shared.errors import Invalid

from app import categories, config, db, model

log = logging.getLogger("iomoney.monarch")
APP = config.APP
KEYS = [
    {"name": "monarch_email", "label": "Monarch Money email", "hint": "the email you sign in to Monarch Money with"},
    {"name": "monarch_password", "label": "Monarch Money password"},
    {"name": "monarch_mfa_secret", "label": "Monarch Money authenticator key",
     "hint": "the text under the QR code Monarch shows when you set up the authenticator app (Settings › Security there)"},
    {"name": "monarch_token", "label": "Monarch Money session",
     "hint": "kept here by ioMoney after it signs in; clear it to make ioMoney sign in again"},
]
INITIAL_DAYS = 730      # transactions fetched on the first sync
OVERLAP_DAYS = 14       # a later sync looks this far back before the last one
PENDING_DAYS = 120      # ... and back to the oldest transaction still pending here, at most this far
PAGE = 500              # transactions per request
TIMEOUT = 60
SYNC_HOURS = 6

_lock = threading.Lock()
_progress = {"stage": None, "count": 0, "started": None}  # what the running sync is at, for Settings › Money


def _at(stage: str, count: int = 0) -> None:
    _progress.update(stage=stage, count=count)


client_factory = None   # tests: a function (token) -> a stand-in for MonarchMoney


class NeedsSignIn(Exception):
    """Monarch would not let ioMoney in; the message says what to do."""


def declare() -> None:
    credentials.declare(APP, KEYS)


def _cred(name: str) -> str:
    return credentials.get(APP, name).strip()


def configured() -> bool:
    return bool(_cred("monarch_token") or (_cred("monarch_email") and _cred("monarch_password")))


def _new(token: str = None):
    if client_factory:
        return client_factory(token)
    from monarchmoney import MonarchMoney
    return MonarchMoney(session_file=str(config.DATA_DIR / "monarch-session.pickle"), timeout=TIMEOUT, token=token or None)


def _errors():
    try:
        from monarchmoney import CaptchaRequiredException, LoginFailedException, RequireMFAException
        return RequireMFAException, CaptchaRequiredException, LoginFailedException
    except ImportError:  # the tests' stand-in
        class _N(Exception):
            pass
        return _N, _N, _N


async def _sign_in(code: str = None):
    """A signed-in client: the kept session, else the email, password and authenticator key (or the code given)."""
    RequireMFA, Captcha, LoginFailed = _errors()
    email, pw, secret = _cred("monarch_email"), _cred("monarch_password"), _cred("monarch_mfa_secret").replace(" ", "")
    if not (email and pw):
        raise NeedsSignIn("Add the Monarch Money email and password in Settings › Global settings › Keys and tokens (ioMoney)")
    mm = _new()
    try:
        if code:
            await mm.multi_factor_authenticate(email, pw, code.strip())
        else:
            await mm.login(email, pw, use_saved_session=False, save_session=False, mfa_secret_key=secret or None)
    except Captcha:
        raise NeedsSignIn("Monarch asks for a CAPTCHA to sign in from here. Sign in to Monarch in a browser on this "
                          "network once, then try again")
    except RequireMFA:
        raise NeedsSignIn("Monarch asks for a code from the authenticator app: add the authenticator key in Keys and "
                          "tokens, or give the code in Settings › Monarch")
    except LoginFailed as e:
        raise NeedsSignIn(f"Monarch did not take the sign-in: {e}")
    if not mm.token:
        raise NeedsSignIn("Monarch signed in but gave no session")
    credentials.put(APP, "monarch_token", mm.token, by="ioMoney")
    return mm


def _unauthorized(e: Exception) -> bool:
    s = f"{type(e).__name__} {e}".lower()
    return "401" in s or "unauthorized" in s or "unauthenticated" in s or "not authenticated" in s


async def _client():
    token = _cred("monarch_token")
    if token:
        mm = _new(token)
        try:
            await mm.get_transaction_categories()  # a light call that tells whether the session still works
            return mm
        except Exception as e:  # noqa: BLE001
            if not _unauthorized(e):
                raise
            log.info("the Monarch session is no longer taken: signing in again")
            credentials.put(APP, "monarch_token", "", by="ioMoney")
    return await _sign_in()


def sign_in_with_code(code: str) -> None:
    """Sign in with a code from the authenticator app (when no authenticator key is kept); the session is kept."""
    if not code or not code.strip().isdigit():
        raise NeedsSignIn("The code: the six digits the authenticator app shows")
    asyncio.run(_sign_in(code))


def forget_session() -> None:
    credentials.put(APP, "monarch_token", "", by="ioMoney")


# ------------------------------------------------------------------ the copy

def _abs(v) -> Decimal:
    return abs(Decimal(str(v or 0))).quantize(model.CENT)


def _bal(acc: dict) -> Decimal:
    v = acc.get("currentBalance")
    if v is None:
        v = acc.get("displayBalance")
    return Decimal(str(v or 0)).quantize(model.CENT)


def _put_account(acc: dict, today: dt.date) -> tuple[int, bool]:
    """Insert or refresh one Monarch account; (its id here, whether it is new)."""
    is_asset = bool(acc.get("isAsset", True))
    kind = model.kind_of_monarch(((acc.get("type") or {}).get("name") or ""), is_asset)
    inst = (acc.get("institution") or {}).get("name") or ((acc.get("credential") or {}).get("institution") or {}).get("name")
    sub = (acc.get("subtype") or {}).get("display")
    bal = _bal(acc)
    if not is_asset:
        bal = abs(bal)
    closed = 1 if acc.get("deactivatedAt") else 0
    ext = str(acc["id"])
    row = db.one("SELECT id FROM mny_accounts WHERE source = 'monarch' AND external_id = %s", (ext,))
    if row:
        db.ex("UPDATE mny_accounts SET institution = %s, kind = %s, subtype = %s, is_asset = %s, closed = %s, mask = %s "
              "WHERE id = %s", (inst, kind, sub, 1 if is_asset else 0, closed, (acc.get("mask") or None), row["id"]))
        aid, new = row["id"], False
    else:
        aid = db.ex("INSERT INTO mny_accounts (owner_id, source, external_id, name, institution, kind, subtype, is_asset, "
                    "balance, in_net_worth, hidden, closed, mask, track) VALUES (NULL, 'monarch', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (ext, (acc.get("displayName") or "Account")[:255], inst, kind, sub, 1 if is_asset else 0, bal,
                     1 if acc.get("includeInNetWorth", True) else 0, 1 if (acc.get("isHidden") or acc.get("hideFromList")) else 0,
                     closed, acc.get("mask") or None, model.track(None, kind)))
        new = True
    model.set_balance(aid, today, bal, "sync")
    return aid, new


async def _history(mm, ext: str, aid: int, is_asset: bool) -> int:
    try:
        snaps = await mm.get_account_history(int(ext) if ext.isdigit() else ext)
    except Exception as e:  # noqa: BLE001 - the history is a bonus
        log.info("no history for Monarch account %s: %s", ext, e)
        return 0
    rows = []
    for s in snaps or []:
        try:
            d = dt.date.fromisoformat(str(s.get("date"))[:10])
        except ValueError:
            continue
        v = Decimal(str(s.get("signedBalance") or 0)).quantize(model.CENT)
        rows.append((aid, d, v if is_asset else abs(v)))
    if rows:
        db.many("INSERT IGNORE INTO mny_balances (account_id, day, balance, source) VALUES (%s, %s, %s, 'sync')", rows)
    return len(rows)


def _put_tx(t: dict, aid: int, groups: dict, cats: tuple = None) -> bool:
    """Insert or refresh one Monarch transaction in account aid (what was changed here by hand stays); one hidden in
    Monarch is not kept here (removed when it was): False. cats: the household's renamed categories and their groups
    (app/categories.py maps())."""
    if t.get("hideFromReports"):
        db.ex("DELETE FROM mny_transactions WHERE source = 'monarch' AND external_id = %s", (str(t["id"]),))
        return False
    cat = (t.get("category") or {})
    merchant = (t.get("merchant") or {}).get("name")
    tags = [x.get("name") for x in (t.get("tags") or []) if x.get("name")]
    day = dt.date.fromisoformat(str(t["date"])[:10])
    amt = Decimal(str(t.get("amount") or 0)).quantize(model.CENT)
    grp = groups.get(str(cat.get("id"))) if cat else None
    cname, grp = categories.mapped(cat.get("name") or None, grp, *(cats or categories.maps()))
    w = model.words(merchant, t.get("plaidName"), cname, grp, t.get("notes"), ",".join(tags))
    db.ex("INSERT INTO mny_transactions (account_id, source, external_id, day, amount, merchant, description, category, "
          "category_group, notes, tags, pending, hidden, recurring, words) "
          "VALUES (%s, 'monarch', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
          "ON DUPLICATE KEY UPDATE account_id = VALUES(account_id), day = VALUES(day), amount = VALUES(amount), "
          "description = VALUES(description), tags = VALUES(tags), pending = VALUES(pending), recurring = VALUES(recurring), "
          "merchant = IF(edited, merchant, VALUES(merchant)), category = IF(edited, category, VALUES(category)), "
          "category_group = IF(edited, category_group, VALUES(category_group)), notes = IF(edited, notes, VALUES(notes)), "
          "hidden = IF(edited, hidden, VALUES(hidden)), words = IF(edited, words, VALUES(words))",
          (aid, str(t["id"]), day, amt, (merchant or "")[:255] or None, (t.get("plaidName") or "")[:255] or None,
           (cname or "")[:128] or None, (grp or "")[:128] or None, t.get("notes") or None,
           json.dumps(tags) if tags else None, 1 if t.get("pending") else 0, 0,
           1 if t.get("isRecurring") else 0, w))
    return True


async def _pages(mm, start: dt.date, end: dt.date, **kw):
    """Monarch's transactions from start to end, a page at a time."""
    offset = 0
    while True:
        got = await mm.get_transactions(limit=PAGE, offset=offset, start_date=start.isoformat(), end_date=end.isoformat(), **kw)
        page = ((got or {}).get("allTransactions") or {}).get("results") or []
        yield page
        if len(page) < PAGE:
            return
        offset += PAGE


async def _transactions(mm, ids: dict, since: dt.date, today: dt.date, groups: dict) -> int:
    seen, n = set(), 0
    cats = categories.maps()
    async for page in _pages(mm, since, today):
        for t in page:
            aid = ids.get(str((t.get("account") or {}).get("id")))
            if not aid:
                continue  # an account held for a person to say what it is, or one Monarch no longer lists
            seen.add(str(t["id"]))
            n += _put_tx(t, aid, groups, cats)
        _at("Transactions", n)
    # gone from Monarch inside the window: a pending one that posted under another id, one deleted there. Only in the
    # accounts Monarch still lists: an account deleted there (to be made again) keeps its transactions until they
    # are matched with the new account's
    aids = sorted(set(ids.values()))
    if aids:
        old = db.q("SELECT id, external_id FROM mny_transactions WHERE source = 'monarch' AND day BETWEEN %s AND %s "
                   f"AND account_id IN ({db.marks(len(aids))})", (since, today, *aids))
        gone = [r["id"] for r in old if r["external_id"] not in seen]
        if gone:
            db.ex(f"DELETE FROM mny_transactions WHERE id IN ({db.marks(len(gone))})", gone)
    # the household's rules, over what just came in (Monarch's own payee and category, unless changed here by hand)
    _at("Rules and transfers", n)
    model.apply_rules("t.source = 'monarch' AND t.day BETWEEN %s AND %s", (since, today))
    from app import transfers
    transfers.link("t.day BETWEEN %s AND %s", (since - dt.timedelta(days=transfers.DAYS), today))
    return n


# ------------------------------------------------------------------ accounts Monarch reports as new

MATCH_DAYS = 3  # a transaction under the new account is one kept under the old when the amount is the same, this near


def _known(ext: str) -> bool:
    return bool(db.one("SELECT 1 AS x FROM mny_accounts WHERE source = 'monarch' AND external_id = %s", (ext,)))


def _hold(acc: dict) -> None:
    db.ex("INSERT INTO mny_monarch_new (external_id, data) VALUES (%s, %s) ON DUPLICATE KEY UPDATE data = VALUES(data)",
          (str(acc["id"]), json.dumps(acc, default=str)))


async def _adopt(mm, move: dict, aid: int, today: dt.date, groups: dict) -> int:
    """An account here now has a new Monarch id (move): take every transaction Monarch has under it, and give each
    one that is already here under the old id (same amount, at most MATCH_DAYS apart, the nearest and the same payee
    first) the new id, so it keeps what was changed here by hand and is not there twice. The rest come in new."""
    ext = move["new_external_id"]
    old = db.q("SELECT id, external_id, day, amount, merchant, description FROM mny_transactions "
               "WHERE account_id = %s AND source IN ('monarch', 'manual')", (aid,))  # manual: an account typed in before
    first = min([r["day"] for r in old], default=today) - dt.timedelta(days=MATCH_DAYS + 7)
    first = min(first, today - dt.timedelta(days=INITIAL_DAYS))
    incoming = []
    async for page in _pages(mm, first, today, account_ids=[ext]):
        incoming += [t for t in page if str((t.get("account") or {}).get("id")) == ext]
        _at("Matching the account's transactions", len(incoming))
    ids_in = {str(t["id"]) for t in incoming}
    orphans = [r for r in old if r["external_id"] not in ids_in]
    used, n = set(), 0
    for t in sorted(incoming, key=lambda x: str(x.get("date"))):
        if _known_tx(str(t["id"])):
            continue
        amt = Decimal(str(t.get("amount") or 0)).quantize(model.CENT)
        day = dt.date.fromisoformat(str(t["date"])[:10])
        name = ((t.get("merchant") or {}).get("name") or t.get("plaidName") or "").lower()
        best = None
        for r in orphans:
            gap = abs((r["day"] - day).days)
            if r["id"] in used or Decimal(r["amount"]) != amt or gap > MATCH_DAYS:
                continue
            same = name and name in ((r["merchant"] or "") + " " + (r["description"] or "")).lower()
            score = (gap, 0 if same else 1)
            if best is None or score < best[0]:
                best = (score, r)
        if best:
            db.ex("UPDATE mny_transactions SET source = 'monarch', external_id = %s WHERE id = %s", (str(t["id"]), best[1]["id"]))
            used.add(best[1]["id"])
            n += 1
    cats = categories.maps()
    for t in incoming:
        _put_tx(t, aid, groups, cats)
    model.apply_rules("t.account_id = %s", (aid,))
    from app import transfers
    transfers.link("t.account_id = %s", (aid,))
    db.ex("UPDATE mny_monarch_moves SET done_at = NOW(), matched = %s WHERE account_id = %s", (n, aid))
    return n


def _known_tx(ext: str) -> bool:
    return bool(db.one("SELECT 1 AS x FROM mny_transactions WHERE source = 'monarch' AND external_id = %s", (ext,)))


def _account_look(acc: dict) -> dict:
    is_asset = bool(acc.get("isAsset", True))
    inst = (acc.get("institution") or {}).get("name") or ((acc.get("credential") or {}).get("institution") or {}).get("name")
    bal = _bal(acc)
    return {"externalId": str(acc["id"]), "name": acc.get("displayName") or "Account", "institution": inst,
            "kind": model.kind_of_monarch(((acc.get("type") or {}).get("name") or ""), is_asset),
            "subtype": (acc.get("subtype") or {}).get("display"), "mask": acc.get("mask") or None,
            "balance": float(bal if is_asset else abs(bal)), "closed": bool(acc.get("deactivatedAt"))}


def _similar(a: str, b: str) -> float:
    wa, wb = set(re.findall(r"[a-z0-9]+", (a or "").lower())), set(re.findall(r"[a-z0-9]+", (b or "").lower()))
    return len(wa & wb) / len(wa | wb) if wa and wb else 0.0


def held() -> list[dict]:
    """The accounts Monarch reported that wait for an admin: each with the accounts here it could be, likeliest first
    (an account whose Monarch id Monarch no longer lists, of the same kind, bank and last digits, a like name)."""
    rows = db.q("SELECT * FROM mny_monarch_new WHERE decision IS NULL ORDER BY first_seen, external_id")
    if not rows:
        return []
    listed = set(json.loads(model.setting("monarch_ids", "[]") or "[]"))
    accts = db.q("SELECT id, name, institution, kind, mask, source, external_id, closed, balance FROM mny_accounts "
                 "WHERE owner_id IS NULL ORDER BY name")
    out = []
    for r in rows:
        look = _account_look(json.loads(r["data"]))
        cands = []
        for a in accts:
            missing = a["source"] == "monarch" and a["external_id"] not in listed
            score = ((40 if missing else 0) + (25 if a["mask"] and a["mask"] == look["mask"] else 0)
                     + (20 if a["kind"] == look["kind"] else 0)
                     + (15 if a["institution"] and a["institution"] == look["institution"] else 0)
                     + round(20 * _similar(a["name"], look["name"])))
            alike = bool(a["mask"] and a["mask"] == look["mask"]) or _similar(a["name"], look["name"]) >= 0.5
            cands.append({"id": a["id"], "name": a["name"], "institution": a["institution"], "kind": a["kind"],
                          "mask": a["mask"], "source": a["source"], "balance": float(a["balance"] or 0),
                          "gone": missing, "closed": bool(a["closed"]), "score": score, "alike": alike})
        # the accounts of its group (a bank account for a bank account), and any whose Monarch id is gone
        group = model.GROUP_OF.get(look["kind"], "asset")
        cands = [c for c in cands if c["gone"] or model.GROUP_OF.get(c["kind"], "asset") == group]
        cands.sort(key=lambda c: (-c["score"], c["name"]))
        # a sure guess: gone from Monarch, the same last digits or a like name, and clearly ahead of the next one
        top = cands[0] if cands else None
        sure = top and top["gone"] and top["alike"] and (len(cands) < 2 or top["score"] - cands[1]["score"] >= 15)
        out.append({**look, "firstSeen": r["first_seen"].isoformat(), "candidates": cands, "likely": top["id"] if sure else None})
    return out


def held_count() -> int:
    return db.one("SELECT COUNT(*) AS n FROM mny_monarch_new WHERE decision IS NULL")["n"]


def decide(ext: str, how: str, account_id: int = None, by: int = None) -> dict:
    """An admin's answer for a held account: 'new' (the next sync adds it, with its history and transactions), or
    'existing' with the account here it is (that account takes the new Monarch id; the next sync matches the
    transactions so none is there twice)."""
    row = db.one("SELECT * FROM mny_monarch_new WHERE external_id = %s AND decision IS NULL", (ext,))
    if not row:
        raise model.NotFound("No such account waits")
    if how == "new":
        db.ex("UPDATE mny_monarch_new SET decision = 'new', decided_by = %s WHERE external_id = %s", (by, ext))
        return {"ok": True}
    if how != "existing":
        raise Invalid("Say new or existing")
    a = db.one("SELECT * FROM mny_accounts WHERE id = %s AND owner_id IS NULL", (account_id,)) if account_id else None
    if not a:
        raise Invalid("Pick the account it is")
    if a["source"] == "monarch" and a["external_id"] in set(json.loads(model.setting("monarch_ids", "[]") or "[]")):
        raise Invalid(f"{a['name']} is still in Monarch Money under its own id")
    acc = json.loads(row["data"])
    with db.tx():
        db.ex("UPDATE mny_accounts SET source = 'monarch', external_id = %s WHERE id = %s", (ext, a["id"]))
        db.ex("REPLACE INTO mny_monarch_moves (account_id, old_external_id, new_external_id, moved_by) VALUES (%s, %s, %s, %s)",
              (a["id"], a["external_id"] if a["source"] == "monarch" else None, ext, by))
        db.ex("DELETE FROM mny_monarch_new WHERE external_id = %s", (ext,))
    log.info("Monarch account %s (%s) is account %s here", ext, acc.get("displayName"), a["id"])
    return {"ok": True, "accountId": a["id"]}


KIND_OF_SECURITY = {"equity": "stock", "stock": "stock", "etf": "etf", "mutual_fund": "fund", "fund": "fund",
                    "cryptocurrency": "crypto", "crypto": "crypto", "cash": "cash", "fixed_income": "bond", "bond": "bond",
                    "option": "option"}


async def _holdings(mm, ext: str, aid: int) -> int:
    got = await mm.get_account_holdings(int(ext) if ext.isdigit() else ext)
    edges = ((((got or {}).get("portfolio") or {}).get("aggregateHoldings") or {}).get("edges")) or []
    seen, n = set(), 0
    now = dt.datetime.now().replace(microsecond=0)
    for e in edges:
        node = e.get("node") or {}
        sec = node.get("security") or {}
        first = (node.get("holdings") or [{}])[0] or {}
        hid = str(node.get("id") or "")
        if not hid:
            continue
        seen.add(hid)
        sym = (sec.get("ticker") or first.get("ticker") or "").strip().upper() or None
        if sym and not model.SYMBOL.match(sym):
            sym = None
        typ = (sec.get("type") or first.get("type") or "").lower()
        price = sec.get("currentPrice") or sec.get("closingPrice") or first.get("closingPrice")
        if price is None and node.get("quantity"):
            try:
                price = Decimal(str(node.get("totalValue") or 0)) / Decimal(str(node["quantity"]))
            except (ArithmeticError, ValueError):
                price = None
        db.ex("INSERT INTO mny_holdings (account_id, source, external_id, symbol, name, kind, shares, cost_basis, price, price_at) "
              "VALUES (%s, 'monarch', %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE account_id = VALUES(account_id), "
              "symbol = VALUES(symbol), name = VALUES(name), kind = VALUES(kind), shares = VALUES(shares), "
              "cost_basis = VALUES(cost_basis), price = VALUES(price), price_at = VALUES(price_at)",
              (aid, f"{ext}:{hid}"[:64], sym, (sec.get("name") or first.get("name") or "")[:255] or None,
               KIND_OF_SECURITY.get(typ, "other"), Decimal(str(node.get("quantity") or 0)),
               _abs(node["basis"]) if node.get("basis") is not None else None,
               Decimal(str(price)).quantize(Decimal("0.000001")) if price is not None else None, now))
        n += 1
    keep = {f"{ext}:{h}"[:64] for h in seen}
    for r in db.q("SELECT id, external_id FROM mny_holdings WHERE account_id = %s AND source = 'monarch'", (aid,)):
        if r["external_id"] not in keep:
            db.ex("DELETE FROM mny_holdings WHERE id = %s", (r["id"],))
    return n


async def _run(full: bool) -> dict:
    today = dt.date.today()
    _at("Signing in")
    mm = await _client()
    _at("Accounts")
    cats = await mm.get_transaction_categories()
    groups = {str(c.get("id")): ((c.get("group") or {}).get("name")) for c in (cats or {}).get("categories") or []}
    accts = (await mm.get_accounts() or {}).get("accounts") or []
    ids, n_hold, n_held = {}, 0, 0
    # after the first sync, an account Monarch reports that is not here waits for an admin: new, or an account here
    # made again in Monarch (when its bank link broke) under a new id
    ask = bool(db.one("SELECT 1 AS x FROM mny_accounts WHERE source = 'monarch' LIMIT 1"))
    said_new = {r["external_id"] for r in db.q("SELECT external_id FROM mny_monarch_new WHERE decision = 'new'")}
    listed = [str(a["id"]) for a in accts]
    for n, acc in enumerate(accts, 1):
        _at("Accounts and their history", n)
        ext = str(acc["id"])
        if ask and ext not in said_new and not _known(ext):
            _hold(acc)
            n_held += 1
            continue
        aid, new = _put_account(acc, today)
        ids[ext] = aid
        if new:
            await _history(mm, ext, aid, bool(acc.get("isAsset", True)))
    db.ex("DELETE FROM mny_monarch_new WHERE decision = 'new' OR external_id NOT IN "
          f"({db.marks(len(listed)) if listed else 'NULL'})", tuple(listed))
    db.set_setting("monarch_ids", json.dumps(listed))
    # accounts given a new Monarch id: their transactions matched with those kept under the old one
    for mv in db.q("SELECT * FROM mny_monarch_moves WHERE done_at IS NULL"):
        if mv["new_external_id"] in ids:
            _at("Matching the account's transactions")
            await _adopt(mm, mv, ids[mv["new_external_id"]], today, groups)
    last = db.one("SELECT MAX(started_at) AS t FROM mny_syncs WHERE ok = 1")["t"]
    since = today - dt.timedelta(days=INITIAL_DAYS) if full or not last else last.date() - dt.timedelta(days=OVERLAP_DAYS)
    # a transaction pending here is asked again until it posts (Monarch keeps its first date, often weeks before it
    # posts) or is gone (it posted under another id): otherwise it would stay pending here, beside its posted twin
    old = db.one("SELECT MIN(day) AS d FROM mny_transactions WHERE source = 'monarch' AND pending = 1 AND day >= %s",
                 (today - dt.timedelta(days=PENDING_DAYS),))["d"]
    if old and old < since:
        since = old
    _at("Transactions")
    n_tx = await _transactions(mm, ids, since, today, groups)
    _at("Holdings")
    for acc in accts:
        if str(acc["id"]) not in ids:
            continue
        if ((acc.get("type") or {}).get("name") == "brokerage" or acc.get("holdingsCount")) and not acc.get("deactivatedAt"):
            try:
                n_hold += await _holdings(mm, str(acc["id"]), ids[str(acc["id"])])
            except Exception as e:  # noqa: BLE001 - one account's holdings do not stop the rest
                if _unauthorized(e):
                    raise
                log.warning("holdings of Monarch account %s: %s", acc["id"], e)
    return {"accounts": len(ids), "transactions": n_tx, "holdings": n_hold, "held": n_held}


def running() -> bool:
    return _lock.locked()


def start(by: int = None, full: bool = False, wait: float = 0) -> dict:
    """Sync in the background (a first sync of two years takes minutes, longer than a browser or a proxy waits) and
    wait for it up to `wait` seconds: its result when it ended by then, else {running: true, progress}."""
    if running():
        return {"ok": None, "running": True, "message": "A sync is already running", "progress": progress()}
    done = threading.Event()
    box = {}

    def go():
        box["r"] = sync(by, full)
        done.set()
    threading.Thread(target=go, name="monarch-sync", daemon=True).start()
    if done.wait(wait):
        return box["r"]
    return {"ok": None, "running": True, "message": "Syncing with Monarch Money", "progress": progress()}


def progress() -> dict | None:
    if not running():
        return None
    return {"stage": _progress["stage"], "count": _progress["count"],
            "started": _progress["started"].isoformat() if _progress["started"] else None}


def sync(by: int = None, full: bool = False) -> dict:
    """Copy Monarch Money in now; what came in, or why it did not. One sync at a time."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "message": "A sync is already running"}
    started = dt.datetime.now().replace(microsecond=0)
    _progress.update(stage="Starting", count=0, started=started)
    sid = db.ex("INSERT INTO mny_syncs (started_at, by_user) VALUES (%s, %s)", (started, by))
    try:
        got = asyncio.run(_run(full))
        msg = f"{got['accounts']} accounts, {got['transactions']} transactions, {got['holdings']} holdings"
        if got["held"]:
            msg += f"; {got['held']} new account{'s' if got['held'] > 1 else ''} wait{'' if got['held'] > 1 else 's'} for you to say what {'they are' if got['held'] > 1 else 'it is'}"
        db.ex("UPDATE mny_syncs SET finished_at = NOW(), ok = 1, message = %s, accounts = %s, transactions = %s, holdings = %s "
              "WHERE id = %s", (msg, got["accounts"], got["transactions"], got["holdings"], sid))
        log.info("Monarch sync: %s", msg)
        try:
            from app import quotes
            quotes.refresh()
        except Exception as e:  # noqa: BLE001
            log.info("quotes after the sync: %s", e)
        return {"ok": True, "message": msg, **got}
    except NeedsSignIn as e:
        db.ex("UPDATE mny_syncs SET finished_at = NOW(), ok = 0, message = %s WHERE id = %s", (str(e)[:1000], sid))
        return {"ok": False, "message": str(e), "signIn": True}
    except Exception as e:  # noqa: BLE001 - kept in the sync's history, for Settings › Monarch
        log.exception("Monarch sync failed")
        why = f"{type(e).__name__}: {e}"[:1000]
        db.ex("UPDATE mny_syncs SET finished_at = NOW(), ok = 0, message = %s WHERE id = %s", (why, sid))
        return {"ok": False, "message": why}
    finally:
        db.ex("DELETE FROM mny_syncs WHERE started_at < %s", (started - dt.timedelta(days=90),))
        _lock.release()


def status() -> dict:
    last = db.one("SELECT * FROM mny_syncs ORDER BY id DESC LIMIT 1")
    good = db.one("SELECT finished_at FROM mny_syncs WHERE ok = 1 ORDER BY id DESC LIMIT 1")
    keys = {k["name"]: credentials.is_set(APP, k["name"]) for k in KEYS}
    return {"configured": configured(), "keys": keys, "running": running(), "progress": progress(), "every": SYNC_HOURS,
            "auto": model.setting("monarch_auto", "1") == "1",
            "last": {"started": last["started_at"].isoformat(), "finished": last["finished_at"].isoformat() if last["finished_at"] else None,
                     "ok": bool(last["ok"]), "message": last["message"]} if last else None,
            "lastGood": good["finished_at"].isoformat() if good and good["finished_at"] else None,
            "history": [{"started": r["started_at"].isoformat(), "ok": bool(r["ok"]), "message": r["message"]}
                        for r in db.q("SELECT started_at, ok, message FROM mny_syncs ORDER BY id DESC LIMIT 10")]}


def due() -> bool:
    """Whether the automatic sync should run now."""
    if not configured() or model.setting("monarch_auto", "1") != "1" or running():
        return False
    last = db.one("SELECT MAX(started_at) AS t FROM mny_syncs")["t"]
    return last is None or (dt.datetime.now() - last).total_seconds() >= SYNC_HOURS * 3600
