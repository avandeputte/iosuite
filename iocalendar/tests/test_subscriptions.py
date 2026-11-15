"""Outside calendars subscribed to by their web address (kind 'subscribed', app/subscribe.py): fetched safely, kept
read-only, brought in line on refresh, and managed only by those who could change such a calendar."""
import http.server
import threading

import pytest

from app import db, subscribe
from iosuite_shared import testing

FEED = {"status": 200, "body": "", "etag": None, "redirect": None, "type": "text/calendar; charset=utf-8", "hits": 0, "inm": []}


def ics(*events, name="Riverside School"):
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//School//Agenda//EN", f"X-WR-CALNAME:{name}", "X-WR-TIMEZONE:Europe/Brussels"]
    for uid, title, start in events:
        out += ["BEGIN:VEVENT", f"UID:{uid}", "DTSTAMP:20260101T000000Z", f"DTSTART;VALUE=DATE:{start}", f"SUMMARY:{title}",
                "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:x", "TRIGGER:-PT15M", "END:VALARM", "END:VEVENT"]
    return "\r\n".join(out + ["END:VCALENDAR", ""])


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        FEED["hits"] += 1
        FEED["inm"].append(self.headers.get("If-None-Match"))
        if FEED["redirect"]:
            self.send_response(302)
            self.send_header("Location", FEED["redirect"])
            self.end_headers()
            return
        if FEED["etag"] and self.headers.get("If-None-Match") == FEED["etag"]:
            self.send_response(304)
            self.end_headers()
            return
        body = FEED["body"].encode()
        self.send_response(FEED["status"])
        self.send_header("Content-Type", FEED["type"])
        if FEED["etag"]:
            self.send_header("ETag", FEED["etag"])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def feed_url():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/school.ics"
    srv.shutdown()


@pytest.fixture()
def feed(feed_url, monkeypatch):
    FEED.update(status=200, body=ics(("a@school", "Parents' evening", "20261120"), ("b@school", "Sports day", "20261125")),
                etag=None, redirect=None, type="text/calendar; charset=utf-8", hits=0, inm=[])
    monkeypatch.setattr(subscribe, "ALLOWED", lambda ip: ip.is_loopback)  # the tests' own server, on this machine
    return feed_url


def titles(client, cid, start="2026-11-01", end="2026-12-01"):
    return [i["title"] for i in client.get("/api/occurrences", params={"start": start, "end": end, "calendars": cid}).json()["items"]]


def test_addresses_are_cleaned():
    assert subscribe.clean_url(" webcal://example.com/a.ics#x ") == "https://example.com/a.ics"
    assert subscribe.clean_url("WEBCALS://example.com/a.ics") == "https://example.com/a.ics"
    for bad in ("", "ftp://example.com/a.ics", "file:///etc/passwd", "https://user:pw@example.com/a.ics", "example.com/a.ics"):
        with pytest.raises(ValueError):
            subscribe.clean_url(bad)


def test_only_the_internet_is_fetched(client, feed_url):
    """By default the server reaches hosts on the internet only: not itself, the home network or link-local."""
    r = client.post("/api/subscriptions", json={"url": feed_url, "shared": True})
    assert r.status_code == 400 and "home network" in r.json()["detail"], r.text
    assert not [c for c in client.get("/api/calendars").json()["items"] if c["kind"] == "subscribed"]
    for url in ("http://169.254.169.254/latest/meta-data", "http://10.0.0.1/a.ics", "http://[::1]/a.ics"):
        assert client.post("/api/subscriptions", json={"url": url}).status_code == 400


def test_a_redirect_is_checked_like_the_first_address(client, feed):
    FEED["redirect"] = "http://169.254.169.254/latest/meta-data"
    r = client.post("/api/subscriptions", json={"url": feed})
    assert r.status_code == 400 and "home network" in r.json()["detail"], r.text
    FEED["redirect"] = "file:///etc/passwd"
    assert client.post("/api/subscriptions", json={"url": feed}).status_code == 400


def test_subscribe_refresh_and_remove(client, feed, family_id):
    r = client.post("/api/subscriptions", json={"url": feed, "shared": True, "refreshHours": 12})
    assert r.status_code == 201, r.text
    c = r.json()["calendar"]
    assert c["kind"] == "subscribed" and c["shared"] and not c["writable"] and c["name"] == "Riverside School" and c["count"] == 2
    assert c["timezone"] == "Europe/Brussels"
    assert c["subscription"]["url"] == feed and c["subscription"]["refreshHours"] == 12 and c["subscription"]["manage"]
    assert titles(client, c["id"]) == ["Parents' evening", "Sports day"]
    ev = client.get("/api/occurrences", params={"start": "2026-11-20", "end": "2026-11-21", "calendars": c["id"]}).json()["items"][0]
    assert "VALARM" not in db.one("SELECT ics FROM cal_events WHERE id = %s", (ev["id"],))["ics"]  # outside reminders do not ring on the family's phones
    # nobody adds or changes events in it; the family calendar is still first
    assert client.post(f"/api/events?calendar={c['id']}", json={"title": "x", "start": "2026-11-21"}).status_code == 403
    assert client.patch(f"/api/events/{ev['id']}", json={"title": "x"}).status_code == 403
    cals = client.get("/api/calendars").json()["items"]
    assert cals[0]["id"] == family_id and any(x["id"] == c["id"] for x in cals)
    # its name and colour are the family's to choose
    assert client.patch(f"/api/calendars/{c['id']}", json={"name": "School", "color": "#00aa00"}).json()["calendar"]["name"] == "School"

    # the school changes its calendar: one moved, one gone, one new
    FEED["body"] = ics(("a@school", "Parents' evening (moved)", "20261121"), ("c@school", "Winter concert", "20261128"))
    FEED["etag"] = '"v2"'
    r = client.post(f"/api/subscriptions/{c['id']}/refresh").json()
    assert r["ok"] and r["events"] == 2 and r["changed"] == 3, r
    assert titles(client, c["id"]) == ["Parents' evening (moved)", "Winter concert"]
    # not changed since: the server says so (If-None-Match) and nothing moves
    r = subscribe.refresh(c["id"])
    assert r["ok"] and r.get("notModified") and FEED["inm"][-1] == '"v2"'
    # it fails for a while: the events stay, the error is noted
    FEED.update(status=500, etag=None)
    r = client.post(f"/api/subscriptions/{c['id']}/refresh").json()
    assert not r["ok"] and "500" in r["error"]
    sub = next(x for x in client.get("/api/calendars").json()["items"] if x["id"] == c["id"])["subscription"]
    assert "500" in sub["error"] and sub["events"] == 2
    assert titles(client, c["id"]) == ["Parents' evening (moved)", "Winter concert"]
    FEED.update(status=200, body="<html>not a calendar</html>", type="text/html")
    assert "does not give a calendar" in client.post(f"/api/subscriptions/{c['id']}/refresh").json()["error"]

    # the schedule: a subscription is fetched again once its hours have passed
    FEED.update(body=ics(("d@school", "Book fair", "20261126")), type="text/calendar")
    assert subscribe.tick() == 0  # just tried
    db.ex("UPDATE cal_subscriptions SET checked_at = UTC_TIMESTAMP() - INTERVAL 13 HOUR WHERE calendar_id = %s", (c["id"],))
    assert subscribe.tick() == 1 and titles(client, c["id"]) == ["Book fair"]

    # a wrong new address leaves the old one; a good one replaces it; refreshHours from the list only
    assert client.patch(f"/api/subscriptions/{c['id']}", json={"url": "http://10.1.2.3/x.ics"}).status_code == 400
    assert client.patch(f"/api/subscriptions/{c['id']}", json={"refreshHours": 5}).status_code == 400
    r = client.patch(f"/api/subscriptions/{c['id']}", json={"url": feed + "?v=2", "refreshHours": 24}).json()
    assert r["calendar"]["subscription"]["url"] == feed + "?v=2" and r["calendar"]["subscription"]["refreshHours"] == 24 and r["sync"]["ok"]

    assert client.delete(f"/api/calendars/{c['id']}").status_code == 200
    assert db.one("SELECT count(*) AS n FROM cal_subscriptions")["n"] == 0


def test_what_is_not_a_calendar_makes_nothing(client, feed):
    FEED.update(body="hello", type="text/plain")
    r = client.post("/api/subscriptions", json={"url": feed, "name": "x"})
    assert r.status_code == 400 and "does not give a calendar" in r.json()["detail"]
    FEED.update(status=404)
    assert "404" in client.post("/api/subscriptions", json={"url": feed}).json()["detail"]
    assert not [c for c in client.get("/api/calendars").json()["items"] if c["kind"] == "subscribed"]


def test_who_manages_an_outside_calendar(client, feed):
    shared = client.post("/api/subscriptions", json={"url": feed, "shared": True, "name": "Bins"}).json()["calendar"]
    assert testing.add_account(client, {"name": "kid", "password": "kidpass99", "role": "member"}).status_code == 200
    assert testing.add_account(client, {"name": "vic", "password": "vicpass99", "role": "viewer"}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "kid", "password": "kidpass99"}).status_code == 200
    # a member sees the shared one, without its address, and cannot change it
    c = next(x for x in client.get("/api/calendars").json()["items"] if x["id"] == shared["id"])
    assert c["subscription"]["url"] is None and c["subscription"]["host"] == "127.0.0.1" and not c["subscription"]["manage"]
    assert client.patch(f"/api/subscriptions/{c['id']}", json={"refreshHours": 1}).status_code == 403
    assert client.post(f"/api/subscriptions/{c['id']}/refresh").status_code == 403
    assert client.delete(f"/api/calendars/{c['id']}").status_code == 403
    assert client.post("/api/subscriptions", json={"url": feed, "shared": True}).status_code == 403
    # ...but subscribes privately; the Personal calendar is still made, and the private one can go again
    mine = client.post("/api/subscriptions", json={"url": feed, "name": "Football"}).json()["calendar"]
    assert not mine["shared"] and mine["subscription"]["manage"]
    cals = client.get("/api/calendars").json()["items"]
    assert any(x["kind"] == "events" and not x["shared"] for x in cals)
    assert client.delete(f"/api/calendars/{mine['id']}").status_code == 200
    # a viewer only looks
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "vic", "password": "vicpass99"}).status_code == 200
    assert client.post("/api/subscriptions", json={"url": feed}).status_code == 403
    assert titles(client, shared["id"]) == ["Parents' evening", "Sports day"]
