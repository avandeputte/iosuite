"""Outside calendars: a calendar subscribed to by its web address (a school's, a sports club's, the bin collection),
kept here as a read-only calendar (kind 'subscribed') and fetched again on a schedule.

Anybody who may make a calendar may subscribe one: a member a private one, an editor a shared one the whole family
sees. Each refresh brings the calendar in line with the address: new and changed events saved, the ones the address no
longer has removed, so the web app, CalDAV, the subscription links, the REST API and MCP show them like any other
calendar. Reminders that come with the outside events are dropped (they would ring on every phone that syncs).

The address is one a person typed, so the server fetches it as iosuite_shared.outbound says: only hosts on the
internet (not this machine, not the home network, not link-local), a redirect checked like the first address before
anything is sent to it, the connection made to the address that was checked, no proxy from the environment, a size cap
and a time limit. The address itself (it may hold a private token, as Google's "secret address" does) is shown only to
those who manage the calendar, and never written to the log.
"""
import datetime as dt
import http.client
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request

from app import __version__, db, ical, model
from iosuite_shared import outbound, users as shared_users
from iosuite_shared.errors import Invalid

log = logging.getLogger("iocalendar.subscriptions")

KIND = "subscribed"
REFRESH_HOURS = (1, 3, 6, 12, 24, 168)  # the choices: hourly to weekly
DEFAULT_HOURS = 6
TIMEOUT = 20
MAX_FEED_BYTES = 16 * 1024 * 1024
MAX_EVENTS = 20000
ALLOWED = outbound.public  # which hosts the server may fetch from (the tests widen it to reach their own server)

_locks: dict[int, threading.Lock] = {}
_locks_lock = threading.Lock()


def _lock(cid: int) -> threading.Lock:
    with _locks_lock:
        return _locks.setdefault(cid, threading.Lock())


# ------------------------------------------------------------------ the address

def clean_url(url) -> str:
    """The address to fetch: http(s), webcal:// read as https://, no name and password in it."""
    u = str(url or "").strip()
    if not u:
        raise Invalid("The calendar's web address, please")
    if len(u) > 2048:
        raise Invalid("That address is too long")
    low = u.lower()
    if low.startswith("webcals://") or low.startswith("webcal://"):
        u = "https://" + u.split("://", 1)[1]
    parts = urllib.parse.urlsplit(u)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise Invalid("A web address starting with https://, http:// or webcal://, please")
    if parts.username or parts.password:
        raise Invalid("Addresses with a name and password in them are not supported")
    return urllib.parse.urlunsplit(parts._replace(fragment=""))


def host_of(url: str) -> str:
    return urllib.parse.urlsplit(url or "").hostname or "?"


def _hours(v) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise Invalid("refreshHours: one of " + ", ".join(map(str, REFRESH_HOURS)))
    if n not in REFRESH_HOURS:
        raise Invalid("refreshHours: one of " + ", ".join(map(str, REFRESH_HOURS)))
    return n


def fetch(url: str, etag: str | None = None, modified: str | None = None) -> dict | None:
    """The calendar at the address: {text, etag, modified}; None when it has not changed since (304). Invalid with a
    sentence a person understands when it cannot be had."""
    host = host_of(url)
    headers = {"User-Agent": f"ioCalendar/{__version__}", "Accept": "text/calendar, */*;q=0.5"}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        outbound.check(url, ALLOWED)  # refused before anything is sent (the connection checks again)
        with outbound.opener(ALLOWED).open(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
            raw = r.read(MAX_FEED_BYTES + 1)
            if len(raw) > MAX_FEED_BYTES:
                raise Invalid(f"The calendar at {host} is larger than {MAX_FEED_BYTES // (1024 * 1024)} MB")
            text = raw.decode(r.headers.get_content_charset() or "utf-8", "replace")
            return {"text": text, "etag": (r.headers.get("ETag") or "")[:255] or None,
                    "modified": (r.headers.get("Last-Modified") or "")[:64] or None}
    except urllib.error.HTTPError as e:
        if e.code == 304:
            return None
        raise Invalid(f"{host} answered {e.code} {e.reason or ''}".strip()) from None
    except outbound.NotAllowed:
        raise Invalid(f"{host} is on this server or the home network: only calendars on the internet can be subscribed to") from None
    except Invalid:
        raise
    except urllib.error.URLError as e:
        raise Invalid(f"Could not reach {host}: {getattr(e, 'reason', e)}") from None
    except (OSError, http.client.HTTPException, ValueError) as e:
        raise Invalid(f"Could not read the calendar at {host}: {type(e).__name__}") from None


def _parse(text: str):
    try:
        return ical.parse(text)
    except Invalid:
        raise Invalid("That address does not give a calendar (an .ics file)") from None


# ------------------------------------------------------------------ bringing a calendar in line

def apply(cid: int, cal, tzname: str | None = None) -> dict:
    """The calendar's events made the same as the outside calendar's: {events, changed, skipped}."""
    have = {r["uid"]: r for r in model.rows(cid, listing=True)}
    seen, changed, skipped = set(), 0, 0
    objs = ical.split_by_uid(cal)
    if len(objs) > MAX_EVENTS:
        raise Invalid(f"That calendar has {len(objs)} events; at most {MAX_EVENTS} are kept")
    for obj in objs:
        for ev in ical.events_of(obj):
            ev.subcomponents = [s for s in ev.subcomponents if s.name != "VALARM"]  # no outside reminders
        try:
            obj = ical.finish(obj)
            uid = ical.index(obj, tzname)["uid"][:255]
        except (ValueError, KeyError, TypeError):  # an event this app cannot read: left out, the others still come
            skipped += 1
            continue
        if uid in seen:
            continue
        seen.add(uid)
        old = have.get(uid)
        if old and old["etag"] == ical.etag_of(ical.text(obj)):
            continue
        try:
            model.save(cid, obj, old["id"] if old else None, tzname=tzname)
        except (ValueError, KeyError, TypeError):
            skipped += 1
            seen.discard(uid)
            continue
        changed += 1
    for uid, r in have.items():
        if uid not in seen:
            model.delete(r["id"])
            changed += 1
    return {"events": len(seen), "changed": changed, "skipped": skipped}


def row(cid: int) -> dict | None:
    return db.one("SELECT * FROM cal_subscriptions WHERE calendar_id = %s", (cid,))


def refresh(cid: int, force: bool = False) -> dict:
    """Fetch the address again and bring the calendar in line. force: ask for the whole calendar (no If-None-Match).
    A failure keeps the events as they were and is noted on the subscription."""
    with _lock(cid):
        s, c = row(cid), model.calendar(cid)
        if not s or not c:
            raise Invalid("No such subscription")
        try:
            got = fetch(s["url"], None if force else s["etag"], None if force else s["last_modified"])
            if got is None:  # not changed since the last time
                db.ex("UPDATE cal_subscriptions SET checked_at = UTC_TIMESTAMP(), synced_at = UTC_TIMESTAMP(), error = NULL WHERE calendar_id = %s", (cid,))
                return {"ok": True, "changed": 0, "events": s["events"], "notModified": True}
            out = apply(cid, _parse(got["text"]), c.get("timezone"))
        except Invalid as e:
            db.ex("UPDATE cal_subscriptions SET checked_at = UTC_TIMESTAMP(), error = %s WHERE calendar_id = %s", (str(e)[:512], cid))
            log.warning("outside calendar %s (%s): %s", cid, host_of(s["url"]), e)
            return {"ok": False, "error": str(e)}
        db.ex("UPDATE cal_subscriptions SET checked_at = UTC_TIMESTAMP(), synced_at = UTC_TIMESTAMP(), error = NULL, etag = %s, "
              "last_modified = %s, events = %s WHERE calendar_id = %s", (got["etag"], got["modified"], out["events"], cid))
        return {"ok": True, **out}


def tick() -> int:
    """The subscriptions whose time has come, refreshed (every few minutes, app/main.py); how many were."""
    due = db.q("SELECT calendar_id FROM cal_subscriptions WHERE checked_at IS NULL "
               "OR checked_at < UTC_TIMESTAMP() - INTERVAL refresh_hours HOUR ORDER BY checked_at")
    for r in due:
        try:
            refresh(r["calendar_id"])
        except Exception as e:  # noqa: BLE001 - one broken subscription does not hold up the others
            log.warning("outside calendar %s: %s", r["calendar_id"], e)
    return len(due)


# ------------------------------------------------------------------ who manages, adding and changing

def can_manage(u: dict | None, c: dict | None) -> bool:
    """Whoever could change it were it an ordinary calendar: its owner (a member), or an editor for a shared one."""
    if not (c and c.get("kind") == KIND and model.can_read(u, c)):
        return False
    return shared_users.can_write(u) if c["owner_id"] is None else shared_users.is_member(u)


def add(u: dict, url, name=None, color=None, shared: bool = False, hours=None) -> int:
    """A new subscribed calendar, filled from the address straight away (nothing is made when it cannot be read)."""
    url = clean_url(url)
    hours = DEFAULT_HOURS if hours in (None, "") else _hours(hours)
    got = fetch(url)
    cal = _parse(got["text"])
    tz = str(cal.get("X-WR-TIMEZONE") or "").strip() or None
    name = (str(name or "").strip() or str(cal.get("X-WR-CALNAME") or "").strip() or host_of(url))[:128]
    desc = (str(cal.get("X-WR-CALDESC") or "").strip() or f"Subscribed from {host_of(url)}")[:512]
    cid = model.create_calendar(None if shared else u["id"], name, desc, color, kind=KIND, timezone=tz if ical.valid_tz(tz) else None)
    try:
        db.ex("INSERT INTO cal_subscriptions (calendar_id, url, refresh_hours, created_by) VALUES (%s, %s, %s, %s)", (cid, url, hours, u["id"]))
        out = apply(cid, cal, model.calendar(cid).get("timezone"))
    except Exception:
        model.delete_calendar(cid)
        raise
    db.ex("UPDATE cal_subscriptions SET checked_at = UTC_TIMESTAMP(), synced_at = UTC_TIMESTAMP(), etag = %s, last_modified = %s, "
          "events = %s WHERE calendar_id = %s", (got["etag"], got["modified"], out["events"], cid))
    return cid


def change(cid: int, url=None, hours=None) -> dict | None:
    """A new address (read before it is kept: a wrong one leaves the old) and/or how often it is fetched."""
    if hours is not None:
        db.ex("UPDATE cal_subscriptions SET refresh_hours = %s WHERE calendar_id = %s", (_hours(hours), cid))
    if url is None:
        return None
    url = clean_url(url)
    s = row(cid)
    if s and url == s["url"]:
        return None
    _parse(fetch(url)["text"])  # it must give a calendar before it replaces the address that does
    db.ex("UPDATE cal_subscriptions SET url = %s, etag = NULL, last_modified = NULL WHERE calendar_id = %s", (url, cid))
    return refresh(cid, force=True)


def _epoch(d: dt.datetime | None) -> int | None:
    return int(d.replace(tzinfo=dt.timezone.utc).timestamp()) if d else None


def public(c: dict, u: dict) -> dict | None:
    """What the web app shows of a calendar's subscription; the address only to those who manage it (it may hold a token)."""
    s = row(c["id"]) if c.get("kind") == KIND else None
    if not s:
        return None
    mine = can_manage(u, c)
    return {"url": s["url"] if mine else None, "host": host_of(s["url"]), "refreshHours": s["refresh_hours"],
            "checked": _epoch(s["checked_at"]), "synced": _epoch(s["synced_at"]), "error": s["error"], "events": s["events"],
            "manage": mine}
