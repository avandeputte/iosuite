"""Apple configuration profiles (.mobileconfig): an iPhone, iPad or Mac gets an app's sync account (CalDAV, CardDAV)
in one install. Each app that syncs (PROFILE_APPS) offers its own profile, and, where the account may use more than
one of them, one profile for all of them at once (the suite profile, router()).

A profile carries an app password per app (an app password belongs to one app), each with the DAV scope: a lost phone
or a leaked profile file reaches the sync protocols and nothing else. With password "ask" it carries none and the
device asks for one per account while installing.

The download is a short-lived link (/profile/<token>/<file>) as well as a form post: the app on the Home Screen hands
a download to a separate browser sheet that has none of its cookies, and a link it can open by itself works. The link
gives the same profile, with the same app passwords, for a few minutes, in the process that made it.
"""
import plistlib
import re
import secrets
import time
import uuid
from urllib.parse import urlsplit

from iosuite_shared import apppasswords, suite

# app -> (protocol, what the account holds): the apps a profile can set up, in no particular order (the suite's order
# comes from suite.apps())
PROFILE_APPS = {"iocalendar": ("caldav", "Calendars"), "iocontact": ("carddav", "Contacts"), "iotask": ("caldav", "Reminders")}
LINK_SECONDS = 600
MEDIA_TYPE = "application/x-apple-aspen-config"


def _slug(s: str, dots: bool = False) -> str:
    return re.sub(r"[^A-Za-z0-9.-]" if dots else r"[^A-Za-z0-9-]", "-", s or "")


def ident(app: str, base: str, user: dict) -> str:
    """The profile's identifier for an app at an address and an account (net.iothing.<app>.<host>.<name>): the same
    install twice replaces itself instead of adding a second account."""
    return f"net.iothing.{app}.{_slug(urlsplit(base).hostname or 'localhost', True)}.{_slug(user['name'])}"


def file_name(app: str, user: dict) -> str:
    return f"{app}-{_slug(user['name'])}.mobileconfig"


def label_of(label: str) -> str:
    return (label or "iPhone").strip()[:48] or "iPhone"


def new_password(user: dict, app: str, label: str) -> str:
    """A DAV-only app password of this app for the profile, named after the device ("iPhone (profile)")."""
    return apppasswords.create(user["id"], app, f"{label_of(label)} (profile)", apppasswords.DAV)


def account(app: str, name: str, base: str, user: dict, secret: str | None) -> dict:
    """The payload that adds the account of one app (PROFILE_APPS) at `base` (scheme://host[:port][/path]) to the
    device, named `name` (ioCalendar) on it; secret: its app password, None to have the device ask."""
    kind, what = PROFILE_APPS[app]
    key = "CalDAV" if kind == "caldav" else "CardDAV"
    parts = urlsplit(base)
    ssl = parts.scheme == "https"
    p = {"PayloadType": f"com.apple.{kind}.account", "PayloadVersion": 1, "PayloadIdentifier": f"{ident(app, base, user)}.{kind}",
         "PayloadUUID": str(uuid.uuid4()).upper(), "PayloadDisplayName": f"{what} ({key})",
         f"{key}AccountDescription": name, f"{key}HostName": parts.hostname or "localhost",
         f"{key}Port": parts.port or (443 if ssl else 80), f"{key}UseSSL": ssl,
         f"{key}PrincipalURL": f"{parts.path.rstrip('/')}/dav/principals/{user['name']}/", f"{key}Username": user["name"]}
    if secret:
        p[f"{key}Password"] = secret
    return p


def build(identifier: str, display: str, description: str, organization: str, content: list) -> bytes:
    return plistlib.dumps({"PayloadType": "Configuration", "PayloadVersion": 1, "PayloadIdentifier": identifier,
                           "PayloadUUID": str(uuid.uuid4()).upper(), "PayloadDisplayName": display,
                           "PayloadDescription": description, "PayloadOrganization": organization,
                           "PayloadRemovalDisallowed": False, "PayloadContent": content})


def asks(secret) -> str:
    return "" if secret else " The device asks for an app password while installing."


# ---- the suite profile
def _address(a: dict) -> str | None:
    for u in (a.get("url"), a.get("internalUrl")):
        if u and urlsplit(u).scheme in ("http", "https") and urlsplit(u).hostname not in (None, "127.0.0.1", "::1"):  # a device cannot use the server's loopback
            return u.rstrip("/")
    return None


def suite_apps(user: dict, here: str, here_base: str) -> list:
    """The apps a suite profile would set up for this account: [{app, name, base}], in the suite's order: each app of
    PROFILE_APPS that is in the suite's list, that the account may use, and whose address is known (this app's own is
    the one it is reached at). None for an account without app passwords (one-click)."""
    if not user or user.get("passwordless"):
        return []
    out = []
    for a in suite.visible(user):
        if a["app"] not in PROFILE_APPS:
            continue
        base = here_base if a["app"] == here else _address(a)
        if base:
            out.append({"app": a["app"], "name": a["name"] or a["app"], "base": base})
    return out


def suite_profile(user: dict, here: str, here_base: str, label: str, password: str) -> tuple:
    """(bytes, file name) of the profile with every account of suite_apps(), each with its own new DAV-only app
    password (password "new") or none ("ask"). ValueError when there are fewer than two (the app's own profile is
    the one to use then)."""
    apps = suite_apps(user, here, here_base)
    if len(apps) < 2:
        raise ValueError("A profile for all apps needs two or more apps that sync")
    content, secret = [], None
    for a in apps:
        secret = new_password(user, a["app"], label) if password == "new" else None
        content.append(account(a["app"], a["name"], a["base"], user, secret))
    who = user.get("displayName") or user["name"]
    names = [a["name"] for a in apps]
    listed = ", ".join(names[:-1]) + " and " + names[-1]
    body = build(ident("iosuite", here_base, user), f"ioSuite for {who}",
                 f"Adds {who}'s {listed} accounts to this device." + asks(secret), "ioSuite", content)
    return body, file_name("iosuite", user)


# ---- the download
def response(body: bytes, name: str):
    from fastapi.responses import Response
    return Response(body, media_type=MEDIA_TYPE, headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})


_links: dict = {}  # token -> (expires, bytes, file name)


def link(body: bytes, name: str) -> dict:
    """{url, expiresIn}: the profile behind a link that needs no cookie, for LINK_SECONDS."""
    now = time.monotonic()
    for t in [t for t, v in _links.items() if v[0] < now]:
        _links.pop(t, None)
    token = secrets.token_urlsafe(24)
    _links[token] = (now + LINK_SECONDS, body, name)
    return {"url": f"/profile/{token}/{name}", "expiresIn": LINK_SECONDS}


def router(auth, base_url):
    """GET /profile/<token>/<file> (the links, open: the token is the secret; the app lists /profile/ among its open
    prefixes and keeps the token out of its request log) and the suite profile: GET /api/apple-profile/suite (the
    apps it would set up: offered only when there are two or more), POST /api/apple-profile/suite (the form post) and
    POST /api/apple-profile/suite/link ({label, password} -> {url}). base_url(request): the address this app is
    reached at."""
    from fastapi import APIRouter, Form, HTTPException, Request
    from fastapi.responses import Response
    from starlette.concurrency import run_in_threadpool

    from iosuite_shared.access import json_body
    r = APIRouter()
    here = auth.app

    def make(request: Request, label: str, password: str):
        try:
            return suite_profile(auth.current_user(request), here, base_url(request), label, password)
        except ValueError as e:
            raise HTTPException(409, str(e))

    @r.get("/api/apple-profile/suite", dependencies=[auth.access.signed_in])
    def api_suite_apps(request: Request):
        return {"apps": [{"app": a["app"], "name": a["name"]} for a in suite_apps(auth.current_user(request), here, base_url(request))]}

    @r.post("/api/apple-profile/suite", dependencies=[auth.access.signed_in])
    def api_suite_profile(request: Request, label: str = Form("iPhone"), password: str = Form("new")):
        return response(*make(request, label, password))

    @r.post("/api/apple-profile/suite/link", dependencies=[auth.access.signed_in])
    async def api_suite_profile_link(request: Request):
        b = await json_body(request)
        return link(*await run_in_threadpool(make, request, str(b.get("label") or ""), str(b.get("password") or "new")))

    @r.get("/profile/{token}/{name}", include_in_schema=False)
    def download(token: str, name: str):
        hit = _links.get(token)
        if not hit or hit[0] < time.monotonic():
            _links.pop(token, None)
            return Response(f"This download link has expired. Make a new one in {auth.label}: Settings › Apps and devices.",
                            status_code=404, media_type="text/plain; charset=utf-8", headers={"Cache-Control": "no-store"})
        return response(hit[1], hit[2])
    return r
