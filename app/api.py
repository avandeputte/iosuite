"""The REST API (JSON) the start page uses. OpenAPI docs at /api/docs.

Clients authenticate with the web session cookie (the suite's, shared by every io app on the domain), HTTP Basic or
`Authorization: Bearer <app password>`, as in the other io apps."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool

from app import APP_VERSION, apps, bookmarks, config, db, updates, users, weather, widgets

router = APIRouter()


def me(request: Request) -> dict:
    u = request.state.user
    if not u:
        raise HTTPException(401, "Sign in first")
    return u


def admin(request: Request) -> dict:
    u = me(request)
    if not users.is_admin(u):
        raise HTTPException(403, "Admins only")
    return u


def editor(request: Request) -> dict:
    u = me(request)
    if u.get("role") not in ("editor", "admin"):
        raise HTTPException(403, "Editors and admins only")
    return u


def _base(request: Request) -> str:
    """The page's own address, for links: PUBLIC_URL, else as reached (through the proxy's headers)."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL
    return f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', request.url.netloc)}"


@router.get("/api/status")
def status(request: Request):
    u = request.state.user
    adm = users.is_admin(u)
    return {"app": "ioSuite", "version": APP_VERSION, "commit": updates.local_commit()[:7] if u else None,
            "usersExist": users.any_users(), "user": users.public(u), "viaProxy": getattr(request.state, "via_proxy", False),
            "updateAvailable": updates.available() if adm and updates.auto_check_enabled() else None}


# ------------------------------------------------------------------ the apps

@router.get("/api/apps")
def list_apps(request: Request):
    """The tiles: every app with its name, icon, colour and address. Hidden ones are left out (Settings lists them)."""
    me(request)
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return {"items": [t for t in apps.tiles(host) if not t["hidden"]]}


@router.get("/api/apps/settings")
def apps_settings(request: Request):
    admin(request)
    return {"items": apps.settings()}


@router.post("/api/apps/settings")
async def apps_save(request: Request):
    """Admins. Body: {iopix: {url?: str, hidden?: bool}, iohealth: {...}, ...}."""
    admin(request)
    b = await request.json()
    if not isinstance(b, dict):
        raise HTTPException(400, "An object of apps, please")
    try:
        apps.save(b)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"items": apps.settings()}


# ------------------------------------------------------------------ the weather

@router.get("/api/weather")
async def get_weather(request: Request):
    """The widget: current conditions and the 5-day forecast, from the server's copy (refreshed from AccuWeather when
    it is older than 45 minutes / 6 hours). {enabled: false} until an admin sets it up."""
    me(request)
    try:
        return await run_in_threadpool(weather.current)
    except weather.WeatherError as e:
        return {"enabled": True, "error": str(e), "current": None, "forecast": None, "units": weather.settings()["units"],
                "location": weather.settings()["locationName"]}


@router.get("/api/weather/settings")
def weather_settings(request: Request):
    admin(request)
    return weather.settings()


@router.post("/api/weather/settings")
async def weather_save(request: Request):
    """Admins. Body: {key?, locationKey?, locationName?, units?}."""
    admin(request)
    b = await request.json()
    try:
        weather.save(b if isinstance(b, dict) else {})
    except weather.WeatherError as e:
        raise HTTPException(400, str(e))
    return weather.settings()


@router.get("/api/weather/search")
async def weather_search(request: Request, q: str = "", key: str = ""):
    """Admins: places matching a city name, to pick the location in Settings. `key` tries a key before it is saved."""
    admin(request)
    try:
        return {"items": await run_in_threadpool(weather.search, q, key)}
    except weather.WeatherError as e:
        raise HTTPException(400, str(e))


# ------------------------------------------------------------------ bookmarks

@router.get("/api/bookmarks")
def list_bookmarks(request: Request):
    me(request)
    return {"groups": bookmarks.groups()}


def _bm(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except bookmarks.BadBookmark as e:
        raise HTTPException(400, str(e))


@router.post("/api/bookmarks/groups")
async def add_group(request: Request):
    """Editors. {name}"""
    editor(request)
    b = await request.json()
    return _bm(bookmarks.add_group, b.get("name"))


@router.patch("/api/bookmarks/groups/{gid}")
async def rename_group(gid: int, request: Request):
    editor(request)
    b = await request.json()
    _bm(bookmarks.rename_group, gid, b.get("name"))
    return {"ok": True}


@router.delete("/api/bookmarks/groups/{gid}")
def delete_group(gid: int, request: Request):
    editor(request)
    _bm(bookmarks.delete_group, gid)
    return {"ok": True}


@router.post("/api/bookmarks/groups/order")
async def order_groups(request: Request):
    """Editors. {ids: [group id, ...]} in the order wanted."""
    editor(request)
    b = await request.json()
    _bm(bookmarks.order_groups, [int(x) for x in b.get("ids") or []])
    return {"ok": True}


@router.post("/api/bookmarks/groups/{gid}/links")
async def add_link(gid: int, request: Request):
    """Editors. {name, href, abbr?, description?, icon?}"""
    editor(request)
    b = await request.json()
    return _bm(bookmarks.add_link, gid, b.get("name"), b.get("href"), b.get("abbr"), b.get("description"), b.get("icon"))


@router.post("/api/bookmarks/groups/{gid}/order")
async def order_links(gid: int, request: Request):
    """Editors. {ids: [link id, ...]} in the order wanted; a link from another group moves into this one."""
    editor(request)
    b = await request.json()
    _bm(bookmarks.order_links, gid, [int(x) for x in b.get("ids") or []])
    return {"ok": True}


@router.patch("/api/bookmarks/links/{lid}")
async def update_link(lid: int, request: Request):
    """Editors. Any of {name, href, abbr, description, icon, groupId}."""
    editor(request)
    b = await request.json()
    return _bm(bookmarks.update_link, lid, b if isinstance(b, dict) else {})


@router.delete("/api/bookmarks/links/{lid}")
def delete_link(lid: int, request: Request):
    editor(request)
    _bm(bookmarks.delete_link, lid)
    return {"ok": True}


@router.get("/api/bookmarks/links/{lid}/icon.svg")
def link_icon(lid: int, request: Request):
    """The SVG uploaded for a link, for everyone signed in. Cached by the browser for good: the address carries a
    version (?v=etag) that changes with the file."""
    me(request)
    ic = bookmarks.icon(lid)
    if not ic:
        raise HTTPException(404, "No icon")
    return Response(ic["svg"], media_type="image/svg+xml",
                    headers={"Cache-Control": "private, max-age=31536000, immutable", "ETag": f'"{ic["etag"]}"',
                             "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"})


@router.put("/api/bookmarks/links/{lid}/icon")
async def upload_link_icon(lid: int, request: Request):
    """Editors. The body is the SVG file itself (up to 256 KB); the stored one is replaced. Returns the link."""
    editor(request)
    data = await request.body()
    return _bm(bookmarks.set_icon, lid, data)


@router.delete("/api/bookmarks/links/{lid}/icon")
def delete_link_icon(lid: int, request: Request):
    editor(request)
    return _bm(bookmarks.clear_icon, lid)


@router.post("/api/bookmarks/import")
async def import_bookmarks(request: Request):
    """Editors. {yaml, replace?}: a homepage bookmarks.yaml."""
    editor(request)
    b = await request.json()
    return _bm(bookmarks.import_yaml, b.get("yaml") or "", bool(b.get("replace")))

# ------------------------------------------------------------------ what the tiles show (app/widgets.py)

@router.get("/api/widgets/{key}")
def widget(key: str, request: Request, tz: str = ""):
    """A glimpse of one app for its tile, asked of the app with the viewer's own sign-in. tz: the viewer's time zone
    (IANA, e.g. Europe/Brussels), for what "today" is. 404 for an app without one; 401/403 when the app refuses this
    account; 502 when it does not answer. The page leaves the tile as it is on any of these."""
    me(request)
    try:
        return widgets.get(request, key, tz)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))


@router.get("/api/widgets/iopix/thumb/{photo_id}")
def widget_thumb(photo_id: int, request: Request):
    """An ioPix thumbnail (square, cropped around its subject), passed through: the page shows images from here only."""
    me(request)
    try:
        body, ctype = widgets.iopix_thumb(request, photo_id)
    except widgets.Unavailable as e:
        raise HTTPException(e.status, str(e))
    return Response(body, media_type=ctype if ctype.startswith("image/") else "image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


# ------------------------------------------------------------------ the server: version, updates

@router.get("/api/server")
def server_info(request: Request):
    """Admins: the installed version, the last update check, whether update.sh can run here, and the switches."""
    admin(request)
    return {**updates.status(), "url": _base(request), "database": f"{config.DB_HOST}:{config.DB_PORT}/{config.DB_NAME}"}


@router.post("/api/server")
async def server_action(request: Request):
    """Admins. Body: {action: check | update, ref?} or {autoCheck: bool}."""
    admin(request)
    b = await request.json()
    if "autoCheck" in b:
        if config.UPDATE_CHECK_LOCKED and b["autoCheck"]:
            raise HTTPException(400, "UPDATE_CHECK=0 in the environment keeps the daily check off")
        db.set_setting("update_check", "1" if b["autoCheck"] else "0")
        if not b["autoCheck"]:
            updates.forget_check()
    action = b.get("action")
    if action == "check":
        return await run_in_threadpool(updates.check)
    if action == "update":
        try:
            updates.run(str(b.get("ref") or ""))
        except RuntimeError as e:
            raise HTTPException(409, str(e))
        return {"started": True}
    return server_info(request)
