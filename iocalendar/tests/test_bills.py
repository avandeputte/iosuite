"""The household's bills from ioMoney on the calendar: asked for as the viewer, shown on the day they are due, and
nothing at all for someone without a role in ioMoney."""
import io
import json
import urllib.error

import pytest
from iosuite_shared import sessions, suite

from app import bills

BILLS = {"currency": "USD", "items": [
    {"id": 3, "day": "2026-11-20", "merchant": "Power Co", "amount": -118.5, "currency": "USD", "approximate": True,
     "frequency": "monthly", "category": "Utilities", "accountId": 1, "account": "Checking", "paid": False},
    {"id": 2, "day": "2026-11-10", "merchant": "Mortgage", "amount": -2100, "currency": "USD", "approximate": False,
     "frequency": "monthly", "category": "Mortgage", "accountId": 1, "account": "Checking", "paid": True,
     "transactionId": 77},
    {"id": 4, "day": "2026-12-01", "merchant": "Later", "amount": -5, "approximate": False, "paid": False}]}


@pytest.fixture()
def iomoney(client, monkeypatch):
    """ioMoney in the suite's list of apps, answering from here: the requests it got, and what it answers."""
    bills.forget()
    suite.register("iomoney", name="ioMoney", url="https://money.example.org", version="1")
    seen, answer = [], {"got": BILLS}

    def fake(req, timeout):
        seen.append({"path": req.full_url.split("example.org", 1)[1], "headers": {k.lower(): v for k, v in req.header_items()}})
        if isinstance(answer["got"], Exception):
            raise answer["got"]
        return Answer(json.dumps(answer["got"]).encode())
    monkeypatch.setattr(bills.links, "call", fake)
    yield seen, answer
    bills.forget()


class Answer(io.BytesIO):
    headers = {"Content-Type": "application/json"}


def test_without_iomoney_the_calendar_has_no_bills(client):
    bills.forget()
    assert client.get("/api/status").json()["iomoney"] is False
    r = client.get("/api/bills?start=2026-11-09&end=2026-11-30").json()
    assert r["available"] is False and r["items"] == [] and "not part of the suite" in r["reason"]


def test_bills_are_asked_for_as_the_viewer(client, iomoney):
    seen, _ = iomoney
    assert client.get("/api/status").json()["iomoney"] is True
    r = client.get("/api/bills?start=2026-11-09&end=2026-11-30").json()
    assert r["available"] is True and r["url"] == "https://money.example.org"
    assert [b["merchant"] for b in r["items"]] == ["Mortgage", "Power Co"]  # by day; one after the days asked is left out
    assert r["items"][1] == {"id": 3, "day": "2026-11-20", "merchant": "Power Co", "amount": -118.5, "currency": "USD",
                             "approximate": True, "frequency": "monthly", "category": "Utilities", "account": "Checking", "paid": False,
                             "transactionId": None}
    assert r["items"][0]["transactionId"] == 77  # the payment: its links show on the bill's card
    assert "start=2026-11-09" in seen[0]["path"] and "end=2026-11-29" in seen[0]["path"]  # ioMoney's end is the last day
    assert seen[0]["headers"]["cookie"].startswith(sessions.COOKIE + "=") and "authorization" not in seen[0]["headers"]
    assert client.get("/api/bills?start=2026-11-30&end=2026-11-09").status_code == 400


def test_no_role_in_iomoney_no_bills(client, iomoney):
    _, answer = iomoney
    answer["got"] = urllib.error.HTTPError("https://money.example.org", 403, "no", {}, io.BytesIO(b'{"detail": "no access to iomoney"}'))
    r = client.get("/api/bills?start=2026-11-09&end=2026-11-30").json()
    assert r["available"] is False and r["items"] == [] and r["reason"] == "No role in ioMoney"
