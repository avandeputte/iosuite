"""ioHealth's answer to the suite's tile endpoint (iosuite_shared.suiteitems): today's steps and rings, last night's
sleep, the week's steps."""
import datetime as dt
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from iosuite_shared.suiteitems import Provider, Unavailable


def _zone(tz: str):
    try:
        return ZoneInfo(tz) if tz else dt.timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return dt.timezone.utc


def tile(local, tz, n, kind):
    """{steps, rings: {move, moveGoal, exercise, exerciseGoal, stand, standGoal} | null, sleep: {date, asleep, inBed,
    start, end} | null, week: [{date, steps}]} for the viewer."""
    zone = _zone(tz)
    today = dt.datetime.now(zone).date()
    day, since = today.isoformat(), (today - dt.timedelta(days=6)).isoformat()
    q = {"from": day, "to": day, "tz": tz or None}
    steps = rings = sleep = None
    week: list = []
    failed = []
    series, nights, activity = local.together(
        lambda: local.get("/api/series", {**q, "from": since, "type": "step_count", "bucket": "day"}),
        # last night: the night that ended this morning (ioHealth names a night by the day it ends on)
        lambda: local.get("/api/sleep", {**q, "from": (today - dt.timedelta(days=1)).isoformat()}),
        lambda: local.get("/api/activity", q))
    for r in (series, nights, activity):
        if isinstance(r, Exception) and not isinstance(r, Unavailable):
            raise r
    if isinstance(series, Unavailable):
        failed.append(series)
    else:
        pts = series.get("points") or []
        by_day = {dt.datetime.fromtimestamp(p["t"], zone).date().isoformat(): p.get("v") for p in pts if p.get("t") is not None}
        week = [{"date": d, "steps": round(by_day[d]) if by_day.get(d) is not None else None}
                for d in ((dt.date.fromisoformat(since) + dt.timedelta(days=i)).isoformat() for i in range(7))]
        steps = week[-1]["steps"] if week and week[-1]["date"] == day else None
        if steps is None and by_day.get(day) is not None:
            steps = round(by_day[day])
    if not isinstance(nights, Unavailable):  # sleep is a bonus: the tile shows without it
        nights = nights if isinstance(nights, list) else nights.get("items", [])
        last = next((x for x in reversed(nights) if x.get("asleep")), None)
        if last:
            sleep = {"date": last.get("date"), "asleep": round(last["asleep"]), "inBed": round(last.get("inBed") or 0),
                     "start": last.get("start"), "end": last.get("end")}
    if isinstance(activity, Unavailable):
        failed.append(activity)
    else:
        rows = activity if isinstance(activity, list) else activity.get("items", [])
        if rows:
            rings = {k: rows[-1].get(k) for k in ("move", "moveGoal", "exercise", "exerciseGoal", "stand", "standGoal")}
    if len(failed) == 2:  # one of the two missing still shows the other
        raise failed[0]
    return {"steps": steps, "rings": rings, "sleep": sleep, "week": week}


PROVIDER = Provider(tile=tile)
