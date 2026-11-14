"""The second round of the code review of 14 November 2026: a picture stays with a note in the trash, the web app's
saves never lose what was typed to a slow clock, baseRev, changes to many notes keep each note's edit time, common
words in a search, and values too long for their columns."""
import time

import pytest

from app import db, notes
from helpers import NID, NID2, png


def test_a_note_comes_back_from_the_trash_with_its_picture(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "shot"})
    assert client.put(f"/api/notes/{NID}/image", content=png(), headers={"content-type": "image/png"}).status_code == 200
    assert client.delete(f"/api/notes/{NID}").status_code == 200
    assert [n["hasImage"] for n in client.get("/api/trash").json()["notes"]] == [True]
    n = client.post(f"/api/notes/{NID}/restore").json()
    assert n["hasImage"] and client.get(f"/api/notes/{NID}/image").status_code == 200
    client.delete(f"/api/notes/{NID}")
    client.post("/api/trash/empty")  # emptied: now the picture goes
    assert client.get(f"/api/notes/{NID}/image").status_code == 404


def test_an_edit_without_a_time_is_stamped_by_the_server(client, admin):
    """What the web app sends: only the fields typed. A note stamped by another device a moment ago still takes it."""
    client.put(f"/api/notes/{NID}", json={"title": "t", "body": "from the phone", "updatedAt": time.time()})
    r = client.put(f"/api/notes/{NID}", json={"body": "typed in the browser"})
    assert r.status_code == 200 and r.json()["body"] == "typed in the browser" and r.json()["title"] == "t"


def test_base_rev_decides_instead_of_the_clocks(client, admin):
    n = client.put(f"/api/notes/{NID}", json={"title": "v1", "updatedAt": 1000}).json()
    ok = client.put(f"/api/notes/{NID}", json={"title": "v2", "baseRev": n["rev"], "updatedAt": 10})  # clock far behind: fine
    assert ok.status_code == 200 and ok.json()["title"] == "v2" and ok.json()["updatedAt"] >= 1000
    stale = client.put(f"/api/notes/{NID}", json={"title": "v3", "baseRev": n["rev"], "updatedAt": time.time()})
    assert stale.status_code == 409 and stale.json()["current"]["title"] == "v2", "it started from a version that is gone"
    assert client.put(f"/api/notes/{NID}", json={"title": "x", "baseRev": "two"}).status_code == 400


def test_changes_to_many_notes_keep_each_notes_edit_time(client, admin):
    """A phone's edit made before a tag rename on the web still counts as the later edit of that note."""
    client.put(f"/api/notes/{NID}", json={"title": "a", "tags": ["old"], "updatedAt": 1000})
    client.put(f"/api/notes/{NID2}", json={"title": "b", "tags": ["old"], "updatedAt": 1000})
    rev = client.get(f"/api/notes/{NID}").json()["rev"]
    assert client.post("/api/tags/rename", json={"from": "old", "to": "new"}).json()["changed"] == 2
    after = client.get(f"/api/notes/{NID}").json()
    assert after["tags"] == ["new"] and after["rev"] > rev and after["updatedAt"] == 1000, "a new rev for the devices, the same edit time"
    r = client.put(f"/api/notes/{NID}", json={"body": "edited on the phone before the rename", "updatedAt": 2000})
    assert r.status_code == 200
    client.post("/api/tags/remove", json={"name": "new"})
    assert client.get(f"/api/notes/{NID2}").json()["updatedAt"] == 1000


@pytest.mark.skipif(not db.connect().mysql, reason="MariaDB's full-text index (IONOTE_TEST_DB=mysql)")
def test_a_search_with_a_common_word_still_finds_the_note(client, admin):
    client.put(f"/api/notes/{NID}", json={"title": "Notes for mom", "body": "What to cook about the garden party"})
    for q in ("notes for mom", "what to cook", "about the garden", "the"):
        assert [n["id"] for n in client.get("/api/notes", params={"q": q}).json()["notes"]] == [NID], q


def test_values_too_long_for_their_column_never_answer_500(client, admin):
    long_tag = "t" * 99
    n = client.put(f"/api/notes/{NID}", json={"title": "x", "sourceApp": "S" * 1000, "tags": [long_tag] + [f"tag{i:03}-" + "x" * 90 for i in range(400)]})
    assert n.status_code == 200, n.text
    assert len(n.json()["sourceApp"]) == 191 and len(n.json()["tags"]) == notes.MAX_TAGS
    assert client.put(f"/api/tags/{long_tag}/color", json={"color": "red"}).status_code == 200
    assert client.post("/api/tags/rename", json={"from": long_tag, "to": "u" * 99}).status_code == 200
    assert client.post("/api/tags/remove", json={"name": "u" * 99}).status_code == 200


def test_one_item_the_database_refuses_does_not_stop_a_push(client, admin, monkeypatch):
    real = notes.save_note

    def picky(uid, data, user, force=False):
        if data.get("title") == "bad":
            raise db.Error[0]("Data too long for column")
        return real(uid, data, user, force)
    monkeypatch.setattr(notes, "save_note", picky)
    r = client.post("/api/sync/push", json={"notes": [{"id": NID, "title": "bad", "updatedAt": 10}, {"id": NID2, "title": "good", "updatedAt": 10}]})
    assert r.status_code == 200
    assert [x["status"] for x in r.json()["notes"]] == ["error", "ok"]
