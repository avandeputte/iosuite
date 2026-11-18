"""ioMoney and ioDocs on their tiles and in the search box, ioPix in the search box, a task and a note from the search box, and the
Bookmarks page's Tidy up (dead links, moved ones, the same address twice). The apps' answers are mocked; the link
check asks a server made here."""
import datetime as dt
from zoneinfo import ZoneInfo
import http.server
import threading
import time
import unittest.mock as um

import pytest

from app import bookmarkcheck, widgets
from conftest import via_providers


@pytest.fixture()
def answers(monkeypatch):
    """The request to an app replaced by a table: {(key, path): reply or callable(params)}; what was asked, and the
    bodies sent, are kept."""
    table, asked, sent = {}, [], []

    monkeypatch.setattr(widgets, "fetch", via_providers(table, asked, sent, cookie=False))
    widgets.forget()
    return table, asked, sent


# ------------------------------------------------------------------ ioMoney

def _bill(day, name, amount, **more):
    return {"id": 1, "day": day, "merchant": name, "amount": amount, "currency": "USD", "approximate": False, "frequency": "Monthly",
            "category": None, "accountId": 1, "account": "Checking", "subscription": False, "paid": False, **more}


def test_money_tile_bills_low_and_behind(client, answers):
    table, asked, _ = answers
    today = dt.datetime.now(ZoneInfo("Europe/Brussels")).date()
    d = [(today + dt.timedelta(days=i)).isoformat() for i in range(8)]
    table[("iomoney", "/api/bills")] = {"currency": "USD", "items": [
        _bill(d[0], "Rent", -1800.0), _bill(d[0], "Salary", 4200.0), _bill(d[1], "Netflix", -15.99, subscription=True, paid=True),
        _bill(d[2], "Power", -92.4, approximate=True), _bill(d[4], "Gym", -35.0, subscription=True), _bill(d[6], "Phone", -40.0)]}
    table[("iomoney", "/api/forecast")] = {"items": [{"accountId": 1, "name": "Checking", "currency": "USD", "floor": 500.0, "belowOn": d[3], "low": {"day": d[5], "value": 212.5}}]}
    table[("iomoney", "/api/summary")] = {"monarch": {"configured": True, "stale": [{"id": 3, "name": "Visa", "institution": "Chase", "stale": "behind", "why": "", "refreshedAt": None}]}}
    r = client.get("/api/widgets/iomoney?tz=Europe/Brussels").json()
    # only what is still to pay, money out, the soonest first; the paid one and the salary are not bills due
    assert [b["name"] for b in r["bills"]] == ["Rent", "Power", "Gym"] and r["more"] == 1
    assert r["total"] == -1967.4 and r["currency"] == "USD"
    assert r["bills"][1]["approximate"] and r["bills"][2]["subscription"] and r["bills"][0]["account"] == "Checking"
    assert r["low"] == [{"name": "Checking", "currency": "USD", "floor": 500.0, "belowOn": d[3], "value": 212.5}]
    assert r["behind"] == [{"name": "Visa", "institution": "Chase"}]
    bills = next(p for k, path, p in asked if path == "/api/bills")
    assert bills == {"start": d[0], "end": d[7]}  # the viewer's today through a week from it


def test_money_tile_without_forecast_or_bank_links(client, answers):
    table, _, _ = answers
    table[("iomoney", "/api/bills")] = {"currency": "EUR", "items": [_bill("2026-11-20", "A", -10.0, currency="EUR"), _bill("2026-11-21", "B", -5.0, currency="USD")]}
    r = client.get("/api/widgets/iomoney").json()  # the forecast and the summary do not answer: the bills stand
    assert len(r["bills"]) == 2 and r["low"] == [] and r["behind"] == []
    assert r["total"] is None  # two currencies do not add up
    del table[("iomoney", "/api/bills")]
    assert client.get("/api/widgets/iomoney").status_code == 502


def test_money_search_payees_then_transactions(client, answers):
    table, asked, _ = answers
    table[("iomoney", "/api/payees")] = {"items": [{"payee": "Rivera Plumbing", "count": 4, "total": -1310.0, "last": "2026-10-02", "category": "Home"},
                                                   {"payee": "Plumb & Co", "count": 1, "total": -80.0, "last": "2025-01-02", "category": None}], "total": 2}
    table[("iomoney", "/api/transactions")] = {"total": 9, "sum": -1390.0, "items": [
        {"id": 7, "day": "2026-10-02", "amount": -420.0, "currency": "USD", "merchant": "Rivera Plumbing", "description": "RIVERA PLMB", "category": "Home", "account_name": "x", "account": "Checking"},
        {"id": 5, "day": "2026-06-11", "amount": -80.0, "currency": "USD", "merchant": None, "description": "PLUMB & CO 1123", "category": None, "account": "Visa"}]}
    r = client.get("/api/widgets/iomoney?q=plumb").json()
    assert [x["kind"] for x in r["items"]] == ["payee", "transaction", "transaction"]  # a payee met once is its one transaction
    p = r["items"][0]  # the suite's shape (iosuite_shared.suiteitems)
    assert (p["title"], p["text"], p["amount"], p["currency"], p["when"], p["category"]) == ("Rivera Plumbing", "all 4", -1310.0, "USD", "2026-10-02", "Home")
    assert p["href"] == "#/transactions?q=Rivera+Plumbing"
    assert r["items"][1]["id"] == "7" and r["items"][1]["amount"] == -420.0 and r["items"][2]["title"] == "PLUMB & CO 1123"
    assert r["items"][1]["href"] == "#/transaction/7" and r["items"][1]["when"] == "2026-10-02"
    assert r["more"] is True
    assert ("iomoney", "/api/transactions", {"q": "plumb", "limit": 5}) in asked


# ------------------------------------------------------------------ ioDocs

def _doc(i, title, days, state, cover=None):
    return {"id": i, "title": title, "kind": "passport", "kindLabel": "Passport", "expiresOn": "2027-01-02", "cover": cover,
            "expiry": {"on": "2027-01-02", "days": days, "state": state}, "people": [{"id": 3, "displayName": "Ava Calloway"}]}


def test_docs_tile_and_search(client, answers):
    table, asked, _ = answers
    table[("iodocs", "/api/documents")] = lambda p: {"items": [_doc(1, "Ava's passport", -2, "expired", "api/documents/1/files/4"),
                                                               _doc(2, "Car insurance", 20, "soon"), _doc(3, "Riley's license", 50, "soon")]}
    r = client.get("/api/widgets/iodocs?n=2").json()
    assert [x["title"] for x in r["items"]] == ["Ava's passport", "Car insurance"] and r["more"] == 1 and r["expired"] == 1
    assert r["items"][0] == {"id": 1, "title": "Ava's passport", "kind": "Passport", "photo": 4, "expiresOn": "2027-01-02", "days": -2,
                             "state": "expired", "people": ["Ava Calloway"]}
    assert ("iodocs", "/api/documents", {"status": "expiring", "sort": "expires", "limit": 100}) in asked
    r = client.get("/api/widgets/iodocs?q=passport").json()
    assert len(r["items"]) == 3 and r["more"] is False
    x = r["items"][0]
    assert (x["kind"], x["id"], x["title"], x["image"], x["href"]) == ("document", "1", "Ava's passport", "4", "#/doc/1")
    assert x["text"] == "Passport · Ava Calloway · expires 2027-01-02"
    assert ("iodocs", "/api/documents", {"q": "passport", "limit": 6}) in asked
    table[("iodocs", "/api/documents/1/files/4")] = (b"jpg", "image/jpeg")
    assert client.get("/api/widgets/iodocs/image/document/1", params={"p": "4"}).content == b"jpg"


# ------------------------------------------------------------------ ioPix

def _pix(table):
    table[("iopix", "/api/meta")] = {
        "tags": [{"id": 1, "name": "Ava Calloway", "person": 1, "nAll": 120, "cover": 11}, {"id": 2, "name": "Avalanche", "person": 0, "nAll": 9, "cover": 12},
                 {"id": 3, "name": "Élodie", "person": 1, "nAll": 4, "cover": 13}, {"id": 4, "name": "Nobody", "person": 1, "nAll": 0, "cover": None}],
        "albums": [{"id": 20, "name": "2024 Avignon", "nAll": 60, "cover": 21}, {"id": 21, "name": "Scans", "nAll": 5, "cover": 22}],
        "places": [["Avignon", "Provence", "France", 58, 31], ["Eugene", "Oregon", "United States", 300, 32]]}
    table[("iopix", "/api/state")] = {"albums": [{"id": 5, "name": "Ava's birthday", "n": 14, "cover": 41}]}


def test_pix_search_people_albums_folders_places(client, answers):
    table, asked, _ = answers
    _pix(table)
    r = client.get("/api/widgets/iopix?q=av").json()["items"]
    assert [(x["kind"], x["title"]) for x in r] == [("person", "Ava Calloway"), ("album", "Ava's birthday"), ("folder", "2024 Avignon"), ("place", "Avignon, Provence")]
    assert r[0]["id"] == "1" and r[0]["text"] == "Person · 120 photos" and r[0]["image"] == "11" and r[0]["round"]  # a tag that is not a person is not found
    assert r[0]["href"] == "#/photos?tag=1" and r[3]["href"] == "#/photos?place=Avignon&region=Provence" and r[3]["image"] == "31"
    assert [x["title"] for x in client.get("/api/widgets/iopix?q=elodie").json()["items"]] == ["Élodie"]  # accents folded
    assert [x["title"] for x in client.get("/api/widgets/iopix?q=france").json()["items"]] == ["Avignon, Provence"]  # a place by its country
    assert client.get("/api/widgets/iopix?q=zzz").json()["items"] == []
    assert len([1 for k, path, _ in asked if path == "/api/meta"]) == 1  # the names are read once for the words typed after


def test_pix_names_are_kept_per_person(client, answers):
    from iosuite_shared import testing
    table, asked, _ = answers
    _pix(table)
    assert client.get("/api/widgets/iopix?q=ava").json()["items"]
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "member"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    table[("iopix", "/api/meta")] = lambda p: (_ for _ in ()).throw(widgets.Unavailable(403, "ioPix does not let this account in"))
    assert client.get("/api/widgets/iopix?q=ava").status_code == 403  # another account never reads the first one's names


# ------------------------------------------------------------------ a task and a note from the search box

def test_quick_add_task(client, answers):
    table, _, sent = answers
    table[("iotask", "/api/lists")] = {"items": [{"id": 1, "name": "Home", "color": "#f00", "writable": True}, {"id": 2, "name": "Theirs", "color": "#0f0", "writable": False}]}
    assert client.get("/api/widgets/iotask/lists").json() == {"items": [{"id": 1, "name": "Home", "color": "#f00"}]}
    table[("iotask", "/api/tasks")] = lambda p: {"id": 9}
    r = client.post("/api/widgets/iotask/tasks", json={"title": " Buy milk ", "due": "2026-11-21", "listId": 1, "timezone": "Europe/Brussels"})
    assert r.status_code == 200 and r.json()["id"] == 9 and r.json()["url"].endswith("/#/task/9")
    assert sent[-1] == ("iotask", "/api/tasks", {"title": "Buy milk", "due": "2026-11-21", "timezone": "Europe/Brussels", "listId": 1})
    client.post("/api/widgets/iotask/tasks", json={"title": "Call", "due": "2026-11-21T09:00"})
    assert sent[-1][2] == {"title": "Call", "due": "2026-11-21T09:00"}
    client.post("/api/widgets/iotask/tasks", json={"title": "Someday"})
    assert sent[-1][2] == {"title": "Someday"}
    assert client.post("/api/widgets/iotask/tasks", json={"title": ""}).status_code == 400
    assert client.post("/api/widgets/iotask/tasks", json={"title": "x", "due": "friday"}).status_code == 400


def test_quick_add_note(client, answers):
    table, _, sent = answers
    table[("ionote", "/api/notes")] = lambda p: {"id": "3f2a"}
    r = client.post("/api/widgets/ionote/notes", json={"text": " the gate code is 4411 "})
    assert r.status_code == 200 and r.json()["url"].endswith("/#/note/3f2a")
    assert sent[-1] == ("ionote", "/api/notes", {"title": "", "body": "the gate code is 4411", "sourceApp": "ioStart"})
    assert client.post("/api/widgets/ionote/notes", json={"title": " ", "text": ""}).status_code == 400
    client.cookies.clear()
    assert client.post("/api/widgets/ionote/notes", json={"text": "x"}).status_code == 401
    assert client.post("/api/widgets/iotask/tasks", json={"title": "x"}).status_code == 401


# ------------------------------------------------------------------ Tidy up: the same address twice

def _folder(client, name, **more):
    return client.post("/api/bookmarks/groups", json={"name": name, **more}).json()["id"]


def _link(client, gid, name, href):
    r = client.post(f"/api/bookmarks/groups/{gid}/links", json={"name": name, "href": href})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_duplicates(client):
    a, b = _folder(client, "News"), _folder(client, "Old", start=False)
    one = _link(client, b, "The Verge (old)", "http://www.theverge.com/")
    two = _link(client, a, "The Verge", "https://theverge.com")
    _link(client, a, "Verge tech", "https://theverge.com/tech")
    _link(client, a, "Search", "https://example.com/?q=a")
    _link(client, b, "Search b", "https://example.com/?q=b")
    d = client.get("/api/bookmarks/duplicates").json()
    assert d["extra"] == 1 and len(d["groups"]) == 1
    links = d["groups"][0]["links"]
    assert [x["id"] for x in links] == [two, one]  # the one on the start page is the one to keep
    assert links[0]["path"] == "News" and links[1]["path"] == "Old" and all(x["canChange"] for x in links)
    client.delete(f"/api/bookmarks/links/{one}")
    assert client.get("/api/bookmarks/duplicates").json() == {"groups": [], "extra": 0}


def test_duplicates_are_each_persons_own(client):
    from iosuite_shared import testing
    g = _folder(client, "Mine")
    _link(client, g, "A", "https://a.example")
    _link(client, g, "A again", "https://a.example/")
    testing.add_account(client, {"name": "kid", "password": "secret123", "role": "member"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"name": "kid", "password": "secret123"})
    assert client.get("/api/bookmarks/duplicates").json() == {"groups": [], "extra": 0}
    assert client.get("/api/bookmarks/check").json()["items"] == []


# ------------------------------------------------------------------ Tidy up: the links that no longer work

def _wait(client):
    for _ in range(100):
        s = client.get("/api/bookmarks/check").json()
        if not s["running"]:
            return s
        time.sleep(0.05)
    raise AssertionError("the check did not finish")


def test_check_lists_dead_gone_and_moved(client, monkeypatch):
    bookmarkcheck.forget()
    assert client.get("/api/bookmarks/check").json() == {"running": False, "done": 0, "total": 0, "checkedAt": None, "offline": False, "items": []}
    g = _folder(client, "Sites")
    ids = {n: _link(client, g, n, h) for n, h in [("Fine", "https://fine.example"), ("Dead", "https://dead.example"), ("Gone", "https://gone.example/page"),
                                                 ("Moved", "http://moved.example/a"), ("Dead twice", "https://dead.example"), ("Mail", "mailto:a@b.example")]}
    asked = []

    def fake(href):
        asked.append(href)
        return {"https://dead.example": {"state": "dead", "status": None, "to": None}, "https://gone.example/page": {"state": "gone", "status": 404, "to": None},
                "http://moved.example/a": {"state": "moved", "status": 301, "to": "https://new.example/a"}}.get(href, {"state": "ok", "status": 200, "to": None})
    monkeypatch.setattr(bookmarkcheck, "probe", fake)
    assert client.post("/api/bookmarks/check").json()["total"] == 4  # each address once; a mailto: is not asked
    s = _wait(client)
    assert sorted(asked) == ["http://moved.example/a", "https://dead.example", "https://fine.example", "https://gone.example/page"]
    assert s["done"] == 4 and s["checkedAt"] and s["offline"] is False
    assert [(x["name"], x["state"]) for x in s["items"]] == [("Dead", "dead"), ("Dead twice", "dead"), ("Gone", "gone"), ("Moved", "moved")]
    moved = s["items"][3]
    assert moved["to"] == "https://new.example/a" and moved["path"] == "Sites" and moved["canChange"] is True
    # what is deleted or given its new address since is no longer listed
    client.delete(f"/api/bookmarks/links/{ids['Dead']}")
    assert client.patch(f"/api/bookmarks/links/{ids['Moved']}", json={"href": moved["to"]}).status_code == 200
    assert [x["name"] for x in client.get("/api/bookmarks/check").json()["items"]] == ["Dead twice", "Gone"]
    client.cookies.clear()
    assert client.get("/api/bookmarks/check").status_code == 401 and client.post("/api/bookmarks/check").status_code == 401
    assert client.get("/api/bookmarks/duplicates").status_code == 401


def test_check_says_when_the_server_cannot_get_out(client, monkeypatch):
    bookmarkcheck.forget()
    g = _folder(client, "Sites")
    for i in range(8):
        _link(client, g, f"Site {i}", f"https://site{i}.example")
    monkeypatch.setattr(bookmarkcheck, "probe", lambda href: {"state": "ok", "status": 200, "to": None} if href.endswith(("0.example", "1.example", "2.example"))
                        else {"state": "dead", "status": None, "to": None})
    client.post("/api/bookmarks/check")
    s = _wait(client)
    assert s["offline"] is True and len(s["items"]) == 5  # five of eight silent: this server's way out, not the bookmarks


def test_probe_against_a_real_server():
    """What each answer means, and that nothing but the address itself is asked: a redirect is never followed."""
    seen = []

    class H(http.server.BaseHTTPRequestHandler):
        def _answer(self):
            seen.append((self.command, self.path))
            code, to = {"/ok": (200, None), "/gone": (404, None), "/headless": (404 if self.command == "HEAD" else 200, None), "/error": (503, None),
                        "/login": (403, None), "/moved": (301, "https://elsewhere.example/new"), "/slash": (301, self.path + "/"),
                        "/temp": (302, "http://127.0.0.1:9/secret"), "/rel": (308, "/other/place")}[self.path]
            self.send_response(code)
            if to:
                self.send_header("Location", to)
            self.end_headers()
        do_HEAD = do_GET = _answer

        def log_message(self, *a):
            pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        assert bookmarkcheck.probe(base + "/ok")["state"] == "ok"  # this server itself is never asked…
        assert seen == []
        with um.patch.object(bookmarkcheck, "_opener", bookmarkcheck.outbound.opener(lambda ip: True, redirects=False)):  # …unless the test lets it
            assert bookmarkcheck.probe(base + "/ok") == {"state": "ok", "status": 200, "to": None}
            assert bookmarkcheck.probe(base + "/gone") == {"state": "gone", "status": 404, "to": None}
            assert bookmarkcheck.probe(base + "/headless")["state"] == "ok"  # "not found" to HEAD only: asked again with GET
            assert bookmarkcheck.probe(base + "/error") == {"state": "dead", "status": 503, "to": None}
            assert bookmarkcheck.probe(base + "/login")["state"] == "ok"  # it answered: a page behind a sign-in is not dead
            assert bookmarkcheck.probe(base + "/moved") == {"state": "moved", "status": 301, "to": "https://elsewhere.example/new"}
            assert bookmarkcheck.probe(base + "/slash")["state"] == "ok"  # only a slash more: the browser sorts that out
            assert bookmarkcheck.probe(base + "/temp")["state"] == "ok"  # moved for now, not for good
            assert bookmarkcheck.probe(base + "/rel") == {"state": "moved", "status": 308, "to": base + "/other/place"}
        assert ("GET", "/secret") not in seen and all(p in ("/ok", "/gone", "/headless", "/error", "/login", "/moved", "/slash", "/temp", "/rel") for _, p in seen)
    finally:
        srv.shutdown()
    assert bookmarkcheck.probe("https://no-such-host.invalid/")["state"] == "dead"
    for href in ("http://169.254.169.254/latest/", "http://localhost/"):
        assert bookmarkcheck.probe(href)["state"] == "ok"  # not asked, so not called dead


def test_same_page():
    same = bookmarkcheck._same_page
    assert same("http://www.example.com/a/", "https://example.com/a") and same("https://Example.com", "https://example.com/")
    assert not same("https://example.com/a", "https://example.com/b") and not same("https://example.com/a?x=1", "https://example.com/a")
    assert not same("https://old.example/a", "https://new.example/a")
