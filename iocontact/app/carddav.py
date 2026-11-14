"""CardDAV (RFC 6352) on WebDAV (RFC 4918), with sync-collection (RFC 6578), getctag and current-user-principal
discovery (RFC 5397, RFC 6764 /.well-known/carddav), so Apple Contacts, iOS, DAVx5, Thunderbird, Evolution and
others find the address books from just the server address, a user name and a password (or an app password).

    /dav/                                         root: points to the principal
    /dav/principals/<user>/                       the principal: points to the address book home
    /dav/addressbooks/<user>/                     home: one collection per address book the user can see
    /dav/addressbooks/<user>/<slug>/              an address book (Family, Personal, ...)
    /dav/addressbooks/<user>/<slug>/<name>.vcf    a contact

The server itself is the suite's (iosuite_shared.dav.Server); what is here is what an address book and a card are:
vCard 3.0 or 4.0, cards read many at a time, what a PUT keeps, and addressbook-query's filters.
"""
import re

from fastapi.responses import Response
from iosuite_shared import dav as webdav
from iosuite_shared.dav import AP, CARDDAV as C, D, q
from iosuite_shared.errors import Invalid

from app import access, db, model, vcard
from app.fold import fold

DATA_PROPS = (q(C, "address-data"), q(D, "getcontentlength"))  # the properties that need the whole card


def _rows(book_id: int, since: int | None = None) -> list[dict]:
    if since is None:
        return db.q("SELECT * FROM con_contacts WHERE address_book_id = %s AND deleted = 0 ORDER BY id", (book_id,))
    return db.q("SELECT * FROM con_contacts WHERE address_book_id = %s AND changed_token > %s ORDER BY changed_token", (book_id, since))


def _version(el) -> str:
    """The vCard version a client asks for in its address-data element: 4.0, or 3.0 (what every client reads)."""
    return "4.0" if el is not None and (el.get("version") or "").startswith("4") else "3.0"


class AddressBooks(webdav.Server):
    label = "ioContact"
    how = "password (or an app password)"
    ns, ns_prefix = C, "card"
    classes = "1, 2, 3, addressbook, extended-mkcol"
    well_known = "carddav"
    home_segment, home_set, home_name = "addressbooks", "addressbook-home-set", "Address books"
    collection_type, description, data = "addressbook", "addressbook-description", "address-data"
    multiget, query = "addressbook-multiget", "addressbook-query"
    reports = ((C, "addressbook-multiget"), (C, "addressbook-query"))
    content_type = "text/vcard; charset=utf-8"
    sync_prefix = "urn:x-iocontact:sync:"
    max_bytes = 4 * 1024 * 1024
    plural, singular = "address books", "address book"
    patch_elsewhere = True
    banner = "ioContact CardDAV server. Point your contacts app at this address."
    allprop = {"collection": [q(D, "resourcetype"), q(D, "displayname"), q(webdav.CS, "getctag"), q(D, "sync-token"),
                              q(C, "addressbook-description"), q(C, "supported-address-data")]}

    def collections(self, user):
        return model.books_for(user)

    def collection(self, user, slug):
        return model.book_by_slug(user, slug)

    def reload(self, b):
        return model.book(b["id"])

    def can_write(self, user, b):
        return model.can_write_book(user, b)

    def rows(self, b, since=None, names=()):
        return _rows(b["id"], since)

    def by_href(self, b, name):
        return model.by_href(b["id"], name)

    def purged_before(self, b):
        return model.purged_before(b["id"])

    def preload(self, rows, names):
        """The whole contacts of a listing or report, read in one go, when the properties asked for need the cards."""
        return model.full_many(rows, with_photo=True) if any(n in DATA_PROPS for n in names) else {}

    def title(self, row):
        return row["fn"]

    def object_data(self, row, data_el, loaded=None):
        return model.vcard_text(row, _version(data_el), loaded)

    def object_body(self, row, headers):
        return model.vcard_text(row, "4.0" if re.search(r"version\s*=\s*\"?4", headers.get("accept", "")) else "3.0")

    def export(self, b):
        return "".join(model.vcard_text(c["id"], "3.0", c) for c in model.full_many(_rows(b["id"]), with_photo=True).values())

    def principal_prop(self, ctx, name, ok):
        if name != q(C, "principal-address"):
            return False
        me = model.get_row(ctx.user["me_contact_id"]) if ctx.user.get("me_contact_id") else None
        b = model.book(me["address_book_id"]) if me else None
        if not me or me["deleted"] or not model.can_read_book(ctx.user, b):
            return False
        webdav.sub(webdav.sub(ok, C, "principal-address"), D, "href", ctx.href(b, me))
        return True

    def collection_prop(self, ctx, b, name, ok):
        if name == q(C, "supported-address-data"):
            s = webdav.sub(ok, C, "supported-address-data")
            for v in ("3.0", "4.0"):
                e = webdav.sub(s, C, "address-data-type")
                e.set("content-type", "text/vcard")
                e.set("version", v)
        elif name == q(AP, "calendar-color") and b.get("color"):
            webdav.sub(ok, AP, "calendar-color", b["color"])
        else:
            return False
        return True

    def patch(self, tag, v):
        if tag == q(D, "displayname") and v:
            return "name", v
        if tag == q(C, "addressbook-description"):
            return "description", v
        if tag == q(AP, "calendar-color"):
            return "color", v
        return None

    def update(self, b, changes):
        model.update_book(b["id"], **changes)  # Invalid for a name that is too long, a colour that is not one

    def save(self, ctx, b, row, name, body):
        try:
            cards = vcard.parse(body.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            cards = []
        if len(cards) != 1:
            return webdav.precondition(C, "valid-address-data", 400 if not cards else 403)
        c = cards[0]
        if not c.get("uid"):
            c["uid"] = name.rsplit(".", 1)[0]
        refused = self.conflict(ctx, b, row, model.by_uid(b["id"], c["uid"]))
        if refused:
            return refused
        if c.get("iopix") is None:
            c.pop("iopix", None)  # a client that drops X-IOPIX-PERSON does not unlink the person
        if row:  # favorites are ioContact's own: a client that drops the mark does not unfavorite
            c["favorite"] = c.get("favorite") or bool(row["favorite"])
        model.save(b["id"], c, row["id"] if row else None, name, resolve_book_ids=[x["id"] for x in model.books_for(ctx.user)])
        new = model.by_href(b["id"], name)
        return Response(status_code=204 if row else 201, headers={"ETag": f'"{new["etag"]}"'} if new else {})

    def delete(self, ctx, b, row):
        model.delete(row["id"])

    def drop(self, b):
        model.delete_book(b["id"])

    def make(self, ctx, slug, root):
        """Extended MKCOL (RFC 5689), or a plain one: a new private address book."""
        dn = root.find(f".//{q(D, 'displayname')}") if root is not None else None
        name = dn.text.strip() if dn is not None and (dn.text or "").strip() else slug
        try:
            model.create_book(ctx.user["id"], name[:128], slug=slug)
        except Invalid as e:  # an address that is not plain, a name that is none
            return Response(str(e), status_code=403)
        return Response(status_code=201)

    def search(self, b, root):
        rows = _rows(b["id"])
        flt = root.find(q(C, "filter"))
        if flt is not None and len(flt):  # the filter reads the cards (without their photos), all at once
            plain = model.full_many(rows)
            rows = [row for row in rows if _matches(plain[row["id"]], flt)]
        return rows

    def limit(self, root):
        lim = root.find(f"{q(C, 'limit')}/{q(C, 'nresults')}")
        return int(lim.text) if lim is not None and (lim.text or "").isdigit() else None


def _matches(contact: dict, flt) -> bool:
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


router = AddressBooks().router([access.public])
