"""Updating every app of the suite from one place: the start page's Settings › Global settings › Apps, or an AI
assistant over the start page's MCP endpoint.

The apps do not call each other for this. A suite admin leaves a request in the Shared ioSuite database (ios_updates:
one row per app), and every app watches its own row (Updater.start_daily starts the watch): "check" asks GitHub
whether there is a newer version, "update" runs the app's own update.sh, exactly as Settings › Server does. Each app
writes back what it knows (the installed version and commit, the newest version on GitHub, whether it can update
itself, how the last update went), which is what overview() shows.

    suiteupdates.request("update", ["iocalendar", "ionotes"], by="alex")   # or apps=None: every app with an update waiting
    suiteupdates.overview()                                                 # one line per app
"""
import time

from iosuite_shared import db, suite
from iosuite_shared.errors import Invalid

ACTIONS = ("check", "update")
WATCH_S = 10     # how often an app looks at its row
STALE_S = 3600   # a request nobody picked up within the hour: the app is not running (or too old to know about this)
FIELDS = ("installed", "git_commit", "latest", "status", "state", "message", "can_run", "docker", "checked_at")


def publish(app: str, **fields) -> None:
    """What an app knows about itself (any of FIELDS), written to its row. Never raises: the database may be away."""
    fields = {k: v for k, v in fields.items() if k in FIELDS}
    try:
        cols = ["app", "updated_at", *fields]
        vals = [app, int(time.time()), *fields.values()]
        db.ex(f"INSERT INTO ios_updates ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
              f"ON DUPLICATE KEY UPDATE {', '.join(f'{c} = VALUES({c})' for c in cols[1:])}", tuple(vals))
    except Exception:  # noqa: BLE001
        pass


def claim(app: str) -> str | None:
    """The action waiting for this app ('check' or 'update'), taken off its row so that only one process runs it; None
    when there is none (or the database is away)."""
    try:
        r = db.one("SELECT action FROM ios_updates WHERE app = %s", (app,))
        if not r or not r["action"]:
            return None
        n = db.ex("UPDATE ios_updates SET action = NULL WHERE app = %s AND action = %s", (app, r["action"]))
        return r["action"] if n else None
    except Exception:  # noqa: BLE001
        return None


def row(app: str) -> dict | None:
    try:
        return db.one("SELECT * FROM ios_updates WHERE app = %s", (app,))
    except Exception:  # noqa: BLE001
        return None


def _out(a: dict, r: dict | None) -> dict:
    r = r or {}
    now = time.time()
    pending = r.get("action") if r.get("action") and now - (r.get("requested_at") or 0) < STALE_S else None
    return {"app": a["app"], "name": a["name"], "version": r.get("installed") or a.get("version"), "commit": r.get("git_commit"),
            "latest": r.get("latest"), "status": r.get("status"),  # current | update | error, from the app's last check
            "checked": r.get("checked_at"), "canUpdate": bool(r.get("can_run")), "docker": bool(r.get("docker")),
            "state": r.get("state") or None,  # running | ok | failed: the last update
            "message": r.get("message") or None, "pending": pending, "requestedBy": r.get("requested_by") if pending else None,
            "requested": r.get("requested_at") if pending else None, "updated": r.get("updated_at"),
            "lastSeen": a.get("lastSeen"), "watching": bool(r)}


def overview() -> list:
    """Every registered app: its version and commit, the newest version on GitHub and when that was checked, whether
    it can update itself (not in Docker, update.sh present), the last update (state running/ok/failed and its message),
    and a request still waiting (pending). watching False: the app has never written its row (not running, or on an
    iosuite-shared from before this)."""
    rows = {r["app"]: r for r in db.q("SELECT * FROM ios_updates")}
    return [_out(a, rows.get(a["app"])) for a in suite.apps()]


def request(action: str, apps=None, by: str = None) -> list:
    """Leave `action` ('check' or 'update') for the apps named (keys such as 'iocalendar'), or with apps None: 'check'
    for every app, 'update' for every app whose last check found a newer version. The names of the apps asked."""
    if action not in ACTIONS:
        raise Invalid("action must be check or update")
    known = {a["app"] for a in suite.apps()}
    if apps is None:
        if action == "check":
            targets = sorted(known)
        else:
            targets = sorted(o["app"] for o in overview() if o["status"] == "update")
    else:
        targets = []
        for k in apps:
            k = str(k or "").strip().lower()
            if k not in known:
                raise Invalid(f"No app {k!r} in the suite (the apps: {', '.join(sorted(known))})")
            if k not in targets:
                targets.append(k)
    now = int(time.time())
    for k in targets:
        db.ex("INSERT INTO ios_updates (app, action, requested_at, requested_by, updated_at) VALUES (%s, %s, %s, %s, %s) "
              "ON DUPLICATE KEY UPDATE action = VALUES(action), requested_at = VALUES(requested_at), requested_by = VALUES(requested_by)",
              (k, action, now, (by or "")[:64] or None, now))
    return targets


def wait_checked(apps, since: float, timeout: float = 25.0) -> None:
    """Wait (at most `timeout` seconds) until every app named has checked GitHub after `since`, or stopped watching."""
    end = time.time() + timeout
    while time.time() < end:
        rows = {r["app"]: r for r in db.q("SELECT app, checked_at, action FROM ios_updates")}
        if all((rows.get(k) or {}).get("checked_at") and rows[k]["checked_at"] >= int(since) for k in apps):
            return
        time.sleep(1)
