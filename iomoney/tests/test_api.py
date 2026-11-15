"""The REST API: accounts and who sees them, the net worth and its history, transactions and the spending, holdings
and the portfolio (quotes from a stand-in for Yahoo Finance), house and car values with their loan, and the bills."""
import datetime as dt

import pytest

from app import db, model, quotes
from conftest import sign_in


def chart(price, prev, currency="USD", name="Example Inc"):
    today = dt.datetime.now(dt.timezone.utc).replace(hour=20, minute=0, second=0, microsecond=0)
    stamps = [int((today - dt.timedelta(days=2)).timestamp()), int((today - dt.timedelta(days=1)).timestamp()), int(today.timestamp())]
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "previousClose": prev, "currency": currency,
                                           "longName": name, "regularMarketTime": stamps[-1]},
                                  "timestamp": stamps, "indicators": {"quote": [{"close": [prev - 1, prev, price]}]}}], "error": None}}


PRICES = {"AAPL": chart(200.0, 190.0, name="Apple Inc."), "VWCE.DE": chart(110.0, 100.0, "EUR", "Vanguard FTSE All-World"),
          "EURUSD=X": chart(1.1, 1.1, "USD", "EUR/USD")}


@pytest.fixture(autouse=True)
def yahoo(monkeypatch):
    asked = []

    def fetch(sym, rng):
        asked.append(sym)
        if sym not in PRICES:
            return {"chart": {"result": None, "error": {"code": "Not Found", "description": "No data found, symbol may be delisted"}}}
        return PRICES[sym]
    monkeypatch.setattr(quotes, "fetcher", fetch)
    quotes._fx_cache.clear()
    return asked


def add(client, **f):
    r = client.post("/api/accounts", json={"name": "Checking", "kind": "cash", "balance": "1,000.50", **f})
    assert r.status_code == 201, r.text
    return r.json()


def test_nobody_without_a_role_sees_anything(client, as_user):
    add(client)
    # ioMoney's default role is none: a new account sees nothing until given a role
    r = client.post("/api/suite-admin/users", json={"name": "kid", "password": "secret123"})
    assert r.status_code in (200, 201), r.text
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "kid", "password": "secret123"}).status_code == 403  # no access here
    assert client.get("/api/accounts", auth=("kid", "secret123")).status_code in (401, 403)


def test_accounts_round_trip_and_net_worth(client):
    a = add(client)
    assert a["household"] and a["writable"] and a["balance"] == 1000.5 and a["value"] == 1000.5 and a["currency"] == "USD"
    card = add(client, name="Visa", kind="credit", balance=250)
    assert card["isAsset"] is False and card["value"] == -250
    nw = client.get("/api/networth?days=30").json()
    assert nw["netWorth"] == 750.5 and nw["assets"] == 1000.5 and nw["liabilities"] == 250
    assert nw["history"][-1]["value"] == 750.5
    r = client.patch(f"/api/accounts/{a['id']}", json={"name": "Joint checking", "balance": 2000}).json()
    assert r["name"] == "Joint checking" and r["balance"] == 2000
    assert client.patch(f"/api/accounts/{a['id']}", json={"kind": "nope"}).status_code == 400
    assert client.patch(f"/api/accounts/{a['id']}", json={"balance": "lots"}).status_code == 400
    r = client.patch(f"/api/accounts/{a['id']}", json={"inNetWorth": False}).json()
    assert client.get("/api/networth").json()["netWorth"] == -250
    assert client.delete(f"/api/accounts/{card['id']}").json()["ok"]
    assert client.get(f"/api/accounts/{card['id']}").status_code == 404


def test_private_accounts_and_roles(client, as_user):
    add(client, name="Household")
    as_user("sam", "member")
    mine = add(client, name="Sam's savings")  # a member's new account is their own
    assert mine["household"] is False
    assert [a["name"] for a in client.get("/api/accounts").json()["items"]] == ["Household", "Sam's savings"] or \
        sorted(a["name"] for a in client.get("/api/accounts").json()["items"]) == ["Household", "Sam's savings"]
    hh = next(a for a in client.get("/api/accounts").json()["items"] if a["name"] == "Household")
    assert hh["writable"] is False
    assert client.patch(f"/api/accounts/{hh['id']}", json={"name": "x"}).status_code == 403
    assert client.post("/api/accounts", json={"name": "x", "kind": "cash", "household": True}).status_code == 403
    sign_in(client, "alex")
    names = [a["name"] for a in client.get("/api/accounts").json()["items"]]
    assert "Sam's savings" not in names  # private, even to an admin
    assert client.get(f"/api/accounts/{mine['id']}").status_code == 404
    as_user("viv", "viewer")
    assert [a["name"] for a in client.get("/api/accounts").json()["items"]] == ["Household"]
    assert client.post("/api/accounts", json={"name": "x", "kind": "cash"}).status_code == 403


def test_transactions_spending_and_cash_flow(client):
    a = add(client)
    today = dt.date.today()
    tx = lambda **f: client.post(f"/api/accounts/{a['id']}/transactions", json={"day": today.isoformat(), **f})  # noqa: E731
    r = tx(amount=-42.5, merchant="Grocer", category="Groceries", group="Food")
    assert r.status_code == 201 and r.json()["amount"] == -42.5
    tx(amount=-7.5, merchant="Coffee bar", category="Coffee", group="Food")
    tx(amount=3000, merchant="Employer", category="Paycheck", group="Income")
    tx(amount=-500, merchant="Move to savings", category="Transfer", group="Transfers")
    d = client.get("/api/transactions?q=grocer").json()
    assert d["total"] == 1 and d["items"][0]["merchant"] == "Grocer"
    s = client.get(f"/api/spending?month={today:%Y-%m}").json()
    assert s["spent"] == 50 and s["income"] == 3000  # the transfer is neither
    assert s["categories"][0]["category"] == "Groceries"
    cf = client.get("/api/cashflow?months=3").json()["items"]
    assert len(cf) == 3 and cf[-1]["spent"] == 50 and cf[-1]["net"] == 2950
    t = d["items"][0]
    r = client.patch(f"/api/transactions/{t['id']}", json={"category": "Dining", "hidden": True}).json()
    assert r["category"] == "Dining" and r["hidden"] and r["edited"]
    assert client.get("/api/transactions?q=grocer").json()["total"] == 0  # hidden: left out
    assert client.get("/api/transactions?q=grocer&hidden=true").json()["total"] == 1
    assert {c["category"] for c in client.get("/api/categories").json()["items"]} >= {"Dining", "Coffee", "Paycheck"}
    assert client.delete(f"/api/transactions/{t['id']}").json()["ok"]
    assert client.post(f"/api/accounts/{a['id']}/transactions", json={"amount": "x"}).status_code == 400


def test_portfolio_with_quotes_and_currencies(client, yahoo):
    inv = add(client, name="Brokerage", kind="investment", balance=0)
    r = client.post(f"/api/accounts/{inv['id']}/holdings", json={"symbol": "aapl", "shares": 10, "costBasis": 1500})
    assert r.status_code == 201, r.text
    client.post(f"/api/accounts/{inv['id']}/holdings", json={"symbol": "VWCE.DE", "shares": 5, "kind": "etf"})
    client.post(f"/api/accounts/{inv['id']}/holdings", json={"name": "Private fund", "shares": 2, "price": 50, "kind": "fund"})
    assert client.post(f"/api/accounts/{inv['id']}/holdings", json={"symbol": "bad symbol!", "shares": 1}).status_code == 400
    quotes.refresh(force=True)  # the exchange rate EUR -> USD too
    model.revalue_manual_investments()
    p = client.get("/api/portfolio").json()
    by = {x["symbol"] or x["name"]: x for x in p["items"]}
    assert by["AAPL"]["value"] == 2000 and by["AAPL"]["gain"] == 500 and by["AAPL"]["dayChange"] == 100 and by["AAPL"]["quoted"]
    assert by["VWCE.DE"]["currency"] == "EUR" and by["VWCE.DE"]["value"] == 550 and by["VWCE.DE"]["homeValue"] == 605
    assert by["Private fund"]["value"] == 100 and not by["Private fund"]["quoted"]
    assert p["value"] == 2705
    assert client.get(f"/api/accounts/{inv['id']}").json()["balance"] == 2705  # a manual investment account is what it holds
    q = client.get("/api/quotes/AAPL").json()
    assert q["price"] == 200 and q["name"] == "Apple Inc." and len(q["closes"]) == 3
    h = by["AAPL"]
    assert client.patch(f"/api/holdings/{h['id']}", json={"shares": 20}).status_code == 200
    assert client.get("/api/portfolio").json()["items"][0]["value"] in (4000, 100, 550)
    assert client.delete(f"/api/holdings/{h['id']}").json()["ok"]
    cash = add(client, name="Euro account", currency="EUR", balance=100)
    assert cash["value"] == 110  # 100 EUR at 1.1


def test_house_values_estimate_and_equity(client):
    house = add(client, name="Our house", kind="property", balance=400000,
                details={"address": "1 Main St", "yearlyRate": 3, "boughtFor": 350000, "boughtOn": "2020-06-01"})
    loan = add(client, name="Mortgage", kind="loan", balance=250000)
    r = client.patch(f"/api/accounts/{house['id']}", json={"loanId": loan["id"]}).json()
    assert r["loan"]["name"] == "Mortgage" and r["equity"] == 150000 and r["details"]["address"] == "1 Main St"
    two_years_ago = (dt.date.today() - dt.timedelta(days=730)).isoformat()
    db.ex("DELETE FROM mny_balances WHERE account_id = %s", (house["id"],))
    assert client.post(f"/api/accounts/{house['id']}/values", json={"value": 400000, "day": two_years_ago, "note": "appraisal"}).status_code == 200
    r = client.get(f"/api/accounts/{house['id']}").json()
    assert 424000 < r["estimate"] < 425000  # 3% a year, two years on
    assert model.write_estimates() == 1
    vals = client.get(f"/api/accounts/{house['id']}/values").json()["items"]
    assert vals[0]["source"] == "estimate" and vals[-1]["note"] == "appraisal"
    nw = client.get("/api/networth").json()
    assert 174000 < nw["netWorth"] < 175000
    assert client.post(f"/api/accounts/{house['id']}/values", json={"value": 1, "day": "2999-01-01"}).status_code == 400
    assert client.delete(f"/api/accounts/{house['id']}/values/{two_years_ago}").json()["ok"]
    assert client.patch(f"/api/accounts/{house['id']}", json={"loanId": house["id"]}).status_code == 400  # not a loan


def test_bills_follow_the_account(client, as_user):
    a = add(client)
    today = dt.date.today()
    db.ex("INSERT INTO mny_bills (ext_key, day, merchant, amount, account_id, seen_at) VALUES ('s1:x', %s, 'Power co', -80, %s, NOW())", (today, a["id"]))
    db.ex("INSERT INTO mny_bills (ext_key, day, merchant, amount, seen_at) VALUES ('s2:x', %s, 'Streaming', -15, NOW())", (today,))
    b = client.get(f"/api/bills?start={today}&end={today}").json()["items"]
    assert [x["merchant"] for x in b] == ["Power co", "Streaming"] and b[0]["account"] == "Checking"
    as_user("sam", "member")
    mine = add(client, name="Sam's", household=False)
    db.ex("INSERT INTO mny_bills (ext_key, day, merchant, amount, account_id, seen_at) VALUES ('s3:x', %s, 'Gym', -30, %s, NOW())", (today, mine["id"]))
    assert len(client.get(f"/api/bills?start={today}&end={today}").json()["items"]) == 3
    sign_in(client, "alex")
    assert len(client.get(f"/api/bills?start={today}&end={today}").json()["items"]) == 2  # Sam's gym is Sam's


def test_settings_and_admin_only(client, as_user):
    assert client.put("/api/settings", json={"currency": "eur"}).json()["currency"] == "EUR"
    assert client.put("/api/settings", json={"currency": "euros"}).status_code == 400
    assert client.get("/api/monarch").json()["configured"] is False
    as_user("ed", "editor")
    assert client.put("/api/settings", json={"currency": "USD"}).status_code == 403
    assert client.post("/api/monarch/sync").status_code == 403


def test_value_or_transactions_and_the_groups(client):
    chk = add(client, balance=100)
    assert chk["track"] == "transactions" and chk["group"] == "cash"  # a bank account follows its transactions
    sav = add(client, name="Savings elsewhere", balance=5000, track="value")
    assert sav["track"] == "value"
    house = add(client, name="House", kind="property", balance=400000)
    assert house["track"] == "value" and house["group"] == "asset"  # a house: its value
    assert add(client, name="Visa", kind="credit", balance=50)["track"] == "transactions"
    assert add(client, name="Car loan", kind="loan", balance=9000)["group"] == "loan"
    assert client.post("/api/accounts", json={"name": "x", "kind": "cash", "track": "both"}).status_code == 400
    # a transaction moves the balance of an account that follows them
    r = client.post(f"/api/accounts/{chk['id']}/transactions", json={"amount": -30, "merchant": "Grocer"})
    assert client.get(f"/api/accounts/{chk['id']}").json()["balance"] == 70
    client.patch(f"/api/transactions/{r.json()['id']}", json={"amount": -40})
    assert client.get(f"/api/accounts/{chk['id']}").json()["balance"] == 60
    # one that follows its value takes none, and keeps a value now and then instead
    assert client.post(f"/api/accounts/{sav['id']}/transactions", json={"amount": -1}).status_code == 400
    assert client.post(f"/api/accounts/{sav['id']}/values", json={"value": 5100}).status_code in (200, 201)
    assert client.get(f"/api/accounts/{sav['id']}").json()["balance"] == 5100
    # switched to its value alone, the checking account's transactions are out of sight, and back
    client.patch(f"/api/accounts/{chk['id']}", json={"track": "value"})
    assert client.get("/api/transactions").json()["total"] == 0
    assert client.get("/api/summary").json()["counts"]["transactions"] == 0
    client.patch(f"/api/accounts/{chk['id']}", json={"track": "transactions"})
    assert client.get("/api/transactions").json()["total"] == 1
    s = client.get("/api/summary").json()
    assert [g["label"] for g in s["groups"]] == ["Cash", "Investments", "Credit cards", "Loans", "Assets"]
    assert [g["group"] for g in s["netWorth"]["byGroup"]] == ["cash", "credit", "loan", "asset"]  # in that order
    assert next(g for g in s["netWorth"]["byGroup"] if g["group"] == "cash")["value"] == 60 + 5100


def test_rules_rename_and_categorize(client, as_user):
    a = add(client)
    tx = lambda m, amt=-10: client.post(f"/api/accounts/{a['id']}/transactions", json={"amount": amt, "merchant": m}).json()  # noqa: E731
    old = tx("AMZN Mktp US*2K4")
    tx("Amazon refund", 15)
    hand = tx("AMZN digital")
    client.patch(f"/api/transactions/{hand['id']}", json={"category": "Books"})  # changed by hand: rules leave it
    t = client.post("/api/rules/test", json={"pattern": "amzn"}).json()
    assert t["count"] == 2 and t["edited"] == 1 and len(t["sample"]) == 2
    assert client.post("/api/rules/test", json={"pattern": "amzn", "how": "starts", "flow": "in"}).json()["count"] == 0
    assert client.post("/api/rules", json={"pattern": "amzn"}).status_code == 400  # it has to do something
    assert client.post("/api/rules", json={"pattern": "", "setCategory": "x"}).status_code == 400
    assert client.post("/api/rules", json={"pattern": "x", "setCategory": "x", "amountMin": 10, "amountMax": 5}).status_code == 400
    r = client.post("/api/rules", json={"pattern": "AMZN", "setMerchant": "Amazon", "setCategory": "Shopping", "flow": "out",
                                        "apply": True})
    assert r.status_code == 201 and r.json()["changed"] == 1
    got = {x["id"]: x for x in client.get("/api/transactions?hidden=true").json()["items"]}
    assert got[old["id"]]["merchant"] == "Amazon" and got[old["id"]]["category"] == "Shopping" and not got[old["id"]]["edited"]
    assert got[hand["id"]]["category"] == "Books" and got[hand["id"]]["merchant"] == "AMZN digital"
    assert client.get("/api/transactions?q=amazon").json()["total"] == 2  # the new name is searched (the refund is "in")
    # the first rule that sets a thing wins; a later one still hides
    r2 = client.post("/api/rules", json={"pattern": "amazon", "field": "merchant", "setCategory": "Other", "setHidden": True}).json()
    new = tx("AMZN Mktp US*9Z1")
    assert new["merchant"] == "Amazon" and new["category"] == "Shopping" and new["hidden"] is False  # names are matched as typed
    assert tx("Amazon", 5)["category"] == "Other"
    order = client.put("/api/rules/order", json={"ids": [r2["id"]]}).json()["items"]
    assert [x["id"] for x in order] == [r2["id"], r.json()["id"]]
    assert client.patch(f"/api/rules/{r2['id']}", json={"enabled": False}).json()["enabled"] is False
    assert client.post("/api/rules/apply").json()["changed"] >= 0
    rules = client.get("/api/rules").json()
    assert rules["writable"] and len(rules["items"]) == 2
    # a viewer sees the rules and changes none
    as_user("viv", "viewer")
    assert len(client.get("/api/rules").json()["items"]) == 2 and client.get("/api/rules").json()["writable"] is False
    assert client.post("/api/rules", json={"pattern": "x", "setCategory": "y"}).status_code == 403
    assert client.delete(f"/api/rules/{r2['id']}").status_code == 403
    sign_in(client, "alex")
    assert client.delete(f"/api/rules/{r2['id']}").json()["ok"]
    assert client.get(f"/api/rules/{r2['id']}").status_code in (404, 405)
