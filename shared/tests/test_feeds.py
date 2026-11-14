"""Subscription links (iosuite_shared.feeds): kept as a hash in the Shared ioSuite database, one app's only, stopped
one at a time, gone with the account; and the request log never shows the secret in those addresses."""
import logging

import pytest

from iosuite_shared import db, feeds, users
from iosuite_shared.errors import Invalid
from iosuite_shared.updates import SecretPaths


def test_a_link_is_a_hash_for_one_person_and_one_app():
    ann = users.create("ann", "secret123")
    bob = users.create("bob", "secret123")
    a = feeds.create(ann["id"], "iocalendar", "iPad")
    b = feeds.create(ann["id"], "iocalendar", "")
    c = feeds.create(bob["id"], "iocontact", "Kitchen")
    assert a not in str(db.q("SELECT * FROM ios_feed_tokens"))
    assert feeds.user_id("iocalendar", a) == ann["id"] and feeds.user_id("iocalendar", b) == ann["id"]
    assert feeds.user_id("iocontact", a) is None and feeds.user_id("iocalendar", c) is None  # another app's link
    assert feeds.user_id("iocalendar", "nope") is None and feeds.user_id("iocalendar", "") is None
    mine = feeds.list_for(ann["id"], "iocalendar")
    assert [f["label"] for f in mine] == ["iPad", "Subscription"] and mine[0]["lastUsed"]
    assert feeds.delete(bob["id"], "iocalendar", mine[0]["id"]) == 0  # not his
    assert feeds.delete(ann["id"], "iocalendar", mine[0]["id"]) == 1
    assert feeds.user_id("iocalendar", a) is None and feeds.user_id("iocalendar", b) == ann["id"]
    users.delete(ann["id"])
    assert feeds.user_id("iocalendar", b) is None and db.one("SELECT count(*) AS n FROM ios_feed_tokens")["n"] == 1


def test_a_page_cannot_fill_the_table(monkeypatch):
    ann = users.create("ann", "secret123")
    monkeypatch.setattr(feeds, "MAX_PER_PERSON", 2)
    feeds.create(ann["id"], "iocalendar", "1")
    feeds.create(ann["id"], "iocalendar", "2")
    with pytest.raises(Invalid):
        feeds.create(ann["id"], "iocalendar", "3")
    feeds.create(ann["id"], "iocontact", "1")  # per app


def test_the_request_log_hides_the_secret_in_those_addresses():
    for path, shown in (("/ics/abc123/all.ics?member=Ann", "/ics/-/all.ics?member=Ann"), ("/calendar/ics/abc123/x.ics", "/calendar/ics/-/x.ics"),
                        ("/cal/abc123/family.ics", "/cal/-/family.ics"), ("/profile/abc123/ioContact.mobileconfig", "/profile/-/ioContact.mobileconfig")):
        rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("10.0.0.5:1234", "GET", path, "1.1", 200), None)
        assert SecretPaths().filter(rec) is True
        assert "abc123" not in rec.getMessage() and shown in rec.getMessage()
    plain = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d', ("10.0.0.5:1234", "GET", "/api/calendars", "1.1", 200), None)
    SecretPaths().filter(plain)
    assert "/api/calendars" in plain.getMessage()
