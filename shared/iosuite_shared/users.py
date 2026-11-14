"""Accounts: one per person for the whole suite, plus their role in each app and their per-app data.

Roles per app, each including the one before it:
- none: no access there.
- viewer: read-only. Sees what is shared with everyone (the Family calendar, the photo library); keeps nothing of
  its own and changes nothing.
- member: keeps their own private things (calendars, lists, address books, notes, health data, favourites) and sees
  the shared ones without changing them.
- editor: also changes what is shared with everyone.
- admin: also the app's settings.
An account without a row for an app holds the app's default_role setting (member unless an admin changes it).
suite_admin is admin in every app and manages accounts. An admin tool (ioDNS, ioBackup: suite.is_admin_tool) is for
suite admins only: everybody else is none there, whatever row or default says otherwise (an app's own service
account keeps the role iosuite_shared.links gave it).
A passwordless account (hash '') signs in with one click on the LAN and is never more than a member anywhere.

Until the first account exists every app is open, as before (a fresh install is not locked out).
"""
import json
import re
import threading
import time

from iosuite_shared import db
from iosuite_shared.passwords import burn, check_password, hash_password, needs_rehash
from iosuite_shared.errors import Invalid

ROLES = ("none", "viewer", "member", "editor", "admin")
APP_ROLES = ("viewer", "member", "editor", "admin")  # what an admin picks for an account in an app ("none" takes the app away)
RANK = {"none": 0, "viewer": 1, "member": 2, "editor": 3, "admin": 4}
DEFAULT_ROLE = "member"  # an app's default_role when no admin changed it
PASSWORDLESS_MAX = "member"  # the most a one-click account (no password) is anywhere
NO_PASSWORD = "Set a password first; an account without one can be a member at most"


def _capped(role: str) -> bool:
    """Whether the role is more than a one-click account may hold."""
    return RANK.get(role, 0) > RANK[PASSWORDLESS_MAX]
COLS = "id, name, display_name, email, hash, suite_admin, listed, created_at, last_login_at, service"

_cache = {"any": None, "any_at": 0.0}
CACHE_S = 3.0


def invalidate():
    _cache.update(any=None, any_at=0.0)
    from iosuite_shared import family, sessions
    sessions.invalidate()
    family.forget()  # names and accounts show in the family list


def init() -> bool:
    """The tables, and the admin named by ADMIN_USER / ADMIN_PASSWORD on a first start with no accounts yet. When the
    Shared ioSuite database cannot be reached the app still starts: False, db.error says why, and every request that needs an
    account is answered 503 until the database is back (the middleware retries)."""
    from iosuite_shared import config
    import logging
    try:
        db.init()
    except Exception as e:
        db.error = str(e)[:300]
        logging.getLogger("iosuite_shared").error("the Shared ioSuite database (%s:%s/%s) cannot be reached: %s", db.params()["host"], db.params()["port"], db.params()["database"], e)
        return False
    db.error = None
    if config.ADMIN_USER and config.ADMIN_PASSWORD and not any_users():
        create(config.ADMIN_USER, config.ADMIN_PASSWORD, suite_admin=True)
    return True


def any_users() -> bool:
    if _cache["any"] is not None and time.time() - _cache["any_at"] < CACHE_S:
        return _cache["any"]
    v = db.one("SELECT 1 AS x FROM ios_users WHERE service IS NULL LIMIT 1") is not None
    _cache.update(any=v, any_at=time.time())
    return v


def row(r, app: str | None = None) -> dict:
    """A users row as the dict the apps serve (never the hash). With an app: `role`, the account's role there."""
    u = {"id": r["id"], "name": r["name"], "displayName": r.get("display_name") or r["name"], "email": r.get("email") or "",
         "passwordless": not r.get("hash"), "suiteAdmin": bool(r.get("suite_admin")), "listed": bool(r.get("listed", 1)),
         "created": r.get("created_at"), "last_login": r.get("last_login_at"), "service": r.get("service") or None}
    if app is not None:
        u["role"] = role_of(u, app)
    return u


def clean_email(email) -> str:
    email = (email or "").strip().lower()
    if email and (len(email) > 191 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)):
        raise Invalid("That does not look like an email address")
    return email


def clean_name(name) -> str:
    name = (name or "").strip()
    if not name or len(name) > 64:
        raise Invalid("A user name is needed (up to 64 characters)")
    return name


def get(user_id: int, app: str | None = None):
    r = db.one(f"SELECT {COLS} FROM ios_users WHERE id = %s", (user_id,))
    return row(r, app) if r else None


def find(name_or_email: str, app: str | None = None):
    """By name, then by email (both case-insensitive)."""
    s = (name_or_email or "").strip()
    if not s:
        return None
    r = db.one(f"SELECT {COLS} FROM ios_users WHERE name = %s", (s,)) or db.one(f"SELECT {COLS} FROM ios_users WHERE email = %s", (s.lower(),))
    return row(r, app) if r else None


def list_users(app: str | None = None, services: bool = False) -> list:
    """Every account; `services` also the apps' own service accounts (see service_account), which people never use."""
    return [row(r, app) for r in db.q(f"SELECT {COLS} FROM ios_users" + ("" if services else " WHERE service IS NULL") + " ORDER BY id")]


SERVICE_SUFFIX = "-app"


def service_account(app: str) -> dict:
    """The account an app uses to read from the other apps of the suite (iosuite_shared.links): one per app, made the
    first time it is needed, named <app>-app, not on any sign-in screen, with a password nobody knows (so it signs in
    with the app passwords links makes for it, never at a sign-in screen)."""
    r = db.one(f"SELECT {COLS} FROM ios_users WHERE service = %s", (app,))
    if r:
        return row(r)
    import secrets
    name = app + SERVICE_SUFFIX
    while find(name):
        name = f"{app}{SERVICE_SUFFIX}-{secrets.token_hex(2)}"
    uid = db.ex("INSERT INTO ios_users (name, display_name, hash, suite_admin, listed, created_at, service) VALUES (%s, %s, %s, 0, 0, %s, %s)",
                (name, f"{app} (automatic)", hash_password(secrets.token_urlsafe(32)), int(time.time()), app))
    invalidate()
    return get(uid)


def accounts(app: str | None = None) -> list:
    """The sign-in picker: listed accounts with a role in this app, and whether a password is asked for."""
    out = []
    for r in db.q(f"SELECT {COLS} FROM ios_users WHERE listed = 1 ORDER BY lower(name)"):
        u = row(r, app)
        if app is None or u["role"] != "none":
            out.append({"id": u["id"], "name": u["name"], "displayName": u["displayName"], "passwordless": u["passwordless"]})
    return out


def create(name: str, password: str, role: str | None = None, app: str | None = None, email: str = "", display_name: str = "",
           suite_admin: bool = False) -> dict:
    """A new account; with app and role, that role there too. ValueError with the message to show."""
    name, email = clean_name(name), clean_email(email)
    if role is not None and role not in ROLES:
        raise Invalid("Unknown role")
    if app and role and not suite_admin:
        _not_a_tool(app)
    if password == "" and (suite_admin or _capped(role or DEFAULT_ROLE)):
        raise Invalid(NO_PASSWORD)
    if password != "" and len(password) < 8:
        raise Invalid("The password needs at least 8 characters")
    if find(name):
        raise Invalid("That user name is taken")
    if email and db.one("SELECT 1 AS x FROM ios_users WHERE email = %s", (email,)):
        raise Invalid("Another account already has that email address")
    uid = db.ex("INSERT INTO ios_users (name, display_name, email, hash, suite_admin, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                (name, (display_name or "").strip()[:128] or None, email or None, hash_password(password) if password else "", 1 if suite_admin else 0, int(time.time())))
    if app and role and not (suite_admin and _is_tool(app)):  # a suite admin is admin in an admin tool without a row
        set_role(uid, app, role)
    invalidate()
    return get(uid, app)


def update(user_id: int, name=None, password=None, email=None, display_name=None, listed=None, suite_admin=None, role=None, app=None):
    """Change the given fields (None: unchanged). A new password or a changed suite_admin ends the account's other sessions."""
    cur = db.one(f"SELECT {COLS} FROM ios_users WHERE id = %s", (user_id,))
    if not cur:
        raise Invalid("No such user")
    sets = {}
    if email is not None:
        email = clean_email(email)
        if email and db.one("SELECT 1 AS x FROM ios_users WHERE email = %s AND id != %s", (email, user_id)):
            raise Invalid("Another account already has that email address")
        sets["email"] = email or None
    if name is not None:
        name = clean_name(name)
        if db.one("SELECT 1 AS x FROM ios_users WHERE name = %s AND id != %s", (name, user_id)):
            raise Invalid("That user name is taken")
        sets["name"] = name
    if display_name is not None:
        sets["display_name"] = display_name.strip()[:128] or None
    if listed is not None:
        sets["listed"] = 1 if listed else 0
    if suite_admin is not None:
        if suite_admin and not cur["hash"] and password in (None, ""):
            raise Invalid(NO_PASSWORD)
        if not suite_admin and cur["suite_admin"] and db.one("SELECT count(*) AS n FROM ios_users WHERE suite_admin = 1 AND id != %s", (user_id,))["n"] == 0:
            raise Invalid("That is the only suite admin; make someone else one first")
        sets["suite_admin"] = 1 if suite_admin else 0
    if password is not None:
        if password == "":  # remove the password: one-click sign-in, a member at most
            still_admin = cur["suite_admin"] if suite_admin is None else suite_admin
            if still_admin or _capped(_max_role(user_id)):
                raise Invalid(NO_PASSWORD)
            sets["hash"] = ""
        else:
            if len(password) < 8:
                raise Invalid("The password needs at least 8 characters")
            sets["hash"] = hash_password(password)
    if role is not None:
        if not app:
            raise Invalid("A role needs an app")
        if role not in ROLES:
            raise Invalid("Unknown role")
        _not_a_tool(app)
        if _capped(role) and not (cur["hash"] or sets.get("hash")):
            raise Invalid(NO_PASSWORD)
    if sets:
        db.ex("UPDATE ios_users SET " + ", ".join(f"{k} = %s" for k in sets) + " WHERE id = %s", (*sets.values(), user_id))
    if role is not None:
        set_role(user_id, app, role)
    # a new password, or suite admin given or taken (a form that sends it unchanged signs nobody out)
    if "hash" in sets or ("suite_admin" in sets and bool(sets["suite_admin"]) != bool(cur["suite_admin"])):
        from iosuite_shared import sessions
        sessions.end_all(user_id)
    invalidate()
    return get(user_id, app)


def check_delete(user_id: int):
    r = db.one("SELECT suite_admin FROM ios_users WHERE id = %s", (user_id,))
    if r and r["suite_admin"] and db.one("SELECT count(*) AS n FROM ios_users WHERE suite_admin = 1")["n"] == 1:
        raise Invalid("That is the only suite admin; make someone else one first")


def delete(user_id: int):
    check_delete(user_id)
    from iosuite_shared import apppasswords
    apppasswords.forget_user(user_id)
    db.ex("DELETE FROM ios_users WHERE id = %s", (user_id,))
    invalidate()


def touch_login(user_id: int):
    db.ex("UPDATE ios_users SET last_login_at = %s WHERE id = %s", (int(time.time()), user_id))


def authenticate(name: str, password: str, app: str | None = None):
    """The account when the password is right (or the account has none), else None; constant time for an unknown name.
    The name is looked up as a user name first and as an email address only when it has an @ in it, so a user name
    that equals somebody else's address never picks their account."""
    s = (name or "").strip()
    r = db.one(f"SELECT {COLS} FROM ios_users WHERE name = %s", (s,))
    if not r and "@" in s:
        r = db.one(f"SELECT {COLS} FROM ios_users WHERE email = %s", (s.lower(),))
    if not r or r.get("service"):
        burn(password)
        return None  # a service account signs in with its app passwords only
    if r["hash"]:
        if not check_password(password, r["hash"]):
            return None
        if needs_rehash(r["hash"]):
            db.ex("UPDATE ios_users SET hash = %s WHERE id = %s", (hash_password(password), r["id"]))
    touch_login(r["id"])
    invalidate()
    return row(r, app)


# ---- roles
def default_role(app: str) -> str:
    """What an account without a row holds in the app: none in an admin tool, else the app's setting (member)."""
    from iosuite_shared import suite
    if suite.is_admin_tool(app):
        return "none"
    v = db.get_setting("default_role", DEFAULT_ROLE, app)
    return v if v in ROLES else DEFAULT_ROLE


def effective(role: str, suite_admin: bool, passwordless: bool, admin_tool: bool) -> str:
    """The role an account holds, from its row (or the default) and what the account is: a suite admin is admin
    everywhere, an admin tool is none for everybody else, a one-click account is a member at most."""
    if suite_admin:
        return "admin"
    if admin_tool:
        return "none"
    if passwordless and _capped(role):
        return PASSWORDLESS_MAX
    return role if role in RANK else "none"


def role_of(user, app: str) -> str:
    """The role this account holds in the app."""
    if not user:
        return "none"
    from iosuite_shared import suite
    if user.get("suiteAdmin"):
        return "admin"
    tool = suite.is_admin_tool(app) and not user.get("service")  # an app's own service account keeps the role links gave it
    r = None if tool else db.one("SELECT role FROM ios_user_roles WHERE user_id = %s AND app = %s", (user["id"], app))
    return effective(r["role"] if r else default_role(app), False, bool(user.get("passwordless")), tool)


def roles_of(user_id: int) -> dict:
    """{app: role} for every app the account has an explicit role in."""
    return {r["app"]: r["role"] for r in db.q("SELECT app, role FROM ios_user_roles WHERE user_id = %s", (user_id,))}


def _is_tool(app: str) -> bool:
    from iosuite_shared import suite
    return suite.is_admin_tool(app)


def _not_a_tool(app: str) -> None:
    """An admin tool takes no roles: it is for suite admins only."""
    if _is_tool(app):
        raise Invalid("This is an admin tool, for suite admins only: it takes no roles")


def set_role(user_id: int, app: str, role: str):
    if role not in ROLES:
        raise Invalid("Unknown role")
    db.ex("INSERT INTO ios_user_roles (user_id, app, role) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE role = VALUES(role)", (user_id, app, role))
    invalidate()


def _max_role(user_id: int, except_app: str = "") -> str:
    best = "none"
    for r in db.q("SELECT role FROM ios_user_roles WHERE user_id = %s AND app != %s", (user_id, except_app)):
        if RANK[r["role"]] > RANK[best]:
            best = r["role"]
    return best


def admins_of(app: str) -> int:
    """How many accounts administer the app (suite admins included)."""
    n = db.one("SELECT count(*) AS n FROM ios_users WHERE suite_admin = 1")["n"]
    n += db.one("SELECT count(*) AS n FROM ios_user_roles r JOIN ios_users u ON u.id = r.user_id WHERE r.app = %s AND r.role = 'admin' AND u.suite_admin = 0", (app,))["n"]
    return n


# ---- permissions (the "no accounts yet: open" rule included)
def is_signed_in(user) -> bool:
    return not any_users() or (user is not None and user.get("role", "viewer") != "none")


def at_least(user, role: str) -> bool:
    """Whether the account holds this role or a higher one in the app (everyone, before the first account exists)."""
    return not any_users() or (user is not None and RANK.get(user.get("role"), 0) >= RANK[role])


def is_member(user) -> bool:
    """A member or more: may keep their own private things (and change them)."""
    return at_least(user, "member")


def can_write(user) -> bool:
    """An editor or admin: may change what is shared with everyone."""
    return at_least(user, "editor")


def is_admin(user) -> bool:
    return not any_users() or (user is not None and user.get("role") == "admin")


def is_suite_admin(user) -> bool:
    return not any_users() or (user is not None and user.get("suiteAdmin"))


def require_login(app: str) -> bool:
    """Settings › Global settings › Apps › Sign-in required: nothing but the sign-in screen for visitors. On unless it
    was turned off ("0"); always on in an admin tool. Off while no account exists, or nobody could sign in."""
    return any_users() and sign_in_required(app)


def sign_in_required(app: str) -> bool:
    """The Sign-in required setting itself (whether or not an account exists yet)."""
    return _is_tool(app) or db.get_setting("require_login", "1", app) != "0"


# ---- per-user, per-app data (display settings; the ioPix person tag; the ioContact "me" contact)
def get_value(user_id: int, app: str, key: str, default=None):
    r = db.one("SELECT value FROM ios_user_data WHERE user_id = %s AND app = %s AND name = %s", (user_id, app, key))
    return db.json_load(r["value"], default) if r else default


def set_value(user_id: int, app: str, key: str, value):
    """Store one value (None removes it)."""
    if value is None:
        db.ex("DELETE FROM ios_user_data WHERE user_id = %s AND app = %s AND name = %s", (user_id, app, key))
    else:
        db.ex("INSERT INTO ios_user_data (user_id, app, name, value) VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE value = VALUES(value)",
              (user_id, app, key, json.dumps(value)))


SETTINGS_KEY = "settings"


def get_settings(user_id: int, app: str) -> dict:
    """The user's display preferences in this app (a free-form JSON object the app reads and writes)."""
    v = get_value(user_id, app, SETTINGS_KEY, {})
    return v if isinstance(v, dict) else {}


def set_settings(user_id: int, app: str, changes: dict) -> dict:
    """Merge changes into the preferences (None removes a key; keys and values are limited in size) and return the result."""
    cur = get_settings(user_id, app)
    for k, v in (changes or {}).items():
        if not isinstance(k, str) or len(k) > 64:
            continue
        if v is None:
            cur.pop(k, None)
        elif isinstance(v, (str, int, float, bool)) and len(str(v)) <= 2000:
            cur[k] = v
    set_value(user_id, app, SETTINGS_KEY, cur)
    return cur


# ---- sign-in attempts: a wrong password costs a growing wait, per address and account (in memory: a restart clears
# them; a counter also starts over once it has been quiet for LOCK_MAX after its wait ended)
_attempts = {}
_attempts_lock = threading.Lock()
LOCK_AFTER = 5
LOCK_AFTER_NAME = 20
LOCK_BASE = 30
LOCK_MAX = 15 * 60


def login_wait(key: str) -> int:
    with _attempts_lock:
        rec = _attempts.get(key)
        if not rec:
            return 0
        return max(0, int(-(-(rec[1] - time.time()) // 1)))


def login_failed(key: str, free: int = LOCK_AFTER) -> int:
    with _attempts_lock:
        if len(_attempts) > 10000:
            now = time.time()
            for k in [k for k, (n, until) in _attempts.items() if until < now - LOCK_MAX]:
                del _attempts[k]
            if len(_attempts) > 10000:
                for k in list(_attempts)[:len(_attempts) // 2]:
                    del _attempts[k]
        rec = _attempts.setdefault(key, [0, 0.0])
        if rec[0] and time.time() > rec[1] + LOCK_MAX:
            rec[0] = 0  # quiet for a quarter of an hour after its wait ended: the count starts over
        rec[0] += 1
        over = rec[0] - free
        wait = min(LOCK_MAX, LOCK_BASE * 2 ** (over - 1)) if over > 0 else 0
        rec[1] = time.time() + wait
        return wait


def login_succeeded(key: str):
    with _attempts_lock:
        _attempts.pop(key, None)


# The three counters a sign-in attempt is counted under: the pair (this visitor, this name), the name alone (a
# distributed guess at one account slows everyone who tries that name a while) and the address alone (a scan of many
# names). The routes, the HTTP Basic / bearer path (Auth._authorization) and ioContact's LDAP bind all use these three.
# Two things keep the name counter from being a way to lock somebody else out: a visitor who signed in to that
# account from this address before (_known) is not held up by it, only by its own pair's counter, so the owner's
# phone and laptop keep working while a stranger hammers the name; and a bearer token has no name, so there is no
# name counter for it (one wrong token would otherwise count against every client that sends one).
_known: dict = {}  # (visitor, name) -> when it last signed in; the pairs the name-wide wait does not apply to
KNOWN_MAX = 5000


def attempt_keys(visitor: str, name: str) -> tuple:
    n = (name or "").strip().lower()
    return f"{visitor}|{n}", (f"name|{n}" if n else None), f"addr|{visitor}"


def attempt_wait(visitor: str, name: str) -> int:
    """Seconds this visitor has to wait before another attempt at this name (0: none)."""
    k, nk, ak = attempt_keys(visitor, name)
    with _attempts_lock:
        known = k in _known
    return max(login_wait(x) for x in (k, ak) + (() if known or not nk else (nk,)))


def attempt_failed(visitor: str, name: str) -> int:
    """Count a failure; the wait it earned (0: none yet)."""
    k, nk, ak = attempt_keys(visitor, name)
    with _attempts_lock:
        known = k in _known
    name_wait = login_failed(nk, LOCK_AFTER_NAME) if nk else 0
    return max(login_failed(k), 0 if known else name_wait, login_failed(ak, LOCK_AFTER_NAME * 4))


def attempt_succeeded(visitor: str, name: str):
    """A right password: this pair's counter and the address's start over (one device with an old password must not
    hold up the others behind the same address), and the pair is remembered. The name's counter is left to run out
    by itself: it counts other people's guesses at this account, which a sync client that signs in on every request
    would otherwise wipe each time."""
    k, _, ak = attempt_keys(visitor, name)
    login_succeeded(k)
    login_succeeded(ak)
    with _attempts_lock:
        if len(_known) >= KNOWN_MAX:
            for old in sorted(_known, key=_known.get)[:KNOWN_MAX // 2]:
                del _known[old]
        _known[k] = time.time()
