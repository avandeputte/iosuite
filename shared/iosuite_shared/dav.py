"""The WebDAV plumbing ioCalendar and ioTasks (CalDAV) and ioContacts (CardDAV) share: building and reading the XML of RFC 4918,
the multistatus response, the preconditions, and the small header rules. What a calendar or an address book is, and
which properties and reports it has, stays in each app (app/caldav.py, app/carddav.py).

Needs defusedxml and FastAPI (the `dav` extra): a client's XML is parsed without entity expansion or external entities.
"""
import datetime as dt
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from urllib.parse import unquote

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_xml
from fastapi.responses import Response

D, CS, AP = "DAV:", "http://calendarserver.org/ns/", "http://apple.com/ns/ical/"
READ = ("read", "read-acl", "read-current-user-privilege-set")
WRITE = ("write", "write-properties", "write-content", "bind", "unbind", "all")


def q(ns: str, tag: str) -> str:
    """The name of an element in a namespace, as ElementTree writes it: {ns}tag."""
    return f"{{{ns}}}{tag}"


def sub(parent, ns: str, tag: str, text=None):
    """A new child element of `parent`, with `text` when given."""
    e = ET.SubElement(parent, q(ns, tag))
    if text is not None:
        e.text = str(text)
    return e


def xml(root: ET.Element, status: int = 207) -> Response:
    body = b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8")
    return Response(body, status_code=status, media_type="application/xml; charset=utf-8")


def unauthorized(label: str, how: str) -> Response:
    """401 with a Basic challenge, which is what makes a DAV client ask for the name and password."""
    return Response(f"Sign in with your {label} name and {how}.", status_code=401,
                    headers={"WWW-Authenticate": f'Basic realm="{label}", charset="UTF-8"'})


def options(classes: str, methods) -> dict:
    """The headers of an OPTIONS answer: the DAV compliance classes ("1, 2, 3, calendar-access, ...") and the methods."""
    return {"DAV": classes, "Allow": ", ".join(methods), "MS-Author-Via": "DAV"}


def http_date(d) -> str:
    """A naive UTC datetime as an HTTP date (getlastmodified, Last-Modified); '' for none."""
    return format_datetime(d.replace(tzinfo=dt.timezone.utc), usegmt=True) if d else ""


def requested(body: bytes) -> tuple[str, list[str]]:
    """PROPFIND body: ('allprop' | 'propname' | 'prop', [clark names])."""
    if not body or not body.strip():
        return "allprop", []
    try:
        root = parse_xml(body)
    except (ET.ParseError, DefusedXmlException):
        return "allprop", []
    if root.find(q(D, "propname")) is not None:
        return "propname", []
    p = root.find(q(D, "prop"))
    if p is None:
        return "allprop", []
    return "prop", [c.tag for c in p]


def privileges(el, writable: bool, also=()):
    """current-user-privilege-set: read, the write privileges when `writable`, and `also` ((namespace, name) pairs: a
    protocol's own, such as CalDAV's read-free-busy)."""
    s = sub(el, D, "current-user-privilege-set")
    for ns, p in [(D, p) for p in READ] + list(also) + ([(D, p) for p in WRITE] if writable else []):
        sub(sub(s, D, "privilege"), ns, p)


def response(ms: ET.Element, href: str, ok: ET.Element, missing: list[str], names_only: bool = False):
    """One <response> of a multistatus: the properties found (200) and the ones asked for that do not exist (404).
    names_only (PROPFIND propname): the names without their values."""
    r = sub(ms, D, "response")
    sub(r, D, "href", href)
    if names_only:
        for c in ok:
            for x in list(c):
                c.remove(x)
            c.text = None
    if len(ok):
        ps = sub(r, D, "propstat")
        ps.append(ok)
        sub(ps, D, "status", "HTTP/1.1 200 OK")
    if missing:
        ps = sub(r, D, "propstat")
        p = sub(ps, D, "prop")
        for n in missing:
            ET.SubElement(p, n)
        sub(ps, D, "status", "HTTP/1.1 404 Not Found")
    return r


def parts_of(path: str) -> list[str]:
    """The segments of a request path below /dav, unquoted."""
    parts = [unquote(p) for p in path.split("/") if p]
    return parts[1:] if parts and parts[0] == "dav" else parts


def etag_match(header: str | None, etag: str | None) -> bool:
    """Whether an If-Match / If-None-Match header names this etag (or *); no header matches anything."""
    if not header:
        return True
    tags = [t.strip().removeprefix("W/").strip('"') for t in header.split(",")]
    return "*" in tags or (etag is not None and etag in tags)


def precondition(ns: str, name: str, status: int = 403, href: str | None = None) -> Response:
    """A failed precondition: <error><name/></error>, as the RFCs ask (valid-sync-token, no-uid-conflict with the
    href of the other resource, max-resource-size...)."""
    e = ET.Element(q(D, "error"))
    el = sub(e, ns, name)
    if href:
        sub(el, D, "href", href)
    return xml(e, status)


def sync_token(prefix: str, collection: dict) -> str:
    """The sync token a client is given for a collection: the app's prefix, the collection's id and its counter."""
    return f"{prefix}{collection['id']}-{collection['sync_token']}"
