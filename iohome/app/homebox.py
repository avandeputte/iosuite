"""Homebox's CSV, both ways: import a Homebox export (Tools › Export inventory, or any sheet with its HB.* columns) and
export ioHome's things in the same format (for a spreadsheet, or to take them elsewhere).

The columns (Homebox's own reader, backend/internal/core/services/reporting): HB.name and HB.location are required;
HB.location is a path ("Home / Garage / Shelf"), made where it is missing; HB.labels (HB.tags in newer versions) are
separated by ";"; dates are 2026-11-15 (or 11/15/2026, 2026/11/15); HB.field.<name> columns are a thing's own fields;
HB.import_ref names a row, so importing the same export again changes the things it brought instead of adding them
twice. Comma- or tab-separated. Cells a spreadsheet would run as a formula are written with a ' in front (as Homebox
does) and read back without it. Photos, manuals and the maintenance log are not in Homebox's CSV.
"""
import csv
import datetime as dt
import io
import re

from iosuite_shared.errors import Invalid

from app import db, model

MAX_ROWS = 20000
FORMULA = "=+-@\t\r"


def _restore(s: str) -> str:
    """Homebox's guard against formulas taken off: '=SUM(...) is =SUM(...) again."""
    return s[1:] if len(s) > 1 and s[0] == "'" and s[1:].lstrip("'")[:1] in FORMULA else s


def _guard(s) -> str:
    s = "" if s is None else str(s)
    return "'" + s if s.lstrip("'")[:1] in FORMULA and s else s


def _date(s: str) -> str | None:
    s = (s or "").strip()
    if not s or s.startswith("0001-01-01"):
        return None
    for f in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            d = dt.datetime.strptime(s[:10], f).date()
            return d.isoformat() if 1900 <= d.year <= 2200 else None
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return None


def _bool(s: str) -> bool:
    return (s or "").strip().lower() in ("1", "t", "true", "yes", "y", "x")


def _num(s: str) -> str | None:
    s = (s or "").strip()
    try:
        return None if not s or float(s.replace(",", "")) == 0 else s
    except ValueError:
        return s


def read(raw: bytes) -> list[dict]:
    """The rows of a Homebox CSV as {column: value} (BOM, comma or tab, quoted cells)."""
    if not raw:
        raise Invalid("The file is empty")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    first = text.split("\n", 1)[0]
    tab, comma = first.find("\t"), first.find(",")
    sep = "\t" if tab != -1 and (comma == -1 or tab < comma) else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=sep))
    if not rows:
        raise Invalid("The file is empty")
    head = [h.strip() for h in rows[0]]
    if "HB.name" not in head or "HB.location" not in head:
        raise Invalid("Not a Homebox export: the columns HB.name and HB.location are missing")
    if len(rows) - 1 > MAX_ROWS:
        raise Invalid(f"At most {MAX_ROWS} rows in one go")
    out = []
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        out.append({h: _restore(r[i]) if i < len(r) else "" for i, h in enumerate(head)})
    return out


def _item_data(row: dict) -> dict:
    g = lambda *names: next((row[n] for n in names if row.get(n, "").strip()), "").strip()  # noqa: E731
    sold = _date(g("HB.sold_date", "HB.sold_time"))
    data = {
        "name": g("HB.name"), "description": g("HB.description") or None, "quantity": int(float(g("HB.quantity") or 1)) if re.fullmatch(r"\d+(\.\d+)?", g("HB.quantity") or "1") else 1,
        "manufacturer": g("HB.manufacturer") or None, "modelNumber": g("HB.model_number") or None,
        "serialNumber": g("HB.serial_number") or None, "url": g("HB.url") or None,
        "purchaseDate": _date(g("HB.purchase_date", "HB.purchase_time")), "purchasePrice": _num(g("HB.purchase_price")),
        "purchaseFrom": g("HB.purchase_from") or None, "warrantyExpires": _date(g("HB.warranty_expires")),
        "lifetimeWarranty": _bool(g("HB.lifetime_warranty")), "warrantyDetails": g("HB.warranty_details") or None,
        "insured": _bool(g("HB.insured")), "archived": _bool(g("HB.archived")) or bool(sold),
        "soldDate": sold, "soldPrice": _num(g("HB.sold_price")), "soldTo": g("HB.sold_to") or None,
        "soldNotes": g("HB.sold_notes") or None, "notes": g("HB.notes") or None,
        "fields": [{"name": h[len("HB.field."):], "value": v} for h, v in row.items() if h.startswith("HB.field.") and v.strip()],
    }
    aid = g("HB.asset_id")
    if aid and aid.strip("0-"):  # Homebox writes 000-000 for none
        data["assetId"] = aid
    return data


def keep(u: dict, rows: list[dict]) -> dict:
    """Every row a thing: a new one, or the one an earlier import of the same row (HB.import_ref) made, changed.
    {added, changed, skipped: [why], locations, labels}."""
    model.need_add(u)
    before_loc = db.one("SELECT COUNT(*) AS n FROM hom_locations")["n"]
    before_lab = db.one("SELECT COUNT(*) AS n FROM hom_labels")["n"]
    places: dict = {}
    added = changed = 0
    skipped = []
    for n, row in enumerate(rows, 2):
        name = (row.get("HB.name") or "").strip()
        if not name:
            skipped.append(f"Row {n}: no name")
            continue
        try:
            data = _item_data(row)
            data["locationId"] = model.location_by_path((row.get("HB.location") or "").split("/"), places)
            data["labels"] = [x.strip() for x in (row.get("HB.labels") or row.get("HB.tags") or "").split(";") if x.strip()]
            ref = (row.get("HB.import_ref") or "").strip()[:191] or None
            old = db.one("SELECT * FROM hom_items WHERE import_ref = %s", (ref,)) if ref else None
            if old:
                model.update(u, model.get(old["id"]), data)
                changed += 1
            else:
                model.create(u, data, import_ref=ref)
                added += 1
        except (Invalid, ValueError, model.NotFound, model.Forbidden) as e:
            skipped.append(f"Row {n} ({name[:60]}): {e}")
    return {"added": added, "changed": changed, "skipped": skipped[:200],
            "locations": db.one("SELECT COUNT(*) AS n FROM hom_locations")["n"] - before_loc,
            "labels": db.one("SELECT COUNT(*) AS n FROM hom_labels")["n"] - before_lab}


COLUMNS = ["HB.import_ref", "HB.location", "HB.labels", "HB.asset_id", "HB.archived", "HB.url", "HB.name", "HB.quantity",
           "HB.description", "HB.insured", "HB.notes", "HB.purchase_price", "HB.purchase_from", "HB.purchase_date",
           "HB.manufacturer", "HB.model_number", "HB.serial_number", "HB.lifetime_warranty", "HB.warranty_expires",
           "HB.warranty_details", "HB.sold_to", "HB.sold_price", "HB.sold_date", "HB.sold_notes"]


NUMBERS = {"HB.quantity", "HB.purchase_price", "HB.sold_price"}


def export(archived: bool = True) -> bytes:
    """Every thing as a Homebox CSV (HB.import_ref: ioHome's id, or the ref it came in with)."""
    rows = model.find(archived="also" if archived else None, limit=5000)
    places = {x["id"]: x["path"] for x in model.locations()}
    tags = model._labels_of([r["id"] for r in rows])
    extra = sorted({f["name"] for r in rows for f in r["fields"]}, key=str.lower)
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(COLUMNS + [f"HB.field.{x}" for x in extra])
    iso = lambda d: d.isoformat() if d else ""  # noqa: E731
    money = lambda v: f"{v:.2f}" if v is not None else ""  # noqa: E731
    for r in rows:
        own = {f["name"]: f["value"] for f in r["fields"]}
        vals = [r["import_ref"] or f"iohome-{r['id']}", places.get(r["location_id"], ""), "; ".join(t["name"] for t in tags.get(r["id"], [])),
                r["asset_id"] or "", str(bool(r["archived"])).lower(), r["url"] or "", r["name"], r["quantity"], r["description"] or "",
                str(bool(r["insured"])).lower(), r["notes"] or "", money(r["purchase_price"]), r["purchase_from"] or "",
                iso(r["purchase_date"]), r["manufacturer"] or "", r["model_number"] or "", r["serial_number"] or "",
                str(bool(r["lifetime_warranty"])).lower(), iso(r["warranty_expires"]), r["warranty_details"] or "",
                r["sold_to"] or "", money(r["sold_price"]), iso(r["sold_date"]), r["sold_notes"] or ""]
        vals += [own.get(x, "") for x in extra]
        w.writerow([v if h in NUMBERS else _guard(v) for h, v in zip(COLUMNS + extra, vals)])
    return out.getvalue().encode("utf-8")
