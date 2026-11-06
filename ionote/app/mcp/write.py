"""The tools that change notes, folders and tags. Each takes an editor's or admin's account (the one the client signed
in as) and is refused in read-only mode. Changes are logged under the name "MCP" and reach the apps with their next sync."""
import base64
import time
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import images, notes
from app.mcp.base import ADDS, DELETES, MCP_USER, WRITES, need_writer, note_or_fail, resolve_folder, server, summary


def _save(uid, data):
    try:
        return notes.save_note(uid, {**data, "updatedAt": time.time()}, MCP_USER, force=True)
    except ValueError as e:
        raise ToolError(str(e))


@server.tool(annotations=ADDS)
def create_note(text: str = "", title: str = "", tags: Optional[list[str]] = None, folder: Optional[str] = None,
                pinned: bool = False, picture_base64: Optional[str] = None) -> dict:
    """Create a note. folder: a name or id. picture_base64: an optional PNG/JPEG for the note (base64)."""
    need_writer()
    if not (text.strip() or title.strip() or picture_base64):
        raise ToolError("A note needs a title, text or a picture")
    n = _save(None, {"title": title, "body": text, "tags": tags or [], "folderID": resolve_folder(folder), "pinned": pinned, "source": "mcp"})
    if picture_base64:
        try:
            n = images.put(n["id"], base64.b64decode(picture_base64), MCP_USER)
        except (images.BadImage, ValueError) as e:
            raise ToolError(f"The note was made, but not its picture: {e}")
    return summary(n)


@server.tool(annotations=WRITES)
def update_note(note_id: str, title: Optional[str] = None, text: Optional[str] = None, append_text: Optional[str] = None,
                tags: Optional[list[str]] = None, add_tags: Optional[list[str]] = None, remove_tags: Optional[list[str]] = None,
                folder: Optional[str] = None, pinned: Optional[bool] = None) -> dict:
    """Change a note: any of title, text (replaces it), append_text (adds a paragraph at the end), tags (replaces
    them), add_tags / remove_tags, folder (a name or id; "none" takes it out of its folder), pinned."""
    need_writer()
    n = note_or_fail(note_id)
    d = {}
    if title is not None:
        d["title"] = title
    if text is not None:
        d["body"] = text
    if append_text:
        base = d.get("body", n["body"])
        d["body"] = (base.rstrip() + "\n\n" if base.strip() else "") + append_text
    t = list(n["tags"]) if tags is None else list(tags)
    t += add_tags or []
    if remove_tags:
        drop = {x.lower().lstrip("#") for x in remove_tags}
        t = [x for x in t if x.lower() not in drop]
    if tags is not None or add_tags or remove_tags:
        d["tags"] = t
    if folder is not None:
        d["folderID"] = None if folder in ("", "none") else resolve_folder(folder)
    if pinned is not None:
        d["pinned"] = pinned
    if not d:
        raise ToolError("Nothing to change")
    return summary(_save(n["id"], d))


@server.tool(annotations=WRITES)
def organize_notes(note_ids: list[str], folder: Optional[str] = None, add_tags: Optional[list[str]] = None,
                   remove_tags: Optional[list[str]] = None, pinned: Optional[bool] = None) -> dict:
    """The same change for many notes at once: move to a folder ("none": out of any folder), add or remove tags, pin."""
    need_writer()
    if len(note_ids) > 500:
        raise ToolError("At most 500 notes at a time")
    fid = None if folder in (None, "", "none") else resolve_folder(folder)
    changed = []
    for uid in note_ids:
        n = note_or_fail(uid)
        d = {}
        if folder is not None:
            d["folderID"] = fid
        if add_tags or remove_tags:
            drop = {x.lower().lstrip("#") for x in remove_tags or []}
            d["tags"] = [x for x in n["tags"] + list(add_tags or []) if x.lower() not in drop]
        if pinned is not None:
            d["pinned"] = pinned
        if d:
            _save(n["id"], d)
            changed.append(n["id"])
    return {"changed": len(changed)}


@server.tool(annotations=DELETES)
def delete_note(note_id: str) -> dict:
    """Move a note to the trash (restore_note brings it back for 30 days; its picture is removed)."""
    need_writer()
    n = note_or_fail(note_id)
    notes.delete_note(n["id"], MCP_USER)
    return {"deleted": n["id"], "title": notes.display_title(n)}


@server.tool(annotations=WRITES)
def restore_note(note_id: str) -> dict:
    """Take a note out of the trash."""
    need_writer()
    n = note_or_fail(note_id)
    return summary(notes.restore_note(n["id"], MCP_USER))


@server.tool(annotations=WRITES)
def manage_folder(action: Literal["create", "rename", "color", "delete"], name: str, new_name: Optional[str] = None,
                  color: Optional[str] = None) -> dict:
    """Folders: create (name, optional color), rename (name → new_name), color (name, color or "" for none), delete
    (the notes in it stay, in no folder). Colours: red orange yellow green mint teal blue indigo purple pink brown gray."""
    need_writer()
    if color and color not in notes.COLORS:
        raise ToolError("Colours: " + ", ".join(notes.COLORS))
    try:
        if action == "create":
            return notes.save_folder(None, {"name": name, "color": color or None}, MCP_USER)
        fid = resolve_folder(name)
        if action == "rename":
            if not new_name:
                raise ToolError("new_name is needed")
            return notes.save_folder(fid, {"name": new_name}, MCP_USER, force=True)
        if action == "color":
            return notes.save_folder(fid, {"color": color or None}, MCP_USER, force=True)
        return notes.save_folder(fid, {"deleted": True}, MCP_USER, force=True)
    except ValueError as e:
        raise ToolError(str(e))


@server.tool(annotations=WRITES)
def manage_tag(action: Literal["rename", "color", "remove"], name: str, new_name: Optional[str] = None,
               color: Optional[str] = None) -> dict:
    """Tags: rename (on every note; merges into an existing tag of that name), color (or "" for none), remove (from
    every note)."""
    need_writer()
    try:
        if action == "rename":
            if not new_name:
                raise ToolError("new_name is needed")
            return {"notes_changed": notes.rename_tag(name, new_name, MCP_USER)}
        if action == "color":
            if color and color not in notes.COLORS:
                raise ToolError("Colours: " + ", ".join(notes.COLORS))
            return notes.set_tag_color(name, color or None, MCP_USER, force=True)
        return {"notes_changed": notes.remove_tag(name, MCP_USER)}
    except ValueError as e:
        raise ToolError(str(e))
