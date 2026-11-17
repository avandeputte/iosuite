"""Demo data (iosuite_shared.demo): three months of made-up Apple Health data for each Calloway, as their phones would
upload it (the same code path as an upload: app/upload.py's Batch). Steps, distance, active energy and heart rate
through the day, resting heart rate and HRV, sleep stages every night, weight, activity rings for the parents and Ava,
and workouts: Morgan's runs (with a route near home), Riley's rides, Ava's swims, Theo's soccer."""
import datetime as dt
import math
import random
import uuid as uuidlib
from zoneinfo import ZoneInfo

from iosuite_shared import demo

from app import db, rollup, upload

DAYS = 90
NS = uuidlib.UUID("6f1c3a52-6e0d-4f4e-9b77-2b0f3c1d0a11")  # the demo's ids are the same every time it is made

PROFILE = {  # steps a day, resting HR, weight kg (None: not weighed), a watch, sleep hours, workouts
    "morgan": {"steps": 9500, "rhr": 58, "kg": 64.0, "watch": True, "sleep": 7.2, "height": 1.70,
               "workouts": [(1, "running", 37, 6.40, 7, 30), (3, "running", 37, 5.20, 7, 0), (6, "running", 37, 10.10, 8, 0)]},
    "riley": {"steps": 7800, "rhr": 63, "kg": 82.5, "watch": True, "sleep": 6.8, "height": 1.83,
              "workouts": [(2, "cycling", 13, 24.0, 17, 30), (5, "cycling", 13, 41.0, 9, 0), (0, "traditionalStrengthTraining", 50, 0, 6, 30)]},
    "ava": {"steps": 8800, "rhr": 70, "kg": None, "watch": True, "sleep": 8.6, "height": 1.62,
            "workouts": [(3, "swimming", 46, 1.2, 18, 0)]},
    "theo": {"steps": 11500, "rhr": 78, "kg": None, "watch": False, "sleep": 9.8, "height": 1.34,
             "workouts": [(2, "soccer", 41, 0, 17, 0), (5, "soccer", 41, 0, 10, 0)]},
}


def _id(*parts) -> str:
    return str(uuidlib.uuid5(NS, "/".join(str(p) for p in parts)))


def _z(t: dt.datetime) -> str:
    return t.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sample(key, typ, kind, start, end, value=None, unit=None, text=None, source="iPhone"):
    m = {"uuid": _id(key, typ, start.isoformat()), "type": typ, "kind": kind, "start": _z(start), "end": _z(end),
         "source": {"name": source}}
    if value is not None:
        m["value"], m["unit"] = value, unit
    if text is not None:
        m["text"] = text
    return ("sample", m)


def _route(key, start: dt.datetime, km: float, seconds: float, rnd: random.Random):
    """A loop of km kilometres around home, a point every 10 seconds."""
    lat0, lon0 = demo.HOME["lat"], demo.HOME["lon"]
    r_km = km / (2 * math.pi)
    n = max(10, int(seconds // 10))
    rid = _id(key, "route", start.isoformat())
    wid = _id(key, "workout", start.isoformat())
    out = []
    for i in range(n):
        a = 2 * math.pi * i / n
        wob = 1 + 0.08 * math.sin(a * 5)
        lat = lat0 + (r_km * wob * math.sin(a)) / 111.0
        lon = lon0 + (r_km * wob * (1 - math.cos(a))) / (111.0 * math.cos(math.radians(lat0)))
        out.append(("routePoint", {"routeUUID": rid, "workoutUUID": wid, "time": _z(start + dt.timedelta(seconds=10 * i)),
                                   "latitude": round(lat, 6), "longitude": round(lon, 6), "altitude": round(130 + 12 * math.sin(a * 2), 1),
                                   "horizontalAccuracy": 4.0, "verticalAccuracy": 3.0, "speed": round(km * 1000 / seconds, 2), "course": 0}))
    return out


def lines_for(p: dict, prof: dict, tz) -> list:
    rnd = random.Random(p["key"])
    key, watch = p["key"], prof["watch"]
    src = "Apple Watch" if watch else "iPhone"
    out = [("characteristic", {"key": "dateOfBirth", "value": demo.born(p).isoformat()}),
           ("characteristic", {"key": "biologicalSex", "value": p["gender"]})]
    today = demo.today()
    for back in range(DAYS, 0, -1):
        day = today - dt.timedelta(days=back)
        weekend = day.weekday() >= 5
        target = prof["steps"] * rnd.uniform(0.65, 1.3) * (1.1 if weekend else 1)
        total_kcal, exercise = 0.0, 0
        for h in range(7, 22):
            share = math.exp(-((h - (13 if weekend else 12.5)) ** 2) / 18)
            steps = int(target * share / 6.2 * rnd.uniform(0.6, 1.4))
            if steps < 20:
                continue
            s = dt.datetime(day.year, day.month, day.day, h, 0, tzinfo=tz)
            e = s + dt.timedelta(minutes=59)
            out.append(_sample(key, "step_count", "quantity", s, e, steps, "count"))
            out.append(_sample(key, "distance_walking_running", "quantity", s, e, round(steps * 0.00072, 3), "km"))
            kcal = round(steps * 0.045 + rnd.uniform(5, 15), 1)
            total_kcal += kcal
            out.append(_sample(key, "active_energy_burned", "quantity", s, e, kcal, "kcal", source=src))
            if watch:
                for mnt in (10, 40):
                    t = s + dt.timedelta(minutes=mnt)
                    bpm = prof["rhr"] + 12 + steps / 90 + rnd.uniform(-6, 8)
                    out.append(_sample(key, "heart_rate", "quantity", t, t, round(bpm), "count/min", source=src))
            if steps > 1100:
                exercise += rnd.randint(5, 20)
        if watch:
            t = dt.datetime(day.year, day.month, day.day, 23, 0, tzinfo=tz)
            out.append(_sample(key, "resting_heart_rate", "quantity", t, t, round(prof["rhr"] + rnd.uniform(-3, 3)), "count/min", source=src))
            if p["parent"]:
                out.append(_sample(key, "heart_rate_variability_sdnn", "quantity", t, t, round(rnd.uniform(35, 70), 1), "ms", source=src))
            out.append(("activitySummary", {"date": day.isoformat(), "activeEnergyBurned": round(total_kcal), "activeEnergyBurnedGoal": 500,
                                            "appleExerciseTime": exercise, "appleExerciseTimeGoal": 30, "appleStandHours": rnd.randint(8, 13),
                                            "appleStandHoursGoal": 12}))
        if prof["kg"] and day.weekday() == 0:
            t = dt.datetime(day.year, day.month, day.day, 7, 5, tzinfo=tz)
            kg = prof["kg"] - back * 0.01 + rnd.uniform(-0.4, 0.4)
            out.append(_sample(key, "body_mass", "quantity", t, t, round(kg, 1), "kg", source="Smart scale"))
        # the night that ends on the morning of day+1
        hours = prof["sleep"] + rnd.uniform(-0.8, 0.6) + (0.5 if weekend else 0)
        bed = dt.datetime(day.year, day.month, day.day, 22 if p["parent"] else 20, 30 if p["parent"] else 15, tzinfo=tz)
        bed += dt.timedelta(minutes=rnd.randint(-25, 45))
        wake = bed + dt.timedelta(hours=hours + 0.3)
        out.append(_sample(key, "sleep_analysis", "category", bed, wake, text="inBed", source=src))
        t = bed + dt.timedelta(minutes=rnd.randint(8, 20))
        cycle = ["core", "deep", "core", "rem"]
        i = 0
        while t < wake - dt.timedelta(minutes=10):
            stage = cycle[i % 4] if rnd.random() > 0.06 else "awake"
            mins = {"core": rnd.randint(25, 50), "deep": rnd.randint(15, 35), "rem": rnd.randint(15, 30), "awake": rnd.randint(2, 8)}[stage]
            end = min(wake, t + dt.timedelta(minutes=mins))
            out.append(_sample(key, "sleep_analysis", "category", t, end, text=stage if watch else ("awake" if stage == "awake" else "asleep"), source=src))
            t, i = end, i + 1
        for wd, act, raw, km, hh, mm in prof["workouts"]:
            if day.weekday() != wd or rnd.random() < 0.15:
                continue
            start = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
            dist = km * rnd.uniform(0.9, 1.1) if km else 0
            pace = {"running": 330, "cycling": 130, "swimming": 1500}.get(act)
            secs = dist * pace * rnd.uniform(0.95, 1.08) if pace else rnd.uniform(45, 70) * 60
            hr = prof["rhr"] + {"running": 92, "cycling": 75, "swimming": 70, "soccer": 80}.get(act, 50)
            kcal = secs / 60 * rnd.uniform(8, 11)
            stats = [{"type": "active_energy_burned", "unit": "kcal", "sum": round(kcal)}]
            if dist:
                stats.append({"type": "distance_swimming" if act == "swimming" else "distance_cycling" if act == "cycling" else "distance_walking_running",
                              "unit": "km", "sum": round(dist, 2)})
            if watch:
                stats.append({"type": "heart_rate", "unit": "count/min", "average": round(hr), "minimum": round(hr - 30), "maximum": round(hr + 22)})
            out.append(("workout", {"uuid": _id(key, "workout", start.isoformat()), "activityType": act, "activityTypeRaw": raw,
                                    "start": _z(start), "end": _z(start + dt.timedelta(seconds=secs)), "duration": round(secs),
                                    "source": {"name": src}, "statistics": stats, "events": [], "activities": [],
                                    "metadata": {"HKIndoorWorkout": act == "traditionalStrengthTraining"}}))
            if act in ("running", "cycling"):
                out += _route(key, start, dist, secs, rnd)
    return out


def seed(people: dict) -> None:
    tz = ZoneInfo(demo.HOME["tz"])
    for key, prof in PROFILE.items():
        p = people[key]
        lines = lines_for(p, prof, tz)
        with rollup.locks.batch(p["id"]), db.tx() as con, con.cursor() as cur:
            b = upload.Batch(cur, p["id"])
            for kind, m in lines:
                b.apply(kind, m)
            b.finish()
            cur.execute("INSERT INTO hlt_sync_log (started_at, finished_at, device, os, full_resync, items, user_id, applied) "
                        "VALUES (UTC_TIMESTAMP(3), UTC_TIMESTAMP(3), %s, %s, 1, %s, %s, %s)",
                        (f"{p['first']}'s iPhone (demo)", "iOS", len(lines), p["id"], b.applied))
