"""The Monarch Money sync against a stand-in for the library: the sign-in kept with the suite's keys, accounts (the
house and the car among them) with their history, transactions (changes made here kept), holdings, bills, and a
session Monarch no longer takes."""
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

    async def get_recurring_transactions(self, start, end):
        return {"recurringTransactionItems": [
            {"stream": {"id": "s1", "frequency": "monthly", "amount": -120, "isApproximate": True, "merchant": {"name": "Power Co"}},
             "date": (TODAY + dt.timedelta(days=5)).isoformat(), "isPast": False, "transactionId": None, "amount": -118.5,
             "category": {"name": "Utilities"}, "account": {"id": "101"}}]}


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
    b = client.get(f"/api/bills?start={TODAY}&end={TODAY + dt.timedelta(days=10)}").json()["items"]
    assert b == [{**b[0], "merchant": "Power Co", "amount": -118.5, "approximate": True, "account": "Checking", "paid": False}]
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
    # Monarch no longer takes the session: ioMoney signs in again by itself
    FakeMM.valid.clear()
    assert client.post("/api/monarch/sync").json()["ok"]
    assert FakeMM.logins == 2 and credentials.get("iomoney", "monarch_token") == "tok-2"
    st = client.get("/api/monarch").json()
    assert st["configured"] and st["keys"]["monarch_token"] and st["last"]["ok"] and len(st["history"]) == 3


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
