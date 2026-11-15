"""The REST API: accounts and who sees them, the net worth and its history, transactions and the spending, holdings
and the portfolio (quotes from a stand-in for Yahoo Finance), house and car values with their loan, and the bills."""
import datetime as dt
import json

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


def test_transfers_between_own_accounts_are_linked(client, as_user):
    chk = add(client, name="Joint checking", institution="JPMorgan Chase", balance=5000)
    sav = add(client, name="Savings", institution="Ally Bank", balance=1000)
    visa = add(client, name="Sapphire", kind="credit", institution="Chase", balance=600)
    today = dt.date.today()
    d = lambda n: (today - dt.timedelta(days=n)).isoformat()  # noqa: E731
    tx = lambda a, amt, payee, n=0, **f: client.post(f"/api/accounts/{a['id']}/transactions", json={"amount": amt, "merchant": payee, "day": d(n), **f}).json()  # noqa: E731
    out = tx(chk, -500, "Ally Bank", 6)            # the payee names the other account
    into = tx(sav, 500, "Jpmorgan Chase", 4)       # two days later
    assert into["transfer"] == {"id": out["id"], "accountId": chk["id"], "account": "Joint checking", "how": "auto"}
    pay = tx(chk, -519.56, "Chase", 3, category="Credit Card Payment")
    got = tx(visa, 519.56, "Payment Thank You", 3)  # the category says it
    assert got["transfer"]["id"] == pay["id"]
    tx(chk, -42, "Grocer", 2, category="Groceries")
    refund = tx(visa, 42, "Grocer refund", 2, category="Groceries")
    assert "transfer" not in refund                  # nothing says it is a transfer
    fund = add(client, name="Emergency fund", institution="Marcus", balance=0)
    tx(sav, 100, "Deposit", 1)
    tx(fund, 100, "Deposit", 1)
    third = tx(chk, -100, "Somebody", 1, category="Transfer")
    assert "transfer" not in third                   # two as likely: left for a person
    s = client.get(f"/api/spending?start={d(10)}&end={today}").json()
    assert s["spent"] == 42 + 100                    # the linked ones are not spending
    # what was learned: next time the same payee in the same account is surely a transfer
    rules = client.get("/api/transfer-rules").json()["items"]
    assert {(r["account"], r["pattern"], r["other"], r["source"]) for r in rules} >= {
        ("Joint checking", "ally bank", "Savings", "learned"), ("Savings", "jpmorgan chase", "Joint checking", "learned")}
    o2 = tx(chk, -250, "Ally Bank", 20)
    i2 = tx(sav, 250, "Interest and things", 11)     # nine days later, a payee that says nothing: the rule knows
    assert i2["transfer"]["id"] == o2["id"] and i2["transfer"]["how"] == "rule"
    # by hand: unlink for good, and link one the guess left
    assert client.delete(f"/api/transactions/{into['id']}/transfer").json()["ok"]
    m = client.post("/api/transfers/link").json()
    assert m["linked"] == 0  # not linked again by itself
    # the maintenance says what still looks like a transfer, and why it was not linked; not the pair unlinked by hand
    why = {(p["out"]["id"], p["in"]["id"]): p["why"] for p in m["possible"]}
    assert why[(next(t["id"] for t in client.get("/api/transactions?q=grocer").json()["items"] if t["amount"] < 0), refund["id"])] == "nothing says it is a transfer"
    assert sum(1 for (o, _i), w in why.items() if o == third["id"] and w.startswith("as likely")) == 2
    assert (out["id"], into["id"]) not in why
    assert client.get("/api/transfers/possible").json()["items"] == m["possible"]
    c = client.get(f"/api/transactions/{third['id']}/transfer").json()
    assert c["other"] is None and len(c["candidates"]) == 2
    r = client.put(f"/api/transactions/{third['id']}/transfer", json={"with": c["candidates"][0]["id"]}).json()
    assert r["other"]["how"] == "hand"
    assert client.put(f"/api/transactions/{refund['id']}/transfer", json={"with": out["id"]}).status_code == 400  # not the same amount
    # a rule typed in
    tr = client.post("/api/transfer-rules", json={"accountId": chk["id"], "otherId": visa["id"], "pattern": "Zelle", "days": 10})
    assert tr.status_code == 201 and tr.json()["pattern"] == "zelle"
    assert client.post("/api/transfer-rules", json={"accountId": chk["id"], "otherId": chk["id"], "pattern": "x"}).status_code == 400
    # a card's and a loan's payment with payees that say little: money from the bank into the card or the loan
    loan = add(client, name="Car loan", kind="loan", balance=9000, track="transactions")
    p1 = tx(chk, -1850, "ONLINE PMT 88213", 9)
    p2 = tx(loan, 1850, "Received", 7)
    assert p2["transfer"]["id"] == p1["id"]
    as_user("viv", "viewer")
    assert client.get("/api/transfer-rules").json()["writable"] is False
    assert client.post("/api/transfers/link").status_code == 403
    assert client.delete(f"/api/transfer-rules/{tr.json()['id']}").status_code == 403


def test_link_transfers_over_everything(client, monkeypatch):
    """The maintenance pairs what came in unlinked (as a bank's history does): card payments every month of the same
    amount, the other account's last digits in the bank's text, each with the nearest of its kind."""
    from app import transfers
    pnc = add(client, name="PNC Checking", institution="PNC", mask="4199", balance=5000)
    visa = add(client, name="PNC Visa", kind="credit", institution="PNC", mask="2530", balance=0)
    sav = add(client, name="Ally Savings", institution="Ally", mask="7081", balance=0)
    chk = add(client, name="Ally Checking", institution="Ally", mask="2748", balance=0)
    today = dt.date.today()
    d = lambda n: (today - dt.timedelta(days=n)).isoformat()  # noqa: E731
    tx = lambda a, amt, desc, n, **f: client.post(f"/api/accounts/{a['id']}/transactions", json={"amount": amt, "merchant": desc, "day": d(n), **f}).json()  # noqa: E731
    with monkeypatch.context() as m:
        m.setattr(transfers, "link", lambda *a, **k: 0)  # as it comes from the bank: nothing linked yet
        pays = [(tx(pnc, -40, "AUTOPAY CHASE CREDIT CRD ACH DEBIT", n + 1, category="Credit Card Payment"),
                 tx(visa, 40, "AUTOMATIC PAYMENT - THANK", n, category="Credit Card Payment")) for n in (60, 30, 2)]
        cat = (tx(pnc, -1830.67, "ONLINE PAYMENT TO *2530", 20, category="Loan Repayments"),
               tx(visa, 1830.67, "THANK YOU FOR YOUR PMT XXXX2530", 20, category="Paychecks"))
        over = (tx(sav, -300, "Overdraft Transfer to Spending Account XXXXXX2748", 50),
                tx(chk, 300, "Overdraft Transfer from Savings Account XXXXXX7081", 50))
        fid = tx(pnc, -300, "MONEYLINE FID BKG SVC LLC ACH DEBIT", 45, category="Transfer")
    r = client.post("/api/transfers/link").json()
    assert r["linked"] == 5
    for o, i in pays + [cat, over]:
        assert client.get(f"/api/transactions/{i['id']}/transfer").json()["other"]["id"] == o["id"]
    assert client.get(f"/api/transactions/{fid['id']}/transfer").json()["other"] is None
    # learned only from what names the other account: the bank's text without what changes each time
    learned = {(x["account"], x["pattern"]) for x in client.get("/api/transfer-rules").json()["items"]}
    assert ("PNC Checking", "online payment to") in learned and ("Ally Savings", "overdraft transfer to spending account") in learned
    assert not any(a == "PNC Checking" and "fid" in p for a, p in learned)


def test_bank_details(client, as_user):
    chk = add(client, name="PNC Checking", mask="4199")
    assert client.get(f"/api/accounts/{chk['id']}/info").json() == {}
    r = client.put(f"/api/accounts/{chk['id']}/info", json={"accountNumber": "  1234 5678 4199 ", "routingNumber": "043000096",
                                                            "phone": "1-888-762-2265", "website": "pnc.com", "address": "PO Box 1\nPittsburgh PA",
                                                            "openedOn": "2015-03-01", "pin": "not kept"})
    assert r.status_code == 200, r.text
    info = r.json()
    assert info == {"accountNumber": "1234 5678 4199", "routingNumber": "043000096", "phone": "1-888-762-2265",
                    "website": "https://pnc.com", "address": "PO Box 1\nPittsburgh PA", "openedOn": "2015-03-01"}
    assert "accountNumber" not in json.dumps(client.get(f"/api/accounts/{chk['id']}").json())  # not with the account
    assert "043000096" not in json.dumps(client.get("/api/summary").json())
    info = client.put(f"/api/accounts/{chk['id']}/info", json={"phone": "", "notes": "Branch on Main St"}).json()
    assert "phone" not in info and info["notes"] == "Branch on Main St" and info["routingNumber"] == "043000096"
    assert client.put(f"/api/accounts/{chk['id']}/info", json={"openedOn": "March"}).status_code == 400
    assert client.put(f"/api/accounts/{chk['id']}/info", json={"accountNumber": "9" * 65}).status_code == 400
    mine = add(client, name="My own", household=False)
    client.put(f"/api/accounts/{mine['id']}/info", json={"accountNumber": "555"})
    as_user("viv", "viewer")
    assert client.get(f"/api/accounts/{chk['id']}/info").json()["routingNumber"] == "043000096"  # whoever sees the account
    assert client.put(f"/api/accounts/{chk['id']}/info", json={"phone": "x"}).status_code == 403
    assert client.get(f"/api/accounts/{mine['id']}/info").status_code == 404  # someone else's private account


def test_reconciled(client, as_user):
    chk = add(client, name="Checking", balance=100)
    t1 = client.post(f"/api/accounts/{chk['id']}/transactions", json={"amount": -10, "merchant": "Cafe"}).json()
    t2 = client.post(f"/api/accounts/{chk['id']}/transactions", json={"amount": -20, "merchant": "Books"}).json()
    assert t1["reconciled"] is False
    r = client.patch(f"/api/transactions/{t1['id']}", json={"reconciled": True}).json()
    assert r["reconciled"] is True and r["edited"] is False  # not a change to what it says
    assert [t["id"] for t in client.get("/api/transactions?reconciled=no").json()["items"]] == [t2["id"]]
    assert client.post("/api/transactions/reconcile", json={"ids": [t1["id"], t2["id"]], "reconciled": True}).json()["changed"] == 2
    assert client.get("/api/transactions?reconciled=no").json()["total"] == 0
    assert client.get("/api/transactions?reconciled=yes").json()["total"] == 2
    as_user("viv", "viewer")
    assert client.post("/api/transactions/reconcile", json={"ids": [t1["id"]], "reconciled": False}).json()["changed"] == 0
