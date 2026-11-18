"""ioDocs, when it is part of the suite: the day a passport, a driver's license or an insurance policy expires shows
on the calendar, beside the events.

Nothing to set up: ioDocs is found in the suite's list of apps. As with the bills (app/bills.py), the documents are
asked for on the viewer's behalf (iosuite_shared.links.as_viewer, with the viewer's own credentials), so each person
sees only the documents ioDocs shows them. Nothing is kept here.
"""
import datetime as dt
import urllib.error

from fastapi import Request
from iosuite_shared import links

PROVIDER = "iodocs"
TIMEOUT = 5  # seconds, per request


class Unavailable(Exception):
    """ioDocs could not be asked, or would not answer: (status, why)."""

    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def enabled() -> bool:
    try:
        return links.available(PROVIDER)
    except Exception:  # noqa: BLE001 - no database yet
        return False


def url() -> str:
    """Where the browser opens ioDocs ('' when it is not part of the suite)."""
    try:
        return links.url(PROVIDER) or ""
    except Exception:  # noqa: BLE001
        return ""


def forget() -> None:
    """ioDocs may be asked again, from its first address on (the tests)."""
    links.ask_again(PROVIDER)


def between(request: Request, start: dt.date, end: dt.date) -> list[dict]:
    """The documents the viewer sees in ioDocs that expire from start up to end (end not included):
    [{id, day, title, kind, members: [family member ids]}], by day."""
    if not enabled():
        raise Unavailable(404, "ioDocs is not part of the suite")
    if links.resting(PROVIDER):
        raise Unavailable(502, "ioDocs did not answer a moment ago")
    q = {"start": start.isoformat(), "end": (end - dt.timedelta(days=1)).isoformat()}
    try:
        got = links.as_viewer(request, PROVIDER, "/api/expiring", q, timeout=TIMEOUT, user_agent="ioCalendar")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise Unavailable(403, "No role in ioDocs")
        raise Unavailable(502, f"ioDocs answered {e.code}")
    except links.Unreachable as e:
        raise Unavailable(502, f"ioDocs is not reachable ({type(e.why).__name__ if e.why else 'no address'})")
    out = []
    for d in got.get("items", []):
        day = str(d.get("expiresOn") or "")[:10]
        if not start.isoformat() <= day < end.isoformat():
            continue
        out.append({"id": d.get("id"), "day": day, "title": d.get("title") or "Document", "kind": d.get("kindLabel") or "",
                    "members": [p["id"] for p in d.get("people") or [] if isinstance(p, dict) and isinstance(p.get("id"), int)]})
    out.sort(key=lambda d: (d["day"], d["title"].lower()))
    return out
