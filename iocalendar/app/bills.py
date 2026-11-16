"""ioMoney, when it is part of the suite: the household's coming bills (the recurring transactions ioMoney keeps: the
power bill, the mortgage, a subscription, a paycheck) show on the day they are due, beside the events.

Nothing to set up: ioMoney is found in the suite's list of apps. As with the tasks (app/tasks.py), the bills are asked
for on the viewer's behalf (iosuite_shared.links.as_viewer, with the viewer's own credentials), so ioMoney answers only
to someone with a role there, with the bills of the accounts that person sees. Anyone else simply has no bills on the
calendar: ioMoney's money is shown only to those it is shown to there. Nothing is kept here.
"""
import datetime as dt
import urllib.error

from fastapi import Request
from iosuite_shared import links

PROVIDER = "iomoney"
TIMEOUT = 5  # seconds, per request


class Unavailable(Exception):
    """ioMoney could not be asked, or would not answer: (status, why)."""

    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def enabled() -> bool:
    try:
        return links.available(PROVIDER)
    except Exception:  # noqa: BLE001 - no database yet
        return False


def url() -> str:
    """Where the browser opens ioMoney ('' when it is not part of the suite)."""
    try:
        return links.url(PROVIDER) or ""
    except Exception:  # noqa: BLE001
        return ""


def forget() -> None:
    """ioMoney may be asked again, from its first address on (the tests)."""
    links.ask_again(PROVIDER)


def between(request: Request, start: dt.date, end: dt.date) -> list[dict]:
    """The bills due from start up to end (end not included) that the viewer sees in ioMoney:
    [{id, day, merchant, amount, currency, approximate, frequency, category, account, paid}], by day."""
    if not enabled():
        raise Unavailable(404, "ioMoney is not part of the suite")
    if links.resting(PROVIDER):
        raise Unavailable(502, "ioMoney did not answer a moment ago")
    q = {"start": start.isoformat(), "end": (end - dt.timedelta(days=1)).isoformat()}
    try:
        got = links.as_viewer(request, PROVIDER, "/api/bills", q, timeout=TIMEOUT, user_agent="ioCalendar")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise Unavailable(403, "No role in ioMoney")
        raise Unavailable(502, f"ioMoney answered {e.code}")
    except links.Unreachable as e:
        raise Unavailable(502, f"ioMoney is not reachable ({type(e.why).__name__ if e.why else 'no address'})")
    out = []
    for b in got.get("items", []):
        day = str(b.get("day") or "")[:10]
        if not start.isoformat() <= day < end.isoformat():
            continue
        out.append({"id": b.get("id"), "day": day, "merchant": b.get("merchant") or "Bill", "amount": b.get("amount"),
                    "currency": b.get("currency") or got.get("currency"), "approximate": bool(b.get("approximate")),
                    "frequency": b.get("frequency"), "category": b.get("category"), "account": b.get("account"),
                    "paid": bool(b.get("paid"))})
    out.sort(key=lambda b: (b["day"], (b["merchant"] or "").lower()))
    return out
