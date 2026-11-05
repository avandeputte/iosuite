"""The MCP server instance and what every tool module shares: the admin-token gate, name resolution, limits."""
import contextvars

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from app import config, db, notes
from app.auth import updater

APP = config.APP_URL  # for the links in results
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# a tool that changes notes but can be repeated with the same outcome (an edit, a colour, a move)
WRITES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False)
CREATES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

server = MCPServer(
    "ionotes",
    instructions=(
        "A personal notes library (text, clipboard snippets, screenshots with the text read from them). Start with "
        "notes_overview, use list_folders / list_tags to find exact names, then search_notes and get_note. "
        "view_note_image shows a note's picture. Notes are private to each account: these tools work on the notes of "
        "one account (notes_overview names it; an admin chooses it in Maintenance › MCP server). Changing anything needs the admin token "
        "(the web app's Maintenance › MCP server shows it to an admin)."
    ),
)

token_given = contextvars.ContextVar("mcp_token_given", default=False)  # set per request by the HTTP layer
MCP_USER = "MCP"


def clamp_limit(limit, cap: int) -> int:
    return max(1, min(int(limit), cap))


def need_token(token: str, writes: bool = False):
    """Changes and diagnostics take the admin token; writes are refused in read-only mode as in the web app."""
    if not updater.token_ok(token):
        raise ToolError("This tool needs the admin token (the web app's Maintenance › MCP server shows it to an admin)")
    if writes and db.read_only():
        raise ToolError("ionotes is in read-only mode; nothing can be changed")


def resolve_folder(name) -> str:
    """A folder id from an id, an exact name (any case), or a unique partial match; "" or "none": no folder."""
    if name in (None, ""):
        return None
    s = str(name).strip()
    folders = notes.list_folders()
    for f in folders:
        if f["id"] == s or f["id"] == s.upper():
            return f["id"]
    exact = [f for f in folders if f["name"].lower() == s.lower()]
    if len(exact) == 1:
        return exact[0]["id"]
    part = [f for f in folders if s.lower() in f["name"].lower()]
    if len(part) == 1:
        return part[0]["id"]
    if not part:
        raise ToolError(f"No folder matches '{s}'. Use list_folders to find it.")
    raise ToolError(f"'{s}' is ambiguous; did you mean one of: " + "; ".join(f"{f['name']} (id {f['id']})" for f in part[:8]))


def note_or_fail(uid: str) -> dict:
    try:
        n = notes.get_note(uid)
    except ValueError as e:
        raise ToolError(str(e))
    if not n:
        raise ToolError(f"No note with id {uid}")
    return n


def summary(n: dict, folders: dict = None, text_chars: int = 300) -> dict:
    """A note as a search result: the title the apps show, a preview of its text, where it is."""
    text = n["body"] or n["ocrText"]
    out = {"id": n["id"], "title": notes.display_title(n), "preview": text[:text_chars] + ("…" if len(text) > text_chars else ""),
           "tags": n["tags"], "folder": (folders or {}).get(n["folderID"]), "pinned": n["pinned"] or None,
           "has_image": n["hasImage"] or None, "source": n["source"], "source_app": n["sourceApp"],
           "created": iso(n["createdAt"]), "updated": iso(n["updatedAt"]), "url": f"{APP}/#/note/{n['id']}"}
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def iso(ts) -> str:
    import time
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(float(ts))) if ts else None


def parse_date(s: str, end: bool = False) -> float:
    """YYYY-MM-DD (UTC day) to seconds; end: the end of that day."""
    import calendar
    import time
    try:
        t = time.strptime(str(s), "%Y-%m-%d")
    except ValueError:
        raise ToolError(f"Dates are YYYY-MM-DD, got '{s}'")
    return calendar.timegm(t) + (86400 if end else 0)
