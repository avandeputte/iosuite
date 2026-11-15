"""The MCP server instance (iosuite_shared.mcp: who is asking, the annotations, the limits) and what every tool module
shares: finding a thing, a place or a label."""
from mcp.server.mcpserver.exceptions import ToolError

from iosuite_shared import mcp as shared_mcp
from iosuite_shared.mcp import ADDS, DELETES, READ_ONLY, UPDATES, WRITES, clamp, current_user, need_admin, who

from app import __version__, config, model

__all__ = ["server", "ADDS", "DELETES", "READ_ONLY", "UPDATES", "WRITES", "clamp", "current_user", "need_admin", "who",
           "find_item", "find_location", "item_out", "summary", "guard"]

server = shared_mcp.make_server(
    config.APP, "ioThings", __version__,
    instructions=(
        "The things in the family's house (ioThings): appliances, tools, furniture, electronics, the car. Start with "
        "overview: who you are, how many things there are, the places and labels, and what needs doing soon. "
        "search_items finds things by words (name, maker, model and serial numbers, notes, place, labels); get_item "
        "has everything about one: where it is, purchase and warranty details, its files (manual, receipt), its upkeep "
        "and its maintenance log. Places are a tree, written as a path ('House / Kitchen'). Upkeep is what a thing "
        "needs every so often (the boiler's service every year); list_upkeep says what is due; upkeep_done records "
        "that it was done and moves it on. log_maintenance writes a one-off line (a repair). Warranties: "
        "warranties_ending. Dates are YYYY-MM-DD; prices are in the currency (overview says which). Ask "
        "before deleting a thing; archiving keeps its story (archived=true)."
    ),
)


def guard(fn, *a, **kw):
    """The model's refusals as tool errors the assistant can read."""
    from iosuite_shared.errors import Invalid
    try:
        return fn(*a, **kw)
    except (model.Forbidden, model.NotFound, Invalid, ValueError) as e:
        raise ToolError(str(e))


def _link(iid: int) -> str | None:
    return f"{config.PUBLIC_URL}/#/item/{iid}" if config.PUBLIC_URL else None


def find_item(u: dict, ref) -> dict:
    """A thing by id, or by a name that matches exactly one."""
    s = str(ref).strip()
    if not s:
        raise ToolError("Name a thing (its id or its name)")
    if s.isdigit():
        it = model.get(int(s))
        if not it:
            raise ToolError(f"No thing with id {s}")
        return it
    found = model.find(s, archived="also", limit=50)
    rows = [r for r in found if r["name"].lower() == s.lower()] or [r for r in found if s.lower() in r["name"].lower()] or found
    if not rows:
        raise ToolError(f"No thing matches '{s}'. Try search_items.")
    if len(rows) > 1:
        raise ToolError(f"'{s}' matches several things; give the id: " + "; ".join(f"{r['name']} (id {r['id']})" for r in rows[:10]))
    return rows[0]


def find_location(ref) -> dict:
    """A place by id, by its name or by its path."""
    s = str(ref).strip()
    rows = model.locations()
    found = [x for x in rows if str(x["id"]) == s] or [x for x in rows if x["path"].lower() == s.lower()] or \
        [x for x in rows if x["name"].lower() == s.lower()]
    if len(found) != 1:
        raise ToolError((f"No place matches '{s}'. " if not found else f"'{s}' matches several places. ")
                        + "The places: " + ("; ".join(f"{x['path']} (id {x['id']})" for x in rows[:40]) or "none yet"))
    return found[0]


def _tidy(j: dict, iid: int) -> dict:
    for k in ("photo", "updated", "created"):
        j.pop(k, None)
    link = _link(iid)
    if link:
        j["webUrl"] = link
    return {k: v for k, v in j.items() if v not in (None, "", [], {}, False) or k in ("archived",)}


def item_out(u: dict, it: dict) -> dict:
    j = model.public(it, u)
    j["location"] = j["location"]["path"] if j["location"] else None
    j["labels"] = [x["name"] for x in j["labels"]]
    j["files"] = [{"kind": f["kind"], "name": f["name"], "size": f["size"]} for f in j["files"]]
    j["youCanChange"] = j.pop("writable")
    j.pop("canLog", None)
    return _tidy(j, it["id"])


def summary(u: dict, row: dict) -> dict:
    j = model.public(row, u, full=False)
    j["location"] = j["location"]["path"] if j["location"] else None
    j["labels"] = [x["name"] for x in j["labels"]]
    j.pop("writable", None)
    return _tidy(j, row["id"])
