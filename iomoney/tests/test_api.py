"""The REST API: accounts and who sees them, the net worth and its history, transactions and the spending, holdings
and the portfolio (quotes from a stand-in for Yahoo Finance), house and car values with their loan, the recurring transactions ioMoney finds (subscriptions among them) and the bills
ioCalendar shows, and the categories."""
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


def months_ago(n):
    from app import recurring
    t = dt.date.today()
    return recurring._add_months(t, -n, t.day).isoformat()


def test_recurring_found_added_and_shown_as_bills(client, as_user):
    a = add(client)
    post = lambda **b: client.post(f"/api/accounts/{a['id']}/transactions", json=b)  # noqa: E731
    for n, amt in ((3, -82), (2, -79.5), (1, -80.4)):
        assert post(day=months_ago(n), amount=amt, merchant="Power co", category="Utilities").status_code == 201
    for n in (2, 1):
        post(day=months_ago(n), amount=-15.49, merchant="NETFLIX.COM")
    for d in (56, 42, 28, 14):
        post(day=(dt.date.today() - dt.timedelta(days=d)).isoformat(), amount=2000, merchant="ACME PAYROLL")
    for d, amt in ((40, -12), (33, -140), (21, -61), (9, -7)):
        post(day=(dt.date.today() - dt.timedelta(days=d)).isoformat(), amount=amt, merchant="Grocer")
    r = client.get("/api/recurring").json()
    assert r["items"] == [] and r["writable"]
    f = {x["name"]: x for x in r["found"]}
    assert set(f) == {"Power co", "NETFLIX.COM", "ACME PAYROLL"}  # the grocer's amounts are all over the place
    assert f["Power co"]["frequency"] == "monthly" and f["Power co"]["approximate"] and f["Power co"]["category"] == "Utilities"
    assert f["Power co"]["subscription"] is False and f["NETFLIX.COM"]["subscription"] is True  # a known service, twice is enough
    assert f["ACME PAYROLL"]["frequency"] == "biweekly" and f["ACME PAYROLL"]["flow"] == "in" and f["ACME PAYROLL"]["amount"] == 2000
    for name in ("Power co", "NETFLIX.COM"):
        assert client.post("/api/recurring", json={"found": f[name]["key"]}).status_code == 201
    assert client.post("/api/recurring/not", json={"key": f["ACME PAYROLL"]["key"]}).json()["ok"]
    r = client.get("/api/recurring").json()
    assert r["found"] == []  # added, or not recurring: not offered again
    items = {x["name"]: x for x in r["items"]}
    nf = items["NETFLIX.COM"]
    assert nf["subscription"] and nf["perMonth"] == -15.49 and nf["last"]["amount"] == -15.49 and nf["source"] == "found"
    assert months_ago(0) <= items["Power co"]["next"] <= months_ago(-1) and items["Power co"]["amount"] == -80.4
    # by hand: a known service is a subscription on its own, and the gym is marked as one
    s = client.post("/api/recurring", json={"name": "Spotify", "amount": 11.99, "day": months_ago(0)}).json()
    assert s["subscription"] and s["flow"] == "out" and s["pattern"] == "spotify"
    g = client.post("/api/recurring", json={"name": "Gym", "amount": 360, "frequency": "yearly", "day": months_ago(1), "subscription": True}).json()
    assert g["subscription"] and g["perMonth"] == -30
    assert client.patch(f"/api/recurring/{g['id']}", json={"subscription": False}).json()["subscription"] is False
    assert client.post("/api/recurring", json={"name": "Water", "amount": 1, "frequency": "hourly"}).status_code == 400
    # the bills ioCalendar shows: last month's power bill paid, this month's due
    b = client.get(f"/api/bills?start={months_ago(1)}&end={months_ago(-1)}").json()["items"]
    power = [x for x in b if x["merchant"] == "Power co"]
    assert [x["paid"] for x in power][:2] == [True, False] and power[0]["amount"] == -80.4 and power[0]["account"] == "Checking"
    assert any(x["merchant"] == "Spotify" and x["subscription"] and not x["paid"] for x in b)
    assert client.delete(f"/api/recurring/{s['id']}").json()["ok"]
    # from the transaction list: which ones are recurring, and one made recurring from a transaction
    txs = {x["merchant"]: x for x in client.get("/api/transactions?limit=500").json()["items"]}
    assert txs["NETFLIX.COM"]["recurring"]["name"] == "NETFLIX.COM" and txs["NETFLIX.COM"]["recurring"]["subscription"]
    assert txs["Grocer"]["recurring"] is None
    got = client.get(f"/api/transactions/{txs['NETFLIX.COM']['id']}/recurring").json()
    assert got["item"]["id"] == nf["id"] and got["suggestion"] is None and got["writable"]
    pay = client.get(f"/api/transactions/{txs['ACME PAYROLL']['id']}/recurring").json()  # set aside as not recurring, still made one by hand
    sug = pay["suggestion"]
    assert pay["item"] is None and sug["frequency"] == "biweekly" and sug["flow"] == "in" and sug["amount"] == 2000 and sug["count"] == 4
    assert sug["pattern"] == "acme payroll" and sug["accountId"] == a["id"] and sug["subscription"] is False
    assert client.post("/api/recurring", json=sug).status_code == 201
    assert client.get("/api/transactions?q=acme").json()["items"][0]["recurring"]["name"] == "ACME PAYROLL"
    # a person's own account: its recurring ones are theirs; the household's are the editors'
    as_user("sam", "member")
    assert client.post("/api/recurring", json={"name": "Water", "amount": 30}).status_code == 403
    mine = add(client, name="Sam's", household=False)
    sg = client.post("/api/recurring", json={"name": "Sam's gym", "amount": 30, "accountId": mine["id"]})
    assert sg.status_code == 201 and sg.json()["writable"]
    assert {x["name"] for x in client.get("/api/recurring").json()["items"]} == {"Power co", "NETFLIX.COM", "Gym", "ACME PAYROLL", "Sam's gym"}
    sign_in(client, "alex")
    as_user("ed", "editor")
    assert client.post("/api/recurring", json={"name": "Ed's gym", "amount": 30, "accountId": mine["id"]}).status_code == 400  # not one Ed sees
    assert client.delete(f"/api/recurring/{sg.json()['id']}").status_code == 404
    sign_in(client, "alex")
    assert "Sam's gym" not in {x["merchant"] for x in client.get(f"/api/bills?start={months_ago(1)}&end={months_ago(-1)}").json()["items"]}


def test_recurring_found_despite_outliers_renames_and_shared_payees(client):
    """What a real household's transactions look like: a bonus among the paychecks, a payee Monarch renamed while the
    bank's text stayed, two loans paid to one bank, a loan's payment linked as a transfer, a bill every two months, a
    yearly one seen twice in two years, a utility whose amount swings, a one-off tiny charge among a phone bill's."""
    chk = add(client)
    card = add(client, name="Card", kind="credit", balance=0)
    loan = add(client, name="Car loan", kind="loan", balance=9000, track="transactions")
    today = dt.date.today()
    d = lambda n: (today - dt.timedelta(days=n)).isoformat()  # noqa: E731

    def tx(acct, day, amount, merchant, description=None):
        return db.ex("INSERT INTO mny_transactions (account_id, source, day, amount, merchant, description, words) "
                     "VALUES (%s, 'manual', %s, %s, %s, %s, %s)", (acct["id"], day, amount, merchant, description, model.words(merchant, description)))
    for i in range(20):  # every other Friday; a bonus once, a raise lately
        tx(chk, d(4 + 14 * i), 24000 if i == 9 else 3600 if i < 2 else 3200, "Acme Corp", "PAYROLL ACME CORP ACH CREDIT")
    for i in range(12):  # two car loans at one bank, renamed by Monarch half way; the bank's text stays
        name = "Big Bank" if i < 6 else "Car Loan Payment"
        tx(chk, months_ago(i), -563.14, name, "*2903 EXT TRNSFR BIGBANK ACH WEB-RECUR")
        tx(chk, (dt.date.fromisoformat(months_ago(i)) - dt.timedelta(days=2)).isoformat(), -368.88, name, "*2903 EXT TRNSFR BIGBANK ACH WEB-RECUR")
    for i in range(10):  # the mortgage, linked as a transfer to the loan account; the card's payment, linked too
        o = tx(chk, months_ago(i), -1182.59, "Mortgage", "PYMT MORTGAGE ACH DEBIT")
        db.ex("INSERT INTO mny_transfers (out_id, in_id) VALUES (%s, %s)", (o, tx(loan, months_ago(i), 1182.59, "Payment")))
        o = tx(chk, months_ago(i), -700 - i, "Card payment", "AUTOPAY CARD")
        db.ex("INSERT INTO mny_transfers (out_id, in_id) VALUES (%s, %s)", (o, tx(card, months_ago(i), 700 + i, "Thank you")))
    for i in range(5):
        tx(card, months_ago(2 * i), -45, "Mobile Co")  # every two months
    for n in (20, 385, 750):
        tx(card, d(n), -99.99, "Office Suite")  # yearly, seen three times in two years
    for i, amt in enumerate([31.2, 88.4, 140.0, 219.5, 180.1, 64.9, 42.0, 35.5]):
        tx(chk, months_ago(i), -amt, "City Water", "UTILITYPMT CITYWATER WEB")  # the amount swings with the seasons
    for i in range(8):
        tx(chk, months_ago(i), -0.17 if i == 2 else -20, "Phone Co", "PHONECO AUTO PAY")
    found = client.get("/api/recurring").json()["found"]
    by = {}
    for x in found:
        by.setdefault(x["name"], []).append(x)
    pay = by["Acme Corp"][0]
    assert pay["frequency"] == "biweekly" and pay["flow"] == "in" and pay["amount"] == 3200 and pay["count"] >= 17
    loans = sorted(by["Big Bank"], key=lambda x: x["amount"])
    assert [x["amount"] for x in loans] == [-563.14, -368.88] and all(x["frequency"] == "monthly" and not x["approximate"] for x in loans)
    assert loans[0]["pattern"] == "big bank|car loan payment" and loans[0]["count"] == 12
    assert by["Mortgage"][0]["amount"] == -1182.59  # a loan's payment is a bill
    assert "Card payment" not in by and "Payment" not in by and "Thank you" not in by  # a card's payment is not
    assert by["Mobile Co"][0]["frequency"] == "bimonthly"
    assert by["Office Suite"][0]["frequency"] == "yearly"
    assert by["City Water"][0]["approximate"] and by["City Water"][0]["frequency"] == "monthly"
    assert by["Phone Co"][0]["amount"] == -20 and not by["Phone Co"][0]["approximate"]
    # added, its payments under both names are its own
    assert client.post("/api/recurring", json={"found": loans[0]["key"]}).status_code == 201
    item = next(x for x in client.get("/api/recurring").json()["items"] if x["name"] == "Big Bank")
    assert item["last"]["amount"] == -563.14
    old = [t for t in client.get("/api/transactions?q=car+loan+payment&limit=50").json()["items"] if t["amount"] == -563.14]
    assert old and all(t["recurring"]["name"] == "Big Bank" for t in old)
    assert len([x for x in client.get("/api/recurring").json()["found"] if x["name"] == "Big Bank"]) == 1  # the other loan


def test_transactions_by_amount(client):
    a = add(client)
    for amt, who in ((-280, "Friend"), (-280.5, "Garage"), (150, "Refund"), (-12.5, "Cafe"), (-7834, "Tax")):
        client.post(f"/api/accounts/{a['id']}/transactions", json={"amount": amt, "merchant": who, "notes": "ref 7834" if who == "Cafe" else None})
    names = lambda **p: sorted(t["merchant"] for t in client.get("/api/transactions", params=p).json()["items"])  # noqa: E731
    assert names(amount="280") == ["Friend"]
    assert names(amount="$280.50") == ["Garage"]
    assert names(amount="100-300") == ["Friend", "Garage", "Refund"]
    assert names(amount=">1000") == ["Tax"] and names(amount="<20") == ["Cafe"]
    assert names(amount="100-300", flow="in") == ["Refund"]
    assert names(q="$12.50") == ["Cafe"] and names(q="200..290") == ["Friend", "Garage"]
    assert names(q="7834") == ["Cafe", "Tax"]  # a bare number: the amount, or words that have it
    assert client.get("/api/transactions", params={"amount": "lots"}).status_code == 400


def test_manual_transactions_and_categories(client):
    a = add(client)
    db.ex("UPDATE mny_accounts SET source = 'monarch', external_id = 'm1' WHERE id = %s", (a["id"],))  # one from Monarch takes them too
    t = client.post(f"/api/accounts/{a['id']}/transactions", json={"amount": -20, "merchant": "Corner shop", "category": "Groceries"}).json()
    assert t["source"] == "manual" and t["category"] == "Groceries"
    assert client.get(f"/api/accounts/{a['id']}").json()["balance"] == 1000.5  # Monarch's balance stays Monarch's
    client.post(f"/api/accounts/{a['id']}/transactions", json={"amount": -5, "merchant": "Bakery", "category": "Bread"})
    assert client.post("/api/categories", json={"name": "Pets", "group": "Home"}).status_code == 201
    assert client.post("/api/categories", json={"name": "Pets"}).status_code == 400
    c = {x["category"]: x for x in client.get("/api/categories").json()["items"]}
    assert c["Pets"]["group"] == "Home" and c["Pets"]["count"] == 0 and c["Groceries"]["count"] == 1
    client.post("/api/rules", json={"pattern": "corner", "setCategory": "Groceries"})
    # renamed (and put in a group): its transactions and rules follow
    r = client.put("/api/categories", json={"name": "Groceries", "newName": "Food", "group": "Everyday"}).json()
    assert r["moved"] == 1
    t = next(x for x in client.get("/api/transactions").json()["items"] if x["id"] == t["id"])
    assert t["category"] == "Food" and t["group"] == "Everyday"
    assert client.get("/api/rules").json()["items"][0]["setCategory"] == "Food"
    assert client.get("/api/transactions?q=food").json()["total"] == 1
    # merged into another, then deleted with its transactions moved
    assert client.put("/api/categories", json={"name": "Bread", "newName": "Food"}).json()["moved"] == 1
    c = {x["category"]: x for x in client.get("/api/categories").json()["items"]}
    assert "Bread" not in c and c["Food"]["count"] == 2 and c["Food"]["group"] == "Everyday"
    assert client.post("/api/categories/delete", json={"name": "Food", "moveTo": "Food"}).status_code == 400
    assert client.post("/api/categories/delete", json={"name": "Food", "moveTo": "Pets"}).json()["moved"] == 2
    c = {x["category"]: x for x in client.get("/api/categories").json()["items"]}
    assert "Food" not in c and c["Pets"]["count"] == 2
    assert client.post("/api/categories/delete", json={"name": "Nope"}).status_code == 404


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
    # not a transfer: off the list for good, and not linked by itself
    grocer_out = next(t["id"] for t in client.get("/api/transactions?q=grocer").json()["items"] if t["amount"] < 0)
    assert client.post("/api/transfers/not", json={"outId": refund["id"], "inId": grocer_out}).status_code == 400  # out first
    assert client.post("/api/transfers/not", json={"outId": grocer_out, "inId": refund["id"]}).json()["ok"]
    assert (grocer_out, refund["id"]) not in {(p["out"]["id"], p["in"]["id"]) for p in client.get("/api/transfers/possible").json()["items"]}
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
        tx(visa, 1830.67, "THANK YOU FOR YOUR PMT XXXX2530", 20, category="Paychecks", hidden=True)  # a hidden twin: not a rival
        over = (tx(sav, -300, "Overdraft Transfer to Spending Account XXXXXX2748", 50),
                tx(chk, 300, "Overdraft Transfer from Savings Account XXXXXX7081", 50))
        fid = tx(pnc, -300, "MONEYLINE FID BKG SVC LLC ACH DEBIT", 45, category="Transfer")
        # two payments of the same amount from the checking account to the card, two days apart: either way is the same
        two = [tx(pnc, -32.10, "ONLINE PMT AMERICAN EXPRESS", 10, category="Transfer"), tx(pnc, -32.10, "ACH PMT AMEX EPAYMENT", 10, category="Credit Card Payment"),
               tx(visa, 32.10, "ELECTRONIC PAYMENT RECEIVED-THANK", 10, category="Transfer"), tx(visa, 32.10, "AUTOPAY PAYMENT - THANK YOU", 12, category="Credit Card Payment")]
    r = client.post("/api/transfers/link").json()
    assert r["linked"] == 7 and not any(p["out"]["amount"] == -32.10 for p in r["possible"])
    assert all(client.get(f"/api/transactions/{t['id']}/transfer").json()["other"] for t in two)
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
