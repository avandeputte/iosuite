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
    uid = client.post("/api/users", json={"name": "kid", "password": "kidpass99", "role": "viewer"}).json()["user"]["id"]
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
