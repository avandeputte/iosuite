"""CalDAV (RFC 4791) on WebDAV (RFC 4918), with sync-collection (RFC 6578), getctag, current-user-principal discovery
(RFC 5397, RFC 6764 /.well-known/caldav), MKCALENDAR and extended MKCOL (RFC 5689) and free-busy-query, so Apple
Calendar (Mac, iPhone, iPad), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Calendar, KDE, Outlook (with CalDAV
Synchronizer) and others find the calendars from just the server address, a user name and an app password.

    /dav/                                         root: points to the principal
    /dav/principals/<user>/                       the principal: points to the calendar home
    /dav/calendars/<user>/                        home: one collection per calendar the user sees
    /dav/calendars/<user>/<slug>/                 a calendar (Family, Personal, Birthdays...)
    /dav/calendars/<user>/<slug>/<name>.ics       an event (with its changed occurrences)

Scheduling (RFC 6638: invitations sent by the server) is not offered: the people on an event are noted, not invited.
"""
import datetime as dt
import re
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from urllib.parse import quote, unquote

from fastapi import APIRouter, Request
from icalendar import vDDDTypes
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response

from app import access, config, ical, model

router = APIRouter()

D, C, CS, AP = "DAV:", "urn:ietf:params:xml:ns:caldav", "http://calendarserver.org/ns/", "http://apple.com/ns/ical/"
for pfx, ns in (("d", D), ("cal", C), ("cs", CS), ("ical", AP)):
    ET.register_namespace(pfx, ns)
METHODS = ["OPTIONS", "PROPFIND", "PROPPATCH", "REPORT", "GET", "HEAD", "PUT", "DELETE", "MKCOL", "MKCALENDAR", "MOVE", "COPY"]
SYNC_PREFIX = "urn:x-iocalendar:sync:"


def q(ns, tag):
    return f"{{{ns}}}{tag}"


def _xml(root: ET.Element, status: int = 207) -> Response:
    body = b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8")
    return Response(body, status_code=status, media_type="application/xml; charset=utf-8")


def _unauth() -> Response:
    return Response("Sign in with your ioCalendar name and an app password.", status_code=401,
                    headers={"WWW-Authenticate": 'Basic realm="ioCalendar", charset="UTF-8"'})


def _opts_headers() -> dict:
    return {"DAV": "1, 2, 3, calendar-access, extended-mkcol", "Allow": ", ".join(METHODS), "MS-Author-Via": "DAV"}


def _http_date(d) -> str:
    return format_datetime(d.replace(tzinfo=dt.timezone.utc), usegmt=True) if d else ""


def _sub(parent, ns, tag, text=None):
    e = ET.SubElement(parent, q(ns, tag))
    if text is not None:
        e.text = str(text)
    return e


def _requested(body: bytes) -> tuple[str, list[str]]:
    """PROPFIND body: ('allprop' | 'propname' | 'prop', [clark names])."""
    if not body or not body.strip():
        return "allprop", []
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return "allprop", []
    if root.find(q(D, "propname")) is not None:
        return "propname", []
    p = root.find(q(D, "prop"))
    if p is None:
        return "allprop", []
    return "prop", [c.tag for c in p]


# ------------------------------------------------------------------ properties

class Ctx:
    def __init__(self, request: Request, user: dict):
        self.request, self.user = request, user
        self.base = "/dav"
        self.uname = quote(user["name"])

    @property
    def principal(self):
        return f"{self.base}/principals/{self.uname}/"

    @property
    def home(self):
        return f"{self.base}/calendars/{self.uname}/"

    def cal_href(self, c):
        return f"{self.home}{quote(c['slug'])}/"


def _common(ctx: Ctx, name: str, el: ET.Element) -> bool:
    if name == q(D, "current-user-principal"):
        _sub(_sub(el, D, "current-user-principal"), D, "href", ctx.principal)
    elif name == q(D, "principal-URL"):
        _sub(_sub(el, D, "principal-URL"), D, "href", ctx.principal)
    elif name == q(C, "calendar-home-set"):
        _sub(_sub(el, C, "calendar-home-set"), D, "href", ctx.home)
    elif name == q(D, "principal-collection-set"):
        _sub(_sub(el, D, "principal-collection-set"), D, "href", f"{ctx.base}/principals/")
    elif name == q(D, "owner"):
        _sub(_sub(el, D, "owner"), D, "href", ctx.principal)
    elif name == q(D, "supported-report-set"):
        s = _sub(el, D, "supported-report-set")
        for ns, r in ((C, "calendar-multiget"), (C, "calendar-query"), (C, "free-busy-query"), (D, "sync-collection"),
                      (D, "principal-property-search"), (D, "expand-property")):
            _sub(_sub(_sub(s, D, "supported-report"), D, "report"), ns, r)
    else:
        return False
    return True


def _privs(el, writable: bool):
    s = _sub(el, D, "current-user-privilege-set")
    for p in (["read", "read-acl", "read-current-user-privilege-set", "read-free-busy"] +
              (["write", "write-properties", "write-content", "bind", "unbind", "all"] if writable else [])):
        e = _sub(s, D, "privilege")
        _sub(e, C if p == "read-free-busy" else D, p)


def props_root(ctx: Ctx, names: list[str]):
    ok, missing = ET.Element(q(D, "prop")), []
    for n in names:
        if _common(ctx, n, ok):
            continue
        if n == q(D, "resourcetype"):
            _sub(_sub(ok, D, "resourcetype"), D, "collection")
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", "ioCalendar")
        else:
            missing.append(n)
    return ok, missing


def props_principal(ctx: Ctx, names: list[str]):
    ok, missing = ET.Element(q(D, "prop")), []
    for n in names:
        if _common(ctx, n, ok):
            continue
        if n == q(D, "resourcetype"):
            _sub(_sub(ok, D, "resourcetype"), D, "principal")
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", ctx.user.get("displayName") or ctx.user["name"])
        elif n == q(C, "calendar-user-address-set"):
            s = _sub(ok, C, "calendar-user-address-set")
            if ctx.user.get("email"):
                _sub(s, D, "href", f"mailto:{ctx.user['email']}")
            _sub(s, D, "href", ctx.principal)
        elif n == q(C, "calendar-user-type"):
            _sub(ok, C, "calendar-user-type", "INDIVIDUAL")
        elif n == q(D, "alternate-URI-set"):
            _sub(ok, D, "alternate-URI-set")
        elif n == q(D, "group-membership"):
            _sub(ok, D, "group-membership")
        elif n == q(D, "current-user-privilege-set"):
            _privs(ok, False)
        elif n == q(CS, "email-address-set") and ctx.user.get("email"):
            _sub(_sub(ok, CS, "email-address-set"), CS, "email-address", ctx.user["email"])
        else:
            missing.append(n)
    return ok, missing


def props_home(ctx: Ctx, names: list[str]):
    ok, missing = ET.Element(q(D, "prop")), []
    for n in names:
        if _common(ctx, n, ok):
            continue
        if n == q(D, "resourcetype"):
            _sub(_sub(ok, D, "resourcetype"), D, "collection")
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", "Calendars")
        elif n == q(D, "current-user-privilege-set"):
            _privs(ok, True)
        else:
            missing.append(n)
    return ok, missing


def sync_token(c) -> str:
    return f"{SYNC_PREFIX}{c['id']}-{c['sync_token']}"


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


def props_calendar(ctx: Ctx, c: dict, names: list[str]):
    ok, missing = ET.Element(q(D, "prop")), []
    w = model.can_write(ctx.user, c)
    for n in names:
        if _common(ctx, n, ok):
            continue
        if n == q(D, "resourcetype"):
            rt = _sub(ok, D, "resourcetype")
            _sub(rt, D, "collection")
            _sub(rt, C, "calendar")
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", c["name"])
        elif n == q(C, "calendar-description"):
            _sub(ok, C, "calendar-description", c.get("description") or "")
        elif n == q(C, "supported-calendar-component-set"):
            _sub(_sub(ok, C, "supported-calendar-component-set"), C, "comp").set("name", "VEVENT")
        elif n == q(C, "supported-calendar-data"):
            e = _sub(_sub(ok, C, "supported-calendar-data"), C, "calendar-data")
            e.set("content-type", "text/calendar")
            e.set("version", "2.0")
        elif n == q(C, "calendar-timezone"):
            tz = _vtimezone(c.get("timezone") or ical.default_tz())
            if tz:
                _sub(ok, C, "calendar-timezone", tz)
            else:
                missing.append(n)
        elif n == q(C, "max-resource-size"):
            _sub(ok, C, "max-resource-size", config.MAX_EVENT_BYTES)
        elif n == q(C, "min-date-time"):
            _sub(ok, C, "min-date-time", "19000101T000000Z")
        elif n == q(C, "max-date-time"):
            _sub(ok, C, "max-date-time", "21991231T235959Z")
        elif n == q(C, "schedule-calendar-transp"):
            _sub(_sub(ok, C, "schedule-calendar-transp"), C, "transparent" if c.get("kind") in model.READ_ONLY_KINDS else "opaque")
        elif n == q(CS, "getctag"):
            _sub(ok, CS, "getctag", str(c["sync_token"]))
        elif n == q(D, "sync-token"):
            _sub(ok, D, "sync-token", sync_token(c))
        elif n == q(D, "current-user-privilege-set"):
            _privs(ok, w)
        elif n == q(D, "getetag"):
            _sub(ok, D, "getetag", f'"ctag-{c["sync_token"]}"')
        elif n == q(AP, "calendar-color"):
            _sub(ok, AP, "calendar-color", (c.get("color") or model.PALETTE[0]).upper() + "FF")
        elif n == q(AP, "calendar-order"):
            _sub(ok, AP, "calendar-order", c.get("position") or c["id"])
        elif n == q(D, "getcontenttype"):
            _sub(ok, D, "getcontenttype", "httpd/unix-directory")
        else:
            missing.append(n)
    return ok, missing


def props_object(ctx: Ctx, row: dict, c: dict, names: list[str], data_el: ET.Element | None = None):
    ok, missing = ET.Element(q(D, "prop")), []
    for n in names:
        if n == q(D, "getetag"):
            _sub(ok, D, "getetag", f'"{row["etag"]}"')
        elif n == q(D, "getcontenttype"):
            _sub(ok, D, "getcontenttype", "text/calendar; charset=utf-8; component=VEVENT")
        elif n == q(D, "resourcetype"):
            _sub(ok, D, "resourcetype")
        elif n == q(D, "getlastmodified"):
            _sub(ok, D, "getlastmodified", _http_date(row["updated_at"]))
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", row["summary"])
        elif n == q(C, "calendar-data"):
            _sub(ok, C, "calendar-data", _calendar_data(row, data_el))
        elif n == q(D, "getcontentlength"):
            _sub(ok, D, "getcontentlength", len(row["ics"].encode()))
        elif n == q(D, "current-user-privilege-set"):
            _privs(ok, model.can_write(ctx.user, c))
        elif n == q(D, "owner"):
            _sub(_sub(ok, D, "owner"), D, "href", ctx.principal)
        elif n == q(C, "schedule-tag"):
            missing.append(n)
        else:
            missing.append(n)
    return ok, missing


def _calendar_data(row: dict, data_el: ET.Element | None) -> str:
    """calendar-data, expanded into separate occurrences when the client asks (<C:expand start= end=/>)."""
    exp = data_el.find(q(C, "expand")) if data_el is not None else None
    if exp is None:
        return row["ics"]
    try:
        s, e = _utc(exp.get("start")), _utc(exp.get("end"))
        import recurring_ical_events
        cal = model.parsed(row)
        out = ical.new_calendar()
        for occ in recurring_ical_events.of(cal).between(s, e):
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


ALLPROP = {
    "root": [q(D, "resourcetype"), q(D, "displayname"), q(D, "current-user-principal")],
    "principal": [q(D, "resourcetype"), q(D, "displayname"), q(D, "principal-URL"), q(C, "calendar-home-set"), q(C, "calendar-user-address-set")],
    "home": [q(D, "resourcetype"), q(D, "displayname")],
    "calendar": [q(D, "resourcetype"), q(D, "displayname"), q(CS, "getctag"), q(D, "sync-token"), q(C, "calendar-description"),
                 q(C, "supported-calendar-component-set"), q(AP, "calendar-color")],
    "object": [q(D, "resourcetype"), q(D, "getetag"), q(D, "getcontenttype"), q(D, "getlastmodified"), q(D, "getcontentlength")],
}


def _response(ms: ET.Element, href: str, ok: ET.Element, missing: list[str], names_only: bool = False):
    r = _sub(ms, D, "response")
    _sub(r, D, "href", href)
    if names_only:
        for c in ok:
            for x in list(c):
                c.remove(x)
            c.text = None
    if len(ok):
        ps = _sub(r, D, "propstat")
        ps.append(ok)
        _sub(ps, D, "status", "HTTP/1.1 200 OK")
    if missing:
        ps = _sub(r, D, "propstat")
        p = _sub(ps, D, "prop")
        for n in missing:
            ET.SubElement(p, n)
        _sub(ps, D, "status", "HTTP/1.1 404 Not Found")
    return r


# ------------------------------------------------------------------ resolving paths

def _parse(path: str) -> list[str]:
    parts = [unquote(p) for p in path.split("/") if p]
    return parts[1:] if parts and parts[0] == "dav" else parts


def _cal(ctx: Ctx, slug: str):
    return model.by_slug(ctx.user, slug)


def _utc(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = dt.datetime.strptime(s[:15], "%Y%m%dT%H%M%S")
    except ValueError:
        try:
            d = dt.datetime.strptime(s[:8], "%Y%m%d")
        except ValueError:
            return None
    return d.replace(tzinfo=dt.timezone.utc)


# ------------------------------------------------------------------ the handler

@router.api_route("/.well-known/caldav", methods=["GET", "PROPFIND", "OPTIONS", "HEAD"], include_in_schema=False, dependencies=[access.public])
def well_known():
    return RedirectResponse("/dav/", status_code=301)


@router.api_route("/dav", methods=METHODS, include_in_schema=False, dependencies=[access.public])
@router.api_route("/dav/{path:path}", methods=METHODS, include_in_schema=False, dependencies=[access.public])
async def dav(request: Request, path: str = ""):
    if request.method == "OPTIONS":
        return Response(status_code=200, headers=_opts_headers())
    user = request.state.user
    if not user:
        return _unauth()
    ctx = Ctx(request, user)
    parts = _parse(request.url.path)
    body = await request.body()
    if len(body) > config.MAX_EVENT_BYTES:  # a PUT larger than that is refused anyway; no request body needs more
        return _precondition(C, "max-resource-size", 403) if request.method == "PUT" else Response(status_code=413)
    return await run_in_threadpool(_dispatch, ctx, request.method, parts, body, request.headers)


def _dispatch(ctx: Ctx, m: str, parts: list[str], body: bytes, headers) -> Response:
    # /dav/principals/<user>/... and /dav/calendars/<user>/... only for that user
    if len(parts) >= 2 and parts[0] in ("principals", "calendars") and parts[1] != ctx.user["name"]:
        return Response("Not yours", status_code=403)
    model.ensure_personal(ctx.user)
    depth = (headers.get("depth") or "1").strip().lower()
    if m == "PROPFIND":
        return _propfind(ctx, parts, body, depth)
    if m == "REPORT":
        return _report(ctx, parts, body)
    if m == "PROPPATCH":
        return _proppatch(ctx, parts, body)
    if m in ("GET", "HEAD"):
        return _get(ctx, parts, m == "HEAD")
    if m == "PUT":
        return _put(ctx, parts, body, headers)
    if m == "DELETE":
        return _delete(ctx, parts, headers)
    if m in ("MKCOL", "MKCALENDAR"):
        return _mkcalendar(ctx, parts, body)
    return Response(status_code=405, headers=_opts_headers())


def _propfind(ctx: Ctx, parts, body, depth) -> Response:
    mode, names = _requested(body)
    ms = ET.Element(q(D, "multistatus"))
    nm = mode == "propname"

    def pick(kind):
        return ALLPROP[kind] if mode != "prop" else names

    if not parts:  # /dav/
        _response(ms, f"{ctx.base}/", *props_root(ctx, pick("root")), names_only=nm)
        if depth != "0":
            _response(ms, ctx.principal, *props_principal(ctx, pick("principal")), names_only=nm)
            _response(ms, ctx.home, *props_home(ctx, pick("home")), names_only=nm)
        return _xml(ms)
    if parts[0] == "principals":
        if len(parts) == 1:
            _response(ms, f"{ctx.base}/principals/", *props_root(ctx, pick("root")), names_only=nm)
            if depth != "0":
                _response(ms, ctx.principal, *props_principal(ctx, pick("principal")), names_only=nm)
            return _xml(ms)
        if len(parts) > 2:
            return Response(status_code=404)
        _response(ms, ctx.principal, *props_principal(ctx, pick("principal")), names_only=nm)
        return _xml(ms)
    if parts[0] != "calendars":
        return Response(status_code=404)
    if len(parts) == 1:
        _response(ms, f"{ctx.base}/calendars/", *props_root(ctx, pick("root")), names_only=nm)
        if depth != "0":
            _response(ms, ctx.home, *props_home(ctx, pick("home")), names_only=nm)
        return _xml(ms)
    if len(parts) == 2:
        _response(ms, ctx.home, *props_home(ctx, pick("home")), names_only=nm)
        if depth != "0":
            for c in model.calendars_for(ctx.user):
                _response(ms, ctx.cal_href(c), *props_calendar(ctx, c, pick("calendar")), names_only=nm)
        return _xml(ms)
    c = _cal(ctx, parts[2])
    if not c:
        return Response(status_code=404)
    if len(parts) == 3:
        _response(ms, ctx.cal_href(c), *props_calendar(ctx, c, pick("calendar")), names_only=nm)
        if depth != "0":
            for row in model.rows(c["id"]):
                _response(ms, ctx.cal_href(c) + quote(row["href"]), *props_object(ctx, row, c, pick("object")), names_only=nm)
        return _xml(ms)
    row = model.by_href(c["id"], parts[3])
    if not row or row["deleted"]:
        return Response(status_code=404)
    _response(ms, ctx.cal_href(c) + quote(row["href"]), *props_object(ctx, row, c, pick("object")), names_only=nm)
    return _xml(ms)


def _proppatch(ctx: Ctx, parts, body) -> Response:
    ms = ET.Element(q(D, "multistatus"))
    try:
        root = ET.fromstring(body or b"<x/>")
    except ET.ParseError:
        return Response(status_code=400)
    c = _cal(ctx, parts[2]) if len(parts) == 3 and parts[0] == "calendars" else None
    w = bool(c) and model.can_write(ctx.user, c)
    r = _sub(ms, D, "response")
    _sub(r, D, "href", "/dav/" + "/".join(quote(p) for p in parts) + "/")
    ps = _sub(r, D, "propstat")
    p = _sub(ps, D, "prop")
    changes: dict = {}  # all the properties in one update (one sync token for the request)
    for s in root.iter(q(D, "set")):
        for prop in s.iter(q(D, "prop")):
            for el in prop:
                ET.SubElement(p, el.tag)
                if not w:
                    continue
                v = (el.text or "").strip()
                if el.tag == q(D, "displayname") and v:
                    changes["name"] = v[:128]
                elif el.tag == q(C, "calendar-description"):
                    changes["description"] = v[:512]
                elif el.tag == q(AP, "calendar-color"):
                    changes["color"] = v[:9]
                elif el.tag == q(AP, "calendar-order") and v.lstrip("-").isdigit():
                    changes["sort"] = int(v)
                elif el.tag == q(C, "calendar-timezone"):
                    m = re.search(r"^TZID:(.+)$", v, re.M)
                    if m and ical.valid_tz(m.group(1).strip()):
                        changes["timezone"] = m.group(1).strip()
    if changes:
        model.update_calendar(c["id"], **changes)
    for s in root.iter(q(D, "remove")):
        for prop in s.iter(q(D, "prop")):
            for el in prop:
                ET.SubElement(p, el.tag)
    _sub(ps, D, "status", "HTTP/1.1 200 OK" if (w or not len(p)) else "HTTP/1.1 403 Forbidden")
    return _xml(ms)


def _get(ctx: Ctx, parts, head: bool) -> Response:
    if len(parts) == 3 and parts[0] == "calendars":
        # GET on a collection: the whole calendar as one .ics (handy for a browser)
        c = _cal(ctx, parts[2])
        if not c:
            return Response(status_code=404)
        text = model.export_text([c], c["name"])
        return Response(b"" if head else text.encode(), media_type="text/calendar; charset=utf-8")
    if len(parts) < 4 or parts[0] != "calendars":
        return Response("ioCalendar CalDAV server. Point your calendar app at this address.", media_type="text/plain")
    c = _cal(ctx, parts[2])
    row = model.by_href(c["id"], parts[3]) if c else None
    if not row or row["deleted"]:
        return Response(status_code=404)
    return Response(b"" if head else row["ics"].encode(), media_type="text/calendar; charset=utf-8",
                    headers={"ETag": f'"{row["etag"]}"', "Last-Modified": _http_date(row["updated_at"])})


def _etag_match(header: str | None, etag: str | None) -> bool:
    if not header:
        return True
    tags = [t.strip().removeprefix("W/").strip('"') for t in header.split(",")]
    return "*" in tags or (etag is not None and etag in tags)


def _precondition(ns: str, name: str, status: int, href: str | None = None) -> Response:
    e = ET.Element(q(D, "error"))
    el = _sub(e, ns, name)
    if href:
        _sub(el, D, "href", href)
    return _xml(e, status)


def _put(ctx: Ctx, parts, body: bytes, headers) -> Response:
    if len(parts) != 4 or parts[0] != "calendars":
        return Response(status_code=405)
    c = _cal(ctx, parts[2])
    if not c:
        return Response(status_code=409)
    if not model.can_write(ctx.user, c):
        return Response(status_code=403)
    if len(body) > config.MAX_EVENT_BYTES:
        return _precondition(C, "max-resource-size", 403)
    row = model.by_href(c["id"], parts[3])
    if row and row["deleted"]:
        row = None
    if headers.get("if-none-match", "").strip() == "*" and row:
        return Response(status_code=412)
    if headers.get("if-match") and (not row or not _etag_match(headers.get("if-match"), row["etag"])):
        return Response(status_code=412)
    try:
        cal = ical.parse(body)
    except ValueError:
        return _precondition(C, "valid-calendar-data", 400)
    kinds = {s.name for s in cal.subcomponents if s.name != "VTIMEZONE"}
    if kinds - {"VEVENT"}:
        return _precondition(C, "supported-calendar-component", 403)
    try:
        ix = ical.index(cal, c.get("timezone"))
    except ValueError:
        return _precondition(C, "valid-calendar-object-resource", 400)
    # the same UID twice in one calendar is refused (RFC 4791 5.3.2.1 no-uid-conflict)
    other = model.by_uid(c["id"], ix["uid"])
    if other and (not row or other["id"] != row["id"]):
        return _precondition(C, "no-uid-conflict", 409, ctx.cal_href(c) + quote(other["href"]))
    new = model.save(c["id"], cal, row["id"] if row else None, parts[3], ctx.user["id"], c.get("timezone"))
    return Response(status_code=204 if row else 201, headers={"ETag": f'"{new["etag"]}"'})


def _delete(ctx: Ctx, parts, headers) -> Response:
    if parts[:1] != ["calendars"] or len(parts) < 3:
        return Response(status_code=403)
    c = _cal(ctx, parts[2])
    if not c:
        return Response(status_code=404)
    if not model.can_write(ctx.user, c):
        return Response(status_code=403)
    if len(parts) == 3:
        if model.is_shared(c):
            return Response("Shared calendars are deleted in the web app by an admin", status_code=403)
        if len([x for x in model.calendars_for(ctx.user) if x["owner_id"] == ctx.user["id"]]) <= 1:
            return Response("Your last private calendar stays", status_code=403)
        model.delete_calendar(c["id"])
        return Response(status_code=204)
    row = model.by_href(c["id"], parts[3])
    if not row or row["deleted"]:
        return Response(status_code=404)
    if headers.get("if-match") and not _etag_match(headers.get("if-match"), row["etag"]):
        return Response(status_code=412)
    model.delete(row["id"])
    return Response(status_code=204)


def _mkcalendar(ctx: Ctx, parts, body) -> Response:
    """MKCALENDAR (RFC 4791) or extended MKCOL (RFC 5689): a client making a new private calendar."""
    if len(parts) != 3 or parts[0] != "calendars":
        return Response(status_code=403)
    if _cal(ctx, parts[2]):
        return Response(status_code=405)
    name, color, desc, tz = parts[2], None, None, None
    try:
        root = ET.fromstring(body) if body else None
    except ET.ParseError:
        root = None
    if root is not None:
        rt = root.find(f".//{q(D, 'resourcetype')}")
        if rt is not None and rt.find(q(C, "calendar")) is None:
            return Response("Only calendars can be made here", status_code=403)
        for el, attr in ((q(D, "displayname"), "name"), (q(AP, "calendar-color"), "color"), (q(C, "calendar-description"), "desc"),
                         (q(C, "calendar-timezone"), "tz")):
            x = root.find(f".//{el}")
            if x is not None and (x.text or "").strip():
                v = x.text.strip()
                if attr == "name":
                    name = v
                elif attr == "color":
                    color = v
                elif attr == "desc":
                    desc = v
                else:
                    m = re.search(r"^TZID:(.+)$", v, re.M)
                    tz = m.group(1).strip() if m else None
    model.create_calendar(ctx.user["id"], name, desc, color, slug=re.sub(r"[^A-Za-z0-9._-]", "-", parts[2])[:56], timezone=tz)
    return Response(status_code=201)


# ------------------------------------------------------------------ REPORT

def _report(ctx: Ctx, parts, body) -> Response:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return Response(status_code=400)
    tag = root.tag
    if tag in (q(D, "principal-property-search"), q(D, "principal-search-property-set")):
        ms = ET.Element(q(D, "multistatus"))
        if tag == q(D, "principal-property-search"):
            p = root.find(q(D, "prop"))
            names = [c.tag for c in p] if p is not None else ALLPROP["principal"]
            _response(ms, ctx.principal, *props_principal(ctx, names))
        return _xml(ms)
    if tag == q(D, "expand-property"):
        ms = ET.Element(q(D, "multistatus"))
        _response(ms, ctx.principal, *props_principal(ctx, ALLPROP["principal"]))
        return _xml(ms)
    if len(parts) < 3 or parts[0] != "calendars":
        return Response(status_code=403)
    c = _cal(ctx, parts[2])
    if not c:
        return Response(status_code=404)
    p = root.find(q(D, "prop"))
    names = [x.tag for x in p] if p is not None else [q(D, "getetag")]
    data_el = p.find(q(C, "calendar-data")) if p is not None else None
    ms = ET.Element(q(D, "multistatus"))
    if tag == q(C, "calendar-multiget"):
        for h in root.findall(q(D, "href")):
            href = unquote((h.text or "").strip())
            name = href.rstrip("/").rsplit("/", 1)[-1]
            row = model.by_href(c["id"], name)
            if row and not row["deleted"]:
                _response(ms, ctx.cal_href(c) + quote(row["href"]), *props_object(ctx, row, c, names, data_el))
            else:
                r = _sub(ms, D, "response")
                _sub(r, D, "href", (h.text or "").strip())
                _sub(r, D, "status", "HTTP/1.1 404 Not Found")
        return _xml(ms)
    if tag == q(C, "calendar-query"):
        flt = root.find(q(C, "filter"))
        for row in _query(c, flt):
            _response(ms, ctx.cal_href(c) + quote(row["href"]), *props_object(ctx, row, c, names, data_el))
        return _xml(ms)
    if tag == q(C, "free-busy-query"):
        tr = root.find(q(C, "time-range"))
        s, e = _utc(tr.get("start") if tr is not None else None), _utc(tr.get("end") if tr is not None else None)
        if not s or not e:
            return Response(status_code=400)
        from app.api import busy_periods
        now = dt.datetime.now(dt.timezone.utc)
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{ical.PRODID}", "BEGIN:VFREEBUSY", f"DTSTAMP:{now:%Y%m%dT%H%M%SZ}",
                 f"DTSTART:{s:%Y%m%dT%H%M%SZ}", f"DTEND:{e:%Y%m%dT%H%M%SZ}"]
        lines += [f"FREEBUSY;FBTYPE=BUSY:{a:%Y%m%dT%H%M%SZ}/{b:%Y%m%dT%H%M%SZ}" for a, b in busy_periods([c], s, e)]
        lines += ["END:VFREEBUSY", "END:VCALENDAR"]
        return Response("\r\n".join(lines) + "\r\n", media_type="text/calendar; charset=utf-8")
    if tag == q(D, "sync-collection"):
        tok_el = root.find(q(D, "sync-token"))
        tok = (tok_el.text or "").strip() if tok_el is not None else ""
        since = None
        if tok:
            m = re.match(re.escape(SYNC_PREFIX) + r"(\d+)-(\d+)$", tok)
            if not m or int(m.group(1)) != c["id"] or int(m.group(2)) > c["sync_token"]:
                return _precondition(D, "valid-sync-token", 403)
            since = int(m.group(2))
        cur = model.calendar(c["id"])
        for row in model.rows(c["id"], since):
            href = ctx.cal_href(c) + quote(row["href"])
            if row["deleted"]:
                if since is None:
                    continue
                r = _sub(ms, D, "response")
                _sub(r, D, "href", href)
                _sub(r, D, "status", "HTTP/1.1 404 Not Found")
            else:
                _response(ms, href, *props_object(ctx, row, c, names, data_el))
        _sub(ms, D, "sync-token", sync_token(cur))
        return _xml(ms)
    return _precondition(D, "supported-report", 403)


def _query(c: dict, flt: ET.Element | None) -> list[dict]:
    """calendar-query: VCALENDAR > VEVENT comp-filters, with a time-range and text-match prop-filters (UID, SUMMARY...)."""
    vc = flt.find(q(C, "comp-filter")) if flt is not None else None
    if vc is None:
        return model.rows(c["id"])
    ve_filters = vc.findall(q(C, "comp-filter"))
    if not ve_filters:
        return model.rows(c["id"])
    out = []
    for vf in ve_filters:
        name = (vf.get("name") or "").upper()
        if vf.find(q(C, "is-not-defined")) is not None:
            if name != "VEVENT":
                return model.rows(c["id"])
            return []
        if name != "VEVENT":
            continue  # VTODO, VJOURNAL: none here
        tr = vf.find(q(C, "time-range"))
        s = _utc(tr.get("start")) if tr is not None else None
        e = _utc(tr.get("end")) if tr is not None else None
        rows = model.rows_in_range([c["id"]], s, e) if (s or e) else model.rows(c["id"])
        for row in rows:
            if (s or e) and not _overlaps(row, c, s, e):
                continue
            if not _props_match(row, vf):
                continue
            out.append(row)
    seen, uniq = set(), []
    for r in out:
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)
    return uniq


def _overlaps(row: dict, c: dict, s, e) -> bool:
    try:
        cal = model.parsed(row)
        return bool(ical.occurrences(cal, s or dt.datetime(1900, 1, 1, tzinfo=dt.timezone.utc), e or ical.FAR, c.get("timezone")))
    except Exception:  # noqa: BLE001 - when in doubt, the client gets it
        return True


def _props_match(row: dict, vf: ET.Element) -> bool:
    pfs = vf.findall(q(C, "prop-filter"))
    if not pfs:
        return True
    comps = ical.events_of(model.parsed(row))
    return any(_props_match_one(ev, pfs) for ev in comps)  # the series, or any of its changed occurrences


def _text_of(v) -> str:
    """A property's text as written (CATEGORIES and the like are objects whose str() is not their text)."""
    if isinstance(v, list):
        return ",".join(_text_of(x) for x in v)
    raw = v.to_ical() if hasattr(v, "to_ical") else v
    return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)


def _props_match_one(ev, pfs) -> bool:
    for pf in pfs:
        name = (pf.get("name") or "").upper()
        v = ev.get(name)
        if pf.find(q(C, "is-not-defined")) is not None:
            if v is not None:
                return False
            continue
        if v is None:
            return False
        tm = pf.find(q(C, "text-match"))
        if tm is not None:
            needle = (tm.text or "").lower()
            hay = _text_of(v).lower()
            kind = tm.get("match-type", "contains")
            hit = (hay == needle if kind == "equals" else hay.startswith(needle) if kind == "starts-with"
                   else hay.endswith(needle) if kind == "ends-with" else needle in hay)
            if (tm.get("negate-condition") == "yes") == hit:
                return False
    return True
