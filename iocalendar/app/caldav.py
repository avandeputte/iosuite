"""CalDAV (RFC 4791) on WebDAV (RFC 4918), with sync-collection (RFC 6578), getctag, current-user-principal discovery
(RFC 5397, RFC 6764 /.well-known/caldav), MKCALENDAR and extended MKCOL (RFC 5689) and free-busy-query, so Apple
Calendar (Mac, iPhone, iPad), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Calendar, KDE, Outlook (with CalDAV
Synchronizer) and others find the calendars from just the server address, a user name and an app password.

    /dav/                                         root: points to the principal
    /dav/principals/<user>/                       the principal: points to the calendar home
    /dav/calendars/<user>/                        home: one collection per calendar the user sees
    /dav/calendars/<user>/<slug>/                 a calendar (Family, Personal, Birthdays...)
    /dav/calendars/<user>/<slug>/<name>.ics       an event (with its changed occurrences)

The server itself is the suite's (iosuite_shared.dav.CalDAV); what is here is what a calendar and an event are: time
zones, expanded occurrences, free-busy, and what is kept of a PUT.

Scheduling (RFC 6638: invitations sent by the server) is not offered: the people on an event are noted, not invited.
"""
import datetime as dt
import re

from fastapi.responses import Response
from icalendar import vDDDTypes
from iosuite_shared import dav as webdav
from iosuite_shared.dav import CALDAV as C, q

from app import access, config, ical, model

TZID = re.compile(r"^TZID:(.+)$", re.M)


def _tzid(text: str | None) -> str | None:
    """The zone a calendar-timezone (a VCALENDAR with one VTIMEZONE) names."""
    m = TZID.search(text or "")
    return m.group(1).strip() if m else None


def _vtimezone(name: str | None) -> str | None:
    if not name:
        return None
    cal = ical.new_calendar()
    ev = ical.Event()
    ev.add("DTSTART", dt.datetime(2026, 1, 1, tzinfo=ical.zone(name)))
    cal.add_component(ev)
    try:
        cal.add_missing_timezones()
    except Exception:  # noqa: BLE001
        return None
    cal.subcomponents[:] = [c for c in cal.subcomponents if c.name == "VTIMEZONE"]
    return ical.text(cal)


class Calendars(webdav.CalDAV):
    label = "ioCalendar"
    banner = "ioCalendar CalDAV server. Point your calendar app at this address."
    sync_prefix = "urn:x-iocalendar:sync:"
    max_bytes = config.MAX_EVENT_BYTES
    reports = webdav.CalDAV.reports + ((C, "free-busy-query"),)
    also_privileges = ((C, "read-free-busy"),)
    home_name, plural, singular = "Calendars", "calendars", "calendar"
    component = "VEVENT"
    placeholders = ("DEFAULT_TASK_CALENDAR_NAME",)  # iOS's task list for an account with none: events only here

    def before(self, ctx):
        model.ensure_personal(ctx.user)

    def collections(self, user):
        return model.calendars_for(user)

    def collection(self, user, slug):
        return model.by_slug(user, slug)

    def reload(self, c):
        return model.calendar(c["id"])

    def can_write(self, user, c):
        return model.can_write(user, c)

    def is_shared(self, c):
        return model.is_shared(c)

    def rows(self, c, since=None, names=()):
        return model.rows(c["id"], since, listing=bool(names) and self.rows_listing(names))

    def by_href(self, c, name):
        return model.by_href(c["id"], name)

    def purged_before(self, c):
        return model.purged_before(c["id"])

    def export(self, c):
        return model.export_text([c], c["name"])

    def timezone(self, c):
        return _vtimezone(c.get("timezone") or ical.default_tz())

    def color(self, c):
        return (c.get("color") or model.PALETTE[0]).upper() + "FF"

    def collection_prop(self, ctx, c, name, ok):
        if name == q(C, "schedule-calendar-transp"):
            webdav.sub(webdav.sub(ok, C, "schedule-calendar-transp"), C, "transparent" if c.get("kind") in model.READ_ONLY_KINDS else "opaque")
            return True
        return super().collection_prop(ctx, c, name, ok)

    def patch(self, tag, v):
        if tag == q(C, "calendar-timezone"):
            tz = _tzid(v)
            return ("timezone", tz) if tz and ical.valid_tz(tz) else None
        return super().patch(tag, v)

    def update(self, c, changes):
        model.update_calendar(c["id"], **changes)

    def object_data(self, row, data_el, loaded=None):
        """calendar-data, expanded into separate occurrences when the client asks (<C:expand start= end=/>)."""
        exp = data_el.find(q(C, "expand")) if data_el is not None else None
        if exp is None:
            return row["ics"]
        try:
            s, e = webdav.utc(exp.get("start")), webdav.utc(exp.get("end"))
            out = ical.new_calendar()
            for occ in ical.expanded(model.parsed(row), s, e):
                for k in ("RRULE", "RDATE", "EXDATE"):
                    if k in occ:
                        del occ[k]
                for k in ("DTSTART", "DTEND", "RECURRENCE-ID"):  # in UTC, as RFC 4791 9.6.5 asks
                    v = occ.get(k)
                    if v is not None and isinstance(v.dt, dt.datetime):
                        occ[k] = vDDDTypes(ical.to_utc(v.dt))
                out.add_component(occ)
            return ical.text(out)
        except Exception:  # noqa: BLE001 - not expandable: the object as stored
            return row["ics"]

    def save(self, ctx, c, row, name, body):
        try:
            cal = ical.parse(body)
        except ValueError:
            return webdav.precondition(C, "valid-calendar-data", 400)
        if {s.name for s in cal.subcomponents if s.name != "VTIMEZONE"} - {"VEVENT"}:
            return webdav.precondition(C, "supported-calendar-component")
        try:
            ix = ical.index(cal, c.get("timezone"))
        except ValueError:
            return webdav.precondition(C, "valid-calendar-object-resource", 400)
        refused = self.conflict(ctx, c, row, model.by_uid(c["id"], ix["uid"]))
        if refused:
            return refused
        new = model.save(c["id"], cal, row["id"] if row else None, name, ctx.user["id"], c.get("timezone"))
        return Response(status_code=204 if row else 201, headers={"ETag": f'"{new["etag"]}"'})

    def delete(self, ctx, c, row):
        model.delete(row["id"])

    def drop(self, c):
        model.delete_calendar(c["id"])

    def create(self, ctx, slug, name, description, color, tz_text):
        model.create_calendar(ctx.user["id"], name, description, color, slug=slug, timezone=_tzid(tz_text))

    def candidates(self, c, start, end):
        return model.rows_in_range([c["id"]], start, end)  # chosen by where each event starts

    def overlaps(self, c, row, start, end):
        if start is None:
            return True  # chosen by where the event starts (model.rows_in_range): when in doubt, the client gets it
        try:
            return ical.happens(model.parsed(row), start, end, c.get("timezone"))
        except Exception:  # noqa: BLE001 - when in doubt, the client gets it
            return True

    def components(self, row):
        return ical.events_of(model.parsed(row))

    def report(self, ctx, c, root):
        if root.tag != q(C, "free-busy-query"):
            return None
        tr = root.find(q(C, "time-range"))
        s, e = webdav.utc(tr.get("start") if tr is not None else None), webdav.utc(tr.get("end") if tr is not None else None)
        if not s or not e:
            return Response(status_code=400)
        from app.api import busy_periods
        now = dt.datetime.now(dt.timezone.utc)
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{ical.PRODID}", "BEGIN:VFREEBUSY", f"DTSTAMP:{now:%Y%m%dT%H%M%SZ}",
                 f"DTSTART:{s:%Y%m%dT%H%M%SZ}", f"DTEND:{e:%Y%m%dT%H%M%SZ}"]
        lines += [f"FREEBUSY;FBTYPE=BUSY:{a:%Y%m%dT%H%M%SZ}/{b:%Y%m%dT%H%M%SZ}" for a, b in busy_periods([c], s, e)]
        lines += ["END:VFREEBUSY", "END:VCALENDAR"]
        return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar; charset=utf-8")


router = Calendars().router([access.public])
