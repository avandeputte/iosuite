"""TRMNL screens: the suite at a glance on a TRMNL e-ink display (trmnl.com), as TRMNL "private plugins".

A TRMNL plugin is markup (Liquid over TRMNL's design framework, in four sizes: full 800×480, half_horizontal 800×240,
half_vertical 400×480, quadrant 400×240) and the data it fills in. The markup lives here (trmnl_markup/: one folder per
screen and a shared.liquid for all) and goes to TRMNL as the zip its "Import new" takes (settings.yml, the four sizes,
shared.liquid). The data is one flat JSON per screen, already worded ("6:00 PM", "in 12 days", "8,214"), so the markup
only lays it out:

    GET /api/trmnl/{screen}?tz=Europe/Brussels&clock=12|24

The screens (SCREENS): today (the date, the weather, what is left of today with each event's place, tomorrow, today's
tasks, birthdays), calendar (the next seven days), tasks (due today and late), docs (ioDocs' to renew), health (steps,
rings, last night's sleep, the week), money (ioMoney's bills of the week, accounts running low, links behind),
weather (the start page's own: now, the next hours, the coming days, with the start page's weather glyphs).

Two ways for the data to reach TRMNL, as the person's TRMNL is set up:

* polling: TRMNL (its cloud through Cloudflare Access with the suite's service token, or a TRMNL server of one's own
  inside the network, BYOS) asks the address above every so often. It signs in like any client: an ioStart app
  password of the person's (Settings › Account), sent as "Authorization: Bearer". The plugin zip asks for the address
  and the app password in TRMNL's form, never with them in it.
* push: for a TRMNL cloud that cannot reach the suite. The person pastes each screen's TRMNL webhook address in
  Settings › TRMNL; the start page then sends the screen's data there itself (trmnlpush.py: every 15 minutes
  when it changed, once an hour at least; TRMNL takes 12 an hour per plugin, 5 KB each). The webhook addresses and
  the app password it reads with are kept with the suite's keys and tokens (iosuite_shared.credentials), so a suite
  admin sees them in Settings › Global settings › Keys and tokens.

Either way the data is read as the person, with what they may see in each app and nothing more (widgets.fetch: the
apps' standard tile endpoints, on the person's own sign-in): there is no service account behind it.
"""
import datetime as dt
import io
import json
import os
import re
import zipfile
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app import apps, wall, weather, widgets

SCREENS = {
    "today": {"name": "Today", "apps": ["iocalendar", "iotask", "iocontact"], "every": 15,
              "about": "The date, the weather, what is left of today with each place, tomorrow, today's tasks"},
    "calendar": {"name": "Calendar", "apps": ["iocalendar"], "every": 15, "about": "ioCalendar: the next seven days"},
    "tasks": {"name": "Tasks", "apps": ["iotask"], "every": 15, "about": "ioTask: what is due today, the late ones first"},
    "docs": {"name": "Documents", "apps": ["iodocs"], "every": 240, "about": "ioDocs: the papers to renew"},
    "health": {"name": "Health", "apps": ["iohealth"], "every": 60, "about": "ioHealth: steps, rings, last night's sleep, the week"},
    "money": {"name": "Money", "apps": ["iomoney"], "every": 60, "about": "ioMoney: the bills of the week, accounts running low"},
    "weather": {"name": "Weather", "apps": [], "every": 60, "about": "The weather now, the next hours and the coming days"},
}
# The weather's glyphs, in the order trmnl_markup/weather/shared.liquid has them (the data names one by its place in
# this list): the start page's own (static/app.js: WX), by AccuWeather's icon number as there (WX_MAP).
WX = ("sun", "moon", "cloud", "partly", "partlyNight", "rain", "storm", "snow", "fog", "wind", "hot")
WX_MAP = {1: "sun", 2: "sun", 3: "partly", 4: "partly", 5: "partly", 6: "cloud", 7: "cloud", 8: "cloud", 11: "fog", 12: "rain", 13: "rain", 14: "partly",
          15: "storm", 16: "storm", 17: "partly", 18: "rain", 19: "snow", 20: "snow", 21: "snow", 22: "snow", 23: "snow", 24: "snow", 25: "snow", 26: "rain",
          29: "snow", 30: "hot", 31: "snow", 32: "wind", 33: "moon", 34: "moon", 35: "partlyNight", 36: "partlyNight", 37: "fog", 38: "cloud", 39: "rain",
          40: "rain", 41: "storm", 42: "storm", 43: "snow", 44: "snow"}
SIZES = ("full", "half_horizontal", "half_vertical", "quadrant")
MARKUP_DIR = os.path.join(os.path.dirname(__file__), "trmnl_markup")
LIMIT = 5000  # bytes: what TRMNL keeps of a webhook push (5 KB; 10 KB with TRMNL+); the polled data stays under it too


class NoScreen(Exception):
    pass


# ------------------------------------------------------------------ wording

def zone(tz: str):
    try:
        return ZoneInfo(tz if wall._zone_ok(tz) else wall.server_zone())
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _at(t, z) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(str(t))
    except (TypeError, ValueError):
        return None
    return (d if d.tzinfo else d.replace(tzinfo=z)).astimezone(z)


def clock(d: dt.datetime, h24: bool) -> str:
    """'6:00 PM', '6 PM' on the hour, or '18:00'."""
    if h24:
        return d.strftime("%H:%M")
    h = d.hour % 12 or 12
    return f"{h}{'' if d.minute == 0 else d.strftime(':%M')} {'AM' if d.hour < 12 else 'PM'}"


def short_place(loc) -> str:
    """What comes before the first comma ('Nan Xiang Dumpling, 38-12 Prince St, …'), as the wall display shows it."""
    t = re.sub(r"\s+", " ", str(loc or "")).strip()
    return (t.split(",")[0].strip() or t)[:60]


def day_name(d: dt.date, today: dt.date) -> str:
    n = (d - today).days
    return "Today" if n == 0 else "Tomorrow" if n == 1 else "Yesterday" if n == -1 else d.strftime("%A")


def month_day(d: dt.date) -> str:
    return f"{d.strftime('%b')} {d.day}"


def in_days(n) -> str:
    if n is None:
        return ""
    n = int(n)
    if n == 0:
        return "today"
    if n > 0:
        return "tomorrow" if n == 1 else f"in {n} days"
    return "yesterday" if n == -1 else f"{-n} days ago"


def thousands(v) -> str:
    return "" if v is None else f"{round(v):,}"


def money(v, cur: str | None) -> str:
    if v is None:
        return ""
    sign = "-" if v < 0 else ""
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "$", "AUD": "$", "JPY": "¥"}.get((cur or "USD").upper())
    num = f"{abs(v):,.2f}"
    return f"{sign}{sym}{num}" if sym else f"{sign}{num} {cur}"


def minutes(m) -> str:
    if not m:
        return ""
    m = round(m)
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def _ask(request, key: str, **kw):
    """The app's tile, or None when the app is not there or will not answer for this person."""
    if not apps.url_for(key):
        return None
    try:
        return widgets.get(request, key, **kw)
    except widgets.Unavailable:
        return None


def _weather(w: dict | None, today: dt.date) -> dict | None:
    """{temp, text, hi, lo, rain, days: [{day, hi, lo, text}]} from the wall feed's weather (already in the suite's
    units), or None."""
    if not w:
        return None
    deg = (lambda v: "" if v is None else f"{v}°")
    days = w.get("days") or []
    first = next((d for d in days if d.get("date") == today.isoformat()), None)
    return {"temp": deg(w.get("temp")), "text": w.get("text") or "",
            "hi": deg(first.get("max")) if first else "", "lo": deg(first.get("min")) if first else "",
            "rain": f"{first['rain']}%" if first and first.get("rain") else "",
            "days": [{"day": dt.date.fromisoformat(d["date"]).strftime("%a"), "hi": deg(d.get("max")), "lo": deg(d.get("min")),
                      "text": d.get("text") or ""} for d in days if str(d.get("date") or "") > today.isoformat()][:4]}


def _tasks(items, z, h24: bool) -> list:
    out = []
    for x in items or []:
        d = _at(x.get("due"), z) if x.get("due") and not x.get("allDay") else None
        out.append({"title": (x.get("title") or "(no title)")[:80], "when": "Late" if x.get("late") else clock(d, h24) if d else "",
                    "late": bool(x.get("late"))})
    return out


def _birthdays(items) -> list:
    out = []
    for b in items or []:
        if (b.get("in") or 0) > 1:
            continue
        what = (f"turns {b['turns']}" if b.get("turns") else "birthday") if b.get("label", "birthday") == "birthday" else b.get("label")
        out.append(f"{b.get('name')}: {what} {in_days(b.get('in'))}")
    return out[:3]


# ------------------------------------------------------------------ the screens

def _wall_event(o: dict, z, h24: bool) -> dict:
    """{time, title, place} for one of the wall feed's events (epoch s for a timed one, day for an all-day one)."""
    s = dt.datetime.fromtimestamp(o["s"], z) if o.get("s") is not None and not o.get("allDay") else None
    return {"time": clock(s, h24) if s else "All day", "title": (o.get("title") or "(no title)")[:80], "place": (o.get("place") or "")[:60]}


def _when(o: dict, z, today: dt.date, h24: bool) -> str:
    """'Fri 9 AM', 'Tomorrow', 'Dec 3': when a coming event is."""
    if o.get("s") is not None and not o.get("allDay"):
        s = dt.datetime.fromtimestamp(o["s"], z)
        d = s.date()
        return f"{day_name(d, today) if (d - today).days < 7 else month_day(d)} {clock(s, h24)}"
    try:
        d = dt.date.fromisoformat(str(o.get("day"))[:10])
    except ValueError:
        return ""
    return day_name(d, today) if (d - today).days < 7 else month_day(d)


def _today(request, z, now, h24):
    """From the wall display's feed (wall.feed): the same events, tasks, birthdays and weather as the start page's #/wall."""
    today = now.date()
    f = wall.feed(request, str(now.tzinfo))
    tom = next((d for d in f.get("days") or [] if d.get("date") == (today + dt.timedelta(days=1)).isoformat()), None)
    t = f.get("tasks") or {}
    nxt = f.get("next")
    return {"weather": _weather(f.get("weather"), today), "has_calendar": f.get("today") is not None, "has_tasks": f.get("tasks") is not None,
            "events": [_wall_event(o, z, h24) for o in f.get("today") or []][:6],
            "events_more": max(0, len(f.get("today") or []) - 6) + (f.get("todayMore") or 0),
            "next": f"Next: {nxt.get('title') or '(no title)'}, {_when(nxt, z, today, h24)}" if nxt and not f.get("today") else "",
            "tomorrow": [_wall_event(o, z, h24) for o in (tom or {}).get("items") or []][:4],
            "tasks": _tasks(t.get("items"), z, h24), "tasks_more": t.get("more") or 0, "overdue": t.get("overdue") or 0,
            "birthdays": _birthdays(f.get("birthdays"))}


def _calendar(request, z, now, h24):
    today = now.date()
    f = wall.feed(request, str(now.tzinfo))
    if f.get("today") is None and f.get("days") is None:
        return {"days": [], "count": 0, "more": 0, "missing": "ioCalendar does not answer"}
    days = [{"label": "Today", "date": month_day(today), "events": [_wall_event(o, z, h24) for o in f.get("today") or []][:8]}]
    for d in f.get("days") or []:
        try:
            day = dt.date.fromisoformat(d["date"])
        except (KeyError, TypeError, ValueError):
            continue
        days.append({"label": day_name(day, today), "date": month_day(day), "events": [_wall_event(o, z, h24) for o in d.get("items") or []][:6]})
    return {"days": days, "count": sum(len(d["events"]) for d in days), "more": f.get("todayMore") or 0}


def _task_screen(request, z, now, h24):
    t = _ask(request, "iotask", tz=str(now.tzinfo), n=14)
    if t is None:
        return {"tasks": [], "more": 0, "overdue": 0, "missing": "ioTask does not answer"}
    return {"tasks": _tasks(t.get("today"), z, h24), "more": t.get("more") or 0, "overdue": t.get("overdue") or 0}


def _docs(request, z, now, h24):
    d = _ask(request, "iodocs", n=10)
    if d is None:
        return {"items": [], "more": 0, "expired": 0, "missing": "ioDocs does not answer"}
    items = []
    for x in d.get("items") or []:
        days = x.get("days")
        try:
            on = dt.date.fromisoformat(str(x.get("expiresOn"))[:10])
            date = f"{month_day(on)}, {on.year}"
        except ValueError:
            date = ""
        when = ("Expired " + in_days(days) if days is not None and days < 0 else "Expires " + in_days(days)) if days is not None else ""
        items.append({"title": (x.get("title") or "(no title)")[:60], "kind": x.get("kind") or "", "who": ", ".join(x.get("people") or [])[:40]
                      if isinstance(x.get("people"), list) else str(x.get("people") or "")[:40],
                      "when": when.replace("Expired today", "Expires today"), "date": date, "expired": x.get("state") == "expired"})
    return {"items": items, "more": d.get("more") or 0, "expired": d.get("expired") or 0}


def _health(request, z, now, h24):
    h = _ask(request, "iohealth", tz=str(now.tzinfo))
    if h is None:
        return {"steps": "", "week": [], "missing": "ioHealth does not answer"}
    week = [w for w in h.get("week") or [] if w.get("date")]
    top = max([w.get("steps") or 0 for w in week] + [1])
    done = [w["steps"] for w in week if w.get("steps") is not None]
    rings = []
    for k, unit, name in (("move", "kcal", "Move"), ("exercise", "min", "Exercise"), ("stand", "h", "Stand")):
        r = h.get("rings") or {}
        if r.get(k) is not None:
            goal = r.get(f"{k}Goal")
            rings.append({"name": name, "value": f"{round(r[k])}", "goal": f"{round(goal)}" if goal else "", "unit": unit,
                          "pct": min(100, round(100 * r[k] / goal)) if goal else 0})
    s = h.get("sleep") or {}
    return {"steps": thousands(h.get("steps")) or "0", "rings": rings, "sleep": minutes(s.get("asleep")), "in_bed": minutes(s.get("inBed")),
            "week": [{"day": dt.date.fromisoformat(w["date"]).strftime("%a"), "steps": thousands(w.get("steps")) or "–",
                      "pct": round(100 * (w.get("steps") or 0) / top)} for w in week],
            "average": thousands(sum(done) / len(done)) if done else ""}


def _money(request, z, now, h24):
    m = _ask(request, "iomoney", tz=str(now.tzinfo), n=8)
    if m is None:
        return {"bills": [], "more": 0, "total": "", "low": [], "behind": [], "missing": "ioMoney does not answer"}
    today = now.date()
    bills = []
    for b in m.get("bills") or []:
        try:
            day = day_name(dt.date.fromisoformat(str(b.get("day"))[:10]), today)
        except ValueError:
            day = ""
        bills.append({"day": day[:3] if day not in ("Today", "Tomorrow") else day, "name": (b.get("name") or "")[:40],
                      "amount": ("~" if b.get("approximate") else "") + money(abs(b.get("amount") or 0), b.get("currency") or m.get("currency"))})
    low = []
    for a in m.get("low") or []:
        try:
            on = month_day(dt.date.fromisoformat(str(a.get("belowOn"))[:10]))
        except ValueError:
            on = ""
        low.append(f"{a.get('name')}: under {money(a.get('floor'), a.get('currency'))}" + (f" on {on}" if on else ""))
    return {"bills": bills, "more": m.get("more") or 0, "total": money(abs(m["total"]), m.get("currency")) if m.get("total") is not None else "",
            "low": low[:3], "behind": [a.get("institution") or a.get("name") for a in m.get("behind") or []][:3]}


def _glyph(icon) -> int:
    return WX.index(WX_MAP.get(icon, "cloud"))


def _forecast(request, z, now, h24):
    """The start page's weather (app/weather.py, as the wall display reads it: wall._weather): now, the next eight
    hours, five days. Everyone signed in may see it, as on the start page."""
    w = wall._weather(z)
    if w is None:
        on = weather.settings()["enabled"]
        return {"hours": [], "days": [], "missing": "The weather does not answer right now" if on else "No weather yet: an admin sets it up on the start page, Settings › Weather"}
    deg = (lambda v: "" if v is None else f"{v}°")
    pct = (lambda v: f"{v}%" if v and v >= 20 else "")
    today = now.date()
    imperial = weather.settings()["units"] == "imperial"
    try:
        c = weather.current().get("current") or {}
    except weather.WeatherError:
        c = {}
    u = "imperial" if imperial else "metric"
    feels, wind = (c.get("feels") or {}).get(u), (c.get("wind") or {}).get(u)
    days = []
    for d in w.get("days") or []:
        try:
            day = dt.date.fromisoformat(str(d.get("date")))
        except ValueError:
            continue
        if day < today:
            continue
        days.append({"day": "Today" if day == today else day.strftime("%a"), "icon": _glyph(d.get("icon")), "text": (d.get("text") or "")[:40],
                     "hi": deg(d.get("max")), "lo": deg(d.get("min")), "rain": pct(d.get("rain"))})
    first = next((d for d in w.get("days") or [] if d.get("date") == today.isoformat()), None) or {}
    r = w.get("rain") or {}
    note = ""
    if r.get("from"):
        note = f"{r.get('what') or 'Rain'} from {clock(dt.datetime.fromtimestamp(r['from'], z), h24)}"
    elif r and "until" in r:
        note = f"{r.get('what') or 'Rain'} until {clock(dt.datetime.fromtimestamp(r['until'], z), h24)}" if r.get("until") else f"{r.get('what') or 'Rain'} for the next hours"
    return {"place": short_place(w.get("place")), "temp": deg(w.get("temp")), "text": w.get("text") or "", "icon": _glyph(w.get("icon")),
            "feels": deg(round(feels)) if feels is not None else "", "hi": deg(first.get("max")), "lo": deg(first.get("min")), "rain": pct(first.get("rain")),
            "note": note, "wind": f"{round(wind)} {'mph' if imperial else 'km/h'}" if wind is not None else "",
            "humidity": f"{round(c['humidity'])}%" if c.get("humidity") is not None else "", "uv": str(round(c["uv"])) if c.get("uv") is not None else "",
            "hours": [{"time": clock(dt.datetime.fromtimestamp(h["t"], z), h24), "icon": _glyph(h.get("icon")), "temp": deg(h.get("temp")), "rain": pct(h.get("rain"))}
                      for h in (w.get("hours") or [])[:8]],
            "days": days[:5]}


BUILDERS = {"today": _today, "calendar": _calendar, "tasks": _task_screen, "docs": _docs, "health": _health, "money": _money, "weather": _forecast}


def build(request, screen: str, tz: str = "", h24: bool = False, now: dt.datetime | None = None) -> dict:
    """The screen's data for TRMNL, as the person `request` signed in with. Every screen also carries the date and the
    time it was made ('updated'), since an e-ink screen shows the same picture for a while."""
    if screen not in BUILDERS:
        raise NoScreen(screen)
    z = zone(tz)
    now = (now or dt.datetime.now(z)).astimezone(z)
    out = {"screen": screen, "name": SCREENS[screen]["name"], "weekday": now.strftime("%A"), "date": f"{now.strftime('%B')} {now.day}",
           "date_short": f"{now.strftime('%a')}, {month_day(now.date())}", "updated": clock(now, h24)}
    out.update(BUILDERS[screen](request, z, now, h24))
    return fit(out)


def fit(d: dict) -> dict:
    """Under LIMIT bytes: the longest lists are shortened (from their end, and 'more' counts on) until it fits."""
    lists = [k for k in ("events", "tomorrow", "tasks", "items", "bills", "days") if isinstance(d.get(k), list)]
    while len(json.dumps(d, ensure_ascii=False).encode()) > LIMIT:
        k = max(lists, key=lambda k: len(json.dumps(d[k])), default=None)
        if k == "days" and all("events" in x for x in d["days"]):
            longest = max(d["days"], key=lambda x: len(x["events"]), default=None)
            if not longest or not longest["events"]:
                break
            longest["events"].pop()
        elif k and d[k]:
            d[k].pop()
            more = {"events": "events_more", "tasks": "tasks_more" if "tasks_more" in d else "more"}.get(k, "more")
            if more in d:
                d[more] = (d[more] or 0) + 1
        else:
            break
    return d


# ------------------------------------------------------------------ the plugin as TRMNL imports it

def markup(screen: str) -> dict:
    """{size: Liquid}: the four sizes of the screen and shared.liquid (common.liquid, the same for every screen, then
    the screen's own shared part)."""
    if screen not in SCREENS:
        raise NoScreen(screen)
    folder = os.path.join(MARKUP_DIR, screen)
    out = {}
    for size in SIZES:
        with open(os.path.join(folder, f"{size}.liquid"), encoding="utf-8") as f:
            out[size] = f.read()
    with open(os.path.join(MARKUP_DIR, "common.liquid"), encoding="utf-8") as f:
        shared = f.read()
    own = os.path.join(folder, "shared.liquid")
    if os.path.exists(own):
        with open(own, encoding="utf-8") as f:
            shared += "\n" + f.read()
    out["shared"] = shared
    return out


def _yaml(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)  # a JSON string is a YAML string


def settings_yml(screen: str, mode: str, server: str) -> str:
    """TRMNL's settings.yml for the screen. polling: TRMNL asks {server}/api/trmnl/{screen} with the app password the
    person types in TRMNL's form (and Cloudflare Access's service token when the suite sits behind it); push: TRMNL
    waits for the start page to send (strategy webhook)."""
    s = SCREENS[screen]
    lines = ["---", f"name: {_yaml('ioSuite ' + s['name'])}", f"refresh_interval: {s['every']}", "no_screen_padding: 'no'", "dark_mode: 'no'"]
    if mode == "push":
        lines += ["strategy: webhook", "static_data: ''", "custom_fields:",
                  "- keyname: about", "  field_type: author_bio", f"  name: {_yaml('ioSuite ' + s['name'])}",
                  f"  description: {_yaml(s['about'] + '. The start page sends it: copy this plugin’s Webhook URL into the start page, Settings › TRMNL.')}"]
        return "\n".join(lines) + "\n"
    url = "{{ server }}/api/trmnl/" + screen + "?tz={{ trmnl.user.time_zone_iana }}&clock={{ clock }}"
    lines += ["strategy: polling", "polling_verb: get", f"polling_url: {_yaml(url)}",
              "polling_headers: " + _yaml("authorization=Bearer {{ app_password }}&cf-access-client-id={{ cf_client_id }}&cf-access-client-secret={{ cf_client_secret }}"),
              "custom_fields:",
              "- keyname: about", "  field_type: author_bio", f"  name: {_yaml('ioSuite ' + s['name'])}",
              f"  description: {_yaml(s['about'] + '. Read from your start page with your own app password.')}",
              "- keyname: server", "  field_type: url", "  name: Start page address",
              "  description: The address TRMNL reaches your start page at: inside your network for a TRMNL server of your own, else its public address",
              f"  default: {_yaml(server)}", "  placeholder: https://start.example.com",
              "- keyname: app_password", "  field_type: password", "  name: App password",
              "  description: An ioStart app password of yours (start page, Settings › Account › App passwords)",
              "  placeholder: iostart-…",
              "- keyname: clock", "  field_type: select", "  name: Clock", "  options:", "  - '12 hours: 12'", "  - '24 hours: 24'", "  default: '12'",
              "- keyname: cf_client_id", "  field_type: string", "  name: Cloudflare Access client ID", "  optional: true",
              "  description: Only when the start page sits behind Cloudflare Access (a service token that its policy lets in)",
              "- keyname: cf_client_secret", "  field_type: password", "  name: Cloudflare Access client secret", "  optional: true"]
    return "\n".join(lines) + "\n"


def plugin_zip(screen: str, mode: str, server: str) -> bytes:
    """The zip TRMNL's Private Plugins › Import new takes: flat, settings.yml and the Liquid files."""
    m = markup(screen)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("settings.yml", settings_yml(screen, mode, server))
        for size in SIZES:
            z.writestr(f"{size}.liquid", m[size])
        z.writestr("shared.liquid", m["shared"])
    return buf.getvalue()


def screens(user) -> list:
    """What Settings › TRMNL lists: every screen whose apps this person may see (Today needs one of its three), and
    the weather once the start page has it (Settings › Weather)."""
    reg = apps.registered()
    out = []
    for k, s in SCREENS.items():
        have = [a for a in s["apps"] if a in reg and reg[a].get("url") and apps.may_see(user, reg[a])]
        if have or (k == "weather" and weather.settings()["enabled"]):
            out.append({"key": k, "name": s["name"], "about": s["about"], "every": s["every"]})
    return out
