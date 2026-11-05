"""Notes, folders, tags, pictures and sync: the API the web app and the Mac and iPhone apps share.

Reads are open to whoever the sign-in rule lets in (as in iopix); every change needs an editor (the apps sign in
as one) and is refused in read-only mode. A change the device made offline carries its own updatedAt: when the
server already has a later edit, the answer is 409 with the server's copy under "current".
"""
import time

from fastapi import APIRouter, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from app import access, images, notes, ocr
from app.http import jresp, json_body, user_name

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


@router.post("/api/notes", dependencies=[access.editor_write])
async def api_note_create(request: Request):
    """A new note; the server picks the id unless the body has one. Notes made in the browser have source "web"."""
    body = await json_body(request)
    body.setdefault("source", "web")
    return await run_in_threadpool(notes.save_note, body.get("id"), body, user_name(request))


@router.put("/api/notes/{uid}", dependencies=[access.editor_write])
async def api_note_put(uid: str, request: Request):
    """Create or update the note with this id (the apps choose ids). updatedAt: when the edit was made."""
    body = await json_body(request)
    try:
        return await run_in_threadpool(notes.save_note, uid, body, user_name(request), bool(body.get("force")))
    except notes.Stale as e:
        return _stale(e)


@router.delete("/api/notes/{uid}", dependencies=[access.editor_write])
def api_note_delete(uid: str, request: Request, ts: float = None):
    """Move to the trash (a tombstone the devices sync). ts: when the device deleted it."""
    if not notes.get_note(uid):
        raise HTTPException(404, "No such note")
    try:
        return notes.delete_note(uid, user_name(request), ts)
    except notes.Stale as e:
        return _stale(e)


@router.post("/api/notes/{uid}/restore", dependencies=[access.editor_write])
def api_note_restore(uid: str, request: Request):
    if not notes.get_note(uid):
        raise HTTPException(404, "No such note")
    return notes.restore_note(uid, user_name(request))


@router.get("/api/trash", dependencies=[access.public])
def api_trash(request: Request):
    return jresp(request, {"notes": notes.trash()})


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
        r.headers["Content-Disposition"] = f'attachment; filename="{name}.{ext}"'
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


@router.put("/api/notes/{uid}/image", dependencies=[access.editor_write])
async def api_image_put(uid: str, request: Request):
    """The picture as the raw request body (Content-Type image/png, image/jpeg...), as the apps send it."""
    data = await request.body()
    return await run_in_threadpool(_store, uid, data, request)


@router.post("/api/notes/{uid}/image", dependencies=[access.editor_write])
async def api_image_upload(uid: str, request: Request, file: UploadFile = File(...)):
    """The picture as a form upload (the web app)."""
    data = await file.read()
    return await run_in_threadpool(_store, uid, data, request)


@router.delete("/api/notes/{uid}/image", dependencies=[access.editor_write])
def api_image_delete(uid: str, request: Request):
    _mine(uid)
    try:
        return images.remove(uid, user_name(request))
    except KeyError:
        raise HTTPException(404, "No such note")


# ---- folders
@router.get("/api/folders", dependencies=[access.public])
def api_folders(request: Request):
    return jresp(request, {"folders": notes.list_folders()})


@router.post("/api/folders", dependencies=[access.editor_write])
async def api_folder_create(request: Request):
    body = await json_body(request)
    return notes.save_folder(body.get("id"), body, user_name(request))


@router.put("/api/folders/{uid}", dependencies=[access.editor_write])
async def api_folder_put(uid: str, request: Request):
    """{name, color, updatedAt}; {deleted: true} deletes it (its notes stay, in no folder)."""
    body = await json_body(request)
    try:
        return notes.save_folder(uid, body, user_name(request), bool(body.get("force")))
    except notes.Stale as e:
        return _stale(e)


@router.delete("/api/folders/{uid}", dependencies=[access.editor_write])
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


@router.put("/api/tags/{name}/color", dependencies=[access.editor_write])
async def api_tag_color(name: str, request: Request):
    """{color: one of the colours, or null for none, updatedAt}."""
    body = await json_body(request)
    try:
        return notes.set_tag_color(name, body.get("color"), user_name(request), body.get("updatedAt"), bool(body.get("force")))
    except notes.Stale as e:
        return _stale(e)


@router.post("/api/tags/rename", dependencies=[access.editor_write])
async def api_tag_rename(request: Request):
    body = await json_body(request)
    return {"changed": notes.rename_tag(str(body.get("from", "")), str(body.get("to", "")), user_name(request))}


@router.post("/api/tags/remove", dependencies=[access.editor_write])
async def api_tag_remove(request: Request):
    body = await json_body(request)
    return {"changed": notes.remove_tag(str(body.get("name", "")), user_name(request))}


# ---- sync
@router.get("/api/sync", dependencies=[access.public])
def api_sync(request: Request, since: int = 0, limit: int = 500):
    """Everything changed after rev `since` (0: everything), tombstones included; ask again while `more`."""
    return jresp(request, notes.changes(since, limit))


@router.post("/api/sync/push", dependencies=[access.editor_write])
async def api_sync_push(request: Request):
    """A device's queued changes in one request: {notes: [...], folders: [...], tags: [{name, color, updatedAt}]}.
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
