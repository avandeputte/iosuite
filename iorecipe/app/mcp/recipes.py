"""The recipe tools, with the same permissions as the web app: a viewer only reads, a member keeps private recipes of
their own, editors and admins change the family's too."""
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, api, config, model
from app.mcp.base import ADDS, DELETES, READ_ONLY, WRITES, clamp, find_book, find_recipe, recipe_out, server, summary, who

RECIPE_FIELDS = """
    ingredients, steps: lists of lines, one ingredient or one step each; a line that ends with a colon is a heading.
    servings: free text such as '4' or '24 cookies'.
    prep_minutes, cook_minutes, total_minutes: whole minutes.
    tags: short words such as ['dessert', 'cookies'].
    source_url, source_name: where the recipe comes from.
"""


def fields(fn):
    fn.__doc__ = (fn.__doc__ or "") + RECIPE_FIELDS
    return fn


def _guard(fn, *a, **kw):
    """The model's refusals as tool errors the assistant can read."""
    try:
        return fn(*a, **kw)
    except (model.Forbidden, model.NotFound, ValueError) as e:
        raise ToolError(str(e))


def _data(**kw) -> dict:
    names = {"title": "title", "description": "description", "servings": "servings", "prep_minutes": "prepMinutes",
             "cook_minutes": "cookMinutes", "total_minutes": "totalMinutes", "ingredients": "ingredients", "steps": "steps",
             "notes": "notes", "tags": "tags", "source_url": "sourceUrl", "source_name": "sourceName"}
    return {names[k]: v for k, v in kw.items() if v is not None}


@server.tool(annotations=READ_ONLY)
def overview() -> dict:
    """Who you are signed in as, how many recipes you see (the family's, your own, your favourites), whether you may
    add family or private recipes, the tags in use and the cookbooks. Start here."""
    u = who()
    return {"you": {"name": u["name"], "displayName": u.get("displayName"), "role": u.get("role")},
            "recipes": model.counts(u), "youCanAdd": {"family": model.may_add(u, True), "private": model.may_add(u, False)},
            "tags": model.tags(u)[:60], "cookbooks": [model.book_public(b, u) for b in model.books(u)],
            "version": __version__, "webApp": config.PUBLIC_URL or None}


@server.tool(annotations=READ_ONLY)
def list_recipes(tag: Optional[str] = None, scope: Optional[Literal["family", "mine", "favourites"]] = None, cookbook: Optional[str] = None,
                 sort: Optional[Literal["title", "new", "rating"]] = None, limit: int = 100) -> list:
    """The recipes: id, title, servings, times, tags, your favourite and rating, the average rating. tag: only those
    with this tag; scope: only the family's, only your own private ones, or only your favourites; cookbook: only those
    in this cookbook (its id or name); sort: by title (as left out), the newest first, or the best rated first."""
    u = who()
    book = find_book(u, cookbook)["id"] if cookbook else None
    return [summary(u, r) for r in _guard(model.find, u, "", tag, scope, limit=clamp(limit, 1, 500), book=book, sort=sort)]


@server.tool(annotations=READ_ONLY)
def search_recipes(query: str, limit: int = 30) -> list:
    """Recipes with every word of the query somewhere in the title, the ingredients, the steps, the notes or the tags
    ('chocolate oat', 'chicken lemon')."""
    u = who()
    return [summary(u, r) for r in model.find(u, query, limit=clamp(limit, 1, 200))]


@server.tool(annotations=READ_ONLY)
def get_recipe(recipe: str) -> dict:
    """Everything about one recipe (its id, or its title when that names one): ingredients, steps, notes, times, tags,
    where it comes from, your favourite and rating, the cookbooks it is in."""
    u = who()
    return recipe_out(u, find_recipe(u, recipe))


@server.tool(annotations=ADDS)
@fields
def create_recipe(title: str, ingredients: list[str], steps: list[str], description: Optional[str] = None,
                  servings: Optional[str] = None, prep_minutes: Optional[int] = None, cook_minutes: Optional[int] = None,
                  total_minutes: Optional[int] = None, notes: Optional[str] = None, tags: Optional[list[str]] = None,
                  source_url: Optional[str] = None, source_name: Optional[str] = None, family: Optional[bool] = None) -> dict:
    """Add a recipe. family: true for a family recipe (editors and admins), false for a private one of yours; left
    out, it is the family's when you may add there."""
    u = who()
    fam = model.may_add(u, True) if family is None else family
    d = _data(title=title, description=description, servings=servings, prep_minutes=prep_minutes, cook_minutes=cook_minutes,
              total_minutes=total_minutes, ingredients=ingredients, steps=steps, notes=notes, tags=tags, source_url=source_url,
              source_name=source_name)
    return recipe_out(u, _guard(model.create, u, d, fam))


@server.tool(annotations=WRITES)
@fields
def update_recipe(recipe: str, title: Optional[str] = None, ingredients: Optional[list[str]] = None, steps: Optional[list[str]] = None,
                  description: Optional[str] = None, servings: Optional[str] = None, prep_minutes: Optional[int] = None,
                  cook_minutes: Optional[int] = None, total_minutes: Optional[int] = None, notes: Optional[str] = None,
                  tags: Optional[list[str]] = None, source_url: Optional[str] = None, source_name: Optional[str] = None,
                  family: Optional[bool] = None) -> dict:
    """Change a recipe (its id or title): only what is given changes; a list given replaces the whole list. family:
    move it to the family's recipes or to your private ones (editors and admins)."""
    u = who()
    r = find_recipe(u, recipe)
    d = _data(title=title, description=description, servings=servings, prep_minutes=prep_minutes, cook_minutes=cook_minutes,
              total_minutes=total_minutes, ingredients=ingredients, steps=steps, notes=notes, tags=tags, source_url=source_url,
              source_name=source_name)
    if family is not None:
        d["family"] = family
    return recipe_out(u, _guard(model.update, u, r, d))


@server.tool(annotations=DELETES)
def delete_recipe(recipe: str) -> dict:
    """Delete a recipe (its id or title) with its picture. It cannot be brought back: ask first."""
    u = who()
    r = find_recipe(u, recipe)
    _guard(model.delete, u, r)
    return {"deleted": r["title"]}


@server.tool(annotations=ADDS)
def import_recipe(url: str, family: Optional[bool] = None) -> dict:
    """Keep the recipe on a web page: the server fetches the page, reads the recipe on it (its schema.org
    Recipe data, which most recipe sites publish; otherwise the page's own lists and text, or the AI model
    on the server) and saves it with its picture. family as in create_recipe. An error when the page cannot be fetched or no
    recipe is found on it."""
    u = who()
    fam = model.may_add(u, True) if family is None else family
    return recipe_out(u, _guard(api.import_from, u, url, fam))


@server.tool(annotations=WRITES)
def mark_recipe(recipe: str, favourite: Optional[bool] = None, rating: Optional[int] = None) -> dict:
    """What the account you act as thinks of a recipe (its id or title): favourite true or false, rating 1 to 5 (0
    takes the rating away). Only what is given changes. The others see only the average of the ratings."""
    u = who()
    d = {}
    if favourite is not None:
        d["favourite"] = favourite
    if rating is not None:
        d["rating"] = rating
    return recipe_out(u, _guard(model.mark, u, find_recipe(u, recipe), d))


@server.tool(annotations=READ_ONLY)
def list_cookbooks() -> list:
    """The cookbooks: id, name, whether it is the family's (everyone sees it; it holds family recipes) or yours,
    whether you may change it, how many recipes it holds. list_recipes(cookbook=...) lists what is in one."""
    u = who()
    return [model.book_public(b, u) for b in model.books(u)]


@server.tool(annotations=ADDS)
def create_cookbook(name: str, description: Optional[str] = None, family: Optional[bool] = None) -> dict:
    """A new cookbook. family: true for a family cookbook (editors and admins), false for one of yours; left out, it
    is the family's when you may add there."""
    u = who()
    fam = model.may_add(u, True) if family is None else family
    return model.book_public({**_guard(model.create_book, u, {"name": name, "description": description}, fam), "n": 0}, u)


@server.tool(annotations=WRITES)
def add_to_cookbook(cookbook: str, recipes: list[str]) -> dict:
    """Put recipes (ids or titles) in a cookbook (its id or name). A family cookbook takes family recipes only."""
    u = who()
    b = find_book(u, cookbook)
    rows = [find_recipe(u, r) for r in recipes]
    for r in rows:
        _guard(model.book_add, u, b, r)
    return {"cookbook": b["name"], "added": [r["title"] for r in rows]}


@server.tool(annotations=WRITES)
def remove_from_cookbook(cookbook: str, recipes: list[str]) -> dict:
    """Take recipes (ids or titles) out of a cookbook (its id or name). The recipes themselves stay."""
    u = who()
    b = find_book(u, cookbook)
    rows = [find_recipe(u, r) for r in recipes]
    for r in rows:
        _guard(model.book_remove, u, b, r)
    return {"cookbook": b["name"], "removed": [r["title"] for r in rows]}


@server.tool(annotations=DELETES)
def delete_cookbook(cookbook: str) -> dict:
    """Delete a cookbook (its id or name). Its recipes stay. Ask first."""
    u = who()
    b = find_book(u, cookbook)
    _guard(model.delete_book, u, b)
    return {"deleted": b["name"]}
