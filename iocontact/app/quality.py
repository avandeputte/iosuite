"""Maintenance and data quality: finding contacts that are probably the same person (with a score and the reasons),
merging them with a choice of what to keep, undoing a merge, and checks that find (and fix) untidy data.

Duplicates are found in pairs. Contacts are first grouped by cheap keys (an email, a phone number's last nine digits,
the name with accents, case and nicknames taken out, the family name) and only contacts sharing a key are compared,
so a book of thousands stays quick. A pair is scored from what it shares (an email, a phone, the same or a similar
name, a nickname of the same name, the same birthday or company) and from what speaks against it (other birthdays,
another gender, a relation between the two). Pairs someone marked as different people are left out for good.
"""
import base64
import datetime as dt
import difflib
import json
import re
import unicodedata

from app import db, model

# ------------------------------------------------------------------ names

NICKNAMES = {
    "robert": "bob bobby rob robbie bert", "william": "bill billy will willy liam wim willem", "elizabeth": "liz lizzy beth betty bess elisabeth lisa eliza",
    "katherine": "kate kathy katie kat catherine kathryn cathy", "james": "jim jimmy jamie", "michael": "mike mikey mick michel",
    "david": "dave davy", "daniel": "dan danny", "thomas": "tom tommy", "anthony": "tony", "christopher": "chris kit",
    "christine": "chris chrissy christina kristin", "nicholas": "nick nicky nico nicolas", "alexander": "alex alec sasha xander",
    "alexandra": "alex sandra lexi", "samuel": "sam sammy", "samantha": "sam sammy", "benjamin": "ben benny",
    "joseph": "joe joey jos jozef", "jennifer": "jen jenny", "matthew": "matt matty", "stephen": "steve stevie steven stefan",
    "richard": "rick ricky rich dick", "andrew": "andy drew", "patrick": "pat paddy", "patricia": "pat patty trish",
    "susan": "sue susie suzanne", "margaret": "meg maggie peggy margo greet", "edward": "ed eddie ted ned", "charles": "charlie chuck",
    "gregory": "greg", "jonathan": "jon jonny", "john": "jack johnny jan johan johannes hans", "timothy": "tim timmy",
    "frederick": "fred freddie", "francis": "frank frankie frans", "jeffrey": "jeff", "lawrence": "larry", "ronald": "ron ronnie",
    "donald": "don donnie", "kenneth": "ken kenny", "gerald": "jerry gerry", "henry": "harry hank henk", "peter": "pete piet",
    "nathaniel": "nate nathan nat", "zachary": "zach zack", "abigail": "abby", "rebecca": "becky becca", "victoria": "vicky tori",
    "amanda": "mandy", "cynthia": "cindy", "deborah": "debbie deb", "jessica": "jess jessie", "nicole": "nicky nikki",
    "joshua": "josh", "theodore": "theo ted", "maximilian": "max", "louis": "lou lewis", "eleanor": "ellie nora",
    "dorothy": "dot dottie", "barbara": "barb barbie", "jacqueline": "jackie", "josephine": "jo josie fien", "johanna": "jo hanna anja",
    "catharina": "katrien trien", "maria": "marie mia mieke", "anna": "anne annie anneke", "philip": "phil flip",
    "gabriel": "gabe", "raymond": "ray", "albert": "al bert", "walter": "walt wouter", "leonard": "leo len lenny",
    "isabella": "bella izzy isabel", "olivia": "liv livvy", "sophia": "sophie", "emily": "em emmy", "madeline": "maddie",
}
_NICK: dict = {}
for _full, _nicks in NICKNAMES.items():
    for _n in [_full, *_nicks.split()]:
        _NICK.setdefault(_n, set()).add(_full)


def norm(s: str | None) -> str:
    """Lower case, no accents, no punctuation, single spaces."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", s).split())


def canon_given(g: str) -> set:
    """The given name and the full names it can be short for (bob: robert)."""
    g = norm(g).split(" ")[0] if g else ""
    return ({g} | _NICK.get(g, set())) if g else set()


def digits9(v: str | None) -> str:
    d = re.sub(r"\D", "", v or "")
    return d[-8:] if len(d) >= 7 else ""  # the last eight digits: the same number written with or without the country code


# ------------------------------------------------------------------ duplicates

LEVELS = ((80, "very likely"), (55, "likely"), (35, "possible"))


def level(score: int) -> str:
    return next((name for lo, name in LEVELS if score >= lo), "unlikely")


def _load(book_ids: list[int]) -> dict:
    if not book_ids:
        return {}
    marks = ",".join(["%s"] * len(book_ids))
    rows = db.q(f"SELECT id, book_id, fn, given, family, nickname, maiden, org, gender, bday_year, bday_month, bday_day, "
                f"photo IS NOT NULL AS has_photo, iopix_person_id FROM contacts WHERE deleted = 0 AND book_id IN ({marks})", book_ids)
    cs = {r["id"]: {**r, "emails": set(), "phones": set(), "rel": set()} for r in rows}
    for r in db.q(f"SELECT e.contact_id, lower(e.value) AS v FROM contact_emails e JOIN contacts c ON c.id = e.contact_id "
                  f"WHERE c.deleted = 0 AND c.book_id IN ({marks})", book_ids):
        cs[r["contact_id"]]["emails"].add(r["v"].strip())
    for r in db.q(f"SELECT p.contact_id, p.value FROM contact_phones p JOIN contacts c ON c.id = p.contact_id "
                  f"WHERE c.deleted = 0 AND c.book_id IN ({marks})", book_ids):
        d = digits9(r["value"])
        if d:
            cs[r["contact_id"]]["phones"].add(d)
    for r in db.q(f"SELECT r.contact_id, r.related_id FROM relations r JOIN contacts c ON c.id = r.contact_id "
                  f"WHERE r.related_id IS NOT NULL AND c.book_id IN ({marks})", book_ids):
        if r["contact_id"] in cs:
            cs[r["contact_id"]]["rel"].add(r["related_id"])
    for c in cs.values():
        given, family = norm(c["given"]), norm(c["family"])
        if not given and not family:  # only fn
            parts = norm(c["fn"]).split()
            given, family = (parts[0] if parts else ""), " ".join(parts[1:])
        c["n_given"], c["n_family"], c["n_full"] = given, family, norm(c["fn"])
        c["canon"] = canon_given(given) | canon_given(c.get("nickname") or "")
        c["families"] = {f for f in (family, norm(c.get("maiden"))) if f}
    return cs


def score_pair(a: dict, b: dict) -> tuple[int, list[str]]:
    """How likely two contacts are one person (0-100) and why."""
    if b["id"] in a["rel"] or a["id"] in b["rel"]:
        return 0, ["related to each other"]
    s, why, name_signal = 0, [], False
    em = a["emails"] & b["emails"]
    if em:
        s += 45
        why.append(f"same email {sorted(em)[0]}")
    ph = a["phones"] & b["phones"]
    if ph:
        s += 35
        why.append("same phone number")
    same_family = bool(a["families"] & b["families"])
    swapped = a["n_given"] and a["n_given"] == b["n_family"] and a["n_family"] == b["n_given"]
    if a["n_full"] and (a["n_full"] == b["n_full"] or swapped or (a["n_given"] == b["n_given"] and a["n_family"] == b["n_family"] and a["n_family"])):
        s += 55
        why.append("same name" + (" (first and last swapped)" if swapped else ""))
        name_signal = True
    elif same_family and a["canon"] & b["canon"] and a["n_given"] != b["n_given"]:
        s += 45
        short, long = sorted([a["n_given"], b["n_given"]], key=len)
        why.append(f"{short.title()} can be short for {long.title()}")
        name_signal = True
    elif same_family and a["n_given"] and b["n_given"] and a["n_given"][0] == b["n_given"][0] and (len(a["n_given"]) <= 2 or len(b["n_given"]) <= 2):
        s += 30
        why.append("same last name, and an initial that fits")
        name_signal = True
    elif a["n_full"] and b["n_full"] and min(len(a["n_full"]), len(b["n_full"])) >= 5:
        r = difflib.SequenceMatcher(None, a["n_full"], b["n_full"]).ratio()
        if r >= 0.86:
            s += 35
            why.append(f"very similar names ({b['fn']} / {a['fn']})")
            name_signal = True
        elif same_family and r >= 0.75:
            s += 15
            why.append("same last name, similar first names")
            name_signal = True
    if a["bday_month"] and b["bday_month"]:
        same_day = (a["bday_month"], a["bday_day"]) == (b["bday_month"], b["bday_day"])
        years_ok = not (a["bday_year"] and b["bday_year"] and a["bday_year"] != b["bday_year"])
        if same_day and years_ok:
            s += 35 if name_signal else 20 if em or ph else 0
            why.append("same birthday")
        else:
            s -= 40
            why.append("different birthdays")
    if a["org"] and b["org"] and norm(a["org"]) == norm(b["org"]) and (name_signal or em or ph):
        s += 10
        why.append("same company")
    if a["gender"] and b["gender"] and a["gender"] != b["gender"] and "UO" not in a["gender"] + b["gender"]:
        s -= 30
        why.append("different genders")
    if not name_signal and (em or ph) and a["n_given"] and b["n_given"] and not (a["canon"] & b["canon"]):
        s = min(s, 40)  # a shared home number or family email, with other first names: probably two people
        why.append("other first names (a shared home number or address?)")
    return max(0, min(100, s)), why


def _blocks(cs: dict) -> dict:
    blocks: dict = {}
    for c in cs.values():
        keys = [("e", e) for e in c["emails"]] + [("p", p) for p in c["phones"]]
        if c["n_full"]:
            keys.append(("n", " ".join(sorted(c["n_full"].split()))))
        for f in c["families"]:
            keys.append(("f", f))
        for g in c["canon"]:
            keys.append(("g", g))
        for k in keys:
            blocks.setdefault(k, []).append(c["id"])
    return blocks


def dismissed_pairs() -> set:
    return {(r["a"], r["b"]) for r in db.q("SELECT a, b FROM not_duplicates")}


def find(book_ids: list[int], min_score: int = 35) -> list[dict]:
    """Groups of probable duplicates, most certain first: [{score, level, contacts, pairs: [{a, b, score, reasons}]}]."""
    cs = _load(book_ids)
    no = dismissed_pairs()
    pairs: dict = {}
    for key, ids in _blocks(cs).items():
        if len(ids) < 2 or len(ids) > 300:  # a very common family or first name alone is no evidence
            continue
        for i, x in enumerate(ids):
            for y in ids[i + 1:]:
                a, b = (x, y) if x < y else (y, x)
                if (a, b) in pairs or (a, b) in no:
                    continue
                sc, why = score_pair(cs[a], cs[b])
                if sc >= min_score:
                    pairs[(a, b)] = (sc, why)
    # groups: contacts joined by pairs
    parent: dict = {}

    def root(x):
        while parent.get(x, x) != x:
            x = parent[x]
        return x
    for a, b in pairs:
        parent[root(a)] = root(b)
    groups: dict = {}
    for (a, b), (sc, why) in pairs.items():
        g = groups.setdefault(root(a), {"ids": set(), "pairs": []})
        g["ids"] |= {a, b}
        g["pairs"].append({"a": a, "b": b, "score": sc, "level": level(sc), "reasons": why})
    out = []
    for g in groups.values():
        ids = sorted(g["ids"])
        rows = db.q(f"{model.SUMMARY_SQL} WHERE c.id IN ({','.join(['%s'] * len(ids))}) ORDER BY c.id", ids)
        top = max(p["score"] for p in g["pairs"])
        out.append({"score": top, "level": level(top), "contacts": [model.summary(r) for r in rows],
                    "pairs": sorted(g["pairs"], key=lambda p: -p["score"])})
    return sorted(out, key=lambda g: (-g["score"], g["contacts"][0]["fn"].lower()))


def compare(a_id: int, b_id: int) -> dict:
    cs = _load([model.get_row(a_id)["book_id"], model.get_row(b_id)["book_id"]])
    sc, why = score_pair(cs[a_id], cs[b_id])
    return {"score": sc, "level": level(sc), "reasons": why}


def not_duplicates(ids: list[int], user_id: int | None) -> int:
    """Mark every pair among these contacts as different people."""
    n = 0
    ids = sorted(set(ids))
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            n += db.ex("INSERT IGNORE INTO not_duplicates (a, b, user_id) VALUES (%s, %s, %s)", (a, b, user_id))
    return n


def forget_not_duplicates() -> int:
    return db.ex("DELETE FROM not_duplicates")


# ------------------------------------------------------------------ merging (with a way back)

SINGLE = ["name", "nickname", "maiden", "gender", "birthday", "org", "department", "title", "role", "notes", "iopix",
          "phoneticGiven", "phoneticFamily"]
TABLES = ["contact_emails", "contact_phones", "contact_addresses", "contact_urls", "contact_social", "contact_dates", "contact_tags"]


def preview(ids: list[int], keep_id: int) -> dict:
    """The contacts, what merging them into keep_id gives by itself, and the fields where they disagree, so a person
    can pick: {contacts, merged, choices: {field: [{contactId, value}]}}."""
    full = {i: model.full(i) for i in ids}
    keep = model.full(keep_id, with_photo=True)
    others = [model.full(i, with_photo=True) for i in ids if i != keep_id]
    merged = model.combine(keep, others)
    merged.pop("photoData", None)
    choices = {}
    for f in SINGLE:
        vals, seen = [], []
        for i in ids:
            v = full[i].get(f)
            if f == "name":
                v = {k: x for k, x in (v or {}).items() if x}
            if v in (None, "", {}, []) or v in seen:
                continue
            seen.append(v)
            vals.append({"contactId": i, "value": v})
        if len(vals) > 1:
            choices[f] = vals
    photos = [{"contactId": i} for i in ids if full[i]["hasPhoto"]]
    if len(photos) > 1:
        choices["photo"] = photos
    return {"keep": keep_id, "contacts": [full[i] for i in ids], "merged": merged, "choices": choices,
            "photoFrom": next((p["contactId"] for p in photos if p["contactId"] == keep_id), photos[0]["contactId"] if photos else None)}


def _rows(table: str, col: str, ids: list[int]) -> list[dict]:
    marks = ",".join(["%s"] * len(ids))
    return db.q(f"SELECT * FROM {table} WHERE {col} IN ({marks})", ids)


def _enc(v):
    if isinstance(v, (bytes, bytearray)):
        return {"$b64": base64.b64encode(v).decode()}
    if isinstance(v, (dt.datetime, dt.date)):
        return {"$dt": v.isoformat()}
    return v


def _dec(v):
    if isinstance(v, dict) and "$b64" in v:
        return base64.b64decode(v["$b64"])
    if isinstance(v, dict) and "$dt" in v:
        return dt.datetime.fromisoformat(v["$dt"])
    return v


def snapshot(ids: list[int]) -> dict:
    """The database rows of these contacts and of every relation to or from them."""
    marks = ",".join(["%s"] * len(ids))
    snap = {"contacts": _rows("contacts", "id", ids), **{t: _rows(t, "contact_id", ids) for t in TABLES},
            "relations": db.q(f"SELECT * FROM relations WHERE contact_id IN ({marks}) OR related_id IN ({marks})", (*ids, *ids))}
    return {k: [{c: _enc(v) for c, v in r.items()} for r in rows] for k, rows in snap.items()}


def merge(u: dict, keep_id: int, other_ids: list[int], result: dict | None = None, photo_from: int | None = None) -> int:
    """Merge (model.merge) after keeping a snapshot for undo. Returns the merge's id."""
    ids = [keep_id, *[i for i in other_ids if i != keep_id]]
    snap = json.dumps(snapshot(ids))
    names = ", ".join(model.get_row(i)["fn"] for i in ids)
    if result is not None:
        result = {k: v for k, v in result.items() if k not in ("photo", "photoData", "id", "uid", "href", "etag", "bookId")}
    model.merge(keep_id, other_ids, result, photo_from)
    return db.ex("INSERT INTO merges (user_id, keep_id, other_ids, names, snapshot, keep_etag) VALUES (%s, %s, %s, %s, %s, %s)",
                 (u["id"] if u else None, keep_id, ",".join(map(str, other_ids)), names[:1024], snap, model.get_row(keep_id)["etag"]))


def history(book_ids: list[int], limit: int = 50) -> list[dict]:
    out = []
    for r in db.q("SELECT m.id, m.keep_id, m.other_ids, m.names, m.keep_etag, m.created, m.undone, u.name AS who, c.etag, c.book_id, c.deleted, c.fn "
                  "FROM merges m LEFT JOIN users u ON u.id = m.user_id LEFT JOIN contacts c ON c.id = m.keep_id ORDER BY m.id DESC LIMIT %s", (limit * 3,)):
        if r["book_id"] not in book_ids:
            continue
        out.append({"id": r["id"], "keepId": r["keep_id"], "keepName": r["fn"], "otherIds": [int(x) for x in r["other_ids"].split(",") if x],
                    "names": r["names"], "by": r["who"], "at": r["created"].isoformat() if r["created"] else None,
                    "undone": r["undone"].isoformat() if r["undone"] else None,
                    "changedSince": bool(r["etag"] != r["keep_etag"]), "canUndo": not r["undone"] and not r["deleted"]})
        if len(out) >= limit:
            break
    return out


def undo(merge_id: int) -> dict:
    """Put the contacts of a merge back as they were (the kept one loses changes made to it since)."""
    m = db.one("SELECT * FROM merges WHERE id = %s", (merge_id,))
    if not m or m["undone"]:
        raise ValueError("No such merge, or it was undone already")
    snap = {k: [{c: _dec(v) for c, v in r.items()} for r in rows] for k, rows in json.loads(m["snapshot"]).items()}
    ids = [r["id"] for r in snap["contacts"]]
    marks = ",".join(["%s"] * len(ids))
    live = {r["id"] for r in db.q("SELECT id FROM contacts WHERE deleted = 0")}
    with db.tx():
        touched = {r["contact_id"] for r in db.q(f"SELECT contact_id FROM relations WHERE related_id IN ({marks})", ids)}
        for r in snap["contacts"]:
            cols = {k: v for k, v in r.items() if k not in ("id", "created", "updated")}
            db.ex("UPDATE contacts SET " + ", ".join(f"`{k}` = %s" for k in cols) + " WHERE id = %s", (*cols.values(), r["id"]))
        for t in TABLES:
            db.ex(f"DELETE FROM {t} WHERE contact_id IN ({marks})", ids)
            for r in snap[t]:
                cols = {k: v for k, v in r.items() if k != "id"}
                db.ex(f"INSERT INTO {t} (" + ", ".join(f"`{k}`" for k in cols) + ") VALUES (" + ", ".join(["%s"] * len(cols)) + ")", tuple(cols.values()))
        db.ex(f"DELETE FROM relations WHERE contact_id IN ({marks}) OR related_id IN ({marks})", (*ids, *ids))
        for r in snap["relations"]:
            if r["contact_id"] not in live and r["contact_id"] not in ids or (r["related_id"] and r["related_id"] not in live and r["related_id"] not in ids):
                continue
            cols = {k: v for k, v in r.items() if k != "id"}
            db.ex("INSERT INTO relations (" + ", ".join(f"`{k}`" for k in cols) + ") VALUES (" + ", ".join(["%s"] * len(cols)) + ")", tuple(cols.values()))
            touched.add(r["contact_id"])
        for cid in set(ids) | touched:
            model._touch(cid)  # new etag and sync token: phones pick the contacts up again
        db.ex("UPDATE merges SET undone = NOW() WHERE id = %s", (merge_id,))
    return {"restored": [model.get_row(i)["fn"] for i in ids]}


# ------------------------------------------------------------------ data quality

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PARTICLES = {"van", "der", "den", "de", "het", "ter", "ten", "von", "zu", "la", "le", "du", "da", "di", "del", "della", "dos", "das", "y", "el", "al", "bin", "ibn"}


def proper(s: str) -> str:
    """ANN-MARIE VAN DER BERG / ann-marie van der berg: Ann-Marie van der Berg (O'Brien, McDonald too)."""
    def word(w, first):
        if not first and w in PARTICLES:
            return w
        w = "-".join(p[:1].upper() + p[1:] for p in w.split("-"))
        w = re.sub(r"^(O')(\w)", lambda m: m.group(1) + m.group(2).upper(), w)
        w = re.sub(r"^(Mc)(\w)", lambda m: m.group(1) + m.group(2).upper(), w)
        return w
    return " ".join(word(w, i == 0) for i, w in enumerate(s.lower().split()))


def _badcase(s: str | None) -> bool:
    s = (s or "").strip()
    letters = [ch for ch in s if ch.isalpha()]
    return len(letters) > 1 and (s == s.upper() or s == s.lower())


CHECKS = {
    "no_name": ("Contacts without a name", "problem", None),
    "bad_email": ("Email addresses that do not look valid", "problem", None),
    "bad_phone": ("Phone numbers that are too short or hold letters", "problem", None),
    "bad_birthday": ("Birthdays in the future or before 1900", "problem", None),
    "name_case": ("Names in ALL CAPITALS or all small letters", "tidy", "Capitalise the names"),
    "repeats": ("The same email, phone or address twice on one contact", "tidy", "Remove the repeats"),
    "unlinked_relation": ("Relations to a name that is now a contact", "tidy", "Link them to the contact"),
    "national_phone": ("Phone numbers without the country code", "tidy", "Add the country code"),
    "iopix_photo": ("Linked to ioPix but no photo of their own", "info", "Use the ioPix face as the photo"),
    "unreachable": ("No phone, email or address at all", "info", None),
}


def run_checks(book_ids: list[int], only: str | None = None) -> list[dict]:
    """Every check (or one): [{check, title, severity, fix, count, items: [{contactId, fn, detail}]}]."""
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    found: dict = {k: [] for k in CHECKS}
    cs = {r["id"]: r for r in db.q(f"SELECT id, book_id, fn, given, family, org, bday_year, bday_month, bday_day, photo IS NOT NULL AS hp, "
                                   f"iopix_person_id FROM contacts WHERE deleted = 0 AND book_id IN ({marks})", book_ids)}

    def add(check, cid, detail=""):
        found[check].append({"contactId": cid, "fn": cs[cid]["fn"], "bookId": cs[cid]["book_id"], "detail": detail})
    child = {}
    for t, key in (("contact_emails", "emails"), ("contact_phones", "phones"), ("contact_addresses", "addresses")):
        for r in db.q(f"SELECT x.* FROM {t} x JOIN contacts c ON c.id = x.contact_id WHERE c.deleted = 0 AND c.book_id IN ({marks})", book_ids):
            child.setdefault(r["contact_id"], {}).setdefault(key, []).append(r)
    this_year = dt.date.today().year
    for cid, c in cs.items():
        ch = child.get(cid, {})
        if not (c["given"] or c["family"] or c["org"]) and (not c["fn"] or c["fn"] == "Unnamed" or "@" in c["fn"]):
            add("no_name", cid, c["fn"])
        for e in ch.get("emails", []):
            if not EMAIL_RE.match(e["value"].strip()):
                add("bad_email", cid, e["value"])
        for p in ch.get("phones", []):
            d = re.sub(r"\D", "", p["value"])
            if len(d) < 6 or re.search(r"[A-Za-z]", re.sub(r"(?i)\b(ext|x|tel)\b\.?", "", p["value"])):
                add("bad_phone", cid, p["value"])
            elif not p["value"].strip().startswith("+") and not p["value"].strip().startswith("00") and len(d) >= 8:
                add("national_phone", cid, p["value"])
        y = c["bday_year"]
        if y and (y > this_year or y < 1900 or (y == this_year and (c["bday_month"], c["bday_day"]) > (dt.date.today().month, dt.date.today().day))):
            add("bad_birthday", cid, f"{y}-{c['bday_month']:02d}-{c['bday_day']:02d}")
        bad = [x for x in (c["given"], c["family"]) if _badcase(x)] or ([c["fn"]] if not (c["given"] or c["family"]) and _badcase(c["fn"]) and not c["org"] else [])
        if bad:
            add("name_case", cid, f"{c['fn']} → {proper(c['fn'])}")
        rep = []
        for key, f in (("emails", lambda r: r["value"].strip().lower()), ("phones", lambda r: re.sub(r"\D", "", r["value"])[-8:]),
                       ("addresses", lambda r: norm(" ".join(str(r.get(k) or "") for k in ("street", "city", "postcode"))))):
            vals = [f(r) for r in ch.get(key, []) if f(r)]
            if len(vals) != len(set(vals)):
                rep.append(key)
        if rep:
            add("repeats", cid, ", ".join(rep))
        if c["iopix_person_id"] and not c["hp"]:
            add("iopix_photo", cid)
        if not ch:
            add("unreachable", cid)
    names: dict = {}
    for cid, c in cs.items():
        names.setdefault(c["fn"].strip().lower(), []).append(cid)
    for r in db.q(f"SELECT r.contact_id, r.related_name, r.type FROM relations r JOIN contacts c ON c.id = r.contact_id "
                  f"WHERE r.related_id IS NULL AND r.related_name IS NOT NULL AND c.deleted = 0 AND c.book_id IN ({marks})", book_ids):
        m = names.get(r["related_name"].strip().lower()) or []
        if len(m) == 1 and m[0] != r["contact_id"]:
            add("unlinked_relation", r["contact_id"], f"{r['type']}: {r['related_name']}")
    out = []
    for k, (title, sev, fix) in CHECKS.items():
        if only and k != only:
            continue
        out.append({"check": k, "title": title, "severity": sev, "fix": fix, "count": len(found[k]), "items": found[k]})
    return out


def fix(u: dict, check: str, contact_ids: list[int] | None, book_ids: list[int], country_code: str | None = None) -> dict:
    """Fix one check's findings (all, or only these contacts) where this account may change them."""
    if check not in CHECKS or not CHECKS[check][2]:
        raise ValueError(f"'{check}' has no automatic fix")
    if check == "national_phone":
        country_code = "+" + re.sub(r"\D", "", country_code or "")
        if len(country_code) < 2:
            raise ValueError("Give the country code to add, such as +32 or +1")
    items = run_checks(book_ids, check)[0]["items"]
    ids = sorted({x["contactId"] for x in items if contact_ids is None or x["contactId"] in contact_ids})
    done, skipped = [], []
    for cid in ids:
        r = model.get_row(cid)
        if not model.can_write_book(u, model.book(r["book_id"])):
            skipped.append(r["fn"])
            continue
        if check == "iopix_photo":
            from app import iopix
            try:
                got = iopix.face(r["iopix_person_id"])
            except Exception:  # noqa: BLE001
                got = None
            if got:
                model.set_photo(cid, got[0], got[1].split(";")[0])
                done.append(r["fn"])
            else:
                skipped.append(r["fn"])
            continue
        if check == "unlinked_relation":
            model.save(r["book_id"], model.full(cid), cid, None, True, book_ids)  # saving links names that match one contact
            done.append(r["fn"])
            continue
        c = model.full(cid)
        if check == "name_case":
            for k in ("prefix", "given", "additional", "family", "suffix"):
                if _badcase(c["name"].get(k)):
                    c["name"][k] = proper(c["name"][k])
            c["fn"] = proper(c["fn"]) if _badcase(c["fn"]) or c["fn"] == c["fn"].upper() else ""
            if c["nickname"] and _badcase(c["nickname"]):
                c["nickname"] = proper(c["nickname"])
        elif check == "repeats":
            for key, f in (("emails", lambda x: x["value"].strip().lower()), ("phones", lambda x: re.sub(r"\D", "", x["value"])[-8:]),
                           ("addresses", lambda x: norm(" ".join(str(x.get(k) or "") for k in ("street", "city", "postcode"))))):
                seen, keep = set(), []
                for x in c[key]:
                    k = f(x)
                    if k and k in seen:
                        continue
                    seen.add(k)
                    keep.append(x)
                c[key] = keep
        elif check == "national_phone":
            for p in c["phones"]:
                v = p["value"].strip()
                d = re.sub(r"[^\d]", "", v)
                if v.startswith("+") or v.startswith("00") or len(d) < 8:
                    continue
                if d.startswith("0"):
                    p["value"] = country_code + " " + re.sub(r"^\s*0\s*", "", v)
                elif country_code == "+1" and len(d) == 10:
                    p["value"] = "+1 " + v
        model.save(r["book_id"], c, cid, None, True, book_ids)
        done.append(r["fn"])
    return {"check": check, "fixed": done, "skipped": skipped}


def summary_counts(book_ids: list[int]) -> dict:
    return {x["check"]: x["count"] for x in run_checks(book_ids)}


