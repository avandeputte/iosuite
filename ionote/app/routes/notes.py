"""Notes, folders, tags, pictures and sync: the API the web app and the Mac and iPhone apps share.

Reads are open to whoever the sign-in rule lets in (as in iopix); every change needs a member (the apps sign in
as one, or as an editor or admin). A change the device made offline carries its own updatedAt: when the
server already has a later edit, the answer is 409 with the server's copy under "current".
"""
import time
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, Response
from iosuite_shared.access import json_body
from starlette.concurrency import run_in_threadpool

from app import access, attachments, images, notes, ocr
from app.http import attachment, jresp, user_name

router = APIRouter()


def _stale(e: notes.Stale):
    return JSONResponse({"detail": "A newer version is on the server", "current": e.current}, status_code=409)


def _bool(v):
    return None if v in (None, "") else v.lower() in ("1", "true", "yes")


@router.get("/api/meta", dependencies=[access.public])
def api_meta(request: Request):
    """Counts, folders (with counts), tags (with counts and colours) and the current rev, for the sidebar."""
    return jresp(request, notes.meta())


@router.get("/api/notes", dependencies=[access.public])
def api_notes(request: Request, q: str = "", folder: str = None, tag: str = None, pinned: str = None, image: str = None,
              sort: str = "updated", limit: int = 200, offset: int = 0, source: str = None):
    """Search and list: q matches every word (prefix) in the title, text, text in the picture and tags."""
    return jresp(request, notes.list_notes(q, folder, tag, _bool(pinned), _bool(image), sort, limit, offset, source))


@router.get("/api/notes/{uid}", dependencies=[access.public])
def api_note(uid: str):
    n = notes.get_note(uid)
    if not n:
        raise HTTPException(404, "No such note")
    if n["hasImage"]:
        n["image"] = images.info(uid)
    return n


@router.post("/api/notes", dependencies=[access.member_write])
async def api_note_create(request: Request):
    """A new note; the server picks the id unless the body has one. Notes made in the browser have source "web".
    {template: id} starts it from a template (its fields, placeholders filled in with the server's clock, unless the
    body gives them already filled in)."""
    body = await json_body(request)
    body.setdefault("source", "web")
    if body.get("template"):
        try:
            for k, v in notes.note_from_template(str(body.pop("template"))).items():
                body.setdefault(k, v)
        except (notes.NotFound, ValueError):
            raise HTTPException(404, "No such template")
    return await run_in_threadpool(notes.save_note, body.get("id"), body, user_name(request))


@router.put("/api/notes/{uid}", dependencies=[access.member_write])
async def api_note_put(uid: str, request: Request):
    """Create or update the note with this id (the apps choose ids). updatedAt: when the edit was made."""
    body = await json_body(request)
    try:
        return await run_in_threadpool(notes.save_note, uid, body, user_name(request), bool(body.get("force")))
    except notes.Stale as e:
        return _stale(e)


@router.delete("/api/notes/{uid}", dependencies=[access.member_write])
def api_note_delete(uid: str, request: Request, ts: float = None):
    """Move to the trash (a tombstone the devices sync). ts: when the device deleted it."""
    if not notes.get_note(uid):
        raise HTTPException(404, "No such note")
    try:
        return notes.delete_note(uid, user_name(request), ts)
    except notes.Stale as e:
        return _stale(e)


@router.post("/api/notes/{uid}/restore", dependencies=[access.member_write])
def api_note_restore(uid: str, request: Request):
    if not notes.get_note(uid):
        raise HTTPException(404, "No such note")
    return notes.restore_note(uid, user_name(request))


@router.get("/api/trash", dependencies=[access.public])
def api_trash(request: Request):
    """The trash; notes in it are purged (deleted for good) after notes.TRASH_DAYS days."""
    return jresp(request, {"notes": notes.trash(), "days": notes.TRASH_DAYS})


@router.post("/api/trash/empty", dependencies=[access.member_write])
def api_trash_empty(request: Request):
    """Delete every note in the trash for good (pictures and attachments too)."""
    return {"purged": notes.empty_trash(user_name(request))}


@router.delete("/api/trash/{uid}", dependencies=[access.member_write])
def api_trash_purge(uid: str, request: Request):
    """Delete one note in the trash for good."""
    return {"purged": notes.empty_trash(user_name(request), uid)}


@router.get("/api/notes/{uid}/related", dependencies=[access.public])
def api_related(uid: str, request: Request):
    """Notes like this one, and the tags and folder it may want (from those notes): {notes, tags, folder}."""
    s = notes.suggestions(uid)
    return jresp(request, {"notes": s["related"], "tags": s["tags"], "folder": s["folder"]})


# ---- pictures
def _mine(uid: str):
    """The note, when it is this account's; 404 otherwise (another account's note is never acknowledged)."""
    n = notes.get_note(uid)
    if not n:
        raise HTTPException(404, "No such note")
    return n


def _image_resp(request: Request, uid: str, thumb: bool):
    _mine(uid)
    got = images.get(uid, thumb)
    if not got:
        raise HTTPException(404, "This note has no picture")
    data, mime, sha = got
    etag = f'"{sha[:24]}{"t" if thumb else ""}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=86400", "Vary": "Cookie"}
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    return Response(data, media_type=mime, headers=headers)


@router.get("/api/notes/{uid}/image", dependencies=[access.public])
def api_image(uid: str, request: Request, download: int = 0):
    r = _image_resp(request, uid, False)
    if download and r.status_code == 200:
        n = notes.get_note(uid) or {}
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}.get(r.media_type, "img")
        name = "".join(c for c in notes.display_title(n) if c.isalnum() or c in " -_")[:60].strip() or "ionotes"
        r.headers.update(attachment(f"{name}.{ext}"))
    return r


@router.get("/api/notes/{uid}/thumb", dependencies=[access.public])
def api_thumb(uid: str, request: Request):
    return _image_resp(request, uid, True)


def _store(uid: str, data: bytes, request: Request):
    if not notes.get_note(uid):
        raise HTTPException(404, "No such note (create the note first)")
    try:
        n = images.put(uid, data, user_name(request))
    except images.BadImage as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, "No such note (create the note first)")
    # the devices read the text themselves; the server does it only for notes made in the web app
    if n["source"] == "web" and not n["ocrText"].strip():
        n["ocrQueued"] = ocr.enqueue(uid)
    return n


@router.put("/api/notes/{uid}/image", dependencies=[access.member_write])
async def api_image_put(uid: str, request: Request):
    """The picture as the raw request body (Content-Type image/png, image/jpeg...), as the apps send it."""
    data = await request.body()
    return await run_in_threadpool(_store, uid, data, request)


@router.post("/api/notes/{uid}/image", dependencies=[access.member_write])
async def api_image_upload(uid: str, request: Request, file: UploadFile = File(...)):
    """The picture as a form upload (the web app)."""
    data = await file.read()
    return await run_in_threadpool(_store, uid, data, request)


@router.delete("/api/notes/{uid}/image", dependencies=[access.member_write])
def api_image_delete(uid: str, request: Request):
    _mine(uid)
    try:
        return images.remove(uid, user_name(request))
    except KeyError:
        raise HTTPException(404, "No such note")


# ---- attachments
def _store_attachment(uid: str, data: bytes, name: str, mime: str, request: Request, aid: str = None, text: str = None):
    try:
        return attachments.put(uid, data, name, user_name(request), mime, aid, text)
    except attachments.BadFile as e:
        raise HTTPException(400, str(e))
    except notes.NotFound:
        raise HTTPException(404, "No such note (create the note first)")


@router.post("/api/notes/{uid}/attachments", dependencies=[access.member_write])
async def api_attach_upload(uid: str, request: Request, file: UploadFile = File(...)):
    """A file as a form upload (the web app); the server picks the attachment's id."""
    data = await file.read()
    return await run_in_threadpool(_store_attachment, uid, data, file.filename or "file", file.content_type or "", request)


@router.put("/api/notes/{uid}/attachments/{aid}", dependencies=[access.member_write])
async def api_attach_put(uid: str, aid: str, request: Request, name: str = "file"):
    """A file as the raw request body, with the id the device chose (?name=<file name>; X-Ionotes-Text: the text the
    device read from it, percent-encoded, when it did)."""
    data = await request.body()
    t = request.headers.get("x-ionotes-text")
    if t is not None:
        from urllib.parse import unquote
        t = unquote(t)
    return await run_in_threadpool(_store_attachment, uid, data, name, request.headers.get("content-type", ""), request, aid, t)


@router.patch("/api/notes/{uid}/attachments/{aid}", dependencies=[access.member_write])
async def api_attach_rename(uid: str, aid: str, request: Request):
    """{name}: rename the file."""
    body = await json_body(request)
    return attachments.rename(uid, aid, str(body.get("name") or ""), user_name(request))


@router.delete("/api/notes/{uid}/attachments/{aid}", dependencies=[access.member_write])
def api_attach_delete(uid: str, aid: str, request: Request):
    return attachments.remove(uid, aid, user_name(request))


def _attachment_resp(request: Request, uid: str, aid: str, thumb: bool, download: bool = False):
    got = attachments.get(uid, aid, thumb)
    if not got:
        raise HTTPException(404, "No such attachment" if not thumb else "This attachment has no preview")
    data, mime, sha, name = got
    etag = f'"{(sha or "")[:24]}{"t" if thumb else ""}"'
    headers = {"ETag": etag, "Cache-Control": "private, max-age=86400", "Vary": "Cookie", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'"}
    if not thumb:
        how = "inline" if mime in attachments.INLINE and not download else "attachment"
        ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in name)
        headers["Content-Disposition"] = f"{how}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"
        if mime not in attachments.INLINE:
            mime = mime if not mime.startswith("text/") else "text/plain"
    if etag in request.headers.get("if-none-match", ""):
        return Response(status_code=304, headers=headers)
    return Response(data, media_type=mime, headers=headers)


@router.get("/api/notes/{uid}/attachments/{aid}", dependencies=[access.public])
def api_attachment(uid: str, aid: str, request: Request, download: int = 0):
    return _attachment_resp(request, uid, aid, False, bool(download))


@router.get("/api/notes/{uid}/attachments/{aid}/thumb", dependencies=[access.public])
def api_attachment_thumb(uid: str, aid: str, request: Request):
    return _attachment_resp(request, uid, aid, True)


@router.get("/api/notes/{uid}/attachments/{aid}/text", dependencies=[access.public])
def api_attachment_text(uid: str, aid: str):
    """The text found in the file (a PDF's, a picture's read by the server, a text file's)."""
    t = attachments.text(uid, aid)
    if t is None:
        raise HTTPException(404, "No such attachment")
    return {"text": t}


# ---- templates
@router.get("/api/templates", dependencies=[access.public])
def api_templates(request: Request):
    notes.ensure_standard_templates()
    return jresp(request, {"templates": notes.list_templates()})


@router.post("/api/templates", dependencies=[access.member_write])
async def api_template_create(request: Request):
    body = await json_body(request)
    return notes.save_template(body.get("id"), body, user_name(request))


@router.post("/api/templates/standard", dependencies=[access.member_write])
def api_templates_standard(request: Request):
    """Add the standard templates that are missing, deleted ones included."""
    return {"added": notes.restore_standard_templates(user_name(request)), "templates": notes.list_templates()}


@router.put("/api/templates/{uid}", dependencies=[access.member_write])
async def api_template_put(uid: str, request: Request):
    """{name, title, body, tags, folderID, updatedAt}; {deleted: true} deletes it."""
    body = await json_body(request)
    try:
        return notes.save_template(uid, body, user_name(request), bool(body.get("force")))
    except notes.Stale as e:
        return _stale(e)


@router.delete("/api/templates/{uid}", dependencies=[access.member_write])
def api_template_delete(uid: str, request: Request, ts: float = None):
    if not notes.get_template(uid):
        raise HTTPException(404, "No such template")
    try:
        return notes.save_template(uid, {"deleted": True, "updatedAt": ts or time.time()}, user_name(request), force=ts is None)
    except notes.Stale as e:
        return _stale(e)


# ---- folders
@router.get("/api/folders", dependencies=[access.public])
def api_folders(request: Request):
    return jresp(request, {"folders": notes.list_folders()})


@router.post("/api/folders", dependencies=[access.member_write])
async def api_folder_create(request: Request):
    body = await json_body(request)
    return notes.save_folder(body.get("id"), body, user_name(request))


@router.put("/api/folders/{uid}", dependencies=[access.member_write])
async def api_folder_put(uid: str, request: Request):
    """{name, color, updatedAt}; {deleted: true} deletes it (its notes stay, in no folder)."""
    body = await json_body(request)
    try:
        return notes.save_folder(uid, body, user_name(request), bool(body.get("force")))
    except notes.Stale as e:
        return _stale(e)


@router.delete("/api/folders/{uid}", dependencies=[access.member_write])
def api_folder_delete(uid: str, request: Request, ts: float = None):
    if not any(f["id"] == notes.check_uuid(uid) for f in notes.list_folders(include_deleted=True)):
        raise HTTPException(404, "No such folder")
    try:
        return notes.save_folder(uid, {"deleted": True, "updatedAt": ts or time.time()}, user_name(request), force=ts is None)
    except notes.Stale as e:
        return _stale(e)


# ---- tags
@router.get("/api/tags", dependencies=[access.public])
def api_tags(request: Request):
    return jresp(request, {"tags": notes.list_tags(), "colors": list(notes.COLORS)})


@router.put("/api/tags/{name}/color", dependencies=[access.member_write])
async def api_tag_color(name: str, request: Request):
    """{color: one of the colours, or null for none, updatedAt}."""
    body = await json_body(request)
    try:
        return notes.set_tag_color(name, body.get("color"), user_name(request), body.get("updatedAt"), bool(body.get("force")))
    except notes.Stale as e:
        return _stale(e)


@router.post("/api/tags/rename", dependencies=[access.member_write])
async def api_tag_rename(request: Request):
    body = await json_body(request)
    return {"changed": notes.rename_tag(str(body.get("from", "")), str(body.get("to", "")), user_name(request))}


@router.post("/api/tags/remove", dependencies=[access.member_write])
async def api_tag_remove(request: Request):
    body = await json_body(request)
    return {"changed": notes.remove_tag(str(body.get("name", "")), user_name(request))}


# ---- sync
@router.get("/api/sync", dependencies=[access.public])
def api_sync(request: Request, since: int = 0, limit: int = 500):
    """Everything changed after rev `since` (0: everything), tombstones included; ask again while `more`."""
    return jresp(request, notes.changes(since, limit))


@router.post("/api/sync/push", dependencies=[access.member_write])
async def api_sync_push(request: Request):
    """A device's queued changes in one request: {notes: [...], folders: [...], tags: [{name, color, updatedAt}], templates: [...]}.
    Each is applied like its own PUT; the answer lists, per item, the server's copy and whether it was taken
    ("ok") or the server already had a later edit ("stale"). Pictures go separately (PUT /api/notes/{id}/image)."""
    body = await json_body(request)
    user = user_name(request)

    def apply():
        out = {"folders": [], "notes": [], "tags": []}
        for f in (body.get("folders") or [])[:5000]:
            out["folders"].append(_one(lambda: notes.save_folder(f.get("id"), f, user)))
        for n in (body.get("notes") or [])[:5000]:
            out["notes"].append(_one(lambda: notes.save_note(n.get("id"), n, user)))
        for t in (body.get("tags") or [])[:5000]:
            out["tags"].append(_one(lambda: notes.set_tag_color(t.get("name", ""), t.get("color"), user, t.get("updatedAt"))))
        if body.get("templates"):
            out["templates"] = [_one(lambda: notes.save_template(t.get("id"), t, user)) for t in (body.get("templates") or [])[:5000]]
        out["rev"] = notes.db.current_rev()
        return out
    return await run_in_threadpool(apply)


def _one(fn):
    try:
        return {"status": "ok", "item": fn()}
    except notes.Stale as e:
        return {"status": "stale", "item": e.current}
    except notes.NotFound as e:
        return {"status": "error", "error": str(e)}
    except (ValueError, TypeError) as e:
        return {"status": "error", "error": str(e)[:200]}
