"""ioRecipe's answers to the suite's standard endpoints (iosuite_shared.suiteitems): recipes found, one recipe, its
picture."""
import re

from iosuite_shared.suiteitems import Provider, item


def _recipe(r: dict) -> dict:
    m = re.search(r"/photos/(\d+)$", str(r.get("photo") or ""))
    mins = r.get("totalMinutes")
    text = f"{mins} min" if mins else ", ".join((r.get("tags") or [])[:3])
    return item("iorecipe", "recipe", r.get("id"), r.get("title"), text, image=m.group(1) if m else None, icon="recipe",
                minutes=mins, favourite=bool(r.get("favourite")) or None)


def search(local, q, n, tz, kinds):
    """The recipes with every word of q in their title, ingredients, steps or tags, by title."""
    if kinds and "recipe" not in kinds:
        return []
    rows = local.get("/api/recipes", {"q": q, "limit": n + 1}).get("items", [])
    return {"items": [_recipe(r) for r in rows[:n]], "more": len(rows) > n}


def get(local, kind, item_id):
    if kind != "recipe" or not item_id.isdigit():
        return None
    return _recipe(local.get(f"/api/recipes/{item_id}"))


def image(local, kind, item_id, p):
    if kind != "recipe" or not item_id.isdigit() or not p.isdigit():
        return None
    return local.raw(f"/api/recipes/{item_id}/photos/{p}", {"size": "small"})


PROVIDER = Provider(search=search, get=get, image=image)
