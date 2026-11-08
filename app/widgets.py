"""What the tiles show under their name: a glimpse of each app (ioPix's On this day, ioCalendar's today, ioHealth's
steps and rings), asked of the app over its own API.

The start page asks on the viewer's behalf: the request goes out from this server with the viewer's own credentials
(the suite's shared session cookie, or the Authorization header they came with), so each app answers with what that
person may see there and nothing more. Nothing is kept here. The browser never talks to the apps itself (the page's
Content-Security-Policy allows only this origin), so ioPix's thumbnails come through here too.

The app is found in the suite's list of apps and asked the way the apps ask each other (iosuite_shared.links):
on localhost when it runs on this machine, then at its address inside the network, then at its public one; the
suite's Cloudflare Access service token goes with every request when one is set (Settings › Global settings › Keys and
tokens). Only the address and the Cloudflare headers come from there: the credentials stay the viewer's own.

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
from iosuite_shared import links, sessions

from app import apps

TIMEOUT = 4  # seconds, per request to an app
UA = "ioSuite start page"
WIDGETS = ("iopix", "iocalendar", "iohealth", "iocontacts")


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


def _cf_headers() -> dict:
    """The suite's Cloudflare Access service token, when one is set ({} otherwise, or while the database is away)."""
    try:
        return links.headers(apps.SELF, "", sign_in=False)
    except Exception:  # noqa: BLE001
        return {}


def _bases(key: str) -> list[str]:
    """Where to ask the app, in order: localhost, its LAN address, its public one."""
    try:
        got = links.addresses(key)
    except Exception:  # noqa: BLE001  the shared database is away
        got = []
    return got or ([apps.url_for(key)] if apps.url_for(key) else [])


def _host(request: Request) -> str:
    return request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc


def _send(request: Request, key: str, path: str, params, raw: bool, body, timeout: float):
    """Ask each address in turn until one answers (an HTTP error is an answer)."""
    bases = _bases(key)
    query = "?" + urllib.parse.urlencode(params) if params else ""
    headers = {**_headers(request), **_cf_headers()}
    if raw:
        headers["Accept"] = "image/*"
    data = None
    if body is not None:
        data, headers = json.dumps(body).encode(), {**headers, "Content-Type": "application/json"}
    for i, base in enumerate(bases):
        req = urllib.request.Request(base + path + query, data=data, headers=headers, method="POST" if body is not None else "GET")
        try:
            return _ask(req, raw, timeout)
        except urllib.error.HTTPError:
            raise  # it answered
        except (urllib.error.URLError, OSError):
            if i == len(bases) - 1:
                raise
    raise urllib.error.URLError("not in the suite's list of apps")


def _ask(req, raw: bool, timeout: float):
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - an http(s) address from the suite's list
        got = r.read()
        if raw:
            return got, r.headers.get("Content-Type", "application/octet-stream")
        return json.loads(got)


def fetch(request: Request, key: str, path: str, params: dict | None = None, raw: bool = False, body: dict | None = None, timeout: float = TIMEOUT):
    """GET path from the app (JSON, or (bytes, content type) with raw); with body, POST that JSON instead."""
    bases = _bases(key)
    base = bases[0] if bases else "(no address)"
    try:
        return _send(request, key, path, params, raw, body, timeout)
    except urllib.error.HTTPError as e:
        name = apps.name_of(key)
        if body is not None and e.code in (400, 403, 409):  # ioCalendar's own word on what it would not take
            try:
                why = json.loads(e.read()).get("detail")
            except (ValueError, AttributeError):
                why = None
            raise Unavailable(400, why if isinstance(why, str) else f"{name} would not take it ({e.code})")
        if e.code in (401, 403):
            raise Unavailable(403, f"{name} does not let this account in ({e.code}); open it once and sign in there")
        if e.code == 404:
            raise Unavailable(404, f"{name} has no {path} (an older version, or the address is not {name}'s)")
        raise Unavailable(502, f"{name} answered {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Unavailable(502, f"{apps.name_of(key)} is not reachable at {base} ({type(e).__name__})")


def _zone(tz: str):
    try:
        return ZoneInfo(tz) if tz else dt.timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return dt.timezone.utc


# ------------------------------------------------------------------ ioPix: On this day, else Rediscover

def iopix(request: Request, tz: str = "", n: int = 4, kind: str = "") -> dict:
    """{kind: onthisday | rediscover, items: [{id, year, yearsAgo}], count}: up to n photos taken on this day in
    earlier years, one from each year first (the most recent years first), then the rest of those years; count is
    how many there are in all. On a day without any, n photos picked at random from the library. kind asks for one
    of the two (onthisday still falls back to rediscover on a day without photos)."""
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
        years = sorted(by_year, reverse=True)
        for y in years:
            random.shuffle(by_year[y])
        items: list[dict] = []
        for i in range(max(len(v) for v in by_year.values())):  # round i: the i-th photo of each year
            items += [{"id": by_year[y][i], "year": y, "yearsAgo": today.year - y} for y in years if i < len(by_year[y])]
        return {"kind": "onthisday", "items": items[:n], "count": sum(len(v) for v in by_year.values())}
    got = fetch(request, "iopix", "/api/random", {"n": n})
    ws, hs = got.get("w") or [], got.get("h") or []
    items = [{"id": pid, "year": dt.datetime.fromtimestamp(ts, dt.timezone.utc).year if ts else None,
              **({"w": ws[i], "h": hs[i]} if i < len(ws) and i < len(hs) and ws[i] and hs[i] else {})}  # the wall display prefers landscape ones
             for i, (pid, ts) in enumerate(zip(got.get("id") or [], got.get("ts") or []))]
    return {"kind": "rediscover", "items": items}


def iopix_thumb(request: Request, photo_id: int) -> tuple[bytes, str]:
    return fetch(request, "iopix", f"/thumb/{int(photo_id)}", {"fit": "square"}, raw=True)


def iopix_preview(request: Request, photo_id: int) -> tuple[bytes, str]:
    """ioPix's screen-size copy (the wall display's slideshow); ioPix may have to make it first, so a longer wait."""
    return fetch(request, "iopix", f"/preview/{int(photo_id)}", raw=True, timeout=20)


# ------------------------------------------------------------------ ioCalendar: the rest of today, else what's next

def _covers(o: dict, day: dt.date) -> bool:
    """Whether an all-day occurrence (dates, end exclusive) falls on `day`. ioCalendar answers a window with the all-day
    events of the days around it too (it pads by 14 hours for other time zones), so yesterday's birthday comes back
    for today's window: this keeps only what is on the day."""
    try:
        s = dt.date.fromisoformat(str(o.get("start"))[:10])
        e = dt.date.fromisoformat(str(o.get("end") or o.get("start"))[:10])
    except ValueError:
        return True
    return s <= day < max(e, s + dt.timedelta(days=1))


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
    today = [pick(o) for o in occ.get("items", []) if not cancelled(o) and ends_after(o, now) and (not o.get("allDay") or _covers(o, now.date()))]
    out = {"today": today[:n], "more": max(0, len(today) - n), "next": None}
    if not today:
        later = fetch(request, "iocalendar", "/api/occurrences", {"start": end.isoformat(timespec="seconds"),
                                                                  "end": (end + dt.timedelta(days=60)).isoformat(timespec="seconds")})
        nxt = next((o for o in later.get("items", []) if not cancelled(o) and (not o.get("allDay") or _covers(o, end.date()) or dt.date.fromisoformat(str(o["start"])[:10]) >= end.date())), None)
        out["next"] = pick(nxt) if nxt else None
    return out


def iocalendar_week(request: Request, tz: str = "", days: int = 7, n: int = 12) -> dict:
    """{days: [{date, items: [occurrence]}]}: the coming `days` days after today, each with its events (cancelled ones
    left out), up to n events in all; days without any are left out."""
    zone = _zone(tz)
    start = (dt.datetime.now(zone) + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=days)
    colors = {c["id"]: c.get("color") for c in fetch(request, "iocalendar", "/api/calendars").get("items", [])}
    occ = fetch(request, "iocalendar", "/api/occurrences", {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")})
    by_day: dict[str, list] = {}
    total = 0
    first, last = start.date(), (end - dt.timedelta(days=1)).date()
    for o in occ.get("items", []):
        if (o.get("status") or "").upper() == "CANCELLED":
            continue
        day = str(o.get("start") or "")[:10]
        if not day:
            continue
        if o.get("allDay"):
            # an all-day event from before the window (ioCalendar pads its answer) goes on its first day in the window, or out
            if day < first.isoformat():
                day = first.isoformat() if _covers(o, first) else ""
            if not day or day > last.isoformat():
                continue
        if total < n:
            by_day.setdefault(day, []).append({"title": o.get("title") or "(no title)", "start": o.get("start"), "end": o.get("end"),
                                               "allDay": bool(o.get("allDay")), "location": o.get("location"), "color": colors.get(o.get("calendarId"))})
        total += 1
    return {"days": [{"date": d, "items": by_day[d]} for d in sorted(by_day)], "more": max(0, total - n)}


# ------------------------------------------------------------------ ioCalendar: a new event from the search box

def iocalendar_calendars(request: Request) -> dict:
    """{items: [{id, name, color}]}: the calendars this viewer may add events to, as ioCalendar lists them (its own
    order, so the first is where ioCalendar itself would put a new event)."""
    got = fetch(request, "iocalendar", "/api/calendars")
    return {"items": [{"id": c.get("id"), "name": c.get("name"), "color": c.get("color")} for c in got.get("items", []) if c.get("writable")]}


def iocalendar_add(request: Request, b: dict) -> dict:
    """A new event in ioCalendar, from {title, start, end?, allDay, timezone?, calendarId?}: start / end are ISO
    (a date for an all-day event, a date and time with its offset otherwise); no end is an hour (or the day).
    {id, url}: the event and where it opens in ioCalendar."""
    if not isinstance(b, dict):
        raise Unavailable(400, "An object, please")
    title = str(b.get("title") or "").strip()[:500]
    start = str(b.get("start") or "").strip()
    if not title or not start:
        raise Unavailable(400, "A title and a start, please")
    all_day = bool(b.get("allDay"))
    try:
        if all_day:
            dt.date.fromisoformat(start[:10])
        else:
            dt.datetime.fromisoformat(start)
        if b.get("end"):
            (dt.date.fromisoformat if all_day else dt.datetime.fromisoformat)(str(b["end"])[:10] if all_day else str(b["end"]))
    except ValueError:
        raise Unavailable(400, "start / end: ISO dates (and times)")
    ev = {"title": title, "start": start[:10] if all_day else start, "allDay": all_day}
    if b.get("end"):
        ev["end"] = str(b["end"])[:10] if all_day else str(b["end"])
    tz = str(b.get("timezone") or "")
    if tz and re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz):
        ev["timezone"] = tz
    if b.get("calendarId") not in (None, ""):
        ev["calendarId"] = b["calendarId"]
    got = fetch(request, "iocalendar", "/api/events", body=ev)
    eid = got.get("id") if isinstance(got, dict) else None
    return {"id": eid, "url": f"{apps.url_for('iocalendar', _host(request))}/#/event/{eid}" if eid is not None else None}


# ------------------------------------------------------------------ ioContacts: birthdays and anniversaries ahead

def iocontacts(request: Request, days: int = 30, n: int = 8) -> dict:
    """{items: [{id, name, hasPhoto, iopixPersonId, label, turns, in, date}]}: the family's birthdays and other dates in
    the next `days` days, soonest first, up to n. A contact without a photo of its own may still have a face in ioPix
    (iopixPersonId), which ioContacts shows in its place; so does the card. A birthday whose "Remind me" box is unchecked
    in ioContacts (remind false) is left out; other dates carry no such box (remind null) and always show."""
    got = fetch(request, "iocontacts", "/api/upcoming", {"days": max(1, min(days, 366))})
    items = []
    for x in got.get("items", []):
        if x.get("remind") is False:
            continue
        items.append({"id": x.get("contactId"), "name": x.get("fn"), "hasPhoto": bool(x.get("hasPhoto")),
                      "iopixPersonId": x.get("iopixPersonId"), "label": x.get("label") or "birthday",
                      "turns": x.get("turns"), "in": x.get("inDays"), "date": x.get("date")})
    return {"items": items[:n], "more": max(0, len(items) - n)}


def iocontacts_search(request: Request, q: str, n: int = 5) -> dict:
    """{items: [{id, name, hasPhoto, iopixPersonId, org}]}: the contacts whose name, email, phone, address… match q (the
    search box)."""
    got = fetch(request, "iocontacts", "/api/contacts", {"q": q[:80], "limit": n})
    return {"items": [{"id": x.get("id"), "name": x.get("fn"), "hasPhoto": bool(x.get("hasPhoto")),
                       "iopixPersonId": x.get("iopixPersonId"), "org": x.get("org")} for x in got.get("items", [])],
            "total": got.get("total")}


def iocontacts_photo(request: Request, contact_id: int) -> tuple[bytes, str]:
    return fetch(request, "iocontacts", f"/api/contacts/{int(contact_id)}/photo", raw=True)


def iocontacts_face(request: Request, person_id: int) -> tuple[bytes, str]:
    """A person's face from ioPix, as ioContacts hands it out (for contacts linked to an ioPix person, no photo of their own)."""
    return fetch(request, "iocontacts", f"/api/iopix/face/{int(person_id)}", raw=True)


# ------------------------------------------------------------------ ioHealth: today's steps and activity rings

def iohealth(request: Request, tz: str = "") -> dict:
    """{steps, rings: {move, moveGoal, exercise, exerciseGoal, stand, standGoal} | null, sleep: {date, asleep, inBed, start,
    end} | null, week: [{date, steps}]} for the viewer: today's steps and rings, last night's sleep (minutes), and the
    steps of the last seven days."""
    day = dt.datetime.now(_zone(tz)).date().isoformat()
    q = {"from": day, "to": day}
    if tz:
        q["tz"] = tz
    steps = rings = sleep = None
    week: list = []
    failed = []
    try:
        # a day per point, the last seven days: today's number, and the trend behind it
        since = (dt.datetime.now(_zone(tz)).date() - dt.timedelta(days=6)).isoformat()
        pts = fetch(request, "iohealth", "/api/series", {**q, "from": since, "type": "step_count", "bucket": "day"}).get("points") or []
        by_day = {dt.datetime.fromtimestamp(p["t"], _zone(tz)).date().isoformat(): p.get("v") for p in pts if p.get("t") is not None}
        week = [{"date": d, "steps": round(by_day[d]) if by_day.get(d) is not None else None}
                for d in (( dt.date.fromisoformat(since) + dt.timedelta(days=i)).isoformat() for i in range(7))]
        steps = week[-1]["steps"] if week and week[-1]["date"] == day else None
        if steps is None and by_day.get(day) is not None:
            steps = round(by_day[day])
    except Unavailable as e:
        failed.append(e)
    try:
        # last night: the night that ended this morning (ioHealth names a night by the day it ends on)
        nights = fetch(request, "iohealth", "/api/sleep", {**q, "from": (dt.date.fromisoformat(day) - dt.timedelta(days=1)).isoformat()})
        nights = nights if isinstance(nights, list) else nights.get("items", [])
        last = next((x for x in reversed(nights) if x.get("asleep")), None)
        if last:
            sleep = {"date": last.get("date"), "asleep": round(last["asleep"]), "inBed": round(last.get("inBed") or 0),
                     "start": last.get("start"), "end": last.get("end")}
    except Unavailable:
        pass  # sleep is a bonus: the tile shows without it
    try:
        a = fetch(request, "iohealth", "/api/activity", q)
        rows = a if isinstance(a, list) else a.get("items", [])
        if rows:
            rings = {k: rows[-1].get(k) for k in ("move", "moveGoal", "exercise", "exerciseGoal", "stand", "standGoal")}
    except Unavailable as e:
        failed.append(e)
    if len(failed) == 2:  # one of the two missing still shows the other
        raise failed[0]
    return {"steps": steps, "rings": rings, "sleep": sleep, "week": week}


def get(request: Request, key: str, tz: str = "", kind: str = "", n: int = 0, q: str = "") -> dict:
    if key not in WIDGETS:
        raise Unavailable(404, f"{key} has nothing to show here")
    if tz and not re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", tz):
        tz = ""
    if key == "iopix":
        return iopix(request, tz, min(max(int(n or 0), 1), 24) if n else 4, kind if kind in ("onthisday", "rediscover") else "")
    if key == "iocalendar" and kind == "week":
        return iocalendar_week(request, tz)
    if key == "iocontacts":
        return iocontacts_search(request, q.strip()) if q.strip() else iocontacts(request)
    if key == "iocalendar":
        return iocalendar(request, tz, min(max(int(n or 0), 1), 12) if n else 3)
    return iohealth(request, tz)
