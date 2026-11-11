"""The recipe tools, with the same permissions as the web app: a viewer only reads, a member keeps private recipes of
their own, editors and admins change the family's too."""
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, api, config, model
from app.mcp.base import ADDS, DELETES, READ_ONLY, WRITES, clamp, find_recipe, recipe_out, server, summary, who

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
    """Who you are signed in as, how many recipes you see (the family's and your own), whether you may add family or
    private recipes, and the tags in use. Start here."""
    u = who()
    return {"you": {"name": u["name"], "displayName": u.get("displayName"), "role": u.get("role")},
            "recipes": model.counts(u), "youCanAdd": {"family": model.may_add(u, True), "private": model.may_add(u, False)},
            "tags": model.tags(u)[:60], "version": __version__, "webApp": config.PUBLIC_URL or None}


@server.tool(annotations=READ_ONLY)
def list_recipes(tag: Optional[str] = None, scope: Optional[Literal["family", "mine"]] = None, limit: int = 100) -> list:
    """The recipes, by title: id, title, servings, times, tags. tag: only those with this tag; scope: only the
    family's, or only your own private ones."""
    u = who()
    return [summary(u, r) for r in model.find(u, "", tag, scope, limit=clamp(limit, 1, 500))]


@server.tool(annotations=READ_ONLY)
def search_recipes(query: str, limit: int = 30) -> list:
    """Recipes with every word of the query somewhere in the title, the ingredients, the steps, the notes or the tags
    ('chocolate oat', 'chicken lemon')."""
    u = who()
    return [summary(u, r) for r in model.find(u, query, limit=clamp(limit, 1, 200))]


@server.tool(annotations=READ_ONLY)
def get_recipe(recipe: str) -> dict:
    """Everything about one recipe (its id, or its title when that names one): ingredients, steps, notes, times, tags,
    where it comes from."""
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
    """Keep the recipe on a web page: the server fetches the page, reads the recipe it describes (schema.org Recipe
    data, which most recipe sites publish) and saves it with its picture. family as in create_recipe. An error when
    the page cannot be fetched or describes no recipe."""
    u = who()
    fam = model.may_add(u, True) if family is None else family
    return recipe_out(u, _guard(api.import_from, u, url, fam))
