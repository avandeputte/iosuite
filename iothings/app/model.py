"""Everything you own: what one is, where it is, its labels, who may change it, and the search.

Everything is the household's: whoever has a role here sees every thing, every place and every label. A viewer only
looks; a member adds things, changes the ones they added and keeps any thing's upkeep and maintenance log; an editor
(and an admin) changes and deletes everything, and keeps the places and labels in order.

A thing (thg_items) has a place (thg_locations, a tree), labels (thg_labels), purchase, warranty and sale details, its
own fields, files (app/files.py: photos, the manual, the receipt), upkeep and a maintenance log (app/upkeep.py).
"""
import datetime as dt
import json
import re
from decimal import Decimal, InvalidOperation

from iosuite_shared import related, users as shared_users
from iosuite_shared.errors import Invalid

from app import db


class NotFound(Exception):
    """No such thing (or place, label, file...)."""


class Forbidden(Exception):
    """The account sees it but may not do this."""


MAX_FIELDS = 50        # own fields of one thing
MAX_LABELS = 30        # labels on one thing
SOON_DAYS = 30         # a warranty that ends within this many days "ends soon"
CURRENCIES = ("EUR", "USD", "GBP", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK", "PLN", "CZK", "JPY", "INR", "ZAR", "BRL", "MXN")


# ---- who may

def may_add(u: dict | None) -> bool:
    """Add things, and keep upkeep and the maintenance log of any thing: members and more."""
    return shared_users.is_member(u)


def may_edit_all(u: dict | None) -> bool:
    """Change and delete every thing, and the places and labels: editors and admins."""
    return shared_users.can_write(u)


def can_write(u: dict | None, it: dict | None) -> bool:
    """A thing: editors and admins, and the member who added it."""
    if not (u and it):
        return False
    return may_edit_all(u) or (shared_users.is_member(u) and it.get("created_by") == u.get("id"))


def need_add(u: dict) -> None:
    if not may_add(u):
        raise Forbidden("A viewer only looks: a member or more adds things")


def need_edit_all(u: dict, what: str = "the places and labels") -> None:
    if not may_edit_all(u):
        raise Forbidden(f"Only editors change {what}")


def need_write(u: dict, it: dict) -> None:
    if not can_write(u, it):
        raise Forbidden("You can see this thing but not change it: editors and the one who added it can")


# ---- the fields, as they come in

def text(v, limit: int, name: str, multiline: bool = False) -> str | None:
    if v is None:
        return None
    s = str(v).replace("\r\n", "\n").strip() if multiline else re.sub(r"\s+", " ", str(v)).strip()
    if len(s) > limit:
        raise Invalid(f"{name} is too long (at most {limit} characters)")
    return s or None


def day(v, name: str) -> dt.date | None:
    """A day: 2026-11-15 (or 2026-11-15T..., or a date). Empty: none."""
    if v in (None, ""):
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = str(v).strip()[:10]
    try:
        d = dt.date.fromisoformat(s)
    except ValueError:
        raise Invalid(f"{name}: a day as YYYY-MM-DD is expected") from None
    if not 1900 <= d.year <= 2200:
        raise Invalid(f"{name}: a day between 1900 and 2200")
    return d


def money(v, name: str) -> Decimal | None:
    """An amount: 12.5, "12,50", "€ 1.299,00", "$1,299.00". Empty: none."""
    if v in (None, ""):
        return None
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        n = Decimal(str(v))
    else:
        s = re.sub(r"[^\d,.\-]", "", str(v))
        if "," in s and "." in s:  # the last of the two is the decimal mark
            s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".") if len(s) - s.rfind(",") - 1 in (1, 2) else s.replace(",", "")
        try:
            n = Decimal(s)
        except InvalidOperation:
            raise Invalid(f"{name}: an amount is expected") from None
    if not Decimal("-1e12") < n < Decimal("1e12"):
        raise Invalid(f"{name}: that amount is out of range")
    return n.quantize(Decimal("0.01"))


def whole(v, name: str, low: int = 0, high: int = 1_000_000) -> int | None:
    if v in (None, ""):
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        raise Invalid(f"{name}: a whole number is expected") from None
    if not low <= n <= high:
        raise Invalid(f"{name}: between {low} and {high}")
    return n


def flag(v) -> int:
    if isinstance(v, str):
        return int(v.strip().lower() in ("1", "true", "yes", "y", "on", "x"))
    return int(bool(v))


def web(v) -> str | None:
    s = text(v, 2048, "The link")
    return s if s and re.match(r"https?://", s, re.I) else None


def own_fields(v) -> list[dict]:
    """The thing's own details: [{name, value}], from such a list or a {name: value} object."""
    if v in (None, ""):
        return []
    if isinstance(v, dict):
        v = [{"name": k, "value": x} for k, x in v.items()]
    if not isinstance(v, list):
        raise Invalid("fields: a list of {name, value} is expected")
    out = []
    for f in v:
        if not isinstance(f, dict):
            continue
        n, x = text(f.get("name"), 100, "A field's name"), text(f.get("value"), 2000, "A field's value", True)
        if n and x:
            out.append({"name": n, "value": x})
    if len(out) > MAX_FIELDS:
        raise Invalid(f"At most {MAX_FIELDS} fields on one thing")
    return out


FIELDS = {
    "name": lambda v: text(v, 255, "The name"),
    "description": lambda v: text(v, 4000, "The description", True),
    "quantity": lambda v: whole(v, "Quantity", 0, 1_000_000),
    "manufacturer": lambda v: text(v, 255, "The manufacturer"),
    "modelNumber": lambda v: text(v, 255, "The model number"),
    "serialNumber": lambda v: text(v, 255, "The serial number"),
    "assetId": lambda v: text(v, 64, "The asset id"),
    "url": web,
    "purchaseDate": lambda v: day(v, "Purchase date"),
    "purchasePrice": lambda v: money(v, "Purchase price"),
    "purchaseFrom": lambda v: text(v, 255, "Bought from"),
    "warrantyExpires": lambda v: day(v, "Warranty end"),
    "lifetimeWarranty": flag,
    "warrantyDetails": lambda v: text(v, 4000, "Warranty details", True),
    "insured": flag,
    "archived": flag,
    "soldDate": lambda v: day(v, "Sale date"),
    "soldPrice": lambda v: money(v, "Sale price"),
    "soldTo": lambda v: text(v, 255, "Sold to"),
    "soldNotes": lambda v: text(v, 4000, "Sale notes", True),
    "notes": lambda v: text(v, 50000, "The notes", True),
    "fields": own_fields,
}
COLUMNS = {"name": "name", "description": "description", "quantity": "quantity", "manufacturer": "manufacturer",
           "modelNumber": "model_number", "serialNumber": "serial_number", "assetId": "asset_id", "url": "url",
           "purchaseDate": "purchase_date", "purchasePrice": "purchase_price", "purchaseFrom": "purchase_from",
           "warrantyExpires": "warranty_expires", "lifetimeWarranty": "lifetime_warranty", "warrantyDetails": "warranty_details",
           "insured": "insured", "archived": "archived", "soldDate": "sold_date", "soldPrice": "sold_price", "soldTo": "sold_to",
           "soldNotes": "sold_notes", "notes": "notes", "fields": "fields"}


def clean(data: dict, partial: bool = False) -> dict:
    """The fields of `data` that are a thing's, checked, by column. Not partial: every field, the missing ones empty."""
    out = {}
    for k, fn in FIELDS.items():
        if k in data or not partial:
            out[COLUMNS[k]] = fn(data.get(k))
    if "name" in out and not out["name"]:
        raise Invalid("A name, please")
    if "quantity" in out and out["quantity"] is None:
        out["quantity"] = 1
    return out


# ---- places

def locations() -> list[dict]:
    """Every place, each with its path ("House / Kitchen") and how many things (not archived) are in it."""
    rows = db.q("SELECT l.id, l.parent_id, l.name, l.description, "
                "(SELECT COUNT(*) FROM thg_items i WHERE i.location_id = l.id AND i.archived = 0) AS n "
                "FROM thg_locations l ORDER BY l.name, l.id")
    by = {r["id"]: r for r in rows}

    def path(r, seen=()):
        p = by.get(r["parent_id"])
        if not p or p["id"] in seen:
            return [r["name"]]
        return path(p, (*seen, r["id"])) + [r["name"]]
    out = []
    for r in rows:
        names = path(r)
        out.append({"id": r["id"], "parentId": r["parent_id"], "name": r["name"], "description": r["description"],
                    "path": " / ".join(names), "depth": len(names) - 1, "count": int(r["n"])})
    return sorted(out, key=lambda x: x["path"].lower())


def location(lid) -> dict:
    found = next((x for x in locations() if str(x["id"]) == str(lid)), None)
    if not found:
        raise NotFound("No such place")
    return found


def _below(lid: int) -> set:
    """The place and every place inside it, at any depth."""
    rows = db.q("SELECT id, parent_id FROM thg_locations")
    out, todo = {int(lid)}, [int(lid)]
    while todo:
        p = todo.pop()
        for r in rows:
            if r["parent_id"] == p and r["id"] not in out:
                out.add(r["id"])
                todo.append(r["id"])
    return out


def save_location(u: dict, data: dict, lid: int | None = None) -> dict:
    """A new place (members and more) or a change to one (editors). {name, description?, parentId?}"""
    if lid is None:
        need_add(u)
    else:
        need_edit_all(u)
        location(lid)
    sets = {}
    if "name" in data or lid is None:
        sets["name"] = text(data.get("name"), 191, "The name")
        if not sets["name"]:
            raise Invalid("A name, please")
    if "description" in data:
        sets["description"] = text(data.get("description"), 2000, "The description", True)
    if "parentId" in data:
        p = data.get("parentId")
        p = int(p) if str(p or "").isdigit() and int(p) else None
        if p is not None:
            location(p)
            if lid is not None and p in _below(lid):
                raise Invalid("A place cannot be inside itself")
        sets["parent_id"] = p
    if lid is None:
        lid = db.ex(f"INSERT INTO thg_locations ({', '.join(sets)}) VALUES ({db.marks(len(sets))})", list(sets.values()))
    elif sets:
        db.ex(f"UPDATE thg_locations SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), lid])
    _rewords_at(lid)
    return location(lid)


def delete_location(u: dict, lid: int) -> dict:
    """The place goes; what was in it (things and places) moves up to the place it was in."""
    need_edit_all(u)
    loc = location(lid)
    with db.tx():
        db.ex("UPDATE thg_locations SET parent_id = %s WHERE parent_id = %s", (loc["parentId"], lid))
        db.ex("UPDATE thg_items SET location_id = %s WHERE location_id = %s", (loc["parentId"], lid))
        db.ex("DELETE FROM thg_locations WHERE id = %s", (lid,))
    if loc["parentId"]:
        _rewords_at(loc["parentId"])
    return loc


def location_by_path(names: list[str], cache: dict | None = None) -> int | None:
    """The place at this path (["House", "Kitchen"]), made where it is missing; None for an empty path."""
    cache = {} if cache is None else cache
    parent = None
    for n in [x for x in (text(n, 191, "A place's name") for n in names) if x]:
        key = (parent, n.lower())
        if key not in cache:
            r = db.one("SELECT id FROM thg_locations WHERE name = %s AND " + ("parent_id IS NULL" if parent is None else "parent_id = %s"),
                       (n,) if parent is None else (n, parent))
            cache[key] = r["id"] if r else db.ex("INSERT INTO thg_locations (name, parent_id) VALUES (%s, %s)", (n, parent))
        parent = cache[key]
    return parent


# ---- labels

COLOR = re.compile(r"#[0-9a-fA-F]{6}")


def labels() -> list[dict]:
    rows = db.q("SELECT l.id, l.name, l.color, (SELECT COUNT(*) FROM thg_item_labels x JOIN thg_items i ON i.id = x.item_id "
                "WHERE x.label_id = l.id AND i.archived = 0) AS n FROM thg_labels l ORDER BY l.name")
    return [{"id": r["id"], "name": r["name"], "color": r["color"], "count": int(r["n"])} for r in rows]


def label(lid) -> dict:
    found = next((x for x in labels() if str(x["id"]) == str(lid)), None)
    if not found:
        raise NotFound("No such label")
    return found


def save_label(u: dict, data: dict, lid: int | None = None) -> dict:
    if lid is None:
        need_add(u)
    else:
        need_edit_all(u)
        label(lid)
    sets = {}
    if "name" in data or lid is None:
        sets["name"] = text(data.get("name"), 100, "The label")
        if not sets["name"]:
            raise Invalid("A name, please")
        same = db.one("SELECT id FROM thg_labels WHERE name = %s", (sets["name"],))
        if same and same["id"] != lid:
            if lid is None:
                return label(same["id"])
            raise Invalid("There is a label with that name already")
    if "color" in data:
        c = str(data.get("color") or "").strip()
        sets["color"] = c if COLOR.fullmatch(c) else None
    if lid is None:
        lid = db.ex(f"INSERT INTO thg_labels ({', '.join(sets)}) VALUES ({db.marks(len(sets))})", list(sets.values()))
    elif sets:
        db.ex(f"UPDATE thg_labels SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), lid])
        _rewords_labelled(lid)
    return label(lid)


def delete_label(u: dict, lid: int) -> dict:
    need_edit_all(u)
    lab = label(lid)
    ids = [r["item_id"] for r in db.q("SELECT item_id FROM thg_item_labels WHERE label_id = %s", (lid,))]
    db.ex("DELETE FROM thg_labels WHERE id = %s", (lid,))
    for i in ids:
        _rewords(i)
    return lab


def label_ids(names_or_ids, make: bool = True) -> list[int]:
    """Labels by id or name (made when missing and make)."""
    if names_or_ids in (None, ""):
        return []
    if isinstance(names_or_ids, str):
        names_or_ids = [x for x in re.split(r"[;,]", names_or_ids)]
    if not isinstance(names_or_ids, list):
        raise Invalid("labels: a list of label ids or names is expected")
    out = []
    for x in names_or_ids:
        if isinstance(x, dict):
            x = x.get("id") or x.get("name")
        if isinstance(x, int) or (isinstance(x, str) and x.strip().isdigit()):
            r = db.one("SELECT id FROM thg_labels WHERE id = %s", (int(x),))
            if not r:
                raise Invalid(f"No label with id {x}")
            out.append(r["id"])
            continue
        n = text(x, 100, "A label")
        if not n:
            continue
        r = db.one("SELECT id FROM thg_labels WHERE name = %s", (n,))
        if r:
            out.append(r["id"])
        elif make:
            out.append(db.ex("INSERT INTO thg_labels (name) VALUES (%s)", (n,)))
        else:
            raise Invalid(f"No label named {n}")
    out = list(dict.fromkeys(out))
    if len(out) > MAX_LABELS:
        raise Invalid(f"At most {MAX_LABELS} labels on one thing")
    return out


# ---- reading things

def _iso(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v


def _num(v):
    return float(v) if isinstance(v, Decimal) else v


def warranty(it: dict, today: dt.date | None = None) -> dict | None:
    """{state, daysLeft}: lifetime, active, soon (within SOON_DAYS), expired; None without a warranty."""
    if it.get("lifetime_warranty"):
        return {"state": "lifetime", "daysLeft": None}
    end = it.get("warranty_expires")
    if not end:
        return None
    left = (end - (today or dt.date.today())).days
    return {"state": "expired" if left < 0 else "soon" if left <= SOON_DAYS else "active", "daysLeft": left}


def _words(it: dict, loc_path: str | None, label_names: list[str]) -> str:
    parts = [it.get("name"), it.get("description"), it.get("manufacturer"), it.get("model_number"), it.get("serial_number"),
             it.get("asset_id"), it.get("purchase_from"), it.get("notes"), it.get("warranty_details"), loc_path, *label_names]
    fields = it.get("fields")
    if isinstance(fields, str):
        fields = json.loads(fields or "[]")
    for f in fields or []:
        parts += [f.get("name"), f.get("value")]
    return "\n".join(str(p) for p in parts if p).lower()


def _rewords(item_id: int) -> None:
    it = db.one("SELECT * FROM thg_items WHERE id = %s", (item_id,))
    if not it:
        return
    loc = next((x["path"] for x in locations() if x["id"] == it["location_id"]), None) if it["location_id"] else None
    names = [r["name"] for r in db.q("SELECT l.name FROM thg_labels l JOIN thg_item_labels x ON x.label_id = l.id WHERE x.item_id = %s", (item_id,))]
    db.ex("UPDATE thg_items SET words = %s, updated_at = updated_at WHERE id = %s", (_words(it, loc, names), item_id))


def _rewords_at(lid: int) -> None:
    for r in db.q(f"SELECT id FROM thg_items WHERE location_id IN ({db.marks(len(_below(lid)))})", list(_below(lid))):
        _rewords(r["id"])


def _rewords_labelled(lid: int) -> None:
    for r in db.q("SELECT item_id FROM thg_item_labels WHERE label_id = %s", (lid,)):
        _rewords(r["item_id"])


def get(item_id) -> dict | None:
    if not str(item_id).strip().isdigit():
        return None
    it = db.one("SELECT * FROM thg_items WHERE id = %s", (int(item_id),))
    if it:
        it["fields"] = json.loads(it["fields"] or "[]")
    return it


def readable(u: dict, item_id) -> dict:
    """The thing (everyone with a role here sees every thing)."""
    it = get(item_id)
    if not it or not u:
        raise NotFound("No such thing")
    return it


def _labels_of(ids: list[int]) -> dict:
    if not ids:
        return {}
    out: dict = {}
    for r in db.q(f"SELECT x.item_id, l.id, l.name, l.color FROM thg_item_labels x JOIN thg_labels l ON l.id = x.label_id "
                  f"WHERE x.item_id IN ({db.marks(len(ids))}) ORDER BY l.name", ids):
        out.setdefault(r["item_id"], []).append({"id": r["id"], "name": r["name"], "color": r["color"]})
    return out


def public(it: dict, u: dict, full: bool = True, places: dict | None = None, tags: dict | None = None) -> dict:
    """The thing as the API gives it; full: with its files, upkeep and maintenance log."""
    places = places if places is not None else {x["id"]: x for x in locations()}
    loc = places.get(it["location_id"])
    tags = tags if tags is not None else _labels_of([it["id"]])
    out = {"id": it["id"], "name": it["name"], "description": it["description"], "quantity": it["quantity"],
           "location": {"id": loc["id"], "name": loc["name"], "path": loc["path"]} if loc else None,
           "labels": tags.get(it["id"], []), "manufacturer": it["manufacturer"], "modelNumber": it["model_number"],
           "serialNumber": it["serial_number"], "assetId": it["asset_id"], "purchaseDate": _iso(it["purchase_date"]),
           "purchasePrice": _num(it["purchase_price"]), "warrantyExpires": _iso(it["warranty_expires"]),
           "lifetimeWarranty": bool(it["lifetime_warranty"]), "warranty": warranty(it), "insured": bool(it["insured"]),
           "archived": bool(it["archived"]),
           "photo": f"api/items/{it['id']}/files/{it['photo']}" if it["photo"] else None,
           "updated": _iso(it["updated_at"]), "writable": can_write(u, it)}
    if not full:
        return out
    from app import files, upkeep
    who = it.get("created_by")
    by = shared_users.get(who) if who else None
    out.update({"url": it["url"], "purchaseFrom": it["purchase_from"], "warrantyDetails": it["warranty_details"],
                "soldDate": _iso(it["sold_date"]), "soldPrice": _num(it["sold_price"]), "soldTo": it["sold_to"],
                "soldNotes": it["sold_notes"], "notes": it["notes"], "fields": it["fields"],
                "files": files.listed(it["id"]), "upkeep": upkeep.of_item(it["id"]), "maintenance": upkeep.log_of(it["id"]),
                "createdBy": (by.get("displayName") or by.get("name")) if by else None, "created": _iso(it["created_at"]),
                "canLog": may_add(u)})
    return out


SORTS = {"name": "i.name, i.id", "new": "i.created_at DESC, i.id DESC", "updated": "i.updated_at DESC, i.id DESC",
         "warranty": "i.warranty_expires IS NULL, i.warranty_expires, i.name", "price": "i.purchase_price IS NULL, i.purchase_price DESC, i.name",
         "bought": "i.purchase_date IS NULL, i.purchase_date DESC, i.name"}


def find(q: str = "", location: int | None = None, label: int | None = None, archived: str | None = None,
         warranty_soon: bool = False, sort: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
    """Things with every word of q somewhere in them, in this place (or a place inside it), with this label; archived:
    "only", "also", or left out for the things you still have; warranty_soon: those whose warranty ends within
    SOON_DAYS (or ended in the last week)."""
    where, args = ["1=1"], []
    if archived == "only":
        where.append("i.archived = 1")
    elif archived != "also":
        where.append("i.archived = 0")
    if location is not None:
        below = list(_below(int(location)))
        where.append(f"i.location_id IN ({db.marks(len(below))})")
        args += below
    if label is not None:
        where.append("EXISTS (SELECT 1 FROM thg_item_labels x WHERE x.item_id = i.id AND x.label_id = %s)")
        args.append(int(label))
    if warranty_soon:
        today = dt.date.today()
        where.append("i.lifetime_warranty = 0 AND i.warranty_expires BETWEEN %s AND %s")
        args += [today - dt.timedelta(days=7), today + dt.timedelta(days=SOON_DAYS)]
    for w in (q or "").lower().split()[:8]:
        where.append("i.words LIKE %s")
        args.append("%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    order = SORTS["warranty"] if warranty_soon and not sort else SORTS.get(sort or "name", SORTS["name"])
    n = max(1, min(int(limit), 5000))
    rows = db.q(f"SELECT i.* FROM thg_items i WHERE {' AND '.join(where)} ORDER BY {order} LIMIT %s OFFSET %s",
                [*args, n, max(0, int(offset))])
    for r in rows:
        r["fields"] = json.loads(r["fields"] or "[]")
    return rows


def listed(u: dict, rows: list[dict]) -> list[dict]:
    places = {x["id"]: x for x in locations()}
    tags = _labels_of([r["id"] for r in rows])
    return [public(r, u, full=False, places=places, tags=tags) for r in rows]


def counts() -> dict:
    today = dt.date.today()
    r = db.one("SELECT COALESCE(SUM(archived = 0), 0) AS items, COALESCE(SUM(archived = 1), 0) AS archived, "
               "COALESCE(SUM(archived = 0 AND lifetime_warranty = 0 AND warranty_expires BETWEEN %s AND %s), 0) AS soon, "
               "COALESCE(SUM(CASE WHEN archived = 0 THEN purchase_price * quantity END), 0) AS worth FROM thg_items",
               (today - dt.timedelta(days=7), today + dt.timedelta(days=SOON_DAYS)))
    due = db.one("SELECT COUNT(*) AS n FROM thg_upkeep k JOIN thg_items i ON i.id = k.item_id WHERE i.archived = 0 AND k.next_due <= %s",
                 (today + dt.timedelta(days=7),))
    return {"items": int(r["items"]), "archived": int(r["archived"]), "warrantySoon": int(r["soon"]),
            "upkeepDue": int(due["n"]), "worth": float(r["worth"] or 0)}


# ---- changing things

def _set_labels(item_id: int, ids: list[int]) -> None:
    db.ex("DELETE FROM thg_item_labels WHERE item_id = %s", (item_id,))
    for lid in ids:
        db.ex("INSERT IGNORE INTO thg_item_labels (item_id, label_id) VALUES (%s, %s)", (item_id, lid))


def _location_of(data: dict) -> tuple[bool, int | None]:
    """(given, place id) from locationId (an id) or location (an id, a path "House / Kitchen", or {id})."""
    if "locationId" in data:
        v = data.get("locationId")
    elif "location" in data:
        v = data.get("location")
        if isinstance(v, dict):
            v = v.get("id")
    else:
        return False, None
    if v in (None, "", 0):
        return True, None
    if isinstance(v, int) or str(v).strip().isdigit():
        return True, location(v)["id"]
    return True, location_by_path(str(v).split("/"))


def create(u: dict, data: dict, import_ref: str | None = None) -> dict:
    need_add(u)
    f = clean(data)
    given, loc = _location_of(data)
    ids = label_ids(data.get("labels"))
    f["location_id"] = loc if given else None
    f["fields"] = json.dumps(f["fields"], ensure_ascii=False)
    f["created_by"] = u.get("id")
    f["words"] = ""
    f["import_ref"] = import_ref
    cols = list(f)
    with db.tx():
        iid = db.ex(f"INSERT INTO thg_items ({', '.join(cols)}) VALUES ({db.marks(len(cols))})", [f[c] for c in cols])
        _set_labels(iid, ids)
    _rewords(iid)
    return get(iid)


def update(u: dict, it: dict, data: dict) -> dict:
    """Change the fields given; labels (ids or names) replace the thing's labels; locationId moves it."""
    need_write(u, it)
    f = clean(data, partial=True)
    given, loc = _location_of(data)
    if given:
        f["location_id"] = loc
    if "fields" in f:
        f["fields"] = json.dumps(f["fields"], ensure_ascii=False)
    with db.tx():
        if f:
            db.ex(f"UPDATE thg_items SET {', '.join(k + ' = %s' for k in f)} WHERE id = %s", [*f.values(), it["id"]])
        if "labels" in data:
            _set_labels(it["id"], label_ids(data.get("labels")))
    _rewords(it["id"])
    return get(it["id"])


def delete(u: dict, it: dict) -> None:
    need_write(u, it)
    db.ex("DELETE FROM thg_items WHERE id = %s", (it["id"],))  # its files, labels, upkeep and log go with it
    related.forget("item", it["id"])  # its links to other items of the suite go too


def duplicate(u: dict, it: dict) -> dict:
    """A copy of the thing (its details and labels; not its files, upkeep or log), named "... (copy)"."""
    need_add(u)
    data = {k: _iso(it[c]) if not isinstance(it[c], Decimal) else float(it[c]) for k, c in COLUMNS.items()}
    data["name"] = (it["name"] + " (copy)")[:255]
    data["serialNumber"] = None
    data["assetId"] = None
    data["locationId"] = it["location_id"]
    data["labels"] = [x["id"] for x in _labels_of([it["id"]]).get(it["id"], [])]
    return create(u, data)


# ---- the app's settings (admins)

def currency() -> str:
    return db.get_setting("currency") or "EUR"


def settings() -> dict:
    return {"currency": currency(), "currencies": list(CURRENCIES)}


def set_settings(data: dict) -> dict:
    if "currency" in data:
        c = str(data.get("currency") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", c):
            raise Invalid("currency: a three-letter code such as EUR or USD")
        db.set_setting("currency", c)
    return settings()
