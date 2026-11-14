"""What the code review of 14 November 2026 settled: a merge finds relations again in every book the person merging
reads, a merge can be undone for 30 days (and not once its contacts are gone for good), and a deleted address book
takes its contacts' links to other items of the suite along."""
from iosuite_shared import related

from app import db, quality
from tests.test_api import mk


def _private(client):
    return next(b["id"] for b in client.get("/api/books").json()["items"] if not b["shared"])


def test_a_merge_keeps_a_relation_to_a_contact_in_another_book(client, family_id):
    mom = mk(client, _private(client), fn="Mom Lee")["id"]
    a = mk(client, family_id, fn="Ann Lee")["id"]
    b = mk(client, family_id, fn="Annie Lee", relations=[{"type": "parent", "relatedId": mom}])["id"]
    pv = client.get(f"/api/merge/preview?ids={a},{b}&keep={a}").json()
    out = client.post("/api/contacts/merge", json={"keep": a, "others": [b], "result": pv["merged"]}).json()
    assert [(r["type"], r.get("relatedId")) for r in out["relations"]] == [("parent", mom)]


def test_a_merge_can_be_undone_for_30_days_and_while_its_contacts_are_there(client, family_id):
    def merge(x, y):
        a, b = mk(client, family_id, fn=x)["id"], mk(client, family_id, fn=y)["id"]
        assert client.post("/api/contacts/merge", json={"keep": a, "others": [b]}).status_code == 200
        return a, b

    merge("Old One", "Old Two")
    _, gone = merge("Kept", "Purged")
    merge("New One", "New Two")
    hist = client.get("/api/merges").json()["items"]
    assert [m["canUndo"] for m in hist] == [True, True, True] and all(m["until"] for m in hist)
    db.ex("UPDATE con_contact_merges SET created_at = NOW() - INTERVAL 31 DAY WHERE names LIKE 'Old%%'")
    db.ex("DELETE FROM con_contacts WHERE id = %s", (gone,))  # the deletion marker was purged
    by = {m["names"]: m for m in client.get("/api/merges").json()["items"]}
    assert not by["Kept, Purged"]["canUndo"]
    assert client.post(f"/api/merges/{by['Kept, Purged']['id']}/undo").status_code == 409
    assert quality.purge_merges() == 2
    assert [m["names"] for m in client.get("/api/merges").json()["items"]] == ["New One, New Two"]


def test_the_daily_chore_purges_markers_and_merges(client, family_id):
    a, b = mk(client, family_id, fn="One")["id"], mk(client, family_id, fn="Two")["id"]
    client.post("/api/contacts/merge", json={"keep": a, "others": [b]})
    db.ex("UPDATE con_contacts SET updated_at = NOW() - INTERVAL 400 DAY WHERE id = %s", (b,))
    quality.housekeeping()
    assert not db.q("SELECT id FROM con_contacts WHERE id = %s", (b,))
    assert client.get("/api/merges").json()["items"] == []


def test_a_deleted_book_takes_the_links_along(client, family_id):
    book = client.post("/api/books", json={"name": "Club"}).json()
    bid = book.get("id") or book["book"]["id"]
    c = mk(client, bid, fn="Coach")["id"]
    related.add(("contact", c), ("event", "7"))
    assert client.delete(f"/api/books/{bid}").status_code == 200
    assert related.of("contact", c) == []
