"""Calendars and events in MariaDB: who may see and change which calendar, saving calendar objects (with the columns
the app searches and draws from), occurrences in a time range, search, import, and the sync tokens CalDAV clients use.

Calendars: the shared ones (owner_id NULL, Family first) that everyone sees, and each account's own private ones
(Personal, made the first time a member uses ioCalendar). Viewers only read the shared calendars; members also keep
their own private ones; editors change the shared ones too; admins also manage settings and users. A calendar of kind 'birthdays' is
filled from ioContact, one of kind 'holidays' from the holiday rules (app/holiday.py); nobody changes either here.
"""
import datetime as dt
import re
import threading
from collections import OrderedDict

from app import config, db, ical, members
from iosuite_shared import related, users as shared_users
from iosuite_shared.errors import Invalid

PALETTE = ["#8e44d6", "#0b8a9e", "#1a73e8", "#e0426a", "#1e8e3e", "#e8710a", "#4b53c7", "#e8a100", "#5f6b7a", "#1294b8"]


READ_ONLY_KINDS = ("birthdays", "holidays")  # filled by the server, never changed by hand


def read_only_reason(c: dict) -> str | None:
    return {"birthdays": "it comes from ioContact", "holidays": "it is filled from the holiday settings"}.get((c or {}).get("kind"))


class NotFound(Exception):
    pass


# ------------------------------------------------------------------ calendars

def calendar(cid: int) -> dict | None:
    return db.one("SELECT * FROM cal_calendars WHERE id = %s", (cid,))


def is_shared(c: dict) -> bool:
    return c["owner_id"] is None


def can_read(u: dict | None, c: dict | None) -> bool:
    return bool(u and c) and (c["owner_id"] is None or c["owner_id"] == u["id"])


def can_write(u: dict | None, c: dict | None) -> bool:
    if not can_read(u, c) or c.get("kind") in READ_ONLY_KINDS:
        return False
    if c["owner_id"] is None:
        return shared_users.can_write(u)  # a shared calendar: editors and admins
    return shared_users.is_member(u)  # one's own: members and more (a viewer only looks)


def ensure_personal(u: dict) -> None:
    """Every member gets their private Personal calendar the first time they use ioCalendar (accounts are made in any
    app of the suite, so not necessarily here). A viewer keeps nothing of their own."""
    if not u or not u.get("id") or not members.in_family(u["id"]):  # not in the suite's family (Settings › Security › Family): no calendar of its own
        return
    if not shared_users.is_member(u):
        return
    if not db.one("SELECT id FROM cal_calendars WHERE owner_id = %s LIMIT 1", (u["id"],)):
        who = u.get("displayName") or u.get("display_name") or u.get("name")
        create_calendar(u["id"], "Personal", f"{who}'s private calendar", "#0b8a9e")


def calendars_for(u: dict | None) -> list[dict]:
    """The calendars this account sees: the shared ones first (Family, then by name), then its own, with event counts."""
    if not u:
        return []
    ensure_personal(u)
    rows = db.q("SELECT c.*, (SELECT count(*) FROM cal_events e WHERE e.calendar_id = c.id AND e.deleted = 0) AS n FROM cal_calendars c "
                "WHERE c.owner_id IS NULL OR c.owner_id = %s "
                "ORDER BY c.owner_id IS NOT NULL, c.kind IN ('birthdays', 'holidays'), c.kind = 'holidays', c.position, c.slug <> 'family', c.slug <> 'personal', lower(c.name)",
                (u["id"],))
    return rows


def calendar_public(c: dict, u: dict) -> dict:
    return {"id": c["id"], "name": c["name"], "slug": c["slug"], "description": c.get("description"), "color": c.get("color") or PALETTE[0],
            "timezone": c.get("timezone"), "shared": c["owner_id"] is None, "kind": c.get("kind") or "events",
            "writable": can_write(u, c), "count": c.get("n"), "mine": c["owner_id"] == (u or {}).get("id")}


def by_slug(u: dict, slug: str) -> dict | None:
    for c in calendars_for(u):
        if c["slug"] == slug:
            return c
    return None


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")[:48]
    return s or "calendar"


def create_calendar(owner_id: int | None, name: str, description: str | None = None, color: str | None = None,
                    kind: str = "events", slug: str | None = None, timezone: str | None = None) -> int:
    name = (name or "").strip()[:128] or "Calendar"
    base = (slug or _slug(name))[:56]
    # CalDAV lists a person's own and the shared ones under one home: a private calendar's address must not hide a
    # shared one's, nor a new shared one's anybody's private one
    taken = {r["slug"] for r in db.q("SELECT slug FROM cal_calendars" + ("" if owner_id is None else " WHERE owner_id IS NULL OR owner_id = %s"),
                                     () if owner_id is None else (owner_id,))}
    s, i = base, 2
    while s in taken:
        s, i = f"{base}-{i}", i + 1
    if not color:
        n = db.one("SELECT count(*) AS n FROM cal_calendars")["n"]
        color = PALETTE[n % len(PALETTE)]
    return db.ex("INSERT INTO cal_calendars (owner_id, slug, name, description, color, kind, timezone) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                 (owner_id, s, name, (description or "").strip()[:512] or None, _color(color), kind,
                  timezone if ical.valid_tz(timezone) else None))


def _color(c: str | None) -> str | None:
    c = (c or "").strip()
    m = re.fullmatch(r"#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?", c)
    return f"#{m.group(1).lower()}" if m else None


def update_calendar(cid: int, **f) -> None:
    sets, args = [], []
    if f.get("name") is not None and str(f["name"]).strip():
        sets.append("name = %s"); args.append(str(f["name"]).strip()[:128])
    if "description" in f:
        sets.append("description = %s"); args.append((f["description"] or "").strip()[:512] or None)
    if f.get("color") is not None and _color(f["color"]):
        sets.append("color = %s"); args.append(_color(f["color"]))
    if "timezone" in f:
        sets.append("timezone = %s"); args.append(f["timezone"] if ical.valid_tz(f["timezone"]) else None)
    if f.get("sort") is not None:
        sets.append("position = %s"); args.append(int(f["sort"]))
    if sets:
        db.ex(f"UPDATE cal_calendars SET {', '.join(sets)}, sync_token = sync_token + 1 WHERE id = %s", (*args, cid))


def delete_calendar(cid: int) -> None:
    with db.tx():
        db.ex("DELETE FROM cal_calendars WHERE id = %s", (cid,))
        db.set_setting(f"{PURGED}{cid}", None)
    _cache_clear()


def bump(cid: int) -> int:
    """The calendar's next sync token (every change gets one; CalDAV's sync-collection and getctag follow it)."""
    with db.tx() as con, con.cursor() as cur:
        cur.execute("UPDATE cal_calendars SET sync_token = sync_token + 1 WHERE id = %s", (cid,))
        cur.execute("SELECT sync_token FROM cal_calendars WHERE id = %s", (cid,))
        return cur.fetchone()["sync_token"]


# ------------------------------------------------------------------ calendar objects

_cache: "OrderedDict[str, object]" = OrderedDict()
_cache_lock = threading.Lock()


def _cache_clear():
    with _cache_lock:
        _cache.clear()


def parsed(row: dict):
    """The row's iCalendar object, parsed (kept by etag: the same object is drawn again and again)."""
    key = f"{row['id']}:{row['etag']}"
    with _cache_lock:
        c = _cache.get(key)
        if c is not None:
            _cache.move_to_end(key)
            return c
    c = ical.parse(row["ics"])
    with _cache_lock:
        _cache[key] = c
        while len(_cache) > 3000:
            _cache.popitem(last=False)
    return c


def get_row(eid: int) -> dict | None:
    return db.one("SELECT * FROM cal_events WHERE id = %s", (eid,))


def by_href(cid: int, href: str) -> dict | None:
    return db.one("SELECT * FROM cal_events WHERE calendar_id = %s AND href = %s", (cid, href))


def by_uid(cid: int, uid: str) -> dict | None:
    return db.one("SELECT * FROM cal_events WHERE calendar_id = %s AND uid = %s AND deleted = 0", (cid, uid))


def href_for(uid: str) -> str:
    s = re.sub(r"[^A-Za-z0-9@._-]", "-", uid)[:200]
    return f"{s}.ics"


def save(cid: int, cal, event_id: int | None = None, href: str | None = None, user_id: int | None = None, tzname: str | None = None) -> dict:
    """Store a calendar object in a calendar: a new event, or the one with event_id (or the tombstone at href)."""
    ix = ical.index(cal, tzname or (calendar(cid) or {}).get("timezone"))
    ics = ical.text(cal)
    etag = ical.etag_of(ics)
    with db.tx():  # the sync token and the row change together: a failure leaves neither
        tok = bump(cid)
        cols = dict(uid=ix["uid"][:255], summary=ix["summary"], location=(ix["location"] or None) and ix["location"][:1024],
                    description=ix["description"], all_day=ix["all_day"], dtstart=ix["dtstart"], dtend=ix["dtend"],
                    tzid=(ix["tzid"] or None) and ix["tzid"][:64], rrule=(ix["rrule"] or None) and ix["rrule"][:1024], status=ix["status"],
                    range_start=ix["range_start"], range_end=ix["range_end"], ics=ics, etag=etag, changed_token=tok, deleted=0)
        if event_id is None:
            if not href:
                href = href_for(ix["uid"])
                old = by_href(cid, href)
                if old and not old["deleted"]:  # an app reusing a name: a new one
                    href, old = href_for(ical.new_uid()), None
            else:
                old = by_href(cid, href)
            event_id = old["id"] if old else None
        if event_id:
            db.ex(f"UPDATE cal_events SET {', '.join(f'{k} = %s' for k in cols)}, calendar_id = %s WHERE id = %s", (*cols.values(), cid, event_id))
        else:
            event_id = db.ex(f"INSERT INTO cal_events ({', '.join(cols)}, calendar_id, href, created_by) VALUES "
                             f"({', '.join(['%s'] * len(cols))}, %s, %s, %s)", (*cols.values(), cid, href, user_id))
        db.ex("DELETE FROM cal_event_people WHERE event_id = %s", (event_id,))
        db.many("INSERT INTO cal_event_people (event_id, position, name, email, contact_id, role) VALUES (%s, %s, %s, %s, %s, %s)",
                [(event_id, i, (p["name"] or None) and p["name"][:255], (p["email"] or None) and p["email"][:255], p.get("contactId"), p["role"])
                 for i, p in enumerate(ix["people"][:200])])
    return get_row(event_id)


def delete(eid: int) -> None:
    """A deletion marker: CalDAV clients learn of the deletion from the next sync. Kept for KEEP_DELETED_DAYS (purge_deleted)."""
    with db.tx():
        r = get_row(eid)
        if not r or r["deleted"]:
            return
        tok = bump(r["calendar_id"])
        db.ex("UPDATE cal_events SET deleted = 1, ics = '', changed_token = %s WHERE id = %s", (tok, eid))
        db.ex("DELETE FROM cal_event_people WHERE event_id = %s", (eid,))


PURGED = "purged_token:"  # cal_settings: per calendar, the newest change among the deletion markers that were purged


def purge_deleted(days: int | None = None) -> int:
    """Remove the deletion markers older than `days` (KEEP_DELETED_DAYS); how many went. Each calendar remembers how
    far its purged markers reached, so a client that last synced before that is told to start over (purged_before)
    instead of being left with events that were deleted."""
    days = config.KEEP_DELETED_DAYS if days is None else days
    with db.tx():
        old = db.q("SELECT calendar_id AS cal, max(changed_token) AS tok FROM cal_events WHERE deleted = 1 "
                   "AND updated_at < NOW() - INTERVAL %s DAY GROUP BY calendar_id", (days,))
        for r in old:
            db.set_setting(f"{PURGED}{r['cal']}", str(max(r["tok"], purged_before(r["cal"]))))
        if not old:
            return 0
        gone = [r["id"] for r in db.q("SELECT id FROM cal_events WHERE deleted = 1 AND updated_at < NOW() - INTERVAL %s DAY", (days,))]
        n = db.ex("DELETE FROM cal_events WHERE deleted = 1 AND updated_at < NOW() - INTERVAL %s DAY", (days,))
    related.forget_many("event", gone)  # their links to other items of the suite go too
    return n


def purged_before(cid: int) -> int:
    """The sync token up to which this calendar's deletion markers are gone (0: none were purged)."""
    return int(db.get_setting(f"{PURGED}{cid}") or 0)


def move(eid: int, to_cid: int) -> dict:
    """To another calendar: a deletion in the old one and a new event in the new one (as CalDAV sees it), in one
    transaction: when the new event cannot be saved, the old one stays."""
    with db.tx():
        r = get_row(eid)
        if r["calendar_id"] == to_cid:
            return r
        other = by_uid(to_cid, r["uid"])
        if other:
            raise Invalid("That calendar already has this event")
        cal = parsed(r)
        delete(eid)
        return save(to_cid, cal, None, None, r.get("created_by"))


LISTED = ("id, calendar_id, uid, href, etag, summary, all_day, dtstart, dtend, rrule, status, range_start, range_end, changed_token, "
          "deleted, created_by, created_at, updated_at, LENGTH(ics) AS ics_bytes")


def rows(cid: int, since: int | None = None, listing: bool = False) -> list[dict]:
    """A calendar's events (since: what changed after that sync token, deletions included). listing: without the
    objects themselves (ics_bytes says how long each is), for the replies that name events and their etags only."""
    cols = LISTED if listing else "*"
    if since is None:
        return db.q(f"SELECT {cols} FROM cal_events WHERE calendar_id = %s AND deleted = 0 ORDER BY id", (cid,))
    return db.q(f"SELECT {cols} FROM cal_events WHERE calendar_id = %s AND changed_token > %s ORDER BY changed_token", (cid, since))


def objects(rows_: list[dict]) -> list:
    """The parsed objects of these rows (from the cache where they are there), one that cannot be read left out."""
    out = []
    for r in rows_:
        try:
            out.append(parsed(r))
        except ValueError:
            continue
    return out


PAD = dt.timedelta(hours=14)  # all-day events are kept at UTC midnight; a day elsewhere is up to 14 hours off


def rows_in_range(cids: list[int], start: dt.datetime | None, end: dt.datetime | None) -> list[dict]:
    if not cids:
        return []
    where, args = [f"calendar_id IN ({db.marks(len(cids))})", "deleted = 0"], list(cids)
    if end is not None:
        where.append("range_start < %s")
        args.append((end + PAD).astimezone(dt.timezone.utc).replace(tzinfo=None))
    if start is not None:
        where.append("(range_end IS NULL OR range_end > %s)")
        args.append((start - PAD).astimezone(dt.timezone.utc).replace(tzinfo=None))
    return db.q(f"SELECT * FROM cal_events WHERE {' AND '.join(where)} ORDER BY range_start", args)


def occurrences(cals: list[dict], start: dt.datetime, end: dt.datetime, q: str = "", member_ids: set[int] | None = None) -> list[dict]:
    """Every occurrence in [start, end) of the events in these calendars, soonest first (member_ids: only those tagged
    with one of these family members)."""
    by_id = {c["id"]: c for c in cals}
    fam = members.family()
    out = []
    rows_ = rows_in_range(list(by_id), start, end)
    if q:
        keep = {r["id"] for r in search_rows(list(by_id), q, 100000)}
        rows_ = [r for r in rows_ if r["id"] in keep]
    for r in rows_:
        try:
            cal = parsed(r)
            occ = ical.occurrences(cal, start - (PAD if r["all_day"] else dt.timedelta(0)), end + (PAD if r["all_day"] else dt.timedelta(0)),
                                   by_id[r["calendar_id"]].get("timezone"))
        except Exception:  # noqa: BLE001 - one broken object does not hide the rest
            continue
        for o in occ:
            mids = members.ids_of(o["categories"], fam)
            if member_ids is not None and not member_ids.intersection(mids):
                continue
            out.append({"id": r["id"], "uid": r["uid"], "calendarId": r["calendar_id"], "title": o["title"], "location": o["location"],
                        "start": ical.iso(o["start"]), "end": ical.iso(o["end"]), "allDay": o["allDay"],
                        "recurrenceId": o["recurrenceId"], "recurring": bool(r["rrule"]) or bool(o["recurrenceId"]),
                        "status": o["status"], "busy": not o["transparent"], "people": o["people"],
                        "categories": o["categories"], "members": mids, "_sort": ical.to_utc(o["start"], by_id[r["calendar_id"]].get("timezone"))})
    out.sort(key=lambda x: (x["_sort"], not x["allDay"], x["title"].lower()))
    for x in out:
        x.pop("_sort")
    return out


def _like(w: str) -> str:
    """A word as a LIKE pattern that matches it anywhere, with its own % and _ taken literally."""
    return "%" + re.sub(r"([\\%_])", r"\\\1", w) + "%"


def search_rows(cids: list[int], q: str, limit: int = 100, member_ids: set[int] | None = None) -> list[dict]:
    """Events whose title, place, notes or people match every word of q, newest first. member_ids: only those tagged
    with one of these family members. The tags are categories inside the object, so the database narrows the search
    to the events that have categories at all and they are read a page at a time until `limit` are found."""
    if not cids:
        return []
    where, args = [f"e.calendar_id IN ({db.marks(len(cids))})", "e.deleted = 0"], list(cids)
    for w in (q or "").split()[:8]:
        like = _like(w)
        where.append("(e.summary LIKE %s OR e.location LIKE %s OR e.description LIKE %s OR EXISTS (SELECT 1 FROM cal_event_people p "
                     "WHERE p.event_id = e.id AND (p.name LIKE %s OR p.email LIKE %s)))")
        args += [like] * 5
    if member_ids is not None:
        where.append("e.ics LIKE '%%CATEGORIES%%'")
    sql = f"SELECT e.* FROM cal_events e WHERE {' AND '.join(where)} ORDER BY e.range_start DESC, e.id DESC LIMIT %s OFFSET %s"
    if member_ids is None:
        return db.q(sql, (*args, int(limit), 0))
    out, offset = [], 0
    while len(out) < limit:
        page = db.q(sql, (*args, SEARCH_PAGE, offset))
        out += [r for r in page if tagged(r, member_ids)]
        if len(page) < SEARCH_PAGE:
            break
        offset += SEARCH_PAGE
    return out[:limit]


SEARCH_PAGE = 500


def event_out(r: dict, cal_row: dict | None = None, recurrence_id: str | None = None) -> dict:
    """An event as the REST API and the web app see it."""
    c = parsed(r)
    j = ical.event_json(c, recurrence_id)
    j.update(id=r["id"], calendarId=r["calendar_id"], href=r["href"], etag=r["etag"], members=members.public(members.of(j["categories"])),
             updated=r["updated_at"].isoformat() if r.get("updated_at") else None,
             created=r["created_at"].isoformat() if r.get("created_at") else None)
    return j


def next_occurrence(r: dict, after: dt.datetime | None = None) -> dict | None:
    after = after or dt.datetime.now(dt.timezone.utc)
    try:
        cal = parsed(r)
        if not r["rrule"]:
            o = ical.occurrences(cal, dt.datetime(1900, 1, 1, tzinfo=dt.timezone.utc), ical.FAR)
            return {"start": ical.iso(o[0]["start"]), "end": ical.iso(o[0]["end"])} if o else None
        for span in (31, 400, 4000):
            o = ical.occurrences(cal, after, after + dt.timedelta(days=span))
            if o:
                return {"start": ical.iso(o[0]["start"]), "end": ical.iso(o[0]["end"]), "recurrenceId": o[0]["recurrenceId"]}
    except Exception:  # noqa: BLE001
        return None
    return None


# ------------------------------------------------------------------ import

def import_text(cid: int, text: str, user_id: int | None = None, replace: bool = True) -> dict:
    """An .ics file (one calendar or many events) into a calendar: every UID becomes an event; a UID the calendar has
    already is updated (replace) or skipped. {created, updated, skipped, errors}."""
    cal = ical.parse(text)
    out = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
    tzname = (calendar(cid) or {}).get("timezone")
    for obj in ical.split_by_uid(cal):
        try:
            ix = ical.index(obj, tzname)
        except ValueError as e:
            out["errors"].append(str(e))
            continue
        old = by_uid(cid, ix["uid"])
        if old and not replace:
            out["skipped"] += 1
            continue
        save(cid, ical.finish(obj), old["id"] if old else None, None, user_id, tzname)
        out["updated" if old else "created"] += 1
    return out


def tagged(r: dict, member_ids: set[int] | None) -> bool:
    """Whether an event (its series or any changed occurrence) is tagged with one of these members (None: any event)."""
    if member_ids is None:
        return True
    try:
        fam = members.family()
        return any(member_ids.intersection(members.ids_of(ical._categories(ev), fam)) for ev in ical.events_of(parsed(r)))
    except Exception:  # noqa: BLE001
        return False


def export_text(cals: list[dict], name: str, member_ids: set[int] | None = None) -> str:
    objs = []
    for c in cals:
        objs += objects([r for r in rows(c["id"]) if tagged(r, member_ids)])
    tz = cals[0].get("timezone") if len(cals) == 1 else None
    return ical.feed(objs, name, color=cals[0].get("color") if len(cals) == 1 else None, tzname=tz or ical.default_tz())


def people_seen(cids: list[int], q: str = "", limit: int = 20) -> list[dict]:
    """People who were on events before (for the picker when ioContact is not connected)."""
    if not cids:
        return []
    like = _like(q)
    return db.q(f"SELECT p.name, p.email, max(p.contact_id) AS contactId, count(*) AS n FROM cal_event_people p JOIN cal_events e ON e.id = p.event_id "
                f"WHERE e.deleted = 0 AND e.calendar_id IN ({db.marks(len(cids))}) AND (p.name LIKE %s OR p.email LIKE %s) "
                f"GROUP BY p.name, p.email ORDER BY n DESC LIMIT %s", (*cids, like, like, int(limit)))
