"""Subscription links: an address with a secret in it, for apps that cannot sign in (a calendar app subscribed to
ioCalendar's events or ioContact's birthdays). Anyone holding the link reads what it gives, so it is kept like an app
password: in the Shared ioSuite database, only a SHA-256 of it (passwords.token_hash), shown once when it is made,
named, and stopped one at a time (an Apple profile gets its own, so a lost phone costs one link, not all of them).
A link belongs to one person and one app, and reads as that person with their role there: an account whose access to
the app was taken away gets nothing from its links, and deleting the account removes them (ON DELETE CASCADE).

The app's routes: GET /api/feeds (your links: name, made, last used), POST /api/feeds {label} -> the new link's
addresses, once, DELETE /api/feeds/<id>. What the addresses are is the app's (router(auth, addresses)); the secret
sits in the path (/ics/<secret>/..., /cal/<secret>/...), so the request log never shows it (updates.SECRET_PATHS).
"""
import secrets
import time

from iosuite_shared import db
from iosuite_shared.errors import Invalid
from iosuite_shared.passwords import token_hash

MAX_PER_PERSON = 50   # per app: a page that makes one on every click cannot fill the table
USED_EVERY_S = 3600   # last_used_at is written at most once an hour (a calendar app polls every few minutes)


def create(user_id: int, app: str, label: str) -> str:
    """A new link's secret, returned this once (only its hash is kept)."""
    n = db.one("SELECT count(*) AS n FROM ios_feed_tokens WHERE user_id = %s AND app = %s", (user_id, app))["n"]
    if n >= MAX_PER_PERSON:
        raise Invalid(f"You have {n} subscription links here: stop some you no longer use first")
    secret = secrets.token_urlsafe(24)
    db.ex("INSERT INTO ios_feed_tokens (user_id, app, label, token_hash, created_at) VALUES (%s, %s, %s, %s, %s)",
          (user_id, app, (label or "Subscription").strip()[:128] or "Subscription", token_hash(secret), int(time.time())))
    return secret


def user_id(app: str, secret: str) -> int | None:
    """The account a link of this app belongs to, or None (unknown, stopped, another app's)."""
    if not secret or len(secret) > 128:
        return None
    r = db.one("SELECT id, user_id, last_used_at FROM ios_feed_tokens WHERE token_hash = %s AND app = %s", (token_hash(secret), app))
    if not r:
        return None
    now = int(time.time())
    if not r["last_used_at"] or now - r["last_used_at"] > USED_EVERY_S:
        db.ex("UPDATE ios_feed_tokens SET last_used_at = %s WHERE id = %s", (now, r["id"]))
    return r["user_id"]


def list_for(user_id: int, app: str) -> list:
    return [{"id": r["id"], "label": r["label"], "created": r["created_at"], "lastUsed": r["last_used_at"]}
            for r in db.q("SELECT id, label, created_at, last_used_at FROM ios_feed_tokens WHERE user_id = %s AND app = %s ORDER BY created_at, id",
                          (user_id, app))]


def delete(user_id: int, app: str, fid: int) -> int:
    return db.ex("DELETE FROM ios_feed_tokens WHERE id = %s AND user_id = %s AND app = %s", (fid, user_id, app))


def router(auth, addresses):
    """GET/POST /api/feeds, DELETE /api/feeds/<id>, for the signed-in person. addresses(request, user, secret) -> the
    app's links made with that secret: [{"name", "url"}, ...] (the first one is what "Open in my calendar app" opens)."""
    from fastapi import APIRouter, HTTPException, Request
    from starlette.concurrency import run_in_threadpool

    from iosuite_shared.access import json_body
    r = APIRouter()
    app = auth.app

    def me(request: Request) -> dict:
        return auth.current_user(request)

    @r.get("/api/feeds", dependencies=[auth.access.signed_in])
    def api_feeds(request: Request):
        return {"feeds": list_for(me(request)["id"], app)}

    @r.post("/api/feeds", dependencies=[auth.access.signed_in])
    async def api_feed_new(request: Request):
        b = await json_body(request)
        u = me(request)
        secret = await run_in_threadpool(create, u["id"], app, str(b.get("label") or ""))
        return {"links": addresses(request, u, secret), "feeds": await run_in_threadpool(list_for, u["id"], app)}

    @r.delete("/api/feeds/{fid}", dependencies=[auth.access.signed_in])
    def api_feed_stop(fid: int, request: Request):
        if not delete(me(request)["id"], app, fid):
            raise HTTPException(404)
        return {"ok": True}
    return r
