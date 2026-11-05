"""The read-only tools: what any signed-in account may ask about the contacts it can see."""
from typing import Literal, Optional

from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError

from app import __version__, config, db, iopix, model, relations as rel, users, vcard
from app.fold import fold
from app.mcp.base import READ_ONLY, book_ids, brief, clamp, contact_out, find_contact, readable_books, server, who

EXPORT_MAX_CHARS = 400_000  # an export bigger than this is a download for the web app, not an answer


@server.tool(annotations=READ_ONLY)
def overview() -> dict:
    """Who you are signed in as, the address books you can see (with counts and whether you may change them), totals,
    the labels in use, the birthdays and anniversaries of the next 14 days, and whether ioPix is connected. Start here."""
    u = who()
    ids = book_ids(u)
    marks = ",".join(["%s"] * len(ids)) or "0"
    t = db.one(f"SELECT count(*) AS n, sum(favorite) AS fav, sum(bday_month IS NOT NULL) AS bday, sum(iopix_person_id IS NOT NULL) AS ip, "
               f"sum(photo IS NOT NULL) AS ph FROM con_contacts WHERE deleted = 0 AND address_book_id IN ({marks})", ids) if ids else {}
    nrel = db.one(f"SELECT count(*) AS n FROM con_contact_relations r JOIN con_contacts c ON c.id = r.contact_id WHERE c.deleted = 0 AND c.address_book_id IN ({marks})", ids)["n"] if ids else 0
    return {
        "you": {"name": u["name"], "displayName": u.get("display_name"), "role": u["role"]},
        "addressBooks": [{"id": b["id"], "name": b["name"], "shared": b["owner_id"] is None, "contacts": b.get("n"),
                          "youCanChange": model.can_write_book(u, b)} for b in readable_books(u)],
        "contacts": int(t.get("n") or 0), "favorites": int(t.get("fav") or 0), "withBirthday": int(t.get("bday") or 0),
        "withPhoto": int(t.get("ph") or 0), "linkedToIopix": int(t.get("ip") or 0), "relations": int(nrel or 0),
        "labels": [f"{x['tag']} ({x['n']})" for x in model.all_tags(ids)],
        "next14Days": model.upcoming(ids, 14),
        "iopixConnected": bool(iopix.settings()["url"]),
        "version": __version__, "webApp": config.PUBLIC_URL or None,
    }


@server.tool(annotations=READ_ONLY)
def list_address_books() -> list:
    """The address books you can see: the shared Family book (and any other shared ones) and your private books."""
    u = who()
    return [{"id": b["id"], "name": b["name"], "description": b.get("description"), "shared": b["owner_id"] is None,
             "contacts": b.get("n"), "youCanChange": model.can_write_book(u, b)} for b in readable_books(u)]


@server.tool(annotations=READ_ONLY)
def search_contacts(text: str = "", book: Optional[str] = None, label: Optional[str] = None, favorites_only: bool = False,
                    linked_to_iopix: bool = False, sort: Literal["given", "family", "updated", "created"] = "given",
                    limit: int = 50, offset: int = 0) -> dict:
    """Find contacts. text matches names, nicknames, maiden names, emails, phone digits, companies, job titles, addresses,
    labels and notes; several words must all match. book: an address book's name or id (all books when left out).
    label: one label (tag) exactly. sort: by given name, family name, last change or creation. Returns {total, contacts}
    with the main email and phone of each; get_contact has everything."""
    u = who()
    ids = book_ids(u, book)
    items, total = model.search(ids, text or "", label, favorites_only, clamp(limit, 1, 200), clamp(offset, 0, 10 ** 6), sort,
                                True if linked_to_iopix else None)
    return {"total": total, "contacts": [brief(u, x) for x in items]}


@server.tool(annotations=READ_ONLY)
def get_contact(contact: str) -> dict:
    """Everything about one contact (by id or name): names, phones, emails, addresses, birthday and other dates, company,
    job, social profiles with links, websites, labels, notes, relations (with the related contact's id when it is a
    contact you can see), the ioPix person it is linked to, and its link in the web app."""
    u = who()
    return contact_out(u, find_contact(u, contact)["id"])


@server.tool(annotations=READ_ONLY)
def get_contacts(contacts: list[str]) -> list:
    """Several contacts at once (ids or names), as get_contact gives them. At most 50."""
    u = who()
    if len(contacts) > 50:
        raise ToolError("At most 50 at a time")
    return [contact_out(u, find_contact(u, c)["id"]) for c in contacts]


@server.tool(annotations=READ_ONLY)
def get_vcard(contact: str, version: Literal["3.0", "4.0", "jcard"] = "3.0") -> str:
    """One contact as a vCard (3.0 for the widest support, 4.0) or as jCard JSON, photo included."""
    import json
    u = who()
    cid = find_contact(u, contact)["id"]
    if version == "jcard":
        return json.dumps(vcard.to_jcard(model.full(cid, with_photo=True)), ensure_ascii=False)
    return model.vcard_text(cid, version)


@server.tool(annotations=READ_ONLY)
def view_photo(contact: str) -> Image:
    """Look at a contact's photo (or, when it has none and is linked to ioPix, the person's face from ioPix)."""
    u = who()
    r = find_contact(u, contact)
    got = model.photo(r["id"])
    if not got and r["iopix_person_id"]:
        try:
            got = iopix.face(r["iopix_person_id"])
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"ioPix did not answer: {e}")
    if not got:
        raise ToolError(f"{r['fn']} has no photo")
    fmt = got[1].split(";")[0].split("/")[-1].replace("jpg", "jpeg")
    return Image(data=got[0], format=fmt)


@server.tool(annotations=READ_ONLY)
def get_relatives(contact: str, relation: Optional[str] = None) -> dict:
    """A contact's relations, each with how they are related ("Sister", "Father-in-law"...). relation: only one kind,
    as a type (sibling, parent, cousin...) or a word (brother, mother, aunt...)."""
    u = who()
    r = find_contact(u, contact)
    c = contact_out(u, r["id"])
    rels = c.get("relations") or []
    if relation:
        t = relation.strip().lower().replace(" ", "_").replace("-", "_")
        if t not in rel.TYPES:
            t = rel.from_label(relation)[0]
        rels = [x for x in rels if x["type"] == t]
    return {"contact": c["fn"], "id": r["id"], "relations": rels}


@server.tool(annotations=READ_ONLY)
def family_tree(contact: str, depth: int = 3) -> dict:
    """The family and other relations around a contact, `depth` steps out (1 to 6): {nodes, edges}, where an edge says
    "from's <type> is to" (from's parent is to). Good for questions like "who are Ann's cousins' children"."""
    from app.api import family_graph
    u = who()
    r = find_contact(u, contact)
    g = family_graph(r["id"], book_ids(u), clamp(depth, 1, 6))
    names = {n["id"]: n["fn"] for n in g["nodes"]}
    for e in g["edges"]:
        e["reads"] = f"{names.get(e['from'])}'s {rel.TYPES.get(e['type'], (None, e['type']))[1].lower()} is {names.get(e['to'])}"
    return g


@server.tool(annotations=READ_ONLY)
def upcoming_dates(days: int = 30, book: Optional[str] = None) -> list:
    """Birthdays, anniversaries and other dates in the next `days` days (up to 366), soonest first, with the age or
    number of years when the year is known. Birthdays someone asked not to be reminded of are left out."""
    u = who()
    return model.upcoming(book_ids(u, book), clamp(days, 1, 366))


@server.tool(annotations=READ_ONLY)
def birthdays_in_month(month: int, book: Optional[str] = None) -> list:
    """Everyone whose birthday falls in a month (1-12), by day. Birthdays someone asked not to be reminded of are
    left out (as in upcoming_dates and the birthday calendar)."""
    u = who()
    if not 1 <= int(month) <= 12:
        raise ToolError("month is 1-12")
    ids = book_ids(u, book)
    marks = ",".join(["%s"] * len(ids)) or "0"
    rows = db.q(f"SELECT id, fn, bday_year, bday_month, bday_day FROM con_contacts WHERE deleted = 0 AND address_book_id IN ({marks}) "
                f"AND bday_month = %s AND bday_remind = 1 ORDER BY bday_day, fn", (*ids, int(month))) if ids else []
    return [{"id": r["id"], "name": r["fn"], "day": r["bday_day"], "year": r["bday_year"]} for r in rows]


@server.tool(annotations=READ_ONLY)
def list_labels(book: Optional[str] = None) -> list:
    """The labels (tags) in use, with how many contacts carry each."""
    u = who()
    return [{"label": x["tag"], "contacts": x["n"]} for x in model.all_tags(book_ids(u, book))]


@server.tool(annotations=READ_ONLY)
def relation_types() -> list:
    """The relation types a relation can have, with their inverse (kept by itself) and how they read for a man, a woman
    or anyone."""
    return [{"type": k, "inverse": v[0], "label": v[1], "male": v[2], "female": v[3]} for k, v in rel.TYPES.items()]


@server.tool(annotations=READ_ONLY)
def social_services() -> list:
    """The social networks a profile can be on (the service names update_contact takes) and their address patterns."""
    return [{"service": k, "name": v[0], "base": vcard.SOCIAL_BASE.get(k)} for k, v in vcard.SOCIAL_SERVICES.items()]


@server.tool(annotations=READ_ONLY)
def find_duplicates(book: Optional[str] = None, min_score: int = 35) -> list:
    """Groups of contacts that are probably the same person, most certain first. Each pair has a score (0-100), a level
    (very likely, likely, possible) and the reasons: the same email or phone, the same or a similar name, a nickname
    (Bob for Robert), the same birthday or company; other birthdays or genders count against. Pairs someone marked
    as different people are left out. merge_contacts folds a group into one; mark_not_duplicates keeps them apart."""
    from app import quality
    u = who()
    out = []
    for g in quality.find(book_ids(u, book), clamp(min_score, 10, 100)):
        out.append({"score": g["score"], "level": g["level"], "contacts": [brief(u, x) for x in g["contacts"]],
                    "pairs": [{"a": p["a"], "b": p["b"], "score": p["score"], "reasons": p["reasons"]} for p in g["pairs"]]})
    return out


@server.tool(annotations=READ_ONLY)
def preview_merge(contacts: list[str], keep: Optional[str] = None) -> dict:
    """What merging these contacts would give, before doing it: the combined contact, and `choices`, the fields where
    they disagree (name, birthday, company, photo...) with each contact's value. Pass your picks to merge_contacts."""
    from app import quality
    u = who()
    rows = [find_contact(u, c) for c in contacts]
    if len(rows) < 2:
        raise ToolError("Name at least two contacts")
    k = find_contact(u, keep)["id"] if keep else rows[0]["id"]
    pv = quality.preview([r["id"] for r in rows], k)
    return {"keep": k, "merged": {kk: v for kk, v in pv["merged"].items() if v not in (None, "", [], {}) and kk not in ("extra", "etag", "href", "uid")},
            "choices": pv["choices"]}


@server.tool(annotations=READ_ONLY)
def data_quality_report(book: Optional[str] = None, check: Optional[str] = None) -> list:
    """Data quality checks: contacts without a name, email addresses and phone numbers that do not look right,
    impossible birthdays, names in ALL CAPITALS, the same email or phone twice on one contact, relations to a name that
    is now a contact, phone numbers without the country code, ioPix links without a photo, contacts with no way to reach
    them. Each check has its findings; `fix` says whether fix_data_quality can repair them."""
    from app import quality
    u = who()
    return [{**x, "items": x["items"][:200]} for x in quality.run_checks(book_ids(u, book), check) if x["count"]]


@server.tool(annotations=READ_ONLY)
def export_contacts(format: Literal["vcf", "vcf4", "jcard", "csv-google", "csv-outlook"] = "vcf", book: Optional[str] = None,
                    contacts: Optional[list[str]] = None) -> str:
    """Contacts as one file's text: vCard 3.0 (vcf), vCard 4.0 (vcf4), jCard, or CSV in Google Contacts' or Outlook's
    columns. Only the named contacts when `contacts` is given, otherwise a whole book (or all books)."""
    from app.api import export_text
    u = who()
    if contacts:
        ids = [find_contact(u, c)["id"] for c in contacts]
    else:
        ids = [x["id"] for x in model.search(book_ids(u, book), limit=100000)[0]]
    text = export_text(ids, format)[0]
    if len(text) > EXPORT_MAX_CHARS:
        raise ToolError(f"That export is {len(text) // 1000} kB; name fewer contacts, or download it from the web app (Import and export)")
    return text


@server.tool(annotations=READ_ONLY)
def connection_details() -> dict:
    """The addresses to type into a phone, a mail app or a calendar: CardDAV, LDAP, the birthday calendar feeds and the
    REST API. Phones and apps sign in with your user name and an app password (Settings › Apps and devices)."""
    u = who()
    base = config.PUBLIC_URL or "(this server's address)"
    tok = users.calendar_token(u["id"])
    return {"user": u["name"], "carddav": f"{base}/dav/", "books": [{"name": b["name"], "url": f"{base}/dav/addressbooks/{u['name']}/{b['slug']}/"}
                                                                   for b in readable_books(u)],
            "ldap": {"enabled": config.LDAP_PORT > 0, "port": config.LDAP_PORT, "base": config.LDAP_BASE,
                     "bindDn": f"cn={u['name']},ou=users,{config.LDAP_BASE}"},
            "calendar": {"family": f"{base}/cal/{tok}/family.ics", "all": f"{base}/cal/{tok}/all.ics"},
            "restApi": f"{base}/api/docs", "mcp": f"{base}/mcp"}


@server.tool(annotations=READ_ONLY)
def list_iopix_people(text: str = "", unlinked_only: bool = False) -> list:
    """The people named in ioPix (the family photo library), with the contact each is linked to, if any.
    text: part of a name. link_iopix_person links one to a contact."""
    u = who()
    if not iopix.settings()["url"]:
        raise ToolError("ioPix is not connected (Settings › ioPix in the web app)")
    try:
        ppl = iopix.people()
    except Exception as e:  # noqa: BLE001
        raise ToolError(f"ioPix did not answer: {e}")
    ids = book_ids(u)
    marks = ",".join(["%s"] * len(ids)) or "0"
    linked = {r["iopix_person_id"]: {"id": r["id"], "name": r["fn"]} for r in db.q(
        f"SELECT id, fn, iopix_person_id FROM con_contacts WHERE iopix_person_id IS NOT NULL AND deleted = 0 AND address_book_id IN ({marks})", ids or [0])}
    t = fold(text).strip()
    out = []
    for p in ppl:
        if t and t not in fold(p["name"]):
            continue
        c = linked.get(p["id"])
        if unlinked_only and c:
            continue
        out.append({"personId": p["id"], "name": p["name"], "photos": p.get("count"), "contact": c,
                    "url": iopix.person_url(p["id"], p["name"])})
    return out[:500]

