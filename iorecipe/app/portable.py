"""Recipes as a file: out (one recipe, a cookbook, or everything the account sees) and in again, here or on another
ioRecipe, and in from Mealie.

What goes out is a .zip: recipes.json (the recipes as GET /api/recipes/{id} gives them, with the account's own
favourite and rating, and the cookbooks they are in) and photos/ (the pictures, as the JPEGs kept).

What comes in is one of:
- such a .zip, or its recipes.json alone;
- a recipe as JSON the way Mealie exports one (or any schema.org Recipe), one or a list;
- a .zip of those, each with its pictures beside it (Mealie's "export recipes", and its migration layout
  recipes/<name>/<name>.json + images/);
- a Mealie backup (.zip with database.json and data/recipes/<id>/images/).
Nothing is unpacked to disk; what is not a recipe is passed over and said so.
"""
import datetime as dt
import io
import json
import re
import zipfile
from fractions import Fraction

from iosuite_shared.errors import Invalid

from app import db, model, scrape, textimport

FORMAT, VERSION = "iorecipe", 1
MAX_MEMBERS = 50_000
MAX_MEMBER = 60 * 1024 * 1024          # one file inside a .zip, unpacked
MAX_RECIPES = 5000
IMAGE_TYPES = (".jpg", ".jpeg", ".png", ".webp", ".gif")
FIELDS = ("title", "description", "servings", "prepMinutes", "cookMinutes", "totalMinutes", "ingredients", "steps", "notes", "tags",
          "sourceUrl", "sourceName")


# ---- out

def export(u: dict, rows: list[dict]) -> bytes:
    """The .zip of these recipes (rows of model.find(full=True) or model.get), as the account sees them."""
    ids = [r["id"] for r in rows]
    place = {rid: n for n, rid in enumerate(ids)}
    recipes = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:  # JPEGs do not get smaller
        for n, r in enumerate(rows):
            j = model.public(r, u)
            out = {k: j.get(k) for k in FIELDS}
            out.update(family=j["family"], favourite=j["favourite"], rating=j["rating"], created=j.get("created"), photos=[])
            for k, p in enumerate(j["photos"]):
                name = f"photos/{n + 1}-{k + 1}.jpg"
                z.writestr(name, model.photo(r["id"], p["id"], False) or b"")
                out["photos"].append({"file": name, "step": p["step"]})
            recipes.append(out)
        books = []
        for b in model.books(u):
            inside = [place[x["recipe_id"]] for x in db.q("SELECT recipe_id FROM rcp_book_recipes WHERE book_id = %s", (b["id"],)) if x["recipe_id"] in place]
            if inside:
                books.append({"name": b["name"], "description": b.get("description"), "family": b["owner_id"] is None, "recipes": sorted(inside)})
        doc = {"format": FORMAT, "version": VERSION, "exported": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
               "recipes": recipes, "cookbooks": books}
        z.writestr("recipes.json", json.dumps(doc, ensure_ascii=False, indent=1), zipfile.ZIP_DEFLATED)
    return buf.getvalue()


# ---- in: what a file holds

class Batch:
    """What a file holds: the recipes (the fields POST /api/recipes takes, their pictures as bytes, the favourite and
    the rating that came with them), the cookbooks (names, and which recipes by their place), and what was passed over."""

    def __init__(self):
        self.recipes: list[dict] = []   # {data, photos: [(bytes, step or None)], favourite, rating}
        self.books: list[dict] = []     # {name, description, recipes: [places]}
        self.skipped: list[str] = []

    def add(self, data: dict, photos=(), favourite=False, rating=None) -> None:
        if len(self.recipes) >= MAX_RECIPES:
            raise Invalid(f"At most {MAX_RECIPES} recipes in one file")
        self.recipes.append({"data": data, "photos": list(photos), "favourite": bool(favourite), "rating": rating})


def _member(z: zipfile.ZipFile, name: str) -> bytes | None:
    try:
        info = z.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_MEMBER:
        return None
    with z.open(info) as f:
        raw = f.read(MAX_MEMBER + 1)
    return raw if len(raw) <= MAX_MEMBER else None


def _quantity(q) -> str:
    """0.5 as 1/2, 1.5 as 1 1/2, 2.0 as 2, 0.33 as 1/3; anything else with two decimals."""
    try:
        v = float(q)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    whole, part = int(v), v - int(v)
    if part < 0.01:
        return str(whole)
    f = Fraction(part).limit_denominator(8)
    if abs(float(f) - part) < 0.02 and f.numerator:
        return f"{whole} {f.numerator}/{f.denominator}" if whole else f"{f.numerator}/{f.denominator}"
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _name(v) -> str:
    return (v.get("name") or "") if isinstance(v, dict) else (v or "") if isinstance(v, str) else ""


def _mealie_ingredients(items) -> list[str]:
    """Mealie's recipeIngredient: a line each, or {title, quantity, unit, food, note, display, originalText}."""
    out: list[str] = []
    for i in items or []:
        if isinstance(i, str):
            out.append(i)
            continue
        if not isinstance(i, dict):
            continue
        if i.get("title"):
            out.append(str(i["title"]).strip().rstrip(":") + ":")
        text = scrape._one_line(i.get("display"))
        if not text:
            unit = i.get("unit")
            unit = (unit.get("abbreviation") if isinstance(unit, dict) and unit.get("useAbbreviation") and unit.get("abbreviation") else _name(unit))
            parts = [] if i.get("disableAmount") else [_quantity(i.get("quantity")), unit, _name(i.get("food"))]
            text = " ".join(p for p in parts if p)
            note = scrape._one_line(i.get("note"))
            text = f"{text}, {note}" if text and note else text or note or scrape._one_line(i.get("originalText"))
        if text:
            out.append(text)
    return out


def _minutes(v) -> int | None:
    return scrape.minutes(v) or (textimport.duration(v) if isinstance(v, str) else None)


def looks_like_recipe(d) -> bool:
    return isinstance(d, dict) and bool(d.get("name") or d.get("title")) and any(k in d for k in ("recipeIngredient", "recipeInstructions", "ingredients", "steps"))


def from_recipe_json(d: dict) -> tuple[dict, int | None]:
    """(the fields, the rating) of a recipe as Mealie exports it, or of any schema.org Recipe."""
    if "steps" in d and "recipeInstructions" not in d:  # one of ioRecipe's own, on its own
        return {k: d.get(k) for k in FIELDS}, d.get("rating")
    steps = []
    ins = d.get("recipeInstructions")
    for s in ins if isinstance(ins, list) else [ins]:
        if isinstance(s, dict) and s.get("title") and "HowToSection" not in scrape._types(s):
            steps.append(str(s["title"]).strip().rstrip(":") + ":")
        steps += scrape._steps([s] if isinstance(s, dict) else s)
    out = scrape.from_jsonld({**d, "recipeInstructions": None}, "")
    out.pop("image", None)
    out["steps"] = steps
    out["ingredients"] = _mealie_ingredients(d.get("recipeIngredient") or d.get("ingredients"))
    out["tags"] = scrape._keywords(d.get("recipeCategory"), d.get("recipeCuisine"), d.get("tags"), d.get("keywords"))
    out["prepMinutes"], out["totalMinutes"] = _minutes(d.get("prepTime")), _minutes(d.get("totalTime"))
    out["cookMinutes"] = _minutes(d.get("performTime")) or _minutes(d.get("cookTime"))
    if not out.get("servings") and d.get("recipeServings"):
        out["servings"] = _quantity(d["recipeServings"]) or None
    notes = d.get("notes")
    if isinstance(notes, list):
        texts = []
        for n in notes:
            if isinstance(n, dict):
                texts.append("\n".join(x for x in (scrape._one_line(n.get("title")), scrape._plain(n.get("text"))) if x))
            elif n:
                texts.append(scrape._plain(n))
        out["notes"] = "\n\n".join(t for t in texts if t) or None
    elif isinstance(notes, str):
        out["notes"] = notes
    out["sourceUrl"] = d.get("orgURL") or d.get("org_url") or (d.get("url") if isinstance(d.get("url"), str) else None)
    if out["sourceUrl"] and not out.get("sourceName"):
        out["sourceName"] = scrape._site(out["sourceUrl"]) or None
    rating = d.get("rating")
    try:
        rating = min(5, max(1, round(float(rating)))) if rating not in (None, "", 0) else None
    except (TypeError, ValueError):
        rating = None
    return out, rating


def _own(doc: dict, picture, batch: Batch) -> None:
    for r in doc.get("recipes") or []:
        if not isinstance(r, dict):
            continue
        photos = []
        for p in r.get("photos") or []:
            raw = picture(p.get("file")) if isinstance(p, dict) and p.get("file") else None
            if raw:
                photos.append((raw, p.get("step")))
        batch.add({k: r.get(k) for k in FIELDS}, photos, r.get("favourite"), r.get("rating"))
    for b in doc.get("cookbooks") or []:
        if isinstance(b, dict) and b.get("name"):
            batch.books.append({"name": b["name"], "description": b.get("description"),
                                "recipes": [i for i in b.get("recipes") or [] if isinstance(i, int)]})


def _images_beside(names: list[str], json_name: str) -> list[str]:
    """The picture of the recipe whose JSON this is: in its folder when the folder is the recipe's alone (Mealie keeps
    three sizes of one there: the original), else the picture with the JSON's own name."""
    folder = json_name.rsplit("/", 1)[0] + "/" if "/" in json_name else ""
    pics = [n for n in names if n.lower().endswith(IMAGE_TYPES)]
    alone = folder and sum(1 for n in names if n.startswith(folder) and n.lower().endswith(".json")) == 1
    if not alone:
        stem = json_name.rsplit(".", 1)[0]
        return [n for n in pics if n.rsplit(".", 1)[0] == stem][:1]
    inside = [n for n in pics if n.startswith(folder)]
    base = lambda n: n.rsplit("/", 1)[-1].lower()  # noqa: E731
    return ([n for n in inside if base(n).startswith("original.")] or [n for n in inside if not base(n).startswith(("min-", "tiny-"))] or inside)[:1]


def _mealie_backup(doc: dict, z: zipfile.ZipFile, names: list[str], batch: Batch) -> None:
    """Mealie's backup: database.json holds its tables as lists of rows."""
    rows = lambda t: [x for x in doc.get(t) or [] if isinstance(x, dict)]  # noqa: E731
    by = lambda t: {x.get("id"): x for x in rows(t)}  # noqa: E731
    units, foods, tags, cats = by("ingredient_units"), by("ingredient_foods"), by("tags"), by("categories")

    def of(table, rid):
        return sorted((x for x in rows(table) if x.get("recipe_id") == rid), key=lambda x: x.get("position") or 0)
    for r in rows("recipes"):
        rid = r.get("id")
        d = {"name": r.get("name"), "description": r.get("description"), "recipeYield": r.get("recipe_yield"),
             "recipeServings": r.get("recipe_servings"), "prepTime": r.get("prep_time"), "totalTime": r.get("total_time"),
             "performTime": r.get("perform_time"), "cookTime": r.get("cook_time"), "orgURL": r.get("org_url"), "rating": r.get("rating"),
             "recipeIngredient": [{"title": i.get("title"), "note": i.get("note"), "quantity": i.get("quantity"), "originalText": i.get("original_text"),
                                   "disableAmount": i.get("disable_amount"), "unit": units.get(i.get("unit_id")), "food": foods.get(i.get("food_id"))}
                                  for i in of("recipes_ingredients", rid)],
             "recipeInstructions": [{"title": s.get("title"), "text": s.get("text")} for s in of("recipe_instructions", rid)],
             "notes": [{"title": n.get("title"), "text": n.get("text")} for n in rows("notes") if n.get("recipe_id") == rid],
             "tags": [_name(tags.get(x.get("tag_id"))) for x in rows("recipes_to_tags") if x.get("recipe_id") == rid],
             "recipeCategory": [_name(cats.get(x.get("category_id"))) for x in rows("recipes_to_categories") if x.get("recipe_id") == rid]}
        for u in d["recipeIngredient"]:
            if isinstance(u["unit"], dict):
                u["unit"] = {**u["unit"], "useAbbreviation": u["unit"].get("use_abbreviation")}
        if not d["name"]:
            continue
        data, rating = from_recipe_json(d)
        keys = {str(rid), str(rid).replace("-", "")}
        pics = [n for n in names if n.lower().endswith(IMAGE_TYPES) and re.search(r"(^|/)original\.\w+$", n.lower())
                and any(f"/recipes/{k}/" in "/" + n for k in keys)]
        photos = [(raw, None) for raw in (_member(z, n) for n in pics[:1]) if raw]
        batch.add(data, photos, False, rating)


def _json(raw: bytes):
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return None


def _zip(raw: bytes, batch: Batch) -> None:
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as e:
        raise Invalid("That .zip file cannot be opened") from e
    with z:
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        if len(names) > MAX_MEMBERS:
            raise Invalid("That .zip file holds too many files")
        if "recipes.json" in names:
            doc = _json(_member(z, "recipes.json") or b"")
            if isinstance(doc, dict) and doc.get("format") == FORMAT:
                _own(doc, lambda f: _member(z, f) if isinstance(f, str) and f.startswith("photos/") else None, batch)
                return
        backup = next((n for n in names if n == "database.json" or n.endswith("/database.json")), None)
        if backup:
            doc = _json(_member(z, backup) or b"")
            if isinstance(doc, dict) and isinstance(doc.get("recipes"), list):
                _mealie_backup(doc, z, names, batch)
                return
        for n in names:
            if not n.lower().endswith(".json"):
                continue
            doc = _json(_member(z, n) or b"")
            for d in doc if isinstance(doc, list) else [doc]:
                if looks_like_recipe(d):
                    data, rating = from_recipe_json(d)
                    photos = [(p, None) for p in (_member(z, i) for i in _images_beside(names, n)) if p]
                    batch.add(data, photos, False, rating)
                elif n.count("/") == 0 and d is not None:
                    batch.skipped.append(f"{n}: not a recipe")


def read(raw: bytes) -> Batch:
    """What the file holds. Invalid when it is none of the kinds this module knows, or holds no recipe."""
    batch = Batch()
    if raw[:2] == b"PK":
        _zip(raw, batch)
    else:
        doc = _json(raw)
        if isinstance(doc, dict) and doc.get("format") == FORMAT:
            _own(doc, lambda f: None, batch)
        else:
            for d in doc if isinstance(doc, list) else [doc]:
                if looks_like_recipe(d):
                    batch.add(*((lambda x: (x[0], (), False, x[1]))(from_recipe_json(d))))
    if not batch.recipes:
        raise Invalid("No recipe was found in that file. It takes an ioRecipe export, a Mealie export or backup, or a recipe as JSON.")
    return batch


# ---- in: keeping it

def keep(u: dict, batch: Batch, family: bool) -> dict:
    """Every recipe of the batch as a new recipe (the family's, or the account's own), with its pictures, the
    account's favourite and rating, and its cookbooks (made when no cookbook of that name is there).
    {imported: [{id, title}], skipped: [why]}."""
    if not model.may_add(u, family):
        raise model.Forbidden("Only editors add family recipes" if family else "A viewer only looks; a member keeps recipes of their own")
    made: dict[int, dict] = {}
    skipped = list(batch.skipped)
    for n, e in enumerate(batch.recipes):
        title = str((e["data"] or {}).get("title") or "A recipe")[:80]
        try:
            r = model.create(u, e["data"], family)
        except Invalid as x:
            skipped.append(f"{title}: {x}")
            continue
        made[n] = r
        for raw, step in e["photos"]:
            try:
                model.add_photo(u, r, raw, step if isinstance(step, int) else None)
            except Invalid:
                skipped.append(f"{title}: one of its photos could not be read")
        if e["favourite"] or e["rating"]:
            try:
                model.mark(u, r, {"favourite": e["favourite"], "rating": e["rating"]})
            except Invalid:
                pass
    if made:
        have = {b["name"].lower(): b for b in model.books(u) if (b["owner_id"] is None) == family}
        for b in batch.books:
            inside = [made[i] for i in b["recipes"] if i in made]
            if not inside:
                continue
            book = have.get(str(b["name"]).lower())
            if not book:
                try:
                    book = model.create_book(u, b, family)
                except Invalid:
                    continue
                have[book["name"].lower()] = book
            for r in inside:
                model.book_add(u, book, r)
    return {"imported": [{"id": r["id"], "title": r["title"]} for r in made.values()], "skipped": skipped[:50]}
