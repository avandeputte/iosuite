"""Notifications from ioHealth (iosuite_shared.push): "goal reached" when a sync from the phone brings today's value of
one of the account's daily goals (Settings › Goals, "at least") up to it, once per goal and day, for the people who
turned notifications on.

Only goals whose numbers mean the same in every unit system are looked at (steps, minutes, kilocalories, hours and
the activity rings): a goal is kept in the units the web app shows, which the server does not know.

And on Monday, at the person's morning time (Settings › Account › Notifications), the weekly summary: last week's
steps, sleep and workouts next to the week before (weekly(), run every minute by the app).

"Today" is the person's own: the zone their phone sends when a sync starts (timeZone), or the web app's, as last seen
(webapi.remember_zone); the server's TZ only until either has been seen.
"""
import json
import logging
from datetime import datetime, timedelta

from iosuite_shared import push

from app import db, webapi

log = logging.getLogger("app.notify")
APP = "iohealth"
UNITS = {"count", "min", "kcal", "h"}
NAMES = {"activity_move": "Move ring", "activity_exercise": "Exercise ring", "activity_stand": "Stand ring",
         "step_count": "Steps", "apple_exercise_time": "Exercise", "active_energy_burned": "Active energy",
         "flights_climbed": "Flights climbed", "apple_stand_time": "Stand time", "mindful_session": "Mindful minutes"}
UNIT_WORDS = {"count": "", "min": " min", "kcal": " kcal", "h": " h"}


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
    loc = webapi.zone_of(uid)  # where the person is: their phone's or browser's zone, as last seen
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


# ------------------------------------------------------------------ the weekly summary

def _week(uid: int, start: datetime, loc) -> dict:
    """One week from `start` (a local midnight): steps a day, hours asleep a night, workouts and their time. None
    where there is nothing to go on."""
    frm, to = db.naive(start), db.naive(webapi.local_add_days(start, 7, loc))
    steps = [p["v"] for p in webapi.series_for(uid, "step_count", frm, to, "day", loc)["points"] if p.get("v")]
    nights = [p["v"] for p in webapi.sleep_series(uid, frm, to, "day", loc)["points"] if p.get("v")]
    works = webapi.workout_list(uid, frm, to)
    return {"steps": sum(steps) / 7 if steps else None,  # a day of the week, days without a step count as none
            "sleep": sum(nights) / len(nights) if nights else None,  # a night slept, over the nights there is sleep for
            "workouts": len(works), "workoutMin": sum(w["duration"] for w in works) / 60}


def _hm(minutes: float) -> str:
    m = int(round(minutes))
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def _lines(now: dict, before: dict) -> list:
    out = []
    if now["steps"] is not None:
        line = f"Steps: {_num(now['steps'])} a day"
        if before["steps"]:
            pct = round((now["steps"] - before["steps"]) / before["steps"] * 100)
            line += ", the same as the week before" if pct == 0 else f", {abs(pct)}% {'more' if pct > 0 else 'fewer'} than the week before"
        out.append(line)
    if now["sleep"] is not None:
        line = f"Sleep: {_hm(now['sleep'] * 60)} a night"
        if before["sleep"] is not None:
            d = round((now["sleep"] - before["sleep"]) * 60)
            line += ", the same as the week before" if abs(d) < 5 else f", {_hm(abs(d))} {'more' if d > 0 else 'less'}"
        out.append(line)
    if now["workouts"] or before["workouts"]:
        n, b = now["workouts"], before["workouts"]
        line = f"Workouts: {n}" + (f", {_hm(now['workoutMin'])}" if n else "")
        if n != b:
            line += f" ({abs(n - b)} {'more' if n > b else 'fewer'} than the week before)"
        elif n:
            line += " (as many as the week before)"
        out.append(line)
    return out


def summary(uid: int, monday: datetime, loc) -> tuple | None:
    """(title, body) of the summary sent on `monday` (its local midnight), or None when last week holds nothing."""
    last = webapi.local_add_days(monday, -7, loc)
    now, before = _week(uid, last, loc), _week(uid, webapi.local_add_days(monday, -14, loc), loc)
    if now["steps"] is None and now["sleep"] is None and not now["workouts"]:
        return None
    end = webapi.local_add_days(monday, -1, loc)
    span = f"{last.day} {last:%b} to {end.day} {end:%b}"
    return f"Your week in health, {span}", "\n".join(_lines(now, before))


def weekly(now: datetime = None) -> int:
    """Monday, at each person's morning time in their own zone: last week's summary, once."""
    sent = 0
    for u in push.recipients("health_week"):
        uid = u["id"]
        loc = webapi.zone_of(uid)
        local = (now or datetime.now(loc)).astimezone(loc)
        if local.weekday() != 0 or not push.is_morning(uid, local.replace(tzinfo=None)):
            continue
        monday = datetime(local.year, local.month, local.day, tzinfo=loc)
        key = f"health:week:{monday.date()}"
        if push.was_sent(uid, key):
            continue
        msg = summary(uid, monday, loc)
        if not msg:
            push.claim(uid, key)  # nothing to say this week, and nothing to work out again this morning
            continue
        sent += push.notify(uid, "health_week", msg[0], msg[1], url=push.link(APP, "#/"), once=key, tag="health-week")
    return sent
