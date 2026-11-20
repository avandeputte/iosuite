"""What the security review of 20 November 2026 settled: a recurring transaction kept for any account, and the
transfer rules, show nothing of someone else's private account."""
import datetime as dt

from app import db
from conftest import sign_in
from test_api import add


def test_recurring_and_transfer_rules_leave_out_private_accounts(client, as_user):
    hh = add(client, name="Household")
    last_month = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    r = client.post("/api/recurring", json={"name": "Rent", "amount": 1500, "day": last_month})  # any account
    assert r.status_code == 201 and r.json()["accountId"] is None
    as_user("sam", "member")
    mine = add(client, name="Sam's savings")
    assert client.post(f"/api/accounts/{mine['id']}/transactions",
                       json={"day": last_month, "amount": -1500, "merchant": "Rent"}).status_code == 201
    rent = next(x for x in client.get("/api/recurring").json()["items"] if x["name"] == "Rent")
    assert rent["last"]["amount"] == -1500  # Sam sees their own payment
    db.ex("INSERT INTO mny_transfer_rules (account_id, pattern, other_id, days, source) VALUES (%s, 'sam secret', %s, 7, 'learned')",
          (mine["id"], hh["id"]))
    rid = db.one("SELECT id FROM mny_transfer_rules WHERE pattern = 'sam secret'")["id"]
    assert [x["pattern"] for x in client.get("/api/transfer-rules").json()["items"]] == ["sam secret"]
    sign_in(client, "alex")
    rent = next(x for x in client.get("/api/recurring").json()["items"] if x["name"] == "Rent")
    assert rent["last"] is None and rent["flag"] is None  # not from Sam's private account
    bills = client.get(f"/api/bills?start={last_month}&end={last_month}").json()["items"]
    assert [b["paid"] for b in bills if b["merchant"] == "Rent"] == [False]
    assert client.get("/api/transfer-rules").json()["items"] == []
    assert client.delete(f"/api/transfer-rules/{rid}").status_code == 404
