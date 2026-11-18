"""The family's papers: what a document is, whose it is, who may see and change it, when it expires, and the search.

A document (doc_documents) is a passport, an ID card, a driver's license, an insurance policy, a birth certificate,
a vehicle registration... It has a kind (KINDS), the people of the family it belongs to (doc_people), its number, who
issued it, its dates, its own fields, its scans (app/files.py, read by app/ocr.py) and a reminder before it expires.

Who sees a document is the document's own business, because some papers are nobody else's:

- family: everyone with a role in ioDocs (the house insurance, the family's travel insurance);
- people (the usual): the people it is for, whoever added it, and the editors and admins (the grown-ups who keep
  the family's papers): a child sees their own passport, not their parents' licenses;
- private: the people it is for and whoever added it, nobody else, not even an admin (a medical record).

A viewer only looks. A member adds documents and changes the ones they added or that are theirs. An editor (and an
admin) changes every document they can see. Nobody has a role here until a suite admin gives one (the default role is
none, as in ioMoney): these are a family's most private papers.
"""
import datetime as dt
import json
import re

from iosuite_shared import family as suite_family, related, users as shared_users
from iosuite_shared.errors import Invalid

from app import db


class NotFound(Exception):
    """No such document (or file), or not one this account may see."""


class Forbidden(Exception):
    """The account sees it but may not do this."""


# kind -> (what one is called, plural, days before it expires that the reminder goes by default: None for papers
# that do not expire, the icon of the web app). Passports: nine months, since many countries want six left at the border.
KINDS = {
    "passport": ("Passport", "Passports", 270, "passport"),
    "passport_card": ("Passport card", "Passport cards", 180, "badge"),
    "id_card": ("ID card", "ID cards", 90, "badge"),
    "driver_license": ("Driver’s license", "Driver’s licenses", 60, "car"),
    "visa": ("Visa", "Visas", 90, "plane"),
    "residence": ("Residence permit", "Residence permits", 180, "home"),
    "insurance": ("Insurance policy", "Insurance policies", 30, "shield"),
    "vehicle": ("Vehicle registration", "Vehicle registrations", 30, "car"),
    "medical": ("Medical or vaccination", "Medical and vaccination", 30, "health"),
    "birth": ("Birth certificate", "Birth certificates", None, "cert"),
    "marriage": ("Marriage certificate", "Marriage certificates", None, "cert"),
    "property": ("Deed or lease", "Deeds and leases", 60, "home"),
    "legal": ("Will or legal paper", "Wills and legal papers", None, "gavel"),
    "tax": ("Tax paper", "Tax papers", None, "receipt"),
    "education": ("Diploma or school paper", "Diplomas and school papers", None, "school"),
    "membership": ("Membership or card", "Memberships and cards", 30, "card"),
    "other": ("Other document", "Other documents", 30, "file"),
}
VISIBILITY = ("family", "people", "private")
MAX_FIELDS = 50
MAX_PEOPLE = 20
NEW_TITLE = "New document"


def kind_label(k: str) -> str:
    return KINDS.get(k, KINDS["other"])[0]


# ---- who may

def may_add(u: dict | None) -> bool:
    """Add documents: members and more."""
    return shared_users.is_member(u)


def may_edit_all(u: dict | None) -> bool:
    """Change every document one sees: editors and admins."""
    return shared_users.can_write(u)


def has_role(u: dict | None) -> bool:
    return bool(u) and (u.get("role") or "none") != "none"


def visible_sql(u: dict, alias: str = "d") -> tuple[str, list]:
    """The WHERE part that keeps the documents this account may see, and its parameters."""
    if not has_role(u):
        return "0", []
    uid = u.get("id") or 0
    mine = f"({alias}.created_by = %s OR EXISTS (SELECT 1 FROM doc_people p WHERE p.doc_id = {alias}.id AND p.user_id = %s))"
    if may_edit_all(u):
        return f"({alias}.visibility <> 'private' OR {mine})", [uid, uid]
    return f"({alias}.visibility = 'family' OR {mine})", [uid, uid]


def _is_theirs(u: dict, d: dict) -> bool:
    uid = u.get("id")
    return bool(uid) and (d.get("created_by") == uid or uid in (d.get("_people") or people_of([d["id"]]).get(d["id"], [])))


def can_see(u: dict, d: dict) -> bool:
    if not has_role(u):
        return False
    if d["visibility"] == "family":
        return True
    if d["visibility"] == "people" and may_edit_all(u):
        return True
    return _is_theirs(u, d)


def can_write(u: dict | None, d: dict | None) -> bool:
    """Editors and admins (any document they see), and a member for the documents they added or that are theirs."""
    if not (u and d) or not can_see(u, d):
        return False
    return may_edit_all(u) or (shared_users.is_member(u) and _is_theirs(u, d))


def need_add(u: dict) -> None:
    if not may_add(u):
        raise Forbidden("A viewer only looks: a member or more adds documents")


def need_write(u: dict, d: dict) -> None:
    if not can_write(u, d):
        raise Forbidden("You can see this document but not change it: editors, the people it is for and whoever added it can")


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
    try:
        d = dt.date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        raise Invalid(f"{name}: a day as YYYY-MM-DD is expected") from None
    if not 1900 <= d.year <= 2200:
        raise Invalid(f"{name}: a day between 1900 and 2200")
    return d


def remind(v) -> int | None:
    """Days before it expires that the reminder goes: a whole number (0: none), empty: the kind's usual."""
    if v in (None, ""):
        return None
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        raise Invalid("Reminder: a number of days is expected") from None
    if not 0 <= n <= 1000:
        raise Invalid("Reminder: between 0 and 1000 days before")
    return n


def flag(v) -> int:
    if isinstance(v, str):
        return int(v.strip().lower() in ("1", "true", "yes", "y", "on"))
    return int(bool(v))


def kind_of(v) -> str:
    s = re.sub(r"[\s'’-]+", "_", str(v or "other").strip().lower())
    if s in KINDS:
        return s
    for k, (label, plural, _, _) in KINDS.items():  # "Driver's license", "passports"
        if s in (re.sub(r"[\s'’-]+", "_", label.lower()), re.sub(r"[\s'’-]+", "_", plural.lower())):
            return k
    raise Invalid("kind: one of " + ", ".join(KINDS))


def visibility(v) -> str:
    s = str(v or "people").strip().lower()
    if s not in VISIBILITY:
        raise Invalid("visibility: family, people or private")
    return s


def own_fields(v) -> list[dict]:
    """The document's own details: [{name, value}], from such a list or a {name: value} object."""
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
        raise Invalid(f"At most {MAX_FIELDS} fields on one document")
    return out


FIELDS = {
    "title": lambda v: text(v, 255, "The title"),
    "kind": kind_of,
    "number": lambda v: text(v, 191, "The number"),
    "issuer": lambda v: text(v, 255, "Issued by"),
    "country": lambda v: text(v, 64, "The country"),
    "issuedOn": lambda v: day(v, "Issued on"),
    "expiresOn": lambda v: day(v, "Expires on"),
    "remindDays": remind,
    "visibility": visibility,
    "archived": flag,
    "notes": lambda v: text(v, 50000, "The notes", True),
    "fields": own_fields,
}
COLUMNS = {"title": "title", "kind": "kind", "number": "number", "issuer": "issuer", "country": "country",
           "issuedOn": "issued_on", "expiresOn": "expires_on", "remindDays": "remind_days", "visibility": "visibility",
           "archived": "archived", "notes": "notes", "fields": "fields"}


def clean(data: dict, partial: bool = False) -> dict:
    out = {}
    for k, fn in FIELDS.items():
        if k in data or not partial:
            out[COLUMNS[k]] = fn(data.get(k))
    if "title" in out and not out["title"]:
        if partial:
            raise Invalid("A title, please")
        out["title"] = kind_label(out.get("kind") or "other") if out.get("kind") not in (None, "other") else NEW_TITLE
    if "fields" in out:
        out["fields"] = json.dumps(out["fields"], ensure_ascii=False)
    return out


# ---- the family: whose a document is

def family(u: dict | None = None) -> list[dict]:
    """The suite's family (Settings › Security › Family), each with how many documents this account sees are theirs."""
    n = {}
    if u:
        where, args = visible_sql(u)
        n = {r["user_id"]: int(r["n"]) for r in db.q(
            f"SELECT p.user_id, COUNT(*) AS n FROM doc_people p JOIN doc_documents d ON d.id = p.doc_id "
            f"WHERE d.archived = 0 AND {where} GROUP BY p.user_id", args)}
    return [{**suite_family.public(m), "count": n.get(m["id"], 0)} for m in suite_family.members()]


def person(ref, fam: list[dict] | None = None) -> dict:
    """A member of the family by id, account name or display name (any case)."""
    fam = fam if fam is not None else [suite_family.public(m) for m in suite_family.members()]
    s = str(ref or "").strip()
    for m in fam:
        if s == str(m["id"]) or s.lower() in (str(m.get("name") or "").lower(), str(m.get("displayName") or "").lower()):
            return m
    first = [m for m in fam if str(m.get("displayName") or "").lower().split(" ")[:1] == [s.lower()]]
    if len(first) == 1:
        return first[0]
    raise Invalid(f"No one in the family is '{s}'. The family: " + (", ".join(m["displayName"] for m in fam) or "nobody yet"))


def people_ids(refs) -> list[int]:
    if refs in (None, ""):
        return []
    if isinstance(refs, str):
        refs = [x for x in refs.split(",") if x.strip()]
    if not isinstance(refs, list):
        raise Invalid("people: a list of family members (ids or names) is expected")
    fam = [suite_family.public(m) for m in suite_family.members()]
    out = []
    for r in refs:
        m = person(r.get("id") if isinstance(r, dict) else r, fam)
        if m["id"] not in out:
            out.append(m["id"])
    if len(out) > MAX_PEOPLE:
        raise Invalid(f"At most {MAX_PEOPLE} people on one document")
    return out


def match_person(name: str | None) -> dict | None:
    """The member of the family a name read off a document is (given names and surname, in any order): their first
    name and, when the family has two of that first name, their last name too."""
    words = [w for w in re.split(r"[\s,]+", (name or "").lower()) if len(w) > 1]
    if not words:
        return None
    fam = [suite_family.public(m) for m in suite_family.members()]
    hits = []
    for m in fam:
        own = [w for w in re.split(r"[\s,]+", str(m.get("displayName") or m.get("name") or "").lower()) if w]
        if own and own[0] in words:
            hits.append((m, len(own) > 1 and own[-1] in words))
    full = [m for m, both in hits if both]
    if len(full) == 1:
        return full[0]
    return hits[0][0] if len(hits) == 1 else None


def people_of(ids: list[int]) -> dict:
    """{document id: [user ids]}."""
    if not ids:
        return {}
    out = {}
    for r in db.q(f"SELECT doc_id, user_id FROM doc_people WHERE doc_id IN ({db.marks(len(ids))})", list(ids)):
        out.setdefault(r["doc_id"], []).append(r["user_id"])
    return out


def _set_people(doc_id: int, ids: list[int]) -> None:
    db.ex("DELETE FROM doc_people WHERE doc_id = %s", (doc_id,))
    for uid in ids:
        db.ex("INSERT IGNORE INTO doc_people (doc_id, user_id) VALUES (%s, %s)", (doc_id, uid))


# ---- expiry

def remind_days(d: dict) -> int | None:
    """Days before it expires that it is mentioned: the document's own, else its kind's (None: never)."""
    if d.get("remind_days") is not None:
        return int(d["remind_days"]) or None
    return KINDS.get(d.get("kind"), KINDS["other"])[2]


def expiry(d: dict, today: dt.date | None = None) -> dict | None:
    """{on, days, state: expired | soon | ok, remindFrom}; None without a day."""
    if not d.get("expires_on"):
        return None
    today = today or dt.date.today()
    days = (d["expires_on"] - today).days
    lead = remind_days(d)
    state = "expired" if days < 0 else "soon" if lead and days <= lead else "ok"
    return {"on": d["expires_on"].isoformat(), "days": days, "state": state,
            "remindFrom": (d["expires_on"] - dt.timedelta(days=lead)).isoformat() if lead else None}


def _words(d: dict, names: list[str], texts: list[str]) -> str:
    try:
        fields = json.loads(d.get("fields") or "[]")
    except ValueError:
        fields = []
    parts = [d.get("title"), kind_label(d.get("kind")), d.get("number"), d.get("issuer"), d.get("country"), d.get("notes"),
             *names, *(f"{f.get('name')} {f.get('value')}" for f in fields if isinstance(f, dict)), *texts]
    return " ".join(str(p) for p in parts if p).lower()[:1_000_000]


def rewords(doc_id: int) -> None:
    d = db.one("SELECT * FROM doc_documents WHERE id = %s", (doc_id,))
    if not d:
        return
    fam = {m["id"]: m for m in suite_family.members()}
    names = [str(fam[u].get("displayName") or "") for u in people_of([doc_id]).get(doc_id, []) if u in fam]
    texts = [r["text"] for r in db.q("SELECT text FROM doc_files WHERE doc_id = %s AND text IS NOT NULL", (doc_id,))]
    db.ex("UPDATE doc_documents SET words = %s, updated_at = updated_at WHERE id = %s", (_words(d, names, texts), doc_id))


# ---- reading and listing

def get(doc_id) -> dict | None:
    try:
        return db.one("SELECT * FROM doc_documents WHERE id = %s", (int(doc_id),))
    except (TypeError, ValueError):
        return None


def readable(u: dict, doc_id) -> dict:
    d = get(doc_id)
    if not d or not can_see(u, d):
        raise NotFound("No such document")
    return d


def _iso(v):
    return v.isoformat() if v else None


def public(d: dict, u: dict, full: bool = True, people: dict | None = None, fam: dict | None = None) -> dict:
    """A document as the API gives it. full: with its files and notes."""
    fam = fam if fam is not None else {m["id"]: suite_family.public(m) for m in suite_family.members()}
    ids = (people if people is not None else people_of([d["id"]])).get(d["id"], [])
    d = {**d, "_people": ids}
    try:
        fields = json.loads(d.get("fields") or "[]")
    except ValueError:
        fields = []
    j = {"id": d["id"], "title": d["title"], "kind": d["kind"], "kindLabel": kind_label(d["kind"]),
         "number": d.get("number"), "issuer": d.get("issuer"), "country": d.get("country"),
         "issuedOn": _iso(d.get("issued_on")), "expiresOn": _iso(d.get("expires_on")), "remindDays": d.get("remind_days"),
         "remindDefault": KINDS.get(d["kind"], KINDS["other"])[2], "expiry": expiry(d),
         "visibility": d["visibility"], "archived": bool(d.get("archived")), "renewedBy": d.get("renewed_by"),
         "people": [fam[x] for x in ids if x in fam], "fields": fields,
         "cover": f"api/documents/{d['id']}/files/{d['cover']}" if d.get("cover") else None,
         "writable": can_write(u, d), "mine": d.get("created_by") == u.get("id"),
         "created": _iso(d.get("created_at")), "updated": _iso(d.get("updated_at"))}
    if full:
        from app import files
        j["notes"] = d.get("notes")
        j["files"] = files.listed(d["id"])
        j["renews"] = [{"id": r["id"], "title": r["title"], "expiresOn": _iso(r["expires_on"])} for r in
                       db.q("SELECT * FROM doc_documents WHERE renewed_by = %s", (d["id"],)) if can_see(u, r)]
    return j


SORTS = {"expires": "d.expires_on IS NULL, d.expires_on, d.title", "title": "d.title, d.id", "new": "d.id DESC",
         "updated": "d.updated_at DESC, d.id DESC", "kind": "d.kind, d.title"}


def find(u: dict, q: str = "", kind: str | None = None, person: int | None = None, status: str | None = None,
         sort: str | None = None, limit: int = 500, offset: int = 0) -> list[dict]:
    """The documents this account sees. q: every word in the title, kind, number, issuer, notes, fields, people or the
    text read off the scans; kind: one kind; person: one family member's (account id); status: expiring (within its
    reminder), expired, archived, all (left out: the ones not archived); sort: SORTS (left out: expires, soonest
    first, the ones without a day last)."""
    where, args = visible_sql(u)
    conds = [where]
    if status == "archived":
        conds.append("d.archived = 1")
    elif status != "all":
        conds.append("d.archived = 0")
    if status == "expired":
        conds.append("d.expires_on < CURDATE()")
    elif status == "expiring":
        conds.append("d.expires_on IS NOT NULL")
    if kind:
        conds.append("d.kind = %s")
        args.append(kind_of(kind))
    if person:
        conds.append("EXISTS (SELECT 1 FROM doc_people p2 WHERE p2.doc_id = d.id AND p2.user_id = %s)")
        args.append(int(person))
    for w in (q or "").lower().split()[:12]:
        conds.append("d.words LIKE %s")
        args.append("%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    rows = db.q(f"SELECT d.* FROM doc_documents d WHERE {' AND '.join(conds)} ORDER BY {SORTS.get(sort or 'expires', SORTS['expires'])} "
                f"LIMIT %s OFFSET %s", [*args, min(max(int(limit), 1), 1000) if status != "expiring" else 1000, max(int(offset), 0)])
    if status == "expiring":
        today = dt.date.today()
        rows = [r for r in rows if (expiry(r, today) or {}).get("state") in ("soon", "expired")][:min(max(int(limit), 1), 1000)]
    return rows


def listed(u: dict, rows: list[dict]) -> list[dict]:
    people = people_of([r["id"] for r in rows])
    fam = {m["id"]: suite_family.public(m) for m in suite_family.members()}
    return [public(r, u, False, people, fam) for r in rows]


def counts(u: dict) -> dict:
    """How many documents this account sees: in all, expiring (within their reminder), expired, archived, by kind."""
    where, args = visible_sql(u)
    rows = db.q(f"SELECT d.id, d.kind, d.archived, d.expires_on, d.remind_days FROM doc_documents d WHERE {where}", args)
    today = dt.date.today()
    live = [r for r in rows if not r["archived"]]
    states = [(expiry(r, today) or {}).get("state") for r in live]
    kinds = {}
    for r in live:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    return {"documents": len(live), "soon": states.count("soon"), "expired": states.count("expired"),
            "archived": len(rows) - len(live), "kinds": kinds}


# ---- changing

def create(u: dict, data: dict) -> dict:
    need_add(u)
    cols = clean(data)
    pids = people_ids(data.get("people")) if "people" in data else []
    with db.tx():
        did = db.ex(f"INSERT INTO doc_documents ({', '.join(cols)}, words, created_by) VALUES ({', '.join(['%s'] * len(cols))}, '', %s)",
                    [*cols.values(), u.get("id")])
        _set_people(did, pids)
    rewords(did)
    return get(did)


def update(u: dict, d: dict, data: dict) -> dict:
    """Change the fields given; people (family members, ids or names) replace the document's people."""
    need_write(u, d)
    cols = clean(data, partial=True)
    pids = people_ids(data.get("people")) if "people" in data else None
    with db.tx():
        if cols:
            db.ex(f"UPDATE doc_documents SET {', '.join(k + ' = %s' for k in cols)} WHERE id = %s", [*cols.values(), d["id"]])
        if pids is not None:
            _set_people(d["id"], pids)
    rewords(d["id"])
    new = get(d["id"])
    if not can_see(u, new):  # made private to someone else: keep it visible to the one changing it, as theirs
        raise Invalid("You would no longer see this document: add yourself to its people, or keep it visible to editors")
    return new


def delete(u: dict, d: dict) -> None:
    need_write(u, d)
    with db.tx():
        db.ex("UPDATE doc_documents SET renewed_by = NULL WHERE renewed_by = %s", (d["id"],))
        db.ex("DELETE FROM doc_documents WHERE id = %s", (d["id"],))
    related.forget("document", d["id"])  # its links to other items of the suite go too


def renew(u: dict, d: dict, data: dict) -> dict:
    """The new passport (policy, license...) in place of this one: a new document of the same kind, title, issuer,
    people, visibility and reminder, with the new number and dates given; the old one is archived and points to it."""
    need_write(u, d)
    base = {"title": d["title"], "kind": d["kind"], "issuer": d.get("issuer"), "country": d.get("country"),
            "remindDays": d.get("remind_days"), "visibility": d["visibility"], "people": people_of([d["id"]]).get(d["id"], [])}
    base.update({k: v for k, v in (data or {}).items() if k in FIELDS or k == "people"})
    new = create(u, base)
    db.ex("UPDATE doc_documents SET archived = 1, renewed_by = %s WHERE id = %s", (new["id"], d["id"]))
    return new


# ---- what a scan says, applied

ZONE_KINDS = ("passport", "passport_card", "id_card", "residence", "visa")  # the kinds with a machine-readable zone
LABELS = {"number": "Number", "issuer": "Issued by", "country": "Country", "issued_on": "Issued on", "expires_on": "Expires on",
          "kind": "Kind", "title": "Title", "people": "Whose"}
EXTRA = (("holder", "Name"), ("birthDate", "Date of birth"), ("sex", "Sex"), ("nationality", "Nationality"),
         ("address", "Address"), ("class", "Class"), ("restrictions", "Restrictions"), ("endorsements", "Endorsements"))


def apply_found(u: dict, d: dict, found: dict) -> dict:
    """Fill in what the scan says where the document says nothing yet: {filled: [label], differs: [{field, label,
    value, current}]} (differs: what the scan says otherwise, for the person to take or leave)."""
    need_write(u, d)
    found = found or {}
    sets, filled, differs = {}, [], []
    ids = people_of([d["id"]]).get(d["id"], [])
    who = match_person(found.get("holder"))
    kind = d["kind"]
    if found.get("kind") in KINDS and found["kind"] != d["kind"]:
        if d["kind"] == "other":
            sets["kind"] = kind = found["kind"]
            filled.append(LABELS["kind"])
        else:
            differs.append({"field": "kind", "label": LABELS["kind"], "value": found["kind"], "shown": kind_label(found["kind"]),
                            "current": d["kind"]})
    for col, key in (("number", "number"), ("issuer", "issuer"), ("country", "country"), ("issued_on", "issuedOn"), ("expires_on", "expiresOn")):
        v = found.get(key)
        if v in (None, ""):
            continue
        if isinstance(v, str) and col.endswith("_on"):
            try:
                v = dt.date.fromisoformat(v[:10])
            except ValueError:
                continue
        if not d.get(col):
            sets[col] = v
            filled.append(LABELS[col])
        elif str(d[col]) != str(v):
            differs.append({"field": next(k for k, c in COLUMNS.items() if c == col), "label": LABELS[col],
                            "value": v.isoformat() if isinstance(v, dt.date) else v, "current": _iso(d[col]) if isinstance(d[col], dt.date) else d[col]})
    if who and not ids:
        _set_people(d["id"], [who["id"]])
        ids = [who["id"]]
        filled.append(LABELS["people"])
    if d["title"] in (NEW_TITLE, kind_label(d["kind"])) and (sets.get("kind") or kind != "other" or who):
        first = (who or {}).get("displayName", "").split(" ")[0] if who else None
        label = kind_label(kind)
        title = f"{first}{'’' if first.endswith('s') else '’s'} {label[0].lower() + label[1:]}" if first else label
        if title != d["title"]:
            sets["title"] = title
            filled.append(LABELS["title"])
    try:
        fields = json.loads(d.get("fields") or "[]")
    except ValueError:
        fields = []
    have = {str(f.get("name") or "").lower() for f in fields}
    added = False
    for key, name in EXTRA:
        v = found.get(key)
        if v in (None, "") or name.lower() in have:
            continue
        fields.append({"name": name, "value": v.isoformat() if isinstance(v, dt.date) else {"M": "Male", "F": "Female"}.get(v, v) if key == "sex" else str(v)})
        added = True
    if added:
        sets["fields"] = json.dumps(fields[:MAX_FIELDS], ensure_ascii=False)
        filled.append("Details")
    if sets:
        db.ex(f"UPDATE doc_documents SET {', '.join(k + ' = %s' for k in sets)} WHERE id = %s", [*sets.values(), d["id"]])
    rewords(d["id"])
    # what a passport or an ID card should have given and did not (most often its issue date: it is only in the printed
    # words, which a scan cannot always be sure of), for the person to type in from the page
    unread = []
    if found.get("source") == "mrz" or (found.get("checked") and kind in ZONE_KINDS):
        unread = [LABELS[c] for c in ("number", "issued_on", "expires_on") if not d.get(c) and c not in sets]
    return {"filled": filled, "differs": differs, "unread": unread}

