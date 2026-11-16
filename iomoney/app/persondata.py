"""What a person keeps in ioMoney, counted or removed when their account is deleted (iosuite_shared.persondata):
their private accounts, with everything in them (balances, transactions with their receipts, holdings). The household's accounts stay,
whoever added them or changed their transactions: they are everyone's."""
from iosuite_shared import related

from app import db, receipts


def of(user_id: int, remove: bool) -> list:
    accts = [r["id"] for r in db.q("SELECT id FROM mny_accounts WHERE owner_id = %s", (user_id,))]
    marks = db.marks(len(accts))
    tx = db.one(f"SELECT count(*) AS n FROM mny_transactions WHERE account_id IN ({marks})", accts)["n"] if accts else 0
    hold = db.one(f"SELECT count(*) AS n FROM mny_holdings WHERE account_id IN ({marks})", accts)["n"] if accts else 0
    added = db.one("SELECT count(*) AS n FROM mny_accounts WHERE owner_id IS NULL AND created_by = %s", (user_id,))["n"]
    if remove and accts:
        tids = [r["id"] for r in db.q(f"SELECT id FROM mny_transactions WHERE account_id IN ({marks})", accts)]
        with db.tx():
            db.ex(f"UPDATE mny_accounts SET loan_id = NULL WHERE loan_id IN ({marks})", accts)
            db.ex("DELETE FROM mny_accounts WHERE owner_id = %s", (user_id,))  # balances, transactions, holdings go with them
        related.forget_many("asset", accts)  # their links to other items of the suite go too
        receipts.forget(tids)                # and those of their transactions (the receipts go with the transactions)
    return [{"what": "private accounts", "one": "private account", "count": len(accts)},
            {"what": "transactions in them", "one": "transaction in them", "count": tx},
            {"what": "holdings in them", "one": "holding in them", "count": hold},
            {"what": "household accounts they added", "one": "household account they added", "count": added, "kept": True}]
