"""The WebDAV server ioCalendar and ioTask (CalDAV) and ioContact (CardDAV) share: the XML of RFC 4918, the multistatus
response, the preconditions and the small header rules, and on them `Server` (PROPFIND, PROPPATCH, GET, PUT, DELETE,
MKCOL, sync-collection, multiget, discovery) and `CalDAV` (calendar-query, MKCALENDAR, the calendar properties). What a
calendar, a task list or an address book is, and what is kept of an object, stays in each app (app/caldav.py,
app/carddav.py): a subclass that fills in the hooks.

Needs defusedxml and FastAPI (the `dav` extra): a client's XML is parsed without entity expansion or external entities.
"""
import datetime as dt
import re
import xml.etree.ElementTree as ET
from email.utils import format_datetime
from urllib.parse import quote, unquote

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_xml
from fastapi import Request
from fastapi.responses import Response

from iosuite_shared import prefix, users
from iosuite_shared.errors import Invalid

D, CS, AP = "DAV:", "http://calendarserver.org/ns/", "http://apple.com/ns/ical/"
CALDAV, CARDDAV = "urn:ietf:params:xml:ns:caldav", "urn:ietf:params:xml:ns:carddav"
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


# ------------------------------------------------------------------ the server

class Ctx:
    """One request: who asks, and the addresses of what they see. `base` is /dav, or /calendar/dav when the suite shares
    one address: what every href starts with."""

    def __init__(self, server: "Server", request, user: dict):
        self.server, self.request, self.user = server, request, user
        self.base = prefix.of(request) + "/dav"
        self.uname = quote(user["name"])

    @property
    def principal(self) -> str:
        return f"{self.base}/principals/{self.uname}/"

    @property
    def home(self) -> str:
        return f"{self.base}/{self.server.home_segment}/{self.uname}/"

    def href(self, collection: dict, row: dict | None = None) -> str:
        """A collection's address, or one of its objects' when `row` is given."""
        h = f"{self.home}{quote(collection['slug'])}/"
        return h + quote(row["href"]) if row else h


def _not_found(ms: ET.Element, href: str) -> None:
    r = sub(ms, D, "response")
    sub(r, D, "href", href)
    sub(r, D, "status", "HTTP/1.1 404 Not Found")


def _xml_of(body: bytes):
    """A request body's XML root, or None when there is none or it is not XML."""
    try:
        return parse_xml(body) if body and body.strip() else None
    except (ET.ParseError, DefusedXmlException):
        return None


class Server:
    """A DAV server for one kind of collection, the same for CalDAV (calendars, task lists) and CardDAV (address books):

        /dav/                                     root: points to the principal
        /dav/principals/<user>/                   the principal: points to the home
        /dav/<home_segment>/<user>/               home: one collection per collection the user sees
        /dav/<home_segment>/<user>/<slug>/        a collection
        /dav/<home_segment>/<user>/<slug>/<name>  an object

    PROPFIND, PROPPATCH, GET, PUT and DELETE preconditions, MKCOL, sync-collection with its tokens, multiget and the
    discovery reports are done here. An app subclasses it (CalDAV below for calendars) and fills in what its collections
    and objects are: the hooks after the settings. Rows are the app's own dicts; a row has at least id, href, etag,
    deleted and updated_at, a collection id, slug, name and sync_token.
    """

    # --- settings
    label = "ioSomething"                    # the realm of the sign-in, the root's name
    how = "an app password"                  # "Sign in with your <label> name and <how>."
    ns = ""                                  # the protocol's namespace (CalDAV's, CardDAV's)
    ns_prefix = ""                           # the prefix it is written with
    classes = "1, 2, 3"                      # the DAV header
    methods = ["OPTIONS", "PROPFIND", "PROPPATCH", "REPORT", "GET", "HEAD", "PUT", "DELETE", "MKCOL", "MOVE", "COPY"]
    well_known = ""                          # /.well-known/<this> points to /dav/
    home_segment = ""                        # calendars, addressbooks
    home_set = ""                            # calendar-home-set, addressbook-home-set
    home_name = ""                           # the home's displayname
    collection_type = ""                     # the resourcetype of a collection beside DAV:collection
    description = ""                         # the property of a collection's description
    data = ""                                # the property of an object's text (calendar-data, address-data)
    multiget = ""                            # the multiget report
    query = ""                               # the query report
    reports: tuple = ()                      # supported-report-set besides sync-collection and the principal ones
    also_privileges: tuple = ()              # privileges of the protocol a reader has (CalDAV's read-free-busy)
    content_type = ""                        # an object's media type (GET)
    object_type = ""                         # an object's getcontenttype (content_type unless set)
    sync_prefix = ""                         # what the sync tokens start with
    max_bytes = 1024 * 1024                  # the largest object, and the largest request body
    plural, singular = "collections", "collection"
    keep_last = False                        # a member's last private collection is not deleted over DAV
    banner = "A WebDAV server."              # GET on what is neither a collection nor an object
    patch_elsewhere = False                  # PROPPATCH on the home or the principal: 200 and nothing kept, or 403
    allprop: dict = {}                       # allprop: root, principal, home, collection, object

    def __init__(self):
        for pfx, ns in (("d", D), (self.ns_prefix, self.ns), ("cs", CS), ("ical", AP)):
            ET.register_namespace(pfx, ns)
        self.allprop = {
            "root": [q(D, "resourcetype"), q(D, "displayname"), q(D, "current-user-principal")],
            "principal": [q(D, "resourcetype"), q(D, "displayname"), q(D, "principal-URL"), q(self.ns, self.home_set)],
            "home": [q(D, "resourcetype"), q(D, "displayname")],
            "collection": [q(D, "resourcetype"), q(D, "displayname"), q(CS, "getctag"), q(D, "sync-token"), q(self.ns, self.description)],
            "object": [q(D, "resourcetype"), q(D, "getetag"), q(D, "getcontenttype"), q(D, "getlastmodified"), q(D, "getcontentlength")],
        } | {k: v for k, v in self.allprop.items()}

    # --- hooks: what the app's collections and objects are

    def before(self, ctx: Ctx) -> None:
        """Before each request (signed in): ioCalendar and ioTask make a member's Personal collection here."""

    def collections(self, user: dict) -> list[dict]:
        raise NotImplementedError

    def collection(self, user: dict, slug: str) -> dict | None:
        raise NotImplementedError

    def reload(self, c: dict) -> dict:
        """The collection as it is now (its sync token after the rows were read)."""
        raise NotImplementedError

    def can_write(self, user: dict, c: dict) -> bool:
        raise NotImplementedError

    def is_shared(self, c: dict) -> bool:
        return c.get("owner_id") is None

    def rows(self, c: dict, since: int | None = None, names: list[str] = ()) -> list[dict]:
        """A collection's objects, or what changed after the sync token `since` (deletions included). `names`: the
        properties asked for, when the app can leave the objects' text out (none of them is `data`)."""
        raise NotImplementedError

    def by_href(self, c: dict, name: str) -> dict | None:
        raise NotImplementedError

    def purged_before(self, c: dict) -> int:
        """The sync token up to which the collection's deletion markers are gone (0: none were purged)."""
        raise NotImplementedError

    def preload(self, rows: list[dict], names: list[str]) -> dict:
        """{id: whatever object_data needs} for many rows read at once (ioContact reads the cards together)."""
        return {}

    def title(self, row: dict) -> str:
        """An object's displayname."""
        raise NotImplementedError

    def object_data(self, row: dict, data_el, loaded=None) -> str:
        """An object's text in a multistatus; `data_el` is the data element the client asked with (CalDAV's expand,
        CardDAV's version)."""
        raise NotImplementedError

    def object_length(self, row: dict, data_el, loaded=None) -> int:
        return len(self.object_data(row, data_el, loaded).encode())

    def object_body(self, row: dict, headers) -> str:
        """An object's text for GET."""
        return self.object_data(row, None)

    def export(self, c: dict) -> str:
        """GET on a collection: all of it as one file (handy for a browser)."""
        raise NotImplementedError

    def principal_prop(self, ctx: Ctx, name: str, ok: ET.Element) -> bool:
        """A principal property of the protocol (calendar-user-address-set, principal-address): added to `ok`, True."""
        return False

    def collection_prop(self, ctx: Ctx, c: dict, name: str, ok: ET.Element) -> bool:
        """A collection property of the app (calendar-color, supported-address-data...): added to `ok`, True."""
        return False

    def patch(self, tag: str, value: str):
        """PROPPATCH: the (field, value) a property sets on the collection, or None when it is not kept."""
        return None

    def update(self, c: dict, changes: dict) -> None:
        """All the changes of one PROPPATCH (one new sync token); Invalid when a value is not acceptable."""
        raise NotImplementedError

    def save(self, ctx: Ctx, c: dict, row: dict | None, name: str, body: bytes) -> Response:
        """PUT, its preconditions passed: parse, check (no-uid-conflict...), keep, and answer."""
        raise NotImplementedError

    def delete(self, ctx: Ctx, c: dict, row: dict) -> None:
        raise NotImplementedError

    def drop(self, c: dict) -> None:
        """DELETE on one's own private collection."""
        raise NotImplementedError

    def make(self, ctx: Ctx, slug: str, root) -> Response:
        """MKCOL (MKCALENDAR) of a new private collection; `root` is the request's XML, or None."""
        raise NotImplementedError

    def search(self, c: dict, root) -> list[dict]:
        """The query report's rows (`root` is the report)."""
        raise NotImplementedError

    def limit(self, root) -> int | None:
        """The query report's limit, if the protocol has one (CardDAV's nresults)."""
        return None

    def report(self, ctx: Ctx, c: dict, root) -> Response | None:
        """Another report on a collection (CalDAV's free-busy-query), or None."""
        return None

    # --- the routes

    def router(self, dependencies=()):
        """The routes: /dav, /dav/<anything> and /.well-known/<well_known>, open to anyone (the app's own sign-in reads
        the app password into request.state.user); `dependencies` mark them public in the app's access rules."""
        from fastapi import APIRouter
        from fastapi.concurrency import run_in_threadpool
        from fastapi.responses import RedirectResponse

        r = APIRouter()
        deps = list(dependencies)

        @r.api_route(f"/.well-known/{self.well_known}", methods=["GET", "PROPFIND", "OPTIONS", "HEAD"], include_in_schema=False, dependencies=deps)
        def well_known(request: Request):
            return RedirectResponse(prefix.of(request) + "/dav/", status_code=301)

        @r.api_route("/dav", methods=self.methods, include_in_schema=False, dependencies=deps)
        @r.api_route("/dav/{path:path}", methods=self.methods, include_in_schema=False, dependencies=deps)
        async def dav(request: Request, path: str = ""):
            if request.method == "OPTIONS":
                return Response(status_code=200, headers=options(self.classes, self.methods))
            user = request.state.user
            if not user:
                return unauthorized(self.label, self.how)
            body = await self._body(request)
            if body is None:  # a PUT larger than an object may be is refused anyway; no other request needs more
                return precondition(self.ns, "max-resource-size") if request.method == "PUT" else Response(status_code=413)
            return await run_in_threadpool(self.dispatch, Ctx(self, request, user), request.method, parts_of(request.url.path),
                                           body, request.headers)

        return r

    async def _body(self, request) -> bytes | None:
        """The request body, read up to max_bytes and never all of it into memory first; None when it is larger."""
        n = request.headers.get("content-length")
        if n and n.isdigit() and int(n) > self.max_bytes:
            return None
        out = bytearray()
        async for chunk in request.stream():
            out += chunk
            if len(out) > self.max_bytes:
                return None
        return bytes(out)

    def dispatch(self, ctx: Ctx, m: str, parts: list[str], body: bytes, headers) -> Response:
        # /dav/principals/<user>/... and /dav/<home>/<user>/... only for that user
        if len(parts) >= 2 and parts[0] in ("principals", self.home_segment) and parts[1] != ctx.user["name"]:
            return Response("Not yours", status_code=403)
        self.before(ctx)
        if m == "PROPFIND":
            return self._propfind(ctx, parts, body, (headers.get("depth") or "1").strip().lower())
        if m == "REPORT":
            return self._report(ctx, parts, body)
        if m == "PROPPATCH":
            return self._proppatch(ctx, parts, body)
        if m in ("GET", "HEAD"):
            return self._get(ctx, parts, m == "HEAD", headers)
        if m == "PUT":
            return self._put(ctx, parts, body, headers)
        if m == "DELETE":
            return self._delete(ctx, parts, headers)
        if m in ("MKCOL", "MKCALENDAR"):
            return self._mkcol(ctx, parts, body)
        return Response(status_code=405, headers=options(self.classes, self.methods))

    def _in_home(self, parts, n: int | None = None) -> bool:
        return parts[:1] == [self.home_segment] and (len(parts) == n if n is not None else len(parts) >= 3)

    # --- properties

    def _common(self, ctx: Ctx, name: str, el: ET.Element) -> bool:
        if name == q(D, "current-user-principal"):
            sub(sub(el, D, "current-user-principal"), D, "href", ctx.principal)
        elif name == q(D, "principal-URL"):
            sub(sub(el, D, "principal-URL"), D, "href", ctx.principal)
        elif name == q(self.ns, self.home_set):
            sub(sub(el, self.ns, self.home_set), D, "href", ctx.home)
        elif name == q(D, "principal-collection-set"):
            sub(sub(el, D, "principal-collection-set"), D, "href", f"{ctx.base}/principals/")
        elif name == q(D, "owner"):
            sub(sub(el, D, "owner"), D, "href", ctx.principal)
        elif name == q(D, "supported-report-set"):
            s = sub(el, D, "supported-report-set")
            for ns, r in (*self.reports, (D, "sync-collection"), (D, "principal-property-search"), (D, "expand-property")):
                sub(sub(sub(s, D, "supported-report"), D, "report"), ns, r)
        else:
            return False
        return True

    def _privs(self, el, writable: bool) -> None:
        privileges(el, writable, also=self.also_privileges)

    def props_root(self, ctx: Ctx, names):
        ok, missing = ET.Element(q(D, "prop")), []
        for n in names:
            if self._common(ctx, n, ok):
                continue
            if n == q(D, "resourcetype"):
                sub(sub(ok, D, "resourcetype"), D, "collection")
            elif n == q(D, "displayname"):
                sub(ok, D, "displayname", self.label)
            else:
                missing.append(n)
        return ok, missing

    def props_principal(self, ctx: Ctx, names):
        ok, missing = ET.Element(q(D, "prop")), []
        for n in names:
            if self._common(ctx, n, ok) or self.principal_prop(ctx, n, ok):
                continue
            if n == q(D, "resourcetype"):
                sub(sub(ok, D, "resourcetype"), D, "principal")
            elif n == q(D, "displayname"):
                sub(ok, D, "displayname", ctx.user.get("displayName") or ctx.user["name"])
            elif n in (q(D, "alternate-URI-set"), q(D, "group-membership")):
                ET.SubElement(ok, n)
            elif n == q(D, "current-user-privilege-set"):
                self._privs(ok, False)
            else:
                missing.append(n)
        return ok, missing

    def props_home(self, ctx: Ctx, names):
        ok, missing = ET.Element(q(D, "prop")), []
        for n in names:
            if self._common(ctx, n, ok):
                continue
            if n == q(D, "resourcetype"):
                sub(sub(ok, D, "resourcetype"), D, "collection")
            elif n == q(D, "displayname"):
                sub(ok, D, "displayname", self.home_name)
            elif n == q(D, "current-user-privilege-set"):
                self._privs(ok, True)
            else:
                missing.append(n)
        return ok, missing

    def sync_token(self, c: dict) -> str:
        return sync_token(self.sync_prefix, c)

    def props_collection(self, ctx: Ctx, c: dict, names):
        ok, missing = ET.Element(q(D, "prop")), []
        for n in names:
            if self._common(ctx, n, ok) or self.collection_prop(ctx, c, n, ok):
                continue
            if n == q(D, "resourcetype"):
                rt = sub(ok, D, "resourcetype")
                sub(rt, D, "collection")
                sub(rt, self.ns, self.collection_type)
            elif n == q(D, "displayname"):
                sub(ok, D, "displayname", c["name"])
            elif n == q(self.ns, self.description):
                sub(ok, self.ns, self.description, c.get("description") or "")
            elif n == q(self.ns, "max-resource-size"):
                sub(ok, self.ns, "max-resource-size", self.max_bytes)
            elif n == q(CS, "getctag"):
                sub(ok, CS, "getctag", str(c["sync_token"]))
            elif n == q(D, "sync-token"):
                sub(ok, D, "sync-token", self.sync_token(c))
            elif n == q(D, "current-user-privilege-set"):
                self._privs(ok, self.can_write(ctx.user, c))
            elif n == q(D, "getetag"):
                sub(ok, D, "getetag", f'"ctag-{c["sync_token"]}"')
            elif n == q(D, "getcontenttype"):
                sub(ok, D, "getcontenttype", "httpd/unix-directory")
            else:
                missing.append(n)
        return ok, missing

    def props_object(self, ctx: Ctx, c: dict, row: dict, names, data_el=None, loaded=None):
        ok, missing = ET.Element(q(D, "prop")), []
        for n in names:
            if n == q(D, "getetag"):
                sub(ok, D, "getetag", f'"{row["etag"]}"')
            elif n == q(D, "getcontenttype"):
                sub(ok, D, "getcontenttype", self.object_type or self.content_type)
            elif n == q(D, "resourcetype"):
                sub(ok, D, "resourcetype")
            elif n == q(D, "getlastmodified"):
                sub(ok, D, "getlastmodified", http_date(row["updated_at"]))
            elif n == q(D, "displayname"):
                sub(ok, D, "displayname", self.title(row))
            elif n == q(self.ns, self.data):
                sub(ok, self.ns, self.data, self.object_data(row, data_el, loaded))
            elif n == q(D, "getcontentlength"):
                sub(ok, D, "getcontentlength", self.object_length(row, data_el, loaded))
            elif n == q(D, "current-user-privilege-set"):
                self._privs(ok, self.can_write(ctx.user, c))
            elif n == q(D, "owner"):
                sub(sub(ok, D, "owner"), D, "href", ctx.principal)
            else:
                missing.append(n)
        return ok, missing

    def _objects(self, ctx: Ctx, ms, c: dict, rows: list[dict], names, data_el=None, since=None) -> None:
        """A multistatus response for each row (a deleted one is 404 when the client asked what changed since a token)."""
        loaded = self.preload([r for r in rows if not r["deleted"]], names)
        for row in rows:
            if row["deleted"]:
                if since is not None:
                    _not_found(ms, ctx.href(c, row))
                continue
            response(ms, ctx.href(c, row), *self.props_object(ctx, c, row, names, data_el, loaded.get(row["id"])))

    # --- methods

    def _propfind(self, ctx: Ctx, parts, body, depth) -> Response:
        mode, names = requested(body)
        ms = ET.Element(q(D, "multistatus"))
        nm = mode == "propname"

        def pick(kind):
            return self.allprop[kind] if mode != "prop" else names

        def root(href):
            response(ms, href, *self.props_root(ctx, pick("root")), names_only=nm)

        def principal():
            response(ms, ctx.principal, *self.props_principal(ctx, pick("principal")), names_only=nm)

        def home():
            response(ms, ctx.home, *self.props_home(ctx, pick("home")), names_only=nm)

        def collection(c):
            response(ms, ctx.href(c), *self.props_collection(ctx, c, pick("collection")), names_only=nm)

        def objects(c, rows):
            for row in rows:
                response(ms, ctx.href(c, row), *self.props_object(ctx, c, row, pick("object"), None, loaded.get(row["id"])), names_only=nm)

        loaded = {}
        if not parts:  # /dav/
            root(f"{ctx.base}/")
            if depth != "0":
                principal()
                home()
        elif parts[0] == "principals":
            if len(parts) > 2:
                return Response(status_code=404)
            if len(parts) == 1:
                root(f"{ctx.base}/principals/")
                if depth == "0":
                    return xml(ms)
            principal()
        elif parts[0] != self.home_segment:
            return Response(status_code=404)
        elif len(parts) == 1:
            root(f"{ctx.base}/{self.home_segment}/")
            if depth != "0":
                home()
        elif len(parts) == 2:
            home()
            if depth != "0":
                for c in self.collections(ctx.user):
                    collection(c)
        else:
            c = self.collection(ctx.user, parts[2])
            if not c:
                return Response(status_code=404)
            if len(parts) == 3:
                collection(c)
                if depth != "0":
                    rows = [r for r in self.rows(c, names=pick("object")) if not r["deleted"]]
                    loaded = self.preload(rows, pick("object"))
                    objects(c, rows)
            elif len(parts) == 4:
                row = self.by_href(c, parts[3])
                if not row or row["deleted"]:
                    return Response(status_code=404)
                objects(c, [row])
            else:
                return Response(status_code=404)
        return xml(ms)

    def _proppatch(self, ctx: Ctx, parts, body) -> Response:
        root = _xml_of(body)
        if root is None and body and body.strip():
            return Response(status_code=400)
        root = root if root is not None else ET.Element("x")
        c = self.collection(ctx.user, parts[2]) if self._in_home(parts, 3) else None
        w = bool(c) and self.can_write(ctx.user, c)
        ms = ET.Element(q(D, "multistatus"))
        r = sub(ms, D, "response")
        sub(r, D, "href", ctx.base + "/" + "/".join(quote(p) for p in parts) + "/")
        ps = sub(r, D, "propstat")
        p = sub(ps, D, "prop")
        changes: dict = {}  # all the properties in one update (one sync token for the request)
        for how in ("set", "remove"):
            for s in root.iter(q(D, how)):
                for prop in s.iter(q(D, "prop")):
                    for el in prop:
                        ET.SubElement(p, el.tag)
                        kept = self.patch(el.tag, (el.text or "").strip()) if how == "set" and w else None
                        if kept:
                            changes[kept[0]] = kept[1]
        # only who may change a collection renames or recolours it; elsewhere nothing is kept, which some clients are
        # told plainly (403) and others not (Apple Contacts sets its me-card on the home, and a refusal would nag)
        status = "200 OK" if (w or not len(p) or (c is None and self.patch_elsewhere)) else "403 Forbidden"
        if changes:
            try:
                self.update(c, changes)
            except Invalid:  # a name that is too long, a colour that is not one
                status = "409 Conflict"
        sub(ps, D, "status", f"HTTP/1.1 {status}")
        return xml(ms)

    def _get(self, ctx: Ctx, parts, head: bool, headers) -> Response:
        if not self._in_home(parts):
            return Response(self.banner, media_type="text/plain")
        c = self.collection(ctx.user, parts[2])
        if c and len(parts) == 3:
            return Response(b"" if head else self.export(c).encode(), media_type=self.content_type)
        row = self.by_href(c, parts[3]) if c and len(parts) == 4 else None
        if not row or row["deleted"]:
            return Response(status_code=404)
        return Response(b"" if head else self.object_body(row, headers).encode(), media_type=self.content_type,
                        headers={"ETag": f'"{row["etag"]}"', "Last-Modified": http_date(row["updated_at"])})

    def _put(self, ctx: Ctx, parts, body: bytes, headers) -> Response:
        if not self._in_home(parts, 4):
            return Response(status_code=405)
        c = self.collection(ctx.user, parts[2])
        if not c:
            return Response(status_code=409)
        if not self.can_write(ctx.user, c):
            return Response(status_code=403)
        row = self.by_href(c, parts[3])
        if row and row["deleted"]:
            row = None
        if headers.get("if-none-match", "").strip() == "*" and row:
            return Response(status_code=412)
        if headers.get("if-match") and (not row or not etag_match(headers.get("if-match"), row["etag"])):
            return Response(status_code=412)
        return self.save(ctx, c, row, parts[3], body)

    def conflict(self, ctx: Ctx, c: dict, row: dict | None, other: dict | None) -> Response | None:
        """no-uid-conflict (RFC 4791 5.3.2.1, RFC 6352 6.3.2.1): the same UID twice in one collection is refused, with
        the address of the other object. `other` is the object with the UID being saved, `row` the one being written."""
        if other and (not row or other["id"] != row["id"]):
            return precondition(self.ns, "no-uid-conflict", 409, ctx.href(c, other))
        return None

    def _delete(self, ctx: Ctx, parts, headers) -> Response:
        if not self._in_home(parts) or len(parts) > 4:
            return Response(status_code=403)
        c = self.collection(ctx.user, parts[2])
        if not c:
            return Response(status_code=404)
        if not self.can_write(ctx.user, c):
            return Response(status_code=403)
        if len(parts) == 3:
            if self.is_shared(c):
                return Response(f"Shared {self.plural} are deleted in the web app by an admin", status_code=403)
            if self.keep_last and len([x for x in self.collections(ctx.user) if x["owner_id"] == ctx.user["id"]]) <= 1:
                return Response(f"Your last private {self.singular} stays", status_code=403)
            self.drop(c)
            return Response(status_code=204)
        row = self.by_href(c, parts[3])
        if not row or row["deleted"]:
            return Response(status_code=404)
        if headers.get("if-match") and not etag_match(headers.get("if-match"), row["etag"]):
            return Response(status_code=412)
        self.delete(ctx, c, row)
        return Response(status_code=204)

    def _mkcol(self, ctx: Ctx, parts, body) -> Response:
        if not self._in_home(parts, 3):
            return Response(status_code=403)
        if not users.is_member(ctx.user):
            return Response(f"A viewer only looks; a member keeps {self.plural} of their own", status_code=403)
        if self.collection(ctx.user, parts[2]):
            return Response(status_code=405)
        return self.make(ctx, parts[2], _xml_of(body))

    def _report(self, ctx: Ctx, parts, body) -> Response:
        root = _xml_of(body)
        if root is None:
            return Response(status_code=400)
        ms = ET.Element(q(D, "multistatus"))
        if root.tag in (q(D, "principal-property-search"), q(D, "principal-search-property-set"), q(D, "expand-property")):
            if root.tag != q(D, "principal-search-property-set"):
                p = root.find(q(D, "prop")) if root.tag == q(D, "principal-property-search") else None
                response(ms, ctx.principal, *self.props_principal(ctx, [x.tag for x in p] if p is not None else self.allprop["principal"]))
            return xml(ms)
        if not self._in_home(parts):
            return Response(status_code=403)
        c = self.collection(ctx.user, parts[2])
        if not c:
            return Response(status_code=404)
        p = root.find(q(D, "prop"))
        names = [x.tag for x in p] if p is not None else [q(D, "getetag")]
        data_el = p.find(q(self.ns, self.data)) if p is not None else None
        if root.tag == q(self.ns, self.multiget):
            asked = [(h.text or "").strip() for h in root.findall(q(D, "href"))]
            found = [self.by_href(c, unquote(h).rstrip("/").rsplit("/", 1)[-1]) for h in asked]
            loaded = self.preload([r for r in found if r and not r["deleted"]], names)  # a phone asks for a hundred at a time
            for h, row in zip(asked, found):
                if row and not row["deleted"]:
                    response(ms, ctx.href(c, row), *self.props_object(ctx, c, row, names, data_el, loaded.get(row["id"])))
                else:
                    _not_found(ms, h)
            return xml(ms)
        if root.tag == q(self.ns, self.query):
            rows, n = self.search(c, root), self.limit(root)
            rows = rows[:n] if n else rows
            self._objects(ctx, ms, c, rows, names, data_el)
            if n and len(rows) >= n:  # there may be more (RFC 6352 8.6.1)
                r = sub(ms, D, "response")
                sub(r, D, "href", ctx.href(c))
                sub(r, D, "status", "HTTP/1.1 507 Insufficient Storage")
            return xml(ms)
        if root.tag == q(D, "sync-collection"):
            tok_el = root.find(q(D, "sync-token"))
            tok = (tok_el.text or "").strip() if tok_el is not None else ""
            since = None
            if tok:
                m = re.match(re.escape(self.sync_prefix) + r"(\d+)-(\d+)$", tok)
                if not m or int(m.group(1)) != c["id"] or int(m.group(2)) > c["sync_token"]:
                    return precondition(D, "valid-sync-token")
                since = int(m.group(2))
                if since < self.purged_before(c):  # deletions this client never heard of are gone: it starts over
                    return precondition(D, "valid-sync-token")
            cur = self.reload(c)  # read before the rows: a change in between comes again next time rather than never
            self._objects(ctx, ms, c, self.rows(c, since, names), names, data_el, since)
            sub(ms, D, "sync-token", self.sync_token(cur))
            return xml(ms)
        return self.report(ctx, c, root) or precondition(D, "supported-report")


class CalDAV(Server):
    """CalDAV (RFC 4791) for collections of one component: ioCalendar's VEVENT calendars, ioTask's VTODO lists. Every
    collection is a calendar that says which component it holds (supported-calendar-component-set), which is how Apple
    tells Reminders lists from calendars."""

    ns, ns_prefix = CALDAV, "cal"
    classes = "1, 2, 3, calendar-access, extended-mkcol"
    methods = Server.methods + ["MKCALENDAR"]
    well_known = "caldav"
    home_segment, home_set, collection_type = "calendars", "calendar-home-set", "calendar"
    description, data, multiget, query = "calendar-description", "calendar-data", "calendar-multiget", "calendar-query"
    reports = ((CALDAV, "calendar-multiget"), (CALDAV, "calendar-query"))
    content_type = "text/calendar; charset=utf-8"
    keep_last = True
    component = "VEVENT"
    placeholders: tuple = ()  # displaynames iOS gives a collection it makes when an account has none of a kind: refused

    def __init__(self):
        self.object_type = f"text/calendar; charset=utf-8; component={self.component}"
        self.allprop = {"principal": [q(D, "resourcetype"), q(D, "displayname"), q(D, "principal-URL"), q(CALDAV, "calendar-home-set"),
                                      q(CALDAV, "calendar-user-address-set")],
                        "collection": [q(D, "resourcetype"), q(D, "displayname"), q(CS, "getctag"), q(D, "sync-token"),
                                       q(CALDAV, "calendar-description"), q(CALDAV, "supported-calendar-component-set"), q(AP, "calendar-color")]}
        super().__init__()

    # --- hooks of a CalDAV app

    def timezone(self, c: dict) -> str | None:
        """calendar-timezone: the collection's zone as a VCALENDAR with its VTIMEZONE, or None."""
        return None

    def color(self, c: dict) -> str:
        """calendar-color, #RRGGBBAA."""
        return (c.get("color") or "#888888").upper() + "FF"

    def create(self, ctx: Ctx, slug: str, name: str, description: str | None, color: str | None, tz_text: str | None) -> None:
        raise NotImplementedError

    def candidates(self, c: dict, start, end) -> list[dict]:
        """The rows a calendar-query with this time range looks at (start/end may be None)."""
        return self.rows(c)

    def overlaps(self, c: dict, row: dict, start, end) -> bool:
        """Whether the object falls in the time range (either end may be open)."""
        return True

    def components(self, row: dict) -> list:
        """The object's components of this kind (the series and its changed occurrences), for prop-filters."""
        raise NotImplementedError

    # --- CalDAV itself

    def principal_prop(self, ctx: Ctx, name: str, ok) -> bool:
        if name == q(CALDAV, "calendar-user-address-set"):
            s = sub(ok, CALDAV, "calendar-user-address-set")
            if ctx.user.get("email"):
                sub(s, D, "href", f"mailto:{ctx.user['email']}")
            sub(s, D, "href", ctx.principal)
        elif name == q(CALDAV, "calendar-user-type"):
            sub(ok, CALDAV, "calendar-user-type", "INDIVIDUAL")
        elif name == q(CS, "email-address-set") and ctx.user.get("email"):
            sub(sub(ok, CS, "email-address-set"), CS, "email-address", ctx.user["email"])
        else:
            return False
        return True

    def collection_prop(self, ctx: Ctx, c: dict, name: str, ok) -> bool:
        if name == q(CALDAV, "supported-calendar-component-set"):
            sub(sub(ok, CALDAV, "supported-calendar-component-set"), CALDAV, "comp").set("name", self.component)
        elif name == q(CALDAV, "supported-calendar-data"):
            e = sub(sub(ok, CALDAV, "supported-calendar-data"), CALDAV, "calendar-data")
            e.set("content-type", "text/calendar")
            e.set("version", "2.0")
        elif name == q(CALDAV, "calendar-timezone"):
            tz = self.timezone(c)
            if not tz:
                return False
            sub(ok, CALDAV, "calendar-timezone", tz)
        elif name == q(CALDAV, "min-date-time"):
            sub(ok, CALDAV, "min-date-time", "19000101T000000Z")
        elif name == q(CALDAV, "max-date-time"):
            sub(ok, CALDAV, "max-date-time", "21991231T235959Z")
        elif name == q(AP, "calendar-color"):
            sub(ok, AP, "calendar-color", self.color(c))
        elif name == q(AP, "calendar-order"):
            sub(ok, AP, "calendar-order", c.get("position") or c["id"])
        else:
            return False
        return True

    def patch(self, tag: str, v: str):
        if tag == q(D, "displayname") and v:
            return "name", v[:128]
        if tag == q(CALDAV, "calendar-description"):
            return "description", v[:512]
        if tag == q(AP, "calendar-color"):
            return "color", v[:9]
        if tag == q(AP, "calendar-order") and v.lstrip("-").isdigit():
            return "sort", int(v)
        return None

    def object_data(self, row: dict, data_el, loaded=None) -> str:
        return row["ics"]

    def object_length(self, row: dict, data_el, loaded=None) -> int:
        return row["ics_bytes"] if "ics_bytes" in row else len(row["ics"].encode())

    def object_body(self, row: dict, headers) -> str:
        return row["ics"]

    def title(self, row: dict) -> str:
        return row["summary"]

    def rows_listing(self, names) -> bool:
        """Whether the rows can leave the objects out: no calendar-data asked for."""
        return q(CALDAV, "calendar-data") not in names

    def make(self, ctx: Ctx, slug: str, root) -> Response:
        """MKCALENDAR (RFC 4791) or extended MKCOL (RFC 5689): a new private collection. One that cannot hold this
        server's component (iOS makes a task list or a calendar when it finds an account with none) is refused."""
        found = {}
        if root is not None:
            rt = root.find(f".//{q(D, 'resourcetype')}")
            if rt is not None and rt.find(q(CALDAV, "calendar")) is None:
                return Response(f"Only {self.plural} can be made here", status_code=403)
            comps = root.find(f".//{q(CALDAV, 'supported-calendar-component-set')}")
            if comps is not None and self.component not in {(x.get("name") or "").upper() for x in comps.findall(q(CALDAV, "comp"))}:
                return precondition(CALDAV, "supported-calendar-component")
            for key, el in (("name", q(D, "displayname")), ("color", q(AP, "calendar-color")),
                            ("description", q(CALDAV, "calendar-description")), ("tz", q(CALDAV, "calendar-timezone"))):
                x = root.find(f".//{el}")
                if x is not None and (x.text or "").strip():
                    found[key] = x.text.strip()
            if found.get("name") in self.placeholders:
                return precondition(CALDAV, "supported-calendar-component")
        self.create(ctx, re.sub(r"[^A-Za-z0-9._-]", "-", slug)[:56], found.get("name", slug), found.get("description"),
                    found.get("color"), found.get("tz"))
        return Response(status_code=201)

    def search(self, c: dict, root) -> list[dict]:
        """calendar-query: VCALENDAR > component comp-filters, with a time-range and prop-filters (UID, SUMMARY, STATUS,
        COMPLETED is-not-defined...)."""
        flt = root.find(q(CALDAV, "filter"))
        vc = flt.find(q(CALDAV, "comp-filter")) if flt is not None else None
        filters = vc.findall(q(CALDAV, "comp-filter")) if vc is not None else []
        if not filters:
            return self.rows(c)
        out, seen = [], set()
        for f in filters:
            name = (f.get("name") or "").upper()
            if f.find(q(CALDAV, "is-not-defined")) is not None:
                return [] if name == self.component else self.rows(c)
            if name != self.component:
                continue  # the other components: none here
            tr = f.find(q(CALDAV, "time-range"))
            s, e = (utc(tr.get("start")), utc(tr.get("end"))) if tr is not None else (None, None)
            for row in (self.candidates(c, s, e) if (s or e) else self.rows(c)):
                if row["id"] in seen or ((s or e) and not self.overlaps(c, row, s, e)) or not self._props_match(row, f):
                    continue
                seen.add(row["id"])
                out.append(row)
        return out

    def _props_match(self, row: dict, f) -> bool:
        pfs = f.findall(q(CALDAV, "prop-filter"))
        return not pfs or any(_props_match(x, pfs) for x in self.components(row))


def utc(s: str | None):
    """A CalDAV time (20261110T100000Z, or a date) as an aware UTC datetime; None when there is none."""
    if not s:
        return None
    s = s.strip()
    for fmt, n in (("%Y%m%dT%H%M%S", 15), ("%Y%m%d", 8)):
        try:
            return dt.datetime.strptime(s[:n], fmt).replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
    return None


def text_of(v) -> str:
    """A property's text as written (CATEGORIES and the like are objects whose str() is not their text)."""
    if isinstance(v, list):
        return ",".join(text_of(x) for x in v)
    raw = v.to_ical() if hasattr(v, "to_ical") else v
    return raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)


def _props_match(comp, pfs) -> bool:
    """Whether one component passes every prop-filter: is-not-defined, or a text-match (contains, equals, starts-with,
    ends-with, negated or not)."""
    for pf in pfs:
        v = comp.get((pf.get("name") or "").upper())
        if pf.find(q(CALDAV, "is-not-defined")) is not None:
            if v is not None:
                return False
            continue
        if v is None:
            return False
        tm = pf.find(q(CALDAV, "text-match"))
        if tm is not None:
            needle, hay, kind = (tm.text or "").lower(), text_of(v).lower(), tm.get("match-type", "contains")
            hit = (hay == needle if kind == "equals" else hay.startswith(needle) if kind == "starts-with"
                   else hay.endswith(needle) if kind == "ends-with" else needle in hay)
            if (tm.get("negate-condition") == "yes") == hit:
                return False
    return True
