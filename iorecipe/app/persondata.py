"""What a person keeps in ioRecipe, counted or removed when their account is deleted (iosuite_shared.persondata):
their private recipes (with their photos), their private cookbooks, and their favourites and ratings. Family recipes
and cookbooks stay, whoever added them: they are everyone's."""
from iosuite_shared import related

from app import db


def of(user_id: int, remove: bool) -> list:
    recipes = db.one("SELECT count(*) AS n FROM rcp_recipes WHERE owner_id = %s", (user_id,))["n"]
    books = db.one("SELECT count(*) AS n FROM rcp_books WHERE owner_id = %s", (user_id,))["n"]
    marks = db.one("SELECT count(*) AS n FROM rcp_marks WHERE user_id = %s", (user_id,))["n"]
    family = db.one("SELECT count(*) AS n FROM rcp_recipes WHERE owner_id IS NULL AND created_by = %s", (user_id,))["n"]
    if remove:
        gone = [r["id"] for r in db.q("SELECT id FROM rcp_recipes WHERE owner_id = %s", (user_id,))]
        with db.tx():
            db.ex("DELETE FROM rcp_recipes WHERE owner_id = %s", (user_id,))  # photos, marks and book places go with them
            db.ex("DELETE FROM rcp_books WHERE owner_id = %s", (user_id,))
            db.ex("DELETE FROM rcp_marks WHERE user_id = %s", (user_id,))
        related.forget_many("recipe", gone)  # their links to other items of the suite go too
    return [{"what": "private recipes", "one": "private recipe", "count": recipes},
            {"what": "private cookbooks", "one": "private cookbook", "count": books},
            {"what": "favourites and ratings", "one": "favourite or rating", "count": marks},
            {"what": "family recipes they added", "one": "family recipe they added", "count": family, "kept": True}]
