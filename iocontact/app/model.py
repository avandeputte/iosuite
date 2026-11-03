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

from app import db, relations as rel, vcard

# ------------------------------------------------------------------ address books


def book_public(b: dict, user: dict | None = None) -> dict:
    return {"id": b["id"], "slug": b["slug"], "name": b["name"], "description": b.get("description"), "color": b.get("color"),
            "shared": b["owner_id"] is None, "ownerId": b["owner_id"], "syncToken": b["sync_token"],
            "writable": can_write_book(user, b) if user is not None else None,
            "count": b.get("n")}


def books_for(user: dict | None) -> list[dict]:
    if not user:
        return []
    return db.q("SELECT b.*, (SELECT count(*) FROM contacts c WHERE c.book_id = b.id AND c.deleted = 0) AS n "
                "FROM addressbooks b WHERE b.owner_id IS NULL OR b.owner_id = %s ORDER BY b.owner_id IS NOT NULL, b.name", (user["id"],))


def book(bid: int) -> dict | None:
    return db.one("SELECT * FROM addressbooks WHERE id = %s", (bid,))


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
    while db.one("SELECT 1 AS x FROM addressbooks WHERE slug = %s AND owner_id <=> %s", (slug, owner_id)):
        n += 1
        slug = f"{base}-{n}"
    return db.ex("INSERT INTO addressbooks (owner_id, slug, name, description, color) VALUES (%s, %s, %s, %s, %s)",
                 (owner_id, slug, name[:128], description, color))


def update_book(bid: int, **f) -> None:
    sets = {k: v for k, v in f.items() if k in ("name", "description", "color")}
    if sets:
        db.ex("UPDATE addressbooks SET " + ", ".join(f"{k} = %s" for k in sets) + ", sync_token = sync_token + 1 WHERE id = %s",
              (*sets.values(), bid))


def delete_book(bid: int) -> None:
    db.ex("DELETE FROM addressbooks WHERE id = %s", (bid,))


def _bump(book_id: int) -> int:
    db.ex("UPDATE addressbooks SET sync_token = sync_token + 1 WHERE id = %s", (book_id,))
    return db.one("SELECT sync_token FROM addressbooks WHERE id = %s", (book_id,))["sync_token"]


# ------------------------------------------------------------------ reading contacts

CHILD = {
    "emails": ("contact_emails", ["label", "value", "pref"]),
    "phones": ("contact_phones", ["label", "value", "pref"]),
    "addresses": ("contact_addresses", ["label", "pobox", "ext", "street", "city", "region", "postcode", "country", "pref"]),
    "urls": ("contact_urls", ["label", "value"]),
    "social": ("contact_social", ["service", "value"]),
    "dates": ("contact_dates", ["label", "year", "month", "day"]),
}


def _bday(r) -> dict | None:
    if r.get("bday_month") and r.get("bday_day"):
        return {"year": r.get("bday_year"), "month": r["bday_month"], "day": r["bday_day"]}
    return None


def summary(r: dict) -> dict:
    return {"id": r["id"], "bookId": r["book_id"], "uid": r["uid"], "kind": r["kind"], "fn": r["fn"],
            "given": r.get("given"), "family": r.get("family"), "nickname": r.get("nickname"), "org": r.get("org"),
            "title": r.get("title"), "favorite": bool(r.get("favorite")), "hasPhoto": bool(r.get("has_photo")),
            "email": r.get("email"), "phone": r.get("phone"), "birthday": _bday(r), "gender": r.get("gender"),
            "iopixPersonId": r.get("iopix_person_id"), "updated": r["updated"].isoformat() if r.get("updated") else None}


SUMMARY_SQL = ("SELECT c.id, c.book_id, c.uid, c.kind, c.fn, c.given, c.family, c.nickname, c.org, c.title, c.favorite, "
               "c.photo IS NOT NULL AS has_photo, c.bday_year, c.bday_month, c.bday_day, c.gender, c.iopix_person_id, c.updated, "
               "(SELECT e.value FROM contact_emails e WHERE e.contact_id = c.id ORDER BY e.pref DESC, e.pos LIMIT 1) AS email, "
               "(SELECT p.value FROM contact_phones p WHERE p.contact_id = c.id ORDER BY p.pref DESC, p.pos LIMIT 1) AS phone "
               "FROM contacts c ")


def sort_key_sql(order: str) -> str:
    return {"family": "coalesce(nullif(c.family, ''), c.fn), c.given",
            "updated": "c.updated DESC",
            "created": "c.created DESC"}.get(order, "coalesce(nullif(c.given, ''), c.fn), c.family")


def search(book_ids: list[int], q: str = "", tag: str | None = None, favorite: bool = False, limit: int = 500,
           offset: int = 0, order: str = "given", iopix: bool | None = None) -> tuple[list[dict], int]:
    if not book_ids:
        return [], 0
    where = [f"c.book_id IN ({','.join(['%s'] * len(book_ids))})", "c.deleted = 0"]
    args: list = list(book_ids)
    for word in (q or "").split():
        like = f"%{word}%"
        digits = re.sub(r"\D", "", word)
        where.append("(c.fn LIKE %s OR c.nickname LIKE %s OR c.org LIKE %s OR c.title LIKE %s OR c.notes LIKE %s "
                     "OR c.maiden LIKE %s "
                     "OR EXISTS (SELECT 1 FROM contact_emails e WHERE e.contact_id = c.id AND e.value LIKE %s) "
                     "OR EXISTS (SELECT 1 FROM contact_tags t WHERE t.contact_id = c.id AND t.tag LIKE %s) "
                     "OR EXISTS (SELECT 1 FROM contact_addresses a WHERE a.contact_id = c.id AND concat_ws(' ', a.street, a.city, a.region, a.postcode, a.country) LIKE %s)"
                     + (" OR EXISTS (SELECT 1 FROM contact_phones p WHERE p.contact_id = c.id AND "
                        "regexp_replace(p.value, '[^0-9]', '') LIKE %s)" if len(digits) >= 3 else "") + ")")
        args += [like] * 9 + ([f"%{digits}%"] if len(digits) >= 3 else [])
    if tag:
        where.append("EXISTS (SELECT 1 FROM contact_tags t WHERE t.contact_id = c.id AND t.tag = %s)")
        args.append(tag)
    if favorite:
        where.append("c.favorite = 1")
    if iopix is True:
        where.append("c.iopix_person_id IS NOT NULL")
    w = " AND ".join(where)
    total = db.one(f"SELECT count(*) AS n FROM contacts c WHERE {w}", args)["n"]
    rows = db.q(f"{SUMMARY_SQL} WHERE {w} ORDER BY {sort_key_sql(order)} LIMIT %s OFFSET %s", (*args, limit, offset))
    return [summary(r) for r in rows], total


def get_row(cid: int) -> dict | None:
    return db.one("SELECT * FROM contacts WHERE id = %s", (cid,))


def by_href(book_id: int, href: str) -> dict | None:
    return db.one("SELECT * FROM contacts WHERE book_id = %s AND href = %s", (book_id, href))


def by_uid(book_id: int, uid: str) -> dict | None:
    return db.one("SELECT * FROM contacts WHERE book_id = %s AND uid = %s AND deleted = 0", (book_id, uid))


def full(cid: int | dict, with_photo: bool = False) -> dict | None:
    r = get_row(cid) if isinstance(cid, int) else cid
    if not r or r["deleted"]:
        return None
    c = {"id": r["id"], "bookId": r["book_id"], "uid": r["uid"], "href": r["href"], "kind": r["kind"], "fn": r["fn"],
         "name": {k: r[k] or "" for k in ("prefix", "given", "additional", "family", "suffix")},
         "nickname": r["nickname"], "maiden": r["maiden"], "phoneticGiven": r["phonetic_given"],
         "phoneticFamily": r["phonetic_family"], "gender": r["gender"], "birthday": _bday(r), "org": r["org"],
         "department": r["department"], "title": r["title"], "role": r["role"], "notes": r["notes"],
         "favorite": bool(r["favorite"]), "hasPhoto": r["photo"] is not None, "etag": r["etag"],
         "iopix": {"personId": r["iopix_person_id"], "name": r["iopix_person_name"]} if r["iopix_person_id"] else None,
         "extra": json.loads(r["extra"]) if r["extra"] else [],
         "created": r["created"].isoformat() if r["created"] else None,
         "updated": r["updated"].strftime("%Y-%m-%dT%H:%M:%SZ") if r["updated"] else None}
    for key, (table, cols) in CHILD.items():
        c[key] = [{k: x[k] for k in cols} for x in db.q(f"SELECT * FROM {table} WHERE contact_id = %s ORDER BY pos, id", (r["id"],))]
        for x in c[key]:
            if "pref" in x:
                x["pref"] = int(x["pref"] or 0)
    c["tags"] = [x["tag"] for x in db.q("SELECT tag FROM contact_tags WHERE contact_id = %s ORDER BY tag", (r["id"],))]
    rels = db.q("SELECT r.*, o.fn AS o_fn, o.uid AS o_uid, o.gender AS o_gender, o.book_id AS o_book, o.deleted AS o_del, o.photo IS NOT NULL AS o_photo "
                "FROM relations r LEFT JOIN contacts o ON o.id = r.related_id WHERE r.contact_id = %s ORDER BY r.pos, r.id", (r["id"],))
    c["relations"] = [{"type": x["type"], "relatedId": x["related_id"] if x["related_id"] and not x["o_del"] else None,
                       "relatedName": x["related_name"], "relatedFn": x["o_fn"], "relatedUid": x["o_uid"],
                       "relatedGender": x["o_gender"], "relatedBookId": x["o_book"], "relatedHasPhoto": bool(x["o_photo"]), "label": x["label"],
                       "typeLabel": x["label"] or rel.label(x["type"], x["o_gender"])} for x in rels]
    if with_photo and r["photo"] is not None:
        c["photoData"] = {"type": r["photo_type"] or "image/jpeg", "data": r["photo"]}
    return c


def photo(cid: int) -> tuple[bytes, str] | None:
    r = db.one("SELECT photo, photo_type FROM contacts WHERE id = %s AND deleted = 0", (cid,))
    return (r["photo"], r["photo_type"] or "image/jpeg") if r and r["photo"] is not None else None


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
    b = c.get("birthday")
    if b and _int(b.get("month"), 1, 12) and _int(b.get("day"), 1, 31):
        out["birthday"] = {"year": _int(b.get("year"), 1, 9999), "month": int(b["month"]), "day": int(b["day"])}
    else:
        out["birthday"] = None
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


def save(book_id: int, data: dict, cid: int | None = None, href: str | None = None, keep_photo: bool = True,
         resolve_book_ids: list[int] | None = None) -> int:
    """Create or replace a contact. `data` is a contact dict (API, vCard or CSV); relations may name the other contact by
    relatedId, relatedUid or relatedName (looked up by name in `resolve_book_ids`). Returns the id."""
    c = validate(data)
    with db.tx():
        prev = get_row(cid) if cid else None
        if prev and prev["book_id"] != book_id:
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
        if "iopix" in data:
            ip = data.get("iopix") or {}
            cols["iopix_person_id"] = _int(ip.get("personId"), 1, 2 ** 31 - 1)
            cols["iopix_person_name"] = _clean(ip.get("name")) if cols["iopix_person_id"] else None
        if data.get("photo") is not None or not keep_photo:
            ph = data.get("photo")
            cols["photo"] = ph["data"] if ph else None
            cols["photo_type"] = ph.get("type") if ph else None
        if prev:
            cols.update({"etag": _etag(prev["id"]), "changed_token": token, "uid": uid})
            db.ex("UPDATE contacts SET " + ", ".join(f"{k} = %s" for k in cols) + " WHERE id = %s", (*cols.values(), prev["id"]))
            cid = prev["id"]
        else:
            href = href or f"{re.sub(r'[^A-Za-z0-9._-]', '-', uid)}.vcf"
            old = by_href(book_id, href)
            if old:  # a tombstone with this name: reuse the row
                cid = old["id"]
                cols.update({"etag": _etag(cid), "changed_token": token, "uid": uid, "deleted": 0})
                db.ex("UPDATE contacts SET " + ", ".join(f"{k} = %s" for k in cols) + " WHERE id = %s", (*cols.values(), cid))
            else:
                cols.update({"book_id": book_id, "uid": uid, "href": href, "etag": "new", "changed_token": token})
                cid = db.ex("INSERT INTO contacts (" + ", ".join(cols) + ") VALUES (" + ", ".join(["%s"] * len(cols)) + ")",
                            tuple(cols.values()))
                db.ex("UPDATE contacts SET etag = %s WHERE id = %s", (_etag(cid), cid))
        for key, (table, fields) in CHILD.items():
            db.ex(f"DELETE FROM {table} WHERE contact_id = %s", (cid,))
            db.many(f"INSERT INTO {table} (contact_id, pos, {', '.join(fields)}) VALUES (%s, %s, {', '.join(['%s'] * len(fields))})",
                    [(cid, i, *(x.get(f) for f in fields)) for i, x in enumerate(c[key])])
        db.ex("DELETE FROM contact_tags WHERE contact_id = %s", (cid,))
        db.many("INSERT IGNORE INTO contact_tags (contact_id, tag) VALUES (%s, %s)", [(cid, t) for t in c["tags"]])
        _save_relations(cid, c["relations"], resolve_book_ids or [book_id])
    return cid


def _resolve(r: dict, book_ids: list[int], self_id: int) -> int | None:
    if r.get("relatedId"):
        row = get_row(int(r["relatedId"]))
        return row["id"] if row and not row["deleted"] and row["book_id"] in book_ids and row["id"] != self_id else None
    marks = ",".join(["%s"] * len(book_ids))
    if r.get("relatedUid"):
        row = db.one(f"SELECT id FROM contacts WHERE uid = %s AND book_id IN ({marks}) AND deleted = 0 AND id <> %s LIMIT 1",
                     (r["relatedUid"], *book_ids, self_id))
        if row:
            return row["id"]
    name = (r.get("relatedName") or "").strip()
    if name:
        rows = db.q(f"SELECT id FROM contacts WHERE fn = %s AND book_id IN ({marks}) AND deleted = 0 AND id <> %s LIMIT 2",
                    (name, *book_ids, self_id))
        if len(rows) == 1:  # only when the name is unambiguous
            return rows[0]["id"]
    return None


def _touch(cid: int) -> None:
    row = get_row(cid)
    if row and not row["deleted"]:
        tok = _bump(row["book_id"])
        db.ex("UPDATE contacts SET etag = %s, changed_token = %s, updated = NOW() WHERE id = %s", (_etag(cid), tok, cid))


def _save_relations(cid: int, rels: list[dict], book_ids: list[int]) -> None:
    me = get_row(cid)
    old = {(x["related_id"], x["type"]) for x in db.q("SELECT related_id, type FROM relations WHERE contact_id = %s AND related_id IS NOT NULL", (cid,))}
    db.ex("DELETE FROM relations WHERE contact_id = %s", (cid,))
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
                db.ex("UPDATE contacts SET gender = %s WHERE id = %s AND gender IS NULL", (g, rid))
    db.many("INSERT INTO relations (contact_id, pos, type, related_id, related_name, label) VALUES (%s, %s, %s, %s, %s, %s)", rows)
    touched = set()
    for rid, t in old - new:
        inv = rel.inverse(t)
        if inv:
            n = db.ex("DELETE FROM relations WHERE contact_id = %s AND related_id = %s AND type = %s LIMIT 1", (rid, cid, inv))
            if n:
                touched.add(rid)
    for rid, t in new - old:
        inv = rel.inverse(t)
        if inv and not db.one("SELECT 1 AS x FROM relations WHERE contact_id = %s AND related_id = %s AND type = %s", (rid, cid, inv)):
            pos = (db.one("SELECT coalesce(max(pos), -1) + 1 AS p FROM relations WHERE contact_id = %s", (rid,)) or {"p": 0})["p"]
            db.ex("INSERT INTO relations (contact_id, pos, type, related_id) VALUES (%s, %s, %s, %s)", (rid, pos, inv, cid))
            touched.add(rid)
    # a relation to a name that now matches this contact (imported before it existed) is linked up
    if me and me["fn"]:
        for x in db.q("SELECT r.id, r.contact_id FROM relations r JOIN contacts o ON o.id = r.contact_id "
                      "WHERE r.related_id IS NULL AND r.related_name = %s AND o.book_id = %s AND o.id <> %s", (me["fn"], me["book_id"], cid)):
            db.ex("UPDATE relations SET related_id = %s, related_name = NULL WHERE id = %s", (cid, x["id"]))
            touched.add(x["contact_id"])
    for rid in touched:
        _touch(rid)


def set_photo(cid: int, data: bytes | None, ctype: str | None) -> None:
    row = get_row(cid)
    tok = _bump(row["book_id"])
    db.ex("UPDATE contacts SET photo = %s, photo_type = %s, etag = %s, changed_token = %s WHERE id = %s",
          (data, ctype if data else None, _etag(cid), tok, cid))


def set_fields(cid: int, **cols) -> None:
    row = get_row(cid)
    tok = _bump(row["book_id"])
    db.ex("UPDATE contacts SET " + ", ".join(f"{k} = %s" for k in cols) + ", etag = %s, changed_token = %s WHERE id = %s",
          (*cols.values(), _etag(cid), tok, cid))


def delete(cid: int) -> None:
    with db.tx():
        row = get_row(cid)
        if not row or row["deleted"]:
            return
        others = [x["contact_id"] for x in db.q("SELECT DISTINCT contact_id FROM relations WHERE related_id = %s", (cid,))]
        db.ex("DELETE FROM relations WHERE related_id = %s OR contact_id = %s", (cid, cid))
        for table, _ in CHILD.values():
            db.ex(f"DELETE FROM {table} WHERE contact_id = %s", (cid,))
        db.ex("DELETE FROM contact_tags WHERE contact_id = %s", (cid,))
        tok = _bump(row["book_id"])
        db.ex("UPDATE contacts SET deleted = 1, photo = NULL, notes = NULL, extra = NULL, etag = %s, changed_token = %s, "
              "iopix_person_id = NULL WHERE id = %s", (_etag(cid), tok, cid))
        from app import users
        users.forget_me_contact(cid)  # whoever had this card as "me"
        for o in others:
            _touch(o)


def move(cid: int, new_book: int) -> None:
    """To another address book: the contact keeps its id (and relations); the old book gets a tombstone."""
    with db.tx():
        row = get_row(cid)
        if row["book_id"] == new_book:
            return
        tok_old = _bump(row["book_id"])
        db.ex("INSERT INTO contacts (book_id, uid, href, fn, etag, changed_token, deleted) VALUES (%s, %s, %s, '', %s, %s, 1) "
              "ON DUPLICATE KEY UPDATE deleted = 1, changed_token = VALUES(changed_token), etag = VALUES(etag)",
              (row["book_id"], row["uid"], row["href"], _etag(cid), tok_old))
        href = row["href"]
        if by_href(new_book, href):
            href = f"{uuidlib.uuid4()}.vcf"
        tok = _bump(new_book)
        db.ex("UPDATE contacts SET book_id = %s, href = %s, etag = %s, changed_token = %s WHERE id = %s",
              (new_book, href, _etag(cid), tok, cid))


def all_tags(book_ids: list[int]) -> list[dict]:
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    return db.q(f"SELECT t.tag, count(*) AS n FROM contact_tags t JOIN contacts c ON c.id = t.contact_id "
                f"WHERE c.book_id IN ({marks}) AND c.deleted = 0 GROUP BY t.tag ORDER BY t.tag", book_ids)


def upcoming(book_ids: list[int], days: int = 30) -> list[dict]:
    """Birthdays and other dates in the next `days` days, soonest first."""
    import datetime as dt
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    today = dt.date.today()
    out = []
    rows = db.q(f"SELECT c.id, c.fn, c.bday_year AS year, c.bday_month AS month, c.bday_day AS day, 'birthday' AS label, "
                f"c.photo IS NOT NULL AS has_photo FROM contacts c WHERE c.book_id IN ({marks}) AND c.deleted = 0 AND c.bday_month IS NOT NULL "
                f"UNION ALL SELECT c.id, c.fn, d.year, d.month, d.day, d.label, c.photo IS NOT NULL FROM contact_dates d "
                f"JOIN contacts c ON c.id = d.contact_id WHERE c.book_id IN ({marks}) AND c.deleted = 0", (*book_ids, *book_ids))
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
                        "turns": (d.year - r["year"]) if r["year"] else None, "hasPhoto": bool(r["has_photo"])})
    return sorted(out, key=lambda x: (x["inDays"], x["fn"]))


def find_duplicates(book_ids: list[int]) -> list[list[dict]]:
    """Contacts that share a name, an email or a phone number (digits only)."""
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    groups: dict = {}
    for r in db.q(f"SELECT id, lower(fn) AS k FROM contacts WHERE book_id IN ({marks}) AND deleted = 0 AND fn <> ''", book_ids):
        groups.setdefault(("n", r["k"]), set()).add(r["id"])
    for r in db.q(f"SELECT c.id, lower(e.value) AS k FROM contact_emails e JOIN contacts c ON c.id = e.contact_id "
                  f"WHERE c.book_id IN ({marks}) AND c.deleted = 0", book_ids):
        groups.setdefault(("e", r["k"]), set()).add(r["id"])
    for r in db.q(f"SELECT c.id, right(regexp_replace(p.value, '[^0-9]', ''), 9) AS k FROM contact_phones p "
                  f"JOIN contacts c ON c.id = p.contact_id WHERE c.book_id IN ({marks}) AND c.deleted = 0", book_ids):
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
    """What merging gives, without saving: `keep` (a full() dict, with photo) with the others' emails, phones,
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
        for k in ("prefix", "given", "additional", "family", "suffix"):
            if not keep["name"].get(k) and o["name"].get(k):
                keep["name"][k] = o["name"][k]
        if o.get("notes") and o["notes"] not in (keep.get("notes") or ""):
            keep["notes"] = ((keep.get("notes") or "") + "\n\n" + o["notes"]).strip()
        if not keep.get("iopix") and o.get("iopix"):
            keep["iopix"] = o["iopix"]
        if not keep.get("photoData") and o.get("photoData"):
            keep["photoData"] = o["photoData"]
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


def merge(keep_id: int, other_ids: list[int], result: dict | None = None, photo_from: int | None = None) -> None:
    """Fold other contacts into one: `result` (the contact as it should end up, e.g. chosen field by field) or what
    combine() gives. Relations from elsewhere that point at the others move to the kept one; then the others are deleted."""
    keep = full(keep_id, with_photo=True)
    others = [o for o in (full(x, with_photo=True) for x in other_ids if x != keep_id) if o]
    data = result if result is not None else combine(keep, others)
    photo = None
    if photo_from is not None:
        src = next((c for c in [keep, *others] if c["id"] == photo_from), None)
        photo = src.get("photoData") if src else None
    elif data.get("photoData"):
        photo = data["photoData"]
    with db.tx():
        for o in others:
            db.ex("UPDATE relations SET related_id = %s WHERE related_id = %s AND contact_id NOT IN (%s, %s)", (keep_id, o["id"], keep_id, o["id"]))
        save(keep["bookId"], {**data, "photo": photo}, cid=keep_id, keep_photo=photo is None and photo_from is None)
        for o in others:
            db.ex("DELETE FROM relations WHERE (contact_id = %s AND related_id = %s) OR (contact_id = %s AND related_id = %s)",
                  (o["id"], keep_id, keep_id, o["id"]))
            delete(o["id"])
