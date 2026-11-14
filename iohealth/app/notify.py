"""Notifications from ioHealth (iosuite_shared.push): "goal reached" when a sync from the phone brings today's value of
one of the account's daily goals (Settings › Goals, "at least") up to it, once per goal and day, for the people who
turned notifications on.

Only goals whose numbers mean the same in every unit system are looked at (steps, minutes, kilocalories, hours and
the activity rings): a goal is kept in the units the web app shows, which the server does not know.
"""
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from iosuite_shared import push

from app import config, db, webapi

log = logging.getLogger("app.notify")
APP = "iohealth"
UNITS = {"count", "min", "kcal", "h"}
NAMES = {"activity_move": "Move ring", "activity_exercise": "Exercise ring", "activity_stand": "Stand ring",
         "step_count": "Steps", "apple_exercise_time": "Exercise", "active_energy_burned": "Active energy",
         "flights_climbed": "Flights climbed", "apple_stand_time": "Stand time", "mindful_session": "Mindful minutes"}
UNIT_WORDS = {"count": "", "min": " min", "kcal": " kcal", "h": " h"}


def _zone():
    try:
        return ZoneInfo(config.TZ or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _goals(uid: int) -> list:
    r = db.one("SELECT value FROM hlt_user_settings WHERE user_id = %s AND name = 'goals'", (uid,))
    try:
        goals = json.loads(r[0]) if r else []
    except (TypeError, ValueError):
        return []
    return [g for g in goals if isinstance(g, dict)] if isinstance(goals, list) else []


def _num(v) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.1f}"


def after_sync(uid: int, now: datetime = None) -> int:
    """After a sync of this account: the goals reached today that were not announced yet."""
    if uid not in {u["id"] for u in push.recipients("health")}:
        return 0
    loc = _zone()
    now = (now or datetime.now(loc)).astimezone(loc)
    start = datetime(now.year, now.month, now.day, tzinfo=loc)
    sent = 0
    for g in _goals(uid):
        t = str(g.get("type") or "")
        try:
            target = float(g.get("value"))
        except (TypeError, ValueError):
            continue
        if g.get("dir", "min") != "min" or target <= 0 or t == "sleep_analysis":
            continue
        key = f"health:goal:{t}:{start.date()}"
        if push.was_sent(uid, key):
            continue
        info = webapi.type_info(uid, t)
        if not info or info["unit"] not in UNITS or not (info["cumulative"] or info["kind"] == "ring"):
            continue
        s = webapi.series_for(uid, t, db.naive(start), db.naive(start + timedelta(days=1)), "day", loc)
        v = s["points"][-1]["v"] if s["points"] else None
        if v is None or v < target:
            continue
        name = NAMES.get(t) or t.replace("_", " ").capitalize()
        unit = UNIT_WORDS.get(info["unit"], "")
        sent += push.notify(uid, "health", f"{name}: goal reached", f"{_num(v)}{unit} today, goal at least {_num(target)}{unit}",
                            url=push.link(APP, f"#/metrics?types={t}&range=30d"), once=key, tag=f"goal-{t}")
    return sent


def after_sync_quietly(uid: int) -> None:
    try:
        after_sync(uid)
    except Exception:  # noqa: BLE001 - a goal alert never fails a sync
        log.exception("goal notifications after the sync of account %s", uid)
