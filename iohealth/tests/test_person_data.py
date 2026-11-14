"""Deleting someone in Settings › Security removes all their health data here, and nobody else's."""
from iosuite_shared import users

from app import db, persondata
from iosuite_shared import testing


def _sample(uid, n):
    db.ex("INSERT INTO hlt_samples (uuid, type, kind, start_date, end_date, value, unit, user_id) "
          "VALUES (%s, 'step_count', 'quantity', '2026-10-01 08:00', '2026-10-01 08:01', 12, 'count', %s)", (f"s-{uid}-{n}", uid))


def test_deleting_someone_removes_their_health_data(client, admin):
    assert testing.add_account(client, {"name": "sam", "password": "secretpw2", "role": "member"}).status_code == 200
    sam = users.find("sam")["id"]
    for n in range(3):
        _sample(sam, n)
    _sample(admin["id"], 0)
    db.ex("INSERT INTO hlt_activity_summaries (date, user_id) VALUES ('2026-10-01', %s)", (sam,))
    db.ex("INSERT INTO hlt_user_settings (name, value, user_id) VALUES ('goal', '1', %s)", (sam,))
    got = {i["what"]: i["count"] for i in client.get(f"/api/suite-admin/person-data/{sam}").json()["items"]}
    assert got["health samples"] == 3 and got["day of activity rings"] == 1 and any(k.startswith("other record") for k in got)
    assert client.delete(f"/api/suite-admin/users/{sam}").status_code == 200
    for t in persondata._tables():
        assert db.one(f"SELECT count(*) FROM {t} WHERE user_id = %s", (sam,))[0] == 0, t
    assert db.one("SELECT count(*) FROM hlt_samples WHERE user_id = %s", (admin["id"],))[0] == 1
