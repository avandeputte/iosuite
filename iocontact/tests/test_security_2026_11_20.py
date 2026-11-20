"""What the security review of 20 November 2026 settled: a relation only mirrors onto a contact the person may change,
undoing a merge needs every book it touches, ioPix's people are for members, and a contact moved a moment ago into a
book the writer cannot change is not written."""
import pytest

from app import model, users
from app.mcp import current_user
from app.mcp import read as mcp_read
from iosuite_shared.errors import Invalid
from tests.test_api import mk
from tests.test_review3 import other_account


def _private(client):
    return next(b["id"] for b in client.get("/api/books").json()["items"] if not b["shared"])


def test_a_relation_does_not_change_a_contact_in_a_book_one_only_reads(client, family_id):
    dad = mk(client, family_id, fn="Dad Lee")["id"]
    kid = other_account(client, "kid", "member")  # sees Family, cannot change it
    own = next(b["id"] for b in kid.get("/api/books").json()["items"] if not b["shared"])
    r = kid.post(f"/api/contacts?book={own}", json={"fn": "Me", "relations": [{"type": "parent", "relatedId": dad, "gender": "M"}]})
    assert r.status_code == 201 and r.json()["relations"][0]["relatedId"] == dad
    d = client.get(f"/api/contacts/{dad}").json()
    assert d["relations"] == [] and not d.get("gender")
    # an editor's relation is mirrored, as before
    ed = other_account(client, "ed", "editor")
    son = ed.post(f"/api/contacts?book={family_id}", json={"fn": "Son Lee", "relations": [{"type": "parent", "relatedId": dad}]}).json()["id"]
    assert [x["relatedId"] for x in client.get(f"/api/contacts/{dad}").json()["relations"]] == [son]


def test_undoing_a_merge_needs_every_book_it_touches(client, family_id):
    a = mk(client, family_id, fn="Ann Lee")["id"]
    b = mk(client, _private(client), fn="Annie Lee")["id"]
    assert client.post("/api/contacts/merge", json={"keep": a, "others": [b]}).status_code == 200
    mid = client.get("/api/merges").json()["items"][0]["id"]
    ed = other_account(client, "ed", "editor")  # changes Family, never sees alex's private book
    assert ed.post(f"/api/merges/{mid}/undo").status_code == 403
    assert client.post(f"/api/merges/{mid}/undo").status_code == 200


def test_iopix_people_over_mcp_are_for_members(client):
    other_account(client, "viv", "viewer")
    current_user.set(users.find("viv"))
    with pytest.raises(Exception, match="members"):
        mcp_read.list_iopix_people()


def test_a_contact_moved_away_a_moment_ago_is_not_written(client, family_id):
    cid = mk(client, family_id, fn="Shared One")["id"]
    other_account(client, "ed", "editor")
    c = model.full(cid)  # what ed's request read, when the contact was still in Family
    model.move(cid, _private(client))  # alex moves it to their private book (no viewer here: the model, unchecked)
    tok = model.viewer.set(users.find("ed"))
    try:
        with pytest.raises(Invalid):
            model.save(family_id, c, cid)  # would have moved it back into Family
        with pytest.raises(Invalid):
            model.move(cid, family_id)
        with pytest.raises(Invalid):
            model.set_fields(cid, favorite=1)
        with pytest.raises(Invalid):
            model.delete(cid)
    finally:
        model.viewer.reset(tok)
    assert model.get_row(cid)["address_book_id"] == _private(client) and not model.get_row(cid)["deleted"]
