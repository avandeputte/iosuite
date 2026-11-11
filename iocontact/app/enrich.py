"""Enrichment: suggestions for a contact, which change nothing until a person accepts them.

Built-in lookups use only public interfaces that need no account and allow automated use:
  Gravatar   by email address (sent as a SHA-256 hash): the public profile's name, job, company,
             location and verified accounts (LinkedIn, X, Instagram... links the person added there themselves)
  GitHub     a GitHub profile on the contact: name, company, website, location, bio, X handle
  Mastodon   a Mastodon profile: name, the links on the profile
  Bluesky    a Bluesky handle: name, bio
LinkedIn, Facebook, Instagram and X have no such interface (and forbid automated fetching), so they are not queried;
an assistant connected over MCP can research a person and file what it finds here with suggest_contact_update.
Photos are never suggested: the linked ioPix person is a contact's only photo.
A lookup runs only when someone asks for it. A suggestion someone dismissed is not offered again.
"""
import hashlib
import logging
import json
import re
import urllib.parse
import urllib.request

from app import db, model, vcard
from iosuite_shared import outbound
from iosuite_shared.errors import Invalid

FIELDS = {  # field: (label, kind) — single fields replace, list fields add an entry
    "name": ("Name", "single"), "nickname": ("Nickname", "single"),
    "org": ("Company", "single"), "department": ("Department", "single"), "title": ("Job title", "single"),
    "birthday": ("Birthday", "single"), "gender": ("Gender", "single"), "notes": ("Notes (added)", "single"),
    "emails": ("Email", "list"), "phones": ("Phone", "list"), "addresses": ("Address", "list"), "urls": ("Website", "list"),
    "social": ("Social profile", "list"), "tags": ("Label", "list"),
}
log = logging.getLogger("iocontact.enrich")
UA = "iocontact (+https://github.com/avandeputte/iocontact)"
TIMEOUT = 8


# Lookups only reach public web servers: an address a profile (or a Mastodon server's answer) names must be http(s)
# on a host that resolves to public addresses, never this machine or the LAN, and the connection goes to the address
# that was checked (iosuite_shared.outbound), a redirect's too.
_public = outbound.check
_opener = outbound.opener(outbound.public)


def _get(url: str, accept: str = "application/json", limit: int = 2_000_000):
    _public(url)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with _opener.open(req, timeout=TIMEOUT) as r:
        return r.read(limit + 1)[:limit], r.headers.get("content-type", "")


def _json(url: str):
    return json.loads(_get(url)[0])


def _text(html: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


# ------------------------------------------------------------------ the lookups (each yields (field, value, evidence))

def gravatar(c: dict):
    for e in c.get("emails") or []:
        h = hashlib.sha256(e["value"].strip().lower().encode()).hexdigest()
        try:
            p = _json(f"https://api.gravatar.com/v3/profiles/{h}")
        except Exception:  # noqa: BLE001  no public profile
            continue
        url = p.get("profile_url") or f"https://gravatar.com/{h}"
        if p.get("display_name"):
            yield "name", {"fn": p["display_name"]}, url
        if p.get("job_title"):
            yield "title", p["job_title"], url
        if p.get("company"):
            yield "org", p["company"], url
        if p.get("location"):
            yield "addresses", {"label": "home", "city": p["location"]}, url
        for a in p.get("verified_accounts") or []:
            if a.get("url"):
                svc = vcard.social_from_url(a["url"])
                yield ("social", {"service": svc, "value": a["url"]}, url) if svc else ("urls", {"value": a["url"], "label": a.get("service_label")}, url)
        for ln in p.get("links") or []:
            if ln.get("url"):
                yield "urls", {"value": ln["url"], "label": ln.get("label")}, url


def _handle(c: dict, service: str) -> list[str]:
    out = []
    for s in c.get("social") or []:
        if s["service"] == service:
            v = s["value"].strip()
            v = re.sub(r"^https?://(www\.)?[^/]+/(profile/)?@?", "", v) if service != "mastodon" else v
            out.append(v.strip("/@"))
    return [x for x in out if x]


def github(c: dict):
    for login in _handle(c, "github"):
        p = _json(f"https://api.github.com/users/{urllib.parse.quote(login)}")
        url = p.get("html_url") or f"https://github.com/{login}"
        if p.get("name"):
            yield "name", {"fn": p["name"]}, url
        if p.get("company"):
            yield "org", p["company"].lstrip("@"), url
        if p.get("blog"):
            b = p["blog"] if "://" in p["blog"] else "https://" + p["blog"]
            yield "urls", {"value": b, "label": "website"}, url
        if p.get("location"):
            yield "addresses", {"label": "home", "city": p["location"]}, url
        if p.get("email"):
            yield "emails", {"value": p["email"], "label": "other"}, url
        if p.get("twitter_username"):
            yield "social", {"service": "x", "value": p["twitter_username"]}, url
        if p.get("bio"):
            yield "notes", f"GitHub: {p['bio']}", url


def mastodon(c: dict):
    for v in _handle(c, "mastodon"):
        m = re.match(r"^@?([^@/\s]+)@([^@/\s]+)$", v) or re.match(r"^https?://([^/]+)/@([^/?#]+)", v)
        if not m:
            continue
        user, host = (m.group(1), m.group(2)) if "@" in v and "://" not in v else (m.group(2), m.group(1))
        p = _json(f"https://{host}/api/v1/accounts/lookup?acct={urllib.parse.quote(user)}")
        url = p.get("url") or f"https://{host}/@{user}"
        if p.get("display_name"):
            yield "name", {"fn": p["display_name"]}, url
        for f in p.get("fields") or []:
            link = re.search(r'href="([^"]+)"', f.get("value") or "")
            if link:
                svc = vcard.social_from_url(link.group(1))
                yield ("social", {"service": svc, "value": link.group(1)}, url) if svc else ("urls", {"value": link.group(1), "label": _text(f.get("name"))[:64]}, url)


def bluesky(c: dict):
    for handle in _handle(c, "bluesky"):
        p = _json(f"https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor={urllib.parse.quote(handle)}")
        url = f"https://bsky.app/profile/{p.get('handle') or handle}"
        if p.get("displayName"):
            yield "name", {"fn": p["displayName"]}, url
        if p.get("description"):
            yield "notes", f"Bluesky: {p['description']}", url


PROVIDERS = {"gravatar": gravatar, "github": github, "mastodon": mastodon, "bluesky": bluesky}


# ------------------------------------------------------------------ suggestions

def _vkey(field: str, value) -> str:
    if field == "phones":
        return re.sub(r"\D", "", str(value.get("value")))[-8:]
    if isinstance(value, dict):
        return json.dumps({k: str(v).strip().lower() for k, v in sorted(value.items()) if v not in (None, "") and k != "label"})[:255]
    return str(value).strip().lower()[:255]


def _already_has(c: dict, field: str, value) -> bool:
    """Whether the contact holds this already (then it is no suggestion)."""
    if field == "name":
        return model.display_name(c).strip().lower() == model.display_name(value).strip().lower()
    if field == "notes":
        return str(value).strip().lower() in (c.get("notes") or "").lower()
    if field == "birthday":
        b = c.get("birthday") or {}
        return bool(b) and all(b.get(k) == value.get(k) for k in ("year", "month", "day"))
    if FIELDS.get(field, ("", ""))[1] == "single":
        return (c.get(field) or "").strip().lower() == str(value).strip().lower()
    if field == "tags":
        return str(value).strip().lower() in {t.lower() for t in c.get("tags") or []}
    have = {_vkey(field, x) for x in c.get(field) or []}
    if field == "social":
        have |= {_vkey("social", {"service": x["service"], "value": vcard.social_url(x["service"], x["value"])}) for x in c.get("social") or []}
        value = {"service": value.get("service"), "value": vcard.social_url(value.get("service") or "", value.get("value") or "")}
    if field == "addresses":
        return any((value.get("city") or "").strip().lower() in (str(x.get("city") or "") + " " + str(x.get("region") or "")).lower()
                   and value.get("city") for x in c.get("addresses") or [])
    return _vkey(field, value) in have


def normalise(field: str, value):
    """A suggestion's value in the shape the contact uses, or ValueError."""
    if field == "photo":
        raise Invalid("contacts keep no photo of their own: link the contact to an ioPix person instead")
    if field not in FIELDS:
        raise Invalid(f"'{field}' is not a field; one of: {', '.join(FIELDS)}")
    if field == "name":
        if isinstance(value, str):
            value = {"fn": value}
        return {k: str(v).strip() for k, v in value.items() if k in ("fn", "prefix", "given", "additional", "family", "suffix") and v}
    if field == "birthday":
        d = model.parse_date(value) if isinstance(value, str) else model.partial_date(value)
        if d is None:
            raise Invalid("a birthday is YYYY-MM-DD, YYYY-MM, YYYY or MM-DD")
        return d
    if FIELDS[field][1] == "single" or field == "tags":
        v = str(value).strip()
        if not v:
            raise Invalid("empty value")
        return v[:2000]
    if isinstance(value, str):
        value = {"value": value}
    if field == "social" and not value.get("service"):
        value["service"] = vcard.social_from_url(value.get("value") or "") or "other"
    if field == "addresses":
        return {k: str(v).strip() for k, v in value.items() if k in ("label", "street", "city", "region", "postcode", "country", "pobox", "ext") and v}
    return {k: str(v).strip() for k, v in value.items() if v not in (None, "")}


def add(cid: int, field: str, value, source: str, evidence: str | None = None, note: str | None = None, user_id: int | None = None) -> str:
    """File one suggestion: 'added', 'known' (the contact has it), 'dismissed' (someone said no before) or 'pending' already."""
    value = normalise(field, value)
    if evidence and not re.match(r"^https?://", str(evidence), re.I):
        evidence = None  # a link to where it was found, or nothing
    c = model.full(cid)
    if _already_has(c, field, value):
        return "known"
    key = _vkey(field, value)
    old = db.one("SELECT status FROM con_contact_suggestions WHERE contact_id = %s AND field = %s AND vkey = %s", (cid, field, key))
    if old:
        return old["status"] if old["status"] != "accepted" else "known"
    db.ex("INSERT INTO con_contact_suggestions (contact_id, field, value, vkey, source, evidence, note, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
          (cid, field, json.dumps(value), key, source[:64], (evidence or "")[:1024] or None, (note or "")[:1024] or None, user_id))
    return "added"


def lookup(cid: int, user_id: int | None = None, providers: list[str] | None = None) -> dict:
    """Run the built-in lookups for one contact and file what they find. {added, known, errors}."""
    c = model.full(cid)
    out = {"contactId": cid, "fn": c["fn"], "added": 0, "known": 0, "errors": [], "sources": []}
    for name, fn in PROVIDERS.items():
        if providers and name not in providers:
            continue
        try:
            for field, value, evidence in fn(c):
                if field == "social" and not value.get("service"):
                    continue
                try:
                    r = add(cid, field, value, name, evidence, None, user_id)
                except ValueError:
                    continue
                out["added" if r == "added" else "known"] += 1
                if r == "added" and name not in out["sources"]:
                    out["sources"].append(name)
        except Exception as e:  # noqa: BLE001  one service down or the person not there: the others still run
            if not (hasattr(e, "code") and getattr(e, "code") == 404):
                # what went wrong is for the log: the text may name hosts and addresses inside the network
                log.warning("lookup %s for contact %s failed: %s: %s", name, cid, type(e).__name__, str(e)[:200])
                out["errors"].append(f"{name}: no answer")
    return out


def listing(book_ids: list[int], status: str = "pending", contact_id: int | None = None, limit: int = 500) -> list[dict]:
    if not book_ids:
        return []
    marks = ",".join(["%s"] * len(book_ids))
    args: list = [status, *book_ids]
    extra = ""
    if contact_id:
        extra = " AND s.contact_id = %s"
        args.append(contact_id)
    rows = db.q(f"SELECT s.*, c.fn, c.address_book_id FROM con_contact_suggestions s JOIN con_contacts c ON c.id = s.contact_id "
                f"WHERE s.status = %s AND s.field <> 'photo' AND c.deleted = 0 AND c.address_book_id IN ({marks}){extra} "
                f"ORDER BY c.fn, s.contact_id, s.field, s.id LIMIT %s", (*args, limit))
    from app import users
    names = users.names_of({r["created_by"] for r in rows if r["created_by"]})  # the accounts live in the Shared ioSuite database
    return [{"id": r["id"], "contactId": r["contact_id"], "fn": r["fn"], "bookId": r["address_book_id"], "field": r["field"],
             "fieldLabel": FIELDS.get(r["field"], (r["field"],))[0], "value": json.loads(r["value"]), "source": r["source"],
             "evidence": r["evidence"], "note": r["note"], "by": names.get(r["created_by"]), "status": r["status"],
             "created": r["created_at"].isoformat() if r["created_at"] else None} for r in rows]


def pending_count(book_ids: list[int]) -> int:
    if not book_ids:
        return 0
    marks = ",".join(["%s"] * len(book_ids))
    return db.one(f"SELECT count(*) AS n FROM con_contact_suggestions s JOIN con_contacts c ON c.id = s.contact_id WHERE s.status = 'pending' AND s.field <> 'photo' "
                  f"AND c.deleted = 0 AND c.address_book_id IN ({marks})", book_ids)["n"]


def accept(sid: int, user_id: int | None, book_ids: list[int], value=None) -> dict:
    """Apply one suggestion to its contact (value: an edited version of it) and mark it accepted."""
    s = db.one("SELECT * FROM con_contact_suggestions WHERE id = %s", (sid,))
    if not s or s["status"] != "pending":
        raise Invalid("No such suggestion waiting")
    field = s["field"]
    if field not in FIELDS:
        raise Invalid("Photos are not kept on contacts any more: link the contact to an ioPix person instead")
    v = normalise(field, value) if value is not None else json.loads(s["value"])
    cid = s["contact_id"]
    c = model.full(cid)
    if field == "name":
        if any(k in v for k in ("given", "family")):
            c["name"] = {**{k: "" for k in c["name"]}, **{k: x for k, x in v.items() if k != "fn"}}
            c["fn"] = v.get("fn") or ""
        else:
            c["fn"], c["name"] = v["fn"], {k: "" for k in c["name"]}
    elif field == "notes":
        c["notes"] = ((c.get("notes") or "") + "\n\n" + v).strip()
    elif field == "tags":
        c["tags"] = sorted(set(c["tags"]) | {v})
    elif FIELDS[field][1] == "single":
        c[field] = v
    else:
        c[field] = (c.get(field) or []) + [v]
    model.save(c["bookId"], c, cid, None, book_ids)
    db.ex("UPDATE con_contact_suggestions SET status = 'accepted', decided_by = %s, decided_at = NOW() WHERE id = %s", (user_id, sid))
    if field in ("name", "org", "title", "birthday", "gender", "nickname", "department"):  # one value: the rival ones are moot
        db.ex("UPDATE con_contact_suggestions SET status = 'dismissed', decided_by = %s, decided_at = NOW() WHERE contact_id = %s AND field = %s AND status = 'pending'",
              (user_id, cid, field))
    return {"accepted": sid, "contactId": cid, "field": field}


def dismiss(sid: int, user_id: int | None) -> None:
    db.ex("UPDATE con_contact_suggestions SET status = 'dismissed', decided_by = %s, decided_at = NOW() WHERE id = %s AND status = 'pending'", (user_id, sid))


def suggestion(sid: int) -> dict | None:
    return db.one("SELECT s.id, s.contact_id, c.address_book_id FROM con_contact_suggestions s JOIN con_contacts c ON c.id = s.contact_id WHERE s.id = %s", (sid,))
