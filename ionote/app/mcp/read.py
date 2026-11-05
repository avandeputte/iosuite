"""The read-only tools: the overview, search with the web app's filters, one note in full, folders and tags,
what changed recently, and looking at a note's picture."""
import io
from typing import Literal, Optional

from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError

from app import images, notes
from app.mcp.base import APP, READ_ONLY, clamp_limit, iso, note_or_fail, parse_date, resolve_folder, server, summary

LARGE_EDGE = 1568


@server.tool(annotations=READ_ONLY)
def notes_overview() -> dict:
    """Totals (notes, pinned, with pictures, in the trash), every folder and tag with its count, where notes came
    from, the newest and oldest note, and the web app's address."""
    m = notes.meta()
    with notes.db.connect() as con:
        o = (notes.owner(),)
        sources = {r[0]: r[1] for r in con.execute("SELECT source, count(*) FROM nts_notes WHERE user_id = ? AND deleted = 0 GROUP BY source ORDER BY 2 DESC", o)}
        apps = {r[0]: r[1] for r in con.execute("SELECT source_app, count(*) FROM nts_notes WHERE user_id = ? AND deleted = 0 AND source_app IS NOT NULL "
                                                 "GROUP BY source_app ORDER BY 2 DESC LIMIT 15", o)}
        first, last = con.execute("SELECT min(created_at), max(created_at) FROM nts_notes WHERE user_id = ? AND deleted = 0", o).fetchone()
    return {"notes": m["total"], "pinned": m["pinned"], "with_picture": m["images"], "in_no_folder": m["noFolder"], "in_trash": m["trash"],
            "folders": {f["name"]: f["count"] for f in m["folders"]}, "tags": {t["name"]: t["count"] for t in m["tags"]},
            "sources": sources, "source_apps": apps, "oldest": iso(first), "newest": iso(last), "web_app": APP,
            "account": _account()}


def _account():
    """Whose notes these are (Settings › MCP server › Notes of)."""
    from app import users
    u = users.get(notes.owner()) if notes.owner() > 0 else None
    return u["name"] if u else None


@server.tool(annotations=READ_ONLY)
def search_notes(text: str = "", folder: Optional[str] = None, tag: Optional[str] = None, pinned: Optional[bool] = None,
                 has_picture: Optional[bool] = None, source: Optional[str] = None, created_from: Optional[str] = None,
                 created_to: Optional[str] = None, sort: Literal["updated", "created", "oldest", "title"] = "updated",
                 limit: int = 25, offset: int = 0) -> dict:
    """Find notes. All filters are optional and combine:
      text: every word must appear (prefix match) in the title, the text, the text read from the picture, or a tag
      folder: a folder name or id ("none" for notes in no folder); tag: a tag name
      pinned, has_picture: true/false; source: clipboard, screenshot, service, manual, web, photo, share, mcp
      created_from / created_to: YYYY-MM-DD (inclusive)
    Pinned notes come first, then by sort. Results carry a preview; get_note returns the full text."""
    fid = "none" if folder == "none" else resolve_folder(folder)
    limit = clamp_limit(limit, 100)
    lo = parse_date(created_from) if created_from else None
    hi = parse_date(created_to, end=True) if created_to else None
    folders = {f["id"]: f["name"] for f in notes.list_folders()}
    res = notes.list_notes(text, fid, tag, pinned, has_picture, sort, limit, offset, source, created_from=lo, created_before=hi)
    found, total = res["notes"], res["total"]
    return {"total": total, "offset": offset, "returned": len(found), "notes": [summary(n, folders) for n in found]}


@server.tool(annotations=READ_ONLY)
def get_note(note_id: str) -> dict:
    """Everything about one note: title, full text, the text read from its picture, tags, folder, pin, where it came
    from, dates, its picture's size, and its link in the web app."""
    n = note_or_fail(note_id)
    folders = {f["id"]: f["name"] for f in notes.list_folders(include_deleted=True)}
    out = {"id": n["id"], "title": n["title"], "display_title": notes.display_title(n), "text": n["body"], "text_in_picture": n["ocrText"],
           "tags": n["tags"], "folder": folders.get(n["folderID"]), "folder_id": n["folderID"], "pinned": n["pinned"], "source": n["source"],
           "source_app": n["sourceApp"], "created": iso(n["createdAt"]), "updated": iso(n["updatedAt"]), "last_changed_by": n["changedBy"],
           "in_trash": n["deleted"], "url": f"{APP}/#/note/{n['id']}"}
    if n["hasImage"]:
        out["picture"] = images.info(n["id"])
    return {k: v for k, v in out.items() if v not in (None, "", [])}


@server.tool(annotations=READ_ONLY)
def list_folders() -> list:
    """Every folder with its note count and colour."""
    return [{"id": f["id"], "name": f["name"], "notes": f["count"], "color": f["color"]} for f in notes.list_folders()]


@server.tool(annotations=READ_ONLY)
def list_tags() -> list:
    """Every tag used on a note, with its count and colour."""
    return [{k: v for k, v in t.items() if v is not None} for t in notes.list_tags()]


@server.tool(annotations=READ_ONLY)
def recent_changes(limit: int = 50) -> list:
    """The change log, newest first: who created, edited, deleted or recoloured what, and when."""
    return [{**c, "ts": iso(c["ts"])} for c in notes.change_log(clamp_limit(limit, 500))]


@server.tool(annotations=READ_ONLY)
def list_trash(limit: int = 50) -> list:
    """Notes deleted in the last 30 days (restore_note brings one back)."""
    return [summary(n) for n in notes.trash(clamp_limit(limit, 200))]


@server.tool(annotations=READ_ONLY)
def view_note_image(note_id: str, size: Literal["small", "large"] = "small") -> Image:
    """Look at a note's picture (a screenshot, a photo). "small" is the list thumbnail (about 480 px);
    "large" is up to 1568 px on the long edge for reading detail."""
    n = note_or_fail(note_id)
    if not n["hasImage"]:
        raise ToolError("This note has no picture")
    got = images.get(n["id"], thumb=size == "small")
    if not got:
        raise ToolError("The picture is missing")
    if size == "small":
        return Image(data=got[0], format="jpeg")
    from PIL import Image as PILImage
    with PILImage.open(io.BytesIO(got[0])) as im:
        im.thumbnail((LARGE_EDGE, LARGE_EDGE), PILImage.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=82)
    return Image(data=buf.getvalue(), format="jpeg")
