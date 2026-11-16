"""The tools, with the same permissions as the web app: a viewer only reads, a member adds things and keeps upkeep and
the log, editors and admins change everything. Upkeep made here stays in ioThings (an assistant has no ioTask list to
pick); its "done" is the same as in the web app."""
from typing import Literal, Optional

from app import __version__, config, model, upkeep
from app.mcp.base import ADDS, DELETES, READ_ONLY, WRITES, clamp, find_item, find_location, guard, item_out, server, summary, who

ITEM_FIELDS = """
    location: a place's id or path ('House / Garage'); a path that does not exist yet is made.
    labels: names (made when missing); given, they replace the thing's labels.
    people: the family members whose it is (names or ids, see overview's family); given, they replace the thing's
    people ([] for nobody's in particular).
    purchase_date, warranty_expires, sold_date: YYYY-MM-DD. purchase_price, sold_price: amounts in the currency.
    fields: the thing's own details as {name: value} (filter size, paint colour, PIN of the safe's manual...).
"""


def fields(fn):
    fn.__doc__ = (fn.__doc__ or "") + ITEM_FIELDS
    return fn


def _data(**kw) -> dict:
    names = {"name": "name", "description": "description", "quantity": "quantity", "location": "location", "labels": "labels", "people": "people",
             "manufacturer": "manufacturer", "model_number": "modelNumber", "serial_number": "serialNumber",
             "asset_id": "assetId", "url": "url", "purchase_date": "purchaseDate", "purchase_price": "purchasePrice",
             "purchase_from": "purchaseFrom", "warranty_expires": "warrantyExpires", "lifetime_warranty": "lifetimeWarranty",
             "warranty_details": "warrantyDetails", "insured": "insured", "archived": "archived", "sold_date": "soldDate",
             "sold_price": "soldPrice", "sold_to": "soldTo", "notes": "notes", "fields": "fields"}
    return {names[k]: v for k, v in kw.items() if v is not None}


@server.tool(annotations=READ_ONLY)
def overview() -> dict:
    """Who you are signed in as and what you may do, how many things there are (still yours, archived, warranties
    ending within 30 days, upkeep due within a week, what they cost together), the currency, the places, the labels
    and the family (the people a thing can be marked as theirs). Start here."""
    u = who()
    return {"you": {"name": u["name"], "displayName": u.get("displayName"), "role": u.get("role")},
            "youCan": {"add": model.may_add(u), "changeEverything": model.may_edit_all(u)},
            "counts": model.counts(), "currency": model.currency(),
            "places": [{"id": x["id"], "path": x["path"], "things": x["count"]} for x in model.locations()][:200],
            "labels": [{"name": x["name"], "things": x["count"]} for x in model.labels()][:100],
            "family": [{"id": x["id"], "name": x["displayName"], "things": x["count"]} for x in model.family()],
            "upkeepSoon": [{"thing": k["item"]["name"], "what": k["title"], "due": k["nextDue"]} for k in upkeep.all_due(14)][:20],
            "version": __version__, "webApp": config.PUBLIC_URL or None}


@server.tool(annotations=READ_ONLY)
def search_items(query: str = "", location: Optional[str] = None, label: Optional[str] = None,
                 archived: Optional[Literal["only", "also"]] = None, person: Optional[str] = None, limit: int = 50) -> list:
    """Things with every word of the query in the name, description, maker, model or serial number, notes, place,
    labels or own fields ('drill', 'samsung fridge'); location: only in this place (or one inside it; id or path);
    label: only with this label; person: only the things of this family member (name or id); archived: only the
    archived ones, or also them (left out: the ones you still have). An empty query lists them all."""
    who()
    pid = guard(model.person, person)["id"] if person else None
    loc = find_location(location)["id"] if location else None
    lab = next((x["id"] for x in model.labels() if x["name"].lower() == (label or "").lower() or str(x["id"]) == str(label)), None)
    if label and lab is None:
        return []
    return [summary(who(), r) for r in model.find(query, loc, lab, archived, limit=clamp(limit, 1, 500), person=pid)]


@server.tool(annotations=READ_ONLY)
def get_item(item: str) -> dict:
    """Everything about one thing (its id, or its name when that names one): place, labels, whose it is, maker, model and serial
    number, purchase, warranty and sale details, own fields, notes, files, upkeep and maintenance log."""
    u = who()
    return item_out(u, find_item(u, item))


@server.tool(annotations=ADDS)
@fields
def create_item(name: str, description: Optional[str] = None, quantity: Optional[int] = None, location: Optional[str] = None,
                labels: Optional[list[str]] = None, people: Optional[list[str]] = None, manufacturer: Optional[str] = None,
                model_number: Optional[str] = None, serial_number: Optional[str] = None, url: Optional[str] = None, purchase_date: Optional[str] = None,
                purchase_price: Optional[float] = None, purchase_from: Optional[str] = None, warranty_expires: Optional[str] = None,
                lifetime_warranty: Optional[bool] = None, warranty_details: Optional[str] = None, insured: Optional[bool] = None,
                notes: Optional[str] = None, fields: Optional[dict[str, str]] = None) -> dict:
    """Add a thing."""
    u = who()
    d = _data(name=name, description=description, quantity=quantity, location=location, labels=labels, people=people, manufacturer=manufacturer,
              model_number=model_number, serial_number=serial_number, url=url, purchase_date=purchase_date,
              purchase_price=purchase_price, purchase_from=purchase_from, warranty_expires=warranty_expires,
              lifetime_warranty=lifetime_warranty, warranty_details=warranty_details, insured=insured, notes=notes, fields=fields)
    return item_out(u, guard(model.create, u, d))


@server.tool(annotations=WRITES)
@fields
def update_item(item: str, name: Optional[str] = None, description: Optional[str] = None, quantity: Optional[int] = None,
                location: Optional[str] = None, labels: Optional[list[str]] = None, people: Optional[list[str]] = None,
                manufacturer: Optional[str] = None,
                model_number: Optional[str] = None, serial_number: Optional[str] = None, url: Optional[str] = None,
                purchase_date: Optional[str] = None, purchase_price: Optional[float] = None, purchase_from: Optional[str] = None,
                warranty_expires: Optional[str] = None, lifetime_warranty: Optional[bool] = None,
                warranty_details: Optional[str] = None, insured: Optional[bool] = None, archived: Optional[bool] = None,
                sold_date: Optional[str] = None, sold_price: Optional[float] = None, sold_to: Optional[str] = None,
                notes: Optional[str] = None, fields: Optional[dict[str, str]] = None) -> dict:
    """Change a thing (its id or name): only what is given changes. archived=true for a thing that is sold, given
    away or thrown out (it keeps its story); sold_* say to whom and for how much."""
    u = who()
    it = find_item(u, item)
    d = _data(name=name, description=description, quantity=quantity, location=location, labels=labels, people=people, manufacturer=manufacturer,
              model_number=model_number, serial_number=serial_number, url=url, purchase_date=purchase_date,
              purchase_price=purchase_price, purchase_from=purchase_from, warranty_expires=warranty_expires,
              lifetime_warranty=lifetime_warranty, warranty_details=warranty_details, insured=insured, archived=archived,
              sold_date=sold_date, sold_price=sold_price, sold_to=sold_to, notes=notes, fields=fields)
    return item_out(u, guard(model.update, u, it, d))


@server.tool(annotations=DELETES)
def delete_item(item: str) -> dict:
    """Delete a thing (its id or name) with its files, upkeep and log. It cannot be brought back: ask first, and
    prefer update_item(archived=true) for something that is gone."""
    u = who()
    it = find_item(u, item)
    guard(model.delete, u, it)
    return {"deleted": it["name"]}


@server.tool(annotations=READ_ONLY)
def list_locations() -> list:
    """The places, as paths ('House / Kitchen / Drawer by the sink'), each with how many things are in it."""
    who()
    return [{"id": x["id"], "path": x["path"], "things": x["count"], **({"description": x["description"]} if x["description"] else {})}
            for x in model.locations()]


@server.tool(annotations=ADDS)
def create_location(name: str, inside: Optional[str] = None, description: Optional[str] = None) -> dict:
    """A new place; inside: the place it is in (id or path)."""
    u = who()
    parent = find_location(inside)["id"] if inside else None
    return guard(model.save_location, u, {"name": name, "parentId": parent, "description": description})


@server.tool(annotations=READ_ONLY)
def warranties_ending(days: int = 60) -> list:
    """Things whose warranty ends within this many days (or ended in the last week), the soonest first."""
    u = who()
    import datetime as dt
    end = dt.date.today() + dt.timedelta(days=clamp(days, 1, 3650))
    rows = [r for r in model.find(archived=None, sort="warranty", limit=2000)
            if r["warranty_expires"] and not r["lifetime_warranty"] and dt.date.today() - dt.timedelta(days=7) <= r["warranty_expires"] <= end]
    return [summary(u, r) for r in rows]


@server.tool(annotations=READ_ONLY)
def list_upkeep(within_days: Optional[int] = None) -> list:
    """The upkeep of the things you own, the soonest first: what, which thing, how often, when it is due next
    (daysLeft below 0: late), and whether it is also a task in ioTask. within_days: only what is due by then."""
    who()
    return [{"id": k["id"], "thing": k["item"]["name"], "thingId": k["itemId"], "what": k["title"], "every": k["every"],
             "nextDue": k["nextDue"], "daysLeft": k["daysLeft"], "inIoTask": bool(k["task"]), **({"notes": k["notes"]} if k["notes"] else {})}
            for k in upkeep.all_due(clamp(within_days, 0, 3650) if within_days is not None else None)]


@server.tool(annotations=ADDS)
def add_upkeep(item: str, what: str, every: int, unit: Literal["day", "week", "month", "year"], next_due: Optional[str] = None,
               notes: Optional[str] = None) -> dict:
    """Something a thing (id or name) needs every so often: what ('Annual service'), every N units, the day it is
    next due (YYYY-MM-DD; today when left out). It stays in ioThings; a person can make it an ioTask task in the web app."""
    u = who()
    it = find_item(u, item)
    return guard(upkeep.add, None, u, it["id"], {"title": what, "everyN": every, "everyUnit": unit, "nextDue": next_due, "notes": notes})


@server.tool(annotations=WRITES)
def upkeep_done(upkeep_id: int, date: Optional[str] = None, notes: Optional[str] = None, cost: Optional[float] = None,
                done_by: Optional[str] = None) -> dict:
    """An upkeep (its id, from list_upkeep or get_item) was done, that day (today when left out): a line in the
    maintenance log, and the upkeep moves on to its next day."""
    u = who()
    return guard(upkeep.done, None, u, upkeep_id, {"date": date, "notes": notes, "cost": cost, "doneBy": done_by})


@server.tool(annotations=ADDS)
def log_maintenance(item: str, what: str, date: Optional[str] = None, notes: Optional[str] = None, cost: Optional[float] = None,
                    done_by: Optional[str] = None) -> dict:
    """A one-off line in a thing's maintenance log (a repair, a part replaced): what, the day (today when left out),
    notes, the cost and who did it."""
    u = who()
    it = find_item(u, item)
    return guard(upkeep.log_add, u, it["id"], {"title": what, "date": date, "notes": notes, "cost": cost, "doneBy": done_by})
