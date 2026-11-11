"""The MCP server instance (iosuite_shared.mcp: who is asking, the annotations, the limits) and what every tool module
shares: finding contacts and books by name."""
from mcp.server.mcpserver.exceptions import ToolError

from iosuite_shared import mcp as shared_mcp
from iosuite_shared.mcp import ADDS, DELETES, READ_ONLY, UPDATES, WRITES, clamp, current_user, need_admin, who

from app import __version__, config, db, model

# what the tool modules take from here: the suite's pieces (iosuite_shared.mcp) and ioContact's own helpers
__all__ = ["ADDS", "DELETES", "READ_ONLY", "UPDATES", "WRITES", "book_ids", "brief", "clamp", "contact_out", "current_user", "default_book", "find_book", "find_contact", "need_admin", "readable_books", "server", "who"]

server = shared_mcp.make_server(
    config.APP, "ioContact", __version__,
    instructions=(
        "The family's address book (ioContact). Start with overview. Find people with search_contacts (names, emails, "
        "phone digits, companies, addresses, labels and notes all match), then get_contact for everything about one, "
        "including relations. Contacts are named by id or by name; a name has to match one contact. Relations are "
        "gender-neutral types (sibling, parent, child, cousin, spouse...; see relation_types) and the other side is kept "
        "by itself: making Tim Mary's child makes Mary Tim's parent. A birthday can be partial: only the parts that are known "
        "(a year, a year and month, a month and day, or all three). "
        "For upkeep: find_duplicates (scored, with reasons), preview_merge and merge_contacts (undo_merge can take a merge "
        "back), data_quality_report and fix_data_quality. To enrich a contact, research the person (LinkedIn, company "
        "sites, social networks...) and file what you find with suggest_contact_update: it only proposes, and a person "
        "accepts or dismisses each suggestion in the web app. Ask before deleting or merging contacts."
    ),
)

def public_url() -> str:
    return config.PUBLIC_URL


def contact_link(cid: int) -> str | None:
    return f"{config.PUBLIC_URL}/#/c/{cid}" if config.PUBLIC_URL else None


# ---- address books

def readable_books(u: dict) -> list[dict]:
    return model.books_for(u)


def book_ids(u: dict, book: str | int | None = None) -> list[int]:
    if book in (None, "", "all"):
        return [b["id"] for b in readable_books(u)]
    return [find_book(u, book)["id"]]


def find_book(u: dict, ref, writable: bool = False) -> dict:
    """A book by id, name or slug ("Family", "Personal")."""
    books = readable_books(u)
    s = str(ref).strip()
    hit = [b for b in books if str(b["id"]) == s] or [b for b in books if b["name"].lower() == s.lower() or b["slug"] == s.lower()]
    if not hit:
        raise ToolError(f"No address book '{ref}'. These are yours: " + ", ".join(f"{b['name']} (id {b['id']})" for b in books))
    if len(hit) > 1:
        raise ToolError(f"'{ref}' names more than one address book: " + ", ".join(f"{b['name']} (id {b['id']})" for b in hit))
    b = hit[0]
    if writable and not model.can_write_book(u, b):
        raise ToolError(f"You can read '{b['name']}' but not change it (a viewer only reads; members change their own private books, editors the shared ones)")
    return b


def default_book(u: dict) -> dict:
    """Where a new contact goes when no book is named: the first shared book this account may change, else its own."""
    books = [b for b in readable_books(u) if model.can_write_book(u, b)]
    if not books:
        raise ToolError("This account cannot add contacts anywhere")
    return books[0]


# ---- contacts

def find_contact(u: dict, ref, writable: bool = False) -> dict:
    """A contact row by id, or by a name that matches exactly one contact (the full name first, then a search)."""
    ids = book_ids(u)
    s = str(ref).strip()
    if not s:
        raise ToolError("Name a contact (its id or its name)")
    row = None
    if s.isdigit():
        row = model.get_row(int(s))
        if not row or row["deleted"] or row["address_book_id"] not in ids:
            raise ToolError(f"No contact with id {s}")
    else:
        marks = ",".join(["%s"] * len(ids)) or "0"
        rows = db.q(f"SELECT id FROM con_contacts WHERE deleted = 0 AND address_book_id IN ({marks}) AND fn = %s COLLATE {db.search_collation()} LIMIT 6",
                    (*ids, s)) if ids else []
        if not rows:
            found, _ = model.search(ids, s, limit=6)
            rows = [{"id": x["id"]} for x in found]
        if not rows:
            raise ToolError(f"No contact matches '{s}'. Try search_contacts.")
        if len(rows) > 1:
            names = db.q(f"SELECT id, fn FROM con_contacts WHERE id IN ({','.join(['%s'] * len(rows))})", [r["id"] for r in rows])
            raise ToolError(f"'{s}' matches several contacts; give the id: " + "; ".join(f"{r['fn']} (id {r['id']})" for r in names))
        row = model.get_row(rows[0]["id"])
    if writable and not model.can_write_book(u, model.book(row["address_book_id"])):
        raise ToolError(f"You can read {row['fn']} but not change them (a viewer only reads; members change their own private books, editors the shared ones)")
    return row


def book_names(u: dict) -> dict:
    return {b["id"]: b["name"] for b in readable_books(u)}


def contact_out(u: dict, cid: int) -> dict:
    """Everything about a contact, for a reader: empty fields left out, social profiles with their links, the book's name."""
    from app import iopix, vcard
    c = model.full(cid)
    c.pop("extra", None)
    c.pop("etag", None)
    c.pop("href", None)
    if not c.get("birthday"):
        c.pop("birthdayRemind", None)
    c["book"] = book_names(u).get(c["bookId"])
    for s in c.get("social") or []:
        s["url"] = vcard.social_url(s["service"], s["value"])
    if c.get("iopix"):
        c["iopix"]["url"] = iopix.person_url(c["iopix"]["personId"])
    for r in c.get("relations") or []:
        for k in ("relatedUid", "relatedGender", "relatedHasPhoto", "label"):
            r.pop(k, None)
        if r.get("relatedBookId") not in book_names(u):
            r.pop("relatedId", None)
        r.pop("relatedBookId", None)
    link = contact_link(cid)
    if link:
        c["webUrl"] = link
    return {k: v for k, v in c.items() if v not in (None, "", [], {})}


def brief(u: dict, s: dict) -> dict:
    out = {"id": s["id"], "name": s["fn"], "book": book_names(u).get(s["bookId"]), "email": s.get("email"), "phone": s.get("phone"),
           "org": s.get("org"), "title": s.get("title"), "birthday": s.get("birthday"), "favorite": s.get("favorite") or None,
           "iopixPersonId": s.get("iopixPersonId")}
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}
