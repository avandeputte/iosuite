"""Outside your usual: the last seven days of a figure next to the four weeks before them, the account's own.

Three figures, each in units that mean the same everywhere: resting heart rate (up by so many beats a minute), heart
rate variability (down by so many percent) and sleep (down by so many minutes a night). How far is the account's own
(Settings › Goals and alerts, kept as "alerts" in hlt_user_settings; 0 turns one off). Plain averages: nothing is
learned or guessed.

The dashboard's Heads-up card shows what is found (GET /api/usual); notify.py sends it as a notification once, on the
day it begins.
"""
import json
import math
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request

from app import access, db, webapi

router = APIRouter()

WEEK, BEFORE = 7, 28              # days: the week looked at, and the weeks it is held against
NEED_WEEK, NEED_BEFORE = 3, 7     # days with a value it takes on each side, or there is nothing to say
QUIET = 7                         # days a figure was within the usual before today for today to be where it begins
DEFAULTS = {"rhr": 5, "hrv": 15, "sleep": 45}  # bpm up, percent down, minutes a night down (static/js/core.js ALERT_DEFAULTS)
TYPES = {"rhr": "resting_heart_rate", "hrv": "heart_rate_variability_sdnn", "sleep": "sleep_analysis"}


def _settings(uid: int) -> tuple:
    """(how far each figure may go, the sections the person hid)."""
    saved = {}
    for name, value in db.q("SELECT name, value FROM hlt_user_settings WHERE user_id = %s AND name IN ('alerts', 'hiddenSections')", (uid,)):
        try:
            saved[name] = json.loads(value)
        except (TypeError, ValueError):
            pass
    alerts = saved.get("alerts") if isinstance(saved.get("alerts"), dict) else {}
    limits = {}
    for k, default in DEFAULTS.items():
        try:  # as the settings page reads it: empty is the default
            v = float(alerts[k]) if alerts.get(k) not in (None, "") else default
        except (TypeError, ValueError):
            v = default
        limits[k] = v if math.isfinite(v) else default
    hidden = saved.get("hiddenSections")
    return limits, set(hidden) if isinstance(hidden, list) else set()


def daily(uid: int, key: str, today: date, days: int, loc) -> list:
    """`days` daily values of a figure, the last one today's; None for a day without one."""
    end = datetime(today.year, today.month, today.day, tzinfo=loc)
    frm, to = webapi.local_add_days(end, 1 - days, loc), webapi.local_add_days(end, 1, loc)
    points = webapi.series_for(uid, TYPES[key], db.naive(frm), db.naive(to), "day", loc)["points"]
    by_day = {datetime.fromtimestamp(p["t"], loc).date(): p["v"] for p in points if p.get("v") is not None}
    return [by_day.get(today - timedelta(days=i)) for i in range(days - 1, -1, -1)]


def _avg(values: list) -> tuple:
    xs = [v for v in values if v is not None]
    return (sum(xs) / len(xs) if xs else None), len(xs)


def off(key: str, values: list, limit: float) -> dict | None:
    """Whether the last week of `values` (daily, the last one the day looked at) left the four weeks before it by
    `limit` or more: {key, now, usual}, or None."""
    now, n = _avg(values[-WEEK:])
    usual, b = _avg(values[-WEEK - BEFORE:-WEEK])
    if limit <= 0 or n < NEED_WEEK or b < NEED_BEFORE:
        return None
    if key == "rhr":
        hit = now - usual >= limit
    elif key == "hrv":
        hit = usual > 0 and (usual - now) / usual * 100 >= limit
    else:
        hit = (usual - now) * 60 >= limit
    return {"key": key, "now": now, "usual": usual} if hit else None


def _hm(hours: float) -> str:
    m = int(round(hours * 60))
    return f"{m // 60} h {m % 60:02d}"


def _words(f: dict) -> dict:
    now, usual = f["now"], f["usual"]
    if f["key"] == "rhr":
        return {"title": "Resting heart rate is up",
                "body": f"{now:.0f} bpm this week against your usual {usual:.0f}. Illness, stress, alcohol or too little recovery can do that.",
                "href": "#/metrics?types=resting_heart_rate,heart_rate_variability_sdnn&range=90d"}
    if f["key"] == "hrv":
        return {"title": "Heart rate variability is down",
                "body": f"{now:.0f} ms this week against your usual {usual:.0f} ms (−{(usual - now) / usual * 100:.0f}%).",
                "href": "#/metrics?types=heart_rate_variability_sdnn,resting_heart_rate&range=90d"}
    return {"title": "Sleep is down",
            "body": f"{_hm(now)} a night this week against your usual {_hm(usual)} ({round((usual - now) * 60)} min less).",
            "href": "#/sleep"}


def findings(uid: int, loc, now: datetime = None) -> list:
    """What is outside the account's usual today: [{key, title, body, href, now, usual, new}]. `new`: it begins today
    (within the usual on each of the QUIET days before), which is when it is worth a notification."""
    today = (now or datetime.now(loc)).astimezone(loc).date()
    limits, hidden = _settings(uid)
    out = []
    for key in TYPES:
        if limits[key] <= 0 or (key == "sleep" and "sleep" in hidden):
            continue
        values = daily(uid, key, today, WEEK + BEFORE + QUIET, loc)
        f = off(key, values, limits[key])
        if f:
            f["new"] = not any(off(key, values[:-i], limits[key]) for i in range(1, QUIET + 1))
            out.append({**f, **_words(f)})
    return out


@router.get("/api/usual", dependencies=[access.signed_in])
def usual(request: Request):
    """What is outside your usual today: resting heart rate, heart rate variability and sleep over the last seven days
    against the four weeks before. tz. [{key, title, body, href, now, usual, new}]; empty when all is as usual."""
    return findings(webapi.uid_of(request), webapi.location(request))
