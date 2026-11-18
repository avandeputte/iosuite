"""The MCP server instance (iosuite_shared.mcp: who is asking, the annotations, the limits) and what every tool module
shares: finding a document and giving it out."""
from mcp.server.mcpserver.exceptions import ToolError

from iosuite_shared import mcp as shared_mcp
from iosuite_shared.mcp import ADDS, DELETES, READ_ONLY, UPDATES, WRITES, clamp, current_user, need_admin, who

from app import __version__, config, model

__all__ = ["server", "ADDS", "DELETES", "READ_ONLY", "UPDATES", "WRITES", "clamp", "current_user", "need_admin", "who",
           "find_doc", "doc_out", "summary", "guard"]

server = shared_mcp.make_server(
    config.APP, "ioDocs", __version__,
    instructions=(
        "The family's important papers (ioDocs): passports, ID cards, driver's licenses, visas, insurance policies, "
        "vehicle registrations, birth and marriage certificates. Each has a kind, the family members it belongs to, "
        "its number, who issued it, when it was issued and when it expires, its own details, and its scans. Start "
        "with overview: who you are, how many documents you see and which expire soon. expiring lists what runs out "
        "within a number of days (or has run out); search_documents finds them by words (the text read off the "
        "scans too); get_document has everything about one. You only ever see the documents your account may see. "
        "Dates are YYYY-MM-DD. A document's number is sensitive: give it only when asked. Ask before deleting; "
        "archiving keeps an old one (archived=true), and renew_document puts the new one in its place."
    ),
)


def guard(fn, *a, **kw):
    """The model's refusals as tool errors the assistant can read."""
    from iosuite_shared.errors import Invalid
    try:
        return fn(*a, **kw)
    except (model.Forbidden, model.NotFound, Invalid, ValueError) as e:
        raise ToolError(str(e))


def _link(did: int) -> str | None:
    return f"{config.PUBLIC_URL}/#/doc/{did}" if config.PUBLIC_URL else None


def find_doc(u: dict, ref) -> dict:
    """A document this account sees, by id or by a title that matches exactly one."""
    s = str(ref).strip()
    if not s:
        raise ToolError("Name a document (its id or its title)")
    if s.isdigit():
        d = model.get(int(s))
        if not d or not model.can_see(u, d):
            raise ToolError(f"No document with id {s}")
        return d
    found = model.find(u, s, status="all", limit=50)
    rows = [r for r in found if r["title"].lower() == s.lower()] or [r for r in found if s.lower() in r["title"].lower()] or found
    if not rows:
        raise ToolError(f"No document matches '{s}'. Try search_documents.")
    if len(rows) > 1:
        raise ToolError(f"'{s}' matches several documents; give the id: " + "; ".join(f"{r['title']} (id {r['id']})" for r in rows[:10]))
    return rows[0]


def _tidy(j: dict, did: int) -> dict:
    for k in ("cover", "updated", "created", "mine", "remindDefault"):
        j.pop(k, None)
    link = _link(did)
    if link:
        j["webUrl"] = link
    return {k: v for k, v in j.items() if v not in (None, "", [], {}, False) or k in ("archived",)}


def doc_out(u: dict, d: dict) -> dict:
    j = model.public(d, u)
    j["people"] = [x["displayName"] for x in j["people"]]
    j["files"] = [{"id": f["id"], "name": f["name"], "size": f["size"], "read": bool(f["read"])} for f in j["files"]]
    j["youCanChange"] = j.pop("writable")
    return _tidy(j, d["id"])


def summary(u: dict, row: dict) -> dict:
    j = model.public(row, u, full=False)
    j["people"] = [x["displayName"] for x in j["people"]]
    j.pop("writable", None)
    j.pop("fields", None)
    return _tidy(j, row["id"])
