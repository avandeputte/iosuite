"""CalDAV (RFC 4791) for to-dos, on WebDAV (RFC 4918), with sync-collection (RFC 6578), getctag,
current-user-principal discovery (RFC 5397, RFC 6764 /.well-known/caldav) and MKCALENDAR / extended MKCOL (RFC 5689),
so Apple Reminders (iPhone, iPad, Mac), DAVx⁵ with jtx Board or Tasks.org on Android, Thunderbird and others find the
lists from just the server address, a user name and an app password.

Every list is a calendar collection that holds VTODO components only (supported-calendar-component-set), which is how
Apple's Reminders tells its lists apart from calendars: on an iPhone the account shows in Reminders, and Calendar finds
nothing to show.

    /dav/                                         root: points to the principal
    /dav/principals/<user>/                       the principal: points to the home
    /dav/calendars/<user>/                        home: one collection per list the user sees
    /dav/calendars/<user>/<slug>/                 a list (Family, Personal...)
    /dav/calendars/<user>/<slug>/<name>.ics       a task

The server itself is the suite's (iosuite_shared.dav.CalDAV); what is here is what a list and a task are: a task that
repeats after completion, the history of changes, and which tasks a time range takes in.
"""
import datetime as dt

from fastapi.responses import Response
from iosuite_shared import dav as webdav
from iosuite_shared.dav import CALDAV as C

from app import access, config, ical, model


class Lists(webdav.CalDAV):
    label = "ioTask"
    banner = "ioTask CalDAV server. Point your reminders app at this address."
    sync_prefix = "urn:x-iotask:sync:"
    max_bytes = config.MAX_TASK_BYTES
    home_name, plural, singular = "Lists", "lists", "list"
    component = "VTODO"
    # iOS makes a placeholder collection when an account has none of a kind ("DEFAULT_CALENDAR_NAME" for events,
    # "DEFAULT_TASK_CALENDAR_NAME" for to-dos): every account has a list here, and events are not kept, so neither is made
    placeholders = ("DEFAULT_CALENDAR_NAME", "DEFAULT_TASK_CALENDAR_NAME")

    def before(self, ctx):
        model.ensure_personal(ctx.user)

    def collections(self, user):
        return model.lists_for(user)

    def collection(self, user, slug):
        return model.by_slug(user, slug)

    def reload(self, c):
        return model.task_list(c["id"])

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
        return ical.vtimezone(ical.default_tz())

    def color(self, c):
        return (c.get("color") or model.PALETTE[0]).upper() + "FF"

    def update(self, c, changes):
        model.update_list(c["id"], **changes)

    def save(self, ctx, c, row, name, body):
        try:
            cal = ical.parse(body)
        except ValueError:
            return webdav.precondition(C, "valid-calendar-data", 400)
        if ical.kinds_of(cal) != {"VTODO"}:  # events belong in ioCalendar
            return webdav.precondition(C, "supported-calendar-component")
        try:
            ix = ical.index(cal)
        except ValueError:
            return webdav.precondition(C, "valid-calendar-object-resource", 400)
        refused = self.conflict(ctx, c, row, model.by_uid(c["id"], ix["uid"]))
        if refused:
            return refused
        # a task that repeats after completion keeps its rule, and comes back when the app ticked it off: the app is not
        # told an ETag then, so it fetches what the server made of it
        ticked = bool(row) and not row["done"] and ical.status_of(ical.todo(cal)) == "COMPLETED"
        mine = bool(row) and ical.keep_after_done(model.parsed(row), cal)
        back = mine and ticked
        with model.step("caldav"):
            new = model.save(c["id"], ical.finish(cal) if mine else cal, row["id"] if row else None, name, ctx.user["id"],
                             "done" if back else None, f"next {(ical.todo_json(cal)['due'] or '')[:10]}" if back else None)
        return Response(status_code=204 if row else 201, headers={} if mine else {"ETag": f'"{new["etag"]}"'})

    def delete(self, ctx, c, row):
        with model.step("caldav"):
            model.delete(row["id"], ctx.user["id"])

    def drop(self, c):
        model.delete_list(c["id"])

    def create(self, ctx, slug, name, description, color, tz_text):
        model.create_list(ctx.user["id"], name, description, color, slug=slug)

    def overlaps(self, c, row, s, e):
        """RFC 4791 9.9 for a VTODO, simplified: its moments (start, due, completed, else created) against the range; a
        task with none of them is in every range."""
        pts = [x.replace(tzinfo=dt.timezone.utc) for x in (row.get("start"), row.get("due"), row.get("completed_at")) if x is not None]
        if not pts:
            return True
        lo, hi = min(pts), max(pts)
        if row.get("due_all_day") and row.get("due") is not None:
            hi = max(hi, row["due"].replace(tzinfo=dt.timezone.utc) + dt.timedelta(days=1))
        return (e is None or lo < e) and (s is None or hi >= s)

    def components(self, row):
        return ical.todos_of(model.parsed(row))


router = Lists().router([access.public])
