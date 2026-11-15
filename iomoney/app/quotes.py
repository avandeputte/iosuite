"""Quotes: the price of every symbol held, and the exchange rates between the currencies in use, from Yahoo Finance.

No key and no account: the price chart Yahoo Finance's own pages read (query1.finance.yahoo.com/v8/finance/chart/<symbol>)
gives the last price, the previous close, the currency, the name and the closing prices of the past year. A symbol is
as Yahoo writes it: AAPL, VWCE.DE (Xetra), BTC-USD; an exchange rate is EURUSD=X. Asked for every symbol at most every
QUOTE_S seconds (refresh(), from the chores in app/main.py and Quotes on the Portfolio page), one symbol at a time, and only for
what somebody holds. A symbol Yahoo does not know keeps its error (shown beside the holding); a holding without a
quote uses the price kept with it (typed in, or Monarch Money's last closing price).
"""
import datetime as dt
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from app import db

log = logging.getLogger("iomoney.quotes")
URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range}&interval=1d&includePrePost=false"
UA = "Mozilla/5.0 (X11; Linux x86_64) ioMoney"
TIMEOUT = 10
QUOTE_S = 15 * 60          # a quote is asked again after this long
FX_S = 6 * 3600            # an exchange rate after this long
HISTORY_DAYS = 400         # closing prices kept
_fx_cache: dict = {}       # (from, to) -> (rate, at)
FX_CACHE_S = 60

fetcher = None  # tests: a function (symbol, range) -> the chart's JSON, instead of asking Yahoo


def _get(sym: str, rng: str) -> dict:
    if fetcher:
        return fetcher(sym, rng)
    req = urllib.request.Request(URL.format(symbol=urllib.parse.quote(sym, safe=""), range=rng),
                                 headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read(2_000_000))


def _dec(v) -> Decimal | None:
    try:
        return None if v is None else Decimal(str(v))
    except (ValueError, ArithmeticError):
        return None


def fetch(sym: str, history: bool = True) -> dict:
    """Ask Yahoo for one symbol; keep its quote (and closing prices) and return the row as kept."""
    now = dt.datetime.now().replace(microsecond=0)
    rng = "1y" if history else "5d"
    try:
        data = _get(sym, rng)
        res = ((data.get("chart") or {}).get("result") or [None])[0]
        err = ((data.get("chart") or {}).get("error") or {})
        if not res:
            raise ValueError(err.get("description") or "Yahoo Finance does not know this symbol")
        meta = res.get("meta") or {}
        price = _dec(meta.get("regularMarketPrice"))
        if price is None:
            raise ValueError("No price for this symbol")
        prev = _dec(meta.get("previousClose"))
        stamps = res.get("timestamp") or []
        closes = ((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        days = [(dt.datetime.fromtimestamp(t, dt.timezone.utc).date(), _dec(c)) for t, c in zip(stamps, closes) if c is not None]
        if prev is None and len(days) >= 2:
            # the close of the day before the last trading day
            last = dt.datetime.fromtimestamp(meta.get("regularMarketTime") or stamps[-1], dt.timezone.utc).date()
            before = [c for d, c in days if d < last]
            prev = before[-1] if before else None
        when = meta.get("regularMarketTime")
        db.ex("INSERT INTO mny_quotes (symbol, name, currency, price, previous_close, market_time, fetched_at, error) "
              "VALUES (%s, %s, %s, %s, %s, %s, %s, NULL) ON DUPLICATE KEY UPDATE name = VALUES(name), currency = VALUES(currency), "
              "price = VALUES(price), previous_close = VALUES(previous_close), market_time = VALUES(market_time), "
              "fetched_at = VALUES(fetched_at), error = NULL",
              (sym, (meta.get("longName") or meta.get("shortName") or "")[:255] or None,
               (meta.get("currency") or "")[:3].upper() or None, price, prev,
               dt.datetime.fromtimestamp(when) if when else None, now))
        if days:
            db.many("INSERT INTO mny_prices (symbol, day, close) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE close = VALUES(close)",
                    [(sym, d, c) for d, c in days])
    except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError) as e:
        why = str(getattr(e, "reason", None) or e)[:250]
        if isinstance(e, urllib.error.HTTPError) and e.code == 404:
            why = "Yahoo Finance does not know this symbol"
        log.info("quote %s: %s", sym, why)
        db.ex("INSERT INTO mny_quotes (symbol, fetched_at, error) VALUES (%s, %s, %s) "
              "ON DUPLICATE KEY UPDATE fetched_at = VALUES(fetched_at), error = VALUES(error)", (sym, now, why))
    _fx_cache.clear()
    return db.one("SELECT * FROM mny_quotes WHERE symbol = %s", (sym,))


def wanted() -> list[str]:
    """The symbols somebody holds, and the exchange rates the accounts and the holdings need."""
    from app import model
    home = model.home_currency()
    syms = [r["symbol"] for r in db.q("SELECT DISTINCT symbol FROM mny_holdings WHERE symbol IS NOT NULL AND shares <> 0")]
    curs = {r["currency"] for r in db.q("SELECT DISTINCT currency FROM mny_accounts")}
    curs |= {r["currency"] for r in db.q("SELECT DISTINCT q.currency FROM mny_quotes q JOIN mny_holdings h ON h.symbol = q.symbol "
                                         "WHERE q.currency IS NOT NULL")}
    return syms + [fx_symbol(c, home) for c in sorted(c for c in curs if c and c != home and c != pence_of(home))]


def fx_symbol(cur: str, home: str) -> str:
    return f"{base_currency(cur)}{home}=X"


def pence_of(cur: str) -> str | None:
    return {"GBP": "GBp", "ILS": "ILA", "ZAR": "ZAc"}.get(cur)


def base_currency(cur: str) -> str:
    """Yahoo quotes London in pence (GBp), Tel Aviv in agorot (ILA), Johannesburg in cents (ZAc)."""
    return {"GBP": "GBP", "GBp": "GBP", "GBX": "GBP", "ILA": "ILS", "ZAc": "ZAR", "ZAC": "ZAR"}.get(cur, cur.upper())


def _minor(cur: str) -> Decimal:
    return Decimal("0.01") if cur in ("GBp", "GBX", "ILA", "ZAc", "ZAC") else Decimal(1)


def refresh(force: bool = False, symbols: list[str] = None) -> dict:
    """Ask again for every quote older than its time (or all, force), one at a time; how many were asked, and failed."""
    asked = failed = 0
    now = dt.datetime.now()
    old = {r["symbol"]: r for r in db.q("SELECT symbol, fetched_at, error, price FROM mny_quotes")}
    for sym in symbols or wanted():
        r = old.get(sym)
        age = (now - r["fetched_at"]).total_seconds() if r and r["fetched_at"] else None
        limit = FX_S if sym.endswith("=X") else QUOTE_S
        if not force and age is not None and age < limit:
            continue
        got = fetch(sym, history=r is None or r.get("price") is None)
        asked += 1
        failed += 1 if got and got["error"] else 0
        time.sleep(0 if fetcher else 0.3)  # gently: one symbol after another
    if asked:
        cutoff = dt.date.today() - dt.timedelta(days=HISTORY_DAYS)
        db.ex("DELETE FROM mny_prices WHERE day < %s", (cutoff,))
    return {"asked": asked, "failed": failed}


def fx(cur: str, home: str) -> Decimal:
    """How many of `home` one of `cur` is: 1 for the same currency, or while the rate is not known yet."""
    if not cur or not home:
        return Decimal(1)
    minor = _minor(cur)
    cur = base_currency(cur)
    if cur == home:
        return minor
    hit = _fx_cache.get((cur, home))
    if hit and time.time() - hit[1] < FX_CACHE_S:
        return hit[0] * minor
    r = db.one("SELECT price FROM mny_quotes WHERE symbol = %s", (fx_symbol(cur, home),))
    rate = Decimal(r["price"]) if r and r["price"] is not None else Decimal(1)
    _fx_cache[(cur, home)] = (rate, time.time())
    return rate * minor


def quote(sym: str) -> dict:
    """One symbol's quote, asked now when it is not fresh (an assistant's question, the holding form)."""
    r = db.one("SELECT * FROM mny_quotes WHERE symbol = %s", (sym,))
    if not r or not r["fetched_at"] or (dt.datetime.now() - r["fetched_at"]).total_seconds() > QUOTE_S:
        r = fetch(sym, history=True)
    return public(r)


def public(r: dict) -> dict:
    p, prev = r.get("price"), r.get("previous_close")
    return {"symbol": r["symbol"], "name": r.get("name"), "currency": r.get("currency"),
            "price": float(p) if p is not None else None, "previousClose": float(prev) if prev is not None else None,
            "changePct": float((Decimal(p) / Decimal(prev) - 1) * 100) if p is not None and prev else None,
            "marketTime": r["market_time"].isoformat() if r.get("market_time") else None,
            "fetched": r["fetched_at"].isoformat() if r.get("fetched_at") else None, "error": r.get("error")}


def closes(sym: str, days: int = 365) -> list[dict]:
    rows = db.q("SELECT day, close FROM mny_prices WHERE symbol = %s AND day >= %s ORDER BY day",
                (sym, dt.date.today() - dt.timedelta(days=days)))
    return [{"day": r["day"].isoformat(), "close": float(r["close"])} for r in rows]
