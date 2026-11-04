"""What the tiles show under their name: a glimpse of each app (ioPix's On this day, ioCalendar's today, ioHealth's
steps and rings), asked of the app over its own API.

The start page asks on the viewer's behalf: the request goes out from this server with the viewer's own credentials
(the suite's shared session cookie, or the Authorization header they came with), so each app answers with what that
person may see there and nothing more. Nothing is kept here. The browser never talks to the apps itself (the page's
Content-Security-Policy allows only this origin), so ioPix's thumbnails come through here too.

Every app is asked with a short timeout: an app that is down, or that this account has no access to, leaves its tile
as it was (the page hides the block) instead of holding up the others.
"""
import datetime as dt
import json
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Request
from iothing_auth import sessions

from app import apps

TIMEOUT = 4  # seconds, per request to an app
UA = "ioSuite start page"
WIDGETS = ("iopix", "iocalendar", "iohealth")


class Unavailable(Exception):
    """The app could not be asked, or would not answer: (status, why). An app's 401 is a 403 here: the viewer is signed
    in to the start page, just not let in there (a 401 would send the page to its sign-in)."""

    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def _headers(request: Request) -> dict:
    """The viewer's credentials, passed on as they came: the shared session cookie, else Basic / Bearer."""
    h = {"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "identity"}
    tok = request.cookies.get(sessions.COOKIE)
    if tok:
        h["Cookie"] = f"{sessions.COOKIE}={tok}"
    elif request.headers.get("authorization"):
        h["Authorization"] = request.headers["authorization"]
    return h


def _host(request: Request) -> str:
    return request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc


def fetch(request: Request, key: str, path: str, params: dict | None = None, raw: bool = False):
    """GET path from the app (JSON, or (bytes, content type) with raw)."""
    base = apps.url_for(key, _host(request))
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers=_headers(request) if not raw else {**_headers(request), "Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - an http(s) address an admin set
            body = r.read()
            if raw:
                return body, r.headers.get("Content-Type", "application/octet-stream")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        raise Unavailable(403 if e.code in (401, 403) else 404 if e.code == 404 else 502, f"{key} answered {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Unavailable(502, f"{key} is not reachable ({type(e).__name__})")


def _zone(tz: str):
    try:
        return ZoneInfo(tz) if tz else dt.timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return dt.timezone.utc


# ------------------------------------------------------------------ ioPix: On this day, else Rediscover

def iopix(request: Request, tz: str = "", n: int = 4, kind: str = "") -> dict:
    """{kind: onthisday | rediscover, items: [{id, year, yearsAgo}]}: photos taken on this day in earlier years, one
    per year (the most recent years first) up to n; on a day without any, n photos picked at random from the library.
    kind asks for one of the two (onthisday still falls back to rediscover on a day without photos)."""
    today = dt.datetime.now(_zone(tz)).date()
    by_year: dict[int, list[int]] = {}
    if kind != "rediscover":
        got = fetch(request, "iopix", "/api/photos", {"md": today.strftime("%m-%d"), "type": "photo"})
        for pid, ts in zip(got.get("id") or [], got.get("ts") or []):
            if ts is None:
                continue
            y = dt.datetime.fromtimestamp(ts, dt.timezone.utc).year  # ioPix keeps the camera's wall time as if it were UTC
            if y < today.year:
                by_year.setdefault(y, []).append(pid)
    if by_year:
        items = [{"id": random.choice(by_year[y]), "year": y, "yearsAgo": today.year - y} for y in sorted(by_year, reverse=True)[:n]]
        return {"kind": "onthisday", "items": items, "count": sum(len(v) for v in by_year.values())}
    got = fetch(request, "iopix", "/api/random", {"n": n})
    items = [{"id": pid, "year": dt.datetime.fromtimestamp(ts, dt.timezone.utc).year if ts else None}
             for pid, ts in zip(got.get("id") or [], got.get("ts") or [])]
    return {"kind": "rediscover", "items": items}


def iopix_thumb(request: Request, photo_id: int) -> tuple[bytes, str]:
    return fetch(request, "iopix", f"/thumb/{int(photo_id)}", {"fit": "square"}, raw=True)


# ------------------------------------------------------------------ ioCalendar: the rest of today, else what's next

def iocalendar(request: Request, tz: str = "", n: int = 3) -> dict:
    """{today: [occurrence], next: occurrence | null}: today's events that have not ended yet (all-day ones first, as
    ioCalendar sorts them), up to n; when there are none left, the next one in the coming 60 days. Each with its
    calendar's colour."""
    zone = _zone(tz)
    now = dt.datetime.now(zone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=1)
    colors = {c["id"]: c.get("color") for c in fetch(request, "iocalendar", "/api/calendars").get("items", [])}

    def pick(o: dict) -> dict:
        return {"title": o.get("title") or "(no title)", "start": o.get("start"), "end": o.get("end"), "allDay": bool(o.get("allDay")),
                "location": o.get("location"), "color": colors.get(o.get("calendarId"))}

    def ends_after(o: dict, t: dt.datetime) -> bool:
        if o.get("allDay"):
            return True
        try:
            e = dt.datetime.fromisoformat(o["end"])
        except (KeyError, TypeError, ValueError):
            return True
        return (e if e.tzinfo else e.replace(tzinfo=zone)) > t

    def cancelled(o: dict) -> bool:
        return (o.get("status") or "").upper() == "CANCELLED"

    occ = fetch(request, "iocalendar", "/api/occurrences", {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")})
    today = [pick(o) for o in occ.get("items", []) if not cancelled(o) and ends_after(o, now)]
    out = {"today": today[:n], "more": max(0, len(today) - n), "next": None}
    if not today:
        later = fetch(request, "iocalendar", "/api/occurrences", {"start": end.isoformat(timespec="seconds"),
                                                                  "end": (end + dt.timedelta(days=60)).isoformat(timespec="seconds")})
        nxt = next((o for o in later.get("items", []) if not cancelled(o)), None)
        out["next"] = pick(nxt) if nxt else None
    return out


# ------------------------------------------------------------------ ioHealth: today's steps and activity rings

def iohealth(request: Request, tz: str = "") -> dict:
    """{steps, rings: {move, moveGoal, exercise, exerciseGoal, stand, standGoal} | null} for the viewer's today."""
    day = dt.datetime.now(_zone(tz)).date().isoformat()
    q = {"from": day, "to": day}
    if tz:
        q["tz"] = tz
    steps = rings = None
    failed = []
    try:
        pts = fetch(request, "iohealth", "/api/series", {**q, "type": "step_count", "bucket": "day"}).get("points") or []
        steps = round(pts[-1]["v"]) if pts else None
    except Unavailable as e:
        failed.append(e)
    try:
        a = fetch(request, "iohealth", "/api/activity", q)
        rows = a if isinstance(a, list) else a.get("items", [])
        if rows:
            rings = {k: rows[-1].get(k) for k in ("move", "moveGoal", "exercise", "exerciseGoal", "stand", "standGoal")}
    except Unavailable as e:
        failed.append(e)
    if len(failed) == 2:  # one of the two missing still shows the other
        raise failed[0]
    return {"steps": steps, "rings": rings}


def get(request: Request, key: str, tz: str = "", kind: str = "", n: int = 0) -> dict:
    if key not in WIDGETS:
        raise Unavailable(404, f"{key} has nothing to show here")
    if tz and not re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz):
        tz = ""
    if key == "iopix":
        return iopix(request, tz, min(max(int(n or 0), 1), 24) if n else 4, kind if kind in ("onthisday", "rediscover") else "")
    return {"iocalendar": iocalendar, "iohealth": iohealth}[key](request, tz)
