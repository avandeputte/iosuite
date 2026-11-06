"""Whose notes: the first admin gets the notes made before accounts existed."""
from app import users


def first_admin_id():
    """The account that gets the notes made before accounts existed, the first admin of ioNotes (lowest id)."""
    ids = [u["id"] for u in users.list_users() if u.get("role") == "admin" or u.get("suiteAdmin")]
    return min(ids) if ids else None
