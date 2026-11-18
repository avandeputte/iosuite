"""The suite's standard endpoints: what every app with items answers, in one shape, so neither the start page nor the
linked-items panel needs to know any app's own API.

    GET /api/suite/search?q=&n=&tz=&kinds=   {items: [item], more}: what the app finds for q, for this viewer
    GET /api/suite/items/{kind}/{id}         one item, or 404 when the viewer may not see it (or it is gone)
    GET /api/suite/items/{kind}/{id}/image?p=   its small picture (p names one of several; "preview": screen size)
    GET /api/suite/tile?tz=&n=&kind=         what the start page's tile shows of the app (its own fields; kind: a
                                              second view, ioCalendar's week, ioPix's rediscover)

They are called as the viewer, like any of the app's routes (the start page and the other apps pass the viewer's own
sign-in on: iosuite_shared.links.as_viewer), so each answers with what that person may see and nothing more. An app
answers only the ones it has: the start page and the panel ask the apps whose manifest (app.json) says so ("search",
"tile", "items").

An item:

    {kind, id, title, text, when, allDay, done, image, href, color, round, icon, amount, currency}

  kind, id     an item kind of the app's manifest ("event", 12), or one only its search box shows ("person", "payee")
  title, text  what it is called, and one short line under it
  when         ISO date or date and time (allDay: a date that is a whole day); done: a finished task, an event that is over
  image        null without a picture; else the p of its picture ("" for its only one): /api/suite/items/{kind}/{id}/image?p=
  href         where it opens, inside the app ("#/event/12"): the manifest's href for its kind, unless the item says
  color, round, icon   a colour dot (the calendar's), a round picture (a face), an icon name (the start page's set)
  amount, currency     money (ioMoney)

The app implements them as a Provider (each function optional) and mounts router(auth, provider). Its functions get a
Local, which asks the app itself for one of its own routes, as the same viewer and through the same middleware, so
the provider reads what the app's own API answers and the viewer's rights are the ones they have there:

    local.get("/api/tasks", {"q": q})            the JSON answer (Unavailable for an answer that is not a 2xx)
    local.raw("/thumb/12", {"fit": "square"})    (bytes, content type)
    local.together(f, g)                         run these at the same time: their answers (or the exception raised)
"""
import asyncio
import datetime as dt
import json
import logging
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from iosuite_shared import catalog

log = logging.getLogger("iosuite_shared.suiteitems")
_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="suiteitems")
TZ = re.compile(r"[A-Za-z0-9_+\-/]{1,64}")
MAX_N = 50


class Unavailable(Exception):
    """The app's own route would not answer: (status, why)."""

    def __init__(self, status: int, why: str = ""):
        super().__init__(why or f"answered {status}")
        self.status = status


@dataclass
class Provider:
    """search(local, q, n, tz, kinds) -> {items, more} | [item]; get(local, kind, id) -> item;
    image(local, kind, id, p) -> (bytes, content type); tile(local, tz, n, kind) -> dict. Leave out what the app has not."""
    search: Callable = None
    get: Callable = None
    image: Callable = None
    tile: Callable = None


def item(app: str, kind: str, item_id, title, text="", when=None, all_day=False, done=False, image=None, href=None,
         color=None, round=False, icon=None, amount=None, currency=None, **extra) -> dict:
    """An item in the suite's shape (see above). href: the manifest's for the kind unless given."""
    if href is None:
        h = (catalog.ITEMS.get(kind) or {}).get("href")
        href = h.replace("{id}", urllib.parse.quote(str(item_id))) if h else None
    out = {"kind": kind, "id": str(item_id), "title": str(title or "").strip()[:120] or "(no title)", "text": str(text or "").strip()[:140],
           "when": when, "allDay": bool(all_day), "done": bool(done), "image": image, "href": href}
    for k, v in (("color", color), ("round", round or None), ("icon", icon), ("amount", amount), ("currency", currency)):
        if v is not None:
            out[k] = v
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


def lines(text) -> list[str]:
    """A text's lines that say something (markdown marks off)."""
    return [s for s in (ln.strip().lstrip("#>*- ").strip() for ln in str(text or "").splitlines()) if s]


def wall_time(ts) -> str | None:
    """An epoch kept as the camera's wall time as if it were UTC (ioPix): that wall time, without a zone."""
    try:
        return dt.datetime.fromtimestamp(float(ts), dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="minutes")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


class Local:
    """The app's own routes, asked as the viewer who called: the request goes through the app again (its middleware
    signs the viewer in from the same headers) on the event loop the call came in on."""

    def __init__(self, request: Request, loop):
        self.app, self.scope, self.loop = request.app, request.scope, loop

    def _scope(self, path: str, params: dict | None) -> dict:
        s = self.scope
        qs = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}).encode()
        headers = [(k, v) for k, v in s.get("headers", []) if k not in (b"content-length", b"content-type", b"accept-encoding")]
        return {"type": "http", "asgi": s.get("asgi", {"version": "3.0"}), "http_version": s.get("http_version", "1.1"),
                "method": "GET", "scheme": s.get("scheme", "http"), "server": s.get("server"), "client": s.get("client"),
                "root_path": s.get("root_path", ""), "path": path, "raw_path": path.encode(), "query_string": qs,
                "headers": headers, "extensions": {}}

    async def _call(self, path: str, params: dict | None) -> tuple[int, bytes, str]:
        sent, got = {"status": 500, "type": "", "body": []}, {"once": False}

        async def receive():
            if not got["once"]:
                got["once"] = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await asyncio.Event().wait()  # nothing more comes: the response is all that matters

        async def send(m):
            if m["type"] == "http.response.start":
                sent["status"] = m["status"]
                sent["type"] = next((v.decode("latin-1") for k, v in m.get("headers", []) if k.lower() == b"content-type"), "")
            elif m["type"] == "http.response.body":
                sent["body"].append(m.get("body", b""))
        await self.app(self._scope(path, params), receive, send)
        return sent["status"], b"".join(sent["body"]), sent["type"]

    def _answer(self, path: str, params: dict | None) -> tuple[bytes, str]:
        status, body, ctype = asyncio.run_coroutine_threadsafe(self._call(path, params), self.loop).result(60)
        if status >= 300:
            why = ""
            try:
                why = json.loads(body).get("detail") or ""
            except (ValueError, AttributeError):
                pass
            raise Unavailable(403 if status == 401 else status, why if isinstance(why, str) else "")
        return body, ctype

    def get(self, path: str, params: dict | None = None):
        return json.loads(self._answer(path, params)[0] or b"null")

    def raw(self, path: str, params: dict | None = None) -> tuple[bytes, str]:
        return self._answer(path, params)

    @staticmethod
    def together(*calls) -> list:
        out = []
        for f in [_pool.submit(c) for c in calls]:
            try:
                out.append(f.result())
            except Exception as e:  # noqa: BLE001 - handed to the caller, who knows which ones matter
                out.append(e)
        return out

    @staticmethod
    def both(*calls) -> list:
        out = Local.together(*calls)
        for r in out:
            if isinstance(r, Exception):
                raise r
        return out


def router(auth, provider: Provider) -> APIRouter:
    """/api/suite/*, for an app of the suite (only what its provider has)."""
    r = APIRouter()
    access = auth.access

    async def run(request: Request, f, *args):
        local = Local(request, asyncio.get_running_loop())
        try:
            return await run_in_threadpool(f, local, *args)
        except Unavailable as e:
            raise HTTPException(e.status if 400 <= e.status < 600 else 502, str(e)) from None

    def zone(tz: str) -> str:
        return tz if tz and TZ.fullmatch(tz) else ""

    if provider.search:
        @r.get("/api/suite/search", dependencies=[access.signed_in])
        async def suite_search(request: Request, q: str = "", n: int = 6, tz: str = "", kinds: str = ""):
            """{items, more}: what this app finds for q (see iosuite_shared.suiteitems)."""
            q = q.strip()[:80]
            if not q:
                return {"items": [], "more": False}
            got = await run(request, provider.search, q, max(1, min(n, MAX_N)), zone(tz), [k for k in kinds.split(",") if k] or None)
            return got if isinstance(got, dict) else {"items": got, "more": False}

    if provider.get:
        @r.get("/api/suite/items/{kind}/{item_id}", dependencies=[access.signed_in])
        async def suite_item(kind: str, item_id: str, request: Request):
            """One item in the suite's shape; 404 when you may not see it."""
            got = await run(request, provider.get, kind, item_id)
            if not got:
                raise HTTPException(404, "No such item")
            return got

    if provider.image:
        @r.get("/api/suite/items/{kind}/{item_id}/image", dependencies=[access.signed_in])
        async def suite_image(kind: str, item_id: str, request: Request, p: str = ""):
            """An item's small picture."""
            got = await run(request, provider.image, kind, item_id, p[:40])
            if not got:
                raise HTTPException(404, "No picture")
            body, ctype = got
            return Response(body, media_type=ctype if str(ctype).startswith("image/") else "image/jpeg",
                            headers={"Cache-Control": "private, max-age=3600"})

    if provider.tile:
        @r.get("/api/suite/tile", dependencies=[access.signed_in])
        async def suite_tile(request: Request, tz: str = "", n: int = 0, kind: str = ""):
            """What the start page's tile shows of this app, for you."""
            return await run(request, provider.tile, zone(tz), max(0, min(n, MAX_N)), kind[:20])
    return r
