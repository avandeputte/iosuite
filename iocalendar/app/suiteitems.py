"""ioCalendar's answers to the suite's standard endpoints (iosuite_shared.suiteitems): events found, one event, and
the start page's tile (the rest of today, else what is next) and its This week card (kind=week)."""
import datetime as dt
import urllib.parse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from iosuite_shared.suiteitems import Provider, item


def _zone(tz: str):
    try:
        return ZoneInfo(tz) if tz else dt.timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return dt.timezone.utc


def _colors(local) -> dict:
    return {c["id"]: c.get("color") for c in local.get("/api/calendars").get("items", [])}


def _event(x: dict, colors: dict, start=None, rid=None, over=False) -> dict:
    href = f"#/event/{urllib.parse.quote(str(x.get('id')))}" + (f"?rid={urllib.parse.quote(str(rid))}" if rid else "")
    return item("iocalendar", "event", x.get("id"), x.get("title"), x.get("location") or "", start or x.get("start"), x.get("allDay"),
                done=over, href=href, color=colors.get(x.get("calendarId")), icon="event", recurring=bool(x.get("recurring")) or None)


def _ahead_first(rows: list, tz: str) -> tuple[list, list]:
    """(the events still to come or going on, soonest first; the ones that are over, the latest first), each at its
    next occurrence. An all-day event is still to come until its day is over in the viewer's zone."""
    zone = _zone(tz)
    now = dt.datetime.now(zone)
    today = now.date().isoformat()

    def moment(s: str) -> dt.datetime:
        t = dt.datetime.fromisoformat(s)
        return t if t.tzinfo else t.replace(tzinfo=zone)  # a floating time: the viewer's

    def at(x):
        s = (x.get("next") or {}).get("start") or x.get("start")
        try:
            return (dt.datetime.combine(dt.date.fromisoformat(s[:10]), dt.time(), zone) if x.get("allDay") else moment(s)).timestamp()
        except (TypeError, ValueError):
            return None

    def ahead(x) -> bool:
        nx = x.get("next") or {}
        if not nx.get("start"):
            return False
        if x.get("allDay"):
            return str(nx.get("end") or nx["start"])[:10] > today or str(nx["start"])[:10] >= today
        try:
            return moment(nx.get("end") or nx["start"]) >= now
        except ValueError:
            return False
    timed = [x for x in rows if at(x) is not None]
    soon = sorted((x for x in timed if ahead(x)), key=at)
    past = sorted((x for x in timed if not ahead(x)), key=at, reverse=True)
    return soon, past


def search(local, q, n, tz, kinds):
    """The events whose title, place, notes or people match q: those still to come soonest first, each at its next
    occurrence, then the ones that are over (done: the search box leaves them out)."""
    if kinds and "event" not in kinds:
        return []
    cals, got = local.together(lambda: local.get("/api/calendars"), lambda: local.get("/api/events", {"q": q, "limit": 200}))
    if isinstance(got, Exception):
        raise got
    colors = {} if isinstance(cals, Exception) else {c["id"]: c.get("color") for c in cals.get("items", [])}
    soon, past = _ahead_first(got.get("items", []), tz)
    out = [_event(x, colors, (x.get("next") or {}).get("start"), (x.get("next") or {}).get("recurrenceId")) for x in soon[:n]]
    out += [_event(x, colors, (x.get("next") or {}).get("start") or x.get("start"), over=True) for x in past[:n]]
    return {"items": out, "more": len(soon) > n}


def get(local, kind, item_id):
    if kind != "event" or not item_id.isdigit():
        return None
    colors, x = local.together(lambda: _colors(local), lambda: local.get(f"/api/events/{item_id}"))
    if isinstance(x, Exception):
        raise x
    return _event({**x, "id": item_id}, {} if isinstance(colors, Exception) else colors)  # no colour without the calendars


# ------------------------------------------------------------------ the start page's tile and its This week card

def _covers(o: dict, day: dt.date) -> bool:
    """Whether an all-day occurrence (dates, end exclusive) falls on `day`. ioCalendar picks whole days by the dates in
    the calendar's own zone; the page's day is the viewer's, which may be another: this keeps only what is on it."""
    try:
        s = dt.date.fromisoformat(str(o.get("start"))[:10])
        e = dt.date.fromisoformat(str(o.get("end") or o.get("start"))[:10])
    except ValueError:
        return True
    return s <= day < max(e, s + dt.timedelta(days=1))


def _cancelled(o: dict) -> bool:
    return (o.get("status") or "").upper() == "CANCELLED"


class _Calendars(dict):
    """{calendar id: its colour}, as _colors gives it, with what an event's details name besides: each calendar's
    name, and the family (who an event is for)."""
    names: dict = {}
    family: dict = {}


def _about(local) -> _Calendars:
    """The calendars' colours and names and the family, asked together. The family not answering leaves the rest."""
    cals, fam = local.together(lambda: local.get("/api/calendars"), lambda: local.get("/api/members"))
    if isinstance(cals, Exception):
        raise cals
    out = _Calendars({c["id"]: c.get("color") for c in cals.get("items", [])})
    out.names = {c["id"]: c.get("name") for c in cals.get("items", [])}
    out.family = {} if isinstance(fam, Exception) else {m["id"]: m for m in fam.get("items", [])}
    return out


def _pick(o: dict, colors: dict) -> dict:
    """An occurrence as the tile shows it, and what its details add where there is any: who of the family it is for
    ({name, color}), the other people on it, the calendar it is on, its notes, whether it repeats."""
    out = {"title": o.get("title") or "(no title)", "start": o.get("start"), "end": o.get("end"), "allDay": bool(o.get("allDay")),
           "location": o.get("location"), "color": colors.get(o.get("calendarId"))}
    fam = getattr(colors, "family", {})
    who = [{"name": fam[i].get("displayName") or fam[i].get("name"), "color": fam[i].get("color")} for i in o.get("members") or [] if i in fam]
    more = {"who": who, "people": [str(p) for p in (o.get("people") or []) if p][:12], "calendar": getattr(colors, "names", {}).get(o.get("calendarId")),
            "notes": (o.get("notes") or "")[:600], "recurring": bool(o.get("recurring"))}
    out.update({k: v for k, v in more.items() if v})
    return out


def _occurrences(local, start: dt.datetime, end: dt.datetime) -> dict:
    return local.get("/api/occurrences", {"start": start.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds"), "notes": 1})


def today(local, tz: str, n: int) -> dict:
    """{today: [occurrence], more, next: occurrence | null}: today's events that have not ended yet (all-day ones
    first, as ioCalendar sorts them), up to n; when there are none left, the next one in the coming 60 days."""
    zone = _zone(tz)
    now = dt.datetime.now(zone)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=1)
    colors, occ = local.both(lambda: _about(local), lambda: _occurrences(local, start, end))

    def ends_after(o: dict) -> bool:
        if o.get("allDay"):
            return True
        try:
            e = dt.datetime.fromisoformat(o["end"])
        except (KeyError, TypeError, ValueError):
            return True
        return (e if e.tzinfo else e.replace(tzinfo=zone)) > now

    rows = [_pick(o, colors) for o in occ.get("items", []) if not _cancelled(o) and ends_after(o) and (not o.get("allDay") or _covers(o, now.date()))]
    out = {"today": rows[:n], "more": max(0, len(rows) - n), "next": None}
    if not rows:
        later = _occurrences(local, end, end + dt.timedelta(days=60))
        nxt = next((o for o in later.get("items", []) if not _cancelled(o) and (not o.get("allDay") or _covers(o, end.date())
                                                                                 or dt.date.fromisoformat(str(o["start"])[:10]) >= end.date())), None)
        out["next"] = _pick(nxt, colors) if nxt else None
    return out


def week(local, tz: str, days: int = 7, n: int = 12) -> dict:
    """{days: [{date, items: [occurrence]}], more}: the coming `days` days after today, each with its events (cancelled
    ones left out), up to n events in all; days without any are left out."""
    zone = _zone(tz)
    start = (dt.datetime.now(zone) + dt.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(days=days)
    colors, occ = local.both(lambda: _about(local), lambda: _occurrences(local, start, end))
    by_day: dict[str, list] = {}
    total = 0
    first, last = start.date(), (end - dt.timedelta(days=1)).date()
    for o in occ.get("items", []):
        if _cancelled(o):
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
            by_day.setdefault(day, []).append(_pick(o, colors))
        total += 1
    return {"days": [{"date": d, "items": by_day[d]} for d in sorted(by_day)], "more": max(0, total - n)}


def tile(local, tz, n, kind):
    return week(local, tz) if kind == "week" else today(local, tz, n or 3)


PROVIDER = Provider(search=search, get=get, tile=tile)
