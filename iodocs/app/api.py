"""The REST API (JSON) the web app uses. OpenAPI docs at /api/docs. Who may call a route is declared on it
(app/access.py); which documents an account sees and may change is the model's business (app/model.py).

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`.
"""
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from iosuite_shared.access import json_body

from app import access, files, model, ocr

router = APIRouter()


@router.get("/api/summary", dependencies=[access.signed_in])
def summary(request: Request):
    """How many documents you see (in all, expiring within their reminder, expired, archived, by kind), the kinds
    (each with its usual reminder), the family (each with how many documents you see are theirs), what this server
    can read off a scan, and what you may do."""
    u = request.state.user
    return {"counts": model.counts(u), "family": model.family(u),
            "kinds": [{"key": k, "label": v[0], "plural": v[1], "remind": v[2], "icon": v[3]} for k, v in model.KINDS.items()],
            "reads": ocr.available(), "may": {"add": model.may_add(u), "editAll": model.may_edit_all(u)}}


# ---- documents

@router.get("/api/documents", dependencies=[access.signed_in])
def list_docs(request: Request, q: str = "", kind: str | None = None, person: str | None = None, status: str | None = None,
              sort: str | None = None, limit: int = 500, offset: int = 0):
    """The documents you see, without their files. q: words to find (title, kind, number, issuer, notes, own fields,
    people, and the text read off the scans); kind: one kind; person: a family member's (id or name); status:
    expiring (expired, or within their reminder), expired, archived or all (left out: those not archived); sort:
    expires (as left out: the soonest first), title, new, updated or kind; limit, offset: a page of them."""
    u = request.state.user
    who = model.person(person)["id"] if person else None
    return {"items": model.listed(u, model.find(u, q, kind, who, status, sort, limit, offset))}


@router.post("/api/documents", dependencies=[access.signed_in])
async def add_doc(request: Request):
    """{title?, kind?, number?, issuer?, country?, issuedOn?, expiresOn?, remindDays? (days before it expires; 0: no
    reminder; left out: the kind's usual), visibility? (family, people or private), people? (family members: ids or
    names), notes?, fields?: [{name, value}]}. Dates are YYYY-MM-DD."""
    u = request.state.user
    b = await json_body(request)
    d = await run_in_threadpool(model.create, u, b)
    return JSONResponse(model.public(d, u), status_code=201)


@router.get("/api/documents/{did}", dependencies=[access.signed_in])
def get_doc(did: int, request: Request):
    """Everything about one document, with its files (and what was read off each)."""
    u = request.state.user
    return model.public(model.readable(u, did), u)


@router.patch("/api/documents/{did}", dependencies=[access.signed_in])
async def change_doc(did: int, request: Request):
    """Change the fields given (as POST /api/documents); the others stay. people replaces the people."""
    u = request.state.user
    b = await json_body(request)
    return model.public(await run_in_threadpool(lambda: model.update(u, model.readable(u, did), b)), u)


@router.delete("/api/documents/{did}", dependencies=[access.signed_in])
def delete_doc(did: int, request: Request):
    """The document goes, with its files. Archive an old one instead to keep it (archived: true)."""
    u = request.state.user
    model.delete(u, model.readable(u, did))
    return {"ok": True}


@router.post("/api/documents/{did}/renew", dependencies=[access.signed_in])
async def renew_doc(did: int, request: Request):
    """The new one in its place: {number?, issuedOn?, expiresOn?, ...} as POST /api/documents; the kind, title, issuer,
    people, visibility and reminder are this one's unless given. This one is archived. The new document."""
    u = request.state.user
    b = await json_body(request)
    d = await run_in_threadpool(lambda: model.renew(u, model.readable(u, did), b))
    return JSONResponse(model.public(d, u), status_code=201)


# ---- files

@router.post("/api/documents/{did}/files", dependencies=[access.signed_in])
async def add_file(did: int, request: Request, name: str | None = None, read: bool = True):
    """The file itself as the request body (Content-Type its type): a scan, a photo, a PDF. name: its file name.
    read (as left out): read it at once (OCR, a passport's zone, a license's barcode) and fill in the document where
    it says nothing yet. {file, found, filled, differs} (found etc. only when read)."""
    u = request.state.user
    raw = await request.body()

    def go():
        d = model.readable(u, did)
        f = files.add(u, d, raw, name, request.headers.get("content-type"))
        if read and (f["mime"].startswith("image/") or f["mime"] == "application/pdf"):
            try:
                return files.read(u, model.get(did), f["id"])
            except Exception as e:  # noqa: BLE001 - the file is kept; reading it can be tried again
                return {"file": files.one(did, f["id"]), "found": {}, "filled": [], "differs": [], "error": str(e)[:300]}
        return {"file": f, "found": {}, "filled": [], "differs": []}
    return JSONResponse(await run_in_threadpool(go), status_code=201)


@router.get("/api/documents/{did}/files/{fid}", dependencies=[access.signed_in])
def get_file(did: int, fid: int, request: Request, size: str = "", download: bool = False):
    """The file (size=small: its small picture). Shown in the browser when it is a picture, a PDF or plain text;
    anything else (and download=true) is a download. A file never changes, so it may be kept."""
    model.readable(request.state.user, did)
    body, mime, name = files.content(did, fid, size == "small")
    shown = files.inline(mime)
    headers = {"Cache-Control": "private, max-age=31536000, immutable",
               "Content-Disposition": f"{'inline' if shown and not download else 'attachment'}; filename*=UTF-8''{urllib.parse.quote(name)}"}
    if mime != "application/pdf":
        headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox"
    return Response(body, media_type=mime if shown else "application/octet-stream", headers=headers)


@router.get("/api/documents/{did}/files/{fid}/text", dependencies=[access.signed_in])
def get_file_text(did: int, fid: int, request: Request):
    """{text}: what was read off the file."""
    model.readable(request.state.user, did)
    return {"text": files.text_of(did, fid)}


@router.post("/api/documents/{did}/files/{fid}/read", dependencies=[access.signed_in])
async def read_file(did: int, fid: int, request: Request, apply: bool = True):
    """Read the file again; apply (as left out): fill in the document where it says nothing yet.
    {file, found, source, filled, differs}: differs is what the scan says otherwise, to take or leave."""
    u = request.state.user
    return await run_in_threadpool(lambda: files.read(u, model.readable(u, did), fid, apply))


@router.patch("/api/documents/{did}/files/{fid}", dependencies=[access.signed_in])
async def change_file(did: int, fid: int, request: Request):
    """{name?, first?: true to put it first (with a picture: the cover)}"""
    u = request.state.user
    b = await json_body(request)
    return await run_in_threadpool(lambda: files.change(u, model.readable(u, did), fid, b))


@router.delete("/api/documents/{did}/files/{fid}", dependencies=[access.signed_in])
def delete_file(did: int, fid: int, request: Request):
    u = request.state.user
    files.remove(u, model.readable(u, did), fid)
    return {"ok": True}


# ---- for ioCalendar and the start page

@router.get("/api/expiring", dependencies=[access.signed_in])
def expiring(request: Request, start: str | None = None, end: str | None = None):
    """{items: [{id, title, kind, kindLabel, expiresOn, people, url}]}: the documents you see (not archived) that
    expire between start and end (YYYY-MM-DD; left out: today to a year from now), soonest first. ioCalendar shows
    them on their days."""
    import datetime as dt
    u = request.state.user
    a = model.day(start, "start") or dt.date.today()
    b = model.day(end, "end") or a + dt.timedelta(days=366)
    if (b - a).days > 3700:
        b = a + dt.timedelta(days=3700)
    where, args = model.visible_sql(u)
    rows = model.db.q(f"SELECT d.* FROM doc_documents d WHERE {where} AND d.archived = 0 AND d.expires_on BETWEEN %s AND %s "
                      f"ORDER BY d.expires_on, d.title", [*args, a, b])
    keep = ("id", "title", "kind", "kindLabel", "expiresOn", "expiry", "people")
    return {"items": [{k: v for k, v in x.items() if k in keep} for x in model.listed(u, rows)]}
