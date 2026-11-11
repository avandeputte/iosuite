"""Suite administration: everything in the Shared ioSuite database, seen and changed from one place by a suite admin.

Accounts (with their role in every app), app passwords of every account in every app, sessions, the keys and tokens
every app keeps (iosuite_shared.credentials; never their values), and the suite's apps with the per-app access settings
(default_role, require_login). `Auth.admin_router()` serves it at /api/suite-admin/*
(suite admins only); the start page's Settings › Security and Global settings are its screen.

The apps are the registered ones (ios_apps) plus any app key that only shows up in roles, settings or app passwords
(an app that is not installed any more, or has not started since the registry came in).
"""
import re
import time

from iosuite_shared import apppasswords, credentials, db, sessions, suite, users
from iosuite_shared.errors import Invalid

APP_KEY = re.compile(r"^[a-z0-9_-]{1,32}$")
DEFAULT_ROLES = ("none", "viewer", "member", "editor")  # what an app gives an account without a role there ("admin" by default is never wanted)
PHOTO_APP = "iopix"  # the app whose People an account can be linked to: the person in photos, its face the account's picture


def clean_app(app) -> str:
    app = str(app or "").strip().lower()
    if not APP_KEY.match(app) or app.startswith("_"):
        raise Invalid("Unknown app")
    return app


def _forget_caches():
    users.invalidate()
    sessions.invalidate()
    apppasswords.forget()
    from iosuite_shared import proxyauth
    proxyauth.forget_identities()


# ---- apps
def apps() -> list:
    """Every app the database knows: the registry's fields (registered: False for one known only from its data), its
    defaultRole and requireLogin, and how many explicit roles and app passwords it has."""
    reg = {a["app"]: a for a in suite.apps()}
    keys = set(reg)
    for sql in ("SELECT DISTINCT app FROM ios_user_roles", "SELECT DISTINCT app FROM ios_app_passwords",
                "SELECT DISTINCT app FROM ios_settings WHERE app != '' AND LEFT(app, 1) != '_'", "SELECT DISTINCT app FROM ios_credentials WHERE app != ''"):
        keys |= {r["app"] for r in db.q(sql)}
    roles = {r["app"]: r["n"] for r in db.q("SELECT app, count(*) AS n FROM ios_user_roles GROUP BY app")}
    pws = {r["app"]: r["n"] for r in db.q("SELECT app, count(*) AS n FROM ios_app_passwords GROUP BY app")}
    creds = {r["app"]: r["n"] for r in db.q("SELECT app, count(*) AS n FROM ios_credentials WHERE name NOT LIKE 'link\\_%' GROUP BY app")}
    out = []
    for k in keys:
        a = dict(reg.get(k) or {"app": k, "name": k, "description": None, "version": None, "color": None, "icon": None, "url": None,
                                "lastSeen": None})
        a["registered"] = k in reg
        a["defaultRole"] = users.default_role(k)  # none in an admin tool, which is for suite admins only
        a["requireLogin"] = db.get_setting("require_login", "0", k) == "1"
        a["roles"], a["appPasswords"], a["credentials"] = roles.get(k, 0), pws.get(k, 0), creds.get(k, 0)
        out.append(a)
    return sorted(out, key=lambda a: (not a["registered"], (a["name"] or a["app"]).lower(), a["app"]))


def set_app(app: str, default_role=None, require_login=None) -> dict:
    """Change an app's access settings (None: unchanged)."""
    app = clean_app(app)
    if default_role is not None:
        if suite.is_admin_tool(app):
            raise Invalid("An admin tool is for suite admins only; it has no default role")
        if default_role not in DEFAULT_ROLES:
            raise Invalid("The default role is none, viewer, member or editor")
        db.set_setting("default_role", "" if default_role == users.DEFAULT_ROLE else default_role, app)  # member is the default: no row
    if require_login is not None:
        db.set_setting("require_login", "1" if require_login else "", app)
    _forget_caches()
    return next((a for a in apps() if a["app"] == app), {"app": app})


def forget_app(app: str, data: bool = False) -> bool:
    """Take an app off the registry; with data, also its roles, its access settings, its app passwords and its keys and
    tokens (an app that was uninstalled for good). It registers again if it starts."""
    app = clean_app(app)
    gone = suite.forget(app)
    db.ex("DELETE FROM ios_updates WHERE app = %s", (app,))  # what it said about its version; it writes it again if it starts
    if data:
        for pid, uid in [(r["id"], r["user_id"]) for r in db.q("SELECT id, user_id FROM ios_app_passwords WHERE app = %s", (app,))]:
            apppasswords.delete(uid, pid)
        gone = (db.ex("DELETE FROM ios_user_roles WHERE app = %s", (app,)) > 0) or gone
        gone = (db.ex("DELETE FROM ios_settings WHERE app = %s", (app,)) > 0) or gone
        gone = (credentials.remove(app) > 0) or gone
        _forget_caches()
    return gone


# ---- accounts
def accounts() -> list:
    """Every account people use (never the apps' own service accounts, which the suite manages itself): the shared fields, `roles` (the explicit role per app), `effective` (the role it holds in every
    known app: the row, else the app's default; suite admin: admin; admin tool: none for the others; passwordless: member
    at most), its number of app
    passwords and sessions, and when it was last seen in any session."""
    keys = [a["app"] for a in apps()]
    pw = {r["user_id"]: r["n"] for r in db.q("SELECT user_id, count(*) AS n FROM ios_app_passwords GROUP BY user_id")}
    now = int(time.time())
    ses = {r["user_id"]: r for r in db.q("SELECT user_id, count(*) AS n, max(coalesce(last_seen_at, renewed_at)) AS seen "
                                         "FROM ios_sessions WHERE expires_at > %s GROUP BY user_id", (now,))}
    roles = {}
    for r in db.q("SELECT user_id, app, role FROM ios_user_roles"):
        roles.setdefault(r["user_id"], {})[r["app"]] = r["role"]
    defaults = {k: users.default_role(k) for k in keys}
    tools = suite.admin_tools()
    photo = {r["user_id"]: db.json_load(r["value"]) for r in db.q(
        "SELECT user_id, value FROM ios_user_data WHERE app = %s AND name = 'person'", (PHOTO_APP,))}
    out = []
    for u in users.list_users():
        mine = roles.get(u["id"], {})
        eff = {}
        for k in keys:
            eff[k] = users.effective(mine.get(k, defaults[k]), u["suiteAdmin"], u["passwordless"], k in tools)
        s = ses.get(u["id"]) or {}
        out.append({**u, "roles": mine, "effective": eff, "appPasswords": pw.get(u["id"], 0), "sessions": int(s.get("n") or 0),
                    "lastSeen": s.get("seen"), "photoPerson": photo.get(u["id"])})
    return sorted(out, key=lambda u: u["name"].lower())


def person(user_id: int) -> dict | None:
    """The account, when it is one people use; None for no account or an app's own service account (users.service_account),
    which the suite makes and looks after itself, so this panel never shows or changes it."""
    u = users.get(user_id)
    return u if u and not u.get("service") else None


def account(user_id: int) -> dict | None:
    return next((u for u in accounts() if u["id"] == user_id), None)


def set_roles(me, user_id: int, roles: dict):
    """{app: role | None}: None (or "default") removes the row, so the app's default role applies."""
    if not isinstance(roles, dict):
        raise Invalid("roles is {app: role}")
    for app, role in roles.items():
        app = clean_app(app)
        if role in (None, "", "default"):
            db.ex("DELETE FROM ios_user_roles WHERE user_id = %s AND app = %s", (user_id, app))
        elif suite.is_admin_tool(app):
            raise Invalid(f"{(suite.get(app) or {}).get('name') or app} is an admin tool, for suite admins only")
        else:
            users.update(user_id, role=str(role), app=app)  # the checks: a known role, a password for more than member


def create(me, body: dict) -> dict:
    roles = body.get("roles") or {}
    u = users.create(str(body.get("name", ""))[:64], str(body.get("password") or "")[:1024], email=str(body.get("email") or ""),
                     display_name=str(body.get("displayName") or ""), suite_admin=bool(body.get("suiteAdmin")))
    try:
        if body.get("listed") is not None:
            users.update(u["id"], listed=bool(body["listed"]))
        set_roles(me, u["id"], roles)
        if body.get("photoPerson"):
            set_photo_person(u["id"], body["photoPerson"])
    except ValueError:
        users.delete(u["id"])
        raise
    _forget_caches()
    return account(u["id"])


def update(me, user_id: int, body: dict) -> dict:
    """Change an account: name, displayName, email, listed, suiteAdmin, password ('' removes it: one-click, member at most),
    roles {app: role | None}, photoPerson (the person in ioPix's People, a tag id; None unlinks)."""
    if not person(user_id):
        raise LookupError("No such user")
    own = bool(me) and me.get("id") == user_id
    if own and body.get("suiteAdmin") is False:
        raise Invalid("You cannot take away your own suite admin while signed in; another suite admin can")
    if own and body.get("password") == "":
        raise Invalid("You cannot remove your own password")
    pw = body.get("password")
    users.update(user_id, name=body.get("name"), email=body.get("email"), display_name=body.get("displayName"),
                 listed=None if body.get("listed") is None else bool(body["listed"]),
                 suite_admin=None if body.get("suiteAdmin") is None else bool(body["suiteAdmin"]),
                 password=None if pw is None else str(pw)[:1024])
    if body.get("roles") is not None:
        set_roles(me, user_id, body["roles"])
    if "photoPerson" in body:
        set_photo_person(user_id, body["photoPerson"])
    _forget_caches()
    return account(user_id)


# ---- the person in photos: an account linked to someone in ioPix's People. Kept here, as ioPix's "person" value of
# the account (ios_user_data); ioPix shows that face on its sign-in screen and menu, and "Photos of me".
def set_photo_person(user_id: int, person):
    if person in (None, "", 0):
        users.set_value(user_id, PHOTO_APP, "person", None)
        return
    try:
        person = int(person)
    except (TypeError, ValueError):
        raise Invalid("photoPerson is a person id from ioPix's People")
    users.set_value(user_id, PHOTO_APP, "person", person)


def photo_people(reader: str) -> dict:
    """The people in ioPix's People, read from ioPix as the reader (iosuite_shared.links):
    {available, people: [{id, name, photos}], error?}. Not available while ioPix is not in the suite."""
    from iosuite_shared import links
    if not links.available(PHOTO_APP):
        return {"available": False, "people": []}
    try:
        r = links.json(reader, PHOTO_APP, "/api/people/list")
    except Exception as e:  # noqa: BLE001  ioPix is away, or older than its /api/people/list
        return {"available": True, "people": [], "error": f"ioPix did not answer: {e}"}
    return {"available": True, "people": [p for p in (r.get("people") if isinstance(r, dict) else r) or [] if isinstance(p, dict)]}


def photo_face(reader: str, person: int) -> bytes:
    """The face ioPix shows for a person (a JPEG). LookupError when there is none."""
    from iosuite_shared import links
    import urllib.error
    try:
        with links.get(reader, PHOTO_APP, f"/face/{int(person)}", accept="image/jpeg") as r:
            return r.read()
    except (RuntimeError, urllib.error.URLError, OSError) as e:
        raise LookupError(f"No face: {e}")


def delete(me, user_id: int):
    if not person(user_id):
        raise LookupError("No such user")
    if me and me.get("id") == user_id:
        raise Invalid("You cannot delete your own account while signed in")
    users.delete(user_id)
    _forget_caches()


# ---- app passwords
# What people's app passwords can be: everything, or sync only. READ is the service accounts' own (iosuite_shared.links).
PERSON_SCOPES = ("", apppasswords.DAV)


def app_passwords(user_id: int = None, app: str = None) -> list:
    """Every app password of the accounts people use (never the secret; the service accounts' own are left out): id, userId, userName, app, appName, label, scope ('' everything, 'dav' sync only), created, lastUsed."""
    where, args = ["u.service IS NULL"], []
    if user_id is not None:
        where.append("p.user_id = %s"); args.append(user_id)
    if app:
        where.append("p.app = %s"); args.append(clean_app(app))
    rows = db.q("SELECT p.id, p.user_id, p.app, p.label, p.scope, p.created_at, p.last_used_at, u.name, u.display_name, a.name AS app_name "
                "FROM ios_app_passwords p JOIN ios_users u ON u.id = p.user_id LEFT JOIN ios_apps a ON a.app = p.app"
                + " WHERE " + " AND ".join(where) + " ORDER BY lower(u.name), p.app, p.created_at", tuple(args))
    return [{"id": r["id"], "userId": r["user_id"], "userName": r["name"], "displayName": r["display_name"] or r["name"], "app": r["app"],
             "appName": r["app_name"] or r["app"], "label": r["label"], "scope": r["scope"] or "", "created": r["created_at"], "lastUsed": r["last_used_at"]} for r in rows]


def new_app_password(user_id: int, app: str, label: str, scope: str = "") -> dict:
    """A new app password for an account in an app (shown once)."""
    u = person(user_id)
    if not u:
        raise LookupError("No such user")
    if scope not in PERSON_SCOPES:
        raise Invalid(f"Unknown app password scope: {scope!r}")
    if u["passwordless"]:
        raise Invalid("A one-click account cannot have app passwords; give it a password first")
    app = clean_app(app)
    pw = apppasswords.create(user_id, app, (label or "Device").strip()[:128] or "Device", scope or "")
    return {"password": pw, "name": u["name"], "app": app, "scope": scope or ""}


def set_app_password_scope(pid: int, scope: str):
    """Change what an app password reaches: '' everything, 'dav' the app's sync protocols only."""
    r = db.one("SELECT p.app, p.prefix FROM ios_app_passwords p JOIN ios_users u ON u.id = p.user_id WHERE p.id = %s AND u.service IS NULL", (pid,))
    if not r:
        raise LookupError("No such app password")
    if (scope or "") not in PERSON_SCOPES:
        raise Invalid(f"Unknown app password scope: {scope!r}")
    apppasswords.set_scope(r["app"], r["prefix"], scope or "")
    apppasswords.forget()


def revoke_app_password(pid: int):
    r = db.one("SELECT p.user_id FROM ios_app_passwords p JOIN ios_users u ON u.id = p.user_id WHERE p.id = %s AND u.service IS NULL", (pid,))
    if not r:
        raise LookupError("No such app password")
    apppasswords.delete(r["user_id"], pid)


# ---- keys and tokens
SUITE = "_suite"  # the whole suite's keys (app '') in the addresses: /api/suite-admin/keys/_suite/<name>


def _suite_keys():
    from iosuite_shared import links
    credentials.declare("", links.SUITE_KEYS)  # the whole suite's: listed before any app needed them


def _key_app(app) -> str:
    return "" if app in ("", SUITE) else clean_app(app)


def keys(app: str = None) -> list:
    """Every key and token the apps keep (never the value): see credentials.listing. The whole suite's have app ''."""
    _suite_keys()
    return credentials.listing(None if app is None else _key_app(app))


def set_key(me, app: str, name: str, value) -> dict:
    """Replace a key's value ('' or None clears it). Only keys an app declared can be set here (not the app
    passwords iosuite_shared.links keeps: revoke those as app passwords)."""
    app, name = _key_app(app), str(name or "")
    _suite_keys()
    if name.startswith("link_") or not db.one("SELECT 1 AS x FROM ios_credentials WHERE app = %s AND name = %s", (app, name)):
        raise LookupError("No such key")
    if value is not None and not isinstance(value, str):
        raise Invalid("The value is text")
    credentials.put(app, name, value, by=(me or {}).get("name"))
    return next(k for k in credentials.listing(app) if k["name"] == name)


# ---- sessions
def end_sessions(user_id: int, session_id: str = None):
    if not person(user_id):
        raise LookupError("No such user")
    if session_id:
        sessions.end_one(user_id, session_id)
    else:
        sessions.end_all(user_id)


def overview() -> dict:
    return {"apps": apps(), "users": accounts(), "roles": list(users.ROLES), "defaultRoles": list(DEFAULT_ROLES),
            "scopes": list(PERSON_SCOPES)}
