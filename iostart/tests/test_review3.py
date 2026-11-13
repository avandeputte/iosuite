"""The lower findings of the code review of 10 November 2026: a bookmark is a web address or a mailto:, a body that
is not a JSON object is a 400, an uploaded icon is parsed without entities, and a ping goes to the address that was
checked."""
import socket

import pytest

from app import bookmarks, status


# ---- P-5
def test_a_bookmark_is_a_web_address_or_a_mailto(client):
    gid = client.post("/api/bookmarks/groups", json={"name": "Home"}).json()["id"]
    for href in ("javascript:alert(1)", "JavaScript:alert(1)", "data:text/html,<script>1</script>", "vbscript:x", "file:///etc/passwd",
                 "ftp://nas.lan/", "mailto:", "mailto:not an address", "https://", " "):
        r = client.post(f"/api/bookmarks/groups/{gid}/links", json={"name": "x", "href": href})
        assert r.status_code == 400 and "web address" in r.json()["detail"], (href, r.text)
    for href, kept in (("nas.lan:5001/ui", "https://nas.lan:5001/ui"), ("example.com", "https://example.com"), ("http://router.lan", "http://router.lan"),
                       ("HTTPS://Example.com/a", "HTTPS://Example.com/a"), ("mailto:ann@example.com", "mailto:ann@example.com")):
        r = client.post(f"/api/bookmarks/groups/{gid}/links", json={"name": "x", "href": href})
        assert r.status_code == 200 and r.json()["href"] == kept, (href, r.text)
    lid = r.json()["id"]
    assert client.patch(f"/api/bookmarks/links/{lid}", json={"href": "javascript:alert(1)"}).status_code == 400
    r = client.post("/api/bookmarks/import", json={"yaml": "- Home:\n    - Bad:\n        - href: javascript:alert(1)\n    - Good:\n        - href: https://example.com\n"})
    assert "javascript:" not in str(client.get("/api/bookmarks").json())


# ---- P-6
def test_a_body_that_is_not_an_object_is_a_400(client):
    gid = client.post("/api/bookmarks/groups", json={"name": "Home"}).json()["id"]
    for method, path in (("POST", "/api/bookmarks/groups"), ("PATCH", f"/api/bookmarks/groups/{gid}"), ("POST", "/api/bookmarks/groups/order"),
                         ("POST", f"/api/bookmarks/groups/{gid}/links"), ("POST", "/api/bookmarks/import"), ("PUT", "/api/me/layout"),
                         ("POST", "/api/home/settings"), ("POST", "/api/weather/settings"), ("POST", "/api/ha/settings"), ("POST", "/api/ha/test"),
                         ("POST", "/api/widgets/iocalendar/events")):
        for body in ("[1, 2]", '"text"', "{not json"):
            r = client.request(method, path, content=body, headers={"Content-Type": "application/json"})
            assert r.status_code == 400, (method, path, body, r.status_code, r.text)


# ---- P-7
def test_an_uploaded_icon_is_parsed_without_entities():
    with pytest.raises(bookmarks.BadBookmark):
        bookmarks.clean_svg(b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>')
    with pytest.raises(bookmarks.BadBookmark):
        bookmarks.clean_svg(b"<svg><g></svg>")
    assert bookmarks.clean_svg(b'<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1"/></svg>').startswith("<svg")


def test_a_ping_goes_to_the_address_that_was_checked(monkeypatch):
    """A name that answers with a home address is pinged at that address; one that answers with this machine's own is
    not pinged, whatever it answered a moment before."""
    answers = iter([[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 80))], [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]])
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: next(answers))
    reached = []

    def connect(address, timeout=None, *a, **kw):
        reached.append(address)
        raise OSError("stop here")
    monkeypatch.setattr(socket, "create_connection", connect)
    assert status._ping("http://nas.lan/") == {"ok": False, "status": None}
    assert reached == [("192.168.1.10", 80)]  # resolved once, and connected to what it resolved to
    assert status._ping("http://rebind.example.net/") == {"ok": None, "status": None}
    assert len(reached) == 1
