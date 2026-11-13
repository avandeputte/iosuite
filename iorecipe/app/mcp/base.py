"""The MCP server instance (iosuite_shared.mcp: who is asking, the annotations, the limits) and what every tool module
shares: finding a recipe."""
from mcp.server.mcpserver.exceptions import ToolError

from iosuite_shared import mcp as shared_mcp
from iosuite_shared.mcp import ADDS, DELETES, READ_ONLY, UPDATES, WRITES, clamp, current_user, need_admin, who

from app import __version__, config, model

# what the tool modules take from here: the suite's pieces (iosuite_shared.mcp) and ioRecipe's own helpers
__all__ = ["server", "ADDS", "DELETES", "READ_ONLY", "UPDATES", "WRITES", "clamp", "current_user", "need_admin", "who",
           "find_book", "find_recipe", "recipe_out", "summary"]

server = shared_mcp.make_server(
    config.APP, "ioRecipe", __version__,
    instructions=(
        "The family's recipes (ioRecipe). Start with overview: it says who you are, how many recipes there are and "
        "the tags in use. list_recipes lists them (by tag, the family's or your own); search_recipes finds them by "
        "words in the title, the ingredients, the steps or the tags; get_recipe has everything about one. A recipe "
        "is either a family recipe (everyone sees it, editors change it) or a private one of the account you act as. "
        "Ingredients and steps are lists of lines; a line that ends with a colon is a heading ('For the icing:'). "
        "Times are minutes. import_recipe takes the address of a recipe on the web and keeps it with its picture; a "
        "recipe you read yourself (from text, a photo, a file somebody shows you) goes in with create_recipe. "
        "mark_recipe sets the favourite and the rating (1 to 5) of the account you act as. Cookbooks group recipes: "
        "list_cookbooks, create_cookbook, add_to_cookbook, remove_from_cookbook. "
        "Ask before deleting a recipe or a cookbook."
    ),
)


def _link(rid: int) -> str | None:
    return f"{config.PUBLIC_URL}/#/recipe/{rid}" if config.PUBLIC_URL else None


def find_recipe(u: dict, ref) -> dict:
    """A recipe by id, or by a title that matches exactly one."""
    s = str(ref).strip()
    if not s:
        raise ToolError("Name a recipe (its id or its title)")
    if s.isdigit():
        try:
            return model.readable(u, int(s))
        except model.NotFound:
            raise ToolError(f"No recipe with id {s}")
    found = model.find(u, s, full=True)
    rows = [r for r in found if r["title"].lower() == s.lower()] or [r for r in found if s.lower() in r["title"].lower()] or found
    if not rows:
        raise ToolError(f"No recipe matches '{s}'. Try search_recipes or list_recipes.")
    if len(rows) > 1:
        raise ToolError(f"'{s}' matches several recipes; give the id: " + "; ".join(f"{r['title']} (id {r['id']})" for r in rows[:10]))
    return rows[0]


def find_book(u: dict, ref) -> dict:
    """A cookbook by id, or by its name."""
    s = str(ref).strip()
    rows = model.books(u)
    found = [b for b in rows if str(b["id"]) == s] or [b for b in rows if b["name"].lower() == s.lower()] or \
        [b for b in rows if s and s.lower() in b["name"].lower()]
    if len(found) != 1:
        raise ToolError((f"No cookbook matches '{s}'. " if not found else f"'{s}' matches several cookbooks. ")
                        + "The cookbooks: " + ("; ".join(f"{b['name']} (id {b['id']})" for b in rows[:30]) or "none yet"))
    return found[0]


def _tidy(j: dict, rid: int) -> dict:
    j.pop("photo", None)
    j.pop("updated", None)
    j.pop("created", None)
    link = _link(rid)
    if link:
        j["webUrl"] = link
    return {k: v for k, v in j.items() if v not in (None, "", [], {}, 0, False) or k in ("family",)}


def recipe_out(u: dict, r: dict) -> dict:
    j = model.public(r, u)
    j["photos"] = len(j.pop("photos"))
    names = {b["id"]: b["name"] for b in model.books(u)}
    j["cookbooks"] = [names[i] for i in j.pop("books") if i in names]
    j["youCanChange"] = j.pop("writable")
    return _tidy(j, r["id"])


def summary(u: dict, r: dict) -> dict:
    j = model.public(r, u, full=False)
    j.pop("writable", None)
    return _tidy(j, r["id"])
