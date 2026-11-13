"""Updating the suite: every app at once, from Settings › Global settings › Updates (in any app) or an AI assistant
over the start page's MCP endpoint.

The suite has one version (iosuite_shared.__version__), which every app carries, and one update: every app to the
newest version. The apps do not call each other for it. A suite admin leaves a request in the Shared ioSuite database
(ios_updates: one row per app), and every app watches its own row (Updater.start_daily starts the watch): "check" asks
GitHub whether there is a newer version, "update" runs the app's own update.sh. Each app writes back what it knows
(the installed version and commit, the newest version on GitHub, whether it can update itself, how the last update
went); summary() makes one answer for the suite out of the rows, overview() is the rows.

    suiteupdates.summary()                      # {installed, latest, status, behind, failed, apps: [...]}
    suiteupdates.request("update", by="alex")   # every app that is behind the newest version
"""
import re
import time

from iosuite_shared import db, suite
from iosuite_shared.errors import Invalid

ACTIONS = ("check", "update")
WATCH_S = 10     # how often an app looks at its row
BEAT_S = 60      # how often it says it is still there (updated_at)
ALIVE_S = 300    # a row not touched for this long: the app is not running
STALE_S = 3600   # a request nobody picked up within the hour is dropped: the app was not running
FIELDS = ("installed", "git_commit", "latest", "status", "state", "message", "can_run", "docker", "checked_at")


def version_tuple(v: str) -> tuple:
    return tuple(int(x) if x.isdigit() else 0 for x in re.split(r"[.+-]", v or "0")[:3])


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
    when there is none (or the database is away). A request from before this start that nobody picked up within the
    hour is dropped: what was asked then is not run now."""
    try:
        r = db.one("SELECT action, requested_at FROM ios_updates WHERE app = %s", (app,))
        if not r or not r["action"]:
            return None
        n = db.ex("UPDATE ios_updates SET action = NULL WHERE app = %s AND action = %s", (app, r["action"]))
        return r["action"] if n and time.time() - (r["requested_at"] or 0) < STALE_S else None
    except Exception:  # noqa: BLE001
        return None


def beat(app: str) -> None:
    """The app is running: its row says so every minute (updated_at), which is how summary() tells the apps that
    run from the ones that were stopped or removed. Never raises."""
    try:
        db.ex("UPDATE ios_updates SET updated_at = %s WHERE app = %s", (int(time.time()), app))
    except Exception:  # noqa: BLE001
        pass


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
            "lastSeen": a.get("lastSeen"), "watching": bool(r) and now - (r.get("updated_at") or 0) < ALIVE_S}


def overview() -> list:
    """Every registered app: its version and commit, the newest version on GitHub and when that was checked, whether
    it can update itself (not in Docker, update.sh present), the last update (state running/ok/failed and its message),
    and a request still waiting (pending). watching False: the app is not running (its row was not touched for five
    minutes, or it never wrote one)."""
    rows = {r["app"]: r for r in db.q("SELECT * FROM ios_updates")}
    return [_out(a, rows.get(a["app"])) for a in suite.apps()]


def summary() -> dict:
    """The suite as one thing: {installed, latest, status, checked, behind, failed, canUpdate, apps}.
    Only the apps that run count (watching). installed: the version they run (the lowest, when an update left one
    behind); latest: the newest version any of them found on GitHub; behind: the keys of the ones below it; failed:
    those of them whose last update failed. status: updating (an update is asked for or running), update (apps are
    behind), error (no app could ask GitHub), current. canUpdate: an app that is behind can update itself (the ones in
    Docker are updated by pulling the image). apps: overview(), each with `behind` (also for an app that is not
    running: it is asked too, should it be there after all)."""
    apps = overview()
    live = [a for a in apps if a["watching"] and a["version"]]
    known = [a["latest"] for a in live if a["latest"] and a["status"] != "error"]
    latest = max(known, key=version_tuple) if known else None
    for a in apps:
        a["behind"] = bool(latest and a["version"] and version_tuple(a["version"]) < version_tuple(latest))
    behind = [a for a in live if a["behind"]]
    if any(a["pending"] == "update" or a["state"] == "running" for a in live):
        status = "updating"
    elif behind:
        status = "update"
    elif live and all(a["status"] == "error" for a in live):
        status = "error"
    else:
        status = "current"
    return {"installed": min((a["version"] for a in live), key=version_tuple, default=None), "latest": latest, "status": status,
            "checked": max((a["checked"] or 0 for a in live), default=0) or None,
            "behind": [a["app"] for a in behind], "failed": [a["app"] for a in behind if a["state"] == "failed"],
            "canUpdate": any(a["canUpdate"] for a in behind), "apps": apps}


def request(action: str, by: str = None) -> list:
    """Leave `action` for the apps: 'check' for every app, 'update' for every app that is behind the newest version.
    The keys of the apps asked."""
    if action not in ACTIONS:
        raise Invalid("action must be check or update")
    if action == "check":
        targets = sorted(a["app"] for a in suite.apps())
    else:
        targets = sorted(a["app"] for a in summary()["apps"] if a["behind"])
    now = int(time.time())
    for k in targets:
        db.ex("INSERT INTO ios_updates (app, action, requested_at, requested_by, updated_at) VALUES (%s, %s, %s, %s, 0) "
              "ON DUPLICATE KEY UPDATE action = VALUES(action), requested_at = VALUES(requested_at), requested_by = VALUES(requested_by)",
              (k, action, now, (by or "")[:64] or None))
    return targets


def wait_checked(since: float, timeout: float = 25.0) -> None:
    """Wait (at most `timeout` seconds) until every app that runs has checked GitHub after `since`."""
    apps = [a["app"] for a in overview() if a["watching"]]
    end = time.time() + timeout
    while time.time() < end:
        rows = {r["app"]: r for r in db.q("SELECT app, checked_at, action FROM ios_updates")}
        if all((rows.get(k) or {}).get("checked_at") and rows[k]["checked_at"] >= int(since) for k in apps):
            return
        time.sleep(1)
