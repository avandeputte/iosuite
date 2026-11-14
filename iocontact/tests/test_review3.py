"""The lower findings of the code review of 10 November 2026: a lookup connects to the address it checked, a deleted
contact leaves nothing of the person behind and its marker goes after a while, a relation into somebody's private
book is theirs alone, bodies and address books are validated, and the small bugs."""
import re
import socket

import pytest
from fastapi.testclient import TestClient

from app import db, enrich, iopix, model
from tests.test_api import mk
from iosuite_shared import testing


def other_account(client, name="ann", role="editor"):
    """A second account, signed in with its own client."""
    from app.main import app
    assert testing.add_account(client, {"name": name, "password": "secret123", "role": role}).status_code == 200
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"name": name, "password": "secret123"}).status_code == 200
    return c


# ---- K-5
def test_a_lookup_connects_to_the_address_it_checked(monkeypatch):
    answers = iter([[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))],   # the check: public
                    [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 80))]])   # asked again: inside
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: next(answers))
    reached = []

    def connect(address, timeout=None, *a, **kw):
        reached.append(address)
        raise OSError("stop here")
    monkeypatch.setattr(socket, "create_connection", connect)
    with pytest.raises(Exception):
        enrich._get("http://rebind.example.net/profile")
    # the name was resolved for the check (public) and once more where the connection is made (inside): refused there,
    # and nothing was ever connected to
    assert reached == []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))])
    with pytest.raises(Exception):
        enrich._get("http://example.net/profile")
    assert reached == [("93.184.216.34", 80)]  # the address that was checked, not the name


def test_a_failed_lookup_keeps_its_details_in_the_log(client, family_id, monkeypatch):
    c = mk(client, family_id, fn="Ann Lee", emails=[{"value": "ann@x.org"}])

    def broken(contact):
        raise OSError("connect to 10.0.0.7:8443 refused")
        yield
    monkeypatch.setattr(enrich, "PROVIDERS", {"gravatar": broken})
    out = enrich.lookup(c["id"])
    assert out["errors"] == ["gravatar: no answer"]


# ---- K-6
def test_a_deleted_contact_leaves_nothing_of_the_person(client, family_id):
    c = mk(client, family_id, fn="Ann Lee", name={"given": "Ann", "family": "Lee"}, org="Acme", birthday={"year": 1980, "month": 5, "day": 4},
           gender="F", notes="private", nickname="Annie")
    assert client.delete(f"/api/contacts/{c['id']}").status_code == 200
    row = db.one("SELECT * FROM con_contacts WHERE id = %s", (c["id"],))
    assert row["deleted"] == 1 and row["uid"] and row["href"]  # what a sync client needs
    kept = {k: v for k, v in row.items() if v not in (None, "", 0) and k not in
            ("id", "address_book_id", "uid", "href", "kind", "etag", "changed_token", "deleted", "created_at", "updated_at", "bday_remind")}
    assert kept == {}


def test_old_deletion_markers_are_purged_and_a_stale_client_starts_over(client, family_id):
    sync = ('<d:sync-collection xmlns:d="DAV:"><d:sync-token>{}</d:sync-token><d:sync-level>1</d:sync-level>'
            '<d:prop><d:getetag/></d:prop></d:sync-collection>')

    def report(tok):
        return client.request("REPORT", "/dav/addressbooks/alex/family/", content=sync.format(tok), auth=("alex", "secret123"))
    a, b = mk(client, family_id, fn="Ann Lee"), mk(client, family_id, fn="Bob Ray")
    first = re.search(r"<d:sync-token>([^<]+)</d:sync-token>", report("").text).group(1)
    client.delete(f"/api/contacts/{a['id']}")
    assert "404 Not Found" in report(first).text  # the marker tells the client
    assert model.purge_deleted() == 0  # not old yet
    db.ex("UPDATE con_contacts SET updated_at = NOW() - INTERVAL 200 DAY WHERE id = %s", (a["id"],))
    assert model.purge_deleted() == 1 and db.one("SELECT 1 AS x FROM con_contacts WHERE id = %s", (a["id"],)) is None
    r = report(first)  # a client that last synced before the deletion cannot be told any more: it starts over
    assert r.status_code == 403 and "valid-sync-token" in r.text
    fresh = report("")
    assert fresh.status_code == 207 and "Bob" not in fresh.text and fresh.text.count("<d:response>") == 1
    now = re.search(r"<d:sync-token>([^<]+)</d:sync-token>", fresh.text).group(1)
    assert report(now).status_code == 207
    assert b["id"]


def test_a_relation_into_a_private_book_is_its_owners_alone(client, family_id):
    ann = other_account(client)
    shared = mk(client, family_id, fn="Sam Shared")
    private_book = next(b["id"] for b in client.get("/api/books").json()["items"] if not b["shared"])
    secret = mk(client, private_book, fn="Pat Private", gender="F", relations=[{"type": "sibling", "relatedId": shared["id"]}])
    # the owner sees the mirrored relation on the shared contact; the other account does not
    mine = client.get(f"/api/contacts/{shared['id']}").json()
    assert [r["relatedFn"] for r in mine["relations"]] == ["Pat Private"]
    theirs = ann.get(f"/api/contacts/{shared['id']}").json()
    assert theirs["relations"] == [] and "Pat" not in ann.get(f"/api/contacts/{shared['id']}", headers={"Accept": "text/vcard"}).text
    # and saving the contact without the relation it was never shown does not remove it
    theirs["notes"] = "seen by ann"
    assert ann.put(f"/api/contacts/{shared['id']}", json=theirs).status_code == 200
    mine = client.get(f"/api/contacts/{shared['id']}").json()
    assert mine["notes"] == "seen by ann" and [r["relatedFn"] for r in mine["relations"]] == ["Pat Private"]
    assert [r["relatedFn"] for r in client.get(f"/api/contacts/{secret['id']}").json()["relations"]] == ["Sam Shared"]


# ---- K-7
def test_a_body_that_is_not_an_object_is_a_400(client, family_id):
    c = mk(client, family_id, fn="Ann Lee")
    for method, path in (("POST", "/api/books"), ("PATCH", f"/api/books/{family_id}"), ("PATCH", f"/api/contacts/{c['id']}"),
                         ("POST", "/api/contacts/bulk"), ("POST", "/api/contacts/merge"), ("PUT", "/api/me-contact"),
                         ("POST", "/api/duplicates/dismiss")):
        for body in ([1, 2], "text", None):
            r = client.request(method, path, json=body)
            assert r.status_code == 400, (method, path, body, r.text)
    r = client.post("/api/contacts/merge", json={"others": [c["id"]]})
    assert r.status_code == 400 and "keep" in r.json()["detail"]


def test_an_address_book_is_validated_whichever_way_it_comes(client, family_id):
    assert client.post("/api/books", json={"name": "  "}).status_code == 400
    assert client.post("/api/books", json={"name": "x" * 200}).status_code == 400
    for bad in ({"name": ""}, {"color": "javascript:alert(1)"}, {"color": "red"}, {"name": 5}, {"description": ["x"]}):
        assert client.patch(f"/api/books/{family_id}", json=bad).status_code == 400, bad
    assert client.patch(f"/api/books/{family_id}", json={"name": "Family", "color": "#A1B2C3FF", "description": ""}).status_code == 200
    book = next(b for b in client.get("/api/books").json()["items"] if b["id"] == family_id)
    assert book["color"] == "#a1b2c3" and book["description"] is None
    auth = ("alex", "secret123")
    patch = ('<d:propertyupdate xmlns:d="DAV:" xmlns:ap="http://apple.com/ns/ical/"><d:set><d:prop>'
             '<ap:calendar-color>{}</ap:calendar-color></d:prop></d:set></d:propertyupdate>')
    r = client.request("PROPPATCH", "/dav/addressbooks/alex/family/", content=patch.format("url(evil)"), auth=auth)
    assert "409 Conflict" in r.text
    assert next(b for b in client.get("/api/books").json()["items"] if b["id"] == family_id)["color"] == "#a1b2c3"
    assert "200 OK" in client.request("PROPPATCH", "/dav/addressbooks/alex/family/", content=patch.format("#00FF00"), auth=auth).text
    # a new book's address over CardDAV is plain
    assert client.request("MKCOL", "/dav/addressbooks/alex/new%20book%3F/", auth=auth).status_code == 403
    assert client.request("MKCOL", "/dav/addressbooks/alex/" + "x" * 80 + "/", auth=auth).status_code == 403
    assert client.request("MKCOL", "/dav/addressbooks/alex/work/", auth=auth).status_code == 201
    assert "work" in [b["slug"] for b in client.get("/api/books").json()["items"]]


def test_a_date_that_is_none_is_not_a_birthday_on_1_march(client, family_id):
    import datetime as dt
    a = mk(client, family_id, fn="Leap Ann", birthday={"month": 2, "day": 29})
    b = mk(client, family_id, fn="Odd Bob")
    db.ex("UPDATE con_contacts SET bday_month = 4, bday_day = 31 WHERE id = %s", (b["id"],))  # as an import once stored it
    up = model.upcoming([family_id], days=400)
    assert [x["fn"] for x in up] == ["Leap Ann"]
    d = dt.date.fromisoformat(up[0]["date"])
    assert (d.month, d.day) in ((2, 29), (3, 1)) and a["id"]


def test_two_contacts_of_one_name_are_not_linked_to_one_person(client, family_id, monkeypatch):
    monkeypatch.setattr(iopix, "people", lambda force=False: [{"id": 7, "name": "Ann Lee"}, {"id": 8, "name": "Bob Ray"}])
    mk(client, family_id, fn="Ann Lee")
    mk(client, family_id, fn="ann lee", emails=[{"value": "other@x.org"}])
    bob = mk(client, family_id, fn="Bob Ray")
    r = client.post("/api/iopix/auto-link?dry=false").json()
    assert [(x["contactId"], x["personId"]) for x in r["items"]] == [(bob["id"], 8)] and r["linked"] == 1


def test_a_gender_set_through_a_relation_changes_the_card(client, family_id):
    bob = mk(client, family_id, fn="Bob Ray")
    before = db.one("SELECT etag, changed_token FROM con_contacts WHERE id = %s", (bob["id"],))
    mk(client, family_id, fn="Ann Lee", relations=[{"type": "sibling", "relatedId": bob["id"], "gender": "M"}])
    after = db.one("SELECT etag, changed_token, gender FROM con_contacts WHERE id = %s", (bob["id"],))
    assert after["gender"] == "M" and after["etag"] != before["etag"] and after["changed_token"] > before["changed_token"]


def test_an_accounts_face_is_for_the_network_or_the_signed_in(client, family_id, monkeypatch):
    from app.main import app
    me = mk(client, family_id, fn="Alex")
    uid = client.get("/api/auth/me").json()["user"]["id"]
    assert client.put("/api/me-contact", json={"contactId": me["id"]}).status_code == 200
    monkeypatch.setattr(model, "photo", lambda cid: (b"\xff\xd8face", "image/jpeg"))
    anon = TestClient(app)
    assert anon.get(f"/api/auth/accounts/{uid}/photo").status_code == 200  # the sign-in screen, at home
    assert anon.get(f"/api/auth/accounts/{uid}/photo", headers={"cf-connecting-ip": "1.2.3.4"}).status_code == 404
    assert client.get(f"/api/auth/accounts/{uid}/photo", headers={"cf-connecting-ip": "1.2.3.4"}).status_code == 200


# ---- K-8
def test_the_face_cache_is_limited_by_what_it_weighs(monkeypatch):
    monkeypatch.setattr(iopix, "FACE_MAX_BYTES", 1000)
    monkeypatch.setattr(iopix, "_faces", {})
    for i in range(10):
        iopix._remember(i, (b"x" * 300, "image/jpeg"), None)
    assert list(iopix._faces) == [7, 8, 9]  # the newest that fit
    iopix._remember(99, None, None)
    assert 99 in iopix._faces
