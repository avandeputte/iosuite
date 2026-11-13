"""The read-only tools: the overview, search with the web app's filters, one note in full, folders and tags,
what changed recently, and looking at a note's picture."""
import io
from typing import Literal, Optional

from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError

from iosuite_shared import users

from app import attachments, config, images, notes
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
    """Whose notes these are: the account the client signed in as."""
    u = users.get(notes.owner(), config.APP) if notes.owner() > 0 else None
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
    if n.get("attachments"):
        out["attachments"] = [{"id": a["id"], "name": a["name"], "type": a["mime"], "bytes": a["bytes"],
                               "text_preview": _preview(attachments.text(n["id"], a["id"]) or "", 400)} for a in n["attachments"]]
    return {k: v for k, v in out.items() if v not in (None, "", [])}


def _preview(t: str, chars: int) -> str:
    t = t.strip()
    return t[:chars] + ("…" if len(t) > chars else "")


@server.tool(annotations=READ_ONLY)
def read_attachment(note_id: str, attachment_id: str, offset: int = 0, max_chars: int = 20000):
    """An attached file: its text (a PDF's, a text file's, the text read from a picture), a page of max_chars at a time
    from offset, or, for a picture with no text, the picture itself."""
    n = note_or_fail(note_id)
    a = next((a for a in n.get("attachments") or [] if a["id"] == attachment_id.upper() or a["id"] == attachment_id), None)
    if not a:
        raise ToolError("No such attachment on this note (get_note lists them)")
    t = attachments.text(n["id"], a["id"]) or ""
    if not t and a["mime"].startswith("image/"):
        got = attachments.get(n["id"], a["id"], thumb=False)
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(got[0])) as im:
            im.thumbnail((LARGE_EDGE, LARGE_EDGE))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, "JPEG", quality=82)
        return Image(data=buf.getvalue(), format="jpeg")
    offset, max_chars = max(0, int(offset)), clamp_limit(max_chars, 100000)
    return {"name": a["name"], "type": a["mime"], "chars": len(t), "offset": offset, "text": t[offset:offset + max_chars],
            "more": offset + max_chars < len(t)}


@server.tool(annotations=READ_ONLY)
def related_notes(note_id: str, limit: int = 8) -> dict:
    """Notes like this one (words and tags in common), best first, with the tags and the folder those notes suggest
    for it. Use it to find what belongs together, to link notes, or before filing or tagging a note."""
    n = note_or_fail(note_id)
    s = notes.suggestions(n["id"])
    folders = {f["id"]: f["name"] for f in notes.list_folders()}
    return {"note": notes.display_title(n), "related": [{**summary(d, folders, 160), "score": d["score"]} for d in s["related"][:clamp_limit(limit, 30)]],
            "suggested_tags": s["tags"], "suggested_folder": s["folder"]["name"] if s["folder"] else None}


@server.tool(annotations=READ_ONLY)
def suggest_organization(limit: int = 30, only_unfiled: bool = True) -> dict:
    """For the newest notes with no folder (or, only_unfiled false, with no tags either way), the tags and folder the
    notes most like them have. A starting point for tidying up: review the suggestions, then apply them with
    organize_notes or update_note."""
    res = notes.list_notes(folder="none" if only_unfiled else None, limit=clamp_limit(limit, 100))
    out = []
    for n in res["notes"]:
        if not only_unfiled and n["tags"] and n["folderID"]:
            continue
        s = notes.suggestions(n["id"])
        if s["tags"] or s["folder"]:
            out.append({"id": n["id"], "title": notes.display_title(n), "tags": n["tags"], "suggested_tags": s["tags"],
                        "suggested_folder": s["folder"]["name"] if s["folder"] else None})
    return {"checked": len(res["notes"]), "with_suggestions": len(out), "notes": out}


@server.tool(annotations=READ_ONLY)
def notes_digest(since: str, until: Optional[str] = None, folder: Optional[str] = None, tag: Optional[str] = None,
                 text_chars: int = 2000, limit: int = 50) -> dict:
    """The notes made between two dates (YYYY-MM-DD, inclusive; until defaults to today), oldest first, each with up
    to text_chars of its text and of the text in its picture and files: what you need to summarise a day, a week or a
    project. Narrow it with folder or tag."""
    lo = parse_date(since)
    hi = parse_date(until, end=True) if until else None
    fid = "none" if folder == "none" else resolve_folder(folder)
    res = notes.list_notes("", fid, tag, None, None, "oldest", clamp_limit(limit, 200), 0, None, created_from=lo, created_before=hi)
    folders = {f["id"]: f["name"] for f in notes.list_folders()}
    chars = clamp_limit(text_chars, 20000)
    items = []
    for n in res["notes"]:
        files = [{"name": a["name"], "text": _preview(attachments.text(n["id"], a["id"]) or "", chars // 2)} for a in n.get("attachments") or []]
        items.append({k: v for k, v in {"id": n["id"], "title": notes.display_title(n), "created": iso(n["createdAt"]), "folder": folders.get(n["folderID"]),
                                        "tags": n["tags"], "text": _preview(n["body"], chars), "text_in_picture": _preview(n["ocrText"], chars // 2),
                                        "files": files, "url": f"{APP}/#/note/{n['id']}"}.items() if v not in (None, "", [])})
    return {"total": res["total"], "returned": len(items), "notes": items}


@server.tool(annotations=READ_ONLY)
def list_templates() -> list:
    """The templates for new notes (create_note with template= makes a note from one; {{date}}, {{time}}, {{weekday}}
    and the like are filled in)."""
    folders = {f["id"]: f["name"] for f in notes.list_folders()}
    return [{k: v for k, v in {"id": t["id"], "name": t["name"], "title": t["title"], "text": t["body"], "tags": t["tags"],
                               "folder": folders.get(t["folderID"])}.items() if v not in (None, "", [])} for t in notes.list_templates()]


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
    """Notes in the trash (restore_note brings one back; they are deleted for good after 30 days)."""
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
