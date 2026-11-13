"""The lower findings of the code review of 10 November 2026: a time no calendar reaches and a time that is not text
are a 400, a type's kind is asked per account, an error reply carries `detail` alone, and the queries inside a
transaction run in it."""
import gzip

import pytest

from app import db, rollup, upload as up, webapi
from tests.test_api import T0, app_password, ndjson, sample, upload


def _batch(client, token, *msgs):
    sid = client.post("/v1/sessions", json={"deviceName": "aphone"}, headers={"Authorization": f"Bearer {token}"}).json()["sessionId"]
    return client.post(f"/v1/sessions/{sid}/items", content=gzip.compress(ndjson(*msgs)),
                       headers={"Authorization": f"Bearer {token}", "X-Batch-Seq": "1", "Content-Encoding": "gzip"})


# ---- H-2
def test_a_time_no_calendar_reaches_is_a_400(client, admin):
    for bad in ("99999999999999999999", "-99999999999999999999", "1e400", "2026-13-45"):
        r = client.get("/api/series", params={"type": "step_count", "from": bad})
        assert r.status_code == 400 and "bad" in r.json()["detail"], (bad, r.status_code, r.text)
    assert client.get("/api/series", params={"type": "step_count", "from": "1790000000", "to": "1790086400"}).status_code == 200


def test_a_time_that_is_not_text_is_a_400(client, admin):
    tok = app_password(client)
    for start in (12345, ["2026-10-01"], None):
        m = sample("11111111-1111-1111-1111-111111111111", "step_count", T0, 10)
        m["sample"]["_0"]["start"] = start
        r = _batch(client, tok, m)
        assert r.status_code == 400 and "line 1" in r.json()["detail"], (start, r.status_code, r.text)
    assert db.one("SELECT COUNT(*) FROM hlt_samples")[0] == 0
    with pytest.raises(ValueError):
        up.parse_time(12345)
    assert up.parse_time(None) is None
    t = rollup.Touched()
    t.add("step_count", None)  # nothing to place in an hour
    assert t.hours == set()


def test_a_types_kind_is_asked_per_account(client, admin):
    tok = app_password(client)
    upload(client, tok, sample("22222222-2222-2222-2222-222222222222", "mindful_session", T0, None, kind="category"))
    me = int(admin["id"])
    assert webapi.kind_of(me, "mindful_session") == "category"
    assert webapi.kind_of(me + 1, "mindful_session") == ""  # another account has none: nothing learnt from this one's
    assert (me, "mindful_session") in webapi._kinds and all(isinstance(k, tuple) for k in webapi._kinds)


# ---- H-3
def test_an_error_reply_carries_detail_alone(client, admin):
    r = client.get("/api/series", params={"type": "step_count", "from": "nonsense"})
    assert r.status_code == 400 and set(r.json()) == {"detail"}
    r = client.get("/api/workouts/nope")
    assert r.status_code == 404 and set(r.json()) == {"detail"}


def test_queries_inside_a_transaction_run_in_it(client, admin):
    with pytest.raises(RuntimeError):
        with db.tx():
            db.ex("INSERT INTO hlt_user_settings (user_id, name, value) VALUES (%s, 'k', '1')", (int(admin["id"]),))
            assert db.one("SELECT value FROM hlt_user_settings WHERE name = 'k'")[0] == "1"  # seen: the same transaction
            assert db.qd("SELECT name FROM hlt_user_settings WHERE name = 'k'") == [{"name": "k"}]
            raise RuntimeError("undo")
    assert db.one("SELECT COUNT(*) FROM hlt_user_settings WHERE name = 'k'")[0] == 0
    assert not hasattr(db, "pending") and not hasattr(rollup, "utcnow")
