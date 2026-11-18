"""What the code review of 10 November 2026 found in the start page: an app that is down is left alone for a while
instead of being waited for again and again, a tile that needs several answers asks for them at the same time, and
the answers the status keeps have a limit. (Home Assistant's part is in test_homeassistant.py.)"""
import io
import json
import time
import urllib.error

from iosuite_shared import suiteitems

from app import status, widgets
from conftest import via_providers


class Answer(io.BytesIO):
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_an_app_that_is_down_is_left_alone_for_a_while(client, monkeypatch):
    monkeypatch.setattr(widgets.links, "addresses", lambda key: ["http://127.0.0.1:8650", "http://10.0.0.5:8650"])
    tried = []

    def down(req, timeout=None):
        tried.append(req.full_url)
        raise urllib.error.URLError("refused")
    monkeypatch.setattr(widgets.links, "call", down)
    assert client.get("/api/widgets/iocontact").status_code == 502
    assert len(tried) == 2  # both addresses, once
    r = client.get("/api/widgets/iocontact")
    assert r.status_code == 502 and "a moment ago" in r.json()["detail"] and len(tried) == 2  # not asked again
    assert client.get("/api/widgets/iopix").status_code == 502 and len(tried) == 4  # another app is another matter
    # a picture that fails says nothing about the app: asked again the next time
    widgets.forget()
    assert client.get("/api/widgets/iopix/image/photo/5").status_code == 502
    n = len(tried)
    assert client.get("/api/widgets/iopix/image/photo/5").status_code == 502 and len(tried) == n + 2
    # when the time is up the app is asked again, and an answer clears it
    widgets.links._resting["iocontact"] = time.monotonic() - 1

    def up(req, timeout=None):
        tried.append(req.full_url)
        if "127.0.0.1" in req.full_url:
            raise urllib.error.URLError("refused")
        return Answer(json.dumps({"items": []}).encode())
    monkeypatch.setattr(widgets.links, "call", up)
    del tried[:]
    assert client.get("/api/widgets/iocontact").status_code == 200
    assert [u.split("/api")[0] for u in tried] == ["http://127.0.0.1:8650", "http://10.0.0.5:8650"]
    # the address that answered is asked first from now on
    del tried[:]
    assert client.get("/api/widgets/iocontact").status_code == 200
    assert [u.split("/api")[0] for u in tried] == ["http://10.0.0.5:8650"]


def test_a_tile_asks_for_its_answers_at_the_same_time(client, monkeypatch):
    """The app's provider asks its own API for a tile's answers at the same time (local.together)."""
    def slow(reply):
        def f(p):
            time.sleep(0.3)
            return reply
        return f
    table = {("iohealth", "/api/series"): slow({"points": []}), ("iohealth", "/api/sleep"): slow({"items": []}),
             ("iohealth", "/api/activity"): slow({"items": []}),
             ("iocalendar", "/api/calendars"): slow({"items": []}), ("iocalendar", "/api/occurrences"): slow({"items": []})}
    monkeypatch.setattr(widgets, "fetch", via_providers(table, []))
    t = time.time()
    assert client.get("/api/widgets/iohealth").status_code == 200
    assert time.time() - t < 0.75  # three answers of 0.3 s each, together
    t = time.time()
    assert client.get("/api/widgets/iocalendar?kind=week").status_code == 200
    assert time.time() - t < 0.55


def test_one_failing_answer_still_shows_the_others(client, monkeypatch):
    def broken(p):
        raise suiteitems.Unavailable(502, "ioHealth answered 500")
    table = {("iohealth", "/api/activity"): broken, ("iohealth", "/api/series"): {"points": []},
             ("iohealth", "/api/sleep"): [{"date": "2026-11-10", "asleep": 431.6, "inBed": 470, "start": "x", "end": "y"}]}
    monkeypatch.setattr(widgets, "fetch", via_providers(table, []))
    d = client.get("/api/widgets/iohealth").json()
    assert d["rings"] is None and d["sleep"]["asleep"] == 432 and len(d["week"]) == 7


def test_the_status_keeps_a_limited_number_of_answers():
    status.forget()
    for i in range(status.MAX_KEPT + 500):
        status._remember(("app", "iopix", f"viewer{i}", "host"), 60, lambda: {"ok": True})
    assert len(status._cache) <= status.MAX_KEPT
    assert ("app", "iopix", f"viewer{status.MAX_KEPT + 499}", "host") in status._cache  # the newest are the ones kept
    status.forget()
