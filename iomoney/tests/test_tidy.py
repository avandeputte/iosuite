"""Putting the data in order: many transactions changed at once, what needs a look, the payees, own tags, likely
duplicates, reconciling against a statement, the rules' upkeep, the history of changes and the way back, saved
searches, and a bank's file brought into an account kept by hand."""
import datetime as dt

from app import db, importer
from conftest import sign_in
from test_api import add

TODAY = dt.date.today()
D = lambda n: (TODAY - dt.timedelta(days=n)).isoformat()  # noqa: E731


def tx(client, a, amount, merchant, days=0, **f):
    r = client.post(f"/api/accounts/{a['id']}/transactions", json={"amount": amount, "merchant": merchant, "day": D(days), **f})
    assert r.status_code == 201, r.text
    return r.json()


def get(client, tid):
    return client.get(f"/api/transactions/{tid}").json()


def test_many_at_once_and_taken_back(client, as_user):
    a = add(client)
    mine = add(client, name="Mine", household=False)
    ids = [tx(client, a, -10 * n, f"Shop {n}", n)["id"] for n in range(1, 5)]
    other = tx(client, mine, -5, "Private")
    assert client.post("/api/transactions/bulk", json={"ids": [], "set": {"category": "x"}}).status_code == 400
    assert client.post("/api/transactions/bulk", json={"ids": ids, "set": {"day": "2020-01-01"}}).status_code == 400  # not that
    r = client.post("/api/transactions/bulk", json={"ids": ids[:3], "set": {"category": "Household", "addTags": ["Trip", "trip", "2026"]}}).json()
    assert r["changed"] == 3 and r["skipped"] == 0 and r["batch"]
    got = [get(client, i) for i in ids]
    assert [t["category"] for t in got] == ["Household"] * 3 + [None]
    assert got[0]["ownTags"] == ["2026", "Trip"] and got[0]["tags"] == ["2026", "Trip"] and got[0]["edited"]
    # hidden and reconciled in one go; a tag off again
    r2 = client.post("/api/transactions/bulk", json={"ids": ids, "set": {"hidden": True, "reconciled": True, "removeTags": ["TRIP"]}}).json()
    assert r2["changed"] == 4
    assert all(t["hidden"] and t["reconciled"] for t in (get(client, i) for i in ids)) and get(client, ids[0])["ownTags"] == ["2026"]
    # the changes made together are one in the list, and taken back as one
    ch = client.get("/api/changes").json()["items"]
    assert [(c["what"], c["count"], c["canUndo"]) for c in ch[:2]] == [("bulk", 4, True), ("bulk", 3, True)]
    assert ch[0]["by"] == "alex" and len(ch[0]["changes"]) == 4 and ch[0]["changes"][0]["transaction"]["payee"].startswith("Shop")
    assert client.post("/api/changes/undo", json={"batch": r2["batch"]}).json()["undone"] == 4
    back = get(client, ids[0])
    assert back["hidden"] is False and back["ownTags"] == ["2026", "Trip"] and back["category"] == "Household"
    assert back["reconciled"] is True  # reconciled is not what the transaction says: it has its own way back
    assert client.post("/api/changes/undo", json={"batch": r2["batch"]}).status_code == 404  # once
    assert client.post("/api/changes/undo", json={"batch": r["batch"]}).json()["undone"] == 3
    assert get(client, ids[0])["category"] is None and get(client, ids[0])["ownTags"] == []
    # someone else's private one is skipped, and a viewer changes none
    as_user("ed", "editor")
    r = client.post("/api/transactions/bulk", json={"ids": [ids[0], other["id"], 99999], "set": {"notes": "checked"}}).json()
    assert r["changed"] == 1 and r["skipped"] == 2
    sign_in(client, "alex")
    as_user("viv", "viewer")
    r = client.post("/api/transactions/bulk", json={"ids": ids, "set": {"notes": "no"}}).json()
    assert (r["changed"], r["skipped"]) == (0, 4) and get(client, ids[1])["notes"] is None


def test_needs_a_look(client, as_user):
    a = add(client)
    client.post("/api/rules", json={"pattern": "grocer", "setCategory": "Groceries"})
    # what was there before the household started looking counts as seen, unless it has no category
    db.set_setting("review_since", str(int((dt.datetime.now() + dt.timedelta(seconds=-5)).timestamp())))
    typed = tx(client, a, -20, "Grocer", 1)      # typed in by a person: looked at
    assert client.get("/api/summary").json()["review"] == 0
    # two that came in by themselves (a file): one the rules categorized, one without a category
    r = client.post(f"/api/accounts/{a['id']}/import", json={"text": f"Date,Amount,Description\n{D(2)},-30.00,GROCER 12\n{D(3)},-7.50,Mystery\n"}).json()
    assert r["added"] == 2
    assert client.get("/api/summary").json()["review"] == 2
    items = client.get("/api/transactions?review=yes").json()["items"]
    assert sorted(t["merchant"] for t in items) == ["GROCER 12", "Mystery"]
    grocer = next(t for t in items if t["merchant"] == "GROCER 12")
    mystery = next(t for t in items if t["merchant"] == "Mystery")
    assert grocer["category"] == "Groceries"
    # changing one by hand marks it; the other is marked reviewed as it is
    client.patch(f"/api/transactions/{mystery['id']}", json={"category": "Gifts"})
    assert [t["id"] for t in client.get("/api/transactions?review=yes").json()["items"]] == [grocer["id"]]
    assert client.post("/api/transactions/review", json={"ids": [grocer["id"]]}).json() == {"changed": 1, "left": 0}
    assert client.post("/api/transactions/review", json={"ids": [grocer["id"]], "reviewed": False}).json()["left"] == 1
    # an old one without a category needs a look too, until someone says it is fine
    db.ex("UPDATE mny_transactions SET created_at = '2020-01-01' WHERE id = %s", (typed["id"],))
    db.ex("DELETE FROM mny_reviewed WHERE transaction_id = %s", (typed["id"],))
    assert client.get("/api/summary").json()["review"] == 1
    db.ex("UPDATE mny_transactions SET category = NULL WHERE id = %s", (typed["id"],))
    assert client.get("/api/summary").json()["review"] == 2
    # a viewer sees them and marks none; all at once for who may
    as_user("viv", "viewer")
    assert client.get("/api/summary").json()["review"] == 2
    assert client.post("/api/transactions/review", json={"all": True}).json() == {"changed": 0, "left": 2}
    sign_in(client, "alex")
    assert client.post("/api/transactions/review", json={"all": True}).json() == {"changed": 2, "left": 0}
    assert client.get("/api/tidy").json()["review"] == 0


def test_payees_renamed_merged_and_categorized(client, as_user):
    a = add(client)
    t1 = tx(client, a, -40, "SHELL OIL 5512", 1)
    t2 = tx(client, a, -35, "SHELL OIL 5512", 9, category="Fuel")
    t3 = tx(client, a, -50, "Shell", 4)
    tx(client, a, -9, "Bakery", 2)
    p = client.get("/api/payees").json()
    assert p["writable"] and p["total"] == 3
    assert [(x["payee"], x["count"], x["total"]) for x in p["items"]] == [("SHELL OIL 5512", 2, -75), ("Bakery", 1, -9), ("Shell", 1, -50)]
    shell = p["items"][0]
    assert shell["categories"] == 2 and shell["last"] == D(1) and shell["rule"] is None
    assert [x["payee"] for x in client.get("/api/payees?q=oil").json()["items"]] == ["SHELL OIL 5512"]
    # renamed into a name another payee has: the two are one, and what comes later under the old name too
    assert client.post("/api/payees/rename", json={"name": "SHELL OIL 5512", "newName": "SHELL OIL 5512"}).status_code == 400
    r = client.post("/api/payees/rename", json={"name": "SHELL OIL 5512", "newName": "Shell"}).json()
    assert r["changed"] == 2
    assert [(x["payee"], x["count"]) for x in client.get("/api/payees").json()["items"]] == [("Shell", 3), ("Bakery", 1)]
    assert client.get("/api/transactions?q=shell").json()["total"] == 3
    assert tx(client, a, -20, "SHELL OIL 5512")["merchant"] == "Shell"
    rules = client.get("/api/rules").json()["items"]
    assert [(x["pattern"], x["how"], x["setMerchant"]) for x in rules] == [("SHELL OIL 5512", "is", "Shell")]
    # its usual category: a rule, and the transactions not changed by hand; with all, those too
    client.patch(f"/api/transactions/{t3['id']}", json={"category": "Travel"})
    r = client.post("/api/payees/category", json={"name": "Shell", "category": "Fuel"}).json()
    assert r["changed"] == 2  # t1 and the one just added (t2 has it, t3 was changed by hand)
    assert get(client, t1["id"])["category"] == "Fuel" and get(client, t3["id"])["category"] == "Travel"
    assert client.post("/api/payees/category", json={"name": "Shell", "category": "Fuel", "all": True}).json()["changed"] == 1
    assert get(client, t3["id"])["category"] == "Fuel" and get(client, t2["id"])["category"] == "Fuel"
    shell = client.get("/api/payees").json()["items"][0]
    assert shell["category"] == "Fuel" and shell["categories"] == 1 and shell["rule"]["category"] == "Fuel"
    # the rule holds for what the rename rule makes of the old name
    assert tx(client, a, -22, "SHELL OIL 5512")["category"] == "Fuel"
    assert len(client.get("/api/rules").json()["items"]) == 2
    # again: the same rule, not another
    client.post("/api/payees/category", json={"name": "Shell", "category": "Car"})
    assert len(client.get("/api/rules").json()["items"]) == 2
    # editors only
    as_user("mem", "member")
    assert client.get("/api/payees").json()["writable"] is False
    assert client.post("/api/payees/rename", json={"name": "Bakery", "newName": "Baker"}).status_code == 403
    assert client.post("/api/payees/category", json={"name": "Bakery", "category": "Food"}).status_code == 403


def test_own_tags(client, as_user):
    a = add(client)
    t1 = tx(client, a, -100, "Hotel", 3, tags=["Trip", "reimbursable"])
    t2 = tx(client, a, -30, "Taxi", 2)
    assert t1["ownTags"] == ["reimbursable", "Trip"]
    r = client.patch(f"/api/transactions/{t2['id']}", json={"tags": "trip, #Work ,trip"}).json()
    assert r["ownTags"] == ["trip", "Work"]
    assert client.patch(f"/api/transactions/{t2['id']}", json={"tags": ["x" * 65]}).status_code == 400
    assert client.get("/api/transactions?tag=trip").json()["total"] == 2 and client.get("/api/transactions?tag=Work").json()["total"] == 1
    assert client.get("/api/transactions?q=reimb").json()["total"] == 1  # a search finds a tag's words
    # one Monarch sent counts beside those set here, and is not kept twice
    db.ex("UPDATE mny_transactions SET tags = %s WHERE id = %s", ('["Vacation", "Trip"]', t1["id"]))
    one = get(client, t1["id"])
    assert one["tags"] == ["Vacation", "Trip", "reimbursable"] and one["ownTags"] == ["reimbursable", "Trip"]
    assert client.get("/api/transactions?tag=Vacation").json()["total"] == 1
    tags = {x["tag"].lower(): x for x in client.get("/api/tags").json()["items"]}
    assert tags["trip"]["count"] == 2 and tags["trip"]["total"] == -130 and tags["trip"]["own"]
    assert tags["vacation"] == {"tag": "Vacation", "count": 1, "total": -100, "own": False}
    # renamed (into one there is: merged), removed
    assert client.put("/api/tags", json={"name": "Work", "newName": "trip"}).json()["moved"] == 1
    assert get(client, t2["id"])["ownTags"] == ["trip"]
    assert client.post("/api/tags/delete", json={"name": "reimbursable"}).json()["removed"] == 1
    assert get(client, t1["id"])["ownTags"] == ["Trip"] and client.get("/api/transactions?q=reimb").json()["total"] == 0
    as_user("mem", "member")
    assert client.put("/api/tags", json={"name": "trip", "newName": "x"}).status_code == 403


def test_likely_duplicates(client, as_user):
    a = add(client)
    b = add(client, name="Card", kind="credit", balance=0)
    d1 = tx(client, a, -42.5, "Hardware store", 5)
    d2 = tx(client, a, -42.5, "HARDWARE STORE", 4)     # the same payee, a day apart
    far = tx(client, a, -42.5, "Hardware store", 20)   # weeks before: another visit
    tx(client, a, -42.5, "Florist", 5)                 # the same amount, another payee
    tx(client, b, -42.5, "Hardware store", 5)          # another account
    c1, c2, c3 = (tx(client, a, -4.5, "Cafe", 1) for _ in range(3))
    g = client.get("/api/duplicates").json()["items"]
    assert [[t["id"] for t in x["items"]] for x in g] == [[c1["id"], c2["id"], c3["id"]], [d1["id"], d2["id"]]]
    assert g[1]["why"] == "same" and g[1]["whyText"] and far["id"] not in [t["id"] for x in g for t in x["items"]]
    assert client.get("/api/tidy").json()["duplicates"] == 2
    # one typed in and one from the bank look alike whatever they are called; a pending one beside the posted one too
    db.ex("UPDATE mny_transactions SET source = 'monarch', external_id = 'm1', merchant = 'Bloom & Co' WHERE id = %s", (far["id"],))
    typed = tx(client, a, -42.5, "flowers", 21)
    g = client.get("/api/duplicates").json()["items"]
    assert [x["why"] for x in g if typed["id"] in [t["id"] for t in x["items"]]] == ["typed"]
    # they are two: not offered again; hidden: gone from the list
    assert client.post("/api/duplicates/not", json={"ids": [c1["id"]]}).status_code == 400
    assert client.post("/api/duplicates/not", json={"ids": [c1["id"], c2["id"], c3["id"]]}).json()["ok"]
    client.patch(f"/api/transactions/{d2['id']}", json={"hidden": True})
    g = client.get("/api/duplicates").json()["items"]
    assert [[t["id"] for t in x["items"]] for x in g] == [[typed["id"], far["id"]]]  # the oldest first
    as_user("viv", "viewer")
    assert client.post("/api/duplicates/not", json={"ids": [far["id"], typed["id"]]}).status_code == 403


def test_reconcile_against_a_statement(client, as_user):
    a = add(client, balance=1000)
    t1 = tx(client, a, -100, "Rent share", 20)
    t2 = tx(client, a, 250, "Refund", 15)
    t3 = tx(client, a, -30, "Late one", 12)
    hid = tx(client, a, -20, "Hidden fee", 18, hidden=True)
    after = tx(client, a, -5, "After", 2)
    s = client.get(f"/api/accounts/{a['id']}/statements").json()
    assert s["items"] == [] and s["writable"] and s["next"]["start"] == D(20)
    lines = client.get(f"/api/accounts/{a['id']}/statement?start={D(25)}&end={D(10)}").json()
    assert [t["id"] for t in lines["items"]] == [t1["id"], hid["id"], t2["id"], t3["id"]] and lines["sign"] == 1  # the hidden one too
    assert client.get(f"/api/accounts/{a['id']}/statement?start={D(10)}&end={D(25)}").status_code == 400
    body = {"start": D(25), "end": D(10), "opening": 900, "closing": 1030, "ids": [t1["id"], t2["id"], hid["id"]]}
    # 900 - 100 + 250 - 20 = 1030
    assert client.post(f"/api/accounts/{a['id']}/statements", json={**body, "closing": 1000}).status_code == 400  # 30 off
    assert client.post(f"/api/accounts/{a['id']}/statements", json={**body, "ids": [t1["id"], after["id"]]}).status_code == 400  # after it
    r = client.post(f"/api/accounts/{a['id']}/statements", json=body)
    assert r.status_code == 201 and r.json()["difference"] == 0 and r.json()["reconciled"] == 3
    assert get(client, t1["id"])["reconciled"] and get(client, hid["id"])["reconciled"] and not get(client, t3["id"])["reconciled"]
    s = client.get(f"/api/accounts/{a['id']}/statements").json()
    assert [(x["start"], x["end"], x["opening"], x["closing"]) for x in s["items"]] == [(D(25), D(10), 900, 1030)]
    assert s["next"] == {"start": D(9), "opening": 1030}
    # the next statement: the one left open on the one before comes first, and can clear on this one
    lines = client.get(f"/api/accounts/{a['id']}/statement?start={D(9)}&end={D(0)}").json()["items"]
    assert [(t["id"], t["earlier"]) for t in lines] == [(t3["id"], True), (after["id"], False)]
    r = client.post(f"/api/accounts/{a['id']}/statements", json={"start": D(9), "end": D(0), "opening": 1030, "closing": 990, "ids": [t3["id"]], "anyway": True})
    assert r.status_code == 201 and r.json()["difference"] == -10  # 1030 - 30 = 1000, the statement says 990
    # what is owed: a purchase makes the balance go up
    card = add(client, name="Card", kind="credit", balance=80)
    buy = tx(client, card, -80, "Shoes", 3)
    r = client.post(f"/api/accounts/{card['id']}/statements", json={"start": D(5), "end": D(1), "opening": 0, "closing": 80, "ids": [buy["id"]]})
    assert r.status_code == 201 and r.json()["difference"] == 0
    sid = r.json()["id"]
    as_user("viv", "viewer")
    assert client.get(f"/api/accounts/{card['id']}/statements").json()["writable"] is False
    assert client.post(f"/api/accounts/{card['id']}/statements", json={"start": D(5), "end": D(1), "opening": 0, "closing": 80, "ids": []}).status_code == 403
    assert client.delete(f"/api/statements/{sid}").status_code == 403
    sign_in(client, "alex")
    assert client.delete(f"/api/statements/{sid}").json()["ok"] and get(client, buy["id"])["reconciled"]
    assert client.delete(f"/api/statements/{sid}").status_code == 404


def test_rules_upkeep_and_suggestions(client, as_user):
    a = add(client)
    r1 = client.post("/api/rules", json={"pattern": "coffee", "setCategory": "Coffee"}).json()
    r2 = client.post("/api/rules", json={"pattern": "coffee corner", "setCategory": "Restaurants"}).json()   # always behind r1
    r3 = client.post("/api/rules", json={"pattern": "zzz", "setHidden": True}).json()                        # matches nothing
    r4 = client.post("/api/rules", json={"pattern": "coffee", "setHidden": False, "enabled": False}).json()
    tx(client, a, -4, "Coffee corner", 1)
    tx(client, a, -5, "Coffee house", 2)
    for n in range(3):  # the same payee, the same category by hand, three times
        t = tx(client, a, -60 - n, "Dr. Molar", 10 + n)
        client.patch(f"/api/transactions/{t['id']}", json={"category": "Dentist"})
    tx(client, a, -70, "Dr. Molar", 30)
    # a rule that renames: the transaction then carries the new name, and the rule still counts as the one that did it
    r5 = client.post("/api/rules", json={"pattern": "KSK*", "field": "merchant", "how": "starts", "setMerchant": "Kiosk"}).json()
    assert tx(client, a, -3, "KSK*0042 MAIN ST", 4)["merchant"] == "Kiosk"
    up = client.get("/api/rules/upkeep").json()
    by = {x["id"]: x for x in up["rules"]}
    assert (by[r5["id"]]["matched"], by[r5["id"]]["decides"], by[r5["id"]]["note"]) == (1, 1, None)
    assert (by[r1["id"]]["matched"], by[r1["id"]]["decides"], by[r1["id"]]["note"], by[r1["id"]]["last"]) == (2, 2, None, D(1))
    assert (by[r2["id"]]["matched"], by[r2["id"]]["decides"], by[r2["id"]]["note"]) == (1, 0, "behind")
    assert by[r3["id"]]["note"] == "never" and by[r3["id"]]["noteText"] and by[r4["id"]]["note"] == "off"
    assert [(s["payee"], s["category"], s["count"], s["wouldChange"]) for s in up["suggestions"]] == [("Dr. Molar", "Dentist", 3, 1)]
    # turned down: not offered again; or added (the payee's usual category), and then a rule does it
    key = up["suggestions"][0]["key"]
    assert client.post("/api/rules/suggestions/not", json={"key": key}).json()["ok"]
    assert client.get("/api/rules/upkeep").json()["suggestions"] == []
    db.ex("DELETE FROM mny_rule_nots")
    assert client.post("/api/payees/category", json={"name": "Dr. Molar", "category": "Dentist"}).json()["changed"] == 1
    assert client.get("/api/rules/upkeep").json()["suggestions"] == []
    as_user("viv", "viewer")
    assert len(client.get("/api/rules/upkeep").json()["rules"]) == 6
    assert client.post("/api/rules/suggestions/not", json={"key": key}).status_code == 403


def test_history_of_a_transaction_and_undo(client, as_user):
    a = add(client, balance=100)
    t = tx(client, a, -10, "Kiosk", 1)
    assert client.get(f"/api/transactions/{t['id']}/changes").json()["items"] == []
    client.patch(f"/api/transactions/{t['id']}", json={"category": "Snacks", "notes": "for the road"})
    client.patch(f"/api/transactions/{t['id']}", json={"category": "Snacks"})  # nothing changed: nothing kept
    client.patch(f"/api/transactions/{t['id']}", json={"amount": -12, "merchant": "Kiosk 2", "tags": ["trip"]})
    ch = client.get(f"/api/transactions/{t['id']}/changes").json()["items"]
    assert len(ch) == 2 and ch[0]["by"] == "alex" and ch[0]["what"] == "hand"
    assert {f["field"]: (f["before"], f["after"]) for f in ch[0]["fields"]} == {"amount": (-10, -12), "payee": ("Kiosk", "Kiosk 2"), "tags": ([], ["trip"])}
    assert {f["field"]: (f["before"], f["after"]) for f in ch[1]["fields"]} == {"category": (None, "Snacks"), "notes": (None, "for the road")}
    assert client.get(f"/api/accounts/{a['id']}").json()["balance"] == 88
    # taken back: the fields as they were, the balance with them; the undo is a change of its own
    assert client.post("/api/changes/undo", json={"id": ch[0]["id"]}).json()["undone"] == 1
    back = get(client, t["id"])
    assert (back["amount"], back["merchant"], back["ownTags"], back["category"]) == (-10, "Kiosk", [], "Snacks")
    assert client.get(f"/api/accounts/{a['id']}").json()["balance"] == 90
    ch = client.get(f"/api/transactions/{t['id']}/changes").json()["items"]
    assert [(c["what"], c["undone"]) for c in ch] == [("undo", False), ("hand", True), ("hand", False)]
    assert client.post("/api/changes/undo", json={"id": ch[0]["id"]}).status_code == 404  # an undo is not undone
    assert client.post(f"/api/transactions/{t['id']}/reset").status_code == 400          # added here: nothing of Monarch's
    # a viewer reads the history and takes nothing back
    as_user("viv", "viewer")
    assert len(client.get(f"/api/transactions/{t['id']}/changes").json()["items"]) == 3
    assert client.post("/api/changes/undo", json={"id": ch[2]["id"]}).status_code == 403
    assert all(not c["canUndo"] for c in client.get("/api/changes").json()["items"])


def test_saved_searches_are_each_persons_own(client, as_user):
    assert client.post("/api/searches", json={"name": "", "query": "q=x"}).status_code == 400
    assert client.post("/api/searches", json={"name": "Nothing", "query": "bogus=1"}).status_code == 400
    r = client.post("/api/searches", json={"name": "Big ones", "query": "?amt=%3E500&flow=out&bogus=1"})
    assert r.status_code == 201 and r.json()["query"] == "flow=out&amt=%3E500"
    client.post("/api/searches", json={"name": "Trip", "query": "tag=Trip"})
    again = client.post("/api/searches", json={"name": "Big ones", "query": "amt=%3E900"}).json()  # the same name: replaced
    assert again["id"] == r.json()["id"] and again["query"] == "amt=%3E900"
    assert [s["name"] for s in client.get("/api/searches").json()["items"]] == ["Big ones", "Trip"]
    assert client.patch(f"/api/searches/{again['id']}", json={"name": "Large", "position": 9}).json()["name"] == "Large"
    assert [s["name"] for s in client.get("/api/searches").json()["items"]] == ["Trip", "Large"]
    as_user("viv", "viewer")
    assert client.get("/api/searches").json()["items"] == []
    assert client.delete(f"/api/searches/{again['id']}").status_code == 404
    assert client.post("/api/searches", json={"name": "Mine", "query": "q=tea"}).status_code == 201
    sign_in(client, "alex")
    assert client.delete(f"/api/searches/{again['id']}").json()["ok"]
    assert [s["name"] for s in client.get("/api/searches").json()["items"]] == ["Trip"]
    # gone with the person
    from app import persondata
    viv = db.one("SELECT user_id FROM mny_searches WHERE name = 'Mine'")["user_id"]
    assert next(x for x in persondata.of(viv, False) if x["what"] == "saved searches")["count"] == 1
    persondata.of(viv, True)
    assert db.one("SELECT count(*) AS n FROM mny_searches WHERE user_id = %s", (viv,))["n"] == 0


CSV = """Account,Checking 1234
Exported,2026-01-31

Posted Date,Description,Debit,Credit,Category
01/15/2026,"COFFEE, CORNER",4.50,,Coffee
01/16/2026,PAYROLL ACME,,"2,500.00",
01/17/2026,Bookshop,(12.00),,
bad row,x,,,
01/31/2026,CARD FEE,1.00,,
"""

OFX = """OFXHEADER:100
DATA:OFXSGML
<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260115120000[-5:EST]<TRNAMT>-4.50<FITID>A1<NAME>COFFEE &amp; CORNER<MEMO>Card 1234</STMTTRN>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260116<TRNAMT>2500.00<FITID>A2<NAME>PAYROLL ACME
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260120<TRNAMT>-80,25<FITID>A3<MEMO>Utilities
</STMTTRN>
</BANKTRANLIST><LEDGERBAL><BALAMT>3415.25<DTASOF>20260131</LEDGERBAL></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>
"""


def test_reading_amounts_and_dates():
    A, d = importer.amount, importer.date
    assert [float(A(x)) for x in ("1,234.56", "1.234,56", "(12.00)", "12.00-", "-12", "$ 7", "12,5", "1,250", "3.00 CR", "3.00 DR", "+4")] == \
        [1234.56, 1234.56, -12, -12, -12, 7, 12.5, 1250, 3, -3, 4]
    assert A("") is None and A("  ") is None
    assert d("01/15/2026", "mdy") == d("15/01/2026", "dmy") == d("2026-01-15") == d("20260115") == d("Jan 15, 2026") == \
        d("15 Jan 2026") == d("15.01.26", "dmy") == d("1/15/26 10:22", "mdy") == dt.date(2026, 1, 15)
    assert importer.order_of(["01/15/2026", "02/03/2026"]) == ("mdy", False) and importer.order_of(["15/01/2026"]) == ("dmy", False)
    assert importer.order_of(["01/02/2026", "03/04/2026"]) == ("mdy", True) and importer.order_of(["01.02.2026"]) == ("dmy", True)
    assert importer.order_of(["2026-01-02"]) == ("ymd", False)


def test_a_banks_file_into_an_account_kept_by_hand(client, as_user):
    a = add(client, balance=1000)
    client.post("/api/rules", json={"pattern": "payroll", "setMerchant": "Acme Inc", "setCategory": "Paychecks"})
    had = tx(client, a, -4.5, "Coffee", (TODAY - dt.date(2026, 1, 15)).days)  # typed in before: the file's is not added again
    bal = client.get(f"/api/accounts/{a['id']}").json()["balance"]
    p = client.post(f"/api/accounts/{a['id']}/import", json={"name": "export.csv", "text": CSV, "preview": True}).json()
    assert p["kind"] == "csv" and p["columns"] == ["Posted Date", "Description", "Debit", "Credit", "Category"]
    assert p["mapping"] == {"date": 0, "debit": 2, "credit": 3, "payee": 1, "category": 4} and p["dateOrder"] == "mdy" and not p["guessed"]
    assert (p["total"], p["new"], p["duplicates"], p["problemCount"]) == (4, 3, 1, 1) and p["problems"][0]["line"] == 8
    assert (p["from"], p["to"]) == ("2026-01-15", "2026-01-31") and "added" not in p
    assert [(r["day"], r["amount"], r["payee"], r["new"]) for r in p["rows"]][:2] == [("2026-01-15", -4.5, "COFFEE, CORNER", False), ("2026-01-16", 2500, "PAYROLL ACME", True)]
    assert client.get("/api/transactions").json()["total"] == 1  # a preview adds nothing
    r = client.post(f"/api/accounts/{a['id']}/import", json={"text": CSV}).json()
    assert r["added"] == 3 and client.get("/api/transactions").json()["total"] == 4
    got = {t["description"]: t for t in client.get("/api/transactions").json()["items"] if t["id"] != had["id"]}
    pay = got["PAYROLL ACME"]
    assert (pay["merchant"], pay["category"], pay["amount"], pay["day"], pay["source"], pay["edited"]) == ("Acme Inc", "Paychecks", 2500, "2026-01-16", "manual", False)
    assert got["Bookshop"]["amount"] == -12 and got["CARD FEE"]["amount"] == -1
    assert client.get(f"/api/accounts/{a['id']}").json()["balance"] == bal + 2500 - 12 - 1  # the balance moved by what came in
    # the same file again: nothing new
    r = client.post(f"/api/accounts/{a['id']}/import", json={"text": CSV}).json()
    assert (r["new"], r["duplicates"], r["added"]) == (0, 4, 0)
    # columns said by hand, day before month, money out written as a positive number
    eu = "x;y;z\n03.02.2026;Bakkerij;12,50\n04.02.2026;Salaris;-100,00\n"
    p = client.post(f"/api/accounts/{a['id']}/import", json={"text": eu, "preview": True}).json()
    assert p["mapping"] == {"date": 0, "amount": 2, "payee": 1} and p["dateOrder"] == "dmy" and p["guessed"]  # no headings: by what they hold
    r = client.post(f"/api/accounts/{a['id']}/import", json={"text": eu, "mapping": {"date": 0, "amount": 2, "payee": 1}, "dateOrder": "dmy",
                                                             "flip": True, "balance": "keep"}).json()
    assert r["added"] == 2 and client.get(f"/api/accounts/{a['id']}").json()["balance"] == bal + 2487
    assert client.get("/api/transactions?q=bakkerij").json()["items"][0]["amount"] == -12.5
    assert client.get("/api/transactions?q=salaris").json()["items"][0]["day"] == "2026-02-04"
    # a file whose columns say nothing asks
    p = client.post(f"/api/accounts/{a['id']}/import", json={"text": "a,b\nfoo,bar\n"}).json()
    assert p["needs"] and "added" not in p
    assert client.post(f"/api/accounts/{a['id']}/import", json={"text": " "}).status_code == 400
    # OFX / QFX: the fields are named, the bank's id keeps a transaction from coming in twice, and the file's balance can be taken
    p = client.post(f"/api/accounts/{a['id']}/import", json={"name": "x.qfx", "text": OFX, "preview": True}).json()
    assert (p["kind"], p["total"], p["new"], p["duplicates"], p["fileBalance"]) == ("ofx", 3, 1, 2, 3415.25)
    r = client.post(f"/api/accounts/{a['id']}/import", json={"text": OFX, "balance": "file"}).json()
    assert r["added"] == 1 and client.get(f"/api/accounts/{a['id']}").json()["balance"] == 3415.25
    util = client.get("/api/transactions?q=utilities").json()["items"][0]
    assert (util["amount"], util["day"], util["merchant"]) == (-80.25, "2026-01-20", "Utilities")
    client.patch(f"/api/transactions/{util['id']}", json={"day": "2026-01-25", "amount": -81})  # changed since: still known by its id
    assert client.post(f"/api/accounts/{a['id']}/import", json={"text": OFX, "preview": True}).json()["new"] == 0
    # not into an account Monarch keeps, nor one followed by its value alone; and not by a viewer
    sav = add(client, name="Savings", track="value")
    assert client.post(f"/api/accounts/{sav['id']}/import", json={"text": CSV}).status_code == 400
    db.ex("UPDATE mny_accounts SET source = 'monarch' WHERE id = %s", (sav["id"],))
    assert client.post(f"/api/accounts/{sav['id']}/import", json={"text": CSV}).status_code == 400
    as_user("viv", "viewer")
    assert client.post(f"/api/accounts/{a['id']}/import", json={"text": CSV, "preview": True}).status_code == 403
