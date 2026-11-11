"""CardDAV (RFC 6352) on WebDAV (RFC 4918), with sync-collection (RFC 6578), getctag and current-user-principal
discovery (RFC 5397, RFC 6764 /.well-known/carddav), so Apple Contacts, iOS, DAVx5, Thunderbird, Evolution and
others find the address books from just the server address, a user name and a password (or an app password).

    /dav/                                         root: points to the principal
    /dav/principals/<user>/                       the principal: points to the address book home
    /dav/addressbooks/<user>/                     home: one collection per address book the user can see
    /dav/addressbooks/<user>/<slug>/              an address book (Family, Personal, ...)
    /dav/addressbooks/<user>/<slug>/<name>.vcf    a contact
"""
import re
import xml.etree.ElementTree as ET

from defusedxml import DefusedXmlException
from defusedxml.ElementTree import fromstring as parse_xml  # a client's XML: no entity expansion or external entities
from urllib.parse import quote, unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response
from iosuite_shared import dav as webdav  # `dav` is the route below
from iosuite_shared import users as shared_users
from iosuite_shared.dav import AP, CS, D, q
from iosuite_shared.errors import Invalid

from app import access, db, limits, model, vcard
from app.fold import fold

# the WebDAV plumbing ioCalendar and ioContacts share (iosuite_shared.dav), under the names this module uses
_xml, _sub, _requested, _response, _parse, _etag_match, _http_date = webdav.xml, webdav.sub, webdav.requested, webdav.response, webdav.parts_of, webdav.etag_match, webdav.http_date
_privs = webdav.privileges

router = APIRouter()

C = "urn:ietf:params:xml:ns:carddav"
for pfx, ns in (("d", D), ("card", C), ("cs", CS), ("ap", AP)):
    ET.register_namespace(pfx, ns)
METHODS = ["OPTIONS", "PROPFIND", "PROPPATCH", "REPORT", "GET", "HEAD", "PUT", "DELETE", "MKCOL", "MOVE", "COPY"]
SYNC_PREFIX = "urn:x-iocontacts:sync:"
MAX_SIZE = 4 * 1024 * 1024


def _unauth() -> Response:
    return webdav.unauthorized("ioContacts", "password (or an app password)")


def _opts_headers() -> dict:
    return webdav.options("1, 2, 3, addressbook, extended-mkcol", METHODS)


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
        return f"{self.base}/addressbooks/{self.uname}/"

    def book_href(self, b):
        return f"{self.home}{quote(b['slug'])}/"


def _common(ctx: Ctx, name: str, el: ET.Element) -> bool:
    if name == q(D, "current-user-principal"):
        _sub(_sub(el, D, "current-user-principal"), D, "href", ctx.principal)
    elif name == q(D, "principal-URL"):
        _sub(_sub(el, D, "principal-URL"), D, "href", ctx.principal)
    elif name == q(C, "addressbook-home-set"):
        _sub(_sub(el, C, "addressbook-home-set"), D, "href", ctx.home)
    elif name == q(D, "principal-collection-set"):
        _sub(_sub(el, D, "principal-collection-set"), D, "href", f"{ctx.base}/principals/")
    elif name == q(D, "owner"):
        _sub(_sub(el, D, "owner"), D, "href", ctx.principal)
    elif name == q(D, "supported-report-set"):
        s = _sub(el, D, "supported-report-set")
        for ns, r in ((C, "addressbook-multiget"), (C, "addressbook-query"), (D, "sync-collection"), (D, "principal-property-search"),
                      (D, "expand-property")):
            _sub(_sub(_sub(s, D, "supported-report"), D, "report"), ns, r)
    else:
        return False
    return True


def props_root(ctx: Ctx, names: list[str]) -> tuple[ET.Element, list[str]]:
    ok, missing = ET.Element(q(D, "prop")), []
    for n in names:
        if _common(ctx, n, ok):
            continue
        if n == q(D, "resourcetype"):
            _sub(_sub(ok, D, "resourcetype"), D, "collection")
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", "ioContacts")
        else:
            missing.append(n)
    return ok, missing


def props_principal(ctx: Ctx, names: list[str]):
    ok, missing = ET.Element(q(D, "prop")), []
    for n in names:
        if _common(ctx, n, ok):
            continue
        if n == q(D, "resourcetype"):
            rt = _sub(ok, D, "resourcetype")
            _sub(rt, D, "principal")
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", ctx.user.get("display_name") or ctx.user["name"])
        elif n == q(C, "principal-address"):
            if ctx.user.get("me_contact_id"):
                r = model.get_row(ctx.user["me_contact_id"])
                b = model.book(r["address_book_id"]) if r else None
                if r and not r["deleted"] and model.can_read_book(ctx.user, b):
                    _sub(_sub(ok, C, "principal-address"), D, "href", ctx.book_href(b) + quote(r["href"]))
                    continue
            missing.append(n)
        elif n == q(D, "alternate-URI-set"):
            _sub(ok, D, "alternate-URI-set")
        elif n == q(D, "group-membership"):
            _sub(ok, D, "group-membership")
        elif n == q(D, "calendar-user-address-set") or n == "{urn:ietf:params:xml:ns:caldav}calendar-user-address-set":
            missing.append(n)
        elif n == q(D, "current-user-privilege-set"):
            _privs(ok, False)
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
            _sub(ok, D, "displayname", "Address books")
        elif n == q(D, "current-user-privilege-set"):
            _privs(ok, True)
        else:
            missing.append(n)
    return ok, missing


def sync_token(b) -> str:
    return webdav.sync_token(SYNC_PREFIX, b)


def props_book(ctx: Ctx, b: dict, names: list[str]):
    ok, missing = ET.Element(q(D, "prop")), []
    w = model.can_write_book(ctx.user, b)
    for n in names:
        if _common(ctx, n, ok):
            continue
        if n == q(D, "resourcetype"):
            rt = _sub(ok, D, "resourcetype")
            _sub(rt, D, "collection")
            _sub(rt, C, "addressbook")
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", b["name"])
        elif n == q(C, "addressbook-description"):
            _sub(ok, C, "addressbook-description", b.get("description") or "")
        elif n == q(CS, "getctag"):
            _sub(ok, CS, "getctag", str(b["sync_token"]))
        elif n == q(D, "sync-token"):
            _sub(ok, D, "sync-token", sync_token(b))
        elif n == q(C, "supported-address-data"):
            s = _sub(ok, C, "supported-address-data")
            for v in ("3.0", "4.0"):
                e = _sub(s, C, "address-data-type")
                e.set("content-type", "text/vcard")
                e.set("version", v)
        elif n == q(C, "max-resource-size"):
            _sub(ok, C, "max-resource-size", MAX_SIZE)
        elif n == q(D, "current-user-privilege-set"):
            _privs(ok, w)
        elif n == q(D, "getetag"):
            _sub(ok, D, "getetag", f'"ctag-{b["sync_token"]}"')
        elif n == q(AP, "calendar-color") and b.get("color"):
            _sub(ok, AP, "calendar-color", b["color"])
        elif n == q(D, "getcontenttype"):
            _sub(ok, D, "getcontenttype", "httpd/unix-directory")
        else:
            missing.append(n)
    return ok, missing


DATA_PROPS = (q(C, "address-data"), q(D, "getcontentlength"))  # the properties that need the whole card


def _loaded(rows: list[dict], names: list[str]) -> dict:
    """{id: the whole contact} for the rows of a listing or report, read in one go (model.full_many), when the
    properties asked for need the card itself; {} when etags and names are enough."""
    return model.full_many(rows, with_photo=True) if any(n in DATA_PROPS for n in names) else {}


def props_card(ctx: Ctx, row: dict, names: list[str], data_version: str | None = None, loaded: dict | None = None):
    """`loaded`: the row's full() dict when the caller read a whole listing at once (_loaded)."""
    ok, missing = ET.Element(q(D, "prop")), []
    for n in names:
        if n == q(D, "getetag"):
            _sub(ok, D, "getetag", f'"{row["etag"]}"')
        elif n == q(D, "getcontenttype"):
            _sub(ok, D, "getcontenttype", "text/vcard; charset=utf-8")
        elif n == q(D, "resourcetype"):
            _sub(ok, D, "resourcetype")
        elif n == q(D, "getlastmodified"):
            _sub(ok, D, "getlastmodified", _http_date(row["updated_at"]))
        elif n == q(D, "displayname"):
            _sub(ok, D, "displayname", row["fn"])
        elif n == q(C, "address-data"):
            _sub(ok, C, "address-data", model.vcard_text(row, data_version or "3.0", loaded))
        elif n == q(D, "getcontentlength"):
            _sub(ok, D, "getcontentlength", len(model.vcard_text(row, data_version or "3.0", loaded).encode()))
        elif n == q(D, "current-user-privilege-set"):
            _privs(ok, model.can_write_book(ctx.user, model.book(row["address_book_id"])))
        elif n == q(D, "owner"):
            _sub(_sub(ok, D, "owner"), D, "href", ctx.principal)
        else:
            missing.append(n)
    return ok, missing


ALLPROP = {
    "root": [q(D, "resourcetype"), q(D, "displayname"), q(D, "current-user-principal")],
    "principal": [q(D, "resourcetype"), q(D, "displayname"), q(D, "principal-URL"), q(C, "addressbook-home-set")],
    "home": [q(D, "resourcetype"), q(D, "displayname")],
    "book": [q(D, "resourcetype"), q(D, "displayname"), q(CS, "getctag"), q(D, "sync-token"), q(C, "addressbook-description"),
             q(C, "supported-address-data")],
    "card": [q(D, "resourcetype"), q(D, "getetag"), q(D, "getcontenttype"), q(D, "getlastmodified"), q(D, "getcontentlength")],
}


# ------------------------------------------------------------------ resolving paths

def _book(ctx: Ctx, slug: str):
    return model.book_by_slug(ctx.user, slug)


def _version(el: ET.Element | None) -> str:
    if el is None:
        return "3.0"
    v = el.get("version") or ""
    ct = el.get("content-type") or ""
    return "4.0" if v.startswith("4") else "3.0" if v or ct else "3.0"


# ------------------------------------------------------------------ the handler

@router.api_route("/.well-known/carddav", methods=["GET", "PROPFIND", "OPTIONS", "HEAD"], include_in_schema=False, dependencies=[access.public])
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
    try:
        body = await limits.body(request)
    except HTTPException:
        return Response("Too large", status_code=413)
    m = request.method
    return await run_in_threadpool(_dispatch, ctx, m, parts, body, request.headers)


def _dispatch(ctx: Ctx, m: str, parts: list[str], body: bytes, headers) -> Response:
    # who: /dav/principals/<user>/... and /dav/addressbooks/<user>/... only for that user
    if len(parts) >= 2 and parts[0] in ("principals", "addressbooks") and parts[1] != ctx.user["name"]:
        return Response("Not yours", status_code=403)
    depth = (headers.get("depth") or "1").strip().lower()
    if m == "PROPFIND":
        return _propfind(ctx, parts, body, depth)
    if m == "REPORT":
        return _report(ctx, parts, body)
    if m == "PROPPATCH":
        return _proppatch(ctx, parts, body)
    if m in ("GET", "HEAD"):
        return _get(ctx, parts, m == "HEAD", headers)
    if m == "PUT":
        return _put(ctx, parts, body, headers)
    if m == "DELETE":
        return _delete(ctx, parts, headers)
    if m == "MKCOL":
        return _mkcol(ctx, parts, body)
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
        _response(ms, ctx.principal, *props_principal(ctx, pick("principal")), names_only=nm)
        return _xml(ms)
    if parts[0] != "addressbooks":
        return Response(status_code=404)
    if len(parts) == 1:
        _response(ms, f"{ctx.base}/addressbooks/", *props_root(ctx, pick("root")), names_only=nm)
        if depth != "0":
            _response(ms, ctx.home, *props_home(ctx, pick("home")), names_only=nm)
        return _xml(ms)
    if len(parts) == 2:
        _response(ms, ctx.home, *props_home(ctx, pick("home")), names_only=nm)
        if depth != "0":
            for b in model.books_for(ctx.user):
                _response(ms, ctx.book_href(b), *props_book(ctx, b, pick("book")), names_only=nm)
        return _xml(ms)
    b = _book(ctx, parts[2])
    if not b:
        return Response(status_code=404)
    if len(parts) == 3:
        _response(ms, ctx.book_href(b), *props_book(ctx, b, pick("book")), names_only=nm)
        if depth != "0":
            rows = _rows(b["id"])
            loaded = _loaded(rows, pick("card"))
            for row in rows:
                _response(ms, ctx.book_href(b) + quote(row["href"]), *props_card(ctx, row, pick("card"), loaded=loaded.get(row["id"])), names_only=nm)
        return _xml(ms)
    row = model.by_href(b["id"], parts[3])
    if not row or row["deleted"]:
        return Response(status_code=404)
    _response(ms, ctx.book_href(b) + quote(row["href"]), *props_card(ctx, row, pick("card")), names_only=nm)
    return _xml(ms)


def _rows(book_id: int, since: int | None = None) -> list[dict]:
    if since is None:
        return db.q("SELECT * FROM con_contacts WHERE address_book_id = %s AND deleted = 0 ORDER BY id", (book_id,))
    return db.q("SELECT * FROM con_contacts WHERE address_book_id = %s AND changed_token > %s ORDER BY changed_token", (book_id, since))


def _proppatch(ctx: Ctx, parts, body) -> Response:
    ms = ET.Element(q(D, "multistatus"))
    try:
        root = parse_xml(body or b"<x/>")
    except (ET.ParseError, DefusedXmlException):
        return Response(status_code=400)
    b = _book(ctx, parts[2]) if len(parts) == 3 and parts[0] == "addressbooks" else None
    r = _sub(ms, D, "response")
    _sub(r, D, "href", "/dav/" + "/".join(quote(p) for p in parts) + "/")
    ps = _sub(r, D, "propstat")
    p = _sub(ps, D, "prop")
    changes = {}
    for s in root.iter(q(D, "set")):
        for prop in s.iter(q(D, "prop")):
            for c in prop:
                ET.SubElement(p, c.tag)
                if c.tag == q(D, "displayname") and (c.text or "").strip():
                    changes["name"] = c.text
                elif c.tag == q(C, "addressbook-description"):
                    changes["description"] = c.text
                elif c.tag == q(AP, "calendar-color"):
                    changes["color"] = c.text
    for s in root.iter(q(D, "remove")):
        for prop in s.iter(q(D, "prop")):
            for c in prop:
                ET.SubElement(p, c.tag)
    if b and not model.can_write_book(ctx.user, b):
        _sub(ps, D, "status", "HTTP/1.1 403 Forbidden")  # only an editor renames or recolours a shared book
        return _xml(ms)
    if b and changes:
        try:
            model.update_book(b["id"], **changes)  # one change, one new sync token
        except Invalid:  # a name that is too long, a colour that is not one
            _sub(ps, D, "status", "HTTP/1.1 409 Conflict")
            return _xml(ms)
    _sub(ps, D, "status", "HTTP/1.1 200 OK")
    return _xml(ms)


def _get(ctx: Ctx, parts, head: bool, headers) -> Response:
    if len(parts) < 4 or parts[0] != "addressbooks":
        if len(parts) == 3 and parts[0] == "addressbooks":
            # GET on a collection: the whole address book as one .vcf (handy for a browser)
            b = _book(ctx, parts[2])
            if not b:
                return Response(status_code=404)
            text = "".join(model.vcard_text(c["id"], "3.0", c) for c in model.full_many(_rows(b["id"]), with_photo=True).values())
            return Response(b"" if head else text.encode(), media_type="text/vcard; charset=utf-8")
        return Response("ioContacts CardDAV server. Point your contacts app at this address.", media_type="text/plain")
    b = _book(ctx, parts[2])
    row = model.by_href(b["id"], parts[3]) if b else None
    if not row or row["deleted"]:
        return Response(status_code=404)
    acc = headers.get("accept", "")
    v = "4.0" if re.search(r"version\s*=\s*\"?4", acc) else "3.0"
    text = model.vcard_text(row, v).encode()
    return Response(b"" if head else text, media_type="text/vcard; charset=utf-8",
                    headers={"ETag": f'"{row["etag"]}"', "Last-Modified": _http_date(row["updated_at"])})


def _put(ctx: Ctx, parts, body: bytes, headers) -> Response:
    if len(parts) != 4 or parts[0] != "addressbooks":
        return Response(status_code=405)
    b = _book(ctx, parts[2])
    if not b:
        return Response(status_code=409)
    if not model.can_write_book(ctx.user, b):
        return Response(status_code=403)
    if len(body) > MAX_SIZE:
        return Response(status_code=413)
    row = model.by_href(b["id"], parts[3])
    if row and row["deleted"]:
        row = None
    if headers.get("if-none-match", "").strip() == "*" and row:
        return Response(status_code=412)
    if headers.get("if-match") and (not row or not _etag_match(headers.get("if-match"), row["etag"])):
        return Response(status_code=412)
    try:
        cards = vcard.parse(body.decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        cards = []
    if len(cards) != 1:
        return webdav.precondition(C, "valid-address-data", 400 if not cards else 403)
    c = cards[0]
    if not c.get("uid"):
        c["uid"] = parts[3].rsplit(".", 1)[0]
    # the same UID twice in one address book is refused (RFC 6352 6.3.2.1 no-uid-conflict)
    other = model.by_uid(b["id"], c["uid"])
    if other and (not row or other["id"] != row["id"]):
        return webdav.precondition(C, "no-uid-conflict", 409, ctx.book_href(b) + quote(other["href"]))
    if c.get("iopix") is None:
        c.pop("iopix", None)  # a client that drops X-IOPIX-PERSON does not unlink the person
    if row:  # favorites are ioContacts' own: a client that drops the mark does not unfavorite
        c["favorite"] = c.get("favorite") or bool(row["favorite"])
    ids = [x["id"] for x in model.books_for(ctx.user)]
    model.save(b["id"], c, row["id"] if row else None, parts[3], resolve_book_ids=ids)
    new = model.by_href(b["id"], parts[3])
    return Response(status_code=204 if row else 201, headers={"ETag": f'"{new["etag"]}"'} if new else {})


def _delete(ctx: Ctx, parts, headers) -> Response:
    if parts[:1] != ["addressbooks"] or len(parts) < 3:
        return Response(status_code=403)
    b = _book(ctx, parts[2])
    if not b:
        return Response(status_code=404)
    if not model.can_write_book(ctx.user, b):
        return Response(status_code=403)
    if len(parts) == 3:
        if b["owner_id"] is None:
            return Response("Shared address books are deleted in the web app by an admin", status_code=403)
        model.delete_book(b["id"])
        return Response(status_code=204)
    row = model.by_href(b["id"], parts[3])
    if not row or row["deleted"]:
        return Response(status_code=404)
    if headers.get("if-match") and not _etag_match(headers.get("if-match"), row["etag"]):
        return Response(status_code=412)
    model.delete(row["id"])
    return Response(status_code=204)


def _mkcol(ctx: Ctx, parts, body) -> Response:
    """Extended MKCOL (RFC 5689): a client making a new private address book (members and more)."""
    if len(parts) != 3 or parts[0] != "addressbooks":
        return Response(status_code=403)
    if not shared_users.is_member(ctx.user):
        return Response("A viewer only looks; a member keeps address books of their own", status_code=403)
    if _book(ctx, parts[2]):
        return Response(status_code=405)
    name = parts[2]
    try:
        root = parse_xml(body) if body else None
        dn = root.find(f".//{q(D, 'displayname')}") if root is not None else None
        if dn is not None and (dn.text or "").strip():
            name = dn.text.strip()
    except (ET.ParseError, DefusedXmlException):
        pass
    try:
        model.create_book(ctx.user["id"], name[:128], slug=parts[2])
    except Invalid as e:  # an address that is not plain, a name that is none
        return Response(str(e), status_code=403)
    return Response(status_code=201)


# ------------------------------------------------------------------ REPORT

def _report(ctx: Ctx, parts, body) -> Response:
    try:
        root = parse_xml(body)
    except (ET.ParseError, DefusedXmlException):
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
    if len(parts) < 3 or parts[0] != "addressbooks":
        return Response(status_code=403)
    b = _book(ctx, parts[2])
    if not b:
        return Response(status_code=404)
    p = root.find(q(D, "prop"))
    names = [c.tag for c in p] if p is not None else [q(D, "getetag")]
    ad = p.find(q(C, "address-data")) if p is not None else None
    version = _version(ad)
    ms = ET.Element(q(D, "multistatus"))
    if tag == q(C, "addressbook-multiget"):
        asked = [(h.text or "").strip() for h in root.findall(q(D, "href"))]
        found = [model.by_href(b["id"], unquote(h).rstrip("/").rsplit("/", 1)[-1]) for h in asked]
        loaded = _loaded([r for r in found if r], names)  # a phone asks for a hundred cards at a time: read together
        for h, row in zip(asked, found):
            if row and not row["deleted"]:
                _response(ms, ctx.book_href(b) + quote(row["href"]), *props_card(ctx, row, names, version, loaded.get(row["id"])))
            else:
                r = _sub(ms, D, "response")
                _sub(r, D, "href", h)
                _sub(r, D, "status", "HTTP/1.1 404 Not Found")
        return _xml(ms)
    if tag == q(C, "addressbook-query"):
        flt = root.find(q(C, "filter"))
        lim = root.find(f"{q(C, 'limit')}/{q(C, 'nresults')}")
        n = int(lim.text) if lim is not None and (lim.text or "").isdigit() else None
        rows = _rows(b["id"])
        if flt is not None and len(flt):  # the filter reads the cards (without their photos), all at once
            plain = model.full_many(rows)
            rows = [row for row in rows if _matches(plain[row["id"]], flt)]
        rows = rows[:n] if n else rows
        loaded = _loaded(rows, names)
        for row in rows:
            _response(ms, ctx.book_href(b) + quote(row["href"]), *props_card(ctx, row, names, version, loaded.get(row["id"])))
        if n and len(rows) >= n:
            r = _sub(ms, D, "response")
            _sub(r, D, "href", ctx.book_href(b))
            _sub(r, D, "status", "HTTP/1.1 507 Insufficient Storage")
        return _xml(ms)
    if tag == q(D, "sync-collection"):
        tok_el = root.find(q(D, "sync-token"))
        tok = (tok_el.text or "").strip() if tok_el is not None else ""
        since = None
        if tok:
            m = re.match(re.escape(SYNC_PREFIX) + r"(\d+)-(\d+)$", tok)
            if not m or int(m.group(1)) != b["id"] or int(m.group(2)) > b["sync_token"]:
                return webdav.precondition(D, "valid-sync-token")
            since = int(m.group(2))
            if since < model.purged_before(b["id"]):  # deletions since then are no longer on record: start over
                return webdav.precondition(D, "valid-sync-token")
        rows = _rows(b["id"], since)
        cur = model.book(b["id"])
        loaded = _loaded(rows, names)
        for row in rows:
            href = ctx.book_href(b) + quote(row["href"])
            if row["deleted"]:
                if since is None:
                    continue
                r = _sub(ms, D, "response")
                _sub(r, D, "href", href)
                _sub(r, D, "status", "HTTP/1.1 404 Not Found")
            else:
                _response(ms, href, *props_card(ctx, row, names, version, loaded.get(row["id"])))
        _sub(ms, D, "sync-token", sync_token(cur))
        return _xml(ms)
    return Response(status_code=403)


def _matches(contact: dict, flt: ET.Element) -> bool:
    """addressbook-query filters: prop-filter with text-match (contains, equals, starts-with, ends-with), is-not-defined.
    `contact` is a full() dict."""
    test_all = flt.get("test", "anyof") == "allof"
    props = vcard.parse_many(vcard.from_contact(contact, "3.0"))[0]
    results = []
    for pf in flt.findall(q(C, "prop-filter")):
        name = (pf.get("name") or "").upper()
        values = [vcard.unescape(p.value) for p in props if p.name == name]
        if pf.find(q(C, "is-not-defined")) is not None:
            results.append(not values)
            continue
        tms = pf.findall(q(C, "text-match"))
        if not tms:
            results.append(bool(values))
            continue
        pf_all = pf.get("test", "anyof") == "allof"
        sub = []
        for tm in tms:
            needle = fold(tm.text)
            how = tm.get("match-type", "contains")
            neg = tm.get("negate-condition") == "yes"
            hit = any((needle in v) if how == "contains" else (v == needle) if how == "equals" else
                      v.startswith(needle) if how == "starts-with" else v.endswith(needle) for v in map(fold, values))
            sub.append(hit != neg)
        results.append(all(sub) if pf_all else any(sub))
    return all(results) if test_all else any(results)

