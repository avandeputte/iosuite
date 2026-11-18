"""The tools, with the same permissions as the web app: each account sees only the documents it may; a viewer only
reads, a member adds documents and changes their own, editors and admins change every one they see."""
from typing import Literal, Optional

from app import __version__, config, files, model
from app.mcp.base import ADDS, DELETES, READ_ONLY, WRITES, clamp, doc_out, find_doc, guard, server, summary, who

DOC_FIELDS = """
    kind: passport, passport_card, id_card, driver_license, visa, residence, insurance, vehicle, medical, birth,
    marriage, property, legal, tax, education, membership or other.
    people: the family members it belongs to (names or ids, see overview's family); given, they replace its people.
    issued_on, expires_on: YYYY-MM-DD. remind_days: days before it expires that a reminder goes (0: none; left out:
    the kind's usual: nine months for a passport, two for a license, one for a policy).
    visibility: family (everyone with a role in ioDocs), people (the people it is for, whoever added it, editors and
    admins; the usual) or private (the people it is for and whoever added it only).
    fields: its own details as {name: value} (nationality, class, coverage, phone number of the insurer...).
"""


def fields(fn):
    fn.__doc__ = (fn.__doc__ or "") + DOC_FIELDS
    return fn


def _data(**kw) -> dict:
    names = {"title": "title", "kind": "kind", "number": "number", "issuer": "issuer", "country": "country",
             "issued_on": "issuedOn", "expires_on": "expiresOn", "remind_days": "remindDays", "visibility": "visibility",
             "people": "people", "notes": "notes", "fields": "fields", "archived": "archived"}
    return {names[k]: v for k, v in kw.items() if v is not None}


@server.tool(annotations=READ_ONLY)
def overview() -> dict:
    """Who you are signed in as and what you may do, how many documents you see (in all, expiring within their
    reminder, expired, archived, by kind), the family (the people a document can belong to) and the documents that
    expire within 120 days. Start here."""
    u = who()
    soon = model.find(u, status="expiring", limit=30)
    return {"you": {"name": u["name"], "displayName": u.get("displayName"), "role": u.get("role")},
            "youCan": {"add": model.may_add(u), "changeAll": model.may_edit_all(u)},
            "counts": model.counts(u),
            "family": [{"id": x["id"], "name": x["displayName"], "documents": x["count"]} for x in model.family(u)],
            "expiringSoon": [summary(u, r) for r in soon][:30],
            "version": __version__, "webApp": config.PUBLIC_URL or None}


@server.tool(annotations=READ_ONLY)
def expiring(within_days: int = 180, person: Optional[str] = None, include_expired: bool = True) -> list:
    """The documents you see that expire within this many days (and, include_expired, those that have), the soonest
    first, with how many days are left; person: only one family member's (name or id)."""
    import datetime as dt
    u = who()
    pid = guard(model.person, person)["id"] if person else None
    rows = model.find(u, person=pid, sort="expires", limit=1000)
    today = dt.date.today()
    out = []
    for r in rows:
        e = model.expiry(r, today)
        if e and e["days"] <= clamp(within_days, 0, 3700) and (include_expired or e["days"] >= 0):
            out.append(summary(u, r))
    return out[:200]


@server.tool(annotations=READ_ONLY)
def search_documents(query: str = "", kind: Optional[str] = None, person: Optional[str] = None,
                     status: Optional[Literal["expiring", "expired", "archived", "all"]] = None, limit: int = 50) -> list:
    """Documents you see with every word of the query in the title, kind, number, issuer, notes, own fields, people
    or the text read off their scans ('passport riley', 'geico'); kind: one kind (see add_document); person: one
    family member's (name or id); status: expiring (within its reminder, or expired), expired, archived or all (left
    out: those not archived). An empty query lists them all."""
    u = who()
    pid = guard(model.person, person)["id"] if person else None
    rows = guard(model.find, u, query, kind, pid, status, None, clamp(limit, 1, 200))
    return [summary(u, r) for r in rows]


@server.tool(annotations=READ_ONLY)
def get_document(document: str) -> dict:
    """Everything about one document (its id, or its title when that names one): kind, whose, number, issuer,
    country, dates and expiry, reminder, visibility, own details, notes and its files."""
    u = who()
    return doc_out(u, find_doc(u, document))


@server.tool(annotations=READ_ONLY)
def scan_text(document: str, file_id: int) -> dict:
    """What was read off one of a document's scans (its text), to answer what the scan alone says."""
    u = who()
    d = find_doc(u, document)
    return {"text": guard(files.text_of, d["id"], file_id)[:20000]}


@server.tool(annotations=ADDS)
@fields
def add_document(title: Optional[str] = None, kind: str = "other", number: Optional[str] = None, issuer: Optional[str] = None,
                 country: Optional[str] = None, issued_on: Optional[str] = None, expires_on: Optional[str] = None,
                 remind_days: Optional[int] = None, visibility: Optional[str] = None, people: Optional[list[str]] = None,
                 notes: Optional[str] = None, fields: Optional[dict] = None) -> dict:
    """Add a document (its scans are added in the web app, which reads them). title: left out, the kind's name."""
    u = who()
    d = guard(model.create, u, _data(title=title, kind=kind, number=number, issuer=issuer, country=country, issued_on=issued_on,
                                     expires_on=expires_on, remind_days=remind_days, visibility=visibility, people=people,
                                     notes=notes, fields=fields))
    return doc_out(u, d)


@server.tool(annotations=WRITES)
@fields
def update_document(document: str, title: Optional[str] = None, kind: Optional[str] = None, number: Optional[str] = None,
                    issuer: Optional[str] = None, country: Optional[str] = None, issued_on: Optional[str] = None,
                    expires_on: Optional[str] = None, remind_days: Optional[int] = None, visibility: Optional[str] = None,
                    people: Optional[list[str]] = None, notes: Optional[str] = None, fields: Optional[dict] = None,
                    archived: Optional[bool] = None) -> dict:
    """Change a document (its id or title): only what is given changes."""
    u = who()
    d = find_doc(u, document)
    new = guard(model.update, u, d, _data(title=title, kind=kind, number=number, issuer=issuer, country=country,
                                          issued_on=issued_on, expires_on=expires_on, remind_days=remind_days,
                                          visibility=visibility, people=people, notes=notes, fields=fields, archived=archived))
    return doc_out(u, new)


@server.tool(annotations=ADDS)
def renew_document(document: str, number: Optional[str] = None, issued_on: Optional[str] = None,
                   expires_on: Optional[str] = None) -> dict:
    """The renewed passport (license, policy...) in place of this one (id or title): a new document with the same
    kind, title, issuer, people and reminder and the new number and dates; the old one is archived."""
    u = who()
    d = find_doc(u, document)
    return doc_out(u, guard(model.renew, u, d, _data(number=number, issued_on=issued_on, expires_on=expires_on)))


@server.tool(annotations=DELETES)
def delete_document(document: str) -> dict:
    """Delete a document (its id or title) with its scans. It cannot be brought back: ask first, and prefer
    update_document(archived=true) for an old one."""
    u = who()
    d = find_doc(u, document)
    guard(model.delete, u, d)
    return {"deleted": d["title"]}
