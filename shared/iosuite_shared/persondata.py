"""What a person keeps in the suite, seen and removed from one place: deleting an account (Settings › Security ›
People, in any app) also removes what that person kept in every app, after the panel showed what that is.

Each app says what it keeps for a person by setting `auth.person_data = fn`, where fn(user_id, remove) returns

    [{"what": "private calendars", "one": "private calendar", "count": 2},
     {"what": "events they added to shared calendars", "count": 5, "kept": True}]

With remove False it only counts; with remove True it removes everything not marked kept and returns the same list
(what it removed, and what it left). What the person made in something everyone shares (an event on the Family
calendar, a family recipe, a shared bookmark, a task on a shared list) is never removed: it belongs to the family, and
stays without their name once the account is gone. An app without a function keeps nothing per person.

Every app serves its own part at /api/suite-admin/person-data/{id} (GET counts, DELETE removes; suite admins only,
Auth.admin_router()). The panel, in whichever app it is open, asks every app in the suite's list (admin tools keep
nothing per person) with the suite admin's own sign-in, the way the start page's tiles ask: on localhost when the app
runs on this machine, then at its address inside the network, then at its public one (iosuite_shared.links), with the
suite's Cloudflare Access service token. An app that cannot be reached when the account is deleted is noted under
PENDING in its settings (ios_settings) and removes that person's data the next time it starts (Auth.register()).
What the Shared ioSuite database holds for the account (roles, sessions, app passwords, notification devices, the
family entry, the person in photos) goes with the account itself (ON DELETE CASCADE).
"""
import json
import logging
import threading
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from iosuite_shared import db, links, sessions, suite, users

log = logging.getLogger("iosuite_shared.persondata")
PATH = "/api/suite-admin/person-data/"
PENDING = "person_data_pending"  # ios_settings(app=<app>): JSON list of account ids whose data that app has yet to remove
COUNT_S = 30     # seconds an app may take to count (ioHealth counts a lot of rows)
REMOVE_S = 300   # and to remove; an app that takes longer finishes anyway, and is asked again at its next start
UA = "ioSuite person data"

# What the Shared ioSuite database keeps for an account, all removed with it. A table that is not there (yet) is skipped.
SHARED = (
    ("ios_user_roles", "roles in the apps", "role in the apps"),
    ("ios_sessions", "sessions", "session"),
    ("ios_app_passwords", "app passwords", "app password"),
    ("ios_push_devices", "devices with notifications", "device with notifications"),
    ("ios_user_data", "settings and links (family, person in photos, own contact card)", "setting or link (family, person in photos, own contact card)"),
)
_lock = threading.Lock()


def clean(items) -> list:
    """An app's list as the panel shows it: only what there is (count above 0)."""
    out = []
    for i in items or []:
        try:
            n = int(i.get("count") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if n > 0:
            what = i.get("one") if n == 1 and i.get("one") else i.get("what")  # "1 private list", "2 private lists"
            out.append({"what": str(what or "")[:200], "count": n, "kept": bool(i.get("kept"))})
    return out


def local(auth, user_id: int, remove: bool = False) -> list:
    """This app's part, from its own function."""
    fn = getattr(auth, "person_data", None)
    if not fn:
        return []
    items = clean(fn(int(user_id), bool(remove)))
    if remove:
        log.info("%s: removed the data of account %s: %s", auth.app, user_id,
                 ", ".join(f"{i['count']} {i['what']}" for i in items if not i["kept"]) or "nothing")
    return items


def shared_part(user_id: int) -> list:
    """What the Shared ioSuite database keeps for the account."""
    out = []
    for table, what, one in SHARED:
        try:
            n = db.one(f"SELECT count(*) AS n FROM {table} WHERE user_id = %s", (int(user_id),))["n"]
        except Exception:  # noqa: BLE001  a table this version does not have
            continue
        out.append({"what": what, "one": one, "count": n})
    return clean(out)


# ---- asking the other apps, as the suite admin
def _headers(request) -> dict:
    """The suite admin's own sign-in (the suite's session cookie, else the Authorization they came with) and the suite's
    Cloudflare Access service token."""
    h = {"User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "identity"}
    tok = request.cookies.get(sessions.COOKIE) if request is not None else None
    if tok:
        h["Cookie"] = f"{sessions.COOKIE}={tok}"
    elif request is not None and request.headers.get("authorization"):
        h["Authorization"] = request.headers["authorization"]
    try:
        h.update(links.headers("", "", sign_in=False))
    except Exception:  # noqa: BLE001  the keys store is away: no Cloudflare token
        pass
    return h


def _ask(headers: dict, app: str, method: str, user_id: int) -> list:
    """The app's part, asked over HTTP at each of its addresses in turn. RuntimeError with what went wrong."""
    bases = links.addresses(app)
    if not bases:
        raise RuntimeError("it has no address to reach it at (PUBLIC_URL or INTERNAL_URL)")
    last = None
    for base in bases:
        req = urllib.request.Request(f"{base}{PATH}{int(user_id)}", headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=REMOVE_S if method == "DELETE" else COUNT_S) as r:  # noqa: S310  http(s), from links.addresses()
                return clean(json.loads(r.read()).get("items"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise RuntimeError("it is on an older version that cannot do this")
            if e.code in (401, 403):
                raise RuntimeError(f"it did not take your sign-in ({e.code}); open it once and sign in there")
            raise RuntimeError(f"it answered {e.code}")
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = e
    raise RuntimeError(f"it did not answer ({type(last).__name__})")


def everywhere(auth, request, user_id: int, remove: bool = False) -> list:
    """Every app's part: [{app, name, items, error}] in the suite's order. This app answers itself; the others are asked
    at the same time. error: why an app could not be asked (its items are then empty)."""
    entries = [a for a in suite.apps() if not a.get("adminTool")]
    if not any(a["app"] == auth.app for a in entries) and not suite.is_admin_tool(auth.app):
        entries.insert(0, {"app": auth.app, "name": auth.label})
    headers = _headers(request)

    def one(a):
        out = {"app": a["app"], "name": a.get("name") or a["app"], "items": [], "error": None}
        try:
            out["items"] = local(auth, user_id, remove) if a["app"] == auth.app else _ask(headers, a["app"], "DELETE" if remove else "GET", user_id)
        except Exception as e:  # noqa: BLE001  one app's trouble never stops the others
            if a["app"] == auth.app:
                log.exception("%s: the data of account %s", auth.app, user_id)
            out["error"] = str(e) or type(e).__name__
        return out
    if not entries:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(entries)), thread_name_prefix="persondata") as pool:
        return list(pool.map(one, entries))


def delete_account(auth, request, me, user_id: int) -> dict:
    """Delete the account and everything the person kept in every app: {apps: [...], shared: [...]}. An app that could
    not be reached removes the data at its next start (PENDING)."""
    from iosuite_shared import admin
    admin.check_delete(me, user_id)
    shared = shared_part(user_id)
    sessions.end_all(user_id)  # nothing more arrives from the person's devices while their data goes
    apps = everywhere(auth, request, user_id, remove=True)
    admin.delete(me, user_id)
    for a in apps:
        if a["error"]:
            note_pending(a["app"], user_id)
            a["pending"] = True
    return {"apps": apps, "shared": shared}


# ---- the apps that could not be reached
def pending(app: str) -> list:
    r = db.one("SELECT value FROM ios_settings WHERE app = %s AND name = %s", (app, PENDING))
    ids = db.json_load(r["value"], []) if r else []
    return [int(i) for i in ids if isinstance(i, int)] if isinstance(ids, list) else []


def note_pending(app: str, user_id: int) -> None:
    with _lock:
        ids = pending(app)
        if int(user_id) not in ids:
            db.set_setting(PENDING, json.dumps(ids + [int(user_id)]), app)


def _done(app: str, user_id: int) -> None:
    with _lock:
        ids = [i for i in pending(app) if i != int(user_id)]
        db.set_setting(PENDING, json.dumps(ids) if ids else None, app)


def run_pending(auth) -> int:
    """Remove the data of accounts deleted while this app could not be reached (at start, from Auth.register()).
    An id whose account is still there is only dropped: nothing of a living account is ever removed here."""
    n = 0
    for uid in pending(auth.app):
        try:
            if users.get(uid) is None:
                local(auth, uid, remove=True)
                n += 1
            _done(auth.app, uid)
        except Exception:  # noqa: BLE001  tried again at the next start
            log.exception("%s: could not remove the data of deleted account %s (tried again at the next start)", auth.app, uid)
    return n
