"""The tools that change notes, folders and tags. Each takes an editor's or admin's account (the one the client signed
in as). Changes are logged under the name "MCP" and reach the apps with their next sync."""
import base64
import time
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import attachments, images, notes
from app.mcp.base import ADDS, DELETES, MCP_USER, WRITES, need_writer, note_or_fail, resolve_folder, server, summary


def _save(uid, data):
    try:
        return notes.save_note(uid, {**data, "updatedAt": time.time()}, MCP_USER, force=True)
    except ValueError as e:
        raise ToolError(str(e))


@server.tool(annotations=ADDS)
def create_note(text: str = "", title: str = "", tags: Optional[list[str]] = None, folder: Optional[str] = None,
                pinned: bool = False, picture_base64: Optional[str] = None, template: Optional[str] = None) -> dict:
    """Create a note. folder: a name or id. picture_base64: an optional PNG/JPEG for the note (base64).
    template: a template's name or id (list_templates): the note starts from it, and text, title, tags and folder
    given here are added (text goes after the template's)."""
    need_writer()
    base = {}
    if template:
        t = _template(template)
        base = notes.note_from_template(t["id"])
    if not (text.strip() or title.strip() or picture_base64 or base):
        raise ToolError("A note needs a title, text or a picture")
    body = (base.get("body", "").rstrip() + "\n\n" + text if base.get("body", "").strip() and text.strip() else (text or base.get("body", "")))
    n = _save(None, {"title": title or base.get("title", ""), "body": body, "tags": list(base.get("tags") or []) + list(tags or []),
                     "folderID": resolve_folder(folder) if folder else base.get("folderID"), "pinned": pinned, "source": "mcp"})
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
    """Move a note to the trash (restore_note brings it back for 30 days, then it is deleted for good; its picture is removed)."""
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


def _template(name_or_id: str) -> dict:
    s = str(name_or_id).strip()
    ts = notes.list_templates()
    for t in ts:
        if t["id"] in (s, s.upper()) or t["name"].lower() == s.lower():
            return t
    part = [t for t in ts if s.lower() in t["name"].lower()]
    if len(part) == 1:
        return part[0]
    raise ToolError(f"No single template matches '{s}'. Templates: " + (", ".join(t["name"] for t in ts) or "none yet"))


@server.tool(annotations=WRITES)
def manage_template(action: Literal["create", "update", "delete"], name: str, new_name: Optional[str] = None, title: Optional[str] = None,
                    text: Optional[str] = None, tags: Optional[list[str]] = None, folder: Optional[str] = None) -> dict:
    """Templates for new notes: create (name, and any of title, text, tags, folder), update (the template called name:
    any of new_name, title, text, tags, folder; folder "none" for none), delete. In title and text, {{date}}, {{time}},
    {{datetime}}, {{weekday}}, {{month}}, {{year}}, {{tomorrow}} and {{yesterday}} are filled in when a note is made."""
    need_writer()
    try:
        if action == "create":
            d = {"name": name, "title": title or "", "body": text or "", "tags": tags or [], "folderID": resolve_folder(folder) if folder and folder != "none" else None}
            return notes.save_template(None, d, MCP_USER)
        t = _template(name)
        if action == "delete":
            notes.save_template(t["id"], {"deleted": True}, MCP_USER, force=True)
            return {"deleted": t["name"]}
        d = {}
        for k, v in (("name", new_name), ("title", title), ("body", text), ("tags", tags)):
            if v is not None:
                d[k] = v
        if folder is not None:
            d["folderID"] = None if folder in ("", "none") else resolve_folder(folder)
        if not d:
            raise ToolError("Nothing to change")
        return notes.save_template(t["id"], {**d, "updatedAt": time.time()}, MCP_USER, force=True)
    except ValueError as e:
        raise ToolError(str(e))


@server.tool(annotations=ADDS)
def attach_file(note_id: str, file_base64: str, name: str) -> dict:
    """Attach a file (a PDF, a picture, a document; base64) to a note. Its text is read for search."""
    need_writer()
    n = note_or_fail(note_id)
    try:
        n = attachments.put(n["id"], base64.b64decode(file_base64), name, MCP_USER)
    except (attachments.BadFile, ValueError) as e:
        raise ToolError(str(e))
    return {**summary(n), "attachments": [a["name"] for a in n["attachments"]]}


@server.tool(annotations=DELETES)
def remove_attachment(note_id: str, attachment_id: str) -> dict:
    """Remove a file attached to a note (get_note lists them)."""
    need_writer()
    n = note_or_fail(note_id)
    try:
        n = attachments.remove(n["id"], attachment_id, MCP_USER)
    except (notes.NotFound, ValueError) as e:
        raise ToolError(str(e))
    return {**summary(n), "attachments": [a["name"] for a in n["attachments"]]}


@server.tool(annotations=DELETES)
def empty_trash(note_id: Optional[str] = None) -> dict:
    """Delete for good, with no way back: one note in the trash (note_id), or everything in it. Only when asked to."""
    need_writer()
    try:
        return {"purged": notes.empty_trash(MCP_USER, note_id)}
    except (notes.NotFound, ValueError) as e:
        raise ToolError(str(e))
