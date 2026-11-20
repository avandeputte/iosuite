"""Exchange rates for the search box's currency conversions ("120 usd in eur"): the European Central Bank's reference
rates of the working day, through Frankfurter (api.frankfurter.dev, free, no key), about 30 currencies against the euro.

Fetched when somebody first converts a currency, then kept in prt_settings for RATES_TTL; when Frankfurter cannot be
reached the last rates are served with their date (the page says which day they are from), and nothing at all only
before the first answer. The page works out every pair from the one list (usd → gbp through the euro)."""
import json
import threading
import time
import urllib.error
import urllib.request

from app import db

URL = "https://api.frankfurter.dev/v1/latest?base=EUR"
RATES_TTL = 6 * 3600
RETRY_S = 15 * 60  # after a failed fetch, the last rates are served for this long before asking again
_lock = threading.Lock()


class RatesError(Exception):
    pass


def _fetch() -> dict:
    """{date, rates: {USD: 1.08, ...}} against the euro. Replaced in the tests."""
    req = urllib.request.Request(URL, headers={"Accept": "application/json", "User-Agent": "iostart"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            got = json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise RatesError(f"Could not reach the exchange rates: {str(e)[:120]}")
    rates = {k.upper(): float(v) for k, v in (got.get("rates") or {}).items() if isinstance(k, str) and len(k) == 3 and isinstance(v, (int, float)) and v > 0}
    if not rates:
        raise RatesError("The exchange rates came back empty")
    rates["EUR"] = 1.0
    return {"date": str(got.get("date") or "")[:10], "rates": rates}


def get() -> dict:
    """{date, rates, base: 'EUR'}: the rates against the euro, fetched when the kept ones are older than RATES_TTL."""
    with _lock:
        try:
            kept = json.loads(db.get_setting("rates") or "null")
        except ValueError:
            kept = None
        now = time.time()
        if kept and now - kept.get("at", 0) < (RATES_TTL if not kept.get("failed") else RETRY_S):
            return {"base": "EUR", "date": kept["date"], "rates": kept["rates"]}
        try:
            got = _fetch()
        except RatesError:
            if not kept:
                raise
            kept.update(at=now, failed=True)  # the old ones, again for a while
            db.set_setting("rates", json.dumps(kept))
            return {"base": "EUR", "date": kept["date"], "rates": kept["rates"]}
        db.set_setting("rates", json.dumps({"at": now, **got}))
        return {"base": "EUR", **got}
