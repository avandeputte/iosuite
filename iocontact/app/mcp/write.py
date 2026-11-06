"""The tools that change contacts, with the same permissions as the web app: a viewer changes only their own private
book, editors and admins the shared ones too. Every change reaches phones and apps at their next CardDAV sync."""
from typing import Literal, Optional

from mcp.server.mcpserver.exceptions import ToolError

from app import db, enrich, iopix, model, relations as rel, users
from app.fold import fold
from app.mcp.base import ADDS, DELETES, READ_ONLY, WRITES, book_ids, contact_out, default_book, find_book, find_contact, server, who

CONTACT_SHAPE = """
    A contact is a JSON object; every field is optional, but give at least a name:
      name: {prefix, given, additional, family, suffix}   (or fn: "Ann Smith", split by itself)
      nickname, maiden, gender: M | F | O | N | U, kind: individual | org
      birthday: {year?, month?, day?} or "1980-05-17"   (any part can be left out: a year, a year and month, a month and day)
      birthdayRemind: false keeps the birthday out of the birthday calendar feed; true by default
      dates: [{label: "anniversary" | any word, year?, month, day}]   (other dates need a month and day)
      org (company), department, title (job title), role
      emails: [{value, label: home | work | other..., pref: true for the main one}]
      phones: [{value, label: mobile | home | work | main | fax..., pref}]
      addresses: [{street, city, region, postcode, country, pobox, ext, label: home | work, pref}]
      urls: [{value, label}]
      social: [{service: linkedin | facebook | instagram | x | threads | bluesky | mastodon | tiktok | youtube | github |
                whatsapp | telegram | signal | ... (see social_services), value: the user name or the profile's address}]
      tags: ["label", ...], notes, favorite: true
      relations: [{type: sibling | parent | child | spouse | cousin | ... (see relation_types), relatedId: a contact id,
                   or relatedName: a name (linked when it matches exactly one contact, else kept as a name)}]
"""
def shape(fn):
    """Adds the contact shape to a tool's description (applied under @server.tool, so before it reads the docstring)."""
    fn.__doc__ = (fn.__doc__ or "") + CONTACT_SHAPE
    return fn


LISTS = ("emails", "phones", "addresses", "urls", "social", "dates", "tags", "relations")


def _save(u: dict, book_id: int, data: dict, cid: Optional[int] = None) -> int:
    try:
        return model.save(book_id, data, cid, None, True, book_ids(u))
    except (ValueError, TypeError, KeyError) as e:
        raise ToolError(f"That contact does not look right: {e}")


def _rel_type(word: str) -> str:
    t = (word or "").strip().lower().replace(" ", "_").replace("-", "_")
    if t in rel.TYPES:
        return t
    t = rel.from_label(word)[0]
    if t == "other" and (word or "").strip().lower() != "other":
        raise ToolError(f"'{word}' is not a relation type; see relation_types")
    return t


def _clean_input(d: dict) -> dict:
    d = dict(d or {})
    for k in ("id", "uid", "href", "etag", "photo", "photoData", "bookId", "book", "webUrl", "hasPhoto", "created", "updated", "extra"):
        d.pop(k, None)
    if isinstance(d.get("tags"), str):
        d["tags"] = [t.strip() for t in d["tags"].split(",")]
    for key in ("emails", "phones", "urls"):  # plain strings are welcome too
        if isinstance(d.get(key), list):
            d[key] = [{"value": x} if isinstance(x, str) else x for x in d[key]]
    if isinstance(d.get("birthday"), str):
        d["birthday"] = _date(d["birthday"])
    return d


def _date(s: str) -> dict | None:
    """"1980-05-17", "1980-05", "1980", "--05-17" or "05-17" to {year, month, day} (None for the unknown parts)."""
    d = model.parse_date(s)
    if d is None:
        raise ToolError(f"A date is YYYY-MM-DD, YYYY-MM, YYYY or MM-DD (no year), not '{s}'")
    return d


@server.tool(annotations=ADDS)
@shape
def create_contact(contact: dict, book: Optional[str] = None) -> dict:
    """Add a contact. book: an address book's name or id (the shared Family book when left out, or your own when you
    cannot change the shared one). Returns the new contact. Look first with search_contacts so as not to make a
    duplicate."""
    u = who()
    b = find_book(u, book, writable=True) if book else default_book(u)
    data = _clean_input(contact)
    if not (data.get("fn") or data.get("name") or data.get("org") or data.get("emails")):
        raise ToolError("Give the contact a name")
    cid = _save(u, b["id"], data)
    return contact_out(u, cid)


@server.tool(annotations=WRITES)
@shape
def update_contact(contact: str, changes: dict, lists: Literal["add", "replace"] = "add") -> dict:
    """Change a contact (by id or name). changes: the fields to change, in the same shape as create_contact; fields left
    out stay as they are, and a field given as null or "" is cleared. lists: with "add" (the default) the emails,
    phones, addresses, websites, social profiles, dates, labels and relations given are added to the ones the contact
    has (the same value is not added twice); with "replace" they replace them, so an empty list clears one.
    Returns the contact as saved."""
    u = who()
    r = find_contact(u, contact, writable=True)
    c = model.full(r["id"])
    ch = _clean_input(changes)
    if "name" in ch and isinstance(ch["name"], dict):
        ch["name"] = {**c["name"], **{k: (v or "") for k, v in ch["name"].items()}}
        if "fn" not in ch:
            ch["fn"] = ""  # the full name follows the new parts
    for k, v in ch.items():
        if k in LISTS and lists == "add" and isinstance(v, list):
            have = c.get(k) or []
            if k == "tags":
                c[k] = sorted(set(have) | {t for t in v if t})
            else:
                keyf = (lambda x: (x.get("type"), x.get("relatedId") or (x.get("relatedName") or "").lower())) if k == "relations" \
                    else (lambda x: (str(x.get("value") or x.get("street") or x.get("label") or "").lower(), x.get("month"), x.get("day")))
                seen = {keyf(x) for x in have}
                c[k] = have + [x for x in v if keyf(x) not in seen]
        else:
            c[k] = v
    _save(u, r["address_book_id"], c, r["id"])
    return contact_out(u, r["id"])


@server.tool(annotations=DELETES)
def delete_contact(contact: str) -> dict:
    """Delete a contact (by id or name), with its relations. Phones and apps remove it at their next sync. There is no
    undo: ask first."""
    u = who()
    r = find_contact(u, contact, writable=True)
    model.delete(r["id"])
    return {"deleted": r["fn"], "id": r["id"]}


@server.tool(annotations=WRITES)
def add_relation(contact: str, related: str, relation: str, related_is_contact: bool = True) -> dict:
    """Say how two people are related: "<related> is <contact>'s <relation>". relation: a type (sibling, parent, child,
    spouse, partner, cousin, aunt_uncle, niece_nephew, grandparent, friend, colleague... see relation_types) or a word
    such as brother, mother or aunt. The other side is added by itself (make Tim Mary's child and Mary becomes Tim's
    parent). related: a contact (id or name); with related_is_contact=false it is only a name, for someone who is not
    a contact."""
    u = who()
    r = find_contact(u, contact, writable=True)
    t = _rel_type(relation)
    c = model.full(r["id"])
    if related_is_contact:
        o = find_contact(u, related)
        if o["id"] == r["id"]:
            raise ToolError("A contact cannot be related to themselves")
        if any(x["type"] == t and x.get("relatedId") == o["id"] for x in c["relations"]):
            return {"unchanged": True, "relations": contact_out(u, r["id"]).get("relations")}
        c["relations"].append({"type": t, "relatedId": o["id"], "relatedName": o["fn"]})
    else:
        c["relations"].append({"type": t, "relatedName": related.strip()})
    _save(u, r["address_book_id"], c, r["id"])
    return {"contact": c["fn"], "relations": contact_out(u, r["id"]).get("relations")}


@server.tool(annotations=DELETES)
def remove_relation(contact: str, related: str, relation: Optional[str] = None) -> dict:
    """Take a relation away (and its other side). related: the related contact or name; relation: only that type,
    when the two are related in more than one way."""
    u = who()
    r = find_contact(u, contact, writable=True)
    c = model.full(r["id"])
    t = _rel_type(relation) if relation else None
    try:
        oid = find_contact(u, related)["id"]
    except ToolError:
        oid = None
    keep = [x for x in c["relations"] if not ((t is None or x["type"] == t) and (
        (oid and x.get("relatedId") == oid) or (x.get("relatedName") or "").lower() == related.strip().lower()))]
    if len(keep) == len(c["relations"]):
        raise ToolError(f"{c['fn']} has no such relation with {related}")
    c["relations"] = keep
    _save(u, r["address_book_id"], c, r["id"])
    if oid:  # the other side, kept for a relation added from there
        o = model.full(oid)
        inv = rel.inverse(t) if t else None
        left = [x for x in o["relations"] if not (x.get("relatedId") == r["id"] and (t is None or x["type"] in (t, inv)))]
        if len(left) != len(o["relations"]) and model.can_write_book(u, model.book(o["bookId"])):
            o["relations"] = left
            _save(u, o["bookId"], o, oid)
    return {"contact": c["fn"], "relations": contact_out(u, r["id"]).get("relations")}


@server.tool(annotations=WRITES)
def set_labels(contacts: list[str], add: Optional[list[str]] = None, remove: Optional[list[str]] = None) -> dict:
    """Add and take away labels (tags) on several contacts at once."""
    u = who()
    done = []
    for ref in contacts:
        r = find_contact(u, ref, writable=True)
        c = model.full(r["id"])
        tags = (set(c["tags"]) | {t.strip() for t in add or [] if t.strip()}) - {t.strip() for t in remove or []}
        if tags != set(c["tags"]):
            _save(u, r["address_book_id"], {**c, "tags": sorted(tags)}, r["id"])
        done.append({"id": r["id"], "name": r["fn"], "labels": sorted(tags)})
    return {"contacts": done}


@server.tool(annotations=WRITES)
def set_favorite(contacts: list[str], favorite: bool = True) -> dict:
    """Mark contacts as favorites (or not)."""
    u = who()
    rows = [find_contact(u, ref, writable=True) for ref in contacts]
    for r in rows:
        model.set_fields(r["id"], favorite=1 if favorite else 0)
    return {"favorite": favorite, "contacts": [r["fn"] for r in rows]}


@server.tool(annotations=WRITES)
def move_contacts(contacts: list[str], book: str) -> dict:
    """Move contacts to another address book (from the shared Family book to your private one, for example). They keep
    their relations."""
    u = who()
    b = find_book(u, book, writable=True)
    rows = [find_contact(u, ref, writable=True) for ref in contacts]
    for r in rows:
        model.move(r["id"], b["id"])
    return {"book": b["name"], "moved": [r["fn"] for r in rows]}


@server.tool(annotations=DELETES)
def merge_contacts(keep: str, others: list[str], choices: Optional[dict] = None, photo_from: Optional[str] = None) -> dict:
    """Fold duplicates into one contact: the others' phones, emails, addresses, dates, profiles, labels and relations are
    added to `keep`, its empty fields are filled from them, relations pointing at the others move to it, and the
    others are deleted. choices: {field: contact} to take a field (name, nickname, birthday, org, title, notes, gender...)
    from a given contact instead (preview_merge lists where they disagree); photo_from: whose photo to keep.
    It can be undone with undo_merge. Ask first."""
    from app import quality
    u = who()
    k = find_contact(u, keep, writable=True)
    rows = [find_contact(u, ref, writable=True) for ref in others]
    if any(r["id"] == k["id"] for r in rows):
        raise ToolError("`keep` is also among `others`")
    ids = [k["id"], *[r["id"] for r in rows]]
    result = None
    if choices:
        full = {i: model.full(i) for i in ids}
        result = model.combine(model.full(k["id"], with_photo=True), [model.full(i, with_photo=True) for i in ids[1:]])
        result.pop("photoData", None)
        for field, who_ref in choices.items():
            src = find_contact(u, who_ref)["id"]
            if src not in full:
                raise ToolError(f"{who_ref} is not one of the contacts being merged")
            if field == "name":
                result["name"], result["fn"] = dict(full[src]["name"]), full[src]["fn"]
            elif field in full[src]:
                result[field] = full[src][field]
            else:
                raise ToolError(f"'{field}' is not a field to choose")
    pf = find_contact(u, photo_from)["id"] if photo_from else None
    mid = quality.merge(u, k["id"], ids[1:], result, pf)
    return {"merged": [r["fn"] for r in rows], "mergeId": mid, "into": contact_out(u, k["id"])}


@server.tool(annotations=WRITES)
def mark_not_duplicates(contacts: list[str]) -> dict:
    """These contacts are different people (twins, a father and son with one name...): find_duplicates stops offering them."""
    from app import quality
    u = who()
    rows = [find_contact(u, c, writable=True) for c in contacts]
    quality.not_duplicates([r["id"] for r in rows], u["id"])
    return {"keptApart": [r["fn"] for r in rows]}


@server.tool(annotations=READ_ONLY)
def list_merges(limit: int = 20) -> list:
    """Recent merges, newest first, and whether each can still be undone."""
    from app import quality
    u = who()
    return quality.history(book_ids(u), max(1, min(int(limit), 100)))


@server.tool(annotations=DELETES)
def undo_merge(merge_id: int) -> dict:
    """Put the contacts of a merge back as they were before it (changes made since to the kept contact are lost)."""
    from app import quality
    u = who()
    m = db.one("SELECT kept_contact_id FROM con_contact_merges WHERE id = %s", (int(merge_id),))
    if not m:
        raise ToolError("No such merge")
    find_contact(u, str(m["kept_contact_id"]), writable=True)
    try:
        return quality.undo(int(merge_id))
    except ValueError as e:
        raise ToolError(str(e))


@server.tool(annotations=WRITES)
def fix_data_quality(check: Literal["name_case", "repeats", "unlinked_relation", "national_phone", "iopix_photo"],
                     contacts: Optional[list[str]] = None, country_code: Optional[str] = None) -> dict:
    """Repair what a data quality check found, for all its findings or only these contacts: capitalise names, remove a
    repeated email or phone, link relations to the contact of that name, add the country code (country_code, such as
    +32) to numbers written without it, use the ioPix face as the photo."""
    from app import quality
    u = who()
    ids = [find_contact(u, c)["id"] for c in contacts] if contacts else None
    try:
        return quality.fix(u, check, ids, book_ids(u), country_code)
    except ValueError as e:
        raise ToolError(str(e))


# ---- enrichment: suggestions a person accepts in the web app

@server.tool(annotations=ADDS)
def suggest_contact_update(contact: str, suggestions: list[dict], source: str) -> dict:
    """File what you found about a contact as suggestions. Nothing changes: they wait in the web app (Maintenance ›
    Suggestions and the contact's page) until a person accepts or dismisses each one. Use it after researching a
    person on LinkedIn, a company site, a news article, Facebook, Instagram, X...; give where you found it.
    suggestions: [{field, value, evidence (the page's address), note (optional: why you think it is this person)}].
    field and value: name {given, family} or {fn}; nickname, org, department, title, notes, gender: text; birthday
    "YYYY-MM-DD", "YYYY-MM", "YYYY" or "MM-DD"; emails / phones / urls {value, label}; addresses {street, city, region, postcode, country,
    label}; social {service: linkedin | facebook | instagram | x | ..., value: the profile's address}; tags: a label.
    source: who found it (e.g. "Claude, web search")."""
    u = who()
    r = find_contact(u, contact, writable=True)
    out = {"added": 0, "known": 0, "dismissedBefore": 0, "pending": 0, "errors": []}
    for s in suggestions[:50]:
        try:
            res = enrich.add(r["id"], str(s.get("field")), s.get("value"), (source or "assistant")[:64], s.get("evidence"), s.get("note"), u["id"])
        except (ValueError, KeyError, TypeError) as e:
            out["errors"].append(f"{s.get('field')}: {e}")
            continue
        out[{"added": "added", "known": "known", "dismissed": "dismissedBefore", "pending": "pending"}[res]] += 1
    out["contact"] = r["fn"]
    out["note"] = "Waiting for a person to accept them in the web app."
    return out


@server.tool(annotations=ADDS)
def lookup_contact(contact: str) -> dict:
    """Look a contact up with the built-in public lookups (Gravatar by email; its GitHub, Mastodon and Bluesky
    profiles) and file what they find as suggestions for a person to accept."""
    u = who()
    r = find_contact(u, contact, writable=True)
    return enrich.lookup(r["id"], u["id"])


@server.tool(annotations=READ_ONLY)
def list_suggestions(contact: Optional[str] = None, status: Literal["pending", "accepted", "dismissed"] = "pending") -> list:
    """The suggestions waiting for a person (or those accepted or dismissed), with their source and evidence. Photos are
    left out of the answer. Accepting happens in the web app only."""
    u = who()
    cid = find_contact(u, contact)["id"] if contact else None
    items = enrich.listing(book_ids(u), status, cid)
    for x in items:
        if x["field"] == "photo":
            x["value"] = "(a photo)"
    return items


@server.tool(annotations=ADDS)
def import_contacts(data: str, book: Optional[str] = None, mode: Literal["update", "skip"] = "update") -> dict:
    """Add contacts from text: vCards (2.1, 3.0 or 4.0, any number), jCard JSON, or CSV with Google Contacts' or
    Outlook's header row. mode: update (a card whose UID is already in the book replaces it) or skip (keeps it)."""
    from app.api import import_cards, parse_cards
    u = who()
    b = find_book(u, book, writable=True) if book else default_book(u)
    try:
        cards = parse_cards(data)
    except (ValueError, KeyError, IndexError) as e:
        raise ToolError(f"Could not read that: {e}")
    if not cards:
        raise ToolError("No contacts in that text")
    return {"book": b["name"], **import_cards(u, b, cards, mode)}


@server.tool(annotations=WRITES)
def link_iopix_person(contact: str, person: Optional[str] = None, use_face_as_photo: bool = False) -> dict:
    """Link a contact to a person in ioPix (the family photo library), by the person's id or exact name
    (list_iopix_people); leave person out to unlink. The ioPix face shows as the contact's picture, and with
    use_face_as_photo it becomes the contact's photo, which phones then show too."""
    u = who()
    r = find_contact(u, contact, writable=True)
    c = model.full(r["id"])
    if not person:
        c["iopix"] = None
        _save(u, r["address_book_id"], c, r["id"])
        return {"contact": r["fn"], "iopix": None}
    try:
        ppl = iopix.people()
    except Exception as e:  # noqa: BLE001
        raise ToolError(f"ioPix did not answer: {e}")
    s = str(person).strip()
    hit = [p for p in ppl if str(p["id"]) == s] or [p for p in ppl if fold(p["name"]) == fold(s)] or \
        [p for p in ppl if fold(s) in fold(p["name"])]
    if not hit:
        raise ToolError(f"No ioPix person '{s}'; see list_iopix_people")
    if len(hit) > 1:
        raise ToolError(f"'{s}' matches several ioPix people: " + "; ".join(f"{p['name']} (id {p['id']})" for p in hit[:8]))
    p = hit[0]
    c["iopix"] = {"personId": p["id"], "name": p["name"]}
    _save(u, r["address_book_id"], c, r["id"])
    out = {"contact": r["fn"], "iopix": {"personId": p["id"], "name": p["name"], "url": iopix.person_url(p["id"], p["name"])}}
    if use_face_as_photo:
        got = iopix.face(p["id"])
        if got:
            model.set_photo(r["id"], got[0], got[1].split(";")[0])
            out["photo"] = "set from ioPix"
        else:
            out["photo"] = "ioPix has no face for this person yet"
    return out


@server.tool(annotations=WRITES)
def auto_link_iopix(book: Optional[str] = None, dry_run: bool = True) -> dict:
    """Contacts whose name matches exactly one ioPix person and that are not linked yet. With dry_run (the default) they
    are only listed; with dry_run=false they are linked."""
    u = who()
    try:
        ppl = iopix.people()
    except Exception as e:  # noqa: BLE001
        raise ToolError(f"ioPix did not answer: {e}")
    by_name: dict = {}
    for p in ppl:
        by_name.setdefault(p["name"].strip().lower(), []).append(p)
    taken = {r["iopix_person_id"] for r in db.q("SELECT iopix_person_id FROM con_contacts WHERE iopix_person_id IS NOT NULL AND deleted = 0")}
    out = []
    for s in model.search(book_ids(u, book), limit=100000)[0]:
        if s["iopixPersonId"]:
            continue
        m = by_name.get(s["fn"].strip().lower()) or []
        if len(m) == 1 and m[0]["id"] not in taken and model.can_write_book(u, model.book(s["bookId"])):
            out.append({"contactId": s["id"], "name": s["fn"], "personId": m[0]["id"]})
    if not dry_run:
        for x in out:
            c = model.full(x["contactId"])
            c["iopix"] = {"personId": x["personId"], "name": x["name"]}
            _save(u, c["bookId"], c, x["contactId"])
    return {"linked" if not dry_run else "wouldLink": out}


@server.tool(annotations=DELETES)
def remove_photo(contact: str) -> dict:
    """Take a contact's photo away (an ioPix face, when linked, still shows in the web app)."""
    u = who()
    r = find_contact(u, contact, writable=True)
    model.set_photo(r["id"], None, None)
    return {"contact": r["fn"], "photo": None}


@server.tool(annotations=ADDS)
def create_address_book(name: str, shared: bool = False, description: Optional[str] = None) -> dict:
    """Make an address book: private (only you see it) or, for editors and admins, shared with everyone."""
    u = who()
    if shared and not users.can_write(u):
        raise ToolError("Viewers make private address books only")
    bid = model.create_book(None if shared else u["id"], name.strip()[:128] or "Contacts", description)
    b = model.book(bid)
    return {"id": bid, "name": b["name"], "shared": shared}
