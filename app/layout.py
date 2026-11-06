"""Each person's own start page: which tiles and cards they see, in what order, and which photo strip.

Saved per account in the prt_settings table ("user:<id>:layout", JSON). Every app registered in the suite's list is on the
page unless the person hides it; the photo strip is the admin's choice (Settings › Home page) unless they pick another.
Empty: the page as it comes."""
import json

from app import apps, db

SECTIONS = ("home", "birthdays", "week", "strip", "bookmarks")  # the cards under the tiles, hideable like a tile (home: Home Assistant)
ENGINES = ("duckduckgo", "google", "bing", "startpage", "ecosia", "kagi")  # the search box's web search (null: DuckDuckGo)
EMPTY = {"hidden": [], "order": [], "cards": [], "strip": None, "search": None}


def _key(user_id: int) -> str:
    return f"user:{int(user_id)}:layout"


def get(user_id: int) -> dict:
    """{hidden: [tile or section keys], order: [tile keys, the first ones first], cards: [section keys, top first],
    strip: rediscover|onthisday|off|null, search: a web search engine (ENGINES) | null}."""
    raw = db.get_setting(_key(user_id))
    if not raw:
        return dict(EMPTY)
    try:
        v = json.loads(raw)
    except ValueError:
        return dict(EMPTY)
    return {"hidden": [k for k in v.get("hidden", []) if apps.is_key(k) or k in SECTIONS],
            "order": [k for k in v.get("order", []) if apps.is_key(k)],
            "cards": [k for k in v.get("cards", []) if k in SECTIONS],
            "strip": v.get("strip") if v.get("strip") in apps.STRIPS else None,
            "search": v.get("search") if v.get("search") in ENGINES else None}


def save(user_id: int, body: dict) -> dict:
    """Checks and keeps the layout; {} (or everything empty) puts the page back as the admin laid it out."""
    if not isinstance(body, dict):
        raise ValueError("An object, please")
    hidden = body.get("hidden") or []
    order = body.get("order") or []
    cards = body.get("cards") or []
    strip = body.get("strip") or None
    search = body.get("search") or None
    if not isinstance(hidden, list) or not all(apps.is_key(k) or k in SECTIONS for k in hidden):
        raise ValueError(f"hidden: a list of app keys and {', '.join(SECTIONS)}")
    if not isinstance(order, list) or not all(apps.is_key(k) for k in order) or len(set(order)) != len(order):
        raise ValueError("order: a list of app keys, each once")
    if not isinstance(cards, list) or not all(isinstance(k, str) and k in SECTIONS for k in cards) or len(set(cards)) != len(cards):
        raise ValueError(f"cards: a list of {', '.join(SECTIONS)}, each once")
    if strip is not None and strip not in apps.STRIPS:
        raise ValueError("strip: rediscover, onthisday, off, or nothing (the admin's choice)")
    if search is not None and search not in ENGINES:
        raise ValueError(f"search: {', '.join(ENGINES)}, or nothing (DuckDuckGo)")
    v = {"hidden": list(dict.fromkeys(hidden)), "order": order, "cards": cards, "strip": strip, "search": search}
    db.set_setting(_key(user_id), None if v == EMPTY else json.dumps(v))
    return get(user_id)
