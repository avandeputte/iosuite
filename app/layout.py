"""Each person's own start page: which tiles and cards they see, in what order, and which photo strip.

Saved per account in the meta table ("user:<id>:layout", JSON), on top of what the admin set in Settings › Apps:
an app the admin hid is not on anyone's page; one the admin shows, a person may hide for themselves. Empty: the page
as the admin laid it out."""
import json

from app import apps, db

SECTIONS = ("birthdays", "week", "strip", "bookmarks")  # the cards under the tiles, hideable like a tile
EMPTY = {"hidden": [], "order": [], "cards": [], "strip": None}


def _key(user_id: int) -> str:
    return f"user:{int(user_id)}:layout"


def get(user_id: int) -> dict:
    """{hidden: [tile or section keys], order: [tile keys, the first ones first], cards: [section keys, top first],
    strip: rediscover|onthisday|off|null}."""
    raw = db.get_setting(_key(user_id))
    if not raw:
        return dict(EMPTY)
    try:
        v = json.loads(raw)
    except ValueError:
        return dict(EMPTY)
    return {"hidden": [k for k in v.get("hidden", []) if k in apps.KEYS or k in SECTIONS],
            "order": [k for k in v.get("order", []) if k in apps.KEYS],
            "cards": [k for k in v.get("cards", []) if k in SECTIONS],
            "strip": v.get("strip") if v.get("strip") in apps.STRIPS else None}


def save(user_id: int, body: dict) -> dict:
    """Checks and keeps the layout; {} (or everything empty) puts the page back as the admin laid it out."""
    if not isinstance(body, dict):
        raise ValueError("An object, please")
    hidden = body.get("hidden") or []
    order = body.get("order") or []
    cards = body.get("cards") or []
    strip = body.get("strip") or None
    if not isinstance(hidden, list) or not all(isinstance(k, str) and (k in apps.KEYS or k in SECTIONS) for k in hidden):
        raise ValueError(f"hidden: a list of {', '.join(apps.KEYS + list(SECTIONS))}")
    if not isinstance(order, list) or not all(isinstance(k, str) and k in apps.KEYS for k in order) or len(set(order)) != len(order):
        raise ValueError(f"order: a list of {', '.join(apps.KEYS)}, each once")
    if not isinstance(cards, list) or not all(isinstance(k, str) and k in SECTIONS for k in cards) or len(set(cards)) != len(cards):
        raise ValueError(f"cards: a list of {', '.join(SECTIONS)}, each once")
    if strip is not None and strip not in apps.STRIPS:
        raise ValueError("strip: rediscover, onthisday, off, or nothing (the admin's choice)")
    v = {"hidden": list(dict.fromkeys(hidden)), "order": order, "cards": cards, "strip": strip}
    db.set_setting(_key(user_id), None if v == EMPTY else json.dumps(v))
    return get(user_id)
