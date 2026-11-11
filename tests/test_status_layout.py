"""The status dots (app/status.py) and each person's own layout (app/layout.py)."""
import pytest

from app import status, widgets


@pytest.fixture(autouse=True)
def fresh():
    status.forget()
    yield
    status.forget()


def test_apps_status_from_each_apps_status(client, monkeypatch):
    answers = {"iopix": {"app": "ioPix", "version": "1.4.0", "update": {"version": "1.5.0", "remote": "1.5.0"}},
               "iohealth": {"app": "ioHealth", "version": "2.0", "update": None},
               "iocalendar": {"app": "ioCalendar", "version": "0.9", "update": None},
               "iotasks": {"app": "ioTasks", "version": "0.1", "update": None}}
    asked = []

    def fake(request, key, path, params=None, raw=False):
        asked.append(key)
        if key == "iocontacts":
            raise widgets.Unavailable(403, "iocontacts answered 401")  # up, but not open to this account
        if key == "ionotes":
            raise widgets.Unavailable(502, "ionotes is not reachable (URLError)")
        return answers[key]
    monkeypatch.setattr(widgets, "fetch", fake)
    d = client.get("/api/apps/status").json()["items"]
    assert d["iopix"] == {"ok": True, "version": "1.4.0", "update": "1.5.0", "why": None}
    assert d["iohealth"]["ok"] and d["iohealth"]["update"] is None and d["iocalendar"]["update"] is None
    assert d["iocontacts"]["ok"] is True and d["ionotes"] == {"ok": False, "version": None, "update": None, "why": "ionotes is not reachable (URLError)"}
    assert sorted(asked) == ["iocalendar", "iocontacts", "iohealth", "ionotes", "iopix", "iotasks"]
    client.get("/api/apps/status")
    assert len(asked) == 6  # remembered for a minute
    client.cookies.clear()
    assert client.get("/api/apps/status").status_code == 401


def test_bookmarks_status_pings_each_link(client, monkeypatch):
    client.post("/api/bookmarks/groups", json={"name": "Home"})
    gid = client.get("/api/bookmarks").json()["groups"][0]["id"]
    for name, href in [("Router", "http://router.lan"), ("NAS", "https://nas.lan:5001")]:
        client.post(f"/api/bookmarks/groups/{gid}/links", json={"name": name, "href": href})
    links = {l["name"]: l["id"] for l in client.get("/api/bookmarks").json()["groups"][0]["links"]}
    pinged = []

    def fake(href):
        pinged.append(href)
        return {"ok": href.startswith("http://router"), "status": 200 if href.startswith("http://router") else None}
    monkeypatch.setattr(status, "_ping", fake)
    d = client.get("/api/bookmarks/status").json()["items"]
    assert d[str(links["Router"])] == {"ok": True, "status": 200} and d[str(links["NAS"])]["ok"] is False
    assert sorted(pinged) == ["http://router.lan", "https://nas.lan:5001"]
    client.get("/api/bookmarks/status")
    assert len(pinged) == 2  # remembered


def test_ping_without_a_server():
    import ipaddress
    assert status._ping("mailto:x@y") == {"ok": None, "status": None}
    assert status._allowed(ipaddress.ip_address("192.168.1.1")) and status._allowed(ipaddress.ip_address("10.0.0.7"))  # bookmarks are for the home network


def test_ping_never_reaches_this_server_or_metadata_and_never_follows_a_redirect():
    """A bookmark editor cannot make the server probe itself or a cloud metadata service, and a redirect is an
    answer (up), not a request to another address."""
    import http.server
    import threading
    for href in ("http://127.0.0.1:9/", "http://localhost/", "http://[::1]/", "http://169.254.169.254/latest/", "http://0.0.0.0/", "ftp://x/"):
        assert status._ping(href) == {"ok": None, "status": None}, href
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self):
            seen.append(self.path)
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:9/secret")
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        # the server is reached through its own address only when it is not loopback: pretend with the check off
        href = f"http://127.0.0.1:{srv.server_port}/x"
        import unittest.mock as um
        with um.patch.object(status, "_allowed", lambda ip: True):
            assert status._ping(href) == {"ok": True, "status": 302}
        assert seen == ["/x"]  # the redirect was not followed
    finally:
        srv.shutdown()


def test_my_layout(client):
    assert client.get("/api/me/layout").json() == {"hidden": [], "order": [], "cards": [], "strip": None, "search": None, "stripMove": None, "stripEvery": None}
    assert client.get("/api/apps").json()["layout"] == {"hidden": [], "order": [], "cards": [], "strip": None, "search": None, "stripMove": None, "stripEvery": None}
    r = client.put("/api/me/layout", json={"hidden": ["ionotes", "week", "ionotes"], "order": ["iocalendar", "iopix"], "cards": ["strip", "birthdays"], "strip": "onthisday"})
    assert r.status_code == 200 and r.json() == {"hidden": ["ionotes", "week"], "order": ["iocalendar", "iopix"], "cards": ["strip", "birthdays"], "strip": "onthisday", "search": None, "stripMove": None, "stripEvery": None}
    assert client.put("/api/me/layout", json={"cards": ["strip", "strip"]}).status_code == 400
    assert client.put("/api/me/layout", json={"cards": ["iopix"]}).status_code == 400
    assert client.get("/api/apps").json()["layout"]["order"] == ["iocalendar", "iopix"]
    assert client.put("/api/me/layout", json={"hidden": ["Not an app!"]}).status_code == 400
    assert client.put("/api/me/layout", json={"order": ["iopix", "iopix"]}).status_code == 400
    assert client.put("/api/me/layout", json={"strip": "all"}).status_code == 400
    assert client.put("/api/me/layout", json={"search": "altavista"}).status_code == 400
    assert client.put("/api/me/layout", json={"search": "google"}).json()["search"] == "google"
    assert client.put("/api/me/layout", json={"stripMove": "spin"}).status_code == 400
    assert client.put("/api/me/layout", json={"stripEvery": 7}).status_code == 400
    r = client.put("/api/me/layout", json={"stripMove": "page", "stripEvery": 300}).json()
    assert (r["stripMove"], r["stripEvery"]) == ("page", 300)
    assert client.put("/api/me/layout", json=[]).status_code == 400
    assert client.put("/api/me/layout", json={}).json() == {"hidden": [], "order": [], "cards": [], "strip": None, "search": None, "stripMove": None, "stripEvery": None}
    # another account has its own
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    client.put("/api/me/layout", json={"hidden": ["iohealth"]})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/me/layout").json()["hidden"] == []


def test_contacts_search_for_the_search_box(client, monkeypatch):
    asked = []

    def fake(request, key, path, params=None, raw=False):
        asked.append((key, path, params))
        return {"total": 1, "items": [{"id": 3, "fn": "Ada Lovelace", "hasPhoto": True, "org": "Analytical Engines"}]}
    monkeypatch.setattr(widgets, "fetch", fake)
    d = client.get("/api/widgets/iocontacts?q=ada").json()
    assert d == {"items": [{"id": 3, "name": "Ada Lovelace", "hasPhoto": True, "iopixPersonId": None, "org": "Analytical Engines"}], "total": 1}
    assert asked == [("iocontacts", "/api/contacts", {"q": "ada", "limit": 5})]


def test_ping_trusts_a_self_signed_certificate(monkeypatch):
    """A router on a home address with its own certificate answered: it is up, not "Not reachable"."""
    import ssl
    import urllib.error

    class Opener:
        def __init__(self, err):
            self.err = err

        def open(self, req, timeout=None):
            raise self.err
    monkeypatch.setattr(status, "_opener", Opener(urllib.error.URLError(ssl.SSLCertVerificationError(1, "self-signed certificate"))))
    assert status._ping("https://192.168.1.1") == {"ok": True, "status": None}
    monkeypatch.setattr(status, "_opener", Opener(ssl.SSLCertVerificationError(1, "self-signed certificate")))
    assert status._ping("https://192.168.1.1") == {"ok": True, "status": None}
    monkeypatch.setattr(status, "_opener", Opener(urllib.error.URLError(ConnectionRefusedError(111, "refused"))))
    assert status._ping("https://192.168.1.1") == {"ok": False, "status": None}
