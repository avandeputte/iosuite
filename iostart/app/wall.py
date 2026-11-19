"""The wall display on a device of its own (devices/tab5-wall: an M5Stack Tab5 on the wall): what the page's #/wall
shows, in one compact answer a small computer can read, its photos made to the size of its screen, and its sign-in.

The device has no browser. It signs in with an ioStart app password of its own (scope '', revocable in Settings ›
Account like any other), which it gets in one of two ways:
- pairing: it asks for a code (POST /api/wall/pair), shows it with a QR code of the page that approves it
  (#/pair/<code>), and asks every few seconds whether someone signed in has approved it (GET /api/wall/pair/<token>);
  the approval makes the app password for that person and hands it over once;
- or it sends a name and the account's password once as HTTP Basic to /api/auth/app-passwords (iosuite_shared), as
  any client can, and keeps only the app password it gets back.

Everything else is the viewer's own: the feed asks the apps with the device's app password, which every app takes as
the same person (iosuite_shared.apppasswords.HUB), so it sees what that person sees and nothing more.
"""
import concurrent.futures
import datetime as dt
import io
import os
import re
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path
from zoneinfo import ZoneInfo

from iosuite_shared import apppasswords

from app import apps, config, homeassistant as ha, layout, weather, widgets

FEED_VERSION = 1

# ------------------------------------------------------------------ pairing

PAIR_TTL = 10 * 60      # seconds a code may be approved
PAIR_MAX = 32           # codes waiting at once (a public endpoint: no more than this, the oldest go first)
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I
_pairs: dict = {}       # token -> {code, label, at, user, password}
_lock = threading.Lock()


class PairError(Exception):
    def __init__(self, status: int, why: str):
        super().__init__(why)
        self.status = status


def _code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))


def _clean_label(label) -> str:
    t = re.sub(r"\s+", " ", str(label or "")).strip()[:60]
    return t or "Wall display"


def _expire(now: float) -> None:
    for t in [t for t, p in _pairs.items() if now - p["at"] > PAIR_TTL]:
        _pairs.pop(t, None)


def pair_start(label: str, base: str) -> dict:
    """A new code for a device: {code, token, approveUrl, expires, every}. base: the address people open the start
    page at (PUBLIC_URL, else the one the device asked), for the QR code."""
    now = time.time()
    with _lock:
        _expire(now)
        while len(_pairs) >= PAIR_MAX:
            _pairs.pop(min(_pairs, key=lambda t: _pairs[t]["at"]))
        token = secrets.token_urlsafe(24)
        code = _code()
        while any(p["code"] == code for p in _pairs.values()):
            code = _code()
        _pairs[token] = {"code": code, "label": _clean_label(label), "at": now, "user": None, "password": None}
    return {"code": code, "token": token, "approveUrl": f"{base.rstrip('/')}/#/pair/{code}", "expires": PAIR_TTL, "every": 3}


def _by_code(code: str):
    c = re.sub(r"[^A-Z0-9]", "", str(code or "").upper())
    for t, p in _pairs.items():
        if p["code"] == c:
            return t, p
    return None, None


def pair_info(code: str) -> dict:
    """What the approval page shows: {code, label, age}. 404 for a code that is not waiting."""
    with _lock:
        _expire(time.time())
        _, p = _by_code(code)
        if not p or p["user"]:
            raise PairError(404, "No wall display is waiting for this code (it lasts ten minutes)")
        return {"code": p["code"], "label": p["label"], "age": int(time.time() - p["at"])}


def pair_approve(code: str, user: dict) -> dict:
    """The signed-in person lets the device in: an app password of theirs (no limit, labelled with the device's name),
    kept until the device fetches it."""
    if user.get("passwordless"):
        raise PairError(403, "A one-click account cannot have app passwords; give the account a password first")
    with _lock:
        _expire(time.time())
        _, p = _by_code(code)
        if not p or p["user"]:
            raise PairError(404, "No wall display is waiting for this code (it lasts ten minutes)")
        p["user"] = user["id"]
    pw = apppasswords.create(user["id"], apppasswords.HUB, p["label"], "")
    with _lock:
        p["password"], p["name"] = pw, user.get("name")
        p["at"] = time.time()  # the device has a few minutes from now to pick it up
    return {"ok": True, "label": p["label"]}


def pair_poll(token: str):
    """None while it waits; {password, name} once approved (handed over once); PairError 404 when unknown or expired."""
    with _lock:
        _expire(time.time())
        p = _pairs.get(str(token or ""))
        if not p:
            raise PairError(404, "This code has expired; ask for a new one")
        if not p["password"]:
            return None
        _pairs.pop(token, None)
        return {"password": p["password"], "name": p.get("name")}


def forget() -> None:
    with _lock:
        _pairs.clear()
    _photos.clear()


# ------------------------------------------------------------------ the time zone

def server_zone() -> str:
    """The server's own time zone name (TZ, /etc/timezone, /etc/localtime's link), UTC when none is found."""
    z = os.environ.get("TZ", "").lstrip(":")
    if z and _zone_ok(z):
        return z
    try:
        z = Path("/etc/timezone").read_text().strip()
        if _zone_ok(z):
            return z
    except OSError:
        pass
    try:
        p = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in p:
            z = p.split("zoneinfo/", 1)[1]
            if _zone_ok(z):
                return z
    except OSError:
        pass
    return "UTC"


def _zone_ok(z: str) -> bool:
    if not z or not re.fullmatch(r"[A-Za-z0-9_+\-/]{1,64}", z):
        return False
    try:
        ZoneInfo(z)
        return True
    except Exception:  # noqa: BLE001
        return False


def posix_tz(name: str) -> str:
    """The POSIX TZ string of an IANA zone ("EST5EDT,M3.2.0,M11.1.0"), for the device's C library: the last line of
    its TZif file (version 2 and later carry it). "UTC0" when it cannot be read."""
    import zoneinfo
    for root in zoneinfo.TZPATH:
        f = Path(root) / name
        try:
            data = f.read_bytes()
        except OSError:
            continue
        if data[:4] == b"TZif" and data[4:5] in (b"2", b"3", b"4"):
            tail = data.rstrip(b"\n").rsplit(b"\n", 1)
            if len(tail) == 2 and re.fullmatch(rb"[A-Za-z0-9<>+\-,./:]{1,60}", tail[1]):
                return tail[1].decode()
        break
    try:  # tzdata's copy (no system zoneinfo, e.g. some containers)
        from importlib import resources
        data = resources.files("tzdata.zoneinfo").joinpath(*name.split("/")).read_bytes()
        tail = data.rstrip(b"\n").rsplit(b"\n", 1)
        if len(tail) == 2 and re.fullmatch(rb"[A-Za-z0-9<>+\-,./:]{1,60}", tail[1]):
            return tail[1].decode()
    except Exception:  # noqa: BLE001
        pass
    return "UTC0"


# ------------------------------------------------------------------ the feed

def _epoch(v, zone) -> int | None:
    try:
        d = dt.datetime.fromisoformat(str(v))
    except (TypeError, ValueError):
        return None
    return int((d if d.tzinfo else d.replace(tzinfo=zone)).timestamp())


def short_place(loc) -> str:
    """What comes before the first comma ("Nan Xiang Dumpling, 38-12 Prince St, …"), as the page's agenda shows it."""
    t = re.sub(r"\s+", " ", str(loc or "")).strip()
    return (t.split(",")[0] or "").strip() or t


def _event(o: dict, zone) -> dict:
    out = {"title": str(o.get("title") or "(no title)")[:120], "allDay": bool(o.get("allDay")), "color": o.get("color") or None,
           "place": short_place(o.get("location"))[:80], "location": str(o.get("location") or "")[:200]}
    # what a tap on the event adds, where ioCalendar has any: who of the family it is for, the other people on it, its
    # calendar, its notes
    who = [{"name": str(w.get("name") or "")[:40], "color": w.get("color") or None} for w in o.get("who") or [] if isinstance(w, dict) and w.get("name")][:8]
    more = {"who": who, "people": [str(p)[:60] for p in o.get("people") or []][:8], "calendar": str(o.get("calendar") or "")[:60],
            "notes": re.sub(r"[ \t]+", " ", str(o.get("notes") or "")).strip()[:400], "recurring": bool(o.get("recurring"))}
    out.update({k: v for k, v in more.items() if v})
    if out["allDay"]:
        out["day"] = str(o.get("start") or "")[:10]
        out["endDay"] = str(o.get("end") or "")[:10] or None
    else:
        out["s"], out["e"] = _epoch(o.get("start"), zone), _epoch(o.get("end"), zone)
    return out


def _temp(v, imperial: bool):
    if v is None:
        return None
    return round(v * 9 / 5 + 32) if imperial else round(v)


def _weather(zone) -> dict | None:
    try:
        w = weather.current()
    except weather.WeatherError:
        return None
    if not w.get("enabled") or not w.get("current"):
        return None
    imp = w.get("units") == "imperial"
    u = "imperial" if imp else "metric"
    c = w["current"]
    hours = []
    now = time.time()
    for x in w.get("hourly") or []:
        t = _epoch(x.get("t"), zone)
        if t is None or t + 3600 <= now:
            continue
        hours.append({"t": t, "temp": _temp(x.get("temp"), imp), "icon": x.get("icon"), "rain": x.get("rain"),
                      "wet": bool(x.get("wet") or (x.get("rain") or 0) >= 50), "kind": x.get("kind") or None})
    days = [{"date": d.get("date"), "max": _temp(d.get("max"), imp), "min": _temp(d.get("min"), imp), "icon": d.get("icon"),
             "rain": d.get("rain"), "text": d.get("text")} for d in ((w.get("forecast") or {}).get("days") or [])]
    rain = None
    if hours:
        what = {"Rain": "Rain", "Snow": "Snow", "Ice": "Ice", "Mixed": "Sleet"}
        if hours[0]["wet"]:
            dry = next((x for x in hours if not x["wet"]), None)
            rain = {"what": what.get(hours[0]["kind"], "Rain"), "until": dry["t"] if dry else None}
        else:
            wet = next((x for x in hours if x["wet"]), None)
            rain = {"what": what.get(wet["kind"], "Rain"), "from": wet["t"]} if wet else None
    temp = (c.get("temp") or {}).get(u)
    return {"temp": round(temp) if temp is not None else None, "text": c.get("text"), "icon": c.get("icon"),
            "day": c.get("isDay") is not False, "place": w.get("location"), "stale": bool(w.get("stale")),
            "hours": hours[:12], "days": days[:5], "rain": rain}


HA_TAP = {"light": "toggle", "switch": "toggle", "fan": "toggle", "input_boolean": "toggle", "humidifier": "toggle",
          "siren": "toggle", "automation": "toggle", "media_player": "toggle", "cover": "toggle", "lock": "toggle",
          "scene": "on", "script": "on", "button": "on", "input_button": "on"}


def _home(user: dict) -> dict | None:
    d = ha.home()
    if not d.get("enabled"):
        return None
    may = user.get("role") in ("editor", "admin")
    on = set(d.get("wall") or [])
    items = []
    for it in d.get("items") or []:
        if it["id"] not in on:
            continue
        tap = HA_TAP.get(it.get("domain")) if may and it.get("control") and it.get("state") != "unavailable" else None
        items.append({"id": it["id"], "name": it.get("name"), "text": it.get("text") or it.get("state"), "on": it.get("on"),
                      "domain": it.get("domain"), "tap": tap})
    return {"items": items[:12], "alerts": [{"name": a.get("name"), "text": a.get("text")} for a in (d.get("alerts") or [])[:3]],
            "error": d.get("error")}


PHOTO_KIND = re.compile(r"[a-z]{2,20}(:[A-Za-z0-9_-]{1,40})?")


def photo_kind(lay: dict) -> str:
    """Which photos: the person's wall choice (wallPhotos: rediscover, onthisday, favorites, album:<id>), else the photo
    strip's (layout, else the home page's default); "off" still shows photos on the wall (rediscover)."""
    k = lay.get("wallPhotos") or lay.get("strip") or apps.photo_strip()
    k = str(k or "rediscover")
    if k == "off" or not PHOTO_KIND.fullmatch(k):
        return "rediscover"
    return k


def feed(request, tz: str = "") -> dict:
    """Everything the device draws, in one answer. Each part is None when its app is not there, not set up, or did not
    answer (errors says which and why), so one app down never blanks the wall."""
    user = request.state.user
    zone_name = tz if _zone_ok(tz) else server_zone()
    zone = ZoneInfo(zone_name)
    lay = layout.get(user["id"]) or {}
    has = {t["key"] for t in apps.tiles(user)}
    pix = "iopix" in has
    bg = lay.get("wallBg") or ("photos" if pix else "sky")
    if bg == "photos" and not pix:
        bg = "sky"
    jobs = {}
    if "iocalendar" in has:
        jobs["today"] = lambda: widgets.fetch(request, "iocalendar", "/api/suite/tile", {"tz": zone_name, "n": 12})
        jobs["week"] = lambda: widgets.fetch(request, "iocalendar", "/api/suite/tile", {"tz": zone_name, "kind": "week"})
    if "iocontact" in has:
        jobs["birthdays"] = lambda: widgets.fetch(request, "iocontact", "/api/suite/tile", {"tz": zone_name})
    if "iotask" in has:
        jobs["tasks"] = lambda: widgets.fetch(request, "iotask", "/api/suite/tile", {"tz": zone_name, "n": 8})
    if pix and bg == "photos":
        jobs["photos"] = lambda: widgets.fetch(request, "iopix", "/api/suite/tile", {"tz": zone_name, "kind": photo_kind(lay), "n": 24})
    jobs["weather"] = lambda: _weather(zone)
    jobs["home"] = lambda: _home(user)
    got, errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as ex:
        futs = {k: ex.submit(f) for k, f in jobs.items()}
        for k, f in futs.items():
            try:
                got[k] = f.result(timeout=widgets.TIMEOUT * 3 + 2)
            except widgets.Unavailable as e:
                errors[k] = str(e)
            except Exception as e:  # noqa: BLE001  one part failing leaves the rest
                errors[k] = type(e).__name__
    out = {"v": FEED_VERSION, "now": int(time.time()), "zone": {"name": zone_name, "posix": posix_tz(zone_name)},
           "units": weather.settings()["units"], "bg": bg, "every": lay.get("wallEvery") or layout.WALL_EVERY[1],
           "user": {"name": user.get("name"), "role": user.get("role")},
           "weather": got.get("weather"), "home": got.get("home"), "birthdays": None, "today": None, "todayMore": 0,
           "next": None, "days": None, "tasks": None, "photos": None, "errors": errors,
           "can": {"addTask": "iotask" in has, "addEvent": "iocalendar" in has and user.get("role") != "viewer",
                   "favorite": pix, "home": user.get("role") in ("editor", "admin")}}
    if got.get("birthdays"):
        out["birthdays"] = [{"name": b.get("name"), "in": b.get("in"), "label": b.get("label") or "birthday", "turns": b.get("turns")}
                            for b in got["birthdays"].get("items", []) if b.get("in") is not None and b["in"] <= 6][:6]
    if got.get("today"):
        t = got["today"]
        out["today"] = [_event(o, zone) for o in t.get("today") or []]
        out["todayMore"] = t.get("more") or 0
        out["next"] = _event(t["next"], zone) if t.get("next") else None
    if got.get("week"):
        out["days"] = [{"date": d.get("date"), "items": [_event(o, zone) for o in d.get("items") or []]} for d in got["week"].get("days") or []]
    if got.get("tasks"):
        t = got["tasks"]
        out["tasks"] = {"items": [{"id": x.get("id"), "title": str(x.get("title") or "")[:120], "late": bool(x.get("late")),
                                   "color": x.get("color"), "due": x.get("due"), "allDay": bool(x.get("allDay"))} for x in t.get("today") or []],
                        "more": t.get("more") or 0, "overdue": t.get("overdue") or 0}
    if got.get("photos"):
        p = got["photos"]
        items = p.get("items") or []
        # landscape ones first: the Tab5 hangs landscape
        items = sorted(items, key=lambda it: 0 if not (it.get("w") and it.get("h")) or it["w"] >= it["h"] else 1)
        out["photos"] = [{"id": str(it.get("id")), "year": it.get("year"), "yearsAgo": it.get("yearsAgo") if p.get("kind") == "onthisday" else None}
                         for it in items if it.get("id") is not None]
    return out


# ------------------------------------------------------------------ the photos, at the device's size

PHOTO_MAX = (1920, 1200)
_photos: "OrderedDict[tuple, bytes]" = OrderedDict()  # (photo id, w, h) -> JPEG, the last few
PHOTO_CACHE = 16
_plock = threading.Lock()


def photo(request, photo_id: str, w: int, h: int) -> bytes:
    """An ioPix photo cut to fill w × h (as the page's wall does: object-fit cover), as a baseline JPEG the device's
    decoder takes (no progressive, 4:2:0). The few last ones are kept, so a device that asks again is not slow."""
    w = max(64, min(int(w or 1280), PHOTO_MAX[0]))
    h = max(64, min(int(h or 720), PHOTO_MAX[1]))
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", photo_id or ""):
        raise widgets.Unavailable(404, "No such photo")
    key = (photo_id, w, h)
    with _plock:
        if key in _photos:
            _photos.move_to_end(key)
            return _photos[key]
    body, _ = widgets.image(request, "iopix", "photo", photo_id, "preview")
    from PIL import Image, ImageOps
    try:
        im = Image.open(io.BytesIO(body))
        im = ImageOps.exif_transpose(im)
        im = im.convert("RGB")
        im = ImageOps.fit(im, (w, h), Image.LANCZOS, centering=(0.5, 0.42))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82, progressive=False, optimize=False, subsampling=2)
    except Exception as e:  # noqa: BLE001  a file Pillow cannot read
        raise widgets.Unavailable(502, f"The photo could not be read ({type(e).__name__})")
    out = buf.getvalue()
    with _plock:
        _photos[key] = out
        while len(_photos) > PHOTO_CACHE:
            _photos.popitem(last=False)
    return out


# ------------------------------------------------------------------ the taps that change something

def task_done(request, task_id: str) -> dict:
    """Ticks off a task in ioTask, as the viewer."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", str(task_id)):
        raise widgets.Unavailable(404, "No such task")
    return widgets.fetch(request, "iotask", f"/api/tasks/{task_id}/complete", body={}) or {"ok": True}


def favorite(request, photo_id: str, on: bool) -> dict:
    """Adds a photo to (or takes it from) the viewer's ioPix favorites."""
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", photo_id or ""):
        raise widgets.Unavailable(404, "No such photo")
    pid = int(photo_id) if photo_id.isdigit() else photo_id
    widgets.fetch(request, "iopix", "/api/favorites", body={"ids": [pid], "on": bool(on)})
    return {"ok": True, "on": bool(on)}


def base_url(request) -> str:
    """Where people open the start page: PUBLIC_URL, else the address the device asked at."""
    if config.PUBLIC_URL:
        return config.PUBLIC_URL.rstrip("/")
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{proto}://{host}"

