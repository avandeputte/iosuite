"""The REST API (JSON; vCard and jCard by content negotiation). OpenAPI docs at /api/docs.

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`.
"""
import datetime as dt
import json
import re

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from app import __version__, calendar, config, csvio, db, enrich, iopix, limits, model, quality, relations as rel, users, vcard
from app.auth import auth, updater
from app.fold import fold

router = APIRouter()

VCARD_TYPES = ("text/vcard", "text/x-vcard", "text/directory")
JCARD_TYPE = "application/vcard+json"


# ------------------------------------------------------------------ helpers

def me(request: Request) -> dict:
    u = request.state.user
    if not u:
        raise HTTPException(401, "Sign in first")
    return u


def writer(request: Request) -> dict:
    return me(request)


def admin(request: Request) -> dict:
    u = me(request)
    if not users.is_admin(u):
        raise HTTPException(403, "Admins only")
    return u


def readable_book(u: dict, bid) -> dict:
    b = model.book(int(bid)) if str(bid).isdigit() else None
    if not model.can_read_book(u, b):
        raise HTTPException(404, "No such address book")
    return b


def writable_book(u: dict, bid) -> dict:
    b = readable_book(u, bid)
    if not model.can_write_book(u, b):
        raise HTTPException(403, "Viewers can only change their own private address book")
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
    data.pop("photo", None)  # photos go through /photo
    return data


# ------------------------------------------------------------------ status and sign-in

@router.get("/api/status")
def status(request: Request):
    u = request.state.user
    adm = users.is_admin(u)
    return {"app": "ioContacts", "version": __version__, "commit": updater.local_commit()[:7] if u else None,
            "usersExist": users.any_users(), "user": users.public(u),
            "iopix": bool(iopix.settings()["url"]), "viaProxy": getattr(request.state, "via_proxy", False),
            "mcp": mcp_enabled() if u else None,
            "suggestions": enrich.pending_count(book_ids(u)) if u else None,
            "updateAvailable": updater.available() if adm and updater.auto_check_enabled() else None}


def mcp_enabled() -> bool:
    """Settings › Server › MCP server: off until an admin turns it on (or MCP=1 in the environment)."""
    if config.MCP_FORCED:
        return True
    try:
        return db.get_setting("mcp_enabled", "0") == "1"
    except Exception:  # noqa: BLE001
        return False


def _cookie(resp: Response, request: Request, u: dict) -> None:
    """The suite's session cookie (iosuite-shared): shared by every ioThing app on the domain."""
    auth.sign_in(resp, request, u, "oneclick" if not u.get("pw_hash") else "password")


@router.post("/api/auth/setup")
async def setup(request: Request):
    """The first account (an admin), while there are none."""
    if users.any_users():
        raise HTTPException(409, "There are accounts already")
    b = await request.json()
    try:
        u = await run_in_threadpool(users.create, (b.get("name") or "").strip(), b.get("password") or "", "admin",
                                    b.get("displayName"), b.get("email"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    resp = JSONResponse({"user": users.public(u)})
    _cookie(resp, request, u)
    return resp


def outside(request: Request) -> bool:
    """From outside the home network (through Cloudflare, or a public address)? One-click sign-in is not offered then."""
    from iosuite_shared.fastapi import peer_of
    return auth.proxy.external(request.headers, peer_of(request))


@router.get("/api/auth/accounts")
def accounts(request: Request):
    """The accounts the sign-in screen shows as tiles (as in iopix). One-click accounts are left out from outside."""
    out = users.accounts() if users.any_users() else []
    if outside(request):
        out = [a for a in out if not a["passwordless"]]
    return {"accounts": out}


@router.get("/api/auth/accounts/{uid}/photo")
async def account_photo(uid: int):
    """The face on an account's tile: the photo of the account's "me" contact, or that contact's ioPix face."""
    u = await run_in_threadpool(users.get, uid)
    cid = u.get("me_contact_id") if u and u["role"] != "none" else None
    p = await run_in_threadpool(model.photo, cid) if cid else None
    if not p and cid:
        r = await run_in_threadpool(db.one, "SELECT iopix_person_id FROM con_contacts WHERE id = %s", (cid,))
        if r and r["iopix_person_id"] and iopix.settings()["url"]:
            try:
                p = await run_in_threadpool(iopix.face, r["iopix_person_id"])
            except Exception:  # noqa: BLE001 - no face, then the initial
                p = None
    if not p:
        raise HTTPException(404)
    return Response(p[0], media_type=p[1], headers={"Cache-Control": "private, max-age=300"})


@router.post("/api/auth/login")
async def login(request: Request):
    b = await request.json()
    name, pw = (b.get("name") or "").strip(), b.get("password") or ""
    if pw:
        u = await run_in_threadpool(users.authenticate, name, pw)
    else:  # one click: an account with no password (a viewer), and only from home
        u = await run_in_threadpool(users.find, name)
        if u and not users.passwordless(u):
            u = None
        if u and outside(request):
            raise HTTPException(403, "From outside your network, sign in with an account that has a password")
    if not u:
        raise HTTPException(401, "Wrong name or password")
    if u["role"] == "none":
        raise HTTPException(403, "Your account has no access to ioContacts")
    resp = JSONResponse({"user": users.public(u)})
    _cookie(resp, request, u)
    return resp


@router.post("/api/auth/logout")
def logout(request: Request):
    from iosuite_shared import sessions
    sessions.end(request.cookies.get(users.COOKIE))
    resp = JSONResponse({"ok": True})
    sessions.clear_cookie(resp, sessions.host_of(request))
    return resp


@router.get("/api/auth/me")
def get_me(request: Request):
    return {"user": users.public(me(request))}


@router.get("/api/auth/suite")
def get_suite(request: Request):
    """The suite's registered apps (iosuite-shared ios_apps), this one among them, for the app switcher: when there are
    others, the app mark top left opens a menu of them. Signed in only."""
    me(request)
    from iosuite_shared import suite
    from app.auth import APP
    try:
        items = suite.apps()
    except Exception:  # noqa: BLE001 - the switcher is a convenience: no menu rather than an error
        items = []
    return {"items": items, "app": APP}


@router.patch("/api/auth/me")
async def patch_me(request: Request):
    u = me(request)
    b = await request.json()
    f = {}
    if "displayName" in b:
        f["display_name"] = (b["displayName"] or "").strip() or None
    if "email" in b:
        f["email"] = (b["email"] or "").strip() or None
    if "meContactId" in b:
        cid = b["meContactId"]
        if cid:
            readable_contact(u, int(cid))
        f["me_contact_id"] = int(cid) if cid else None
    return {"user": users.public(users.update(u["id"], **f))}


@router.post("/api/auth/password")
async def change_password(request: Request):
    u = me(request)
    b = await request.json()
    if u.get("pw_hash") and not await run_in_threadpool(users.authenticate, u["name"], b.get("old") or ""):
        raise HTTPException(403, "The current password is wrong")
    try:
        users.update(u["id"], password=b.get("new") or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    users.forget_cached_auth()
    return {"ok": True}


@router.get("/api/app-passwords")
def app_passwords(request: Request):
    return {"items": users.list_app_passwords(me(request)["id"])}


@router.post("/api/app-passwords")
async def new_app_password(request: Request):
    b = await request.json()
    pw = await run_in_threadpool(users.create_app_password, me(request)["id"], (b.get("label") or "Device").strip())
    return {"password": pw, "name": me(request)["name"]}


@router.delete("/api/app-passwords/{pid}")
def del_app_password(pid: int, request: Request):
    users.delete_app_password(me(request)["id"], pid)
    users.forget_cached_auth()
    return {"ok": True}


# ------------------------------------------------------------------ users (admin)

@router.get("/api/users")
def list_users(request: Request):
    admin(request)
    return {"items": [users.public(u) for u in users.all_users()]}


@router.post("/api/users")
async def add_user(request: Request):
    admin(request)
    b = await request.json()
    try:
        u = await run_in_threadpool(users.create, (b.get("name") or "").strip(), b.get("password") or None, b.get("role") or "editor",
                                    b.get("displayName"), b.get("email"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"user": users.public(u)}


@router.patch("/api/users/{uid}")
async def edit_user(uid: int, request: Request):
    a = admin(request)
    b = await request.json()
    if not users.get(uid):
        raise HTTPException(404)
    if uid == a["id"] and b.get("role") and b["role"] != "admin":
        raise HTTPException(400, "You cannot take your own admin role away")
    f = {k2: b[k1] for k1, k2 in (("displayName", "display_name"), ("email", "email"), ("role", "role"), ("password", "password")) if k1 in b}
    try:
        u = await run_in_threadpool(lambda: users.update(uid, **f))
    except ValueError as e:
        raise HTTPException(400, str(e))
    users.forget_cached_auth()
    return {"user": users.public(u)}


@router.delete("/api/users/{uid}")
def del_user(uid: int, request: Request):
    a = admin(request)
    if uid == a["id"]:
        raise HTTPException(400, "You cannot delete your own account")
    users.delete(uid)
    users.forget_cached_auth()
    return {"ok": True}


# ------------------------------------------------------------------ address books

@router.get("/api/books")
def list_books(request: Request):
    u = me(request)
    return {"items": [model.book_public(b, u) for b in model.books_for(u)]}


@router.post("/api/books")
async def add_book(request: Request):
    u = me(request)
    b = await request.json()
    shared = bool(b.get("shared"))
    if shared and not users.can_write(u):
        raise HTTPException(403, "Only editors make shared address books")
    name = (b.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "A name, please")
    bid = model.create_book(None if shared else u["id"], name, b.get("description"), b.get("color"))
    return {"book": model.book_public(model.book(bid), u)}


@router.patch("/api/books/{bid}")
async def edit_book(bid: int, request: Request):
    u = me(request)
    writable_book(u, bid)
    b = await request.json()
    model.update_book(bid, **{k: b[k] for k in ("name", "description", "color") if k in b})
    return {"book": model.book_public(model.book(bid), u)}


@router.delete("/api/books/{bid}")
def del_book(bid: int, request: Request):
    u = me(request)
    b = writable_book(u, bid)
    if b["owner_id"] is None and not users.is_admin(u):
        raise HTTPException(403, "Only an admin deletes a shared address book")
    if b["owner_id"] is None and len([x for x in model.books_for(u) if x["owner_id"] is None]) <= 1:
        raise HTTPException(400, "The last shared address book stays")
    model.delete_book(bid)
    return {"ok": True}


# ------------------------------------------------------------------ contacts

@router.get("/api/contacts")
def list_contacts(request: Request, q: str = "", book: str | None = None, tag: str | None = None, favorite: bool = False,
                  limit: int = 5000, offset: int = 0, order: str = "given", format: str | None = None, iopix_linked: bool = False):
    u = me(request)
    ids = book_ids(u, book)
    items, total = model.search(ids, q, tag, favorite, max(1, min(limit, 20000)), max(0, offset), order,
                                True if iopix_linked else None)
    fmt = wants(request, format)
    if fmt in ("vcard", "vcard4"):
        v = "4.0" if fmt == "vcard4" else "3.0"
        return vcard_response("".join(model.vcard_text(x["id"], v) for x in items), v)
    if fmt == "jcard":
        return JSONResponse([vcard.to_jcard(model.full(x["id"], with_photo=False)) for x in items], media_type=JCARD_TYPE)
    return {"total": total, "items": items}


@router.get("/api/contacts/{cid}")
def get_contact(cid: int, request: Request, format: str | None = None):
    u = me(request)
    readable_contact(u, cid)
    fmt = wants(request, format)
    if fmt in ("vcard", "vcard4"):
        v = "4.0" if fmt == "vcard4" else "3.0"
        c = model.full(cid)
        return vcard_response(model.vcard_text(cid, v), v, f"{re.sub(r'[^A-Za-z0-9 _-]', '', c['fn']) or 'contact'}.vcf")
    if fmt == "jcard":
        return JSONResponse(vcard.to_jcard(model.full(cid, with_photo=True)), media_type=JCARD_TYPE)
    return {**contact_out(model.full(cid)), "impliedRelations": model.implied_relations(cid, book_ids(u))}


@router.post("/api/contacts")
async def create_contact(request: Request, book: str | None = None):
    u = writer(request)
    data = await body_contact(request)
    bid = book or data.get("bookId") or next((b["id"] for b in model.books_for(u) if model.can_write_book(u, b)), None)
    b = writable_book(u, bid)
    photo = data.pop("photo", None) if isinstance(data.get("photo"), dict) and data["photo"].get("data") else None
    cid = await run_in_threadpool(model.save, b["id"], {**data, **({"photo": photo} if photo else {})}, None, None, True, book_ids(u))
    return JSONResponse(contact_out(model.full(cid)), status_code=201, headers={"Location": f"/api/contacts/{cid}"})


@router.put("/api/contacts/{cid}")
async def update_contact(cid: int, request: Request):
    u = writer(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    data = await body_contact(request)
    inm = request.headers.get("if-match")
    if inm and inm.strip('"') != r["etag"]:
        raise HTTPException(412, "The contact changed since you loaded it")
    target = data.get("bookId") or r["address_book_id"]
    if int(target) != r["address_book_id"]:
        writable_book(u, target)
    photo = data.pop("photo", None) if isinstance(data.get("photo"), dict) and data["photo"].get("data") else None
    await run_in_threadpool(model.save, int(target), {**data, **({"photo": photo} if photo else {})}, cid, None, True, book_ids(u))
    return contact_out(model.full(cid))


@router.patch("/api/contacts/{cid}")
async def patch_contact(cid: int, request: Request):
    """Only some fields, e.g. {"favorite": true} or {"iopix": {"personId": 12, "name": "Ann"}}."""
    u = writer(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    b = await request.json()
    c = model.full(cid)
    c.update({k: v for k, v in b.items() if k not in ("id", "uid", "href", "etag", "photo")})
    dest = int(c.get("bookId") or r["address_book_id"])
    if dest != r["address_book_id"]:
        writable_book(u, dest)  # moving it needs the right to change the other book too
    await run_in_threadpool(model.save, dest, c, cid, None, True, book_ids(u))
    return contact_out(model.full(cid))


@router.delete("/api/contacts/{cid}")
def delete_contact(cid: int, request: Request):
    u = writer(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    model.delete(cid)
    return {"ok": True}


@router.post("/api/contacts/bulk")
async def bulk(request: Request):
    """{ids: [...], action: delete | favorite | unfavorite | move | tag | untag, book?, tag?}"""
    u = writer(request)
    b = await request.json()
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
                model.save(c["bookId"], {**c, "tags": sorted(tags)}, cid, None, True, book_ids(u))
    await run_in_threadpool(run)
    return {"ok": True, "n": len(ids)}


@router.get("/api/contacts/{cid}/photo")
def get_photo(cid: int, request: Request):
    readable_contact(me(request), cid)
    p = model.photo(cid)
    if not p:
        raise HTTPException(404)
    return Response(p[0], media_type=p[1], headers={"Cache-Control": "private, max-age=60"})


@router.put("/api/contacts/{cid}/photo")
async def put_photo(cid: int, request: Request, file: UploadFile = File(...)):
    u = writer(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    data = await file.read()
    if len(data) > config.MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photos up to 2 MB")
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF" or data[:6] in (b"GIF87a", b"GIF89a")):
        raise HTTPException(400, "A JPEG, PNG, GIF or WebP image")
    ctype = "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png" if data[:4] == b"\x89PNG" else "image/webp" if data[:4] == b"RIFF" else "image/gif"
    model.set_photo(cid, data, ctype)
    return {"ok": True}


@router.delete("/api/contacts/{cid}/photo")
def del_photo(cid: int, request: Request):
    u = writer(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    model.set_photo(cid, None, None)
    return {"ok": True}


@router.post("/api/contacts/{cid}/photo/from-iopix")
async def photo_from_iopix(cid: int, request: Request):
    u = writer(request)
    r = readable_contact(u, cid)
    writable_book(u, r["address_book_id"])
    if not r["iopix_person_id"]:
        raise HTTPException(400, "Link the contact to an ioPix person first")
    try:
        got = await run_in_threadpool(iopix.face, r["iopix_person_id"])
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"ioPix did not answer: {e}")
    if not got:
        raise HTTPException(404, "ioPix has no face for this person yet")
    model.set_photo(cid, got[0], got[1].split(";")[0])
    return {"ok": True}


@router.post("/api/contacts/merge")
async def merge(request: Request):
    """{keep, others, result?, photoFrom?}: fold the others into keep. result is the contact as it should end up (fields
    chosen one by one, as /api/merge/preview offers them); without it, everything is combined. Undo: /api/merges."""
    u = writer(request)
    b = await request.json()
    keep, others = int(b["keep"]), [int(x) for x in b.get("others") or [] if int(x) != int(b["keep"])]
    if not others:
        raise HTTPException(400, "Name the contacts to merge into the kept one")
    for cid in [keep, *others]:
        r = readable_contact(u, cid)
        writable_book(u, r["address_book_id"])
    result = b.get("result") if isinstance(b.get("result"), dict) else None
    pf = b.get("photoFrom")
    mid = await run_in_threadpool(quality.merge, u, keep, others, result, int(pf) if pf not in (None, "") else None)
    return {**contact_out(model.full(keep)), "mergeId": mid}


@router.get("/api/merge/preview")
def merge_preview(request: Request, ids: str, keep: int | None = None):
    """What merging these contacts gives, and the fields where they disagree (to choose from)."""
    u = me(request)
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


@router.get("/api/duplicates")
def duplicates(request: Request, book: str | None = None, min_score: int = 35):
    """Probable duplicates, grouped, most certain first, each pair with a score and the reasons."""
    return {"groups": quality.find(book_ids(me(request), book), max(10, min(min_score, 100)))}


@router.post("/api/duplicates/dismiss")
async def duplicates_dismiss(request: Request):
    """{ids: [...]}: these contacts are different people; they are not offered as duplicates again."""
    u = writer(request)
    ids = [int(x) for x in (await request.json()).get("ids") or []]
    for cid in ids:
        writable_book(u, readable_contact(u, cid)["address_book_id"])
    return {"ok": True, "pairs": quality.not_duplicates(ids, u["id"])}


@router.delete("/api/duplicates/dismissed")
def duplicates_forget(request: Request):
    """Admins: offer every pair marked "not duplicates" again."""
    admin(request)
    return {"ok": True, "forgotten": quality.forget_not_duplicates()}


@router.get("/api/merges")
def merges(request: Request, limit: int = 50):
    """Recent merges, newest first, with whether each can still be undone."""
    return {"items": quality.history(book_ids(me(request)), max(1, min(limit, 200)))}


@router.post("/api/merges/{mid}/undo")
async def merge_undo(mid: int, request: Request):
    u = writer(request)
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

@router.post("/api/contacts/{cid}/lookup")
async def contact_lookup(cid: int, request: Request):
    """Look this contact up (Gravatar by email, and its GitHub, Mastodon and Bluesky profiles); what is found waits as
    suggestions."""
    u = me(request)
    writable_book(u, readable_contact(u, cid)["address_book_id"])
    return await run_in_threadpool(enrich.lookup, cid, u["id"])


@router.post("/api/lookup")
async def lookup_many(request: Request):
    """{ids?: [...], book?, offset?, limit?}: look several contacts up (25 at a time; call again with the next offset)."""
    u = me(request)
    b = await request.json()
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


@router.get("/api/suggestions")
def suggestions(request: Request, status: str = "pending", contact: int | None = None, book: str | None = None):
    u = me(request)
    if status not in ("pending", "accepted", "dismissed"):
        raise HTTPException(400, "status: pending, accepted or dismissed")
    return {"items": enrich.listing(book_ids(u, book), status, contact)}


@router.post("/api/suggestions/{sid}/accept")
async def suggestion_accept(sid: int, request: Request):
    """Apply a suggestion to its contact. Body (optional): {value} to apply an edited version."""
    u = writer(request)
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


@router.post("/api/suggestions/{sid}/dismiss")
def suggestion_dismiss(sid: int, request: Request):
    u = me(request)
    s = enrich.suggestion(sid)
    if not s:
        raise HTTPException(404, "No such suggestion")
    writable_book(u, readable_contact(u, s["contact_id"])["address_book_id"])
    enrich.dismiss(sid, u["id"])
    return {"ok": True}


@router.get("/api/quality")
def data_quality(request: Request, book: str | None = None, check: str | None = None):
    """The data quality checks: [{check, title, severity: problem | tidy | info, fix, count, items}]."""
    return {"checks": quality.run_checks(book_ids(me(request), book), check)}


@router.post("/api/quality/fix")
async def data_quality_fix(request: Request):
    """{check, ids?, countryCode?, book?}: fix a check's findings (all, or these contacts) where you may change them."""
    u = writer(request)
    b = await request.json()
    ids = [int(x) for x in b["ids"]] if b.get("ids") else None
    try:
        return await run_in_threadpool(quality.fix, u, str(b.get("check")), ids, book_ids(u, b.get("book")), b.get("countryCode"))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/tags")
def tags(request: Request, book: str | None = None):
    return {"items": model.all_tags(book_ids(me(request), book))}


@router.get("/api/relation-types")
def relation_types():
    return rel.catalog()


@router.get("/api/social-services")
def social_services():
    return {"items": [{"service": k, "name": v[0], "base": vcard.SOCIAL_BASE.get(k)} for k, v in vcard.SOCIAL_SERVICES.items()]}


@router.get("/api/upcoming")
def upcoming(request: Request, days: int = 30, book: str | None = None):
    return {"items": model.upcoming(book_ids(me(request), book), max(1, min(days, 366)))}


@router.get("/api/contacts/{cid}/family")
def family(cid: int, request: Request, depth: int = 3):
    """The relation graph around a contact: {nodes: [{id, fn, given, family, gender, hasPhoto, iopixPersonId, birthday}], edges: [{from, to, type}]}."""
    u = me(request)
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
             for r in db.q(f"SELECT id, fn, given, family, gender, photo IS NOT NULL AS hp, iopix_person_id, bday_year, bday_month, bday_day "
                           f"FROM con_contacts WHERE id IN ({marks})", list(seen))]
    uniq = {(e["from"], e["to"], e["type"]): e for e in edges}
    return {"root": cid, "nodes": nodes, "edges": list(uniq.values())}


# ------------------------------------------------------------------ import / export

@router.post("/api/import")
async def import_file(request: Request, file: UploadFile = File(...), book: str = Form(...), mode: str = Form("update")):
    """A .vcf (any number of cards, vCard 2.1/3.0/4.0), a jCard .json, or a Google / Outlook .csv.
    mode: update (a card whose UID is already in the book replaces it) or skip (keeps the existing one)."""
    u = writer(request)
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
        model.save(b["id"], c, existing["id"] if existing else None, None, True, ids)
        if existing:
            updated += 1
        else:
            made += 1
    return {"created": made, "updated": updated, "skipped": skipped, "read": len(cards)}


@router.get("/api/export")
def export(request: Request, book: str | None = None, format: str = "vcf", ids: str = ""):
    u = me(request)
    bids = book_ids(u, book)
    if ids:
        want = [int(x) for x in ids.split(",") if x.strip().isdigit()]
        sel = [x for x in want if model.get_row(x) and model.get_row(x)["address_book_id"] in bids]
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
        return "".join(model.vcard_text(x, v) for x in ids), f"text/vcard; charset=utf-8; version={v}", "vcf"
    if format == "jcard":
        return json.dumps([vcard.to_jcard(model.full(x, with_photo=True)) for x in ids], ensure_ascii=False), JCARD_TYPE, "json"
    full = [model.full(x) for x in ids]
    text = csvio.export_outlook(full) if format == "csv-outlook" else csvio.export_google(full)
    return "\ufeff" + text, "text/csv; charset=utf-8", "csv"


# ------------------------------------------------------------------ calendar and connection details

def _base(request: Request) -> str:
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


@router.get("/api/connect")
def connect_info(request: Request):
    """What to type into a mail, contacts or calendar app."""
    u = me(request)
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


@router.post("/api/apple-profile")
def apple_profile(request: Request, label: str = Form("iPhone"), password: str = Form("new"), calendar: str = Form("family"),
                  ldap: bool = Form(False)):
    """A configuration profile (.mobileconfig) that sets an iPhone, iPad or Mac up in one go: the CardDAV account for the
    contacts and, if asked, the birthday calendar subscription (and the LDAP directory). password: "new" puts a new app
    password (named after label) in the profile; "ask" leaves it out, and the device asks for it while installing."""
    import plistlib
    import uuid
    from urllib.parse import urlsplit
    u = me(request)
    base = _base(request)
    parts = urlsplit(base)
    ssl = parts.scheme == "https"
    host = parts.hostname or "localhost"
    port = parts.port or (443 if ssl else 80)
    label = (label or "iPhone").strip()[:48] or "iPhone"
    secret = users.create_app_password(u["id"], f"{label} (profile)") if password == "new" else None
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
    return Response(plistlib.dumps(profile), media_type="application/x-apple-aspen-config",
                    headers={"Content-Disposition": f'attachment; filename="iocontacts-{re.sub(r"[^A-Za-z0-9-]", "-", u["name"])}.mobileconfig"',
                             "Cache-Control": "no-store"})


@router.post("/api/calendar/reset")
def calendar_reset(request: Request):
    users.reset_calendar_token(me(request)["id"])
    return {"ok": True}


@router.get("/cal/{token}/{which}.ics")
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

@router.get("/api/iopix/settings")
def iopix_settings(request: Request):
    me(request)
    return iopix.public_settings()


@router.post("/api/iopix/settings")
async def iopix_save(request: Request):
    admin(request)
    b = await request.json()
    try:
        iopix.save_settings(b.get("url"), b.get("user"), b.get("password"), b.get("cfId"), b.get("cfSecret"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {**iopix.public_settings(), "test": await run_in_threadpool(iopix.test) if iopix.settings()["url"] else None}


@router.post("/api/iopix/test")
async def iopix_test(request: Request):
    admin(request)
    return await run_in_threadpool(iopix.test)


@router.get("/api/iopix/people")
async def iopix_people(request: Request, q: str = "", refresh: bool = False):
    u = me(request)
    try:
        ppl = await run_in_threadpool(iopix.people, refresh)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"ioPix did not answer: {type(e).__name__}: {e}")
    linked = {r["iopix_person_id"]: {"id": r["id"], "fn": r["fn"]} for r in db.q(
        f"SELECT id, fn, iopix_person_id FROM con_contacts WHERE iopix_person_id IS NOT NULL AND deleted = 0 "
        f"AND address_book_id IN ({','.join(['%s'] * max(1, len(book_ids(u))))})", book_ids(u) or [0])}
    ql = fold(q).strip()
    return {"items": [{**p, "contact": linked.get(p["id"])} for p in ppl if not ql or ql in fold(p["name"])]}


@router.get("/api/iopix/face/{pid}")
async def iopix_face(pid: int, request: Request):
    me(request)
    try:
        got = await run_in_threadpool(iopix.face, pid)
    except Exception:  # noqa: BLE001
        raise HTTPException(502)
    if not got:
        raise HTTPException(404)
    return Response(got[0], media_type=got[1], headers={"Cache-Control": "private, max-age=86400"})


@router.post("/api/iopix/auto-link")
async def iopix_autolink(request: Request, book: str | None = None, dry: bool = True):
    """Contacts whose name matches exactly one ioPix person (and that are not linked yet): listed, or linked with dry=false."""
    u = writer(request)
    ppl = await run_in_threadpool(iopix.people)
    by_name: dict = {}
    for p in ppl:
        by_name.setdefault(p["name"].strip().lower(), []).append(p)
    taken = {r["iopix_person_id"] for r in db.q("SELECT iopix_person_id FROM con_contacts WHERE iopix_person_id IS NOT NULL AND deleted = 0")}
    out = []
    for c in model.search(book_ids(u, book), limit=100000)[0]:
        if c["iopixPersonId"]:
            continue
        m = by_name.get(c["fn"].strip().lower()) or []
        if len(m) == 1 and m[0]["id"] not in taken:
            r = model.get_row(c["id"])
            if model.can_write_book(u, model.book(r["address_book_id"])):
                out.append({"contactId": c["id"], "fn": c["fn"], "personId": m[0]["id"], "personName": m[0]["name"]})
    if not dry:
        for x in out:
            model.set_fields(x["contactId"], iopix_person_id=x["personId"], iopix_person_name=x["personName"])
    return {"items": out, "linked": 0 if dry else len(out)}
