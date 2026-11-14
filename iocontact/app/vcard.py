"""vCard 2.1 / 3.0 (RFC 2426) / 4.0 (RFC 6350) and jCard (RFC 7095), to and from ioContact's contact dicts.

Writing: vCard 3.0 is what Apple Contacts, iOS, Outlook and most older clients expect; vCard 4.0 for clients that ask
for it (CardDAV address-data version="4.0", Accept: text/vcard;version=4.0). Apple's extensions (X-ABRELATEDNAMES,
X-ABDATE, X-SOCIALPROFILE, X-ABLabel item groups) ride along in 3.0 so relations, anniversaries and social profiles
survive in Apple Contacts. Reading takes all of them, plus Google's and Outlook's habits.

Properties ioContact does not model are kept verbatim (contact["extra"]) and written back, so a client's own data
round-trips through the server.
"""
import base64
import binascii
import quopri
import re
import uuid as uuidlib
from dataclasses import dataclass, field

from app import relations as rel
from iosuite_shared.errors import Invalid

SOCIAL_SERVICES = {
    "linkedin": ("LinkedIn", ["linkedin.com"]),
    "facebook": ("Facebook", ["facebook.com", "fb.com"]),
    "instagram": ("Instagram", ["instagram.com"]),
    "x": ("X (Twitter)", ["twitter.com", "x.com"]),
    "threads": ("Threads", ["threads.net", "threads.com"]),
    "bluesky": ("Bluesky", ["bsky.app"]),
    "mastodon": ("Mastodon", []),
    "tiktok": ("TikTok", ["tiktok.com"]),
    "youtube": ("YouTube", ["youtube.com", "youtu.be"]),
    "snapchat": ("Snapchat", ["snapchat.com"]),
    "pinterest": ("Pinterest", ["pinterest.com"]),
    "github": ("GitHub", ["github.com"]),
    "reddit": ("Reddit", ["reddit.com"]),
    "flickr": ("Flickr", ["flickr.com"]),
    "whatsapp": ("WhatsApp", ["wa.me", "whatsapp.com"]),
    "telegram": ("Telegram", ["t.me", "telegram.me"]),
    "signal": ("Signal", ["signal.me"]),
    "skype": ("Skype", []),
    "other": ("Other", []),
}
# how Apple names them in X-SOCIALPROFILE;type=
APPLE_SOCIAL = {"x": "twitter", "linkedin": "linkedin", "facebook": "facebook", "instagram": "instagram"}
SOCIAL_BASE = {"linkedin": "https://www.linkedin.com/in/", "facebook": "https://www.facebook.com/",
               "instagram": "https://www.instagram.com/", "x": "https://x.com/", "threads": "https://www.threads.net/@",
               "bluesky": "https://bsky.app/profile/", "tiktok": "https://www.tiktok.com/@", "youtube": "https://www.youtube.com/@",
               "github": "https://github.com/", "pinterest": "https://www.pinterest.com/", "reddit": "https://www.reddit.com/user/",
               "snapchat": "https://www.snapchat.com/add/", "flickr": "https://www.flickr.com/people/", "telegram": "https://t.me/"}

KEEP_OUT = {"BEGIN", "END", "VERSION", "PRODID", "REV", "UID", "FN", "N", "NICKNAME", "BDAY", "X-IOCONTACT-BDAY", "ANNIVERSARY", "GENDER",
            "X-GENDER", "ORG", "TITLE", "ROLE", "NOTE", "EMAIL", "TEL", "ADR", "URL", "PHOTO", "CATEGORIES", "RELATED",
            "X-ABRELATEDNAMES", "X-ABDATE", "X-ABLABEL", "X-SOCIALPROFILE", "SOCIALPROFILE", "KIND", "X-ADDRESSBOOKSERVER-KIND",
            "X-MAIDENNAME", "X-PHONETIC-FIRST-NAME", "X-PHONETIC-LAST-NAME", "X-IOPIX-PERSON", "X-IOCONTACT-FAVORITE",
            "X-ABSHOWAS", "LABEL", "X-ANNIVERSARY", "X-MS-ANNIVERSARY", "X-EVOLUTION-ANNIVERSARY", "X-ABUID", "X-ABADR",
            "IMPP", "X-AIM", "X-JABBER", "X-SKYPE", "X-TWITTER", "X-SPOUSE",
            "X-MS-SPOUSE", "X-EVOLUTION-SPOUSE", "X-KADDRESSBOOK-X-SPOUSENAME", "X-ASSISTANT", "X-MANAGER",
            "X-EVOLUTION-ASSISTANT", "X-EVOLUTION-MANAGER", "X-KADDRESSBOOK-X-ANNIVERSARY", "X-KADDRESSBOOK-X-MANAGERSNAME",
            "X-KADDRESSBOOK-X-ASSISTANTSNAME", "X-IOCONTACT-ROLE", "X-ABORG",
            "X-IMAGEHASH", "X-IMAGETYPE"}  # these two describe the photo a phone sent, which is not kept


@dataclass
class Prop:
    name: str
    value: object                  # str, or list[str] for structured values
    params: dict = field(default_factory=dict)  # lower-case name -> list[str]
    group: str | None = None
    vtype: str = "text"            # jCard value type


# ------------------------------------------------------------------ low level text

def _unfold(text: str) -> list[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    for line in text.split("\n"):
        if line[:1] in (" ", "\t") and out:
            out[-1] += line[1:]
        elif out and out[-1].upper().find("QUOTED-PRINTABLE") >= 0 and out[-1].endswith("="):
            out[-1] = out[-1][:-1] + line   # vCard 2.1 soft line break
        else:
            out.append(line)
    return [x for x in out if x.strip()]


def _split_unescaped(s: str, sep: str) -> list[str]:
    parts, cur, i = [], [], 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            cur.append(s[i:i + 2])
            i += 2
            continue
        if c == sep:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


def unescape(s: str) -> str:
    return re.sub(r"\\([\\,;nN:])", lambda m: "\n" if m.group(1) in "nN" else m.group(1), s)


def escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def _parse_line(line: str) -> Prop | None:
    # split name;params from value at the first ':' outside quotes
    inq, idx = False, -1
    for i, c in enumerate(line):
        if c == '"':
            inq = not inq
        elif c == ":" and not inq:
            idx = i
            break
    if idx < 0:
        return None
    head, value = line[:idx], line[idx + 1:]
    pieces, cur, inq = [], [], False
    for c in head:
        if c == '"':
            inq = not inq
            cur.append(c)
        elif c == ";" and not inq:
            pieces.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    pieces.append("".join(cur))
    name = pieces[0]
    group = None
    if "." in name:
        group, name = name.split(".", 1)
    params: dict[str, list[str]] = {}
    for p in pieces[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            vals = [x.strip().strip('"') for x in re.findall(r'"[^"]*"|[^,]+', v)]
        else:  # vCard 2.1 bare types: TEL;HOME;VOICE
            k, vals = ("ENCODING" if p.upper() in ("QUOTED-PRINTABLE", "BASE64", "B") else "TYPE"), [p]
        params.setdefault(k.lower(), []).extend(vals)
    enc = [e.upper() for e in params.get("encoding", [])]
    if "QUOTED-PRINTABLE" in enc:
        charset = (params.get("charset") or ["utf-8"])[0]
        try:
            value = quopri.decodestring(value.encode("latin-1", "replace")).decode(charset, "replace")
        except LookupError:
            value = quopri.decodestring(value.encode("latin-1", "replace")).decode("utf-8", "replace")
    return Prop(name.upper(), value, params, group)


def parse_many(text: str) -> list[list[Prop]]:
    """Every VCARD in a text (a .vcf can hold many) as raw property lists (values still escaped)."""
    cards, cur = [], None
    for line in _unfold(text):
        p = _parse_line(line)
        if not p:
            continue
        if p.name == "BEGIN" and p.value.strip().upper() == "VCARD":
            cur = []
        elif p.name == "END" and p.value.strip().upper() == "VCARD":
            if cur is not None:
                cards.append(cur)
            cur = None
        elif cur is not None:
            cur.append(p)
    return cards


def _types(p: Prop) -> list[str]:
    out = []
    for t in p.params.get("type", []):
        out.extend(x.strip().lower() for x in t.split(",") if x.strip())
    return out


def _date(s: str):
    """vCard dates: 19800415, 1980-04-15, --0415, --04-15, 1604-04-15 with Apple's omit-year, and the partial forms of
    vCard 4 (1980, 1980-04) -> (y, m, d) with None for the unknown parts, or None."""
    s = (s or "").strip().split("T")[0]
    m = re.match(r"^(\d{4})-?(\d{2})-?(\d{2})$", s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    m = re.match(r"^--(\d{2})-?(\d{2})$", s)
    if m:
        return None, int(m.group(1)), int(m.group(2))
    m = re.match(r"^(\d{4})(?:-(\d{2}))?$", s)  # 198004 would be ambiguous, so RFC 6350 wants the dash
    if m:
        return int(m.group(1)), int(m.group(2)) if m.group(2) else None, None
    return None


def _omitted(p, year) -> bool:
    """Apple's X-APPLE-OMIT-YEAR=1604 marks the year that stands for "no year"; a real year next to it stays."""
    if "x-apple-omit-year" not in p.params or year is None:
        return False
    omit = (p.params["x-apple-omit-year"] or ["1604"])[0].strip()
    return not omit.isdigit() or int(omit) == year


def social_from_url(url: str) -> str | None:
    host = re.sub(r"^https?://", "", (url or "").lower()).split("/")[0]
    host = host[4:] if host.startswith("www.") else host
    for key, (_name, hosts) in SOCIAL_SERVICES.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return key
    return None


def social_url(service: str, value: str) -> str:
    v = (value or "").strip()
    if re.match(r"^[a-z]+://", v, re.I) or service not in SOCIAL_BASE:
        return v
    return SOCIAL_BASE[service] + v.lstrip("@")


LABEL_MAP = {"home": "home", "work": "work", "cell": "mobile", "mobile": "mobile", "iphone": "iPhone", "main": "main",
             "fax": "fax", "pager": "pager", "other": "other", "school": "school", "internet": None, "voice": None,
             "pref": None, "x-mobile": "mobile", "text": None, "msg": None, "x-school": "school"}


def _label_from(p: Prop, labels: dict) -> str | None:
    if p.group and p.group.lower() in labels:
        s = labels[p.group.lower()]
        return s[4:-4].lower() if s.startswith("_$!<") else s
    found = []
    for t in _types(p):
        if t in LABEL_MAP:
            if LABEL_MAP[t]:
                found.append(LABEL_MAP[t])
        elif t.startswith("x-"):
            found.append(t[2:])
    if "fax" in found:
        return ("home fax" if "home" in found else "work fax" if "work" in found else "fax")
    return found[0] if found else None


def _pref(p: Prop) -> int:
    if "pref" in _types(p):
        return 1
    v = p.params.get("pref")
    return 1 if v and v[0].isdigit() and int(v[0]) <= 1 else 0


# ------------------------------------------------------------------ reading

def to_contact(props: list[Prop]) -> dict:
    """A parsed vCard as a contact dict. Relations carry relatedUid / relatedName for the model to resolve."""
    labels = {p.group.lower(): unescape(p.value) for p in props if p.group and p.name == "X-ABLABEL"}
    c = {"uid": None, "kind": "individual", "fn": "", "name": {}, "nickname": None, "maiden": None, "phoneticGiven": None,
         "phoneticFamily": None, "gender": None, "birthday": None, "org": None, "department": None, "title": None,
         "role": None, "notes": None, "favorite": False, "emails": [], "phones": [], "addresses": [], "urls": [],
         "social": [], "dates": [], "tags": [], "relations": [], "photo": None, "iopix": None, "extra": []}
    for p in props:
        n, raw = p.name, p.value
        if n == "UID":
            c["uid"] = unescape(raw).strip()
        elif n == "FN":
            c["fn"] = unescape(raw).strip()
        elif n == "N":
            parts = [unescape(x).strip() for x in _split_unescaped(raw, ";")] + [""] * 5
            c["name"] = {"family": parts[0], "given": parts[1], "additional": parts[2], "prefix": parts[3], "suffix": parts[4]}
        elif n == "NICKNAME":
            c["nickname"] = unescape(raw).strip() or None
        elif n in ("KIND", "X-ADDRESSBOOKSERVER-KIND"):
            k = raw.strip().lower()
            c["kind"] = "org" if k == "org" else "group" if k == "group" else "individual"
        elif n == "X-ABSHOWAS" and raw.strip().upper() == "COMPANY":
            c["kind"] = "org"
        elif n in ("BDAY", "X-IOCONTACT-BDAY"):
            # X-IOCONTACT-BDAY carries a birthday vCard 3 cannot (a year, or a year and month) next to no BDAY; a
            # real BDAY wins over it
            d = _date(raw)
            if d and not (n == "X-IOCONTACT-BDAY" and c.get("birthday")):
                y, m, dd = d
                if _omitted(p, y):
                    y = None
                if y or m:
                    c["birthday"] = {"year": y, "month": m, "day": dd}
        elif n in ("ANNIVERSARY", "X-ANNIVERSARY", "X-MS-ANNIVERSARY", "X-EVOLUTION-ANNIVERSARY", "X-KADDRESSBOOK-X-ANNIVERSARY"):
            d = _date(raw)
            if d and d[1] and d[2] and not any(x["label"] == "anniversary" for x in c["dates"]):
                c["dates"].append({"label": "anniversary", "year": d[0], "month": d[1], "day": d[2]})
        elif n == "X-ABDATE":
            d = _date(raw)
            if d and d[1] and d[2]:
                lab = _label_from(p, labels) or "other"
                y = None if _omitted(p, d[0]) else d[0]
                if not (lab == "anniversary" and any(x["label"] == "anniversary" for x in c["dates"])):
                    c["dates"].append({"label": lab, "year": y, "month": d[1], "day": d[2]})
        elif n in ("GENDER", "X-GENDER"):
            g = unescape(_split_unescaped(raw, ";")[0]).strip().upper()[:1]
            c["gender"] = g if g in ("M", "F", "O", "N", "U") else None
        elif n == "ORG":
            parts = [unescape(x).strip() for x in _split_unescaped(raw, ";")]
            c["org"] = parts[0] or None
            c["department"] = "; ".join(x for x in parts[1:] if x) or None
        elif n == "TITLE":
            c["title"] = unescape(raw).strip() or None
        elif n == "ROLE":
            c["role"] = unescape(raw).strip() or None
        elif n == "NOTE":
            c["notes"] = unescape(raw)
        elif n == "EMAIL":
            v = unescape(raw).strip()
            if v.lower().startswith("mailto:"):
                v = v[7:]
            if v:
                c["emails"].append({"label": _label_from(p, labels), "value": v, "pref": _pref(p)})
        elif n == "TEL":
            v = unescape(raw).strip()
            if v.lower().startswith("tel:"):
                v = v[4:]
            if v:
                c["phones"].append({"label": _label_from(p, labels), "value": v, "pref": _pref(p)})
        elif n == "ADR":
            parts = [unescape(x).strip() for x in _split_unescaped(raw, ";")] + [""] * 7
            if any(parts[:7]):
                c["addresses"].append({"label": _label_from(p, labels), "pobox": parts[0], "ext": parts[1], "street": parts[2],
                                       "city": parts[3], "region": parts[4], "postcode": parts[5], "country": parts[6],
                                       "pref": _pref(p)})
        elif n == "URL":
            v = unescape(raw).strip()
            svc = social_from_url(v)
            if svc:
                c["social"].append({"service": svc, "value": v})
            elif v:
                c["urls"].append({"label": _label_from(p, labels), "value": v})
        elif n in ("X-SOCIALPROFILE", "SOCIALPROFILE"):
            v = unescape(raw).strip()
            if v.lower().startswith("x-apple:"):
                v = v[8:]
            t = (_types(p) or [None])[0] or (p.params.get("service-type") or [None])[0]
            t = (t or "").lower()
            svc = {"twitter": "x"}.get(t, t) if t in SOCIAL_SERVICES or t == "twitter" else social_from_url(v) or "other"
            if not v and p.params.get("x-user"):
                v = social_url(svc, p.params["x-user"][0])
            if v and not any(s["value"] == v for s in c["social"]):
                c["social"].append({"service": svc, "value": v})
        elif n in ("X-TWITTER",):
            c["social"].append({"service": "x", "value": social_url("x", unescape(raw))})
        elif n == "X-SKYPE":
            c["social"].append({"service": "skype", "value": unescape(raw)})
        elif n == "IMPP":
            v = unescape(raw).strip()
            scheme = v.split(":", 1)[0].lower() if ":" in v else ""
            svc = {"skype": "skype", "xmpp": "other", "whatsapp": "whatsapp", "telegram": "telegram", "signal": "signal"}.get(scheme)
            if svc:
                c["social"].append({"service": svc, "value": v.split(":", 1)[1]})
            else:
                c["extra"].append(p)
        elif n == "CATEGORIES":
            c["tags"].extend(t for t in (unescape(x).strip() for x in _split_unescaped(raw, ",")) if t)
        elif n == "RELATED":
            v = unescape(raw).strip()
            t, g = rel.from_label((_types(p) or ["contact"])[0])
            if (p.params.get("x-iocontact-type")):
                t = p.params["x-iocontact-type"][0]
            r = {"type": t, "gender": g, "label": None}
            if v.lower().startswith("urn:uuid:"):
                r["relatedUid"] = v[9:]
            elif p.params.get("value", [""])[0].lower() == "text" or not re.match(r"^[a-z][a-z0-9+.-]*:", v, re.I):
                r["relatedName"] = v
            else:
                r["relatedUri"] = v
                r["relatedName"] = v
            c["relations"].append(r)
        elif n == "X-ABRELATEDNAMES":
            v = unescape(raw).strip()
            lab = labels.get((p.group or "").lower()) or (_types(p) or ["other"])[0]
            t, g = rel.from_label(lab)
            plain = lab[4:-4] if lab.startswith("_$!<") else lab
            c["relations"].append({"type": t, "gender": g, "relatedName": v,
                                   "label": None if t != "other" or plain.lower() == "other" else plain})
        elif n in ("X-SPOUSE", "X-MS-SPOUSE", "X-EVOLUTION-SPOUSE", "X-KADDRESSBOOK-X-SPOUSENAME"):
            c["relations"].append({"type": "spouse", "relatedName": unescape(raw).strip()})
        elif n in ("X-MANAGER", "X-EVOLUTION-MANAGER", "X-KADDRESSBOOK-X-MANAGERSNAME"):
            c["relations"].append({"type": "manager", "relatedName": unescape(raw).strip()})
        elif n in ("X-ASSISTANT", "X-EVOLUTION-ASSISTANT", "X-KADDRESSBOOK-X-ASSISTANTSNAME"):
            c["relations"].append({"type": "assistant", "relatedName": unescape(raw).strip()})
        elif n == "PHOTO":
            c["photo"] = _photo(p)
        elif n == "X-MAIDENNAME":
            c["maiden"] = unescape(raw).strip() or None
        elif n == "X-PHONETIC-FIRST-NAME":
            c["phoneticGiven"] = unescape(raw).strip() or None
        elif n == "X-PHONETIC-LAST-NAME":
            c["phoneticFamily"] = unescape(raw).strip() or None
        elif n == "X-IOPIX-PERSON":
            pid = p.params.get("x-id", [""])[0]
            if pid.isdigit():
                c["iopix"] = {"personId": int(pid), "name": unescape(raw).strip() or None}
        elif n == "X-IOCONTACT-FAVORITE":
            c["favorite"] = raw.strip() in ("1", "TRUE", "true", "yes")
        elif n in KEEP_OUT or n == "X-ABLABEL":
            continue
        else:
            c["extra"].append(p)
    if not c["fn"]:
        nm = c["name"]
        c["fn"] = " ".join(x for x in (nm.get("prefix"), nm.get("given"), nm.get("additional"), nm.get("family"), nm.get("suffix")) if x) \
            or c["org"] or (c["emails"][0]["value"] if c["emails"] else "") or (c["phones"][0]["value"] if c["phones"] else "")
    # drop exact duplicate relations (a client may echo both RELATED and X-ABRELATEDNAMES)
    seen, rels = set(), []
    for r in c["relations"]:
        key = (r.get("type"), r.get("relatedUid") or (r.get("relatedName") or "").lower())
        if key not in seen:
            seen.add(key)
            rels.append(r)
    c["relations"] = rels
    c["extra"] = [_kept(p) for p in c["extra"]]
    return c


def _kept(p: Prop) -> str:
    """A property ioContact does not model, as the line it is kept as. Its value is still escaped as it came, so it
    is written as it is: escaping it again would double every backslash each time the card is saved."""
    if "QUOTED-PRINTABLE" in [e.upper() for e in p.params.get("encoding", [])]:  # vCard 2.1, decoded when it was read
        return _line(p, "4.0")
    name = f"{p.group}.{p.name}" if p.group else p.name
    return f"{name}{_param_str(p.params)}:" + re.sub(r"[\r\n]+", " ", str(p.value))


def _photo(p: Prop):
    v = p.value.strip()
    m = re.match(r"^data:([^;,]+)?(;base64)?,(.*)$", v, re.S)
    try:
        if m:
            return {"type": m.group(1) or "image/jpeg", "data": base64.b64decode(m.group(3))}
        enc = [e.lower() for e in p.params.get("encoding", [])]
        if "b" in enc or "base64" in enc:
            t = (p.params.get("type") or ["JPEG"])[0].lower()
            return {"type": t if "/" in t else f"image/{t}", "data": base64.b64decode(v)}
    except (binascii.Error, ValueError):
        return None
    return None


def parse(text: str) -> list[dict]:
    return [to_contact(props) for props in parse_many(text)]


# ------------------------------------------------------------------ writing

def _date_str(y, m, d, version: str) -> tuple[str, dict]:
    """vCard 4: 19800415, --0415, 1980-04 or 1980. vCard 3 takes a full date only (1604 with Apple's omit-year stands
    for no year); for a date without a day the vCard 4 form is returned, for X-IOCONTACT-BDAY."""
    if version == "4.0" or not (m and d):
        if not y:
            return f"--{m:02d}{d:02d}", {}
        return (f"{y:04d}{m:02d}{d:02d}" if d else f"{y:04d}-{m:02d}" if m else f"{y:04d}"), {}
    if y:
        return f"{y:04d}-{m:02d}-{d:02d}", {}
    return f"1604-{m:02d}-{d:02d}", {"x-apple-omit-year": ["1604"]}


def _type_params(label: str | None, kind: str, pref: int, version: str) -> dict:
    types: list[str] = []
    lab = (label or "").strip()
    low = lab.lower()
    if kind == "EMAIL" and version != "4.0":
        types.append("INTERNET")
    std = {"home": "HOME", "work": "WORK", "mobile": "CELL", "cell": "CELL", "fax": "FAX", "pager": "PAGER",
           "main": "MAIN" if version != "4.0" else "VOICE", "iphone": "CELL", "other": "OTHER" if version != "4.0" else None,
           "home fax": "HOME,FAX", "work fax": "WORK,FAX", "school": None}
    if low in std:
        if std[low]:
            types.extend(std[low].split(","))
        if low in ("main", "iphone", "school") and version != "4.0":
            types.append(f"X-{low.upper()}" if low != "main" else "")
    elif kind == "TEL" and version != "4.0" and not lab:
        types.append("VOICE")
    types = [t for t in types if t]
    params: dict = {}
    if version == "4.0":
        types = [t.lower() for t in types if t not in ("INTERNET",)]
        if kind == "TEL" and "cell" in types:
            types = ["cell" if t == "cell" else t for t in types]
        if pref:
            params["pref"] = ["1"]
    elif pref:
        types.append("pref")
    if types:
        params["type"] = types
    return params


def _custom_label(label: str | None) -> str | None:
    """Labels that are not vCard TYPEs travel as Apple item labels."""
    low = (label or "").strip().lower()
    if not low or low in ("home", "work", "mobile", "cell", "fax", "pager", "main", "other", "home fax", "work fax", "iphone"):
        return None
    return label.strip()


def from_contact(c: dict, version: str = "3.0") -> str:
    return "\r\n".join(_fold(_line(p, version)) for p in _props(c, version)) + "\r\n"


def _props(c: dict, version: str) -> list[Prop]:
    v4 = version == "4.0"
    out: list[Prop] = [Prop("BEGIN", "VCARD"), Prop("VERSION", version), Prop("PRODID", "-//iothing//ioContact//EN")]
    item = [0]
    # the groups of the properties kept as received (a phone's own item1.X-...) are theirs: ours take other numbers
    taken = {m.group(1).lower() for m in (re.match(r"^([A-Za-z0-9-]+)\.", raw) for raw in c.get("extra") or []) if m}

    def grp() -> str:
        item[0] += 1
        while f"item{item[0]}" in taken:
            item[0] += 1
        return f"item{item[0]}"

    def add_labeled(name, value, params, label, vtype="text"):
        custom = _custom_label(label)
        if custom and not v4:
            g = grp()
            out.append(Prop(name, value, params, g, vtype))
            out.append(Prop("X-ABLabel", custom, {}, g))
        else:
            if custom and v4:
                params = {**params, "label": [custom]} if name != "ADR" else {**params, "x-label": [custom]}
            out.append(Prop(name, value, params, None, vtype))

    nm = c.get("name") or {}
    out.append(Prop("UID", c.get("uid") or str(uuidlib.uuid4()), {}, None, "uri" if (c.get("uid") or "").startswith("urn:") else "text"))
    if v4 and c.get("kind") in ("org", "group"):
        out.append(Prop("KIND", c["kind"]))
    if not v4 and c.get("kind") == "org":
        out.append(Prop("X-ABShowAs", "COMPANY"))
    out.append(Prop("FN", c.get("fn") or ""))
    out.append(Prop("N", [nm.get("family") or "", nm.get("given") or "", nm.get("additional") or "", nm.get("prefix") or "", nm.get("suffix") or ""]))
    if c.get("nickname"):
        out.append(Prop("NICKNAME", c["nickname"]))
    if c.get("maiden"):
        out.append(Prop("X-MAIDENNAME", c["maiden"]))
    if c.get("phoneticGiven"):
        out.append(Prop("X-PHONETIC-FIRST-NAME", c["phoneticGiven"]))
    if c.get("phoneticFamily"):
        out.append(Prop("X-PHONETIC-LAST-NAME", c["phoneticFamily"]))
    if c.get("gender"):
        out.append(Prop("GENDER" if v4 else "X-GENDER", [c["gender"]] if v4 else {"M": "Male", "F": "Female"}.get(c["gender"], "Other")))
    b = c.get("birthday")
    if b and (b.get("year") or b.get("month")):
        s, params = _date_str(b.get("year"), b.get("month"), b.get("day"), version)
        if v4 or (b.get("month") and b.get("day")):
            out.append(Prop("BDAY", s, params, None, "date-and-or-time" if v4 else "date"))
        else:  # vCard 3 has no partial dates: the year (and month) ride along in a property clients keep
            out.append(Prop("X-IOCONTACT-BDAY", s))
    for d in c.get("dates") or []:
        s, params = _date_str(d.get("year"), d["month"], d["day"], version)
        if v4 and d.get("label") == "anniversary":
            out.append(Prop("ANNIVERSARY", s, {}, None, "date-and-or-time"))
        else:
            g = grp()
            out.append(Prop("X-ABDATE", s, params, g, "date"))
            lab = d.get("label") or "other"
            out.append(Prop("X-ABLabel", "_$!<Anniversary>!$_" if lab == "anniversary" else "_$!<Other>!$_" if lab == "other" else lab, {}, g))
    if c.get("org") or c.get("department"):
        out.append(Prop("ORG", [c.get("org") or "", *([c["department"]] if c.get("department") else [])]))
    if c.get("title"):
        out.append(Prop("TITLE", c["title"]))
    if c.get("role"):
        out.append(Prop("ROLE", c["role"]))
    for e in c.get("emails") or []:
        add_labeled("EMAIL", e["value"], _type_params(e.get("label"), "EMAIL", e.get("pref"), version), e.get("label"))
    for t in c.get("phones") or []:
        add_labeled("TEL", t["value"], _type_params(t.get("label"), "TEL", t.get("pref"), version), t.get("label"))
    for a in c.get("addresses") or []:
        add_labeled("ADR", [a.get("pobox") or "", a.get("ext") or "", a.get("street") or "", a.get("city") or "",
                            a.get("region") or "", a.get("postcode") or "", a.get("country") or ""],
                    _type_params(a.get("label"), "ADR", a.get("pref"), version), a.get("label"))
    for u in c.get("urls") or []:
        add_labeled("URL", u["value"], _type_params(u.get("label"), "URL", 0, version), u.get("label"), "uri")
    for s in c.get("social") or []:
        svc = s.get("service") or "other"
        url = social_url(svc, s.get("value") or "")
        user = re.sub(r"^.*/(?:in/|@)?", "", url.rstrip("/")) if "://" in url else url
        out.append(Prop("X-SOCIALPROFILE", url, {"type": [APPLE_SOCIAL.get(svc, svc)], "x-user": [user]}, None, "uri"))
    for r in c.get("relations") or []:
        name = r.get("relatedFn") or r.get("relatedName") or ""
        t = r.get("type") or "other"
        if r.get("relatedUid"):
            out.append(Prop("RELATED", f"urn:uuid:{r['relatedUid']}",
                            {"type": [rel.vcard4_type(t)], "x-iocontact-type": [t]} if v4 else {"x-iocontact-type": [t]}, None, "uri"))
        elif v4 and name:
            out.append(Prop("RELATED", name, {"value": ["text"], "type": [rel.vcard4_type(t)], "x-iocontact-type": [t]}))
        if not v4 and name:
            g = grp()
            out.append(Prop("X-ABRELATEDNAMES", name, {}, g))
            lab = r.get("label") or rel.label(t, r.get("relatedGender") or r.get("gender"))
            apple = {"Father", "Mother", "Parent", "Brother", "Sister", "Child", "Son", "Daughter", "Friend", "Spouse",
                     "Husband", "Wife", "Partner", "Assistant", "Manager", "Other"}
            out.append(Prop("X-ABLabel", f"_$!<{lab}>!$_" if lab in apple else lab, {}, g))
    if c.get("tags"):
        out.append(Prop("CATEGORIES", list(c["tags"])))
    if c.get("notes"):
        out.append(Prop("NOTE", c["notes"]))
    if c.get("iopix") and c["iopix"].get("personId"):
        out.append(Prop("X-IOPIX-PERSON", c["iopix"].get("name") or "", {"x-id": [str(c["iopix"]["personId"])]}))
    if c.get("favorite"):
        out.append(Prop("X-IOCONTACT-FAVORITE", "1"))
    photo = c.get("photoData")
    if photo and photo.get("data"):
        b64 = base64.b64encode(photo["data"]).decode()
        if v4:
            out.append(Prop("PHOTO", f"data:{photo.get('type') or 'image/jpeg'};base64,{b64}", {}, None, "uri"))
        else:
            t = (photo.get("type") or "image/jpeg").split("/")[-1].upper()
            out.append(Prop("PHOTO", b64, {"encoding": ["b"], "type": [t]}, None, "binary"))
    for raw in c.get("extra") or []:
        p = _parse_line(raw)
        if p:
            p._raw = raw  # written exactly as received
            out.append(p)
    if c.get("updated"):
        out.append(Prop("REV", c["updated"], {}, None, "timestamp"))
    out.append(Prop("END", "VCARD"))
    return out


def _param_str(params: dict) -> str:
    s = ""
    for k, vals in params.items():
        vals = [re.sub(r'[\r\n"]+', " ", v) for v in vals]  # a parameter value holds no line break or quote (RFC 6350 3.3)
        vv = ",".join(f'"{v}"' if re.search(r'[:;,]', v) else v for v in vals)
        s += f";{k.upper()}={vv}"
    return s


def _line(p: Prop, version: str) -> str:
    if getattr(p, "_raw", None):
        return p._raw
    name = f"{p.group}.{p.name}" if p.group else p.name
    if p.name in ("BEGIN", "END", "VERSION", "PRODID", "REV", "UID", "BDAY", "ANNIVERSARY", "X-ABDATE", "PHOTO", "URL",
                  "X-SOCIALPROFILE", "RELATED") and isinstance(p.value, str):
        val = p.value if p.name not in ("PRODID",) else p.value
        if p.name == "RELATED" and (p.params.get("value") or [""])[0] == "text":
            val = escape(p.value)
    elif isinstance(p.value, list):
        sep = "," if p.name == "CATEGORIES" else ";"
        val = sep.join(escape(x) for x in p.value)
    else:
        val = escape(str(p.value)) if p.vtype == "text" else str(p.value)
    # what is not escaped (a URL, a UID, a profile...) cannot break the line and start a property of its own
    val = re.sub(r"[\r\n]+", " ", val)
    return f"{name}{_param_str(p.params)}:{val}"


def _fold(line: str) -> str:
    """Lines over 75 octets are folded (RFC 6350 3.2), without splitting a UTF-8 character."""
    b = line.encode()
    if len(b) <= 75:
        return line
    parts, cur, size = [], [], 0
    limit = 75
    for ch in line:
        n = len(ch.encode())
        if size + n > limit:
            parts.append("".join(cur))
            cur, size, limit = [], 0, 74
        cur.append(ch)
        size += n
    parts.append("".join(cur))
    return "\r\n ".join(parts)


# ------------------------------------------------------------------ jCard (RFC 7095)

def to_jcard(c: dict) -> list:
    props = []
    for p in _props(c, "4.0"):
        if p.name in ("BEGIN", "END"):
            continue
        if getattr(p, "_raw", None):
            pp = _parse_line(p._raw)
            if not pp:
                continue
            val = unescape(pp.value)
            props.append([pp.name.lower(), _jparams(pp), "unknown", val])
            continue
        params = _jparams(p)
        if p.name == "VERSION":
            props.append(["version", {}, "text", "4.0"])
            continue
        if p.name == "BDAY" or p.name == "ANNIVERSARY":
            s = p.value  # jCard writes dates with dashes: 1980-04-15, --04-15, 1980-04, 1980
            val = f"{s[:4]}-{s[4:6]}-{s[6:8]}" if len(s) == 8 and s.isdigit() else f"--{s[2:4]}-{s[4:6]}" if re.match(r"^--\d{4}$", s) else s
            props.append([p.name.lower(), params, "date", val])
            continue
        if isinstance(p.value, list):
            if p.name == "CATEGORIES":
                props.append([p.name.lower(), params, "text", *p.value])
            else:
                props.append([p.name.lower(), params, "text", list(p.value)])
        else:
            props.append([p.name.lower(), params, p.vtype if p.vtype in ("text", "uri", "date", "timestamp", "date-and-or-time") else "text", p.value])
    return ["vcard", props]


def _jparams(p: Prop) -> dict:
    out = {}
    if p.group:
        out["group"] = p.group
    for k, v in p.params.items():
        out[k] = v[0] if len(v) == 1 else v
    return out


def from_jcard(j) -> dict:
    """A jCard (["vcard", [...]]) as a contact dict, by way of vCard text."""
    if not (isinstance(j, list) and len(j) == 2 and j[0] == "vcard"):
        raise Invalid("Not a jCard")
    lines = ["BEGIN:VCARD", "VERSION:4.0"]
    for prop in j[1]:
        name, params, vtype, *vals = prop
        if name.lower() == "version":
            continue
        group = params.pop("group", None) if isinstance(params, dict) else None
        ps = {k: (v if isinstance(v, list) else [str(v)]) for k, v in (params or {}).items()}
        if name.lower() in ("bday", "anniversary") and vals and isinstance(vals[0], str):
            vals = [vals[0].replace("-", "") if re.match(r"^\d{4}-\d{2}-\d{2}$", vals[0]) else "--" + vals[0][2:].replace("-", "") if re.match(r"^--\d{2}-\d{2}$", vals[0]) else vals[0]]
        if len(vals) == 1 and isinstance(vals[0], list):
            val = ";".join(escape(str(x)) if not isinstance(x, list) else ",".join(escape(str(y)) for y in x) for x in vals[0])
        elif name.lower() == "categories":
            val = ",".join(escape(str(x)) for x in vals)
        else:
            val = escape(str(vals[0])) if vtype == "text" else str(vals[0])
        lines.append(f"{group + '.' if group else ''}{name.upper()}{_param_str(ps)}:{val}")
    lines.append("END:VCARD")
    return parse("\r\n".join(lines))[0]
