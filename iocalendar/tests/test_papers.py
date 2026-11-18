"""The documents from ioDocs on the calendar: asked for as the viewer, each on the day it expires, and nothing at all
when ioDocs is not part of the suite or does not let the viewer in."""
import io
import json
import urllib.error

import pytest
from iosuite_shared import sessions, suite

from app import papers

DOCS = {"items": [
    {"id": 7, "title": "Ava's passport", "kind": "passport", "kindLabel": "Passport", "expiresOn": "2026-11-20",
     "people": [{"id": 3, "displayName": "Ava Calloway"}]},
    {"id": 2, "title": "Car insurance", "kind": "insurance", "kindLabel": "Insurance policy", "expiresOn": "2026-11-10", "people": []},
    {"id": 4, "title": "Later", "kindLabel": "Other", "expiresOn": "2026-12-01", "people": []}]}


@pytest.fixture()
def iodocs(client, monkeypatch):
    """ioDocs in the suite's list of apps, answering from here: the requests it got, and what it answers."""
    papers.forget()
    suite.register("iodocs", name="ioDocs", url="https://docs.example.org", version="1")
    seen, answer = [], {"got": DOCS}

    def fake(req, timeout):
        seen.append({"path": req.full_url.split("example.org", 1)[1], "headers": {k.lower(): v for k, v in req.header_items()}})
        if isinstance(answer["got"], Exception):
            raise answer["got"]
        return Answer(json.dumps(answer["got"]).encode())
    monkeypatch.setattr(papers.links, "call", fake)
    yield seen, answer
    papers.forget()


class Answer(io.BytesIO):
    headers = {"Content-Type": "application/json"}


def test_without_iodocs_no_documents(client):
    papers.forget()
    assert client.get("/api/status").json()["iodocs"] is False
    r = client.get("/api/papers?start=2026-11-09&end=2026-11-30").json()
    assert r["available"] is False and r["items"] == [] and "not part of the suite" in r["reason"]


def test_documents_are_asked_for_as_the_viewer(client, iodocs):
    seen, answer = iodocs
    assert client.get("/api/status").json()["iodocs"] is True
    r = client.get("/api/papers?start=2026-11-09&end=2026-11-30").json()
    assert r["available"] is True and r["url"] == "https://docs.example.org"
    assert [d["title"] for d in r["items"]] == ["Car insurance", "Ava's passport"]  # by day; one after the days asked is left out
    assert r["items"][1] == {"id": 7, "day": "2026-11-20", "title": "Ava's passport", "kind": "Passport", "members": [3]}
    assert "/api/expiring?" in seen[0]["path"] and "start=2026-11-09" in seen[0]["path"] and "end=2026-11-29" in seen[0]["path"]
    assert seen[0]["headers"]["cookie"].startswith(sessions.COOKIE + "=") and "authorization" not in seen[0]["headers"]
    assert client.get("/api/papers?start=2026-11-30&end=2026-11-09").status_code == 400
    answer["got"] = urllib.error.HTTPError("https://docs.example.org", 403, "no", {}, io.BytesIO(b'{"detail": "no access"}'))
    r = client.get("/api/papers?start=2026-11-09&end=2026-11-30").json()
    assert r["available"] is False and r["items"] == [] and r["reason"] == "No role in ioDocs"
