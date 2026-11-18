"""The Monarch Money sync against a stand-in for the library: the sign-in kept with the suite's keys, accounts (the
house and the car among them) with their history, transactions (changes made here kept, categories renamed here
followed), holdings (not Monarch's recurring transactions: ioMoney finds those itself), and a session Monarch no
longer takes."""
import datetime as dt

import pytest
from iosuite_shared import credentials

from app import db, monarch, quotes

TODAY = dt.date.today()
D = lambda n: (TODAY - dt.timedelta(days=n)).isoformat()  # noqa: E731


class FakeMM:
    """What app/monarch.py asks of monarchmoney.MonarchMoney, with Monarch's shapes."""
    logins = 0
    valid = {"tok-1"}
    transactions = []
    accounts = []

    def __init__(self, token=None):
        self.token = token

    async def login(self, email, password, use_saved_session=True, save_session=True, mfa_secret_key=None):
        assert not use_saved_session and not save_session
        if (email, password) != ("me@example.com", "pw") or mfa_secret_key != "JBSWY3DPEHPK3PXP":
            raise RuntimeError("401 Unauthorized: bad sign-in")
        FakeMM.logins += 1
        self.token = f"tok-{FakeMM.logins}"
        FakeMM.valid.add(self.token)

    async def multi_factor_authenticate(self, email, password, code):
        self.token = "tok-code"
        FakeMM.valid.add(self.token)

    def _check(self):
        if self.token not in FakeMM.valid:
            raise RuntimeError("401, message='Unauthorized'")

    async def get_transaction_categories(self):
        self._check()
        return {"categories": [{"id": "c1", "name": "Groceries", "group": {"name": "Food & Dining"}},
                               {"id": "c2", "name": "Transfer", "group": {"name": "Transfers"}}]}

    async def get_accounts(self):
        self._check()
        return {"accounts": FakeMM.accounts}

    async def get_account_history(self, account_id):
        return [{"date": D(30), "signedBalance": 4000 if account_id == 101 else 600000 if account_id == 104 else -1},
                {"date": D(10), "signedBalance": 4500 if account_id == 101 else 640000 if account_id == 104 else -1}]

    async def get_transactions(self, limit, offset, start_date, end_date, account_ids=()):
        self._check()
        rows = [t for t in FakeMM.transactions if start_date <= t["date"] <= end_date
                and (not account_ids or t["account"]["id"] in account_ids)]
        return {"allTransactions": {"totalCount": len(rows), "results": rows[offset:offset + limit]}}

    async def get_account_holdings(self, account_id):
        return {"portfolio": {"aggregateHoldings": {"edges": [
            {"node": {"id": "h1", "quantity": 50, "basis": 7000, "totalValue": 10000,
                      "security": {"ticker": "AAPL", "name": "Apple Inc.", "type": "equity", "currentPrice": 200}, "holdings": []}},
            {"node": {"id": "h2", "quantity": 100, "basis": None, "totalValue": 2000,
                      "security": {"ticker": None, "name": "Target date fund", "type": "mutual_fund", "closingPrice": 20}, "holdings": []}}]}}}


def acct(i, name, typ, bal, asset=True, **kw):
    return {"id": i, "displayName": name, "type": {"name": typ}, "subtype": {"display": typ.title()}, "isAsset": asset,
            "currentBalance": bal, "includeInNetWorth": True, "institution": {"name": "Bank"}, "mask": "1234", **kw}


ACCOUNTS = [acct("101", "Checking", "depository", 5000), acct("102", "Visa", "credit", -300, asset=False, mask="9876"),
            acct("103", "Brokerage", "brokerage", 12000, holdingsCount=2, mask=None),
            acct("104", "1 Main St", "real_estate", 650000, dataProvider="zillow", mask=None),
            acct("105", "Mortgage", "loan", -400000, asset=False, mask="5555"), acct("106", "Honda", "vehicle", 21000, mask=None)]


def tx(i, days_ago, amount, merchant, cat="c1", **kw):
    return {"id": i, "date": D(days_ago), "amount": amount, "merchant": {"name": merchant}, "plaidName": merchant.upper(),
            "category": {"id": cat, "name": {"c1": "Groceries", "c2": "Transfer"}[cat]}, "account": {"id": "101"},
            "pending": False, "hideFromReports": False, "isRecurring": False, "notes": None, "tags": [], **kw}


@pytest.fixture()
def mm(monkeypatch, client):
    monkeypatch.setattr(monarch, "client_factory", FakeMM)
    monkeypatch.setattr(monarch, "_errors", lambda: (KeyError, LookupError, IndexError))
    monkeypatch.setattr(quotes, "fetcher", lambda sym, rng: {"chart": {"result": None, "error": {"description": "offline"}}})
    FakeMM.logins, FakeMM.valid = 0, set()
    FakeMM.accounts = list(ACCOUNTS)
    FakeMM.transactions = [tx("t1", 3, -54.2, "Grocer"), tx("t2", 2, -1000, "To savings", cat="c2"), tx("t3", 1, -12, "Pending cafe", pending=True)]
    monarch.declare()
    credentials.forget()
    return FakeMM


def grocer(client):
    return next(t for t in client.get("/api/transactions").json()["items"] if t["merchant"] == "Grocer")


def put_keys():
    credentials.put("iomoney", "monarch_email", "me@example.com")
    credentials.put("iomoney", "monarch_password", "pw")
    credentials.put("iomoney", "monarch_mfa_secret", "JBSW Y3DP EHPK 3PXP")


def test_sync_needs_the_sign_in_in_keys_and_tokens(client, mm):
    r = client.post("/api/monarch/sync").json()
    assert r["ok"] is False and "Keys and tokens" in r["message"] and r["signIn"]
    keys = {k["name"] for k in client.get("/api/suite-admin/keys").json().get("items", [])} if client.get("/api/suite-admin/keys").status_code == 200 else set()
    assert not keys or {"monarch_email", "monarch_password", "monarch_mfa_secret", "monarch_token"} <= keys


def test_first_sync_copies_everything(client, mm):
    put_keys()
    r = client.post("/api/monarch/sync").json()
    assert r["ok"], r
    assert r["accounts"] == 6 and r["transactions"] == 3 and r["holdings"] == 2
    assert credentials.get("iomoney", "monarch_token") == "tok-1"  # the session is kept, not the code
    accts = {a["name"]: a for a in client.get("/api/accounts").json()["items"]}
    assert accts["Checking"]["kind"] == "cash" and accts["Checking"]["source"] == "monarch" and accts["Checking"]["balance"] == 5000
    assert accts["Visa"]["kind"] == "credit" and accts["Visa"]["value"] == -300
    assert accts["1 Main St"]["kind"] == "property" and accts["1 Main St"]["value"] == 650000
    assert accts["Honda"]["kind"] == "vehicle" and accts["Mortgage"]["kind"] == "loan" and accts["Mortgage"]["balance"] == 400000
    nw = client.get("/api/networth?days=60").json()
    assert nw["netWorth"] == 5000 - 300 + 12000 + 650000 - 400000 + 21000
    hist = client.get(f"/api/accounts/{accts['1 Main St']['id']}/history?days=60").json()["items"]
    assert hist[0]["value"] == 600000 and hist[-1]["value"] == 650000  # Monarch's history came along
    # the house's mortgage, for its equity
    h = client.patch(f"/api/accounts/{accts['1 Main St']['id']}", json={"loanId": accts["Mortgage"]["id"]}).json()
    assert h["equity"] == 250000
    assert client.post(f"/api/accounts/{accts['1 Main St']['id']}/values", json={"value": 1}).status_code == 403  # Monarch's
    s = client.get("/api/spending").json() if TODAY.day > 3 else None
    if s:
        assert s["spent"] == 66.2  # the transfer is left out
    t = grocer(client)
    assert t["group"] == "Food & Dining" and t["description"] == "GROCER" and t["source"] == "monarch"
    p = client.get("/api/portfolio").json()
    by = {x["symbol"] or x["name"]: x for x in p["items"]}
    assert by["AAPL"]["value"] == 10000 and by["AAPL"]["gain"] == 3000 and by["Target date fund"]["kind"] == "fund"
    assert client.get("/api/recurring").json()["items"] == []  # Monarch's recurring ones are not brought in
    assert client.delete(f"/api/accounts/{accts['Checking']['id']}").status_code == 403  # hide it instead


def test_later_syncs_keep_changes_and_drop_what_went(client, mm):
    put_keys()
    assert client.post("/api/monarch/sync").json()["ok"]
    t = grocer(client)
    client.patch(f"/api/transactions/{t['id']}", json={"category": "Party", "notes": "birthday"})
    chk = next(a for a in client.get("/api/accounts").json()["items"] if a["name"] == "Checking")
    client.patch(f"/api/accounts/{chk['id']}", json={"name": "Joint checking", "hidden": True})
    # the pending one posted under a new id, the grocer's amount was corrected
    FakeMM.transactions = [tx("t1", 3, -55.2, "Grocer"), tx("t2", 2, -1000, "To savings", cat="c2"), tx("t4", 1, -12, "Cafe")]
    assert client.post("/api/monarch/sync").json()["ok"]
    assert FakeMM.logins == 1  # the kept session served
    t = grocer(client)
    assert t["category"] == "Party" and t["notes"] == "birthday" and t["amount"] == -55.2
    assert [x["merchant"] for x in client.get("/api/transactions?q=cafe").json()["items"]] == ["Cafe"]
    a = client.get(f"/api/accounts/{chk['id']}").json()
    assert a["name"] == "Joint checking" and a["hidden"] is True
    # hidden in Monarch (a duplicate, "Hide from reports"): not brought in, and gone here when it was
    FakeMM.transactions = [tx("t1", 3, -55.2, "Grocer"), tx("t2", 2, -1000, "To savings", cat="c2"), tx("t4", 1, -12, "Cafe", hideFromReports=True),
                           tx("t5", 1, -12, "Cafe twin", hideFromReports=True)]
    assert client.post("/api/monarch/sync").json()["transactions"] == 2
    assert client.get("/api/transactions?q=cafe&hidden=true").json()["total"] == 0
    # Monarch no longer takes the session: ioMoney signs in again by itself
    FakeMM.valid.clear()
    assert client.post("/api/monarch/sync").json()["ok"]
    assert FakeMM.logins == 2 and credentials.get("iomoney", "monarch_token") == "tok-2"
    st = client.get("/api/monarch").json()
    assert st["configured"] and st["keys"]["monarch_token"] and st["last"]["ok"] and len(st["history"]) == 4


def test_a_code_by_hand_and_a_wrong_sign_in(client, mm):
    credentials.put("iomoney", "monarch_email", "me@example.com")
    credentials.put("iomoney", "monarch_password", "wrong")
    r = client.post("/api/monarch/sync").json()
    assert r["ok"] is False and "401" in r["message"]
    assert db.one("SELECT ok FROM mny_syncs ORDER BY id DESC LIMIT 1")["ok"] == 0
    assert client.post("/api/monarch/code", json={"code": "abc"}).status_code == 400
    assert client.post("/api/monarch/code", json={"code": "123456"}).status_code == 200
    assert credentials.get("iomoney", "monarch_token") == "tok-code"
    assert client.delete("/api/monarch/session").json()["keys"]["monarch_token"] is False


def test_rules_run_over_what_monarch_sends(client, mm):
    put_keys()
    client.post("/api/rules", json={"pattern": "GROCER", "field": "description", "setMerchant": "Corner grocer", "setCategory": "Food"})
    assert client.post("/api/monarch/sync").json()["ok"]
    t = next(x for x in client.get("/api/transactions").json()["items"] if x["description"] == "GROCER")
    assert t["merchant"] == "Corner grocer" and t["category"] == "Food" and t["edited"] is False
    accts = {a["name"]: a for a in client.get("/api/accounts").json()["items"]}
    assert accts["Checking"]["track"] == "transactions" and accts["Brokerage"]["track"] == "value"
    assert accts["1 Main St"]["track"] == "value" and accts["1 Main St"]["group"] == "asset"
    # the next sync brings Monarch's name back, and the rule makes it ours again
    assert client.post("/api/monarch/sync").json()["ok"]
    assert next(x for x in client.get("/api/transactions").json()["items"] if x["description"] == "GROCER")["merchant"] == "Corner grocer"
    # an account followed by its value alone keeps that through the syncs
    client.patch(f"/api/accounts/{accts['Checking']['id']}", json={"track": "value"})
    assert client.post("/api/monarch/sync").json()["ok"]
    assert client.get(f"/api/accounts/{accts['Checking']['id']}").json()["track"] == "value"
    assert client.get("/api/transactions").json()["total"] == 0


def test_a_pending_one_is_followed_until_it_posts(client, mm):
    put_keys()
    FakeMM.transactions = [tx("p1", 40, -280, "Friend", pending=True), tx("p2", 35, -60, "Garage", pending=True), tx("t1", 3, -54.2, "Grocer")]
    assert client.post("/api/monarch/sync").json()["ok"]
    assert client.get("/api/transactions?q=friend").json()["items"][0]["pending"] is True
    # weeks later (far before the last sync's two weeks): one posted under a new id, the other under its own
    FakeMM.transactions = [tx("p1b", 40, -280, "Friend"), tx("p2", 35, -60, "Garage"), tx("t1", 3, -54.2, "Grocer")]
    assert client.post("/api/monarch/sync").json()["ok"]
    friend = client.get("/api/transactions?q=friend").json()["items"]
    assert len(friend) == 1 and friend[0]["pending"] is False  # not there twice, nor still pending
    assert client.get("/api/transactions?q=garage").json()["items"][0]["pending"] is False


def test_receipts_links_and_split_follow_a_pending_one_that_posts(client, mm):
    """Monarch gives a pending transaction a new id when it posts: what was kept with it here moves to the new one."""
    from iosuite_shared import related
    put_keys()
    FakeMM.transactions = [tx("p1", 4, -280, "Appliance shop", pending=True), tx("p2", 4, -40, "Bistro", pending=True),
                           tx("p3", 4, -15, "Kiosk", pending=True), tx("p4", 4, -9, "Newsstand", pending=True), tx("t1", 3, -54.2, "Grocer")]
    assert client.post("/api/monarch/sync").json()["ok"]
    one = lambda q: client.get(f"/api/transactions?q={q}").json()["items"][0]  # noqa: E731
    shop, bistro, kiosk = one("appliance"), one("bistro"), one("kiosk")
    client.patch(f"/api/transactions/{shop['id']}", json={"tags": ["warranty"]})
    client.patch(f"/api/transactions/{one('newsstand')['id']}", json={"tags": ["trip"]})  # a tag alone goes along too
    pdf = b"%PDF-1.4\n%%EOF\n"
    for t in (shop, bistro, kiosk):
        assert client.post(f"/api/transactions/{t['id']}/receipts", params={"name": "slip.pdf"}, content=pdf).status_code == 201
    related.add(("transaction", shop["id"]), ("item", 7))
    related.add(("transaction", kiosk["id"]), ("item", 9))
    client.put(f"/api/transactions/{shop['id']}/splits", json={"items": [{"amount": 200, "category": "Home"}, {"amount": 80, "category": "Gifts"}]})
    # posted: the shop's under a new id, the bistro's with the tip added; the kiosk's charge never went through
    FakeMM.transactions = [tx("p1b", 3, -280, "Appliance shop"), tx("p2b", 3, -46, "Bistro"), tx("p4b", 3, -9, "Newsstand"),
                           tx("t1", 3, -54.2, "Grocer")]
    assert client.post("/api/monarch/sync").json()["ok"]
    new, tipped = one("appliance"), one("bistro")
    assert new["ownTags"] == ["warranty"] and one("newsstand")["ownTags"] == ["trip"] and one("newsstand")["pending"] is False
    assert client.get("/api/transactions?q=warranty").json()["total"] == 1
    assert new["id"] != shop["id"] and new["pending"] is False
    assert [r["name"] for r in new["receipts"]] == ["slip.pdf"] and client.get(f"/api/receipts/{new['receipts'][0]['id']}").content == pdf
    assert [(p["amount"], p["category"]) for p in new["splits"]] == [(-200, "Home"), (-80, "Gifts")]
    assert [(x["kind"], x["id"]) for x in related.of("item", 7)] == [("transaction", str(new["id"]))]
    assert tipped["amount"] == -46 and len(tipped["receipts"]) == 1
    assert client.get("/api/transactions?q=kiosk").json()["items"] == [] and related.of("item", 9) == []
    assert db.one("SELECT count(*) AS n FROM mny_receipts")["n"] == 2


def test_one_account_synced_again(client, mm):
    put_keys()
    assert client.post("/api/monarch/sync").json()["ok"]
    accts = {a["name"]: a for a in client.get("/api/accounts").json()["items"]}
    t = grocer(client)
    client.patch(f"/api/transactions/{t['id']}", json={"category": "Party"})
    # a year-old one Monarch has now (fetched only with the account's two years), and one gone there
    FakeMM.transactions = [tx("t1", 3, -54.2, "Grocer"), tx("t0", 300, -75, "Old shop"), tx("v1", 300, -9, "Card shop", account={"id": "102"}),
                           tx("t9", 1500, -20, "Very old shop")]
    r = client.post("/api/monarch/sync", json={"accountId": accts["Checking"]["id"], "wait": 30}).json()
    assert r["ok"] and r["message"].startswith("Only Checking") and r["transactions"] == 2  # two years as left out
    items = {t["merchant"]: t for t in client.get("/api/transactions").json()["items"]}
    assert set(items) == {"Grocer", "Old shop"}  # the Visa's not fetched; To savings, gone from Monarch, removed
    assert items["Grocer"]["category"] == "Party"  # changed here, kept
    r = client.post("/api/monarch/sync", json={"accountId": accts["Checking"]["id"], "years": 0, "wait": 30}).json()
    assert r["ok"] and r["transactions"] == 3 and "since 1990" in r["message"]  # all Monarch has
    assert client.get("/api/transactions?q=very").json()["total"] == 1
    # it does not move the next sync's window: a regular sync still looks back from the last regular one
    assert db.one("SELECT MAX(started_at) AS t FROM mny_syncs WHERE ok = 1 AND message NOT LIKE 'Only %%'")["t"] is not None
    assert client.post("/api/monarch/sync", json={"accountId": accts["Mortgage"]["id"] + 1000}).status_code == 400


def test_accounts_whose_bank_link_is_behind_are_flagged(client, mm):
    put_keys()
    now = dt.datetime.now(dt.timezone.utc)
    at = lambda hours: (now - dt.timedelta(hours=hours)).isoformat()  # noqa: E731
    cred = lambda **kw: {"id": "c", "updateRequired": False, "disconnectedFromDataProviderAt": None,  # noqa: E731
                         "institution": {"name": "Bank", "status": None}, **kw}
    FakeMM.accounts = [acct("101", "Checking", "depository", 5000, displayLastUpdatedAt=at(3), credential=cred()),
                       acct("102", "Visa", "credit", -300, asset=False, displayLastUpdatedAt=at(80), credential=cred()),
                       acct("103", "Brokerage", "brokerage", 12000, displayLastUpdatedAt=at(5), credential=cred(updateRequired=True)),
                       acct("105", "Mortgage", "loan", -400000, asset=False, displayLastUpdatedAt=at(400),
                            credential=cred(disconnectedFromDataProviderAt=at(300))),
                       # a house valued by Monarch and an account typed in there: no bank behind them
                       acct("104", "1 Main St", "real_estate", 650000, dataProvider="zillow", displayLastUpdatedAt=at(900)),
                       acct("106", "Honda", "vehicle", 21000, isManual=True, displayLastUpdatedAt=at(900)),
                       # its updates turned off in Monarch, and one closed
                       acct("107", "Old card", "credit", 0, asset=False, syncDisabled=True, displayLastUpdatedAt=at(900), credential=cred()),
                       acct("108", "Closed", "depository", 0, deactivatedAt=D(30), displayLastUpdatedAt=at(900), credential=cred())]
    assert client.post("/api/monarch/sync").json()["ok"]
    accts = {a["name"]: a for a in client.get("/api/accounts").json()["items"]}
    assert accts["Checking"]["bank"]["stale"] is None and accts["Checking"]["bank"]["hoursBehind"] == 3
    assert accts["Checking"]["bank"]["refreshedAt"].endswith("Z")
    assert accts["Visa"]["bank"]["stale"] == "old" and accts["Visa"]["bank"]["hoursBehind"] == 80
    assert accts["Brokerage"]["bank"]["stale"] == "update"
    assert accts["Mortgage"]["bank"]["stale"] == "disconnected"
    assert all(accts[n]["bank"]["stale"] is None for n in ("1 Main St", "Honda", "Old card", "Closed"))
    stale = client.get("/api/summary").json()["monarch"]["stale"]
    assert {x["name"] for x in stale} == {"Visa", "Brokerage", "Mortgage"}
    assert client.get(f"/api/accounts/{accts['Visa']['id']}").json()["bank"]["why"].startswith("Monarch Money has not heard")
    # asked not to flag one: it stays quiet through the next syncs, until asked again
    v = client.patch(f"/api/accounts/{accts['Visa']['id']}", json={"flagStale": False}).json()
    assert v["bank"]["quiet"] and v["bank"]["stale"] is None
    assert client.post("/api/monarch/sync").json()["ok"]
    assert "Visa" not in {x["name"] for x in client.get("/api/summary").json()["monarch"]["stale"]}
    assert client.patch(f"/api/accounts/{accts['Visa']['id']}", json={"flagStale": True}).json()["bank"]["stale"] == "old"
    # once Monarch hears from the bank again, the flag goes at the next sync
    FakeMM.accounts[1] = acct("102", "Visa", "credit", -300, asset=False, displayLastUpdatedAt=at(1), credential=cred())
    assert client.post("/api/monarch/sync").json()["ok"]
    assert client.get(f"/api/accounts/{accts['Visa']['id']}").json()["bank"]["stale"] is None
    # a manual account has no bank link at all
    m = client.post("/api/accounts", json={"name": "Cash jar", "kind": "cash", "balance": 10}).json()
    assert "bank" not in m


def test_history_follows_the_dates_of_the_transactions(client, mm, monkeypatch):
    put_keys()
    # an account typed in at Monarch: a starting balance long ago, then one added there with an earlier date
    FakeMM.accounts = list(ACCOUNTS) + [acct("109", "Pension", "depository", 400, isManual=True)]
    FakeMM.transactions = [tx("p1", 700, 400, "Balance Adjustment", account={"id": "109"})]
    assert client.post("/api/monarch/sync").json()["ok"]
    pid = next(a["id"] for a in client.get("/api/accounts").json()["items"] if a["name"] == "Pension")
    FakeMM.accounts[-1] = acct("109", "Pension", "depository", 500, isManual=True)
    FakeMM.transactions = [tx("p1", 700, 400, "Balance Adjustment", account={"id": "109"}),
                           tx("p2", 300, 100, "Adjustment", account={"id": "109"})]
    r = client.post("/api/monarch/sync", json={"accountId": pid, "wait": 30}).json()
    assert r["ok"], r
    kept = {r["day"].isoformat(): float(r["balance"]) for r in db.q("SELECT day, balance FROM mny_balances WHERE account_id = %s", (pid,))}
    assert kept == {D(701): 0, D(700): 400, D(300): 500, TODAY.isoformat(): 500}  # the daily copies give way
    assert client.get(f"/api/accounts/{pid}/history?days=400").json()["items"][0]["value"] == 400
    # an account linked to its bank keeps Monarch's history, and syncing it again takes Monarch's new one
    chk = next(a["id"] for a in client.get("/api/accounts").json()["items"] if a["name"] == "Checking")
    monkeypatch.setattr(FakeMM, "get_account_history", lambda self, i: _async([{"date": D(30), "signedBalance": 3000}]))
    assert client.post("/api/monarch/sync", json={"accountId": chk, "wait": 30}).json()["ok"]
    hist = {p["day"]: p["value"] for p in client.get(f"/api/accounts/{chk}/history?days=60").json()["items"]}
    assert hist[D(30)] == 3000 and hist[D(10)] == 4500


async def _async(v):
    return v


def test_categories_renamed_here_follow_the_syncs(client, mm):
    put_keys()
    assert client.post("/api/monarch/sync").json()["ok"]
    assert client.put("/api/categories", json={"name": "Groceries", "newName": "Food shopping", "group": "Everyday"}).json()["moved"] == 2  # the grocer and the pending cafe
    assert client.post("/api/categories/delete", json={"name": "Transfer"}).json()["moved"] == 1
    FakeMM.transactions.append(tx("t9", 1, -9, "Grocer two"))
    assert client.post("/api/monarch/sync").json()["ok"]
    by = {t["merchant"]: t for t in client.get("/api/transactions?hidden=true").json()["items"]}
    assert by["Grocer"]["category"] == "Food shopping" and by["Grocer two"]["category"] == "Food shopping"
    assert by["Grocer two"]["group"] == "Everyday" and by["To savings"]["category"] is None
    # the name taken again here: Monarch's comes in under it once more
    assert client.post("/api/categories", json={"name": "Groceries"}).status_code == 201
    assert client.post("/api/monarch/sync").json()["ok"]
    assert grocer(client)["category"] == "Groceries"


def test_an_account_made_again_in_monarch_is_not_there_twice(client, mm):
    put_keys()
    assert client.post("/api/monarch/sync").json()["ok"]
    chk = next(a for a in client.get("/api/accounts").json()["items"] if a["name"] == "Checking")
    t1 = grocer(client)
    client.patch(f"/api/transactions/{t1['id']}", json={"category": "Party"})
    # the bank link broke: Checking deleted in Monarch and made again (new ids for it and its transactions, a day off
    # here and there, older history too); and a new account, an HSA
    FakeMM.accounts = [a for a in ACCOUNTS if a["id"] != "101"] + [acct("201", "Checking", "depository", 4900),
                                                                    acct("301", "HSA", "depository", 800, mask="4444")]
    new = lambda i, d, amount, m, **kw: tx(i, d, amount, m, account={"id": "201"}, **kw)  # noqa: E731
    FakeMM.transactions = [new("n1", 2, -54.2, "Grocer"), new("n2", 2, -1000, "To savings", cat="c2"), new("n3", 1, -8, "Bakery"),
                           new("n0", 40, -70, "Hardware")]
    r = client.post("/api/monarch/sync").json()
    assert r["ok"] and r["held"] == 2 and "2 new accounts wait" in r["message"]
    assert client.get("/api/transactions").json()["total"] == 3  # the old Checking's are kept meanwhile
    assert client.get("/api/summary").json()["monarch"]["newAccounts"] == 2
    held = {x["externalId"]: x for x in client.get("/api/monarch/new").json()["items"]}
    assert set(held) == {"201", "301"}
    assert held["201"]["likely"] == chk["id"] and held["201"]["candidates"][0]["gone"] is True
    assert held["301"]["likely"] is None and held["301"]["balance"] == 800
    # not an account Monarch still lists; not one that does not wait
    visa = next(a for a in client.get("/api/accounts").json()["items"] if a["name"] == "Visa")
    assert client.post("/api/monarch/new/201", json={"as": "existing", "accountId": visa["id"]}).status_code == 400
    assert client.post("/api/monarch/new/999", json={"as": "new"}).status_code == 404
    # the HSA is new: it comes in with the next sync
    r = client.post("/api/monarch/new/301", json={"as": "new", "wait": 30}).json()
    assert r["sync"]["ok"] and r["sync"]["held"] == 1
    assert any(a["name"] == "HSA" for a in client.get("/api/accounts").json()["items"])
    # the new Checking is the old one: same account, its transactions matched, none twice, the change kept
    r = client.post("/api/monarch/new/201", json={"as": "existing", "accountId": chk["id"], "wait": 30}).json()
    assert r["accountId"] == chk["id"] and r["sync"]["ok"] and r["sync"]["held"] == 0
    items = client.get(f"/api/transactions?account={chk['id']}").json()["items"]
    assert sorted(t["merchant"] for t in items) == ["Bakery", "Grocer", "Hardware", "To savings"]
    g = next(t for t in items if t["merchant"] == "Grocer")
    assert g["id"] == t1["id"] and g["category"] == "Party"
    assert client.get(f"/api/accounts/{chk['id']}").json()["balance"] == 4900
    assert db.one("SELECT matched FROM mny_monarch_moves WHERE account_id = %s", (chk["id"],))["matched"] == 2
    assert client.get("/api/monarch/new").json()["items"] == []
    assert client.post("/api/monarch/sync").json()["ok"]
    assert client.get("/api/transactions").json()["total"] == 4


def test_back_to_monarchs_own(client, mm):
    """What was changed here on a transaction from Monarch is undone in one go, and the syncs are let in again."""
    put_keys()
    assert client.post("/api/monarch/sync").json()["ok"]
    g = grocer(client)
    client.patch(f"/api/transactions/{g['id']}", json={"category": "Food", "merchant": "Corner grocer", "tags": ["weekly"]})
    client.patch(f"/api/transactions/{g['id']}", json={"notes": "with the neighbours", "hidden": True})
    client.put(f"/api/transactions/{g['id']}/splits", json={"items": [{"amount": 50, "category": "Food"}, {"amount": 4.2, "category": "Gifts"}]})
    FakeMM.transactions[0] = tx("t1", 3, -54.2, "Grocer & Sons")  # Monarch renames it meanwhile: kept out while changed here
    assert client.post("/api/monarch/sync").json()["ok"]
    assert client.get(f"/api/transactions/{g['id']}").json()["merchant"] == "Corner grocer"
    r = client.post(f"/api/transactions/{g['id']}/reset")
    assert r.status_code == 200, r.text
    t = r.json()
    assert (t["merchant"], t["category"], t["notes"], t["hidden"], t["edited"], t["ownTags"], t["splits"]) == \
        ("Grocer", "Groceries", None, False, False, [], [])
    ch = client.get(f"/api/transactions/{g['id']}/changes").json()["items"]
    assert ch[0]["what"] == "reset" and {f["field"] for f in ch[0]["fields"]} == {"payee", "category", "notes", "hidden", "tags"}
    assert client.post("/api/monarch/sync").json()["ok"]
    assert client.get(f"/api/transactions/{g['id']}").json()["merchant"] == "Grocer & Sons"  # the sync is let in again
    assert client.get("/api/transactions?review=yes").json()["total"] >= 0


def test_balance_check(client, mm):
    """An account's balance should move by what its transactions add up to; where it does not, it says by how much."""
    put_keys()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    cred = {"id": "c", "updateRequired": False, "disconnectedFromDataProviderAt": None, "institution": {"name": "Bank", "status": None}}
    FakeMM.accounts = [acct("101", "Checking", "depository", 5000, displayLastUpdatedAt=now, credential=cred),
                       acct("103", "Brokerage", "brokerage", 12000, holdingsCount=2, displayLastUpdatedAt=now, credential=cred),
                       acct("109", "Typed in", "depository", 50, isManual=True)]
    # Monarch's history: 4000 thirty days ago, 4500 ten days ago, 5000 now
    FakeMM.transactions = [tx("b1", 20, 500, "Employer"), tx("b2", 8, 700, "Employer"), tx("b3", 5, -200, "Plumber"),
                           tx("b4", 1, -12, "Cafe", pending=True)]
    assert client.post("/api/monarch/sync").json()["ok"]
    chk = next(a["id"] for a in client.get("/api/accounts").json()["items"] if a["name"] == "Checking")
    r = client.get("/api/balance-check").json()
    assert [(x["name"], x["status"], x["gap"]) for x in r["items"]] == [("Checking", "ok", 0)] and r["gaps"] == 0  # only what has a bank and transactions
    one = r["items"][0]
    assert (one["from"], one["opening"], one["balance"], one["moved"], one["count"], one["pending"]) == (D(30), 4000, 5000, 1000, 3, -12)
    # the bank counts the pending one in the balance: explained
    FakeMM.accounts[0] = acct("101", "Checking", "depository", 4988, displayLastUpdatedAt=now, credential=cred)
    assert client.post("/api/monarch/sync").json()["ok"]
    assert [(x["status"], x["gap"]) for x in client.get("/api/balance-check").json()["items"]] == [("pending", -12)]
    # the plumber's is gone from Monarch (hidden there): the balance says 200 less than the transactions do
    FakeMM.accounts[0] = acct("101", "Checking", "depository", 5000, displayLastUpdatedAt=now, credential=cred)
    FakeMM.transactions = [tx("b1", 20, 500, "Employer"), tx("b2", 8, 700, "Employer"), tx("b3", 5, -200, "Plumber", hideFromReports=True)]
    assert client.post("/api/monarch/sync").json()["ok"]
    r = client.get("/api/balance-check").json()
    one = r["items"][0]
    assert r["gaps"] == 1 and (one["status"], one["gap"]) == ("gap", -200) and client.get("/api/tidy").json()["balanceGaps"] == 1
    assert one["weeks"] == [{"from": D(9), "to": D(0), "change": -200, "gap": -200}]  # it agreed ten days ago
    # looked at and fine: quiet while it stays the same, flagged again when it moves
    assert client.post(f"/api/balance-check/{chk}/ok", json={"gap": -200}).json()["ok"]
    assert client.get("/api/balance-check").json()["items"][0]["status"] == "accepted" and client.get("/api/balance-check").json()["gaps"] == 0
    FakeMM.transactions.append(tx("b5", 2, 30, "Refund"))
    assert client.post("/api/monarch/sync").json()["ok"]
    assert [(x["status"], x["gap"]) for x in client.get("/api/balance-check").json()["items"]] == [("gap", -230)]
    assert client.post(f"/api/balance-check/{chk}/ok", json={"gap": None}).json()["ok"]


def test_balance_check_dates_and_old_pending(client, mm, monkeypatch):
    """What is no gap: a payment of the first day that the balance shows a day later, and one Monarch still calls
    pending weeks after the bank took it. Weeks that cancel out are left out of where a gap appeared."""
    from app import balancecheck
    put_keys()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    cred = {"id": "c", "updateRequired": False, "disconnectedFromDataProviderAt": None, "institution": {"name": "Bank", "status": None}}
    checking = lambda bal: acct("101", "Checking", "depository", bal, displayLastUpdatedAt=now, credential=cred)  # noqa: E731
    # the balance of forty days ago does not hold that day's card payment yet: the next day's does
    monkeypatch.setattr(FakeMM, "get_account_history", lambda self, i: _async(
        [{"date": D(40), "signedBalance": 4000}, {"date": D(39), "signedBalance": 3700}, {"date": D(20), "signedBalance": 5000}]))
    FakeMM.accounts = [checking(5000)]
    FakeMM.transactions = [tx("e1", 40, -300, "Card autopay"), tx("e2", 25, 1300, "Employer")]
    assert client.post("/api/monarch/sync").json()["ok"]
    one = client.get("/api/balance-check").json()["items"][0]
    assert (one["status"], one["gap"], one["from"], one["opening"], one["count"]) == ("ok", 0, D(39), 3700, 1)
    # a bill still called pending twelve days on, which the bank took: counted, and named
    FakeMM.accounts = [checking(4880)]
    FakeMM.transactions.append(tx("e3", 12, -120, "Power company", pending=True))
    assert client.post("/api/monarch/sync").json()["ok"]
    one = client.get("/api/balance-check").json()["items"][0]
    assert (one["status"], one["gap"], one["pending"], one["moved"], one["count"]) == ("ok", 0, 0, 1180, 2)
    assert [(x["name"], x["day"], x["amount"], x["days"], x["counted"]) for x in one["stale"]] == [("Power company", D(12), -120, 12, True)]
    # its posted twin is there too: the pending one is a leftover, and stays out
    FakeMM.transactions.append(tx("e4", 11, -120, "Power company"))
    assert client.post("/api/monarch/sync").json()["ok"]
    one = client.get("/api/balance-check").json()["items"][0]
    assert (one["status"], one["gap"], one["count"]) == ("ok", 0, 2) and [x["counted"] for x in one["stale"]] == [False]
    # one of this week is a hold: explained when the bank counts it, as before
    FakeMM.accounts = [checking(4868)]
    FakeMM.transactions.append(tx("e5", 2, -12, "Cafe", pending=True))
    assert client.post("/api/monarch/sync").json()["ok"]
    one = client.get("/api/balance-check").json()["items"][0]
    assert (one["status"], one["gap"], one["pending"]) == ("pending", -12, -12)
    # a gap that is one: money out the account never got; the old pending one beside it is still counted, since the
    # gap grew by just that in its week
    FakeMM.accounts = [checking(4368)]
    FakeMM.transactions = [t for t in FakeMM.transactions if t["id"] != "e4"]
    assert client.post("/api/monarch/sync").json()["ok"]
    chk = client.get("/api/accounts").json()["items"][0]["id"]
    one = client.get("/api/balance-check").json()["items"][0]
    assert (one["gap"], [x["counted"] for x in one["stale"]]) == (-632, [False])  # nothing says when: not counted, but named
    db.ex("INSERT INTO mny_balances (account_id, day, balance, source) VALUES (%s, %s, 4880, 'sync')", (chk, D(9)))
    one = client.get("/api/balance-check").json()["items"][0]
    assert [(w["from"], w["to"], w["change"]) for w in one["weeks"]] == [(D(8), D(0), -512)]
    assert (one["status"], one["gap"], one["pending"]) == ("gap", -512, -12) and [x["counted"] for x in one["stale"]] == [True]  # 500 missing, 12 on hold
    # where a gap appeared: the weeks that cancel out (a transaction dated a day off) are left out
    wk = lambda n, change: {"from": D(n), "to": D(n - 6), "change": change, "gap": 0}  # noqa: E731
    weeks = [wk(84, -50), wk(77, 20.5), wk(70, -30.5), wk(63, 10), wk(49, -40), wk(42, 40), wk(28, -7)]
    assert [(w["from"], w["change"], w["gap"]) for w in balancecheck._settled(weeks)] == [(D(84), -50, -50), (D(28), -7, -57)]
    far = [wk(84, -40), wk(21, 40)]  # two months apart: not a matter of dates
    assert [w["change"] for w in balancecheck._settled(far)] == [-40, 40]
