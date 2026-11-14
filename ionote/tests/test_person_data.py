"""Deleting someone in Settings › Security removes all their notes here (every note is its owner's alone), and
nobody else's."""
from iosuite_shared import users

from app import db
from helpers import NID

OTHER = "BBBBBBBB-1111-2222-3333-444444444444"


def _as(client, name, password):
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": name, "password": password}).status_code == 200


def test_deleting_someone_removes_their_notes(client, admin):
    assert client.post("/api/users", json={"name": "sam", "password": "secretpw2", "role": "editor"}).status_code == 200
    client.put(f"/api/notes/{NID}", json={"title": "alex's", "updatedAt": 1})
    _as(client, "sam", "secretpw2")
    sam = users.find("sam")["id"]
    client.put(f"/api/notes/{OTHER}", json={"title": "sam's", "tags": ["work"], "updatedAt": 2})
    client.post("/api/folders", json={"name": "Sam folder"})
    client.put("/api/tags/work/color", json={"color": "blue"})
    _as(client, "alex", "secretpw1")
    got = {i["what"]: i["count"] for i in client.get(f"/api/suite-admin/person-data/{sam}").json()["items"]}
    assert got["note"] == 1 and got["folder"] == 1 and got["tag colour"] == 1
    assert client.delete(f"/api/suite-admin/users/{sam}").status_code == 200
    with db.connect() as con:
        for t in ("nts_notes", "nts_folders", "nts_tag_colors", "nts_templates", "nts_change_log"):
            assert con.execute(f"SELECT count(*) FROM {t} WHERE user_id = ?", (sam,)).fetchone()[0] == 0, t
    assert client.get(f"/api/notes/{NID}").json()["title"] == "alex's"
