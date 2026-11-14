"""What a person keeps in ioContact, counted or removed when their account is deleted (iosuite_shared.persondata):
their private address books with every contact in them, and their birthdays feed link (users.forget_gone, which the
start also runs for accounts deleted while ioContact was away). Contacts in a shared address book stay, their own
card among them: the family still needs them."""
from iosuite_shared import related

from app import db, users


def of(user_id: int, remove: bool) -> list:
    books = db.one("SELECT count(*) AS n FROM con_address_books WHERE owner_id = %s", (user_id,))["n"]
    contacts = db.one("SELECT count(*) AS n FROM con_contacts c JOIN con_address_books b ON b.id = c.address_book_id "
                      "WHERE b.owner_id = %s AND c.deleted = 0", (user_id,))["n"]
    feeds = db.one("SELECT count(*) AS n FROM con_feed_tokens WHERE user_id = %s", (user_id,))["n"]
    if remove:
        gone = [r["id"] for r in db.q("SELECT c.id FROM con_contacts c JOIN con_address_books b ON b.id = c.address_book_id WHERE b.owner_id = %s", (user_id,))]
        users.forget_gone(user_id)
        related.forget_many("contact", gone)  # their links to other items of the suite go too
    return [{"what": "private address books", "one": "private address book", "count": books},
            {"what": "contacts in them", "one": "contact in it", "count": contacts},
            {"what": "birthdays feed link", "count": feeds}]
