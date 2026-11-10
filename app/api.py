"""The REST API (JSON) the start page uses. OpenAPI docs at /api/docs. Who may call a route is declared on it (app/access.py).

Clients authenticate with the web session cookie (the suite's, shared by every io app on the domain), HTTP Basic or
`Authorization: Bearer <app password>`, as in the other io apps."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.concurrency import run_in_threadpool
import asyncio
import json

from app import access, apps, bookmarks, config, homeassistant as ha, layout, status as appstatus, weather, widgets

router = APIRouter()


def _base(request: Request) -> str:
    """The page's own address, for links: PUBLIC_URL, else as reached (through the proxy's headers)."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    return f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', request.url.netloc)}"


# ------------------------------------------------------------------ the apps

@router.get("/api/apps", dependencies=[access.signed_in])
def list_apps(request: Request):
    """The tiles: every app this person may use, with its name, icon, colour and address (an admin tool only for its
    admins). Hidden ones are left out (Settings lists them)."""
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    u = request.state.user
    return {"items": apps.tiles(host, u), "photoStrip": apps.photo_strip(), "layout": layout.get(u["id"])}


@router.get("/api/apps/status", dependencies=[access.signed_in])
async def apps_status(request: Request):
    """Each app's /api/status, asked with the viewer's sign-in: {items: {key: {ok, version, update, why}}}. `update` is
    set when the app says one is waiting (it tells admins only). Cached a minute."""
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
    try:
        return layout.save(u["id"], await request.json())
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/api/home/settings", dependencies=[access.admin])
def home_settings(request: Request):
    """Admins: what the home page shows everyone by default (the photo strip under the tiles)."""
    return {"photoStrip": apps.photo_strip()}


@router.post("/api/home/settings", dependencies=[access.admin])
async def home_save(request: Request):
    """Admins. Body: {photoStrip: rediscover | onthisday | off}."""
    b = await request.json()
    if not isinstance(b, dict):
        raise HTTPException(400, "An object, please")
    try:
        if "photoStrip" in b:
            apps.set_photo_strip(b["photoStrip"])
    except ValueError as e:
        raise HTTPException(400, str(e))
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


@router.get("/api/weather/settings", dependencies=[access.admin])
def weather_settings(request: Request):
    return weather.settings()


@router.post("/api/weather/settings", dependencies=[access.admin])
async def weather_save(request: Request):
    """Admins. Body: {key?, locationKey?, locationName?, units?}."""
    u = request.state.user
    b = await request.json()
    try:
        weather.save(b if isinstance(b, dict) else {}, by=u.get("name"))
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
    try:
        b = await request.json()
    except ValueError:
        raise HTTPException(400, "JSON, please")
    return await run_in_threadpool(_ha, ha.set_entity, entity_id, b)


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
    b = await request.json()
    _ha(ha.save, b if isinstance(b, dict) else {}, by=u.get("name"))
    return ha.settings()


@router.post("/api/ha/test", dependencies=[access.admin])
async def ha_test(request: Request):
    """Admins. Body: {url?, token?}: tries them (the saved ones when empty) → {ok, name, version, entities}."""
    b = await request.json()
    b = b if isinstance(b, dict) else {}
    return await run_in_threadpool(_ha, ha.test, str(b.get("url") or ""), str(b.get("token") or ""))


# ------------------------------------------------------------------ bookmarks

@router.get("/api/bookmarks", dependencies=[access.signed_in])
def list_bookmarks(request: Request):
    return {"groups": bookmarks.groups()}


@router.get("/api/bookmarks/status", dependencies=[access.signed_in])
async def bookmarks_status(request: Request):
    """Each bookmark pinged from this server: {items: {link id: {ok, status}}}; ok is null for an address that cannot
    be pinged (mailto:…). Cached five minutes."""
    return {"items": await run_in_threadpool(appstatus.of_bookmarks)}


def _bm(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except bookmarks.BadBookmark as e:
        raise HTTPException(400, str(e))


@router.post("/api/bookmarks/groups", dependencies=[access.editor])
async def add_group(request: Request):
    """Editors. {name}"""
    b = await request.json()
    return _bm(bookmarks.add_group, b.get("name"))


@router.patch("/api/bookmarks/groups/{gid}", dependencies=[access.editor])
async def rename_group(gid: int, request: Request):
    b = await request.json()
    _bm(bookmarks.rename_group, gid, b.get("name"))
    return {"ok": True}


@router.delete("/api/bookmarks/groups/{gid}", dependencies=[access.editor])
def delete_group(gid: int, request: Request):
    _bm(bookmarks.delete_group, gid)
    return {"ok": True}


@router.post("/api/bookmarks/groups/order", dependencies=[access.editor])
async def order_groups(request: Request):
    """Editors. {ids: [group id, ...]} in the order wanted."""
    b = await request.json()
    _bm(bookmarks.order_groups, [int(x) for x in b.get("ids") or []])
    return {"ok": True}


@router.post("/api/bookmarks/groups/{gid}/links", dependencies=[access.editor])
async def add_link(gid: int, request: Request):
    """Editors. {name, href, abbr?, description?, icon?}"""
    b = await request.json()
    return _bm(bookmarks.add_link, gid, b.get("name"), b.get("href"), b.get("abbr"), b.get("description"), b.get("icon"))


@router.post("/api/bookmarks/groups/{gid}/order", dependencies=[access.editor])
async def order_links(gid: int, request: Request):
    """Editors. {ids: [link id, ...]} in the order wanted; a link from another group moves into this one."""
    b = await request.json()
    _bm(bookmarks.order_links, gid, [int(x) for x in b.get("ids") or []])
    return {"ok": True}


@router.patch("/api/bookmarks/links/{lid}", dependencies=[access.editor])
async def update_link(lid: int, request: Request):
    """Editors. Any of {name, href, abbr, description, icon, groupId}."""
    b = await request.json()
    return _bm(bookmarks.update_link, lid, b if isinstance(b, dict) else {})


@router.delete("/api/bookmarks/links/{lid}", dependencies=[access.editor])
def delete_link(lid: int, request: Request):
    _bm(bookmarks.delete_link, lid)
    return {"ok": True}


@router.get("/api/bookmarks/links/{lid}/icon.svg", dependencies=[access.signed_in])
def link_icon(lid: int, request: Request):
    """The SVG uploaded for a link, for everyone signed in. Cached by the browser for good: the address carries a
    version (?v=etag) that changes with the file."""
    ic = bookmarks.icon(lid)
    if not ic:
        raise HTTPException(404, "No icon")
    return Response(ic["svg"], media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": f'"{ic["etag"]}"',
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"})


@router.put("/api/bookmarks/links/{lid}/icon", dependencies=[access.editor])
async def upload_link_icon(lid: int, request: Request):
    """Editors. The body is the SVG file itself (up to 256 KB); the stored one is replaced. Returns the link."""
    data = await request.body()
    return _bm(bookmarks.set_icon, lid, data)


@router.delete("/api/bookmarks/links/{lid}/icon", dependencies=[access.editor])
def delete_link_icon(lid: int, request: Request):
    return _bm(bookmarks.clear_icon, lid)


@router.post("/api/bookmarks/import", dependencies=[access.editor])
async def import_bookmarks(request: Request):
    """Editors. {yaml, replace?}: a homepage bookmarks.yaml."""
    b = await request.json()
    return _bm(bookmarks.import_yaml, b.get("yaml") or "", bool(b.get("replace")))

# ------------------------------------------------------------------ what the tiles show (app/widgets.py)

@router.get("/api/widgets/{key}", dependencies=[access.signed_in])
def widget(key: str, request: Request, tz: str = "", kind: str = "", n: int = 0, q: str = ""):
    """A glimpse of one app for its tile, asked of the app with the viewer's own sign-in. tz: the viewer's time zone
    (IANA, e.g. Europe/Brussels), for what "today" is. For iopix, kind (onthisday | rediscover; empty: on this day
    when there are photos, else rediscover) and n (how many, up to 24) pick what the photo strip shows; for iocalendar,
    kind=week gives the coming week instead of today; for iocontacts, q searches the contacts (the search box) instead
    of listing the birthdays ahead. 404 for an app without one; 401/403 when the app refuses this account; 502 when it does not answer. The page leaves the
    tile as it is on any of these."""
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
    try:
        b = await request.json()
    except ValueError:
        raise HTTPException(400, "JSON, please")
    try:
        return await run_in_threadpool(widgets.iocalendar_add, request, b)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/widgets/iocontacts/photo/{contact_id}", dependencies=[access.signed_in])
def widget_contact_photo(contact_id: int, request: Request):
    """A contact's photo from ioContacts, passed through (for the birthdays card)."""
    try:
        body, ctype = widgets.iocontacts_photo(request, contact_id)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    return Response(body, media_type=ctype if ctype.startswith("image/") else "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/widgets/iocontacts/face/{person_id}", dependencies=[access.signed_in])
def widget_contact_face(person_id: int, request: Request):
    """A contact's ioPix face, through ioContacts (a contact linked to an ioPix person, without a photo of its own)."""
    try:
        body, ctype = widgets.iocontacts_face(request, person_id)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    return Response(body, media_type=ctype if ctype.startswith("image/") else "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/widgets/iopix/thumb/{photo_id}", dependencies=[access.signed_in])
def widget_thumb(photo_id: int, request: Request):
    """An ioPix thumbnail (square, cropped around its subject), passed through: the page shows images from here only."""
    try:
        body, ctype = widgets.iopix_thumb(request, photo_id)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    return Response(body, media_type=ctype if ctype.startswith("image/") else "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


@router.get("/api/widgets/iopix/preview/{photo_id}", dependencies=[access.signed_in])
def widget_preview(photo_id: int, request: Request):
    """An ioPix photo at screen size, passed through (the wall display's slideshow)."""
    try:
        body, ctype = widgets.iopix_preview(request, photo_id)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    return Response(body, media_type=ctype if ctype.startswith("image/") else "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


# the server (version, updates, the log, restart): iosuite_shared's server_router, mounted in main.py
