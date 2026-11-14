"""Clean up and data quality: finding contacts that are probably the same person (with a score and the reasons),
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

from app import csvio, db, model
from iosuite_shared.errors import Invalid

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
    rows = db.q(f"SELECT id, address_book_id, fn, given, family, suffix, nickname, maiden, org, gender, bday_year, bday_month, bday_day, "
                f"iopix_person_id FROM con_contacts WHERE deleted = 0 AND address_book_id IN ({marks})", book_ids)
    cs = {r["id"]: {**r, "emails": set(), "phones": set(), "rel": set()} for r in rows}
    for r in db.q(f"SELECT e.contact_id, lower(e.value) AS v FROM con_contact_emails e JOIN con_contacts c ON c.id = e.contact_id "
                  f"WHERE c.deleted = 0 AND c.address_book_id IN ({marks})", book_ids):
        cs[r["contact_id"]]["emails"].add(r["v"].strip())
    for r in db.q(f"SELECT p.contact_id, p.value FROM con_contact_phones p JOIN con_contacts c ON c.id = p.contact_id "
                  f"WHERE c.deleted = 0 AND c.address_book_id IN ({marks})", book_ids):
        d = digits9(r["value"])
        if d:
            cs[r["contact_id"]]["phones"].add(d)
    for r in db.q(f"SELECT r.contact_id, r.related_id FROM con_contact_relations r JOIN con_contacts c ON c.id = r.contact_id "
                  f"WHERE r.related_id IS NOT NULL AND c.address_book_id IN ({marks})", book_ids):
        if r["contact_id"] in cs:
            cs[r["contact_id"]]["rel"].add(r["related_id"])
    # an email or number on three or more contacts is a household's (a home phone, a family address): it says nothing
    # about whether two of them are one person
    held: dict = {}
    for c in cs.values():
        for v in c["emails"]:
            held[("e", v)] = held.get(("e", v), 0) + 1
        for v in c["phones"]:
            held[("p", v)] = held.get(("p", v), 0) + 1
    for c in cs.values():
        c["emails"] = {v for v in c["emails"] if held[("e", v)] < 3}
        c["phones"] = {v for v in c["phones"] if held[("p", v)] < 3}
    for c in cs.values():
        given, family = norm(c["given"]), norm(c["family"])
        if not given and not family:  # only fn
            parts = norm(c["fn"]).split()
            given, family = (parts[0] if parts else ""), " ".join(parts[1:])
        c["n_given"], c["n_family"], c["n_full"] = given, family, norm(c["fn"])
        c["canon"] = canon_given(given) | canon_given(c.get("nickname") or "")
        c["families"] = {f for f in (family, norm(c.get("maiden"))) if f}
        c["suffix"] = norm(c.get("suffix")).replace(" ", "")
    return cs


def _name_match(a: dict, b: dict) -> tuple[str | None, str]:
    """How the two names agree: ('exact' | 'nickname' | 'initial' | 'typo', why), or (None, why) when they are other
    names. People in one household share a last name, an address and often a phone or an email, so only the first
    name tells them apart: without a first name that fits, two contacts are never offered as duplicates."""
    ga, gb = a["n_given"], b["n_given"]
    fa, fb = a["n_family"], b["n_family"]
    same_family = bool(a["families"] & b["families"]) or (not fa and not fb)
    if ga and ga == fb and fa == gb:
        return "exact", "same name (first and last swapped)"
    if ga and ga == gb and same_family:
        return "exact", "same name"
    if not ga or not gb:
        return (None, "") if ga or gb else ("unnamed", "")
    if same_family and a["canon"] & b["canon"]:
        short, long = sorted([ga, gb], key=len)
        return "nickname", f"{short.title()} can be short for {long.title()}"
    if same_family and ga[0] == gb[0] and (len(ga.rstrip(".")) == 1 or len(gb.rstrip(".")) == 1):
        return "initial", "same last name, and an initial that fits"
    # a misspelling: long enough names that differ by a letter or two (Jonathan / Jonathon, Smith / Smyth), never
    # two short names (Mary / Mark, Ann / Anna are usually two people)
    if min(len(ga), len(gb)) >= 5 and difflib.SequenceMatcher(None, ga, gb).ratio() >= 0.85 and (same_family or (
            fa and fb and difflib.SequenceMatcher(None, fa, fb).ratio() >= 0.85)):
        return "typo", f"very similar names ({a['fn']} / {b['fn']})"
    if ga == gb and fa and fb and min(len(fa), len(fb)) >= 4 and difflib.SequenceMatcher(None, fa, fb).ratio() >= 0.8:
        return "typo", f"very similar names ({a['fn']} / {b['fn']})"
    if ga == gb and fa and fb:
        return "firstname", "same first name, another last name (married?)"
    return None, "other first names"


def score_pair(a: dict, b: dict) -> tuple[int, list[str]]:
    """How likely two contacts are one person (0-100) and why. The first name has to fit: a shared last name, address,
    home phone or family email alone never makes two people duplicates."""
    if b["id"] in a["rel"] or a["id"] in b["rel"]:
        return 0, ["related to each other"]
    match, why_name = _name_match(a, b)
    if match is None:
        return 0, [why_name] if why_name else []
    s, why = 0, []
    if match == "exact":
        s += 55
    elif match == "nickname":
        s += 45
    elif match == "firstname":
        s += 20
    elif match == "initial":
        s += 25
    elif match == "typo":
        s += 35
    if why_name:
        why.append(why_name)
    if a["suffix"] != b["suffix"] and (a["suffix"] or b["suffix"]):
        s -= 50  # John Smith Sr. and John Smith Jr.
        why.append("different suffixes (Sr./Jr.)")
    em = a["emails"] & b["emails"]
    ph = a["phones"] & b["phones"]
    # in a household these are shared, so they confirm a name that fits but count for little on their own
    if em:
        s += 25
        why.append(f"same email {sorted(em)[0]}")
    if ph:
        s += 15
        why.append("same phone number")
    if match == "unnamed" and not em and not ph:
        return 0, []
    if match == "unnamed":
        s += 20  # two contacts with no names at all (an email or a number only) that share it
    # birthdays can be partial: only the parts both have are compared, and a lone year that agrees is weak evidence
    parts = [k for k in ("bday_year", "bday_month", "bday_day") if a[k] and b[k]]
    if parts:
        if all(a[k] == b[k] for k in parts):
            s += 35 if "bday_day" in parts else 10
            why.append("same birthday" if "bday_day" in parts else "same birth year")
        else:
            s -= 60
            why.append("different birthdays")
    if a["org"] and b["org"] and norm(a["org"]) == norm(b["org"]):
        s += 10
        why.append("same company")
    if a["gender"] and b["gender"] and a["gender"] != b["gender"] and "UO" not in a["gender"] + b["gender"]:
        s -= 50
        why.append("different genders")
    if match == "firstname" and not (em or "same birthday" in why):
        return 0, []
    if match in ("initial", "typo") and not (em or "same birthday" in why):
        s = min(s, 40)  # only a similar name (and maybe the household's phone): worth a look, no more
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
    return {(r["contact_id"], r["other_contact_id"]) for r in db.q("SELECT contact_id, other_contact_id FROM con_contact_non_duplicates")}


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
    cs = _load([model.get_row(a_id)["address_book_id"], model.get_row(b_id)["address_book_id"]])
    sc, why = score_pair(cs[a_id], cs[b_id])
    return {"score": sc, "level": level(sc), "reasons": why}


def not_duplicates(ids: list[int], user_id: int | None) -> int:
    """Mark every pair among these contacts as different people."""
    n = 0
    ids = sorted(set(ids))
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            n += db.ex("INSERT IGNORE INTO con_contact_non_duplicates (contact_id, other_contact_id, user_id) VALUES (%s, %s, %s)", (a, b, user_id))
    return n


def forget_not_duplicates() -> int:
    return db.ex("DELETE FROM con_contact_non_duplicates")


# ------------------------------------------------------------------ merging (with a way back)

SINGLE = ["name", "nickname", "maiden", "gender", "birthday", "org", "department", "title", "role", "notes", "iopix",
          "phoneticGiven", "phoneticFamily"]
TABLES = ["con_contact_emails", "con_contact_phones", "con_contact_addresses", "con_contact_urls", "con_contact_social_profiles", "con_contact_dates", "con_contact_tags"]


def preview(ids: list[int], keep_id: int) -> dict:
    """The contacts, what merging them into keep_id gives by itself, and the fields where they disagree, so a person
    can pick: {contacts, merged, choices: {field: [{contactId, value}]}}."""
    full = {i: model.full(i) for i in ids}
    merged = model.combine(full[keep_id], [full[i] for i in ids if i != keep_id])
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
    return {"keep": keep_id, "contacts": [full[i] for i in ids], "merged": merged, "choices": choices}


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


PHOTO_COLUMNS = ("photo", "photo_type")  # no longer used: the linked ioPix person is a contact's only photo


def snapshot(ids: list[int]) -> dict:
    """The database rows of these contacts and of every relation to or from them."""
    marks = ",".join(["%s"] * len(ids))
    contacts = [{k: v for k, v in r.items() if k not in PHOTO_COLUMNS} for r in _rows("con_contacts", "id", ids)]
    snap = {"contacts": contacts, **{t: _rows(t, "contact_id", ids) for t in TABLES},
            "relations": db.q(f"SELECT * FROM con_contact_relations WHERE contact_id IN ({marks}) OR related_id IN ({marks})", (*ids, *ids))}
    return {k: [{c: _enc(v) for c, v in r.items()} for r in rows] for k, rows in snap.items()}


def merge(u: dict, keep_id: int, other_ids: list[int], result: dict | None = None) -> int:
    """Merge (model.merge) after keeping a snapshot for undo. Returns the merge's id."""
    ids = [keep_id, *[i for i in other_ids if i != keep_id]]
    snap = json.dumps(snapshot(ids))
    names = ", ".join(model.get_row(i)["fn"] for i in ids)
    if result is not None:
        result = {k: v for k, v in result.items() if k not in ("photo", "photoData", "id", "uid", "href", "etag", "bookId")}
    model.merge(keep_id, other_ids, result)
    return db.ex("INSERT INTO con_contact_merges (user_id, kept_contact_id, other_ids, names, snapshot, keep_etag) VALUES (%s, %s, %s, %s, %s, %s)",
                 (u["id"] if u else None, keep_id, ",".join(map(str, other_ids)), names[:1024], snap, model.get_row(keep_id)["etag"]))


def history(book_ids: list[int], limit: int = 50) -> list[dict]:
    out = []
    from app import users
    rows = db.q("SELECT m.id, m.kept_contact_id, m.other_ids, m.names, m.keep_etag, m.created_at, m.undone_at, m.user_id, c.etag, c.address_book_id, c.deleted, c.fn "
                "FROM con_contact_merges m LEFT JOIN con_contacts c ON c.id = m.kept_contact_id ORDER BY m.id DESC LIMIT %s", (limit * 3,))
    who = users.names_of({r["user_id"] for r in rows if r["user_id"]})  # the accounts live in the Shared ioSuite database
    for r in rows:
        if r["address_book_id"] not in book_ids:
            continue
        out.append({"id": r["id"], "keepId": r["kept_contact_id"], "keepName": r["fn"], "otherIds": [int(x) for x in r["other_ids"].split(",") if x],
                    "names": r["names"], "by": who.get(r["user_id"]), "at": r["created_at"].isoformat() if r["created_at"] else None,
                    "undone": r["undone_at"].isoformat() if r["undone_at"] else None,
                    "changedSince": bool(r["etag"] != r["keep_etag"]), "canUndo": not r["undone_at"] and not r["deleted"]})
        if len(out) >= limit:
            break
    return out


def undo(merge_id: int) -> dict:
    """Put the contacts of a merge back as they were (the kept one loses changes made to it since)."""
    m = db.one("SELECT * FROM con_contact_merges WHERE id = %s", (merge_id,))
    if not m or m["undone_at"]:
        raise Invalid("No such merge, or it was undone already")
    snap = {k: [{c: _dec(v) for c, v in r.items()} for r in rows] for k, rows in json.loads(m["snapshot"]).items()}
    ids = [r["id"] for r in snap["contacts"]]
    marks = ",".join(["%s"] * len(ids))
    live = {r["id"] for r in db.q("SELECT id FROM con_contacts WHERE deleted = 0")}
    with db.tx():
        touched = {r["contact_id"] for r in db.q(f"SELECT contact_id FROM con_contact_relations WHERE related_id IN ({marks})", ids)}
        for r in snap["contacts"]:
            cols = {k: v for k, v in r.items() if k not in ("id", "created_at", "updated_at", *PHOTO_COLUMNS)}
            db.ex("UPDATE con_contacts SET " + ", ".join(f"`{k}` = %s" for k in cols) + " WHERE id = %s", (*cols.values(), r["id"]))
        for t in TABLES:
            db.ex(f"DELETE FROM {t} WHERE contact_id IN ({marks})", ids)
            for r in snap[t]:
                cols = {k: v for k, v in r.items() if k != "id"}
                db.ex(f"INSERT INTO {t} (" + ", ".join(f"`{k}`" for k in cols) + ") VALUES (" + ", ".join(["%s"] * len(cols)) + ")", tuple(cols.values()))
        db.ex(f"DELETE FROM con_contact_relations WHERE contact_id IN ({marks}) OR related_id IN ({marks})", (*ids, *ids))
        for r in snap["relations"]:
            if r["contact_id"] not in live and r["contact_id"] not in ids or (r["related_id"] and r["related_id"] not in live and r["related_id"] not in ids):
                continue
            cols = {k: v for k, v in r.items() if k != "id"}
            db.ex("INSERT INTO con_contact_relations (" + ", ".join(f"`{k}`" for k in cols) + ") VALUES (" + ", ".join(["%s"] * len(cols)) + ")", tuple(cols.values()))
            touched.add(r["contact_id"])
        for cid in set(ids) | touched:
            model._touch(cid)  # new etag and sync token: phones pick the contacts up again
        db.ex("UPDATE con_contact_merges SET undone_at = NOW() WHERE id = %s", (merge_id,))
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
    "joined": ("Values glued together with ::: (from a Google import)", "tidy", "Split them"),
    "unreachable": ("No phone, email or address at all", "info", None),
}


JOINED_COLS = ("fn", "prefix", "given", "additional", "family", "suffix", "nickname", "maiden", "org", "department", "title", "role")


def run_checks(book_ids: list[int], only: str | None = None) -> list[dict]:
    """Every check (or one): [{check, title, severity, fix, count, items: [{contactId, fn, detail}]}]."""
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    found: dict = {k: [] for k in CHECKS}
    cs = {r["id"]: r for r in db.q(f"SELECT id, address_book_id, fn, given, family, org, bday_year, bday_month, bday_day, "
                                   f"iopix_person_id, {', '.join(JOINED_COLS)} FROM con_contacts WHERE deleted = 0 AND address_book_id IN ({marks})", book_ids)}

    def add(check, cid, detail=""):
        found[check].append({"contactId": cid, "fn": cs[cid]["fn"], "bookId": cs[cid]["address_book_id"], "detail": detail})
    child = {}
    for t, key in (("con_contact_emails", "emails"), ("con_contact_phones", "phones"), ("con_contact_addresses", "addresses")):
        for r in db.q(f"SELECT x.* FROM {t} x JOIN con_contacts c ON c.id = x.contact_id WHERE c.deleted = 0 AND c.address_book_id IN ({marks})", book_ids):
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
        y, m, d = c["bday_year"], c["bday_month"], c["bday_day"]
        if y and (y > this_year or y < 1900 or (y == this_year and (m or 0, d or 0) > (dt.date.today().month, dt.date.today().day))):
            add("bad_birthday", cid, f"{y}" + (f"-{m:02d}" if m else "") + (f"-{d:02d}" if d else ""))
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
        glued = [k for k in JOINED_COLS if csvio.joined(c[k])] + \
            [key for key in ("emails", "phones") if any(csvio.joined(x["value"]) for x in ch.get(key, []))] + \
            (["addresses"] if any(csvio.joined(x.get(k)) for x in ch.get("addresses", []) for k in csvio.ADDR_KEYS) else [])
        if glued:
            add("joined", cid, ", ".join(glued))
        if not ch:
            add("unreachable", cid)
    names: dict = {}
    for cid, c in cs.items():
        names.setdefault(c["fn"].strip().lower(), []).append(cid)
    for r in db.q(f"SELECT r.contact_id, r.related_name, r.type FROM con_contact_relations r JOIN con_contacts c ON c.id = r.contact_id "
                  f"WHERE r.related_id IS NULL AND r.related_name IS NOT NULL AND c.deleted = 0 AND c.address_book_id IN ({marks})", book_ids):
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
        raise Invalid(f"'{check}' has no automatic fix")
    if check == "national_phone":
        country_code = "+" + re.sub(r"\D", "", country_code or "")
        if len(country_code) < 2:
            raise Invalid("Give the country code to add, such as +32 or +1")
    items = run_checks(book_ids, check)[0]["items"]
    ids = sorted({x["contactId"] for x in items if contact_ids is None or x["contactId"] in contact_ids})
    done, skipped = [], []
    for cid in ids:
        r = model.get_row(cid)
        if not model.can_write_book(u, model.book(r["address_book_id"])):
            skipped.append(r["fn"])
            continue
        if check == "unlinked_relation":
            model.save(r["address_book_id"], model.full(cid), cid, None, book_ids)  # saving links names that match one contact
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
        elif check == "joined":
            for k in ("fn", "nickname", "maiden", "org", "department", "title", "role"):
                if csvio.joined(c.get(k)):
                    c[k] = csvio._one(c[k])
            for k, v in (c.get("name") or {}).items():
                if csvio.joined(v):
                    c["name"][k] = csvio._one(v)
            for key in ("emails", "phones"):
                c[key] = [{**x, "value": v, "pref": x.get("pref") if not j else 0}
                          for x in c[key] for j, v in enumerate(p for p in csvio._parts(x["value"]) if p)]
            c["addresses"] = [b for a in c["addresses"] for b in csvio.split_address(a)]
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
        model.save(r["address_book_id"], c, cid, None, book_ids)
        done.append(r["fn"])
    return {"check": check, "fixed": done, "skipped": skipped}


