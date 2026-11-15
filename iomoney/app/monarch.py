"""Monarch Money: the household's accounts, balances, transactions, holdings and coming bills, copied in.

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
- transactions: those since the last sync (two weeks back, for late changes), or the past INITIAL_DAYS the first time.
  A transaction whose category, notes or hidden was changed here keeps those. One that disappeared from Monarch inside
  the window (a pending one that posted under another id, one deleted there) goes here too.
- holdings of the investment accounts, with Monarch's last price (used while there is no quote).
- the recurring transactions from a month back to two months ahead: the bills ioCalendar shows.
"""
import asyncio
import datetime as dt
import json
import logging
import threading
from decimal import Decimal

from iosuite_shared import credentials

from app import config, db, model

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
PAGE = 500              # transactions per request
BILLS_BACK, BILLS_AHEAD = 31, 62
TIMEOUT = 60
SYNC_HOURS = 6

_lock = threading.Lock()
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


async def _transactions(mm, ids: dict, since: dt.date, today: dt.date, groups: dict) -> int:
    seen, offset, n = set(), 0, 0
    while True:
        got = await mm.get_transactions(limit=PAGE, offset=offset, start_date=since.isoformat(), end_date=today.isoformat())
        page = ((got or {}).get("allTransactions") or {}).get("results") or []
        for t in page:
            aid = ids.get(str((t.get("account") or {}).get("id")))
            if not aid:
                continue
            ext = str(t["id"])
            seen.add(ext)
            cat = (t.get("category") or {})
            merchant = (t.get("merchant") or {}).get("name")
            tags = [x.get("name") for x in (t.get("tags") or []) if x.get("name")]
            day = dt.date.fromisoformat(str(t["date"])[:10])
            amt = Decimal(str(t.get("amount") or 0)).quantize(model.CENT)
            grp = groups.get(str(cat.get("id"))) if cat else None
            w = model.words(merchant, t.get("plaidName"), cat.get("name"), grp, t.get("notes"), ",".join(tags))
            db.ex("INSERT INTO mny_transactions (account_id, source, external_id, day, amount, merchant, description, category, "
                  "category_group, notes, tags, pending, hidden, recurring, words) "
                  "VALUES (%s, 'monarch', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                  "ON DUPLICATE KEY UPDATE account_id = VALUES(account_id), day = VALUES(day), amount = VALUES(amount), "
                  "description = VALUES(description), tags = VALUES(tags), pending = VALUES(pending), recurring = VALUES(recurring), "
                  "merchant = IF(edited, merchant, VALUES(merchant)), category = IF(edited, category, VALUES(category)), "
                  "category_group = IF(edited, category_group, VALUES(category_group)), notes = IF(edited, notes, VALUES(notes)), "
                  "hidden = IF(edited, hidden, VALUES(hidden)), words = IF(edited, words, VALUES(words))",
                  (aid, ext, day, amt, (merchant or "")[:255] or None, (t.get("plaidName") or "")[:255] or None,
                   (cat.get("name") or "")[:128] or None, (grp or "")[:128] or None, t.get("notes") or None,
                   json.dumps(tags) if tags else None, 1 if t.get("pending") else 0, 1 if t.get("hideFromReports") else 0,
                   1 if t.get("isRecurring") else 0, w))
            n += 1
        if len(page) < PAGE:
            break
        offset += PAGE
    # gone from Monarch inside the window: a pending one that posted under another id, one deleted there
    old = db.q("SELECT id, external_id FROM mny_transactions WHERE source = 'monarch' AND day BETWEEN %s AND %s", (since, today))
    gone = [r["id"] for r in old if r["external_id"] not in seen]
    if gone:
        db.ex(f"DELETE FROM mny_transactions WHERE id IN ({db.marks(len(gone))})", gone)
    # the household's rules, over what just came in (Monarch's own payee and category, unless changed here by hand)
    model.apply_rules("t.source = 'monarch' AND t.day BETWEEN %s AND %s", (since, today))
    return n


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


async def _bills(mm, ids: dict, today: dt.date) -> int:
    start, end = today - dt.timedelta(days=BILLS_BACK), today + dt.timedelta(days=BILLS_AHEAD)
    got = await mm.get_recurring_transactions(start.isoformat(), end.isoformat())
    items = (got or {}).get("recurringTransactionItems") or []
    seen, now = set(), dt.datetime.now().replace(microsecond=0)
    for it in items:
        stream = it.get("stream") or {}
        try:
            day = dt.date.fromisoformat(str(it.get("date"))[:10])
        except ValueError:
            continue
        key = f"{stream.get('id') or ''}:{day.isoformat()}"[:128]
        seen.add(key)
        amt = it.get("amount") if it.get("amount") is not None else stream.get("amount")
        db.ex("INSERT INTO mny_bills (ext_key, stream_id, day, merchant, amount, approximate, frequency, category, account_id, paid, seen_at) "
              "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON DUPLICATE KEY UPDATE merchant = VALUES(merchant), "
              "amount = VALUES(amount), approximate = VALUES(approximate), frequency = VALUES(frequency), category = VALUES(category), "
              "account_id = VALUES(account_id), paid = VALUES(paid), seen_at = VALUES(seen_at)",
              (key, str(stream.get("id") or "")[:64] or None, day, ((stream.get("merchant") or {}).get("name") or "")[:255] or None,
               Decimal(str(amt or 0)).quantize(model.CENT), 1 if stream.get("isApproximate") else 0,
               (stream.get("frequency") or "")[:32] or None, ((it.get("category") or {}).get("name") or "")[:128] or None,
               ids.get(str((it.get("account") or {}).get("id"))), 1 if (it.get("isPast") and it.get("transactionId")) else 0, now))
    old = db.q("SELECT id, ext_key FROM mny_bills WHERE day BETWEEN %s AND %s", (start, end))
    gone = [r["id"] for r in old if r["ext_key"] not in seen]
    if gone:
        db.ex(f"DELETE FROM mny_bills WHERE id IN ({db.marks(len(gone))})", gone)
    db.ex("DELETE FROM mny_bills WHERE day < %s", (today - dt.timedelta(days=400),))
    return len(items)


async def _run(full: bool) -> dict:
    today = dt.date.today()
    mm = await _client()
    cats = await mm.get_transaction_categories()
    groups = {str(c.get("id")): ((c.get("group") or {}).get("name")) for c in (cats or {}).get("categories") or []}
    accts = (await mm.get_accounts() or {}).get("accounts") or []
    ids, n_hold = {}, 0
    for acc in accts:
        aid, new = _put_account(acc, today)
        ids[str(acc["id"])] = aid
        if new:
            await _history(mm, str(acc["id"]), aid, bool(acc.get("isAsset", True)))
    last = db.one("SELECT MAX(started_at) AS t FROM mny_syncs WHERE ok = 1")["t"]
    since = today - dt.timedelta(days=INITIAL_DAYS) if full or not last else last.date() - dt.timedelta(days=OVERLAP_DAYS)
    n_tx = await _transactions(mm, ids, since, today, groups)
    for acc in accts:
        if ((acc.get("type") or {}).get("name") == "brokerage" or acc.get("holdingsCount")) and not acc.get("deactivatedAt"):
            try:
                n_hold += await _holdings(mm, str(acc["id"]), ids[str(acc["id"])])
            except Exception as e:  # noqa: BLE001 - one account's holdings do not stop the rest
                if _unauthorized(e):
                    raise
                log.warning("holdings of Monarch account %s: %s", acc["id"], e)
    try:
        await _bills(mm, ids, today)
    except Exception as e:  # noqa: BLE001 - the bills are a bonus
        if _unauthorized(e):
            raise
        log.warning("Monarch's recurring transactions: %s", e)
    return {"accounts": len(accts), "transactions": n_tx, "holdings": n_hold}


def running() -> bool:
    return _lock.locked()


def sync(by: int = None, full: bool = False) -> dict:
    """Copy Monarch Money in now; what came in, or why it did not. One sync at a time."""
    if not _lock.acquire(blocking=False):
        return {"ok": False, "message": "A sync is already running"}
    started = dt.datetime.now().replace(microsecond=0)
    sid = db.ex("INSERT INTO mny_syncs (started_at, by_user) VALUES (%s, %s)", (started, by))
    try:
        got = asyncio.run(_run(full))
        msg = f"{got['accounts']} accounts, {got['transactions']} transactions, {got['holdings']} holdings"
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
    return {"configured": configured(), "keys": keys, "running": running(), "every": SYNC_HOURS,
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
