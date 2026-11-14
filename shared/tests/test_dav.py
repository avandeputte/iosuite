"""The WebDAV server ioCalendar, ioTask and ioContact share (iosuite_shared.dav): its plumbing, and the server itself."""
import datetime as dt
import xml.etree.ElementTree as ET

from iosuite_shared import dav

C = "urn:ietf:params:xml:ns:caldav"


def test_a_propfind_body_is_read_without_trusting_it():
    assert dav.requested(b"") == ("allprop", []) and dav.requested(b"  ") == ("allprop", []) and dav.requested(b"<not xml") == ("allprop", [])
    assert dav.requested(b'<d:propfind xmlns:d="DAV:"><d:propname/></d:propfind>') == ("propname", [])
    assert dav.requested(b'<d:propfind xmlns:d="DAV:"><d:prop><d:getetag/><d:displayname/></d:prop></d:propfind>') == ("prop", ["{DAV:}getetag", "{DAV:}displayname"])
    bomb = b'<!DOCTYPE x [<!ENTITY a "aaaa">]><d:propfind xmlns:d="DAV:"><d:prop><d:getetag>&a;</d:getetag></d:prop></d:propfind>'
    assert dav.requested(bomb) == ("allprop", [])  # entities are refused, not expanded


def test_a_multistatus_response_separates_found_and_missing():
    ms = ET.Element(dav.q(dav.D, "multistatus"))
    ok = ET.Element(dav.q(dav.D, "prop"))
    dav.sub(ok, dav.D, "getetag", '"abc"')
    dav.response(ms, "/dav/x/1.ics", ok, [dav.q(C, "calendar-data")])
    r = dav.xml(ms)
    text = r.body.decode()
    assert r.status_code == 207 and r.media_type.startswith("application/xml")
    assert text.count("propstat>") == 4 and "200 OK" in text and "404 Not Found" in text and "/dav/x/1.ics" in text
    names = ET.Element(dav.q(dav.D, "prop"))
    dav.sub(names, dav.D, "getetag", '"abc"')
    dav.response(ET.Element("x"), "/dav/x/", names, [], names_only=True)
    assert names[0].text is None


def test_privileges_preconditions_and_headers():
    el = ET.Element("x")
    dav.privileges(el, False, also=[(C, "read-free-busy")])
    assert [p[0].tag for p in el[0]] == [dav.q(dav.D, "read"), dav.q(dav.D, "read-acl"), dav.q(dav.D, "read-current-user-privilege-set"), dav.q(C, "read-free-busy")]
    el = ET.Element("x")
    dav.privileges(el, True)
    assert dav.q(dav.D, "write-content") in [p[0].tag for p in el[0]] and len(el[0]) == 9
    r = dav.precondition(C, "no-uid-conflict", 409, "/dav/x/2.ics")
    assert r.status_code == 409 and b"no-uid-conflict" in r.body and b"/dav/x/2.ics" in r.body
    assert dav.precondition(dav.D, "valid-sync-token").status_code == 403
    assert dav.etag_match(None, "a") and dav.etag_match('"a", "b"', "b") and dav.etag_match("*", None) and dav.etag_match('W/"a"', "a")
    assert not dav.etag_match('"a"', "b") and not dav.etag_match('"a"', None)
    assert dav.parts_of("/dav/calendars/alex/My%20cal/") == ["calendars", "alex", "My cal"] and dav.parts_of("/") == []
    assert dav.http_date(dt.datetime(2026, 11, 10, 4, 30)) == "Tue, 10 Nov 2026 04:30:00 GMT" and dav.http_date(None) == ""
    u = dav.unauthorized("ioCalendar", "an app password")
    assert u.status_code == 401 and u.headers["www-authenticate"] == 'Basic realm="ioCalendar", charset="UTF-8"'
    assert dav.options("1, 2, 3, calendar-access", ["OPTIONS", "GET"]) == {"DAV": "1, 2, 3, calendar-access", "Allow": "OPTIONS, GET", "MS-Author-Via": "DAV"}
    assert dav.sync_token("urn:x:sync:", {"id": 4, "sync_token": 17}) == "urn:x:sync:4-17"


# ------------------------------------------------------------------ the server, with a small app of notes in memory

def notes_app():
    """A CalDAV-shaped app whose collections and objects are dicts: what the server itself does, without any app."""
    from fastapi import FastAPI, Request
    from fastapi.responses import Response

    from iosuite_shared.errors import Invalid

    store = {"cols": [{"id": 1, "slug": "family", "name": "Family", "owner_id": None, "sync_token": 1},
                      {"id": 2, "slug": "mine", "name": "Mine", "owner_id": 7, "sync_token": 1}],
             "rows": []}

    class Notes(dav.Server):
        label, ns, ns_prefix, well_known = "ioNotes", C, "cal", "notes"
        home_segment, home_set, home_name = "notes", "calendar-home-set", "Notes"
        collection_type, description, data = "calendar", "calendar-description", "calendar-data"
        multiget, query, content_type = "calendar-multiget", "calendar-query", "text/plain; charset=utf-8"
        sync_prefix, max_bytes, keep_last, banner = "urn:x-notes:sync:", 400, True, "notes here"

        def collections(self, user):
            return store["cols"]

        def collection(self, user, slug):
            return next((c for c in store["cols"] if c["slug"] == slug), None)

        def reload(self, c):
            return dict(c)

        def can_write(self, user, c):
            return c["owner_id"] == user["id"] or user["role"] == "editor"

        def rows(self, c, since=None, names=()):
            return [r for r in store["rows"] if r["cid"] == c["id"] and (r["token"] > since if since is not None else not r["deleted"])]

        def by_href(self, c, name):
            return next((r for r in store["rows"] if r["cid"] == c["id"] and r["href"] == name), None)

        def purged_before(self, c):
            return 0

        def title(self, row):
            return row["text"][:10]

        def object_data(self, row, data_el, loaded=None):
            return row["text"]

        def export(self, c):
            return "".join(r["text"] for r in self.rows(c))

        def patch(self, tag, v):
            return ("name", v) if tag == dav.q(dav.D, "displayname") else None

        def update(self, c, changes):
            if len(changes["name"]) > 8:
                raise Invalid("too long")
            c.update(changes, sync_token=c["sync_token"] + 1)

        def _bump(self, c):
            c["sync_token"] += 1
            return c["sync_token"]

        def save(self, ctx, c, row, name, body):
            text = body.decode()
            refused = self.conflict(ctx, c, row, next((r for r in self.rows(c) if r["text"] == text), None))
            if refused:
                return refused
            if row:
                row.update(text=text, etag=f"e{len(store['rows'])}{text}", token=self._bump(c))
            else:
                store["rows"].append({"id": len(store["rows"]) + 1, "cid": c["id"], "href": name, "text": text, "etag": f"e{text}",
                                      "deleted": 0, "updated_at": dt.datetime(2026, 11, 14), "token": self._bump(c)})
            return Response(status_code=204 if row else 201)

        def delete(self, ctx, c, row):
            row.update(deleted=1, token=self._bump(c))

        def drop(self, c):
            store["cols"].remove(c)

        def make(self, ctx, slug, root):
            store["cols"].append({"id": 9, "slug": slug, "name": slug, "owner_id": ctx.user["id"], "sync_token": 1})
            return Response(status_code=201)

        def search(self, c, root):
            return self.rows(c)

    app = FastAPI()
    who = {"user": {"id": 7, "name": "alex", "displayName": "Alex", "role": "member"}}

    @app.middleware("http")
    async def sign_in(request: Request, call_next):
        request.state.user = who["user"] if request.headers.get("authorization") else None
        return await call_next(request)

    app.include_router(Notes().router())
    return app, store, who


def test_the_shared_server_does_discovery_preconditions_and_sync():
    import re

    from fastapi.testclient import TestClient

    from iosuite_shared import users
    users.create("someone", "secret123")  # accounts exist: roles count
    app, store, who = notes_app()
    c = TestClient(app)

    def dav_(m, path, body=None, **h):
        return c.request(m, path, content=body, headers={"Authorization": "Basic x", **h})

    assert c.request("PROPFIND", "/.well-known/notes", follow_redirects=False).headers["location"] == "/dav/"
    assert c.request("PROPFIND", "/dav/").status_code == 401 and c.request("OPTIONS", "/dav/").headers["DAV"] == "1, 2, 3"
    r = dav_("PROPFIND", "/dav/", Depth="1")
    assert r.status_code == 207 and "/dav/principals/alex/" in r.text and "/dav/notes/alex/" in r.text and ">ioNotes<" in r.text
    assert "Alex" in dav_("PROPFIND", "/dav/principals/alex/", Depth="0").text
    assert dav_("PROPFIND", "/dav/notes/bob/").status_code == 403
    r = dav_("PROPFIND", "/dav/notes/alex/", Depth="1")
    assert "/dav/notes/alex/family/" in r.text and "/dav/notes/alex/mine/" in r.text and "urn:x-notes:sync:1-1" in r.text
    # PUT: who may write, If-None-Match, If-Match, the same object twice, too large
    assert dav_("PUT", "/dav/notes/alex/family/a.txt", "hello").status_code == 403  # a shared collection, a member
    who["user"] = dict(who["user"], role="editor")
    assert dav_("PUT", "/dav/notes/alex/family/a.txt", "hello", **{"If-None-Match": "*"}).status_code == 201
    assert dav_("PUT", "/dav/notes/alex/family/a.txt", "again", **{"If-None-Match": "*"}).status_code == 412
    assert dav_("PUT", "/dav/notes/alex/family/a.txt", "again", **{"If-Match": '"nope"'}).status_code == 412
    r = dav_("PUT", "/dav/notes/alex/family/b.txt", "hello")
    assert r.status_code == 409 and "no-uid-conflict" in r.text and "/dav/notes/alex/family/a.txt" in r.text
    r = dav_("PUT", "/dav/notes/alex/family/c.txt", "x" * 401)
    assert r.status_code == 403 and "max-resource-size" in r.text
    assert dav_("PUT", "/dav/notes/alex/nowhere/c.txt", "x").status_code == 409
    got = dav_("GET", "/dav/notes/alex/family/a.txt")
    assert got.text == "hello" and got.headers["etag"] == '"ehello"' and dav_("GET", "/dav/notes/alex/family/").text == "hello"
    assert dav_("GET", "/dav/").text == "notes here"
    # sync-collection: from nothing, then what changed (a deletion included), and a token that is not ours
    sync = ('<d:sync-collection xmlns:d="DAV:"><d:sync-token>{}</d:sync-token><d:prop><d:getetag/></d:prop></d:sync-collection>')
    r = dav_("REPORT", "/dav/notes/alex/family/", sync.format(""))
    tok = re.search(r"<d:sync-token>([^<]+)<", r.text).group(1)
    assert "a.txt" in r.text and tok == "urn:x-notes:sync:1-2"
    assert dav_("PUT", "/dav/notes/alex/family/d.txt", "new").status_code == 201
    assert dav_("DELETE", "/dav/notes/alex/family/a.txt", **{"If-Match": '"nope"'}).status_code == 412
    assert dav_("DELETE", "/dav/notes/alex/family/a.txt").status_code == 204
    r = dav_("REPORT", "/dav/notes/alex/family/", sync.format(tok))
    assert "d.txt" in r.text and "a.txt" in r.text and "404 Not Found" in r.text and "urn:x-notes:sync:1-4" in r.text
    for bad in ("urn:x-notes:sync:2-1", "urn:x-notes:sync:1-99", "http://bogus/1"):
        assert "valid-sync-token" in dav_("REPORT", "/dav/notes/alex/family/", sync.format(bad)).text
    # multiget: found and missing; an unknown report
    mg = ('<c:calendar-multiget xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-data/></d:prop>'
          '<d:href>/dav/notes/alex/family/d.txt</d:href><d:href>/dav/notes/alex/family/a.txt</d:href></c:calendar-multiget>')
    r = dav_("REPORT", "/dav/notes/alex/family/", mg)
    assert ">new<" in r.text and r.text.count("404 Not Found") == 1
    assert "supported-report" in dav_("REPORT", "/dav/notes/alex/family/", '<x:odd xmlns:x="urn:x"/>').text
    assert dav_("REPORT", "/dav/notes/alex/family/", "not xml").status_code == 400
    # PROPPATCH: kept, refused by the app (409), not allowed (403)
    patch = '<d:propertyupdate xmlns:d="DAV:"><d:set><d:prop><d:displayname>{}</d:displayname></d:prop></d:set></d:propertyupdate>'
    assert "200 OK" in dav_("PROPPATCH", "/dav/notes/alex/family/", patch.format("Fam")).text and store["cols"][0]["name"] == "Fam"
    assert "409 Conflict" in dav_("PROPPATCH", "/dav/notes/alex/family/", patch.format("Much too long")).text
    assert "403 Forbidden" in dav_("PROPPATCH", "/dav/notes/alex/", patch.format("Home")).text
    assert "Shared collections" in dav_("DELETE", "/dav/notes/alex/family/").text  # even for an editor
    who["user"] = dict(who["user"], role="member")
    assert "403 Forbidden" in dav_("PROPPATCH", "/dav/notes/alex/family/", patch.format("Fam")).text
    # DELETE of a collection: not a shared one, not one's last private one; MKCOL
    assert dav_("DELETE", "/dav/notes/alex/family/").status_code == 403
    assert "last private" in dav_("DELETE", "/dav/notes/alex/mine/").text
    assert dav_("MKCOL", "/dav/notes/alex/mine/").status_code == 405
    assert dav_("MKCOL", "/dav/notes/alex/more/").status_code == 201
    assert dav_("DELETE", "/dav/notes/alex/mine/").status_code == 204 and [x["slug"] for x in store["cols"]] == ["family", "more"]
