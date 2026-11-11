"""The REST API (JSON) the web app uses. OpenAPI docs at /api/docs. Who may call a route is declared on it
(app/access.py); what an account may see and change is a recipe's business (app/model.py).

Clients authenticate with the web session cookie, HTTP Basic (name + password or app password) or
`Authorization: Bearer <app password>`.
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from iosuite_shared.access import json_body

from app import access, model, scrape

router = APIRouter()


def _family(u: dict, b: dict) -> bool:
    """Where a new recipe goes: `family` as given, else the family's for those who may add there, else one's own."""
    return bool(b["family"]) if "family" in b else model.may_add(u, True)


@router.get("/api/recipes", dependencies=[access.signed_in])
def list_recipes(request: Request, q: str = "", tag: str | None = None, scope: str | None = None):
    """The recipes you see, by title, without their ingredients and steps. q: words to find (in the title, the
    ingredients, the steps, the tags); tag: only those with this tag; scope: family or mine."""
    u = request.state.user
    return {"items": [model.public(r, u, full=False) for r in model.find(u, q, tag, scope)], "counts": model.counts(u), "tags": model.tags(u)}


@router.get("/api/summary", dependencies=[access.signed_in])
def summary(request: Request):
    """How many recipes you see (all, family, mine) and the tags in use, the most used first."""
    u = request.state.user
    return {"counts": model.counts(u), "tags": model.tags(u)}


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


@router.get("/api/recipes/{rid}/photo", dependencies=[access.signed_in])
def get_photo(rid: int, request: Request, size: str = ""):
    """The recipe's picture (JPEG); size=small for the card's. Its address carries a version, so it may be kept."""
    u = request.state.user
    model.readable(u, rid)
    b = model.photo(rid, size == "small")
    if b is None:
        raise HTTPException(404, "This recipe has no picture")
    return Response(b, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.put("/api/recipes/{rid}/photo", dependencies=[access.signed_in])
async def put_photo(rid: int, request: Request):
    """The picture itself as the request body (JPEG, PNG, WebP or GIF). It is turned upright and kept as a JPEG."""
    u = request.state.user
    raw = await request.body()

    def go():
        return model.set_photo(u, model.readable(u, rid), raw)
    return model.public(await run_in_threadpool(go), u)


@router.delete("/api/recipes/{rid}/photo", dependencies=[access.signed_in])
def delete_photo(rid: int, request: Request):
    u = request.state.user
    return model.public(model.remove_photo(u, model.readable(u, rid)), u)


def import_from(u: dict, url: str, family: bool) -> dict:
    """Fetch the page, read its recipe, keep it (with its picture when there is one)."""
    if not model.may_add(u, family):
        raise model.Forbidden("Only editors add family recipes" if family else "A viewer only looks; a member keeps recipes of their own")
    data, picture = scrape.recipe_at(url)
    r = model.create(u, data, family)
    if picture:
        try:
            r = model.set_photo(u, r, picture)
        except ValueError:
            pass  # not a picture after all: the recipe without it
    return r


@router.post("/api/import", dependencies=[access.signed_in])
async def import_recipe(request: Request):
    """{url, family?}: the recipe on that web page (the schema.org Recipe data most recipe sites publish), with its
    picture, as a new recipe. 400 when the page cannot be fetched or describes no recipe."""
    u = request.state.user
    b = await json_body(request)
    if not str(b.get("url") or "").strip():
        raise HTTPException(400, "The address of a recipe, please")
    r = await run_in_threadpool(import_from, u, str(b["url"]), _family(u, b))
    return JSONResponse(model.public(r, u), status_code=201)
