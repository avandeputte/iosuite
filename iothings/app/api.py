"""The REST API (JSON) the web app uses. OpenAPI docs at /api/docs. Who may call a route is declared on it
(app/access.py); what an account may change is the model's business (app/model.py).

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`.
"""
import datetime as dt
import urllib.parse

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from iosuite_shared.access import json_body

from app import access, files, homebox, homebox_api, model, upkeep

router = APIRouter()


def _int(v) -> int | None:
    return int(v) if str(v or "").strip().isdigit() else None


@router.get("/api/summary", dependencies=[access.signed_in])
def summary(request: Request):
    """How many things (still yours, archived, warranties ending soon, upkeep due within a week, what they cost), the
    places (a tree, each with its path), the labels and the family (Settings › Security › Family), each with how many
    things; the currency; and what you may do."""
    u = request.state.user
    return {"counts": model.counts(), "locations": model.locations(), "labels": model.labels(), "family": model.family(),
            "currency": model.currency(),
            "may": {"add": model.may_add(u), "editAll": model.may_edit_all(u)}, "tasks": upkeep.tasks_enabled()}


# ---- things

@router.get("/api/items", dependencies=[access.signed_in])
def list_items(request: Request, q: str = "", location: int | None = None, label: int | None = None, archived: str | None = None,
               warranty: str | None = None, sort: str | None = None, limit: int = 500, offset: int = 0, person: str | None = None):
    """The things, without their files and log. q: words to find (in the name, the description, the maker, the model
    and serial numbers, the notes, the place, the labels, the own fields); location: in this place or one inside it;
    label: with this label; person: a family member's (id or name); archived: only (the archived ones) or also;
    warranty=soon: those whose warranty ends within 30 days; sort: name (as left out), new, updated, warranty, price or
    bought; limit, offset: a page of them."""
    u = request.state.user
    who = model.person(person)["id"] if person else None
    rows = model.find(q, location, label, archived, warranty == "soon", sort, limit, offset, person=who)
    return {"items": model.listed(u, rows)}


@router.post("/api/items", dependencies=[access.signed_in])
async def add_item(request: Request):
    """{name, description?, quantity?, locationId? (or location: a path such as "House / Kitchen", made where it is
    missing), labels? (ids or names, made where missing), people? (the family members whose it is: ids or names, see
    GET /api/summary's family), manufacturer?, modelNumber?, serialNumber?, assetId?, url?,
    purchaseDate?, purchasePrice?, purchaseFrom?, warrantyExpires?, lifetimeWarranty?, warrantyDetails?, insured?,
    archived?, soldDate?, soldPrice?, soldTo?, soldNotes?, notes?, fields?: [{name, value}]}. Dates are YYYY-MM-DD."""
    u = request.state.user
    b = await json_body(request)
    it = await run_in_threadpool(model.create, u, b)
    return JSONResponse(model.public(it, u), status_code=201)


@router.get("/api/items/{iid}", dependencies=[access.signed_in])
def get_item(iid: int, request: Request):
    """Everything about one thing: its files, its upkeep (with each next due day as ioTask has it, for the ones that are
    a task there) and its maintenance log."""
    u = request.state.user
    it = model.readable(u, iid)
    upkeep.sync(request, it["id"])
    return model.public(it, u)


@router.patch("/api/items/{iid}", dependencies=[access.signed_in])
async def change_item(iid: int, request: Request):
    """Change the fields given (as POST /api/items); the others stay. labels replaces the labels, people the people."""
    u = request.state.user
    b = await json_body(request)
    return model.public(await run_in_threadpool(lambda: model.update(u, model.readable(u, iid), b)), u)


@router.delete("/api/items/{iid}", dependencies=[access.signed_in])
def delete_item(iid: int, request: Request):
    """The thing goes, with its files, upkeep and log (and its upkeep's tasks in ioTask, where you may delete them).
    Archive a thing that is sold or thrown away instead to keep its story."""
    u = request.state.user
    it = model.readable(u, iid)
    model.need_write(u, it)
    upkeep.drop_tasks(request, it["id"])
    model.delete(u, it)
    return {"ok": True}


@router.post("/api/items/{iid}/duplicate", dependencies=[access.signed_in])
def duplicate_item(iid: int, request: Request):
    """A copy of the thing (its details, labels and people, not its serial number, files, upkeep or log)."""
    u = request.state.user
    return JSONResponse(model.public(model.duplicate(u, model.readable(u, iid)), u), status_code=201)


# ---- files

@router.post("/api/items/{iid}/files", dependencies=[access.signed_in])
async def add_file(iid: int, request: Request, kind: str | None = None, name: str | None = None):
    """The file itself as the request body (Content-Type its type): a photo, the manual, the receipt, the warranty, or
    another file (kind; left out: a photo for a picture, a manual for a PDF, other otherwise). name: its file name.
    The file as listed."""
    u = request.state.user
    raw = await request.body()

    def go():
        return files.add(u, model.readable(u, iid), raw, name, request.headers.get("content-type"), kind)
    return JSONResponse(await run_in_threadpool(go), status_code=201)


@router.get("/api/items/{iid}/files/{fid}", dependencies=[access.signed_in])
def get_file(iid: int, fid: int, request: Request, size: str = "", download: bool = False):
    """The file (size=small: the small picture of a photo). Shown in the browser when it is a picture, a PDF or plain
    text; anything else (and download=true) is a download. A file never changes, so it may be kept."""
    model.readable(request.state.user, iid)
    body, mime, name = files.content(iid, fid, size == "small")
    shown = files.inline(mime)
    headers = {"Cache-Control": "private, max-age=31536000, immutable",
               "Content-Disposition": f"{'inline' if shown and not download else 'attachment'}; filename*=UTF-8''{urllib.parse.quote(name)}"}
    if mime != "application/pdf":  # a browser's PDF viewer does not open in a sandbox; nothing else needs more than this
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; media-src 'self'; style-src 'unsafe-inline'; sandbox"
    return Response(body, media_type=mime if shown else "application/octet-stream", headers=headers)


@router.patch("/api/items/{iid}/files/{fid}", dependencies=[access.signed_in])
async def change_file(iid: int, fid: int, request: Request):
    """{name?, kind?, first?: true to put it first (a photo: the one the cards show)}"""
    u = request.state.user
    b = await json_body(request)
    return await run_in_threadpool(lambda: files.change(u, model.readable(u, iid), fid, b))


@router.delete("/api/items/{iid}/files/{fid}", dependencies=[access.signed_in])
def delete_file(iid: int, fid: int, request: Request):
    u = request.state.user
    files.remove(u, model.readable(u, iid), fid)
    return {"ok": True}


# ---- places and labels

@router.get("/api/locations", dependencies=[access.signed_in])
def list_locations(request: Request):
    """Every place, with its path and how many things are in it, in the order of their paths."""
    return {"items": model.locations()}


@router.post("/api/locations", dependencies=[access.signed_in])
async def add_location(request: Request):
    """{name, description?, parentId?}: a new place (inside another one, with parentId)."""
    b = await json_body(request)
    return JSONResponse(model.save_location(request.state.user, b), status_code=201)


@router.patch("/api/locations/{lid}", dependencies=[access.signed_in])
async def change_location(lid: int, request: Request):
    """{name?, description?, parentId?} (editors)"""
    b = await json_body(request)
    return model.save_location(request.state.user, b, lid)


@router.delete("/api/locations/{lid}", dependencies=[access.signed_in])
def delete_location(lid: int, request: Request):
    """The place goes; the things and places in it move up to the place it was in (editors)."""
    model.delete_location(request.state.user, lid)
    return {"ok": True}


@router.get("/api/labels", dependencies=[access.signed_in])
def list_labels(request: Request):
    return {"items": model.labels()}


@router.post("/api/labels", dependencies=[access.signed_in])
async def add_label(request: Request):
    """{name, color?: #rrggbb}"""
    b = await json_body(request)
    return JSONResponse(model.save_label(request.state.user, b), status_code=201)


@router.patch("/api/labels/{lid}", dependencies=[access.signed_in])
async def change_label(lid: int, request: Request):
    b = await json_body(request)
    return model.save_label(request.state.user, b, lid)


@router.delete("/api/labels/{lid}", dependencies=[access.signed_in])
def delete_label(lid: int, request: Request):
    model.delete_label(request.state.user, lid)
    return {"ok": True}


# ---- upkeep and the maintenance log

def _unavailable(e: upkeep.Unavailable):
    return HTTPException(e.status if e.status in (400, 403, 404, 409) else 502, str(e))


@router.get("/api/upkeep", dependencies=[access.signed_in])
def list_upkeep(request: Request, within: int | None = None):
    """Every upkeep of the things you own, the soonest first (within: only those due within that many days, the
    late ones included), each with its thing."""
    upkeep.sync(request)
    return {"items": upkeep.all_due(within)}


@router.get("/api/upkeep/lists", dependencies=[access.signed_in])
def upkeep_lists(request: Request):
    """Where an upkeep can go as a repeating task: {available, url, lists: [{id, name, shared}]}: your lists in ioTask
    that take new tasks. available is false while ioTask is not part of the suite; error says why it gave no lists."""
    if not upkeep.tasks_enabled():
        return {"available": False, "url": "", "lists": []}
    try:
        return {"available": True, "url": upkeep.tasks_url(), "lists": upkeep.task_lists(request)}
    except upkeep.Unavailable as e:
        return {"available": True, "url": upkeep.tasks_url(), "lists": [], "error": str(e)}


@router.post("/api/items/{iid}/upkeep", dependencies=[access.signed_in])
async def add_upkeep(iid: int, request: Request):
    """{title, everyN, everyUnit (day, week, month or year), nextDue, notes?, listId?}: what the thing needs every so
    often. listId: also a repeating task in that list of yours in ioTask, linked to the thing."""
    u = request.state.user
    b = await json_body(request)
    model.readable(u, iid)

    def go():
        try:
            return upkeep.add(request, u, iid, b)
        except upkeep.Unavailable as e:
            raise _unavailable(e)
    return JSONResponse(await run_in_threadpool(go), status_code=201)


@router.patch("/api/upkeep/{kid}", dependencies=[access.signed_in])
async def change_upkeep(kid: int, request: Request):
    """{title?, everyN?, everyUnit?, nextDue?, notes?}: its task in ioTask follows."""
    u = request.state.user
    b = await json_body(request)
    return await run_in_threadpool(upkeep.change, request, u, kid, b)


@router.delete("/api/upkeep/{kid}", dependencies=[access.signed_in])
def delete_upkeep(kid: int, request: Request, keepTask: bool = False):
    """The upkeep goes, and its task in ioTask too (keepTask=true leaves the task there)."""
    upkeep.remove(request, request.state.user, kid, keepTask)
    return {"ok": True}


@router.post("/api/upkeep/{kid}/done", dependencies=[access.signed_in])
async def upkeep_done(kid: int, request: Request):
    """{date?, notes?, cost?, doneBy?}: it was done (that day; today when left out): a line in the maintenance log, and
    the upkeep (and its task in ioTask) moves on to the next day. {upkeep, logged}."""
    u = request.state.user
    b = await json_body(request)
    return await run_in_threadpool(upkeep.done, request, u, kid, b)


@router.post("/api/items/{iid}/maintenance", dependencies=[access.signed_in])
async def add_maintenance(iid: int, request: Request):
    """{date?, title, notes?, cost?, doneBy?}: a line in the thing's maintenance log (a repair, a service, a part)."""
    u = request.state.user
    b = await json_body(request)
    model.readable(u, iid)
    return JSONResponse(await run_in_threadpool(upkeep.log_add, u, iid, b), status_code=201)


@router.patch("/api/maintenance/{mid}", dependencies=[access.signed_in])
async def change_maintenance(mid: int, request: Request):
    b = await json_body(request)
    return await run_in_threadpool(upkeep.log_change, request.state.user, mid, b)


@router.delete("/api/maintenance/{mid}", dependencies=[access.signed_in])
def delete_maintenance(mid: int, request: Request):
    upkeep.log_remove(request.state.user, mid)
    return {"ok": True}


# ---- Homebox: import its CSV export, export in the same format

@router.post("/api/import/homebox", dependencies=[access.signed_in])
async def import_homebox(request: Request):
    """A Homebox CSV export as the request body (Tools › Export inventory in Homebox): every row a thing, with its place
    (made where missing), labels and own fields. Importing the same export again changes what it brought instead of
    adding it twice. {added, changed, skipped: [why], locations, labels} (the new places and labels)."""
    u = request.state.user
    raw = await request.body()
    return await run_in_threadpool(lambda: homebox.keep(u, homebox.read(raw)))


@router.post("/api/import/homebox-server", dependencies=[access.signed_in])
async def import_homebox_server(request: Request):
    """{url, username, password}: sign in to a running Homebox and bring everything over in the background, the photos,
    manuals, receipts and the maintenance log too (editors). Answers at once, with a wrong address or password as an
    error; then GET this address says how far it got. Nothing about the Homebox account is kept."""
    u = request.state.user
    body = await json_body(request)
    return await run_in_threadpool(lambda: homebox_api.start(u, str(body.get("url") or ""), str(body.get("username") or ""), str(body.get("password") or "")))


@router.get("/api/import/homebox-server", dependencies=[access.signed_in])
def import_homebox_server_progress():
    """How far the import from a Homebox server got: {state: idle|running|done|failed, total, done, added, changed,
    files, log, skipped: [what was left out and why], error}."""
    return homebox_api.progress()


@router.get("/api/export.csv", dependencies=[access.signed_in])
def export_csv(request: Request, archived: bool = True):
    """Every thing as a CSV in Homebox's format (archived=false: the ones you still have only)."""
    body = homebox.export(archived)
    return Response(body, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="iothings-{dt.date.today().isoformat()}.csv"'})


# ---- the app's settings

@router.get("/api/things-settings", dependencies=[access.signed_in])
def home_settings(request: Request):
    """{currency, currencies}: the currency prices and costs are in."""
    return model.settings()


@router.put("/api/things-settings", dependencies=[access.admin])
async def set_home_settings(request: Request):
    """{currency}: a three-letter code (admins)."""
    return model.set_settings(await json_body(request))
