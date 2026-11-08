"""Fixes from the v0.4.4 code review: book checks on moves and on what viewers can mark, no access for "none",
lookups only to public hosts, request limits, line breaks in exports, search wildcards and Apple's omit-year."""
from fastapi.testclient import TestClient

from app import calendar, enrich, users, vcard
from app.main import app


def mk(client, book, **kw):
    r = client.post(f"/api/contacts?book={book}", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def viewer(client):
    uid = client.post("/api/users", json={"name": "kid", "password": "kidpass99", "role": "viewer"}).json()["id"]
    k = TestClient(app)
    assert k.post("/api/auth/login", json={"name": "kid", "password": "kidpass99"}).status_code == 200
    own = next(b for b in k.get("/api/books").json()["items"] if not b["shared"])
    return k, uid, own


def test_viewer_cannot_move_a_contact_into_a_book_they_cannot_write(client, family_id):
    k, _uid, own = viewer(client)
    c = mk(k, own["id"], fn="Sneaky")
    assert k.patch(f"/api/contacts/{c['id']}", json={"bookId": family_id}).status_code == 403
    assert k.get(f"/api/contacts/{c['id']}").json()["bookId"] == own["id"]
    assert k.patch(f"/api/contacts/{c['id']}", json={"favorite": True}).status_code == 200


def test_viewer_cannot_mark_shared_contacts(client, family_id):
    a = mk(client, family_id, fn="Dup One", emails=[{"value": "same@x.org"}])
    b = mk(client, family_id, fn="Dup Two", emails=[{"value": "same@x.org"}])
    k, _uid, _own = viewer(client)
    assert k.post("/api/duplicates/dismiss", json={"ids": [a["id"], b["id"]]}).status_code == 403
    assert k.post(f"/api/contacts/{a['id']}/lookup").status_code == 403
    assert k.post("/api/lookup", json={"ids": [a["id"]]}).status_code == 403
    assert k.post("/api/lookup", json={}).json()["total"] == 0  # only their own book is looked up
    assert len(client.get("/api/duplicates").json()["groups"]) == 1


def test_no_access_means_no_calendar_feed(client, family_id):
    _k, uid, _own = viewer(client)
    tok = users.calendar_token(uid)
    assert users.user_from_calendar_token(tok)
    users.update(uid, role="none")
    users.forget_cached_auth()
    assert users.user_from_calendar_token(tok) is None


def test_lookups_reach_public_hosts_only():
    for url in ("file:///etc/passwd", "http://127.0.0.1:8610/api/status", "http://localhost/", "http://192.168.1.89/",
                "http://169.254.169.254/latest/", "ftp://example.com/x", "https://[::1]/"):
        try:
            enrich._public(url)
        except ValueError:
            continue
        raise AssertionError(f"{url} was allowed")


def test_import_and_body_limits(client, family_id, monkeypatch):
    from app import limits
    monkeypatch.setattr(limits, "MAX_IMPORT", 1000)
    big = ("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:X\r\nEND:VCARD\r\n" * 100).encode()
    r = client.post("/api/import", data={"book": str(family_id)}, files={"file": ("a.vcf", big, "text/vcard")})
    assert r.status_code == 413
    monkeypatch.setattr(limits, "MAX_BODY", 1000)
    assert client.post(f"/api/contacts?book={family_id}", json={"fn": "x" * 2000}).status_code == 413


def test_line_breaks_cannot_add_properties(client, family_id):
    c = mk(client, family_id, fn="Line Break", urls=[{"value": "https://a.example\r\nEMAIL:evil@x.org", "label": "home\"\r\nX"}],
           birthday={"year": 1980, "month": 1, "day": 2})
    text = client.get(f"/api/contacts/{c['id']}?format=vcard").text
    assert "\r\nEMAIL:evil" not in text and "\nEMAIL:evil" not in text
    assert vcard.escape("a\rb") == "a\\nb"
    assert calendar._esc("a\rb") == "a\\nb" and calendar._uid("x\r\nDESCRIPTION:y") == "x-DESCRIPTION:y"


def test_search_wildcards_mean_themselves(client, family_id):
    mk(client, family_id, fn="Ann Example")
    mk(client, family_id, fn="Half_Moon")
    assert client.get("/api/contacts?q=%25").json()["total"] == 0
    assert client.get("/api/contacts?q=_").json()["total"] == 1


def test_apple_omit_year_keeps_a_real_year():
    c = vcard.parse("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:A\r\nBDAY;X-APPLE-OMIT-YEAR=1604:1985-03-21\r\nEND:VCARD\r\n")[0]
    assert c["birthday"] == {"year": 1985, "month": 3, "day": 21}
    c = vcard.parse("BEGIN:VCARD\r\nVERSION:3.0\r\nFN:A\r\nBDAY;X-APPLE-OMIT-YEAR=1604:1604-03-21\r\nEND:VCARD\r\n")[0]
    assert c["birthday"] == {"year": None, "month": 3, "day": 21}


# ---- the 0.26 review round: the shared sign-in routes, the LDAP bind's throttle, every account's private book, XML


def test_app_passwords_are_the_shared_routes_and_only_the_owner_revokes(client):
    """/api/auth/app-passwords (iosuite-shared): a signed-in account makes and revokes its own; the old admin-only
    DELETE is gone with ioContacts' own routes."""
    k, uid, _own = viewer(client)
    pid = None
    k.post("/api/auth/app-passwords", json={"label": "kid phone", "scope": "dav"})
    items = k.get("/api/auth/app-passwords").json()["items"]
    assert [(p["label"], p["scope"]) for p in items] == [("kid phone", "dav")] and isinstance(items[0]["created"], int)
    pid = items[0]["id"]
    assert k.delete(f"/api/auth/app-passwords/{pid}").status_code == 200  # a viewer, not an admin
    assert k.get("/api/auth/app-passwords").json()["items"] == []
    assert client.get("/api/app-passwords").status_code == 404
    # the password route takes {current, password}; an empty new password is refused rather than removing it
    assert client.post("/api/auth/password", json={"current": "secret123", "password": ""}).status_code == 400
    assert client.post("/api/auth/password", json={"current": "wrong", "password": "another123"}).status_code == 403


def test_every_account_gets_a_private_book_however_it_was_made(client):
    """Accounts made by the suite (Settings › Accounts and access, the shared setup, the command line) never passed through
    ioContacts' users.create: their private book appears when their books are first listed."""
    from iosuite_shared import users as shared
    u = shared.create("sue", "suepass123", "editor", "iocontacts")
    k = TestClient(app)
    assert k.post("/api/auth/login", json={"name": "sue", "password": "suepass123"}).status_code == 200
    books = k.get("/api/books").json()["items"]
    assert [b["name"] for b in books if not b["shared"]] == ["Personal"]
    assert len([b for b in k.get("/api/books").json()["items"] if not b["shared"]]) == 1  # not made twice
    # an account deleted elsewhere leaves its book behind; the start-up sweep removes it
    own = next(b for b in books if not b["shared"])
    mk(k, own["id"], fn="Sue's friend")
    shared.delete(u["id"])
    from app import db
    assert db.one("SELECT 1 AS x FROM con_address_books WHERE id = %s", (own["id"],))
    users.init()
    assert not db.one("SELECT 1 AS x FROM con_address_books WHERE id = %s", (own["id"],))
    assert not db.one("SELECT 1 AS x FROM con_contacts WHERE address_book_id = %s", (own["id"],))


def test_carddav_refuses_xml_entities(client):
    """A report body with entity expansion (a billion laughs) or an external entity is refused (400), not parsed."""
    client.post("/api/books", json={"name": "Family", "shared": True})
    bomb = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
            '<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav"><D:prop><D:getetag>&b;</D:getetag></D:prop></C:addressbook-query>')
    h = {"Depth": "1", "Content-Type": "application/xml"}
    assert client.request("REPORT", "/dav/addressbooks/alex/family/", content=bomb, headers=h).status_code == 400
    ext = ('<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
           '<C:addressbook-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:carddav"><D:prop>&e;</D:prop></C:addressbook-query>')
    r = client.request("REPORT", "/dav/addressbooks/alex/family/", content=ext, headers=h)
    assert r.status_code == 400 and "root:" not in r.text
    # a PROPFIND body is never fatal: a bad one means "all properties", entities included
    assert client.request("PROPFIND", "/dav/", content=bomb.replace("addressbook-query", "propfind"), headers={"Depth": "0"}).status_code == 207


def test_ldap_bind_is_throttled_after_repeated_failures(client):
    """Wrong LDAP passwords count like wrong web sign-ins: after the free tries the bind is refused before any hash."""
    import asyncio
    from iosuite_shared import users as shared
    from app import ldapd
    shared._attempts.clear()
    checked = []
    real = users.authenticate

    def counting(name, pw, protocol=False):
        checked.append(name)
        return real(name, pw, protocol)

    users.authenticate = counting
    try:
        loop = asyncio.new_event_loop()
        srv = loop.run_until_complete(ldapd.serve("127.0.0.1", 0))
        port = srv.sockets[0].getsockname()[1]
        import threading
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        try:
            import ldap3
            s = ldap3.Server("127.0.0.1", port=port, get_info=ldap3.NONE)
            for _ in range(shared.LOCK_AFTER + 1):
                assert not ldap3.Connection(s, "cn=alex,ou=users,dc=iocontacts", "wrong").bind()
            n = len(checked)
            c = ldap3.Connection(s, "cn=alex,ou=users,dc=iocontacts", "secret123")
            assert not c.bind() and "try again" in str(c.result.get("message", ""))
            assert len(checked) == n  # refused without checking the password
        finally:
            srv.close()
            loop.call_soon_threadsafe(loop.stop)
            t.join(timeout=5)
    finally:
        users.authenticate = real
        shared._attempts.clear()
