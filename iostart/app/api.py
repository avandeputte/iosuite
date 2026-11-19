"""The REST API (JSON) the start page uses. OpenAPI docs at /api/docs. Who may call a route is declared on it (app/access.py).

Clients authenticate with the web session cookie (the suite's, shared by every io app on the domain), HTTP Basic or
`Authorization: Bearer <app password>`, as in the other io apps."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.concurrency import run_in_threadpool
import asyncio
import io
import json
import os
import zipfile

from iosuite_shared import prefix
from iosuite_shared.access import json_body

from app import access, apps, config, siteicons, bookmarkcheck, bookmarkdav, bookmarkfiles, bookmarks, bookmarksync, homeassistant as ha, ncbookmarks, layout, status as appstatus, trmnl, trmnlpush, trmnlserver, wall, weather, widgets

router = APIRouter()


# ------------------------------------------------------------------ the apps

@router.get("/api/apps", dependencies=[access.signed_in])
def list_apps(request: Request):
    """The tiles: every app this person may use, with its name, icon, colour and address (an admin tool only for its
    admins). Hidden ones are left out (Settings lists them)."""
    u = request.state.user
    return {"items": apps.tiles(u), "photoStrip": apps.photo_strip(), "layout": layout.get(u["id"])}


@router.get("/api/apps/status", dependencies=[access.signed_in])
async def apps_status(request: Request):
    """Each app's /api/status, asked with the viewer's sign-in: {items: {key: {ok, version, why}}}. Cached a
    minute."""
    return {"items": await run_in_threadpool(appstatus.of_apps, request)}


@router.get("/api/me/layout", dependencies=[access.signed_in])
def my_layout(request: Request):
    """The viewer's own start page: {hidden, order, strip} (see app/layout.py)."""
    return layout.get(request.state.user["id"])


@router.put("/api/me/layout", dependencies=[access.signed_in])
async def my_layout_save(request: Request):
    """Body: {hidden?: [keys], order?: [app keys], cards?: [home | birthdays | week | strip | bookmarks], strip?: rediscover |
    onthisday | off | null}. {} puts it back."""
    u = request.state.user
    return layout.save(u["id"], await json_body(request))


@router.get("/api/home/settings", dependencies=[access.admin])
def home_settings(request: Request):
    """Admins: what the home page shows everyone by default (the photo strip under the tiles)."""
    return {"photoStrip": apps.photo_strip()}


@router.post("/api/home/settings", dependencies=[access.admin])
async def home_save(request: Request):
    """Admins. Body: {photoStrip: rediscover | onthisday | off}."""
    b = await json_body(request)
    if "photoStrip" in b:
        apps.set_photo_strip(b["photoStrip"])
    return {"photoStrip": apps.photo_strip()}


# ------------------------------------------------------------------ the weather

@router.get("/api/weather", dependencies=[access.signed_in])
async def get_weather(request: Request):
    """The widget: current conditions and the 5-day forecast, from the server's copy (refreshed from AccuWeather when
    it is older than 45 minutes / 6 hours). {enabled: false} until an admin sets it up."""
    try:
        return await run_in_threadpool(weather.current)
    except weather.WeatherError as e:
        return {"enabled": True, "error": str(e), "current": None, "forecast": None, "units": weather.settings()["units"],
                "location": weather.settings()["locationName"]}


@router.get("/api/weather/place", dependencies=[access.signed_in])
def weather_place(request: Request):
    """The weather's place and units, for the other apps (ioCalendar draws its own forecast for this place): {name,
    units}; name empty while none is chosen. Never asks AccuWeather."""
    s = weather.settings()
    return {"name": s["locationName"] if s["locationKey"] else "", "units": s["units"]}


@router.get("/api/weather/settings", dependencies=[access.admin])
def weather_settings(request: Request):
    return weather.settings()


@router.post("/api/weather/settings", dependencies=[access.admin])
async def weather_save(request: Request):
    """Admins. Body: {key?, locationKey?, locationName?, units?}."""
    u = request.state.user
    b = await json_body(request)
    try:
        weather.save(b, by=u.get("name"))
    except weather.WeatherError as e:
        raise HTTPException(400, str(e))
    return weather.settings()


@router.get("/api/weather/search", dependencies=[access.admin])
async def weather_search(request: Request, q: str = "", key: str = ""):
    """Admins: places matching a city name, to pick the location in Settings. `key` tries a key before it is saved."""
    try:
        return {"items": await run_in_threadpool(weather.search, q, key)}
    except weather.WeatherError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ Home Assistant (app/homeassistant.py)

def _ha(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ha.HAError as e:
        raise HTTPException(e.status, str(e))


def _ha_card(request: Request, d: dict) -> dict:
    """The card as this viewer gets it: switching things takes an editor or an admin, so a viewer's copy offers no
    control (the page then shows the state alone). A copy: the card itself is shared between the pages."""
    if (getattr(request.state, "user", None) or {}).get("role") in ("editor", "admin") or not d.get("items"):
        return d
    return {**d, "items": [{**it, "control": False} for it in d["items"]]}


@router.get("/api/ha", dependencies=[access.signed_in])
async def get_home(request: Request):
    """The Home card and the wall's sensors: the chosen entities with their state (from the server's copy, a few seconds
    old at most), which of them go on the wall, and what needs attention. {enabled: false} until an admin sets it up.
    `control` on an entity is true for editors and admins only."""
    return _ha_card(request, await run_in_threadpool(ha.home))


@router.get("/api/ha/events", dependencies=[access.signed_in])
async def ha_events(request: Request, once: bool = False):
    """The Home card as server-sent events: the same JSON as /api/ha, sent when something in it changes (within a
    second while the live feed is up, else as the REST copy refreshes) and a comment every 20 seconds to keep the
    connection. The page's EventSource reconnects by itself. once=1: the card as it stands, then the end (a check)."""

    async def gen():
        last, seen = None, ha.feed.version
        beat = 0.0
        while True:
            if await request.is_disconnected():
                return
            d = _ha_card(request, await run_in_threadpool(ha.home))
            raw = json.dumps(d, separators=(",", ":"))
            now = asyncio.get_running_loop().time()
            if raw != last:
                last = raw
                beat = now
                yield f"data: {raw}\n\n"
                if once:
                    return
            elif now - beat > 20:
                beat = now
                yield ": keep\n\n"
            if d.get("live"):  # wait for the feed to move (or a few seconds, to notice a disconnect), without a thread
                seen = await ha.feed.wait_async(seen, 5.0)
            else:
                await asyncio.sleep(ha.STATES_TTL)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/api/ha/{entity_id}/set", dependencies=[access.editor])
async def ha_set(entity_id: str, request: Request):
    """Editors and admins. The popups: a thermostat takes {temperature? | low? + high?, mode?, fan?, preset?}, a cover
    {action: open | close | stop} or {position: 0-100}; on an entity the admin lets the page control. Returns the
    entity's state right after."""
    return await run_in_threadpool(_ha, ha.set_entity, entity_id, await json_body(request))


@router.post("/api/ha/{entity_id}/{action}", dependencies=[access.editor])
async def ha_act(entity_id: str, action: str, request: Request):
    """Editors and admins. toggle | on | off: switch an entity the admin lets the page control (Settings › Home
    Assistant). Returns the entity's state right after. 403 for any other entity, and for a viewer."""
    return await run_in_threadpool(_ha, ha.act, entity_id, action)


@router.get("/api/ha/search", dependencies=[access.admin])
async def ha_search(request: Request, q: str = "", n: int = 8):
    """Entities whose name or id contains every word of q (the search box; up to 50)."""
    return {"items": await run_in_threadpool(_ha, ha.search, q, max(1, min(int(n or 8), 50)))}


@router.get("/api/ha/settings", dependencies=[access.admin])
def ha_settings(request: Request):
    return ha.settings()


@router.post("/api/ha/settings", dependencies=[access.admin])
async def ha_save(request: Request):
    """Admins. Body: {url?, token?, entities?: [{id, name?, control?, wall?, alert?}], builtinAlerts?}."""
    u = request.state.user
    _ha(ha.save, await json_body(request), by=u.get("name"))
    return ha.settings()


@router.post("/api/ha/test", dependencies=[access.admin])
async def ha_test(request: Request):
    """Admins. Body: {url?, token?}: tries them (the saved ones when empty) → {ok, name, version, entities}."""
    b = await json_body(request)
    return await run_in_threadpool(_ha, ha.test, str(b.get("url") or ""), str(b.get("token") or ""))


# ------------------------------------------------------------------ bookmarks

@router.get("/api/bookmarks", dependencies=[access.signed_in])
def list_bookmarks(request: Request):
    """What the start page shows: {groups: [{id, name, path, links}]}: the folders picked for it, with the links shown."""
    _me(request)
    return {"groups": bookmarks.groups()}


@router.get("/api/bookmarks/tree", dependencies=[access.signed_in])
def bookmarks_tree(request: Request):
    """Every folder and link, nested (the Bookmarks page): {rev, count, items}. A folder: {id, type: 'folder', name,
    start, shared, canChange, items}; a link: {id, type: 'bookmark', name, href, start (null: as its folder), onStart,
    shared, canChange, …}. canEdit: the person may keep bookmarks of their own; canShare: they manage the shared ones."""
    _me(request)
    return bookmarks.tree()


@router.get("/api/bookmarks/status", dependencies=[access.signed_in])
async def bookmarks_status(request: Request):
    """Each bookmark on the start page pinged from this server: {items: {link id: {ok, status}}}; ok is null for an
    address that cannot be pinged (mailto:…). Cached five minutes."""
    _me(request)
    return {"items": await run_in_threadpool(appstatus.of_bookmarks)}


def _me(request: Request) -> None:
    """The bookmarks read and changed in this request are the signed-in person's (theirs and the shared ones)."""
    bookmarks.as_user(request.state.user)


@router.get("/api/bookmarks/duplicates", dependencies=[access.signed_in])
def bookmarks_duplicates(request: Request):
    """Tidy up: the addresses your tree holds more than once: {groups: [{href, links: [{id, name, href, path, shared,
    onStart, canChange}]}], extra}; in each group the copy to keep comes first."""
    _me(request)
    return bookmarkcheck.duplicates()


@router.get("/api/bookmarks/check", dependencies=[access.signed_in])
def bookmarks_check(request: Request):
    """Tidy up: how far the check of your bookmarks' addresses is, and what it found: {running, done, total,
    checkedAt, items: [{id, name, href, path, shared, canChange, state: dead | gone | moved, status, to}]}."""
    _me(request)
    return bookmarkcheck.state()


@router.post("/api/bookmarks/check", dependencies=[access.signed_in])
def bookmarks_check_start(request: Request):
    """Tidy up: ask every web address of your bookmarks (yours and the shared ones) whether it still answers, in the
    background; GET says how far it is. One check at a time per person."""
    _me(request)
    return bookmarkcheck.start()


def _bm(request: Request, fn, *a, **kw):
    _me(request)
    try:
        return fn(*a, **kw)
    except bookmarks.NotFound as e:
        raise HTTPException(404, str(e))
    except bookmarks.NotAllowed as e:
        raise HTTPException(403, str(e))
    except (bookmarks.BadBookmark, bookmarkfiles.BadFile) as e:
        raise HTTPException(400, str(e))


@router.post("/api/bookmarks/groups", dependencies=[access.signed_in])
async def add_group(request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {name, parentId? (a folder; none: the top), start? (on the start page; true unless said)}"""
    b = await json_body(request)
    return _bm(request, bookmarks.add_group, b.get("name"), b.get("parentId"), bool(b.get("start", True)))


@router.patch("/api/bookmarks/groups/{gid}", dependencies=[access.signed_in])
async def update_group(gid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). Any of {name, parentId (0: the top), start,
    shared (admins)}. start on a shared folder, from someone who is not an admin: their own start page only."""
    return _bm(request, bookmarks.update_group, gid, await json_body(request))


@router.delete("/api/bookmarks/groups/{gid}", dependencies=[access.signed_in])
def delete_group(gid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). The folder and everything in it."""
    _bm(request, bookmarks.delete_group, gid)
    return {"ok": True}


@router.post("/api/bookmarks/groups/order", dependencies=[access.signed_in])
async def order_groups(request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {ids: [folder id, ...], parentId?}: these folders in this order inside the parent (none: the top); one
    named from elsewhere moves in."""
    b = await json_body(request)
    _bm(request, bookmarks.order, b.get("parentId"), [int(x) for x in b.get("ids") or []])
    return {"ok": True}


@router.post("/api/bookmarks/groups/{gid}/links", dependencies=[access.signed_in])
async def add_link(gid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {name, href, abbr?, description?, icon?, start?, tags?}; group 0 is the top level."""
    b = await json_body(request)
    return _bm(request, bookmarks.add_link, gid, b.get("name"), b.get("href"), b.get("abbr"), b.get("description"), b.get("icon"), b.get("start"), b.get("tags"))


@router.post("/api/bookmarks/groups/{gid}/order", dependencies=[access.signed_in])
async def order_links(gid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {ids: [link id, ...]} in the order wanted; a link from another folder moves into this one (0: the top)."""
    b = await json_body(request)
    _bm(request, bookmarks.order, gid, [int(x) for x in b.get("ids") or []])
    return {"ok": True}


@router.patch("/api/bookmarks/links/{lid}", dependencies=[access.signed_in])
async def update_link(lid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). Any of {name, href, abbr, description, icon, groupId, tags, start (true | false | null: as its folder), shared (admins)}."""
    return _bm(request, bookmarks.update_link, lid, await json_body(request))


@router.delete("/api/bookmarks/links/{lid}", dependencies=[access.signed_in])
def delete_link(lid: int, request: Request):
    _bm(request, bookmarks.delete_link, lid)
    return {"ok": True}


@router.get("/api/bookmarks/links/{lid}/icon.svg", dependencies=[access.signed_in])
def link_icon(lid: int, request: Request):
    """The icon uploaded for a link (an SVG; an uploaded PNG is served inside one), for everyone signed in. Cached by the browser for good: the address carries a
    version (?v=etag) that changes with the file."""
    _me(request)
    try:
        ic = bookmarks.icon(lid)
    except bookmarks.NotFound:
        ic = None
    if not ic:
        raise HTTPException(404, "No icon")
    return Response(ic["svg"], media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": f'"{ic["etag"]}"',
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:", "X-Content-Type-Options": "nosniff"})


@router.get("/api/bookmarks/site-icon", dependencies=[access.signed_in])
def site_icon(site: str, request: Request):
    """A bookmarked site's own icon, as the server fetched it (app/siteicons.py), for everyone signed in. Cached by the
    browser for good: the address carries a version (?v=etag). Served as the kind of image its bytes are, and as
    nothing a browser would run."""
    ic = siteicons.get(site)
    if not ic:
        raise HTTPException(404, "No icon")
    return Response(bytes(ic["data"]), media_type=ic["mime"],
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": f'"{ic["etag"]}"',
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox", "X-Content-Type-Options": "nosniff"})


@router.put("/api/bookmarks/links/{lid}/icon", dependencies=[access.signed_in])
async def upload_link_icon(lid: int, request: Request):
    """Members, editors and admins (their own; the shared ones: admins). The body is the file itself, an SVG or a PNG (up to 256 KB); the stored one is replaced. Returns the link."""
    data = await request.body()
    return _bm(request, bookmarks.set_icon, lid, data)


@router.delete("/api/bookmarks/links/{lid}/icon", dependencies=[access.signed_in])
def delete_link_icon(lid: int, request: Request):
    return _bm(request, bookmarks.clear_icon, lid)


@router.post("/api/bookmarks/import", dependencies=[access.signed_in])
async def import_bookmarks(request: Request):
    """Members, editors and admins (their own; the shared ones: admins). {file, parentId?, start?}: the text of a
    bookmarks file a browser exported (HTML) or an XBEL file, added under the folder (none: the top); start: its
    folders go on the start page too (false unless said)."""
    b = await json_body(request)
    if b.get("file") is None:
        raise HTTPException(400, "Send {file}: a bookmarks file a browser exported (HTML) or an XBEL file")

    def work():
        items = bookmarkfiles.parse(str(b["file"]))
        bookmarks.add_items(b.get("parentId"), items, bool(b.get("start")))
        f, l = bookmarkfiles.count(items)
        return {"groups": f, "links": l}
    return await run_in_threadpool(_bm, request, work)


@router.get("/api/bookmarks/export.{kind}", dependencies=[access.signed_in])
def export_bookmarks(kind: str, request: Request):
    """Every bookmark as a file: export.html (what a browser imports) or export.xbel."""
    if kind not in ("html", "xbel"):
        raise HTTPException(404, "export.html or export.xbel")
    _me(request)
    items = bookmarksync.items()
    body = bookmarkfiles.to_html(items) if kind == "html" else bookmarkfiles.to_xbel(items, bookmarks.highest_id())
    return Response(body, media_type="text/html; charset=utf-8" if kind == "html" else "application/xml; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="bookmarks.{kind}"'})


@router.get("/api/bookmarks/sync", dependencies=[access.signed_in])
def bookmarks_sync(request: Request):
    """What to type into a sync app (the Bookmarks page): the addresses, and whether one is syncing right now."""
    root = ncbookmarks._root(request)
    return {"nextcloud": root + ncbookmarks.BASE, "webdav": root + bookmarkdav.BASE + "/", "files": list(bookmarkdav.NAMES),
            "syncing": bool(bookmarksync.locked_at()), "user": request.state.user["name"] if request.state.user else "",
            "extension": _extension_version()}


EXTENSION_DIR = os.path.join(config.STATIC_DIR, "extension")


def _extension_version() -> str:
    try:
        with open(os.path.join(EXTENSION_DIR, "manifest.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "")
    except (OSError, ValueError):
        return ""


@router.get("/api/bookmarks/extension.zip", dependencies=[access.signed_in])
def bookmarks_extension():
    """The ioStart Bookmarks browser extension (static/extension) as one file: unpacked, Chrome and Edge load the
    folder; Firefox takes the signed file of the same version (the repository's releases)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in sorted(os.walk(EXTENSION_DIR)):
            for name in sorted(files):
                full = os.path.join(base, name)
                z.write(full, os.path.join("iostart-bookmarks", os.path.relpath(full, EXTENSION_DIR)))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="iostart-bookmarks-{_extension_version() or "extension"}.zip"'})


# ------------------------------------------------------------------ what the tiles show (app/widgets.py)

@router.get("/api/widgets/{key}", dependencies=[access.signed_in])
def widget(key: str, request: Request, tz: str = "", kind: str = "", n: int = 0, q: str = ""):
    """A glimpse of one app for its tile (the app's /api/suite/tile), asked of the app with the viewer's own sign-in;
    with q, what the app finds for the search box instead (its /api/suite/search: {items, more}, items in the suite's
    shape). tz: the viewer's time zone (IANA, e.g. Europe/Brussels), for what "today" is; kind and n: what the app's
    tile takes (ioPix: onthisday | rediscover and how many; ioCalendar: week). 404 for an app without one (its
    manifest says which have a tile, and which a search); 401/403 when the app refuses this account; 502 when it does
    not answer. The page leaves the tile as it is on any of these."""
    try:
        return widgets.get(request, key, tz, kind, n, q)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/widgets/iocalendar/calendars", dependencies=[access.signed_in])
def widget_calendars(request: Request):
    """The ioCalendar calendars this viewer may add events to (quick add in the search box)."""
    try:
        return widgets.iocalendar_calendars(request)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.post("/api/widgets/iocalendar/events", dependencies=[access.signed_in])
async def widget_add_event(request: Request):
    """Quick add: a new event in ioCalendar, made with the viewer's own sign-in. {title, start, end?, allDay,
    timezone?, calendarId?} → {id, url}."""
    b = await json_body(request)
    try:
        return await run_in_threadpool(widgets.iocalendar_add, request, b)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/widgets/iotask/lists", dependencies=[access.signed_in])
def widget_task_lists(request: Request):
    """The ioTask lists this viewer may add tasks to (quick add in the search box)."""
    try:
        return widgets.iotask_lists(request)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.post("/api/widgets/iotask/tasks", dependencies=[access.signed_in])
async def widget_add_task(request: Request):
    """Quick add: a new task in ioTask, made with the viewer's own sign-in. {title, due? (a date, or a date and
    time), listId?, timezone?} → {id, url}."""
    b = await json_body(request)
    try:
        return await run_in_threadpool(widgets.iotask_add, request, b)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.post("/api/widgets/ionote/notes", dependencies=[access.signed_in])
async def widget_add_note(request: Request):
    """Quick add: a new note in ioNote, the viewer's own. {title?, text?} → {id, url}."""
    b = await json_body(request)
    try:
        return await run_in_threadpool(widgets.ionote_add, request, b)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/widgets/{key}/image/{kind}/{item_id}", dependencies=[access.signed_in])
def widget_image(key: str, kind: str, item_id: str, request: Request, p: str = ""):
    """An item's picture from its app (the suite's /api/suite/items/{kind}/{id}/image), passed through: the page shows
    images from here only. A photo, a contact's face, a recipe's or a thing's picture; p names one of several
    ("preview": an ioPix photo at screen size, for the wall display)."""
    try:
        body, ctype = widgets.image(request, key, kind, item_id, p)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    return Response(body, media_type=ctype if ctype.startswith("image/") else "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


# ------------------------------------------------------------------ the wall display on a device (app/wall.py)

def _wall(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    except wall.PairError as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/wall/feed", dependencies=[access.signed_in])
def wall_feed(request: Request, tz: str = ""):
    """Everything the wall display shows, in one compact answer for a device of its own (devices/tab5-wall): the time
    zone (IANA and POSIX), the weather and its next hours, today's and the coming days' events (times as epoch
    seconds, the place before its first comma), birthdays, today's tasks, the Home Assistant entities on the wall, the
    photos to show and what the viewer may change. tz: the device's zone (IANA), else the server's. A part is null when
    its app is not there or did not answer (errors says why)."""
    return _wall(wall.feed, request, tz)


@router.get("/api/wall/photo/{photo_id}.jpg", dependencies=[access.signed_in])
def wall_photo(photo_id: str, request: Request, w: int = 1280, h: int = 720):
    """An ioPix photo cut to fill w × h (at most 1920 × 1200), as a baseline JPEG."""
    body = _wall(wall.photo, request, photo_id, w, h)
    return Response(body, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/api/wall/tasks/{task_id}/done", dependencies=[access.signed_in])
def wall_task_done(task_id: str, request: Request):
    """Ticks off one of today's tasks in ioTask, as the viewer."""
    return _wall(wall.task_done, request, task_id)


@router.post("/api/wall/photos/{photo_id}/favorite", dependencies=[access.signed_in])
async def wall_favorite(photo_id: str, request: Request):
    """Body {on: bool (default true)}: the photo in (or out of) the viewer's ioPix favorites."""
    b = await json_body(request)
    return await run_in_threadpool(_wall, wall.favorite, request, photo_id, b.get("on", True) is not False)


@router.post("/api/wall/pair", dependencies=[access.public])
async def wall_pair(request: Request):
    """A device asks to be let in: {label?} → {code, token, approveUrl, expires, every}. It shows the code (and a QR
    code of approveUrl) and asks GET /api/wall/pair/{token} every `every` seconds."""
    try:
        b = await json_body(request)
    except HTTPException:
        b = {}
    return wall.pair_start(b.get("label") or "", wall.base_url(request))


@router.get("/api/wall/pair/{token}", dependencies=[access.public])
def wall_pair_poll(token: str):
    """202 {waiting: true} until someone approves the code; then once {password, name}: the device's own ioStart app
    password; 404 when the code expired."""
    got = _wall(wall.pair_poll, token)
    if got is None:
        return Response('{"waiting": true}', status_code=202, media_type="application/json")
    return got


@router.get("/api/wall/pair/code/{code}", dependencies=[access.signed_in])
def wall_pair_info(code: str):
    """The approval page (#/pair/<code>): the device waiting for this code, {code, label, age}."""
    return _wall(wall.pair_info, code)


@router.post("/api/wall/pair/code/{code}", dependencies=[access.signed_in])
def wall_pair_approve(code: str, request: Request):
    """The signed-in person lets the device in: it gets an app password of theirs (Settings › Account lists it)."""
    return _wall(wall.pair_approve, code, request.state.user)


# ------------------------------------------------------------------ TRMNL e-ink screens (app/trmnl.py, app/trmnlpush.py)

def _trmnl_state(request: Request, got: dict) -> dict:
    return {**got, **trmnlserver.state(request.state.user), "server": wall.base_url(request)}


@router.get("/api/trmnl", dependencies=[access.signed_in])
def trmnl_settings(request: Request):
    """Settings › TRMNL: the screens this person may put on a TRMNL, which of them the start page pushes and how the
    last push went, their time zone and clock, the address TRMNL reaches the start page at (for the plugin files),
    their TRMNL devices that ask this server itself (app/trmnlserver.py) and the address such a device is given."""
    return _trmnl_state(request, trmnlpush.state(request.state.user))


@router.put("/api/trmnl", dependencies=[access.signed_in])
async def trmnl_save(request: Request):
    """{tz?, clock? (12|24), hooks?: {screen: webhook URL | ''}}: which screens the start page pushes to TRMNL's cloud
    and where. The first address makes the app password they are read with; the last one removed revokes it."""
    b = await json_body(request)
    return _trmnl_state(request, await run_in_threadpool(trmnlpush.configure, request.state.user, b))


# A TRMNL device set to this server (app/trmnlserver.py). It has no account and cannot pass Cloudflare Access: the four
# below answer without a sign-in (main.py: is_open), to a device's own key. The paths are TRMNL's firmware's.

def _device(fn, *a):
    try:
        return fn(*a)
    except trmnlserver.NotFound as e:
        return JSONResponse({"status": 404, "message": str(e), "detail": str(e)}, status_code=404)


@router.get("/api/setup", dependencies=[access.public])
def trmnl_device_setup(request: Request):
    """A TRMNL device's first question (header ID: its MAC address): its key, and the code its screen shows until
    someone types it in Settings › TRMNL. {status: 200, api_key, friendly_id, image_url, message}."""
    return _device(trmnlserver.setup, request.headers, prefix.base_url(request))


@router.get("/api/display", dependencies=[access.public])
def trmnl_device_display(request: Request):
    """What a TRMNL device shows next (headers ID and Access-Token, and what it says of its battery and signal):
    {status: 0, image_url, filename, refresh_rate, ...}, as TRMNL's firmware reads it."""
    return _device(trmnlserver.display, request.headers, prefix.base_url(request))


@router.get("/api/current_screen", dependencies=[access.public])
def trmnl_device_current(request: Request):
    """What a TRMNL device shows now, without moving its playlist on (headers ID and Access-Token): for a client that
    only looks, as TRMNL's own apps do. {status: 200, image_url, filename, refresh_rate, ...}."""
    return _device(trmnlserver.current, request.headers, prefix.base_url(request))


@router.post("/api/log", dependencies=[access.public])
async def trmnl_device_log(request: Request):
    """A TRMNL device's own log lines (headers ID and Access-Token): the last few are kept with the device."""
    try:
        b = await json_body(request)
    except HTTPException:
        b = {}
    return _device(lambda: trmnlserver.add_log(request.headers, b) or {"status": 200})


@router.get("/api/trmnl/image/{key}.png", dependencies=[access.public])
def trmnl_device_image(key: str):
    """The picture an answer of /api/display named (the key in its address is its secret, new with every answer)."""
    got = _device(trmnlserver.image, key)
    return got if isinstance(got, JSONResponse) else Response(got, media_type="image/png", headers={"Cache-Control": "no-store"})


def _mine(fn, *a):
    try:
        return fn(*a)
    except trmnlserver.NotFound as e:
        raise HTTPException(404, str(e))


@router.post("/api/trmnl/devices", dependencies=[access.signed_in])
async def trmnl_device_claim(request: Request):
    """{code}: the signed-in person takes the TRMNL device whose screen shows this code; it shows their screens from
    its next look."""
    b = await json_body(request)
    return await run_in_threadpool(_mine, trmnlserver.claim, request.state.user, b.get("code"))


@router.put("/api/trmnl/devices/{dev_id}", dependencies=[access.signed_in])
async def trmnl_device_save(dev_id: int, request: Request):
    """{name?, refresh? (seconds), bits? (1|2|4), playlist? [{layout, screens}], pair? (true: let the device ask for a
    new key for ten minutes, after a reset)}."""
    b = await json_body(request)
    return await run_in_threadpool(_mine, trmnlserver.configure, request.state.user, dev_id, b)


@router.delete("/api/trmnl/devices/{dev_id}", dependencies=[access.signed_in])
def trmnl_device_remove(dev_id: int, request: Request):
    _mine(trmnlserver.remove, request.state.user, dev_id)
    return {"ok": True}


@router.get("/api/trmnl/devices/{dev_id}/preview.png", dependencies=[access.signed_in])
def trmnl_device_preview(dev_id: int, request: Request, at: int = 0, layout: str = "", screens: str = ""):
    """What the device shows, drawn now: entry `at` of its playlist, or (while it is edited) `layout` with `screens`
    (comma-separated, one for each place of the layout)."""
    body = _mine(trmnlserver.preview, request.state.user, dev_id, at, layout, [k for k in screens.split(",") if k])
    return Response(body, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/api/trmnl/{screen}/send", dependencies=[access.signed_in])
def trmnl_send(screen: str, request: Request):
    """Push this screen now (Settings › TRMNL's Send now): {at, ok, error}."""
    if screen not in trmnl.SCREENS:
        raise HTTPException(404, "No such TRMNL screen")
    got = trmnlpush.push(request.state.user["id"], only=screen, force=True)
    if screen not in got:
        raise HTTPException(400, "This screen is not pushed: add its TRMNL webhook address first")
    return got[screen]


@router.get("/api/trmnl/{screen}/plugin.zip", dependencies=[access.signed_in])
def trmnl_plugin(screen: str, request: Request, mode: str = "poll"):
    """The screen as a TRMNL private plugin, the zip TRMNL's Import new takes. mode poll: TRMNL (its cloud, or a
    TRMNL server of your own) asks the start page, with an app password typed in TRMNL's form; push: the start page
    sends it (strategy webhook). No password or key is in the file."""
    if screen not in trmnl.SCREENS:
        raise HTTPException(404, "No such TRMNL screen")
    body = trmnl.plugin_zip(screen, "push" if mode == "push" else "poll", wall.base_url(request))
    return Response(body, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="iosuite-trmnl-{screen}{"-push" if mode == "push" else ""}.zip"'})


@router.get("/api/trmnl/{screen}", dependencies=[access.signed_in])
def trmnl_data(screen: str, request: Request, tz: str = "", clock: str = "12"):
    """What a TRMNL plugin shows (its polling URL): the screen's data, flat and already worded, as the person signed in
    (an ioStart app password as Bearer, for TRMNL). tz: their time zone (TRMNL fills it in: trmnl.user.time_zone_iana);
    clock: 12 or 24. Screens: today, calendar, tasks, docs, health, money."""
    try:
        return trmnl.build(request, screen, tz, clock == "24")
    except trmnl.NoScreen:
        raise HTTPException(404, "No such TRMNL screen (today, calendar, tasks, docs, health, money)")


# the server (version, updates, the log, restart): iosuite_shared's server_router, mounted in main.py
