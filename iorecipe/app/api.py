"""The REST API (JSON) the web app uses. OpenAPI docs at /api/docs. Who may call a route is declared on it
(app/access.py); what an account may see and change is a recipe's business (app/model.py).

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`.
"""
import datetime as dt
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from iosuite_shared.access import json_body

from app import access, ai, config, model, ocr, portable, scrape, shopping, textimport

router = APIRouter()


def _family(u: dict, b: dict) -> bool:
    """Where a new recipe goes: `family` as given, else the family's for those who may add there, else one's own."""
    return bool(b["family"]) if "family" in b else model.may_add(u, True)


@router.get("/api/recipes", dependencies=[access.signed_in])
def list_recipes(request: Request, q: str = "", tag: str | None = None, scope: str | None = None, book: int | None = None,
                 sort: str | None = None):
    """The recipes you see, without their ingredients and steps. q: words to find (in the title, the ingredients, the
    steps, the tags); tag: only those with this tag; scope: family, mine or favourites; book: only those in this
    cookbook; sort: title (as left out), new (the newest first) or rating (the best rated first)."""
    u = request.state.user
    return {"items": [model.public(r, u, full=False) for r in model.find(u, q, tag, scope, book=book, sort=sort)], **_around(u)}


def _around(u: dict) -> dict:
    return {"counts": model.counts(u), "tags": model.tags(u), "books": [model.book_public(b, u) for b in model.books(u)]}


@router.get("/api/summary", dependencies=[access.signed_in])
def summary(request: Request):
    """How many recipes you see (all, family, mine, favourites), the tags in use, the most used first, and the cookbooks."""
    return _around(request.state.user)


@router.post("/api/recipes", dependencies=[access.signed_in])
async def add_recipe(request: Request):
    """{title, description?, servings?, prepMinutes?, cookMinutes?, totalMinutes?, ingredients: [..], steps: [..],
    notes?, tags: [..], sourceUrl?, sourceName?, family?}. Ingredients and steps are lists of lines (or one text, a
    line each); a line that ends with a colon is a heading. family: true for a family recipe (editors), false for a
    private one."""
    u = request.state.user
    b = await json_body(request)
    r = await run_in_threadpool(model.create, u, b, _family(u, b))
    return JSONResponse(model.public(r, u), status_code=201)


@router.get("/api/recipes/{rid}", dependencies=[access.signed_in])
def get_recipe(rid: int, request: Request):
    u = request.state.user
    return model.public(model.readable(u, rid), u)


@router.patch("/api/recipes/{rid}", dependencies=[access.signed_in])
async def change_recipe(rid: int, request: Request):
    """Change the fields given (as POST /api/recipes); the others stay. family: move it to or from the family's (editors)."""
    u = request.state.user
    b = await json_body(request)

    def go():
        return model.update(u, model.readable(u, rid), b)
    return model.public(await run_in_threadpool(go), u)


@router.delete("/api/recipes/{rid}", dependencies=[access.signed_in])
def delete_recipe(rid: int, request: Request):
    u = request.state.user
    model.delete(u, model.readable(u, rid))
    return {"ok": True}


# ---- the photos

@router.get("/api/recipes/{rid}/photos/{pid}", dependencies=[access.signed_in])
def get_photo(rid: int, pid: int, request: Request, size: str = ""):
    """One of the recipe's pictures (JPEG); size=small for the card's. A picture never changes, so it may be kept."""
    u = request.state.user
    model.readable(u, rid)
    b = model.photo(rid, pid, size == "small")
    if b is None:
        raise HTTPException(404, "This recipe has no such photo")
    return Response(b, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.post("/api/recipes/{rid}/photos", dependencies=[access.signed_in])
async def add_photo(rid: int, request: Request, step: int | None = None):
    """The picture itself as the request body (JPEG, PNG, WebP or GIF): one more photo of the recipe (the first is
    the one the cards show). ?step=2: the picture of that step instead (its place in steps, from 0), in place of the
    one it had. It is turned upright and kept as a JPEG. The recipe, as GET gives it."""
    u = request.state.user
    raw = await request.body()

    def go():
        r = model.readable(u, rid)
        model.add_photo(u, r, raw, step)
        return model.readable(u, rid)
    return JSONResponse(model.public(await run_in_threadpool(go), u), status_code=201)


@router.put("/api/recipes/{rid}/photos/order", dependencies=[access.signed_in])
async def order_photos(rid: int, request: Request):
    """{ids: [..]}: the recipe's own photos in this order; the first is the one the cards show."""
    u = request.state.user
    b = await json_body(request)
    model.order_photos(u, model.readable(u, rid), b.get("ids") if isinstance(b.get("ids"), list) else [])
    return model.public(model.readable(u, rid), u)


@router.delete("/api/recipes/{rid}/photos/{pid}", dependencies=[access.signed_in])
def delete_photo(rid: int, pid: int, request: Request):
    u = request.state.user
    model.remove_photo(u, model.readable(u, rid), pid)
    return model.public(model.readable(u, rid), u)


# ---- favourites and ratings

@router.put("/api/recipes/{rid}/mark", dependencies=[access.signed_in])
async def mark_recipe(rid: int, request: Request):
    """{favourite?: true or false, rating?: 1 to 5, or null to take it away}: what you think of the recipe. Yours
    alone: the others see only the average of the ratings."""
    u = request.state.user
    b = await json_body(request)
    return model.public(model.mark(u, model.readable(u, rid), b), u)


# ---- cookbooks

@router.get("/api/books", dependencies=[access.signed_in])
def list_books(request: Request):
    """The cookbooks you see: the family's, then your own, each with how many recipes it shows you."""
    u = request.state.user
    return {"items": [model.book_public(b, u) for b in model.books(u)]}


@router.post("/api/books", dependencies=[access.signed_in])
async def add_book(request: Request):
    """{name, description?, family?}: a family cookbook (editors; it holds family recipes) or one of your own."""
    u = request.state.user
    b = await json_body(request)
    book = model.create_book(u, b, _family(u, b))
    return JSONResponse(model.book_public({**book, "n": 0}, u), status_code=201)


@router.patch("/api/books/{bid}", dependencies=[access.signed_in])
async def change_book(bid: int, request: Request):
    """{name?, description?}"""
    u = request.state.user
    b = await json_body(request)
    return model.book_public(model.update_book(u, model.readable_book(u, bid), b), u)


@router.delete("/api/books/{bid}", dependencies=[access.signed_in])
def delete_book(bid: int, request: Request):
    """The cookbook goes; its recipes stay."""
    u = request.state.user
    model.delete_book(u, model.readable_book(u, bid))
    return {"ok": True}


@router.put("/api/books/{bid}/recipes/{rid}", dependencies=[access.signed_in])
def book_add(bid: int, rid: int, request: Request):
    """Put the recipe in the cookbook. A family cookbook takes family recipes only."""
    u = request.state.user
    model.book_add(u, model.readable_book(u, bid), model.readable(u, rid))
    return {"ok": True}


@router.delete("/api/books/{bid}/recipes/{rid}", dependencies=[access.signed_in])
def book_remove(bid: int, rid: int, request: Request):
    u = request.state.user
    model.book_remove(u, model.readable_book(u, bid), model.readable(u, rid))
    return {"ok": True}


# ---- import

def import_from(u: dict, url: str, family: bool) -> dict:
    """Fetch the page, read its recipe, keep it (with its picture when there is one)."""
    if not model.may_add(u, family):
        raise model.Forbidden("Only editors add family recipes" if family else "A viewer only looks; a member keeps recipes of their own")
    data, picture = scrape.recipe_at(url)
    how = data.pop("readBy", "data")
    r = model.create(u, data, family)
    if picture:
        try:
            model.add_photo(u, r, picture)
        except ValueError:
            pass  # not a picture after all: the recipe without it
    return {**model.readable(u, r["id"]), "readBy": how}


@router.post("/api/import", dependencies=[access.signed_in])
async def import_recipe(request: Request):
    """{url, family?}: the recipe on that web page, with its picture, as a new recipe. `readBy` in the answer says how
    it was found: "data" (the schema.org Recipe data most recipe sites publish), "page" (the page's own lists or the
    text under its "Ingredients" heading) or "ai" (the AI model on this server read the page's text).
    400 when the page cannot be fetched or no recipe is found on it."""
    u = request.state.user
    b = await json_body(request)
    if not str(b.get("url") or "").strip():
        raise HTTPException(400, "The address of a recipe, please")
    r = await run_in_threadpool(import_from, u, str(b["url"]), _family(u, b))
    return JSONResponse({**model.public(r, u), "readBy": r["readBy"]}, status_code=201)


def _may_draft(u: dict) -> None:
    """A draft is for those who may keep a recipe somewhere."""
    if not (model.may_add(u, False) or model.may_add(u, True)):
        raise model.Forbidden("A viewer only looks; a member keeps recipes of their own")


@router.get("/api/import", dependencies=[access.signed_in])
def import_ways(request: Request):
    """What this server can import from: {photo: whether it reads a photo of a recipe (Tesseract is installed),
    languages: the languages it reads, ai: whether a web page without recipe data is read with the AI model on this
    server, aiState: "ready", "fetching" (the model is on its way), "missing" or "off"}."""
    return {"photo": ocr.available(), "languages": ocr.languages(), "ai": ai.available(), "aiState": ai.state()}


@router.post("/api/import/text", dependencies=[access.signed_in])
async def import_text(request: Request):
    """{text}: the recipe in a piece of plain text (pasted from a message, a document, a page), as a draft: the fields
    POST /api/recipes takes, for the form to show. Nothing is saved."""
    _may_draft(request.state.user)
    b = await json_body(request)
    return {"draft": await run_in_threadpool(textimport.parse, b.get("text"))}


@router.post("/api/import/photo", dependencies=[access.signed_in])
async def import_photo(request: Request):
    """The photo of a recipe (a page of a book, a card, a screenshot) as the request body: the text on it is read on
    this server and turned into a draft, as POST /api/import/text does. {draft, text}. Nothing is saved; 400 when the
    server has no Tesseract or nothing can be read."""
    _may_draft(request.state.user)
    raw = await request.body()

    def go():
        text = ocr.read(raw)
        return {"draft": textimport.parse(text), "text": text}
    return await run_in_threadpool(go)


@router.post("/api/import/file", dependencies=[access.signed_in])
async def import_file(request: Request, family: bool | None = None):
    """A file of recipes as the request body: an ioRecipe export (.zip), a Mealie export or backup (.zip), or a recipe
    as JSON (Mealie's, or schema.org's). Every recipe in it becomes a new one, with its photos; ?family=true for
    family recipes (editors), false for your own. {imported: [{id, title}], skipped: [why]}."""
    u = request.state.user
    raw = await request.body()
    fam = model.may_add(u, True) if family is None else family

    def go():
        return portable.keep(u, portable.read(raw), fam)
    return await run_in_threadpool(go)


# ---- export

def _download(u: dict, rows: list, name: str) -> Response:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-")[:80] or "recipes"
    return Response(portable.export(u, rows), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.zip"'})


@router.get("/api/export", dependencies=[access.signed_in])
def export_recipes(request: Request, scope: str | None = None, book: int | None = None):
    """A .zip of the recipes you see (scope: family, mine or favourites; book: one cookbook), with their photos, your
    favourites and ratings and the cookbooks they are in: for safekeeping, or for POST /api/import/file elsewhere."""
    u = request.state.user
    rows = model.find(u, scope=scope, book=book, limit=2000, full=True)
    name = model.readable_book(u, book)["name"] if book is not None else "iorecipe-" + (scope or "recipes")
    return _download(u, rows, f"{name}-{dt.date.today().isoformat()}")


@router.get("/api/recipes/{rid}/export", dependencies=[access.signed_in])
def export_recipe(rid: int, request: Request):
    """One recipe as such a .zip."""
    u = request.state.user
    r = model.readable(u, rid)
    return _download(u, [r], r["title"])


# ---- the shopping list (ioTask)

@router.get("/api/shopping", dependencies=[access.signed_in])
def shopping_lists(request: Request):
    """Where a recipe's ingredients can be sent: {available, url, lists: [{id, name, shared}]}: your lists in ioTask
    that take new tasks. available is false while ioTask is not part of the suite; error says why it gave no lists."""
    if not shopping.enabled():
        return {"available": False, "url": "", "lists": []}
    try:
        return {"available": True, "url": shopping.url(), "lists": shopping.lists(request)}
    except shopping.Unavailable as e:
        return {"available": True, "url": shopping.url(), "lists": [], "error": str(e)}


@router.post("/api/recipes/{rid}/shopping", dependencies=[access.signed_in])
async def shopping_add(rid: int, request: Request):
    """{listId, lines: [..]}: each line (an ingredient, as the page shows it) becomes a task in that list of yours in
    ioTask. {added}."""
    u = request.state.user
    b = await json_body(request)
    r = model.readable(u, rid)

    def go():
        try:
            link = f"{config.PUBLIC_URL}/#/recipe/{r['id']}" if config.PUBLIC_URL else None
            return shopping.add(request, b.get("listId"), b.get("lines"), r["title"], link)
        except shopping.Unavailable as e:
            raise HTTPException(e.status if e.status in (400, 403, 404) else 502, str(e))
    return {"added": await run_in_threadpool(go)}
