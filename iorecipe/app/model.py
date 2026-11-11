"""Recipes: what one is, who sees it and who may change it, and the search.

A recipe is either a family recipe (owner_id NULL: everyone with a role here sees it; editors and admins change it)
or the private recipe of one account (only that account sees it; members and more keep their own). A viewer only looks.
"""
import json
import re

from iosuite_shared import users as shared_users
from iosuite_shared.errors import Invalid

from app import db, images


class NotFound(Exception):
    """No such recipe (or not one this account sees)."""


class Forbidden(Exception):
    """The account sees it but may not do this."""


MAX_LINES = 400       # ingredients or steps of one recipe
MAX_LINE = 4000       # one of them
MAX_TAGS = 30


# ---- who may

def can_read(u: dict | None, r: dict | None) -> bool:
    return bool(u and r) and (r["owner_id"] is None or r["owner_id"] == u["id"])


def can_write(u: dict | None, r: dict | None) -> bool:
    """A family recipe: editors and admins. One's own private recipe: members and more (a viewer only looks)."""
    if not can_read(u, r):
        return False
    return shared_users.can_write(u) if r["owner_id"] is None else shared_users.is_member(u)


def may_add(u: dict, family: bool) -> bool:
    return shared_users.can_write(u) if family else shared_users.is_member(u)


# ---- the fields, as they come in

def _text(v, limit: int, name: str) -> str | None:
    if v is None:
        return None
    s = re.sub(r"[ \t\r\f\v]+", " ", str(v)).strip() if limit <= 2048 else str(v).replace("\r\n", "\n").strip()
    if len(s) > limit:
        raise Invalid(f"{name} is too long (at most {limit} characters)")
    return s or None


def _lines(v, name: str) -> list[str]:
    """A list of lines, from a list of strings or from one text with a line each."""
    if v is None:
        return []
    if isinstance(v, str):
        v = v.replace("\r\n", "\n").split("\n")
    if not isinstance(v, list):
        raise Invalid(f"{name}: a list of lines is expected")
    out = [re.sub(r"\s+", " ", str(x)).strip() for x in v if x is not None]
    out = [x for x in out if x]
    if len(out) > MAX_LINES or any(len(x) > MAX_LINE for x in out):
        raise Invalid(f"{name}: too many lines, or one that is too long")
    return out


def _tags(v) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = v.split(",")
    if not isinstance(v, list):
        raise Invalid("tags: a list of words is expected")
    out: list[str] = []
    for x in v:
        t = re.sub(r"\s+", " ", str(x)).strip().strip("#")[:40]
        if t and t.lower() not in [o.lower() for o in out]:
            out.append(t)
    return out[:MAX_TAGS]


def _minutes(v, name: str) -> int | None:
    if v in (None, ""):
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise Invalid(f"{name}: a number of minutes is expected")
    if not 0 <= n <= 60 * 24 * 30:
        raise Invalid(f"{name}: between 0 and 30 days, in minutes")
    return n or None


def _url(v) -> str | None:
    s = _text(v, 2048, "The link")
    return s if s and re.match(r"https?://", s, re.I) else None


FIELDS = {
    "title": lambda v: _text(v, 255, "The title"),
    "description": lambda v: _text(v, 4000, "The description"),
    "servings": lambda v: _text(v, 64, "Servings"),
    "prepMinutes": lambda v: _minutes(v, "Preparation time"),
    "cookMinutes": lambda v: _minutes(v, "Cooking time"),
    "totalMinutes": lambda v: _minutes(v, "Total time"),
    "ingredients": lambda v: _lines(v, "Ingredients"),
    "steps": lambda v: _lines(v, "Steps"),
    "notes": lambda v: _text(v, 20000, "The notes"),
    "tags": _tags,
    "sourceUrl": _url,
    "sourceName": lambda v: _text(v, 255, "The source"),
}
COLUMNS = {"title": "title", "description": "description", "servings": "servings", "prepMinutes": "prep_minutes",
           "cookMinutes": "cook_minutes", "totalMinutes": "total_minutes", "ingredients": "ingredients", "steps": "steps",
           "notes": "notes", "tags": "tags", "sourceUrl": "source_url", "sourceName": "source_name"}
JSON_COLUMNS = ("ingredients", "steps", "tags")


def clean(data: dict, partial: bool = False) -> dict:
    """The fields of `data` that are a recipe's, checked, by column. Not partial: every field, the missing ones empty."""
    out = {}
    for k, fn in FIELDS.items():
        if k in data or not partial:
            out[COLUMNS[k]] = fn(data.get(k))
    if "title" in out and not out["title"]:
        raise Invalid("A title, please")
    return out


def _words(r: dict) -> str:
    parts = [r.get("title"), r.get("description"), r.get("notes"), r.get("source_name"),
             *(r.get("ingredients") or []), *(r.get("steps") or []), *(r.get("tags") or [])]
    return "\n".join(p for p in parts if p).lower()


def _row(r: dict | None) -> dict | None:
    if r:
        for k in JSON_COLUMNS:
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k] or "[]")
    return r


# ---- reading

LIST_COLUMNS = "id, owner_id, title, description, servings, prep_minutes, cook_minutes, total_minutes, tags, source_name, photo, updated_at, created_at"


def get(rid: int) -> dict | None:
    return _row(db.one("SELECT * FROM rcp_recipes WHERE id = %s", (int(rid),)))


def readable(u: dict, rid) -> dict:
    r = get(rid) if str(rid).isdigit() else None
    if not can_read(u, r):
        raise NotFound("No such recipe")
    return r


def _scope(u: dict, scope: str | None) -> tuple[str, list]:
    if scope == "family":
        return "owner_id IS NULL", []
    if scope == "mine":
        return "owner_id = %s", [u["id"]]
    return "(owner_id IS NULL OR owner_id = %s)", [u["id"]]


def find(u: dict, q: str = "", tag: str | None = None, scope: str | None = None, limit: int = 500, full: bool = False) -> list[dict]:
    """The recipes this account sees, by title: every word of q somewhere in them, with this tag, family or mine."""
    where, args = _scope(u, scope)
    for w in (q or "").lower().split()[:8]:
        where += " AND words LIKE %s"
        args.append("%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    rows = db.q(f"SELECT {'*' if full else LIST_COLUMNS} FROM rcp_recipes WHERE {where} ORDER BY title, id", args)
    rows = [_row(r) for r in rows]
    if tag:
        rows = [r for r in rows if tag.lower() in [t.lower() for t in r["tags"]]]
    return rows[:max(1, min(int(limit), 2000))]


def tags(u: dict) -> list[dict]:
    """[{tag, count}] over the recipes this account sees, the most used first."""
    where, args = _scope(u, None)
    n: dict[str, list] = {}
    for r in db.q(f"SELECT tags FROM rcp_recipes WHERE {where}", args):
        for t in json.loads(r["tags"] or "[]"):
            n.setdefault(t.lower(), [t, 0])[1] += 1
    return [{"tag": t, "count": c} for t, c in sorted(n.values(), key=lambda x: (-x[1], x[0].lower()))]


def counts(u: dict) -> dict:
    r = db.one("SELECT count(*) AS n, COALESCE(SUM(owner_id IS NULL), 0) AS fam FROM rcp_recipes WHERE (owner_id IS NULL OR owner_id = %s)", (u["id"],))
    return {"all": int(r["n"]), "family": int(r["fam"]), "mine": int(r["n"]) - int(r["fam"])}


# ---- changing

def create(u: dict, data: dict, family: bool) -> dict:
    if not may_add(u, family):
        raise Forbidden("Only editors add family recipes" if family else "A viewer only looks; a member keeps recipes of their own")
    f = clean(data)
    f["words"] = _words(f)
    for k in JSON_COLUMNS:
        f[k] = json.dumps(f[k], ensure_ascii=False)
    f["owner_id"] = None if family else u["id"]
    f["created_by"] = u["id"]
    cols = list(f)
    rid = db.ex(f"INSERT INTO rcp_recipes ({', '.join(cols)}) VALUES ({db.marks(len(cols))})", [f[c] for c in cols])
    return get(rid)


def update(u: dict, r: dict, data: dict) -> dict:
    """Change the fields given; `family` (true or false) moves the recipe between the family's and one's own."""
    if not can_write(u, r):
        raise Forbidden("You can see this recipe but not change it")
    f = clean(data, partial=True)
    merged = {**r, **f}
    sets = {k: (json.dumps(v, ensure_ascii=False) if k in JSON_COLUMNS else v) for k, v in f.items()}
    sets["words"] = _words(merged)
    if "family" in data and bool(data["family"]) != (r["owner_id"] is None):
        if not shared_users.can_write(u):
            raise Forbidden("Only editors move a recipe to or from the family's")
        sets["owner_id"] = None if data["family"] else u["id"]
    db.ex(f"UPDATE rcp_recipes SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), r["id"]])
    return get(r["id"])


def delete(u: dict, r: dict) -> None:
    if not can_write(u, r):
        raise Forbidden("You can see this recipe but not delete it")
    db.ex("DELETE FROM rcp_recipes WHERE id = %s", (r["id"],))


# ---- the photo

def set_photo(u: dict, r: dict, raw: bytes) -> dict:
    if not can_write(u, r):
        raise Forbidden("You can see this recipe but not change it")
    pic = images.prepare(raw)
    with db.tx():
        db.ex("REPLACE INTO rcp_photos (recipe_id, picture, thumb, width, height) VALUES (%s, %s, %s, %s, %s)",
              (r["id"], pic["picture"], pic["thumb"], pic["width"], pic["height"]))
        db.ex("UPDATE rcp_recipes SET photo = photo + 1 WHERE id = %s", (r["id"],))
    return get(r["id"])


def remove_photo(u: dict, r: dict) -> dict:
    if not can_write(u, r):
        raise Forbidden("You can see this recipe but not change it")
    with db.tx():
        db.ex("DELETE FROM rcp_photos WHERE recipe_id = %s", (r["id"],))
        db.ex("UPDATE rcp_recipes SET photo = 0 WHERE id = %s", (r["id"],))
    return get(r["id"])


def photo(rid: int, small: bool) -> bytes | None:
    r = db.one(f"SELECT {'thumb' if small else 'picture'} AS b FROM rcp_photos WHERE recipe_id = %s", (int(rid),))
    return bytes(r["b"]) if r else None


# ---- as JSON

def public(r: dict, u: dict, full: bool = True) -> dict:
    out = {"id": r["id"], "title": r["title"], "description": r.get("description"), "family": r["owner_id"] is None,
           "servings": r.get("servings"), "prepMinutes": r.get("prep_minutes"), "cookMinutes": r.get("cook_minutes"),
           "totalMinutes": r.get("total_minutes") or ((r.get("prep_minutes") or 0) + (r.get("cook_minutes") or 0)) or None,
           "tags": r.get("tags") or [], "sourceName": r.get("source_name"),
           "photo": f"/api/recipes/{r['id']}/photo?v={r['photo']}" if r.get("photo") else None,
           "writable": can_write(u, r),
           "updated": r["updated_at"].isoformat() if r.get("updated_at") else None}
    if full:
        out.update(ingredients=r["ingredients"], steps=r["steps"], notes=r.get("notes"), sourceUrl=r.get("source_url"),
                   created=r["created_at"].isoformat() if r.get("created_at") else None)
    return out
