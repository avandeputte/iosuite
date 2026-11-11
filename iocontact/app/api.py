"""The REST API (JSON; vCard and jCard by content negotiation). OpenAPI docs at /api/docs. Who may call a route is declared on
it (app/access.py); what an account may change is an address book's business (app/model.py), checked in the route.

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`.
"""
import datetime as dt
import json
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from iosuite_shared import users as shared_users
from iosuite_shared.access import json_body

from app import access, calendar, config, csvio, db, enrich, iopix, limits, model, quality, relations as rel, users, vcard
from app.auth import auth
from app.fold import fold

router = APIRouter()

VCARD_TYPES = ("text/vcard", "text/x-vcard", "text/directory")
JCARD_TYPE = "application/vcard+json"


# ------------------------------------------------------------------ helpers

def readable_book(u: dict, bid) -> dict:
    b = model.book(int(bid)) if str(bid).isdigit() else None
    if not model.can_read_book(u, b):
        raise HTTPException(404, "No such address book")
    return b


def writable_book(u: dict, bid) -> dict:
    b = readable_book(u, bid)
    if not model.can_write_book(u, b):
        raise HTTPException(403, "You can see this address book but not change it")
    return b


def readable_contact(u: dict, cid: int) -> dict:
    r = model.get_row(cid)
    if not r or r["deleted"] or not model.can_read_book(u, model.book(r["address_book_id"])):
        raise HTTPException(404, "No such contact")
    return r


def book_ids(u: dict, book: str | None = None) -> list[int]:
    if book and book != "all":
        return [readable_book(u, book)["id"]]
    return [b["id"] for b in model.books_for(u)]


def wants(request: Request, fmt: str | None) -> str:
    if fmt:
        return {"vcf": "vcard", "vcard": "vcard", "vcard4": "vcard4", "vcf4": "vcard4", "jcard": "jcard", "json": "json"}.get(fmt, "json")
    acc = request.headers.get("accept", "")
    if JCARD_TYPE in acc:
        return "jcard"
    if any(t in acc for t in VCARD_TYPES):
        return "vcard4" if re.search(r"version\s*=\s*\"?4", acc) else "vcard"
    return "json"


def vcard_response(text: str, version: str, filename: str | None = None) -> Response:
    h = {"Content-Disposition": f'attachment; filename="{filename}"'} if filename else {}
    return Response(text, media_type=f"text/vcard; charset=utf-8; version={version}", headers=h)


def contact_out(c: dict) -> dict:
    c = dict(c)
    c.pop("photoData", None)
    if c.get("iopix"):
        c["iopix"]["url"] = iopix.person_url(c["iopix"]["personId"])
    for s in c.get("social") or []:
        s["url"] = vcard.social_url(s["service"], s["value"])
    return c


async def body_contact(request: Request) -> dict:
    ct = request.headers.get("content-type", "").split(";")[0].strip().lower()
    raw = await limits.body(request)
    if ct in VCARD_TYPES:
        cards = vcard.parse(raw.decode("utf-8", "replace"))
        if not cards:
            raise HTTPException(400, "No vCard in the body")
        return cards[0]
    try:
        data = json.loads(raw or b"{}")
    except ValueError:
        raise HTTPException(400, "Expected JSON, a vCard or a jCard")
    if ct == JCARD_TYPE or (isinstance(data, list) and data[:1] == ["vcard"]):
        try:
            return vcard.from_jcard(data)
        except (ValueError, TypeError) as e:
            raise HTTPException(400, f"Bad jCard: {e}")
    if not isinstance(data, dict):
        raise HTTPException(400, "Expected a contact object")
    data.pop("photo", None)  # contacts keep no photo: the linked ioPix person is the photo
    return data


# ------------------------------------------------------------------ the account's own fields
# Sign-in, accounts, sessions, passwords, app passwords and the users admin are iosuite-shared's routes (app/main.py);
# what is ioContacts' own: the face on an account's tile, and which contact an account is ("me").

@router.get("/api/auth/accounts/{uid}/photo", dependencies=[access.public])
async def account_photo(uid: int, request: Request):
    """The face on an account's tile: the ioPix face of the account's "me" contact. Public because the sign-in screen
    shows it, and like the tiles themselves (/api/auth/accounts) it is for the network the server is on: from outside,
    only a signed-in account gets it."""
    if auth.outside(request) and not auth.current_user(request):
        raise HTTPException(404)
    u = await run_in_threadpool(users.get, uid)
    cid = u.get("me_contact_id") if u and u["role"] != "none" else None
    p = await run_in_threadpool(model.photo, cid) if cid else None
    if not p:
        raise HTTPException(404)
    return Response(p[0], media_type=p[1], headers={"Cache-Control": "private, max-age=300"})


@router.put("/api/me-contact", dependencies=[access.signed_in])
async def put_me_contact(request: Request):
    """Which contact is the signed-in account ({contactId}; null: none), for CardDAV apps and the face on its tile.
    The display name and email are iosuite-shared's (PATCH /api/auth/me, Settings › Account)."""
    u = auth.current_user(request)
    cid = (await json_body(request)).get("contactId")
    if cid:
        readable_contact(u, int(cid))
    return {"user": users.public(users.update(u["id"], me_contact_id=int(cid) if cid else None))}


# ------------------------------------------------------------------ address books

@router.get("/api/books", dependencies=[access.signed_in])
def list_books(request: Request):
    u = auth.current_user(request)
    return {"items": [model.book_public(b, u) for b in model.books_for(u)]}


@router.post("/api/books", dependencies=[access.signed_in])
async def add_book(request: Request):
    u = auth.current_user(request)
    b = await json_body(request)
    shared = bool(b.get("shared"))
    if shared and not shared_users.can_write(u):
        raise HTTPException(403, "Only editors make shared address books")
    if not shared and not shared_users.is_member(u):
        raise HTTPException(403, "A viewer only looks; a member keeps address books of their own")
    bid = model.create_book(None if shared else u["id"], b.get("name"), b.get("description"), b.get("color"))
    return {"book": model.book_public(model.book(bid), u)}


@router.patch("/api/books/{bid}", dependencies=[access.signed_in])
async def edit_book(bid: int, request: Request):
    u = auth.current_user(request)
    writable_book(u, bid)
    b = await json_body(request)
    model.update_book(bid, **{k: b[k] for k in ("name", "description", "color") if k in b})
    return {"book": model.book_public(model.book(bid), u)}


@router.delete("/api/books/{bid}", dependencies=[access.signed_in])
def del_book(bid: int, request: Request):
    u = auth.current_user(request)
    b = writable_book(u, bid)
    if b["owner_id"] is None and not shared_users.is_admin(u):
        raise HTTPException(403, "Only an admin deletes a shared address book")
    if b["owner_id"] is None and len([x for x in model.books_for(u) if x["owner_id"] is None]) <= 1:
        raise HTTPException(400, "The last shared address book stays")
    model.delete_book(bid)
    return {"ok": True}


# ------------------------------------------------------------------ contacts

@router.get("/api/contacts", dependencies=[access.signed_in])
def list_contacts(request: Request, q: str = "", book: str | None = None, tag: str | None = None, favorite: bool = False,
                  limit: int = 5000, offset: int = 0, order: str = "given", format: str | None = None, iopix_linked: bool = False):
    u = auth.current_user(request)
    ids = book_ids(u, book)
    items, total = model.search(ids, q, tag, favorite, max(1, min(limit, 20000)), max(0, offset), order,
                                True if iopix_linked else None)
    fmt = wants(request, format)
    if fmt in ("vcard", "vcard4"):
        v = "4.0" if fmt == "vcard4" else "3.0"
        return vcard_response("".join(model.vcard_text(c["id"], v, c) for c in model.load([x["id"] for x in items], with_photo=True)), v)
    if fmt == "jcard":
        return JSONResponse([vcard.to_jcard(c) for c in model.load([x["id"] for x in items])], media_type=JCARD_TYPE)
    return {"total": total, "items": items}


@router.get("/api/contacts/{cid}", dependencies=[access.signed_in])
def get_contact(cid: int, request: Request, format: str | None = None):
    u = auth.current_user(request)
    readable_contact(u, cid)
    fmt = wants(request, format)
    if fmt in ("vcard", "vcard4"):
        v = "4.0" if fmt == "vcard4" else "3.0"
        c = model.full(cid)
        return vcard_response(model.vcard_text(cid, v), v, f"{re.sub(r'[^A-Za-z0-9 _-]', '', c['fn']) or 'contact'}.vcf")
    if fmt == "jcard":
        return JSONResponse(vcard.to_jcard(model.full(cid, with_photo=True)), media_type=JCARD_TYPE)
    return {**contact_out(model.full(cid)), "impliedRelations": model.implied_relations(cid, book_ids(u))}


@router.post("/api/contacts", dependencies=[access.signed_in])
async def create_contact(request: Request, book: str | None = None):
    u = auth.current_user(request)
    data = await body_contact(request)
    bid = book or data.get("bookId") or next((b["id"] for b in model.books_for(u) if model.can_write_book(u, b)), None)
    b = writable_book(u, bid)
    cid = await run_in_threadpool(model.save, b["id"], data, None, None, book_ids(u))
    return JSONResponse(contact_out(model.full(cid)), status_code=201, headers={"Location": f"/api/contacts/{cid}"})


@router.put("/api/contacts/{cid}", dependencies=[access.signed_in])
async def update_contact(cid: int, request: Request):
    u = auth.current_user(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    data = await body_contact(request)
    inm = request.headers.get("if-match")
    if inm and inm.strip('"') != r["etag"]:
        raise HTTPException(412, "The contact changed since you loaded it")
    target = data.get("bookId") or r["address_book_id"]
    if int(target) != r["address_book_id"]:
        writable_book(u, target)
    await run_in_threadpool(model.save, int(target), data, cid, None, book_ids(u))
    return contact_out(model.full(cid))


@router.patch("/api/contacts/{cid}", dependencies=[access.signed_in])
async def patch_contact(cid: int, request: Request):
    """Only some fields, e.g. {"favorite": true} or {"iopix": {"personId": 12, "name": "Ann"}}."""
    u = auth.current_user(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    b = await json_body(request)
    c = model.full(cid)
    c.update({k: v for k, v in b.items() if k not in ("id", "uid", "href", "etag", "photo")})
    dest = int(c.get("bookId") or r["address_book_id"])
    if dest != r["address_book_id"]:
        writable_book(u, dest)  # moving it needs the right to change the other book too
    await run_in_threadpool(model.save, dest, c, cid, None, book_ids(u))
    return contact_out(model.full(cid))


@router.delete("/api/contacts/{cid}", dependencies=[access.signed_in])
def delete_contact(cid: int, request: Request):
    u = auth.current_user(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    model.delete(cid)
    return {"ok": True}


@router.post("/api/contacts/bulk", dependencies=[access.signed_in])
async def bulk(request: Request):
    """{ids: [...], action: delete | favorite | unfavorite | move | tag | untag, book?, tag?}"""
    u = auth.current_user(request)
    b = await json_body(request)
    ids, action = [int(x) for x in b.get("ids") or []], b.get("action")
    for cid in ids:
        r = readable_contact(u, cid)
        writable_book(u, r["address_book_id"])
    if action == "move":
        writable_book(u, b.get("book"))

    def run():
        for cid in ids:
            if action == "delete":
                model.delete(cid)
            elif action in ("favorite", "unfavorite"):
                model.set_fields(cid, favorite=1 if action == "favorite" else 0)
            elif action == "move":
                model.move(cid, int(b["book"]))
            elif action in ("tag", "untag") and (b.get("tag") or "").strip():
                c = model.full(cid)
                tags = set(c["tags"])
                (tags.add if action == "tag" else tags.discard)(b["tag"].strip())
                model.save(c["bookId"], {**c, "tags": sorted(tags)}, cid, None, book_ids(u))
    await run_in_threadpool(run)
    return {"ok": True, "n": len(ids)}


@router.get("/api/contacts/{cid}/photo", dependencies=[access.signed_in])
def get_photo(cid: int, request: Request):
    """The contact's photo: the face of the ioPix person it is linked to (contacts keep no photo of their own)."""
    readable_contact(auth.current_user(request), cid)
    p = model.photo(cid)
    if not p:
        raise HTTPException(404)
    return Response(p[0], media_type=p[1], headers={"Cache-Control": "private, max-age=60"})


@router.post("/api/contacts/merge", dependencies=[access.signed_in])
async def merge(request: Request):
    """{keep, others, result?}: fold the others into keep. result is the contact as it should end up (fields
    chosen one by one, as /api/merge/preview offers them); without it, everything is combined. Undo: /api/merges."""
    u = auth.current_user(request)
    b = await json_body(request)
    if not isinstance(b.get("keep"), int) or not isinstance(b.get("others") or [], list):
        raise HTTPException(400, "keep is the id of the contact to keep, others the ids of the ones to merge into it")
    keep, others = b["keep"], [int(x) for x in b.get("others") or [] if int(x) != b["keep"]]
    if not others:
        raise HTTPException(400, "Name the contacts to merge into the kept one")
    for cid in [keep, *others]:
        r = readable_contact(u, cid)
        writable_book(u, r["address_book_id"])
    result = b.get("result") if isinstance(b.get("result"), dict) else None
    mid = await run_in_threadpool(quality.merge, u, keep, others, result)
    return {**contact_out(model.full(keep)), "mergeId": mid}


@router.get("/api/merge/preview", dependencies=[access.signed_in])
def merge_preview(request: Request, ids: str, keep: int | None = None):
    """What merging these contacts gives, and the fields where they disagree (to choose from)."""
    u = auth.current_user(request)
    want = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    if len(want) < 2:
        raise HTTPException(400, "At least two contacts")
    for cid in want:
        readable_contact(u, cid)
    keep = keep if keep in want else want[0]
    out = quality.preview(want, keep)
    out["contacts"] = [contact_out(c) for c in out["contacts"]]
    if len(want) == 2:
        out["compare"] = quality.compare(want[0], want[1])
    return out


@router.get("/api/duplicates", dependencies=[access.signed_in])
def duplicates(request: Request, book: str | None = None, min_score: int = 35):
    """Probable duplicates, grouped, most certain first, each pair with a score and the reasons."""
    return {"groups": quality.find(book_ids(auth.current_user(request), book), max(10, min(min_score, 100)))}


@router.post("/api/duplicates/dismiss", dependencies=[access.admin])
async def duplicates_dismiss(request: Request):
    """{ids: [...]}: these contacts are different people; they are not offered as duplicates again."""
    u = auth.current_user(request)
    ids = [int(x) for x in (await json_body(request)).get("ids") or []]
    for cid in ids:
        writable_book(u, readable_contact(u, cid)["address_book_id"])
    return {"ok": True, "pairs": quality.not_duplicates(ids, u["id"])}


@router.delete("/api/duplicates/dismissed", dependencies=[access.admin])
def duplicates_forget(request: Request):
    """Admins: offer every pair marked "not duplicates" again."""
    auth.current_user(request)
    return {"ok": True, "forgotten": quality.forget_not_duplicates()}


@router.get("/api/merges", dependencies=[access.signed_in])
def merges(request: Request, limit: int = 50):
    """Recent merges, newest first, with whether each can still be undone."""
    return {"items": quality.history(book_ids(auth.current_user(request)), max(1, min(limit, 200)))}


@router.post("/api/merges/{mid}/undo", dependencies=[access.signed_in])
async def merge_undo(mid: int, request: Request):
    u = auth.current_user(request)
    m = db.one("SELECT kept_contact_id FROM con_contact_merges WHERE id = %s", (mid,))
    if not m:
        raise HTTPException(404, "No such merge")
    r = readable_contact(u, m["kept_contact_id"])
    writable_book(u, r["address_book_id"])
    try:
        return await run_in_threadpool(quality.undo, mid)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ------------------------------------------------------------------ enrichment (suggestions that wait for a person)

@router.post("/api/contacts/{cid}/lookup", dependencies=[access.signed_in])
async def contact_lookup(cid: int, request: Request):
    """Look this contact up (Gravatar by email, and its GitHub, Mastodon and Bluesky profiles); what is found waits as
    suggestions."""
    u = auth.current_user(request)
    writable_book(u, readable_contact(u, cid)["address_book_id"])
    return await run_in_threadpool(enrich.lookup, cid, u["id"])


@router.post("/api/lookup", dependencies=[access.signed_in])
async def lookup_many(request: Request):
    """{ids?: [...], book?, offset?, limit?}: look several contacts up (25 at a time; call again with the next offset)."""
    u = auth.current_user(request)
    b = await json_body(request)
    if b.get("ids"):
        ids = [int(x) for x in b["ids"]]
        for cid in ids:
            writable_book(u, readable_contact(u, cid)["address_book_id"])
        total = len(ids)
    else:
        mine = [x for x in book_ids(u, b.get("book")) if model.can_write_book(u, model.book(x))]
        items, total = model.search(mine, limit=max(1, min(int(b.get("limit") or 25), 50)), offset=max(0, int(b.get("offset") or 0)))
        ids = [x["id"] for x in items]

    def run():
        return [enrich.lookup(cid, u["id"]) for cid in ids]
    res = await run_in_threadpool(run)
    return {"total": total, "done": len(res), "added": sum(r["added"] for r in res), "results": res}


@router.get("/api/suggestions", dependencies=[access.signed_in])
def suggestions(request: Request, status: str = "pending", contact: int | None = None, book: str | None = None):
    u = auth.current_user(request)
    if status not in ("pending", "accepted", "dismissed"):
        raise HTTPException(400, "status: pending, accepted or dismissed")
    return {"items": enrich.listing(book_ids(u, book), status, contact)}


@router.post("/api/suggestions/{sid}/accept", dependencies=[access.signed_in])
async def suggestion_accept(sid: int, request: Request):
    """Apply a suggestion to its contact. Body (optional): {value} to apply an edited version."""
    u = auth.current_user(request)
    s = enrich.suggestion(sid)
    if not s:
        raise HTTPException(404, "No such suggestion")
    writable_book(u, readable_contact(u, s["contact_id"])["address_book_id"])
    raw = await request.body()
    b = json.loads(raw) if raw else {}
    try:
        return await run_in_threadpool(enrich.accept, sid, u["id"], book_ids(u), b.get("value"))
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(400, str(e))


@router.post("/api/suggestions/{sid}/dismiss", dependencies=[access.signed_in])
def suggestion_dismiss(sid: int, request: Request):
    u = auth.current_user(request)
    s = enrich.suggestion(sid)
    if not s:
        raise HTTPException(404, "No such suggestion")
    writable_book(u, readable_contact(u, s["contact_id"])["address_book_id"])
    enrich.dismiss(sid, u["id"])
    return {"ok": True}


@router.get("/api/quality", dependencies=[access.signed_in])
def data_quality(request: Request, book: str | None = None, check: str | None = None):
    """The data quality checks: [{check, title, severity: problem | tidy | info, fix, count, items}]."""
    return {"checks": quality.run_checks(book_ids(auth.current_user(request), book), check)}


@router.post("/api/quality/fix", dependencies=[access.signed_in])
async def data_quality_fix(request: Request):
    """{check, ids?, countryCode?, book?}: fix a check's findings (all, or these contacts) where you may change them."""
    u = auth.current_user(request)
    b = await json_body(request)
    ids = [int(x) for x in b["ids"]] if b.get("ids") else None
    try:
        return await run_in_threadpool(quality.fix, u, str(b.get("check")), ids, book_ids(u, b.get("book")), b.get("countryCode"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/tags", dependencies=[access.signed_in])
def tags(request: Request, book: str | None = None):
    return {"items": model.all_tags(book_ids(auth.current_user(request), book))}


@router.get("/api/relation-types", dependencies=[access.signed_in])
def relation_types():
    return rel.catalog()


@router.get("/api/social-services", dependencies=[access.signed_in])
def social_services():
    return {"items": [{"service": k, "name": v[0], "base": vcard.SOCIAL_BASE.get(k)} for k, v in vcard.SOCIAL_SERVICES.items()]}


@router.get("/api/upcoming", dependencies=[access.signed_in])
def upcoming(request: Request, days: int = 30, book: str | None = None):
    return {"items": model.upcoming(book_ids(auth.current_user(request), book), max(1, min(days, 366)))}


@router.get("/api/contacts/{cid}/family", dependencies=[access.signed_in])
def family(cid: int, request: Request, depth: int = 3):
    """The relation graph around a contact: {nodes: [{id, fn, given, family, gender, hasPhoto, iopixPersonId, birthday}], edges: [{from, to, type}]}."""
    u = auth.current_user(request)
    readable_contact(u, cid)
    return family_graph(cid, book_ids(u), depth)


def family_graph(cid: int, allowed_ids: list[int], depth: int = 3) -> dict:
    allowed = set(allowed_ids)
    seen, frontier, edges = {cid}, [cid], []
    for _ in range(max(1, min(depth, 6))):
        if not frontier:
            break
        marks = ",".join(["%s"] * len(frontier))
        rows = db.q(f"SELECT r.contact_id, r.related_id, r.type, o.address_book_id FROM con_contact_relations r JOIN con_contacts o ON o.id = r.related_id "
                    f"WHERE r.contact_id IN ({marks}) AND o.deleted = 0", frontier)
        nxt = []
        for r in rows:
            if r["address_book_id"] not in allowed:
                continue
            edges.append({"from": r["contact_id"], "to": r["related_id"], "type": r["type"]})
            if r["related_id"] not in seen:
                seen.add(r["related_id"])
                nxt.append(r["related_id"])
        frontier = nxt
    # what the family implies for the root (parent's sibling: aunt) is drawn too, so the tree reads "Aunt", not "Sister of Mom"
    for x in model.implied_relations(cid, allowed_ids):
        edges.append({"from": cid, "to": x["relatedId"], "type": x["type"], "implied": True})
        seen.add(x["relatedId"])
    marks = ",".join(["%s"] * len(seen))
    nodes = [{"id": r["id"], "fn": r["fn"], "given": r["given"], "family": r["family"], "gender": r["gender"], "hasPhoto": bool(r["hp"]),
              "iopixPersonId": r["iopix_person_id"], "birthday": model._bday(r)}
             for r in db.q(f"SELECT id, fn, given, family, gender, iopix_person_id IS NOT NULL AS hp, iopix_person_id, bday_year, bday_month, bday_day "
                           f"FROM con_contacts WHERE id IN ({marks})", list(seen))]
    uniq = {(e["from"], e["to"], e["type"]): e for e in edges}
    return {"root": cid, "nodes": nodes, "edges": list(uniq.values())}


# ------------------------------------------------------------------ import / export

@router.post("/api/import", dependencies=[access.signed_in])
async def import_file(request: Request, file: UploadFile = File(...), book: str = Form(...), mode: str = Form("update")):
    """A .vcf (any number of cards, vCard 2.1/3.0/4.0), a jCard .json, or a Google / Outlook .csv.
    mode: update (a card whose UID is already in the book replaces it) or skip (keeps the existing one)."""
    u = auth.current_user(request)
    b = writable_book(u, book)
    data = await file.read(limits.MAX_IMPORT + 1)
    if len(data) > limits.MAX_IMPORT:
        raise limits.too_big(limits.MAX_IMPORT)
    raw = data.decode("utf-8-sig", "replace")
    try:
        cards = parse_cards(raw, file.filename or "")
    except (ValueError, KeyError, IndexError) as e:
        raise HTTPException(400, f"Could not read the file: {e}")
    return await run_in_threadpool(import_cards, u, b, cards, mode)


def parse_cards(raw: str, name: str = "") -> list[dict]:
    """Contacts from a vCard file (2.1/3.0/4.0), a jCard (one or a list) or a Google / Outlook CSV."""
    name = name.lower()
    raw = raw.lstrip("\ufeff")
    if name.endswith(".csv") or (not raw.lstrip().upper().startswith("BEGIN:VCARD") and "," in raw.split("\n", 1)[0] and not raw.lstrip().startswith("[")):
        return csvio.parse(raw)
    if raw.lstrip().startswith("["):
        j = json.loads(raw)
        return [vcard.from_jcard(x) for x in (j if j and isinstance(j[0], list) and j[0] and j[0][0] == "vcard" else [j])]
    return vcard.parse(raw)


def import_cards(u: dict, b: dict, cards: list[dict], mode: str = "update") -> dict:
    """Save cards into book b. mode: update (a card whose UID is already in the book replaces it) or skip."""
    made = updated = skipped = 0
    ids = book_ids(u)
    for c in cards:
        existing = model.by_uid(b["id"], c["uid"]) if c.get("uid") else None
        if not existing and not c.get("uid"):
            em = next((e["value"] for e in c.get("emails") or []), None)
            if em:
                existing = db.one("SELECT c.* FROM con_contacts c JOIN con_contact_emails e ON e.contact_id = c.id WHERE c.address_book_id = %s "
                                  "AND c.deleted = 0 AND e.value = %s AND c.fn = %s LIMIT 1", (b["id"], em, model.display_name(c)))
        if existing and mode == "skip":
            skipped += 1
            continue
        if c.get("iopix") is None:
            c.pop("iopix", None)
        model.save(b["id"], c, existing["id"] if existing else None, None, ids)
        if existing:
            updated += 1
        else:
            made += 1
    return {"created": made, "updated": updated, "skipped": skipped, "read": len(cards)}


@router.get("/api/export", dependencies=[access.signed_in])
def export(request: Request, book: str | None = None, format: str = "vcf", ids: str = ""):
    u = auth.current_user(request)
    bids = book_ids(u, book)
    if ids:
        want = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        sel = [c["id"] for c in model.load(want) if c["bookId"] in bids]
    else:
        sel = [x["id"] for x in model.search(bids, limit=100000)[0]]
    stamp = dt.date.today().isoformat()
    text, mtype, ext = export_text(sel, format)
    name = f"iocontacts-{stamp}{'-' + format.replace('csv-', '') if format.startswith('csv') else ''}.{ext}"
    return Response(text, media_type=mtype, headers={"Content-Disposition": f'attachment; filename="{name}"'})


EXPORT_FORMATS = ("vcf", "vcf4", "jcard", "csv-google", "csv-outlook")


def export_text(ids: list[int], format: str = "vcf") -> tuple[str, str, str]:
    """(text, media type, file extension) of these contacts in one of EXPORT_FORMATS."""
    if format in ("vcf", "vcf4"):
        v = "4.0" if format == "vcf4" else "3.0"
        return "".join(model.vcard_text(c["id"], v, c) for c in model.load(ids, with_photo=True)), f"text/vcard; charset=utf-8; version={v}", "vcf"
    if format == "jcard":
        return json.dumps([vcard.to_jcard(c) for c in model.load(ids, with_photo=True)], ensure_ascii=False), JCARD_TYPE, "json"
    full = model.load(ids)
    text = csvio.export_outlook(full) if format == "csv-outlook" else csvio.export_google(full)
    return "\ufeff" + text, "text/csv; charset=utf-8", "csv"


# ------------------------------------------------------------------ calendar and connection details

def _base(request: Request) -> str:
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


@router.get("/api/connect", dependencies=[access.signed_in])
def connect_info(request: Request):
    """What to type into a mail, contacts or calendar app."""
    u = auth.current_user(request)
    base = _base(request)
    tok = users.calendar_token(u["id"])
    host = re.sub(r"^https?://", "", base).split("/")[0].split(":")[0]
    return {"user": u["name"], "server": base, "carddav": f"{base}/dav/", "principal": f"{base}/dav/principals/{u['name']}/",
            "books": [{"name": b["name"], "url": f"{base}/dav/addressbooks/{u['name']}/{b['slug']}/"} for b in model.books_for(u)],
            "ldap": {"enabled": config.LDAP_PORT > 0, "host": host, "port": config.LDAP_PORT, "base": config.LDAP_BASE,
                     "bindDn": f"cn={u['name']},ou=users,{config.LDAP_BASE}"},
            "calendar": {"family": f"{base}/cal/{tok}/family.ics", "all": f"{base}/cal/{tok}/all.ics",
                         "webcalFamily": re.sub(r"^https?://", "webcal://", f"{base}/cal/{tok}/family.ics")},
            "api": f"{base}/api/docs"}


def _apple_profile(request: Request, label: str, password: str, calendar: str, ldap: bool) -> tuple:
    """(bytes, file name) of a configuration profile (.mobileconfig) that sets an iPhone, iPad or Mac up in one go: the CardDAV account for the
    contacts and, if asked, the birthday calendar subscription (and the LDAP directory). password: "new" puts a new app
    password (named after label) in the profile; "ask" leaves it out, and the device asks for it while installing."""
    import plistlib
    import uuid
    from urllib.parse import urlsplit
    u = auth.current_user(request)
    base = _base(request)
    parts = urlsplit(base)
    ssl = parts.scheme == "https"
    host = parts.hostname or "localhost"
    port = parts.port or (443 if ssl else 80)
    label = (label or "iPhone").strip()[:48] or "iPhone"
    # the profile's password is for CardDAV and LDAP only: a lost phone or a leaked profile file does not reach the web app, API or MCP
    secret = users.create_app_password(u["id"], f"{label} (profile)", protocols_only=True) if password == "new" else None
    ident = "net.iothing.iocontacts." + re.sub(r"[^A-Za-z0-9.-]", "-", host) + "." + re.sub(r"[^A-Za-z0-9-]", "-", u["name"])
    who = u.get("display_name") or u["name"]
    carddav = {"PayloadType": "com.apple.carddav.account", "PayloadVersion": 1, "PayloadIdentifier": ident + ".carddav",
               "PayloadUUID": str(uuid.uuid4()).upper(), "PayloadDisplayName": "Contacts (CardDAV)",
               "CardDAVAccountDescription": "ioContacts", "CardDAVHostName": host, "CardDAVPort": port, "CardDAVUseSSL": ssl,
               "CardDAVPrincipalURL": f"{parts.path.rstrip('/')}/dav/principals/{u['name']}/", "CardDAVUsername": u["name"]}
    if secret:
        carddav["CardDAVPassword"] = secret
    content = [carddav]
    if calendar in ("family", "all"):
        tok = users.calendar_token(u["id"])
        content.append({"PayloadType": "com.apple.subscribedcalendar.account", "PayloadVersion": 1,
                        "PayloadIdentifier": ident + ".birthdays", "PayloadUUID": str(uuid.uuid4()).upper(),
                        "PayloadDisplayName": "Birthday calendar",
                        "SubCalAccountDescription": "Family birthdays" if calendar == "family" else "Birthdays",
                        "SubCalAccountHostName": f"{base}/cal/{tok}/{calendar}.ics", "SubCalAccountUseSSL": ssl})
    if ldap and config.LDAP_PORT:
        lp = {"PayloadType": "com.apple.ldap.account", "PayloadVersion": 1, "PayloadIdentifier": ident + ".ldap",
              "PayloadUUID": str(uuid.uuid4()).upper(), "PayloadDisplayName": "Directory (LDAP)",
              "LDAPAccountDescription": "ioContacts directory", "LDAPAccountHostName": f"{host}:{config.LDAP_PORT}",
              "LDAPAccountUseSSL": False, "LDAPAccountUserName": f"cn={u['name']},ou=users,{config.LDAP_BASE}",
              "LDAPSearchSettings": [{"LDAPSearchSettingDescription": "Contacts", "LDAPSearchSettingSearchBase": config.LDAP_BASE,
                                      "LDAPSearchSettingScope": "LDAPSearchSettingScopeSubtree"}]}
        if secret:
            lp["LDAPAccountPassword"] = secret
        content.append(lp)
    profile = {"PayloadType": "Configuration", "PayloadVersion": 1, "PayloadIdentifier": ident,
               "PayloadUUID": str(uuid.uuid4()).upper(), "PayloadDisplayName": f"ioContacts for {who}",
               "PayloadDescription": f"Sets up {who}'s ioContacts contacts" + (" and the birthday calendar" if len(content) > 1 else "")
                                     + f" from {host}." + ("" if secret else " The device asks for an app password while installing."),
               "PayloadOrganization": "ioContacts", "PayloadRemovalDisallowed": False, "PayloadContent": content}
    return plistlib.dumps(profile), f'iocontacts-{re.sub(r"[^A-Za-z0-9-]", "-", u["name"])}.mobileconfig'


def _profile_response(body: bytes, name: str) -> Response:
    return Response(body, media_type="application/x-apple-aspen-config",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


@router.post("/api/apple-profile", dependencies=[access.signed_in])
def apple_profile(request: Request, label: str = Form("iPhone"), password: str = Form("new"), calendar: str = Form("family"),
                  ldap: bool = Form(False)):
    """The profile itself, as the answer to a form post (a browser tab that downloads in place: Safari, a Mac)."""
    return _profile_response(*_apple_profile(request, label, password, calendar, ldap))


PROFILE_LINK_SECONDS = 600
_profile_links: dict = {}  # token -> (expires, bytes, file name): a few minutes, in this process


@router.post("/api/apple-profile/link", dependencies=[access.signed_in])
async def apple_profile_link(request: Request):
    """{label, password, calendar, ldap} -> {url}: the profile behind a short-lived download link (/profile/<token>)
    that needs no cookie. The app on the Home Screen hands a download to a separate browser sheet that has none of its
    cookies, so a form post answers that sheet "Sign in"; a link it can open by itself works. The link may be opened
    more than once in its few minutes and always gives the same profile, with one app password."""
    import secrets
    import time
    b = await json_body(request)
    body, name = await run_in_threadpool(_apple_profile, request, str(b.get("label") or ""), str(b.get("password") or "new"),
                                         str(b.get("calendar") or "family"), bool(b.get("ldap")))
    now = time.monotonic()
    for t in [t for t, v in _profile_links.items() if v[0] < now]:
        _profile_links.pop(t, None)
    token = secrets.token_urlsafe(24)
    _profile_links[token] = (now + PROFILE_LINK_SECONDS, body, name)
    return {"url": f"/profile/{token}/{name}", "expiresIn": PROFILE_LINK_SECONDS}


@router.get("/profile/{token}/{name}", include_in_schema=False)
def apple_profile_download(token: str, name: str):
    import time
    hit = _profile_links.get(token)
    if not hit or hit[0] < time.monotonic():
        _profile_links.pop(token, None)
        return Response("This download link has expired. Make a new one in ioContacts: Settings › Apps and devices.",
                        status_code=404, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store"})
    return _profile_response(hit[1], hit[2])


@router.post("/api/calendar/reset", dependencies=[access.signed_in])
def calendar_reset(request: Request):
    users.reset_calendar_token(auth.current_user(request)["id"])
    return {"ok": True}


@router.get("/cal/{token}/{which}.ics", dependencies=[access.public])
def calendar_feed(token: str, which: str, request: Request):
    u = users.user_from_calendar_token(token)
    if not u:
        raise HTTPException(404)
    books = model.books_for(u)
    if which == "family":
        ids, title = [b["id"] for b in books if b["owner_id"] is None], "Family birthdays"
    else:
        ids, title = [b["id"] for b in books], "Birthdays"
    return Response(calendar.feed(ids, title, _base(request)), media_type="text/calendar; charset=utf-8")


# ------------------------------------------------------------------ ioPix

@router.get("/api/iopix/people", dependencies=[access.signed_in])
async def iopix_people(request: Request, q: str = "", refresh: bool = False):
    u = auth.current_user(request)
    try:
        ppl = await run_in_threadpool(iopix.people, refresh)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"ioPix did not answer: {type(e).__name__}: {e}")
    linked = {r["iopix_person_id"]: {"id": r["id"], "fn": r["fn"]} for r in db.q(
        f"SELECT id, fn, iopix_person_id FROM con_contacts WHERE iopix_person_id IS NOT NULL AND deleted = 0 "
        f"AND address_book_id IN ({','.join(['%s'] * max(1, len(book_ids(u))))})", book_ids(u) or [0])}
    ql = fold(q).strip()
    return {"items": [{**p, "contact": linked.get(p["id"])} for p in ppl if not ql or ql in fold(p["name"])]}


@router.get("/api/iopix/face/{pid}", dependencies=[access.signed_in])
async def iopix_face(pid: int, request: Request):
    auth.current_user(request)
    try:
        got = await run_in_threadpool(iopix.face, pid)
    except Exception:  # noqa: BLE001
        raise HTTPException(502)
    if not got:
        raise HTTPException(404)
    return Response(got[0], media_type=got[1], headers={"Cache-Control": "private, max-age=86400"})


@router.post("/api/iopix/auto-link", dependencies=[access.signed_in])
async def iopix_autolink(request: Request, book: str | None = None, dry: bool = True):
    """Contacts whose name matches exactly one ioPix person (and that are not linked yet): listed, or linked with dry=false."""
    u = auth.current_user(request)
    ppl = await run_in_threadpool(iopix.people)
    by_name: dict = {}
    for p in ppl:
        by_name.setdefault(p["name"].strip().lower(), []).append(p)
    taken = {r["iopix_person_id"] for r in db.q("SELECT iopix_person_id FROM con_contacts WHERE iopix_person_id IS NOT NULL AND deleted = 0")}
    found = [c for c in model.search(book_ids(u, book), limit=100000)[0] if not c["iopixPersonId"]]
    same_name: dict = {}
    for c in found:
        same_name[c["fn"].strip().lower()] = same_name.get(c["fn"].strip().lower(), 0) + 1
    out = []
    for c in found:
        name = c["fn"].strip().lower()
        m = by_name.get(name) or []
        if len(m) == 1 and m[0]["id"] not in taken and same_name[name] == 1:  # one person, one contact: two contacts of a name are left to be linked by hand
            r = model.get_row(c["id"])
            if model.can_write_book(u, model.book(r["address_book_id"])):
                out.append({"contactId": c["id"], "fn": c["fn"], "personId": m[0]["id"], "personName": m[0]["name"]})
                taken.add(m[0]["id"])
    if not dry:
        for x in out:
            model.set_fields(x["contactId"], iopix_person_id=x["personId"], iopix_person_name=x["personName"])
    return {"items": out, "linked": 0 if dry else len(out)}
