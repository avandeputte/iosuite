"""ioPix's answers to the suite's standard endpoints (iosuite_shared.suiteitems): the people, albums, folders and
places the search box finds (photos for the linked-items picker), one photo, a picture, and the start page's tile
(On this day, else Rediscover)."""
import datetime as dt
import hashlib
import random
import threading
import time
import unicodedata
import urllib.parse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from iosuite_shared.suiteitems import Provider, item, wall_time

NAMES_TTL = 120    # seconds the names of one viewer's ioPix are kept for the search box
_names: dict = {}  # who -> (until, [{kind, id, name, n, cover, …}])
_names_lock = threading.Lock()
KINDS = {"person": ("person", "Person"), "album": ("photo", "Album"), "folder": ("folder", "Folder"), "place": ("place", "Place")}


def _zone(tz: str):
    try:
        return ZoneInfo(tz) if tz else dt.timezone.utc
    except (ZoneInfoNotFoundError, ValueError):
        return dt.timezone.utc


def _fold(s) -> str:
    """Lower case without accents, as the start page folds the bookmarks."""
    return "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if not unicodedata.combining(c)).lower()


def _who(local) -> str | None:
    """This viewer's sign-in (the session cookie or the Authorization header), hashed: whose names are kept."""
    h = dict(local.scope.get("headers") or [])
    tok = (h.get(b"cookie") or b"") + b"|" + (h.get(b"authorization") or b"")
    return hashlib.blake2b(tok, digest_size=16).hexdigest() if tok != b"|" else None


def _names_of(local) -> list[dict]:
    """The people, the albums (the viewer's and the shared ones), the folders and the places, each with how many
    photos and one to show. Read from /api/meta and /api/state and kept NAMES_TTL seconds for this viewer."""
    who, now = _who(local), time.monotonic()
    with _names_lock:
        hit = _names.get(who) if who else None
        if hit and hit[0] > now:
            return hit[1]
    meta, state = local.together(lambda: local.get("/api/meta"), lambda: local.get("/api/state"))
    if isinstance(meta, Exception):
        raise meta
    out = []
    for t in meta.get("tags") or []:
        if t.get("person") and t.get("nAll"):
            out.append({"kind": "person", "id": t.get("id"), "name": t.get("name"), "n": t.get("nAll"), "cover": t.get("cover")})
    for a in ([] if isinstance(state, Exception) else state.get("albums") or []):
        out.append({"kind": "album", "id": a.get("id"), "name": a.get("name"), "n": a.get("n") or 0, "cover": a.get("cover")})
    for a in meta.get("albums") or []:
        if a.get("name") and a.get("nAll"):
            out.append({"kind": "folder", "id": a.get("id"), "name": a.get("name"), "n": a.get("nAll"), "cover": a.get("cover")})
    for p in meta.get("places") or []:
        if len(p) >= 5 and p[0]:
            out.append({"kind": "place", "id": None, "name": p[0], "region": p[1] or "", "country": p[2] or "", "n": p[3], "cover": p[4]})
    for x in out:
        x["_f"] = _fold(" ".join(str(x.get(k) or "") for k in ("name", "region", "country")))
        x["_n"] = _fold(x["name"])
    with _names_lock:
        if len(_names) > 200:
            _names.clear()
        if who:
            _names[who] = (now + NAMES_TTL, out)
    return out


def _named(x: dict) -> dict:
    kind = x["kind"]
    if kind == "person":
        q = {"tag": x["id"]}
    elif kind == "album":
        q = {"ualbum": x["id"]}
    elif kind == "folder":
        q = {"album": x["id"]}
    else:
        q = {"place": x["name"], **({"region": x["region"]} if x.get("region") else {})}
    n = x.get("n") or 0
    title = f"{x['name']}, {x['region']}" if kind == "place" and x.get("region") else x["name"]
    return item("iopix", kind, x.get("id") if x.get("id") is not None else x["name"], title, f"{KINDS[kind][1]} · {n:,} photo{'' if n == 1 else 's'}",
                image=str(x["cover"]) if x.get("cover") else None, href="#/photos?" + urllib.parse.urlencode(q),
                round=kind == "person", icon=KINDS[kind][0])


def _photo(pid, ts) -> dict:
    return item("iopix", "photo", pid, "Photo", "", wall_time(ts), image="", icon="photo")


def search(local, q, n, tz, kinds):
    """The search box: the people, albums, folders and places whose name has every word of q (a place: its town,
    region or country), the ones that start with it first, then the ones with the most photos; up to three of a kind,
    n in all. With kinds=photo (the linked-items picker): the photos ioPix finds for q."""
    if kinds:
        if "photo" not in kinds:
            return []
        got = local.get("/api/photos", {"q": q, "type": "photo"})
        return [_photo(pid, ts) for pid, ts in list(zip(got.get("id") or [], got.get("ts") or []))[:max(n, 12)]]
    words = _fold(q).split()
    if not words:
        return []
    found = [x for x in _names_of(local) if all(w in x["_f"] for w in words)]
    found.sort(key=lambda x: (not x["_n"].startswith(words[0]), -(x.get("n") or 0)))
    out, per = [], {}
    for kind in KINDS:
        for x in found:
            if x["kind"] == kind and per.get(kind, 0) < 3:
                per[kind] = per.get(kind, 0) + 1
                out.append(_named(x))
    return {"items": out[:n], "more": len(found) > n}


def get(local, kind, item_id):
    if kind != "photo" or not item_id.isdigit():
        return None
    p = local.get(f"/api/photo/{item_id}")
    album = (p.get("album") or {}).get("name") if isinstance(p.get("album"), dict) else None
    title = p.get("title") or p.get("caption") or album or p.get("name") or "Photo"
    return item("iopix", "photo", p.get("id") or item_id, title, album if album and album != title else "", wall_time(p.get("ts")),
                image="", icon="photo")


def image(local, kind, item_id, p):
    """A photo's square thumbnail (p "preview": its screen-size copy, which ioPix may have to make first); a person,
    album, folder or place: the photo p, its cover."""
    if kind == "photo" and item_id.isdigit():
        return local.raw(f"/preview/{item_id}") if p == "preview" else local.raw(f"/thumb/{item_id}", {"fit": "square"})
    if kind in KINDS and p.isdigit():
        return local.raw(f"/thumb/{p}", {"fit": "square"})
    return None


def _random(local, n, params=None) -> list[dict]:
    got = local.get("/api/random", {"n": n, **(params or {})})
    ws, hs = got.get("w") or [], got.get("h") or []
    return [{"id": pid, "year": dt.datetime.fromtimestamp(ts, dt.timezone.utc).year if ts else None,
             **({"w": ws[i], "h": hs[i]} if i < len(ws) and i < len(hs) and ws[i] and hs[i] else {})}
            for i, (pid, ts) in enumerate(zip(got.get("id") or [], got.get("ts") or []))]


def tile(local, tz, n, kind):
    """{kind: onthisday | rediscover, items: [{id, year, yearsAgo}], count}: up to n photos taken on this day in
    earlier years, one from each year first (the most recent years first), then the rest of those years; count is
    how many there are in all. On a day without any, n photos picked at random from the library (with w and h: the
    wall display prefers landscape ones). kind asks for one of the two (onthisday still falls back to rediscover).
    For the wall display, kind "favorites" (the viewer's) or "album:<id>" (one of the app's albums the viewer may
    see) picks n of those at random ({kind, items}; none: the library's, as rediscover), and "albums" lists the albums
    to choose from: {kind: albums, albums: [{id, name, n}]}."""
    n = n or 4
    if kind == "albums":
        state = local.get("/api/state")
        return {"kind": "albums", "albums": [{"id": a.get("id"), "name": a.get("name"), "n": a.get("n") or 0}
                                             for a in state.get("albums") or [] if a.get("id") and a.get("name")]}
    pick = {"fav": "1"} if kind == "favorites" else {"ualbum": kind[6:]} if kind.startswith("album:") and kind[6:].isdigit() else None
    if pick:
        items = _random(local, n, pick)
        if items:
            return {"kind": kind, "items": items}
        kind = "rediscover"
    today = dt.datetime.now(_zone(tz)).date()
    by_year: dict[int, list] = {}
    if kind != "rediscover":
        got = local.get("/api/photos", {"md": today.strftime("%m-%d"), "type": "photo"})
        for pid, ts in zip(got.get("id") or [], got.get("ts") or []):
            if ts is None:
                continue
            y = dt.datetime.fromtimestamp(ts, dt.timezone.utc).year  # the camera's wall time, kept as if it were UTC
            if y < today.year:
                by_year.setdefault(y, []).append(pid)
    if by_year:
        years = sorted(by_year, reverse=True)
        for y in years:
            random.shuffle(by_year[y])
        items: list[dict] = []
        for i in range(max(len(v) for v in by_year.values())):  # round i: the i-th photo of each year
            items += [{"id": by_year[y][i], "year": y, "yearsAgo": today.year - y} for y in years if i < len(by_year[y])]
        return {"kind": "onthisday", "items": items[:n], "count": sum(len(v) for v in by_year.values())}
    return {"kind": "rediscover", "items": _random(local, n)}


PROVIDER = Provider(search=search, get=get, image=image, tile=tile)
