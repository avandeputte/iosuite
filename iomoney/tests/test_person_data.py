"""Deleting someone in Settings › Security removes their private accounts here, with everything in them; the
household's accounts they added stay."""
from iosuite_shared import users

from app import db
from conftest import sign_in
from test_api import add


def test_deleting_someone_removes_their_accounts_and_keeps_the_households(client, as_user):
    as_user("ann", "editor")
    ann = users.find("ann")["id"]
    mine = add(client, name="Ann's savings", household=False)
    hh = add(client, name="Joint", household=True)
    client.post(f"/api/accounts/{mine['id']}/transactions", json={"amount": -5, "merchant": "Snack"})
    sign_in(client, "alex")
    got = client.get(f"/api/suite-admin/person-data/{ann}").json()["items"]
    assert {i["what"]: (i["count"], i["kept"]) for i in got} == {
        "private account": (1, False), "transaction in them": (1, False),
        "household account they added": (1, True)}
    assert client.delete(f"/api/suite-admin/users/{ann}").status_code == 200
    assert not db.q("SELECT id FROM mny_accounts WHERE id = %s", (mine["id"],))
    assert not db.q("SELECT id FROM mny_transactions WHERE account_id = %s", (mine["id"],))
    assert db.q("SELECT id FROM mny_accounts WHERE id = %s", (hh["id"],))
