"""Recipes: what one is, who sees it and who may change it, and the search.

A recipe is either a family recipe (owner_id NULL: everyone with a role here sees it; editors and admins change it)
or the private recipe of one account (only that account sees it; members and more keep their own). A viewer only looks.

Around a recipe: its photos (its own, the first of which the cards show, and one for a step), what each account
thinks of it (a favourite, a rating of 1 to 5) and the cookbooks it is in (a family cookbook holds family recipes; a
private one is its owner's).
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
MAX_PHOTOS = 40       # of one recipe, its steps' included


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
# what the account asking thinks of it, and what everyone who rated it does
MARKS = ("COALESCE(m.favourite, 0) AS favourite, m.rating AS rating, "
         "(SELECT AVG(x.rating) FROM rcp_marks x WHERE x.recipe_id = r.id AND x.rating IS NOT NULL) AS rating_avg, "
         "(SELECT COUNT(x.rating) FROM rcp_marks x WHERE x.recipe_id = r.id AND x.rating IS NOT NULL) AS rating_n")
SORTS = {"title": "r.title, r.id", "new": "r.created_at DESC, r.id DESC", "rating": "rating_avg IS NULL, rating_avg DESC, r.title, r.id"}


def get(rid: int, u: dict | None = None) -> dict | None:
    """The recipe; with u, what that account thinks of it too (favourite, rating, and everyone's average)."""
    if u is None:
        return _row(db.one("SELECT * FROM rcp_recipes WHERE id = %s", (int(rid),)))
    return _row(db.one(f"SELECT r.*, {MARKS} FROM rcp_recipes r LEFT JOIN rcp_marks m ON m.recipe_id = r.id AND m.user_id = %s WHERE r.id = %s",
                       (u["id"], int(rid))))


def readable(u: dict, rid) -> dict:
    r = get(rid, u) if str(rid).isdigit() else None
    if not can_read(u, r):
        raise NotFound("No such recipe")
    return r


def _scope(u: dict, scope: str | None) -> tuple[str, list]:
    if scope == "family":
        return "r.owner_id IS NULL", []
    if scope == "mine":
        return "r.owner_id = %s", [u["id"]]
    seen = "(r.owner_id IS NULL OR r.owner_id = %s)"
    if scope == "favourites":
        return seen + " AND m.favourite = 1", [u["id"]]
    return seen, [u["id"]]


def find(u: dict, q: str = "", tag: str | None = None, scope: str | None = None, limit: int = 500, full: bool = False,
         book: int | None = None, sort: str | None = None) -> list[dict]:
    """The recipes this account sees: every word of q somewhere in them, with this tag, the family's, its own or its
    favourites, in this cookbook; by title, or the newest or the best rated first."""
    where, args = _scope(u, scope)
    join = "LEFT JOIN rcp_marks m ON m.recipe_id = r.id AND m.user_id = %s"
    if book is not None:
        b = readable_book(u, book)
        join += " JOIN rcp_book_recipes br ON br.recipe_id = r.id AND br.book_id = %s"
        args = [b["id"], *args]
    for w in (q or "").lower().split()[:8]:
        where += " AND r.words LIKE %s"
        args.append("%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    cols = "r.*" if full else ", ".join("r." + c.strip() for c in LIST_COLUMNS.split(","))
    rows = db.q(f"SELECT {cols}, {MARKS} FROM rcp_recipes r {join} WHERE {where} ORDER BY {SORTS.get(sort or 'title', SORTS['title'])}", [u["id"], *args])
    rows = [_row(r) for r in rows]
    if tag:
        rows = [r for r in rows if tag.lower() in [t.lower() for t in r["tags"]]]
    return rows[:max(1, min(int(limit), 2000))]


def tags(u: dict) -> list[dict]:
    """[{tag, count}] over the recipes this account sees, the most used first."""
    n: dict[str, list] = {}
    for r in db.q("SELECT tags FROM rcp_recipes r WHERE (r.owner_id IS NULL OR r.owner_id = %s)", (u["id"],)):
        for t in json.loads(r["tags"] or "[]"):
            n.setdefault(t.lower(), [t, 0])[1] += 1
    return [{"tag": t, "count": c} for t, c in sorted(n.values(), key=lambda x: (-x[1], x[0].lower()))]


def counts(u: dict) -> dict:
    r = db.one("SELECT count(*) AS n, COALESCE(SUM(r.owner_id IS NULL), 0) AS fam, COALESCE(SUM(m.favourite = 1), 0) AS fav FROM rcp_recipes r "
               "LEFT JOIN rcp_marks m ON m.recipe_id = r.id AND m.user_id = %s WHERE (r.owner_id IS NULL OR r.owner_id = %s)", (u["id"], u["id"]))
    return {"all": int(r["n"]), "family": int(r["fam"]), "mine": int(r["n"]) - int(r["fam"]), "favourites": int(r["fav"])}


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
    return get(rid, u)


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
    with db.tx():
        db.ex(f"UPDATE rcp_recipes SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), r["id"]])
        if "steps" in f and f["steps"] != r["steps"]:
            _move_step_photos(r["id"], r["steps"], f["steps"])
        if sets.get("owner_id", None) is not None:
            # private now: out of the family's cookbooks, and nobody else's favourite or rating stays on it
            db.ex("DELETE br FROM rcp_book_recipes br JOIN rcp_books b ON b.id = br.book_id WHERE br.recipe_id = %s AND b.owner_id IS NULL", (r["id"],))
            db.ex("DELETE FROM rcp_marks WHERE recipe_id = %s AND user_id <> %s", (r["id"], u["id"]))
    return get(r["id"], u)


def delete(u: dict, r: dict) -> None:
    if not can_write(u, r):
        raise Forbidden("You can see this recipe but not delete it")
    db.ex("DELETE FROM rcp_recipes WHERE id = %s", (r["id"],))


# ---- the photos

def _writable(u: dict, r: dict) -> None:
    if not can_write(u, r):
        raise Forbidden("You can see this recipe but not change it")


def _cover(rid: int) -> None:
    """The picture the cards show: the first of the recipe's own."""
    p = db.one("SELECT id FROM rcp_photos WHERE recipe_id = %s AND step IS NULL ORDER BY position, id LIMIT 1", (rid,))
    db.ex("UPDATE rcp_recipes SET photo = %s WHERE id = %s", (p["id"] if p else 0, rid))


def photos(rid: int) -> list[dict]:
    """The recipe's pictures without their bytes: its own in their order, then the steps'."""
    return db.q("SELECT id, step, position, width, height FROM rcp_photos WHERE recipe_id = %s ORDER BY step IS NOT NULL, step, position, id", (int(rid),))


def add_photo(u: dict, r: dict, raw: bytes, step: int | None = None) -> dict:
    """One more picture of the recipe (the first is the one the cards show), or the picture of a step (it replaces
    the one that step had). The picture's row, without its bytes."""
    _writable(u, r)
    if step is not None:
        if not 0 <= int(step) < len(r["steps"]):
            raise Invalid("This recipe has no such step")
        step = int(step)
    pic = images.prepare(raw)
    with db.tx():
        if step is not None:
            db.ex("DELETE FROM rcp_photos WHERE recipe_id = %s AND step = %s", (r["id"], step))
        n = db.one("SELECT COUNT(*) AS n, COALESCE(MAX(position), -1) AS last FROM rcp_photos WHERE recipe_id = %s", (r["id"],))
        if n["n"] >= MAX_PHOTOS:
            raise Invalid(f"A recipe holds at most {MAX_PHOTOS} photos")
        pid = db.ex("INSERT INTO rcp_photos (recipe_id, step, position, picture, thumb, width, height) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (r["id"], step, n["last"] + 1, pic["picture"], pic["thumb"], pic["width"], pic["height"]))
        _cover(r["id"])
    return {"id": pid, "step": step, "width": pic["width"], "height": pic["height"]}


def remove_photo(u: dict, r: dict, pid: int) -> None:
    _writable(u, r)
    with db.tx():
        if not db.ex("DELETE FROM rcp_photos WHERE id = %s AND recipe_id = %s", (int(pid), r["id"])):
            raise NotFound("This recipe has no such photo")
        _cover(r["id"])


def order_photos(u: dict, r: dict, ids: list) -> None:
    """The recipe's own pictures in this order (the first is the one the cards show); those left out follow."""
    _writable(u, r)
    have = [p["id"] for p in photos(r["id"]) if p["step"] is None]
    want = [int(i) for i in ids if str(i).isdigit() and int(i) in have]
    order = list(dict.fromkeys(want)) + [i for i in have if i not in want]
    with db.tx():
        for n, pid in enumerate(order):
            db.ex("UPDATE rcp_photos SET position = %s WHERE id = %s", (n, pid))
        _cover(r["id"])


def _move_step_photos(rid: int, old: list[str], new: list[str]) -> None:
    """The steps changed: each step's picture follows its step (the same words), stays where it was when that place
    still holds a step, and otherwise becomes one of the recipe's own."""
    rows = db.q("SELECT id, step FROM rcp_photos WHERE recipe_id = %s AND step IS NOT NULL ORDER BY step", (rid,))
    taken: set[int] = set()
    for p in rows:
        text = old[p["step"]] if p["step"] < len(old) else None
        to = next((i for i, s in enumerate(new) if s == text and i not in taken), None)
        if to is None and p["step"] < len(new) and p["step"] not in taken and new[p["step"]] not in old:
            to = p["step"]  # the step was reworded where it stands
        if to is not None:
            taken.add(to)
        db.ex("UPDATE rcp_photos SET step = %s WHERE id = %s", (to, p["id"]))
    _cover(rid)


def photo(rid: int, pid: int, small: bool) -> bytes | None:
    r = db.one(f"SELECT {'thumb' if small else 'picture'} AS b FROM rcp_photos WHERE id = %s AND recipe_id = %s", (int(pid), int(rid)))
    return bytes(r["b"]) if r else None


# ---- favourites and ratings

def mark(u: dict, r: dict, data: dict) -> dict:
    """{favourite?: bool, rating?: 1 to 5, or null for none}: what this account thinks of the recipe."""
    if not shared_users.is_member(u):
        raise Forbidden("A viewer only looks")
    sets = {}
    if "favourite" in data:
        sets["favourite"] = 1 if data["favourite"] else 0
    if "rating" in data:
        v = data["rating"]
        if v in (None, "", 0):
            sets["rating"] = None
        else:
            try:
                sets["rating"] = int(v)
            except (TypeError, ValueError):
                raise Invalid("A rating is a number from 1 to 5")
            if not 1 <= sets["rating"] <= 5:
                raise Invalid("A rating is a number from 1 to 5")
    if sets:
        with db.tx():
            db.ex("INSERT IGNORE INTO rcp_marks (recipe_id, user_id) VALUES (%s, %s)", (r["id"], u["id"]))
            db.ex(f"UPDATE rcp_marks SET {', '.join(k + ' = %s' for k in sets)} WHERE recipe_id = %s AND user_id = %s", [*sets.values(), r["id"], u["id"]])
            db.ex("DELETE FROM rcp_marks WHERE recipe_id = %s AND user_id = %s AND favourite = 0 AND rating IS NULL", (r["id"], u["id"]))
    return get(r["id"], u)


# ---- cookbooks

def can_change_book(u: dict | None, b: dict | None) -> bool:
    """A family cookbook: editors and admins. One's own: members and more."""
    if not u or not b:
        return False
    return shared_users.can_write(u) if b["owner_id"] is None else (b["owner_id"] == u["id"] and shared_users.is_member(u))


def books(u: dict) -> list[dict]:
    """The cookbooks this account sees (the family's, then its own, by name), each with how many recipes it shows."""
    return db.q("SELECT b.*, (SELECT COUNT(*) FROM rcp_book_recipes br JOIN rcp_recipes r ON r.id = br.recipe_id "
                "WHERE br.book_id = b.id AND (r.owner_id IS NULL OR r.owner_id = %s)) AS n "
                "FROM rcp_books b WHERE b.owner_id IS NULL OR b.owner_id = %s ORDER BY b.owner_id IS NOT NULL, b.name, b.id", (u["id"], u["id"]))


def readable_book(u: dict, bid) -> dict:
    b = db.one("SELECT * FROM rcp_books WHERE id = %s", (int(bid),)) if str(bid).isdigit() else None
    if not b or not (b["owner_id"] is None or b["owner_id"] == u["id"]):
        raise NotFound("No such cookbook")
    return b


def _book_fields(data: dict, partial: bool) -> dict:
    out = {}
    if "name" in data or not partial:
        out["name"] = _text(data.get("name"), 191, "The name")
        if not out["name"]:
            raise Invalid("A name, please")
    if "description" in data or not partial:
        out["description"] = _text(data.get("description"), 4000, "The description")
    return out


def create_book(u: dict, data: dict, family: bool) -> dict:
    if not may_add(u, family):
        raise Forbidden("Only editors make family cookbooks" if family else "A viewer only looks; a member keeps cookbooks of their own")
    f = _book_fields(data, False)
    bid = db.ex("INSERT INTO rcp_books (owner_id, name, description) VALUES (%s, %s, %s)", (None if family else u["id"], f["name"], f["description"]))
    return readable_book(u, bid)


def update_book(u: dict, b: dict, data: dict) -> dict:
    if not can_change_book(u, b):
        raise Forbidden("You can see this cookbook but not change it")
    f = _book_fields(data, True)
    if f:
        db.ex(f"UPDATE rcp_books SET {', '.join(k + ' = %s' for k in f)} WHERE id = %s", [*f.values(), b["id"]])
    return readable_book(u, b["id"])


def delete_book(u: dict, b: dict) -> None:
    """The cookbook goes; its recipes stay."""
    if not can_change_book(u, b):
        raise Forbidden("You can see this cookbook but not delete it")
    db.ex("DELETE FROM rcp_books WHERE id = %s", (b["id"],))


def book_add(u: dict, b: dict, r: dict) -> None:
    if not can_change_book(u, b):
        raise Forbidden("You can see this cookbook but not change it")
    if b["owner_id"] is None and r["owner_id"] is not None:
        raise Invalid("A family cookbook holds family recipes; this one is private")
    db.ex("INSERT IGNORE INTO rcp_book_recipes (book_id, recipe_id) VALUES (%s, %s)", (b["id"], r["id"]))


def book_remove(u: dict, b: dict, r: dict) -> None:
    if not can_change_book(u, b):
        raise Forbidden("You can see this cookbook but not change it")
    db.ex("DELETE FROM rcp_book_recipes WHERE book_id = %s AND recipe_id = %s", (b["id"], r["id"]))


def books_of(u: dict, rid: int) -> list[int]:
    """The cookbooks this account sees that hold the recipe."""
    return [x["id"] for x in db.q("SELECT b.id FROM rcp_books b JOIN rcp_book_recipes br ON br.book_id = b.id WHERE br.recipe_id = %s "
                                  "AND (b.owner_id IS NULL OR b.owner_id = %s) ORDER BY b.name", (int(rid), u["id"]))]


def book_public(b: dict, u: dict) -> dict:
    return {"id": b["id"], "name": b["name"], "description": b.get("description"), "family": b["owner_id"] is None,
            "writable": can_change_book(u, b), "count": int(b["n"]) if b.get("n") is not None else None}


# ---- as JSON

def photo_url(rid: int, pid: int) -> str:
    return f"api/recipes/{rid}/photos/{pid}"  # relative to the page, which may be in a folder (/recipes/)


def public(r: dict, u: dict, full: bool = True) -> dict:
    if "favourite" not in r:  # a row read without the asker's marks
        r = {**get(r["id"], u), **{k: v for k, v in r.items() if k in ("updated_at",)}}
    avg = r.get("rating_avg")
    out = {"id": r["id"], "title": r["title"], "description": r.get("description"), "family": r["owner_id"] is None,
           "servings": r.get("servings"), "prepMinutes": r.get("prep_minutes"), "cookMinutes": r.get("cook_minutes"),
           "totalMinutes": r.get("total_minutes") or ((r.get("prep_minutes") or 0) + (r.get("cook_minutes") or 0)) or None,
           "tags": r.get("tags") or [], "sourceName": r.get("source_name"),
           "photo": photo_url(r["id"], r["photo"]) if r.get("photo") else None,
           "favourite": bool(r.get("favourite")), "rating": r.get("rating"),
           "ratingAverage": round(float(avg), 1) if avg is not None else None, "ratingCount": int(r.get("rating_n") or 0),
           "writable": can_write(u, r),
           "updated": r["updated_at"].isoformat() if r.get("updated_at") else None}
    if full:
        out.update(ingredients=r["ingredients"], steps=r["steps"], notes=r.get("notes"), sourceUrl=r.get("source_url"),
                   created=r["created_at"].isoformat() if r.get("created_at") else None,
                   photos=[{"id": p["id"], "url": photo_url(r["id"], p["id"]), "step": p["step"], "width": p["width"], "height": p["height"]}
                           for p in photos(r["id"])],
                   books=books_of(u, r["id"]))
    return out
