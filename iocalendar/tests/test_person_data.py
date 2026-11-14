"""Deleting someone in Settings › Security removes their private calendars here; their events on the Family calendar stay."""
from iosuite_shared import related, users

from app import db
from iosuite_shared import testing


def _as(client, name, password="secret123"):
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200
    return users.find(name)["id"]


def test_deleting_someone_removes_their_calendars_and_keeps_the_family_ones(client, family_id):
    assert testing.add_account(client, {"name": "ann", "password": "secret123", "role": "editor"}).status_code == 200
    ann = _as(client, "ann")
    mine = next(c["id"] for c in client.get("/api/calendars").json()["items"] if c["mine"])
    own = [client.post(f"/api/events?calendar={mine}", json={"title": t, "start": "2026-11-10T10:00"}).json()["id"] for t in ("Dentist", "Gym")]
    party = client.post(f"/api/events?calendar={family_id}", json={"title": "Party", "start": "2026-11-12T18:00"}).json()["id"]
    related.add(("event", own[0]), ("event", party))
    _as(client, "alex")
    got = client.get(f"/api/suite-admin/person-data/{ann}").json()["items"]
    assert {i["what"]: (i["count"], i["kept"]) for i in got} == {
        "private calendar": (1, False), "events in them": (2, False), "event they added to a shared calendar": (1, True)}
    r = client.delete(f"/api/suite-admin/users/{ann}")
    assert r.status_code == 200, r.text
    assert not db.q("SELECT id FROM cal_calendars WHERE owner_id = %s", (ann,))
    assert related.of("event", party) == []  # the link to her private event went with it
    assert [e["title"] for e in db.q("SELECT summary AS title FROM cal_events WHERE calendar_id = %s AND deleted = 0", (family_id,))] == ["Party"]
    assert client.get(f"/api/suite-admin/person-data/{ann}").json()["items"] == [
        {"what": "event they added to a shared calendar", "count": 1, "kept": True}]
