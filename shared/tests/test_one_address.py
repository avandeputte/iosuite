"""The suite on one address (iosuite_shared.suite: FOLDERS, one_address; the start page passes each folder on,
iostart: app/frontdoor.py): one switch in the Shared ioSuite database, and what the suite's list of apps answers
while it is on."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from iosuite_shared import admin, db, proxyauth, suite, users
from iosuite_shared.errors import Invalid
from iosuite_shared.fastapi import Auth



def both():
    suite.register("iostart", "ioStart", url="https://home.example.com")
    suite.register("iocalendar", "ioCalendar", url="https://calendar.example.com", internal_url="http://192.168.1.10:8620")
    suite.register("ionote", "ioNote", url="https://notes.example.com")  # in a container without INTERNAL_URL: nowhere to pass on to


def test_off_until_switched_on_and_the_addresses_follow():
    both()
    assert not suite.one_address() and suite.door_url() is None
    assert suite.get("iocalendar")["url"] == "https://calendar.example.com"
    suite.set_one_address(True)
    assert suite.one_address() and suite.door_url() == "https://home.example.com"
    cal = suite.get("iocalendar")
    assert cal["url"] == "https://home.example.com/calendar" and cal["icon"] == "https://home.example.com/calendar/static/icons/mark.svg"
    assert cal["configuredUrl"] == "https://calendar.example.com"  # what the app's configuration names stays what it is
    assert suite.get("iostart")["url"] == "https://home.example.com"
    assert suite.get("ionote")["url"] == "https://notes.example.com"  # the start page cannot reach it: it keeps its own
    assert suite.known_host("iocalendar", "home.example.com") and suite.known_host("iocalendar", "calendar.example.com")
    suite.set_one_address(False)
    assert suite.get("iocalendar")["url"] == "https://calendar.example.com" and suite.door_url() is None


def test_without_the_start_page_there_is_no_address():
    suite.register("iocalendar", "ioCalendar", url="https://calendar.example.com", internal_url="http://192.168.1.10:8620")
    with pytest.raises(Invalid):
        admin.set_one_address(True)
    suite.set_one_address(True)  # the setting alone, as a start page that was removed leaves it
    assert suite.door_url() is None and suite.get("iocalendar")["url"] == "https://calendar.example.com"


def test_folders():
    assert suite.folder_of("iocalendar") == "calendar" and suite.folder_of("iopix") == "pix" and suite.folder_of("iostart") is None
    assert suite.folder_of("ioplant") == "ioplant"  # an app the suite does not know: by its key
    assert suite.folder_of("api") is None and suite.folder_of("static") is None and suite.folder_of("a/b") is None
    assert len(set(suite.FOLDERS.values())) == len(suite.FOLDERS) and not set(suite.FOLDERS.values()) & suite.TAKEN
    assert set(suite.FOLDERS) == set(suite.PORTS) - {"iostart"}


def test_where_the_start_page_passes_on_to(monkeypatch):
    from iosuite_shared import links
    monkeypatch.setattr(links, "_this_machine", lambda host: host in ("192.168.1.10", "127.0.0.1"))
    assert suite.upstream_of({"internal_url": "http://192.168.1.10:8620"}) == "http://127.0.0.1:8620"  # on this machine: its loopback
    assert suite.upstream_of({"internal_url": "http://192.168.1.20:8620/"}) == "http://192.168.1.20:8620"
    assert suite.upstream_of({"internal_url": "https://calendar.lan:8620"}) == "https://calendar.lan:8620"
    assert suite.upstream_of({"internal_url": None, "configured_url": "https://calendar.example.com"}) is None  # never the public one


def test_api_for_suite_admins():
    both()
    users.create("alex", "secret123", suite_admin=True)
    users.create("ann", "secret123", "admin", "iostart")
    auth = Auth("iostart", register=False)
    app = FastAPI()
    app.middleware("http")(auth.middleware(open_prefixes=("/api/auth/",)))
    app.include_router(auth.router())
    app.include_router(auth.admin_router())

    def signed_in(name):
        c = TestClient(app, base_url="http://home.example.com")
        assert c.post("/api/auth/login", json={"name": name, "password": "secret123"}).status_code == 200
        return c
    c = signed_in("alex")
    d = c.get("/api/suite-admin/address").json()
    assert d["on"] is False and d["start"] is True and d["address"] == "https://home.example.com"
    by = {a["app"]: a for a in d["apps"]}
    assert set(by) == {"iocalendar", "ionote"}  # the start page is the address itself
    assert by["iocalendar"] == {"app": "iocalendar", "name": "ioCalendar", "folder": "calendar", "reachable": True, "url": "https://home.example.com/calendar"}
    assert by["ionote"]["reachable"] is False
    assert c.put("/api/suite-admin/address", json={"on": True}).json()["on"] is True and suite.one_address()
    assert c.put("/api/suite-admin/address", json={"on": False}).json()["on"] is False and not suite.one_address()
    ann = signed_in("ann")  # an admin of the start page alone does not open every app to wherever the start page is
    assert ann.get("/api/suite-admin/address").status_code == 403
    assert ann.put("/api/suite-admin/address", json={"on": True}).status_code == 403 and not suite.one_address()


def test_the_start_page_says_when_a_request_came_from_outside():
    p = proxyauth.Proxy("iocalendar")
    assert not p.external({}, "127.0.0.1")
    assert p.external({proxyauth.OUTSIDE_HEADER: "1"}, "127.0.0.1")  # passed on by the start page for a visitor outside
    assert p.external({proxyauth.OUTSIDE_HEADER: "1"}, "192.168.1.50")  # from anyone: it can only take away


def test_behind_the_start_page_an_app_still_knows_where_its_visitor_is():
    """A reverse proxy on another machine is listed, this machine is not: what the start page passes on from this
    machine is still read for the visitor's address, as the Forwarded middleware reads it."""
    db.set_setting("auth_proxy_trusted", "10.0.0.5", "")
    db.settings_cache.clear()
    p = proxyauth.Proxy("iocalendar")
    door = {"x-forwarded-proto": "https", "x-forwarded-host": "home.example.com", "x-forwarded-prefix": "/calendar"}
    assert not p.external({**door, "x-forwarded-for": "192.168.1.20, 10.0.0.5"}, "127.0.0.1"), "a visitor on the network"
    assert p.external({**door, "x-forwarded-for": "8.8.8.8, 10.0.0.5"}, "127.0.0.1"), "a visitor outside"
    assert not p.external({**door, "x-forwarded-for": "192.168.1.20"}, "127.0.0.1"), "straight to the start page"
    assert p.external({**door, "x-forwarded-for": "192.168.1.20"}, "192.168.1.9"), "a proxy nobody listed is still not believed"

    class R:
        scope = {"iothing.peer": "127.0.0.1"}
        client = None
        headers = {"x-forwarded-for": "1.2.3.4, 8.8.8.8, 10.0.0.5"}
    assert p.visitor_of(R) == "8.8.8.8 via 127.0.0.1", "the sign-in throttle counts by the visitor, not by this machine"
    assert not p.from_trusted("127.0.0.1"), "who is signed in is still only a listed proxy's word"
