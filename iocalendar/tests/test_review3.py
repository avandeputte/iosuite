"""The lower findings of the code review of 10 November 2026: a deleted event's marker goes after a while and a client
that was away longer starts its sync over, a body that is not a JSON object is a 400, and a search by member is asked
of the database a page at a time."""
import re

import pytest

from app import db, model
from tests.test_api import mk

BASE = "/dav/calendars/alex/family/"
SYNC = '<d:sync-collection xmlns:d="DAV:"><d:sync-token>{tok}</d:sync-token><d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>'


@pytest.fixture()
def dav(client):
    pw = client.post("/api/auth/app-passwords", json={"label": "iPhone"}).json()["password"]
    return lambda method, path, body=None, **h: client.request(method, path, content=body, auth=("alex", pw), headers=h)


def _token(text: str) -> str:
    return re.search(r"<d:sync-token>([^<]+)</d:sync-token>", text).group(1)


# ---- C-9
def test_deletion_markers_go_after_a_while(client, family_id, dav):
    a = mk(client, family_id, title="Dentist", start="2026-11-12T10:00")
    b = mk(client, family_id, title="Piano", start="2026-11-13T10:00")
    before = _token(dav("REPORT", BASE, SYNC.format(tok="")).text)   # a phone that syncs now, and then stays away
    assert client.delete(f"/api/events/{a['id']}").status_code == 200
    after = _token(dav("REPORT", BASE, SYNC.format(tok=before)).text)  # a phone that heard of the deletion
    assert model.purge_deleted() == 0  # the marker is new: it stays
    r = dav("REPORT", BASE, SYNC.format(tok=before))
    assert r.status_code == 207 and "404 Not Found" in r.text
    db.ex("UPDATE cal_events SET updated_at = NOW() - INTERVAL 200 DAY WHERE id = %s", (a["id"],))
    assert model.purge_deleted() == 1 and model.get_row(a["id"]) is None and model.get_row(b["id"])
    assert model.purged_before(family_id) > 0
    # the phone that never heard of it is told to start over; the one that did carries on
    r = dav("REPORT", BASE, SYNC.format(tok=before))
    assert r.status_code == 403 and "valid-sync-token" in r.text
    assert dav("REPORT", BASE, SYNC.format(tok=after)).status_code == 207
    r = dav("REPORT", BASE, SYNC.format(tok=""))
    assert r.status_code == 207 and r.text.count("<d:response>") == 1
    assert model.purge_deleted() == 0


def test_a_deleted_calendar_takes_its_purge_mark_along(client):
    cid = client.post("/api/calendars", json={"name": "Soccer", "shared": True}).json()["calendar"]["id"]
    e = mk(client, cid, title="Match", start="2026-11-07T10:00")
    client.delete(f"/api/events/{e['id']}")
    db.ex("UPDATE cal_events SET updated_at = NOW() - INTERVAL 200 DAY WHERE id = %s", (e["id"],))
    assert model.purge_deleted() == 1 and model.purged_before(cid) > 0
    model.delete_calendar(cid)
    assert model.purged_before(cid) == 0


# ---- C-4
def test_a_body_that_is_not_an_object_is_a_400(client, family_id):
    e = mk(client, family_id, title="Dentist", start="2026-11-12T10:00")
    for method, path in (("POST", "/api/calendars"), ("PATCH", f"/api/calendars/{family_id}"), ("POST", f"/api/events?calendar={family_id}"),
                         ("PATCH", f"/api/events/{e['id']}")):
        for body in ("[1, 2]", '"text"', "12", "{not json"):
            r = client.request(method, path, content=body, headers={"Content-Type": "application/json"})
            assert r.status_code == 400, (method, path, body, r.status_code)


# ---- C-3
def test_a_search_by_member_reads_a_page_at_a_time(client, family_id, monkeypatch):
    ann = client.get("/api/members").json()["items"][0]  # the family members are the accounts: the one signed in
    for i in range(7):
        mk(client, family_id, title=f"Swim {i}", start=f"2026-11-{10 + i:02d}T10:00", members=[ann["id"]] if i % 2 else [])
    monkeypatch.setattr(model, "SEARCH_PAGE", 2)
    asked = []
    real = db.q

    def q(sql, args=None, *a, **kw):
        if "FROM cal_events e" in sql and "LIMIT" in sql:
            asked.append(sql)
        return real(sql, args, *a, **kw)
    monkeypatch.setattr(db, "q", q)
    found = model.search_rows([family_id], "", 100, {ann["id"]})
    assert sorted(r["summary"] for r in found) == ["Swim 1", "Swim 3", "Swim 5"]
    assert len(asked) >= 2  # pages of two, not everything at once
    assert len(model.search_rows([family_id], "", 2, {ann["id"]})) == 2
