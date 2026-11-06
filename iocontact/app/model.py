"""Address books and contacts in MariaDB: reading, saving (with the inverse side of relations), deleting, searching.

Every change bumps the address book's sync token and stamps the contact with it, so CardDAV's sync-collection
and getctag tell clients exactly what changed. Deleted contacts stay as tombstones (deleted = 1, data cleared)
so clients learn about the deletion.
"""
import hashlib
import json
import re
import time
import uuid as uuidlib

from app import db, iopix, relations as rel, vcard

# ------------------------------------------------------------------ address books


def book_public(b: dict, user: dict | None = None) -> dict:
    return {"id": b["id"], "slug": b["slug"], "name": b["name"], "description": b.get("description"), "color": b.get("color"),
            "shared": b["owner_id"] is None, "ownerId": b["owner_id"], "syncToken": b["sync_token"],
            "writable": can_write_book(user, b) if user is not None else None,
            "count": b.get("n")}


def books_for(user: dict | None) -> list[dict]:
    if not user:
        return []
    return db.q("SELECT b.*, (SELECT count(*) FROM con_contacts c WHERE c.address_book_id = b.id AND c.deleted = 0) AS n "
                "FROM con_address_books b WHERE b.owner_id IS NULL OR b.owner_id = %s ORDER BY b.owner_id IS NOT NULL, b.name", (user["id"],))


def book(bid: int) -> dict | None:
    return db.one("SELECT * FROM con_address_books WHERE id = %s", (bid,))


def book_by_slug(user: dict, slug: str) -> dict | None:
    for b in books_for(user):
        if b["slug"] == slug:
            return b
    return None


def can_read_book(user: dict | None, b: dict | None) -> bool:
    return bool(user and b) and (b["owner_id"] is None or b["owner_id"] == user["id"])


def can_write_book(user: dict | None, b: dict | None) -> bool:
    if not can_read_book(user, b):
        return False
    if b["owner_id"] == user["id"]:
        return True  # everyone may change their own private book, viewers included
    return user["role"] in ("editor", "admin")


def create_book(owner_id: int | None, name: str, description: str | None = None, color: str | None = None) -> int:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "contacts"
    slug, n = base, 1
    while db.one("SELECT 1 AS x FROM con_address_books WHERE slug = %s AND owner_id <=> %s", (slug, owner_id)):
        n += 1
        slug = f"{base}-{n}"
    return db.ex("INSERT INTO con_address_books (owner_id, slug, name, description, color) VALUES (%s, %s, %s, %s, %s)",
                 (owner_id, slug, name[:128], description, color))


def update_book(bid: int, **f) -> None:
    sets = {k: v for k, v in f.items() if k in ("name", "description", "color")}
    if sets:
        db.ex("UPDATE con_address_books SET " + ", ".join(f"{k} = %s" for k in sets) + ", sync_token = sync_token + 1 WHERE id = %s",
              (*sets.values(), bid))


def delete_book(bid: int) -> None:
    db.ex("DELETE FROM con_address_books WHERE id = %s", (bid,))


def _bump(book_id: int) -> int:
    db.ex("UPDATE con_address_books SET sync_token = sync_token + 1 WHERE id = %s", (book_id,))
    return db.one("SELECT sync_token FROM con_address_books WHERE id = %s", (book_id,))["sync_token"]


# ------------------------------------------------------------------ reading contacts

CHILD = {
    "emails": ("con_contact_emails", ["label", "value", "pref"]),
    "phones": ("con_contact_phones", ["label", "value", "pref"]),
    "addresses": ("con_contact_addresses", ["label", "pobox", "ext", "street", "city", "region", "postcode", "country", "pref"]),
    "urls": ("con_contact_urls", ["label", "value"]),
    "social": ("con_contact_social_profiles", ["service", "value"]),
    "dates": ("con_contact_dates", ["label", "year", "month", "day"]),
}


def _bday(r) -> dict | None:
    """The stored birthday, which can be any part of a date: a year, a year and month, a month and day, or all three."""
    if r.get("bday_year") or r.get("bday_month"):
        return {"year": r.get("bday_year"), "month": r.get("bday_month"), "day": r.get("bday_day")}
    return None


def partial_date(b) -> dict | None:
    """A date with any part unknown, as {year, month, day} with None for what is not known. Allowed: a year, a year and
    a month, a month and a day, or all three. A day without a month, or a month alone, is not a date and is dropped."""
    if not isinstance(b, dict):
        return None
    y, m, d = _int(b.get("year"), 1, 9999), _int(b.get("month"), 1, 12), _int(b.get("day"), 1, 31)
    if not m:
        d = None
    if m and not (d or y):
        m = None
    if not (y or m):
        return None
    return {"year": y, "month": m, "day": d}


def parse_date(s) -> dict | None:
    """Text to a partial date: 1980-05-17, 1980-05, 1980, --05-17 or 05-17 (and the same without dashes: 19800517,
    --0517). None when it is not a date."""
    s = str(s or "").strip().split("T")[0]
    m = re.match(r"^(\d{4})(?:-?(\d{2})(?:-?(\d{2}))?)?$", s)
    if m and not (m.group(2) and not m.group(3) and "-" not in s and len(s) == 6):
        return partial_date({"year": m.group(1), "month": m.group(2), "day": m.group(3)})
    m = re.match(r"^(?:--)?(\d{1,2})-(\d{1,2})$", s) or re.match(r"^--(\d{2})(\d{2})$", s)
    if m:
        return partial_date({"month": m.group(1), "day": m.group(2)})
    return None


def summary(r: dict) -> dict:
    return {"id": r["id"], "bookId": r["address_book_id"], "uid": r["uid"], "kind": r["kind"], "fn": r["fn"],
            "given": r.get("given"), "family": r.get("family"), "nickname": r.get("nickname"), "org": r.get("org"),
            "title": r.get("title"), "favorite": bool(r.get("favorite")), "hasPhoto": bool(r.get("has_photo")),
            "email": r.get("email"), "phone": r.get("phone"), "birthday": _bday(r), "gender": r.get("gender"),
            "iopixPersonId": r.get("iopix_person_id"), "updated": r["updated_at"].isoformat() if r.get("updated_at") else None}


SUMMARY_SQL = ("SELECT c.id, c.address_book_id, c.uid, c.kind, c.fn, c.given, c.family, c.nickname, c.org, c.title, c.favorite, "
               "c.iopix_person_id IS NOT NULL AS has_photo, c.bday_year, c.bday_month, c.bday_day, c.gender, c.iopix_person_id, c.updated_at, "
               "(SELECT e.value FROM con_contact_emails e WHERE e.contact_id = c.id ORDER BY e.pref DESC, e.position LIMIT 1) AS email, "
               "(SELECT p.value FROM con_contact_phones p WHERE p.contact_id = c.id ORDER BY p.pref DESC, p.position LIMIT 1) AS phone "
               "FROM con_contacts c ")


def sort_key_sql(order: str) -> str:
    return {"family": "coalesce(nullif(c.family, ''), c.fn), c.given",
            "updated": "c.updated_at DESC",
            "created": "c.created_at DESC"}.get(order, "coalesce(nullif(c.given, ''), c.fn), c.family")


def search(book_ids: list[int], q: str = "", tag: str | None = None, favorite: bool = False, limit: int = 500,
           offset: int = 0, order: str = "given", iopix: bool | None = None) -> tuple[list[dict], int]:
    if not book_ids:
        return [], 0
    where = [f"c.address_book_id IN ({','.join(['%s'] * len(book_ids))})", "c.deleted = 0"]
    args: list = list(book_ids)
    like_ = f"LIKE %s COLLATE {db.search_collation()}"  # case- and accent-insensitive: "celia" finds "Célia"
    for word in (q or "").split():
        lit = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")  # "50%" or "a_b" mean themselves
        like = f"%{lit}%"
        digits = re.sub(r"\D", "", word)
        where.append((f"(c.fn {like_} OR c.nickname {like_} OR c.org {like_} OR c.title {like_} OR c.notes {like_} "
                      f"OR c.maiden {like_} "
                      f"OR EXISTS (SELECT 1 FROM con_contact_emails e WHERE e.contact_id = c.id AND e.value {like_}) "
                      f"OR EXISTS (SELECT 1 FROM con_contact_tags t WHERE t.contact_id = c.id AND t.tag {like_}) "
                      f"OR EXISTS (SELECT 1 FROM con_contact_addresses a WHERE a.contact_id = c.id AND concat_ws(' ', a.street, a.city, a.region, a.postcode, a.country) {like_})")
                     + (" OR EXISTS (SELECT 1 FROM con_contact_phones p WHERE p.contact_id = c.id AND "
                        "regexp_replace(p.value, '[^0-9]', '') LIKE %s)" if len(digits) >= 3 else "") + ")")
        args += [like] * 9 + ([f"%{digits}%"] if len(digits) >= 3 else [])
    if tag:
        where.append("EXISTS (SELECT 1 FROM con_contact_tags t WHERE t.contact_id = c.id AND t.tag = %s)")
        args.append(tag)
    if favorite:
        where.append("c.favorite = 1")
    if iopix is True:
        where.append("c.iopix_person_id IS NOT NULL")
    w = " AND ".join(where)
    total = db.one(f"SELECT count(*) AS n FROM con_contacts c WHERE {w}", args)["n"]
    rows = db.q(f"{SUMMARY_SQL} WHERE {w} ORDER BY {sort_key_sql(order)} LIMIT %s OFFSET %s", (*args, limit, offset))
    return [summary(r) for r in rows], total


def get_row(cid: int) -> dict | None:
    return db.one("SELECT * FROM con_contacts WHERE id = %s", (cid,))


def by_href(book_id: int, href: str) -> dict | None:
    return db.one("SELECT * FROM con_contacts WHERE address_book_id = %s AND href = %s", (book_id, href))


def by_uid(book_id: int, uid: str) -> dict | None:
    return db.one("SELECT * FROM con_contacts WHERE address_book_id = %s AND uid = %s AND deleted = 0", (book_id, uid))


def full(cid: int | dict, with_photo: bool = False) -> dict | None:
    r = get_row(cid) if isinstance(cid, int) else cid
    if not r or r["deleted"]:
        return None
    c = {"id": r["id"], "bookId": r["address_book_id"], "uid": r["uid"], "href": r["href"], "kind": r["kind"], "fn": r["fn"],
         "name": {k: r[k] or "" for k in ("prefix", "given", "additional", "family", "suffix")},
         "nickname": r["nickname"], "maiden": r["maiden"], "phoneticGiven": r["phonetic_given"],
         "phoneticFamily": r["phonetic_family"], "gender": r["gender"], "birthday": _bday(r),
         "birthdayRemind": bool(r.get("bday_remind", 1)), "org": r["org"],
         "department": r["department"], "title": r["title"], "role": r["role"], "notes": r["notes"],
         "favorite": bool(r["favorite"]), "hasPhoto": r["iopix_person_id"] is not None, "etag": r["etag"],
         "iopix": {"personId": r["iopix_person_id"], "name": r["iopix_person_name"]} if r["iopix_person_id"] else None,
         "extra": json.loads(r["extra"]) if r["extra"] else [],
         "created": r["created_at"].isoformat() if r["created_at"] else None,
         "updated": r["updated_at"].strftime("%Y-%m-%dT%H:%M:%SZ") if r["updated_at"] else None}
    for key, (table, cols) in CHILD.items():
        c[key] = [{k: x[k] for k in cols} for x in db.q(f"SELECT * FROM {table} WHERE contact_id = %s ORDER BY position, id", (r["id"],))]
        for x in c[key]:
            if "pref" in x:
                x["pref"] = int(x["pref"] or 0)
    c["tags"] = [x["tag"] for x in db.q("SELECT tag FROM con_contact_tags WHERE contact_id = %s ORDER BY tag", (r["id"],))]
    rels = db.q("SELECT r.*, o.fn AS o_fn, o.uid AS o_uid, o.gender AS o_gender, o.address_book_id AS o_book, o.deleted AS o_del, o.iopix_person_id IS NOT NULL AS o_photo, o.iopix_person_id AS o_iopix "
                "FROM con_contact_relations r LEFT JOIN con_contacts o ON o.id = r.related_id WHERE r.contact_id = %s ORDER BY r.position, r.id", (r["id"],))
    c["relations"] = [{"type": x["type"], "relatedId": x["related_id"] if x["related_id"] and not x["o_del"] else None,
                       "relatedName": x["related_name"], "relatedFn": x["o_fn"], "relatedUid": x["o_uid"],
                       "relatedGender": x["o_gender"], "relatedBookId": x["o_book"], "relatedHasPhoto": bool(x["o_photo"]),
                       "relatedIopixPersonId": x["o_iopix"] if not x["o_del"] else None, "label": x["label"],
                       "typeLabel": x["label"] or rel.label(x["type"], x["o_gender"])} for x in rels]
    if with_photo and r["iopix_person_id"]:
        got = iopix.photo(r["iopix_person_id"])
        if got:
            c["photoData"] = {"type": got[1], "data": got[0]}
    return c


def photo(cid: int) -> tuple[bytes, str] | None:
    """A contact's photo: the face of the ioPix person it is linked to. Contacts keep no photo of their own."""
    r = db.one("SELECT iopix_person_id FROM con_contacts WHERE id = %s AND deleted = 0", (cid,))
    return iopix.photo(r["iopix_person_id"]) if r else None


def vcard_text(cid: int | dict, version: str = "3.0") -> str:
    c = full(cid, with_photo=True)
    return vcard.from_contact(c, version)


# ------------------------------------------------------------------ saving

def _clean(s, n=255):
    if s is None:
        return None
    s = str(s).strip()
    return s[:n] if s else None


def _int(v, lo, hi):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


def display_name(c: dict) -> str:
    if (c.get("fn") or "").strip():
        return c["fn"].strip()
    nm = c.get("name") or {}
    s = " ".join(x for x in (nm.get("prefix"), nm.get("given"), nm.get("additional"), nm.get("family"), nm.get("suffix")) if x)
    return s or c.get("org") or next((e["value"] for e in c.get("emails") or [] if e.get("value")), "") or "Unnamed"


def validate(c: dict) -> dict:
    """Normalise a contact dict from the API, vCard or CSV."""
    nm = c.get("name") or {}
    out = dict(c)
    out["name"] = {k: _clean(nm.get(k), 128 if k in ("given", "additional", "family") else 64) or "" for k in ("prefix", "given", "additional", "family", "suffix")}
    # a name typed into fn alone (from the web form's single box or a CSV with only "Name") is split for N
    if not any(out["name"].values()) and (c.get("fn") or "").strip() and c.get("kind", "individual") == "individual":
        parts = c["fn"].strip().split()
        out["name"]["given"] = parts[0][:128]
        out["name"]["family"] = " ".join(parts[1:])[:128]
    out["fn"] = display_name({**c, "name": out["name"]})[:255]
    out["kind"] = c.get("kind") if c.get("kind") in ("individual", "org", "group") else "individual"
    out["gender"] = (c.get("gender") or "").upper()[:1] or None
    if out["gender"] not in (None, "M", "F", "O", "N", "U"):
        out["gender"] = None
    out["birthday"] = partial_date(c.get("birthday"))
    # remind: whether the birthday goes into the birthday feeds; None (not given, as from a vCard) keeps what was there
    rem = c.get("birthdayRemind")
    out["birthdayRemind"] = None if rem is None else rem not in (False, 0, "0", "false", "no", "off")
    out["dates"] = [{"label": _clean(d.get("label"), 64) or "other", "year": _int(d.get("year"), 1, 9999),
                     "month": int(d["month"]), "day": int(d["day"])}
                    for d in c.get("dates") or [] if _int(d.get("month"), 1, 12) and _int(d.get("day"), 1, 31)]
    out["emails"] = [{"label": _clean(e.get("label"), 64), "value": _clean(e.get("value")), "pref": 1 if e.get("pref") else 0}
                     for e in c.get("emails") or [] if _clean(e.get("value"))]
    out["phones"] = [{"label": _clean(e.get("label"), 64), "value": _clean(e.get("value"), 64), "pref": 1 if e.get("pref") else 0}
                     for e in c.get("phones") or [] if _clean(e.get("value"), 64)]
    out["addresses"] = [{"label": _clean(a.get("label"), 64), **{k: _clean(a.get(k), 255 if k == "street" else 128) for k in
                                                                ("pobox", "ext", "street", "city", "region", "postcode", "country")},
                         "pref": 1 if a.get("pref") else 0}
                        for a in c.get("addresses") or [] if any(_clean(a.get(k)) for k in ("pobox", "ext", "street", "city", "region", "postcode", "country"))]
    out["urls"] = [{"label": _clean(u.get("label"), 64), "value": _clean(u.get("value"), 512)} for u in c.get("urls") or [] if _clean(u.get("value"), 512)]
    out["social"] = [{"service": (s.get("service") or "other").lower()[:64], "value": _clean(s.get("value"), 512)}
                     for s in c.get("social") or [] if _clean(s.get("value"), 512)]
    out["tags"] = sorted({t.strip()[:128] for t in c.get("tags") or [] if t and t.strip()})
    out["relations"] = [r for r in c.get("relations") or [] if r.get("type") and (r.get("relatedId") or r.get("relatedUid") or _clean(r.get("relatedName")))]
    for k, n in (("nickname", 128), ("maiden", 128), ("phoneticGiven", 128), ("phoneticFamily", 128), ("org", 255),
                 ("department", 255), ("title", 255), ("role", 255)):
        out[k] = _clean(c.get(k), n)
    out["notes"] = (c.get("notes") or "").strip() or None
    return out


def _etag(cid: int) -> str:
    return hashlib.sha1(f"{cid}-{time.time_ns()}-{uuidlib.uuid4()}".encode()).hexdigest()[:20]


def save(book_id: int, data: dict, cid: int | None = None, href: str | None = None,
         resolve_book_ids: list[int] | None = None) -> int:
    """Create or replace a contact. `data` is a contact dict (API, vCard or CSV); relations may name the other contact by
    relatedId, relatedUid or relatedName (looked up by name in `resolve_book_ids`). Returns the id. A photo in `data`
    (a vCard's PHOTO, say) is not kept: the linked ioPix person is a contact's only photo."""
    c = validate(data)
    with db.tx():
        prev = get_row(cid) if cid else None
        if prev and prev["address_book_id"] != book_id:
            move(cid, book_id)
            prev = get_row(cid)
        uid = (prev["uid"] if prev else None) or c.get("uid") or str(uuidlib.uuid4())
        if not prev and c.get("uid"):
            uid = c["uid"]
        token = _bump(book_id)
        nm, b = c["name"], c["birthday"] or {}
        cols = {"kind": c["kind"], "fn": c["fn"], "prefix": nm["prefix"] or None, "given": nm["given"] or None,
                "additional": nm["additional"] or None, "family": nm["family"] or None, "suffix": nm["suffix"] or None,
                "nickname": c["nickname"], "maiden": c["maiden"], "phonetic_given": c["phoneticGiven"],
                "phonetic_family": c["phoneticFamily"], "gender": c["gender"], "bday_year": b.get("year"),
                "bday_month": b.get("month"), "bday_day": b.get("day"), "org": c["org"], "department": c["department"],
                "title": c["title"], "role": c["role"], "notes": c["notes"], "favorite": 1 if c.get("favorite") else 0,
                "extra": json.dumps(c.get("extra") or []) if c.get("extra") else None}
        if c["birthdayRemind"] is not None or not prev:
            cols["bday_remind"] = 0 if c["birthdayRemind"] is False else 1
        if "iopix" in data:
            ip = data.get("iopix") or {}
            cols["iopix_person_id"] = _int(ip.get("personId"), 1, 2 ** 31 - 1)
            cols["iopix_person_name"] = _clean(ip.get("name")) if cols["iopix_person_id"] else None
        if prev:
            cols.update({"etag": _etag(prev["id"]), "changed_token": token, "uid": uid})
            db.ex("UPDATE con_contacts SET " + ", ".join(f"{k} = %s" for k in cols) + " WHERE id = %s", (*cols.values(), prev["id"]))
            cid = prev["id"]
        else:
            href = href or f"{re.sub(r'[^A-Za-z0-9._-]', '-', uid)}.vcf"
            old = by_href(book_id, href)
            if old:  # a tombstone with this name: reuse the row
                cid = old["id"]
                cols.update({"etag": _etag(cid), "changed_token": token, "uid": uid, "deleted": 0})
                db.ex("UPDATE con_contacts SET " + ", ".join(f"{k} = %s" for k in cols) + " WHERE id = %s", (*cols.values(), cid))
            else:
                cols.update({"address_book_id": book_id, "uid": uid, "href": href, "etag": "new", "changed_token": token})
                cid = db.ex("INSERT INTO con_contacts (" + ", ".join(cols) + ") VALUES (" + ", ".join(["%s"] * len(cols)) + ")",
                            tuple(cols.values()))
                db.ex("UPDATE con_contacts SET etag = %s WHERE id = %s", (_etag(cid), cid))
        for key, (table, fields) in CHILD.items():
            db.ex(f"DELETE FROM {table} WHERE contact_id = %s", (cid,))
            db.many(f"INSERT INTO {table} (contact_id, position, {', '.join(fields)}) VALUES (%s, %s, {', '.join(['%s'] * len(fields))})",
                    [(cid, i, *(x.get(f) for f in fields)) for i, x in enumerate(c[key])])
        db.ex("DELETE FROM con_contact_tags WHERE contact_id = %s", (cid,))
        db.many("INSERT IGNORE INTO con_contact_tags (contact_id, tag) VALUES (%s, %s)", [(cid, t) for t in c["tags"]])
        _save_relations(cid, c["relations"], resolve_book_ids or [book_id])
    return cid


def _resolve(r: dict, book_ids: list[int], self_id: int) -> int | None:
    if r.get("relatedId"):
        row = get_row(int(r["relatedId"]))
        return row["id"] if row and not row["deleted"] and row["address_book_id"] in book_ids and row["id"] != self_id else None
    marks = ",".join(["%s"] * len(book_ids))
    if r.get("relatedUid"):
        row = db.one(f"SELECT id FROM con_contacts WHERE uid = %s AND address_book_id IN ({marks}) AND deleted = 0 AND id <> %s LIMIT 1",
                     (r["relatedUid"], *book_ids, self_id))
        if row:
            return row["id"]
    name = (r.get("relatedName") or "").strip()
    if name:
        rows = db.q(f"SELECT id FROM con_contacts WHERE fn = %s AND address_book_id IN ({marks}) AND deleted = 0 AND id <> %s LIMIT 2",
                    (name, *book_ids, self_id))
        if len(rows) == 1:  # only when the name is unambiguous
            return rows[0]["id"]
    return None


def _touch(cid: int) -> None:
    row = get_row(cid)
    if row and not row["deleted"]:
        tok = _bump(row["address_book_id"])
        db.ex("UPDATE con_contacts SET etag = %s, changed_token = %s, updated_at = NOW() WHERE id = %s", (_etag(cid), tok, cid))


def _save_relations(cid: int, rels: list[dict], book_ids: list[int]) -> None:
    me = get_row(cid)
    old = {(x["related_id"], x["type"]) for x in db.q("SELECT related_id, type FROM con_contact_relations WHERE contact_id = %s AND related_id IS NOT NULL", (cid,))}
    db.ex("DELETE FROM con_contact_relations WHERE contact_id = %s", (cid,))
    new, rows, seen = set(), [], set()
    for i, r in enumerate(rels):
        t = r["type"] if r["type"] in rel.TYPES else "other"
        rid = _resolve(r, book_ids, cid)
        key = (rid, t) if rid else (None, t, (r.get("relatedName") or "").strip().lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append((cid, i, t, rid, None if rid else _clean(r.get("relatedName")), _clean(r.get("label"), 64)))
        if rid:
            new.add((rid, t))
            g = r.get("gender")  # "Brother" picked: the related person is a man, if nobody said otherwise
            if g in ("M", "F"):
                db.ex("UPDATE con_contacts SET gender = %s WHERE id = %s AND gender IS NULL", (g, rid))
    db.many("INSERT INTO con_contact_relations (contact_id, position, type, related_id, related_name, label) VALUES (%s, %s, %s, %s, %s, %s)", rows)
    touched = set()
    for rid, t in old - new:
        inv = rel.inverse(t)
        if inv:
            n = db.ex("DELETE FROM con_contact_relations WHERE contact_id = %s AND related_id = %s AND type = %s LIMIT 1", (rid, cid, inv))
            if n:
                touched.add(rid)
    for rid, t in new - old:
        inv = rel.inverse(t)
        if inv and not db.one("SELECT 1 AS x FROM con_contact_relations WHERE contact_id = %s AND related_id = %s AND type = %s", (rid, cid, inv)):
            pos = (db.one("SELECT coalesce(max(position), -1) + 1 AS p FROM con_contact_relations WHERE contact_id = %s", (rid,)) or {"p": 0})["p"]
            db.ex("INSERT INTO con_contact_relations (contact_id, position, type, related_id) VALUES (%s, %s, %s, %s)", (rid, pos, inv, cid))
            touched.add(rid)
    # a relation to a name that now matches this contact (imported before it existed) is linked up
    if me and me["fn"]:
        for x in db.q("SELECT r.id, r.contact_id FROM con_contact_relations r JOIN con_contacts o ON o.id = r.contact_id "
                      "WHERE r.related_id IS NULL AND r.related_name = %s AND o.address_book_id = %s AND o.id <> %s", (me["fn"], me["address_book_id"], cid)):
            db.ex("UPDATE con_contact_relations SET related_id = %s, related_name = NULL WHERE id = %s", (cid, x["id"]))
            touched.add(x["contact_id"])
    for rid in touched:
        _touch(rid)


def set_fields(cid: int, **cols) -> None:
    row = get_row(cid)
    tok = _bump(row["address_book_id"])
    db.ex("UPDATE con_contacts SET " + ", ".join(f"{k} = %s" for k in cols) + ", etag = %s, changed_token = %s WHERE id = %s",
          (*cols.values(), _etag(cid), tok, cid))


def delete(cid: int) -> None:
    with db.tx():
        row = get_row(cid)
        if not row or row["deleted"]:
            return
        others = [x["contact_id"] for x in db.q("SELECT DISTINCT contact_id FROM con_contact_relations WHERE related_id = %s", (cid,))]
        db.ex("DELETE FROM con_contact_relations WHERE related_id = %s OR contact_id = %s", (cid, cid))
        for table, _ in CHILD.values():
            db.ex(f"DELETE FROM {table} WHERE contact_id = %s", (cid,))
        db.ex("DELETE FROM con_contact_tags WHERE contact_id = %s", (cid,))
        tok = _bump(row["address_book_id"])
        db.ex("UPDATE con_contacts SET deleted = 1, photo = NULL, notes = NULL, extra = NULL, etag = %s, changed_token = %s, "
              "iopix_person_id = NULL WHERE id = %s", (_etag(cid), tok, cid))
        from app import users
        users.forget_me_contact(cid)  # whoever had this card as "me"
        for o in others:
            _touch(o)


def move(cid: int, new_book: int) -> None:
    """To another address book: the contact keeps its id (and relations); the old book gets a tombstone."""
    with db.tx():
        row = get_row(cid)
        if row["address_book_id"] == new_book:
            return
        tok_old = _bump(row["address_book_id"])
        db.ex("INSERT INTO con_contacts (address_book_id, uid, href, fn, etag, changed_token, deleted) VALUES (%s, %s, %s, '', %s, %s, 1) "
              "ON DUPLICATE KEY UPDATE deleted = 1, changed_token = VALUES(changed_token), etag = VALUES(etag)",
              (row["address_book_id"], row["uid"], row["href"], _etag(cid), tok_old))
        href = row["href"]
        if by_href(new_book, href):
            href = f"{uuidlib.uuid4()}.vcf"
        tok = _bump(new_book)
        db.ex("UPDATE con_contacts SET address_book_id = %s, href = %s, etag = %s, changed_token = %s WHERE id = %s",
              (new_book, href, _etag(cid), tok, cid))


def all_tags(book_ids: list[int]) -> list[dict]:
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    return db.q(f"SELECT t.tag, count(*) AS n FROM con_contact_tags t JOIN con_contacts c ON c.id = t.contact_id "
                f"WHERE c.address_book_id IN ({marks}) AND c.deleted = 0 GROUP BY t.tag ORDER BY t.tag", book_ids)


def upcoming(book_ids: list[int], days: int = 30) -> list[dict]:
    """Birthdays and other dates in the next `days` days, soonest first. Every birthday is listed; `remind` says
    whether it goes in the birthday calendar feed (the only thing "Remind me" decides). None for other dates."""
    import datetime as dt
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    today = dt.date.today()
    out = []
    rows = db.q(f"SELECT c.id, c.fn, c.bday_year AS year, c.bday_month AS month, c.bday_day AS day, 'birthday' AS label, "
                f"c.iopix_person_id IS NOT NULL AS has_photo, c.iopix_person_id, c.bday_remind AS remind FROM con_contacts c WHERE c.address_book_id IN ({marks}) AND c.deleted = 0 "
                f"AND c.bday_day IS NOT NULL UNION ALL SELECT c.id, c.fn, d.year, d.month, d.day, d.label, c.iopix_person_id IS NOT NULL, c.iopix_person_id, NULL FROM con_contact_dates d "
                f"JOIN con_contacts c ON c.id = d.contact_id WHERE c.address_book_id IN ({marks}) AND c.deleted = 0", (*book_ids, *book_ids))
    for r in rows:
        for yr in (today.year, today.year + 1):
            try:
                d = dt.date(yr, r["month"], r["day"])
            except ValueError:  # 29 February in a common year
                d = dt.date(yr, 3, 1)
            if d >= today:
                break
        delta = (d - today).days
        if delta <= days:
            out.append({"contactId": r["id"], "fn": r["fn"], "label": r["label"], "date": d.isoformat(), "inDays": delta,
                        "turns": (d.year - r["year"]) if r["year"] else None, "hasPhoto": bool(r["has_photo"]),
                        "iopixPersonId": r["iopix_person_id"], "remind": None if r["remind"] is None else bool(r["remind"])})
    return sorted(out, key=lambda x: (x["inDays"], x["fn"]))


def find_duplicates(book_ids: list[int]) -> list[list[dict]]:
    """Contacts that share a name, an email or a phone number (digits only)."""
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    groups: dict = {}
    for r in db.q(f"SELECT id, lower(fn) AS k FROM con_contacts WHERE address_book_id IN ({marks}) AND deleted = 0 AND fn <> ''", book_ids):
        groups.setdefault(("n", r["k"]), set()).add(r["id"])
    for r in db.q(f"SELECT c.id, lower(e.value) AS k FROM con_contact_emails e JOIN con_contacts c ON c.id = e.contact_id "
                  f"WHERE c.address_book_id IN ({marks}) AND c.deleted = 0", book_ids):
        groups.setdefault(("e", r["k"]), set()).add(r["id"])
    for r in db.q(f"SELECT c.id, right(regexp_replace(p.value, '[^0-9]', ''), 9) AS k FROM con_contact_phones p "
                  f"JOIN con_contacts c ON c.id = p.contact_id WHERE c.address_book_id IN ({marks}) AND c.deleted = 0", book_ids):
        if r["k"] and len(r["k"]) >= 7:
            groups.setdefault(("p", r["k"]), set()).add(r["id"])
    # merge overlapping groups
    sets: list[set] = []
    for ids in groups.values():
        if len(ids) < 2:
            continue
        hit = [s for s in sets if s & ids]
        merged = set(ids).union(*hit) if hit else set(ids)
        sets = [s for s in sets if s not in hit] + [merged]
    out = []
    for s in sets:
        rows = db.q(f"{SUMMARY_SQL} WHERE c.id IN ({','.join(['%s'] * len(s))}) ORDER BY c.id", list(s))
        out.append([summary(r) for r in rows])
    return out


def combine(keep: dict, others: list[dict]) -> dict:
    """What merging gives, without saving: `keep` (a full() dict) with the others' emails, phones,
    addresses, urls, social profiles, dates, labels and relations added when missing, and its empty fields filled."""
    keep = {**keep, "name": dict(keep["name"]), "tags": list(keep["tags"]), "relations": list(keep["relations"]),
            **{k: list(keep[k]) for k in CHILD}}
    ids = {keep["id"], *(o["id"] for o in others)}
    keep["relations"] = [r for r in keep["relations"] if r.get("relatedId") not in ids]
    for o in others:
        for key, (_t, cols) in CHILD.items():
            have = {_child_key(key, x, cols) for x in keep[key]}
            for x in o[key]:
                k = _child_key(key, x, cols)
                if k not in have:
                    keep[key].append(x)
                    have.add(k)
        keep["tags"] = sorted(set(keep["tags"]) | set(o["tags"]))
        for f in ("nickname", "maiden", "gender", "org", "department", "title", "role", "birthday", "phoneticGiven", "phoneticFamily"):
            if not keep.get(f) and o.get(f):
                keep[f] = o[f]
                if f == "birthday":
                    keep["birthdayRemind"] = o.get("birthdayRemind", True)
        for k in ("prefix", "given", "additional", "family", "suffix"):
            if not keep["name"].get(k) and o["name"].get(k):
                keep["name"][k] = o["name"][k]
        if o.get("notes") and o["notes"] not in (keep.get("notes") or ""):
            keep["notes"] = ((keep.get("notes") or "") + "\n\n" + o["notes"]).strip()
        if not keep.get("iopix") and o.get("iopix"):
            keep["iopix"] = o["iopix"]
        seen = {(r["type"], r.get("relatedId") or (r.get("relatedName") or "").lower()) for r in keep["relations"]}
        for r in o["relations"]:
            k = (r["type"], r.get("relatedId") or (r.get("relatedName") or "").lower())
            if r.get("relatedId") not in ids and k not in seen:
                keep["relations"].append(r)
                seen.add(k)
        keep["favorite"] = keep["favorite"] or o["favorite"]
    return keep


def _child_key(key: str, x: dict, cols: list) -> tuple:
    if key == "phones":
        return (re.sub(r"\D", "", x.get("value") or "")[-8:],)
    return tuple(str(x.get(k) or "").strip().lower() for k in cols if k not in ("pref", "label"))


def merge(keep_id: int, other_ids: list[int], result: dict | None = None) -> None:
    """Fold other contacts into one: `result` (the contact as it should end up, e.g. chosen field by field) or what
    combine() gives. Relations from elsewhere that point at the others move to the kept one; then the others are deleted."""
    keep = full(keep_id)
    others = [o for o in (full(x) for x in other_ids if x != keep_id) if o]
    data = result if result is not None else combine(keep, others)
    with db.tx():
        for o in others:
            db.ex("UPDATE con_contact_relations SET related_id = %s WHERE related_id = %s AND contact_id NOT IN (%s, %s)", (keep_id, o["id"], keep_id, o["id"]))
        save(keep["bookId"], data, cid=keep_id)
        for o in others:
            db.ex("DELETE FROM con_contact_relations WHERE (contact_id = %s AND related_id = %s) OR (contact_id = %s AND related_id = %s)",
                  (o["id"], keep_id, keep_id, o["id"]))
            delete(o["id"])


# ------------------------------------------------------------------ implied relations

_KIN = sorted({t for pair in rel.COMPOSE for t in pair} | {rel.inverse(t) for pair in rel.COMPOSE for t in pair} - {None})


def implied_relations(cid: int, book_ids: list[int], depth: int = 4) -> list[dict]:
    """Relations the contact's family implies (her sibling's parent is her parent, her parent's sibling her aunt...)
    but nobody entered, worked out from the stated ones among contacts in `book_ids`. Never stored."""
    allowed = set(book_ids)
    seen, frontier, edges = {cid}, [cid], []
    kin = ",".join(["%s"] * len(_KIN))
    for _ in range(depth):
        if not frontier:
            break
        marks = ",".join(["%s"] * len(frontier))
        rows = db.q(f"SELECT r.contact_id, r.related_id, r.type, o.address_book_id FROM con_contact_relations r JOIN con_contacts o ON o.id = r.related_id "
                    f"WHERE r.contact_id IN ({marks}) AND o.deleted = 0 AND r.type IN ({kin})", frontier + _KIN)
        nxt = []
        for r in rows:
            if r["address_book_id"] not in allowed:
                continue
            edges.append((r["contact_id"], r["type"], r["related_id"]))
            if r["related_id"] not in seen:
                seen.add(r["related_id"])
                nxt.append(r["related_id"])
        frontier = nxt
    # every relation of the root counts, also non-family ones: a stated "friend" is not overridden by a guess
    edges += [(cid, x["type"], x["related_id"]) for x in db.q("SELECT type, related_id FROM con_contact_relations WHERE contact_id = %s AND related_id IS NOT NULL", (cid,))]
    edges += [(x["contact_id"], x["type"], cid) for x in db.q("SELECT type, contact_id FROM con_contact_relations WHERE related_id = %s", (cid,))]
    found = rel.infer(edges, cid)
    if not found:
        return []
    ids = list({f["relatedId"] for f in found} | {f["viaId"] for f in found})
    marks = ",".join(["%s"] * len(ids))
    info = {r["id"]: r for r in db.q(f"SELECT id, fn, gender, iopix_person_id IS NOT NULL AS hp, iopix_person_id FROM con_contacts WHERE id IN ({marks}) AND deleted = 0", ids)}
    order = {t: i for i, t in enumerate(rel.TYPES)}
    out = []
    for f in sorted(found, key=lambda f: (order.get(f["type"], 99), (info.get(f["relatedId"]) or {}).get("fn") or "")):
        o, v = info.get(f["relatedId"]), info.get(f["viaId"])
        if not o or not v:
            continue
        out.append({"type": f["type"], "relatedId": o["id"], "relatedFn": o["fn"], "relatedGender": o["gender"],
                    "relatedHasPhoto": bool(o["hp"]), "relatedIopixPersonId": o["iopix_person_id"],
                    "typeLabel": rel.label(f["type"], o["gender"]), "implied": True,
                    "viaId": v["id"], "viaFn": v["fn"], "viaLabel": rel.label(f["viaType"], v["gender"])})
    return out
