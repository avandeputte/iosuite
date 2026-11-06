"""CSV import and export in Google Contacts' and Outlook's layouts (the two every other tool reads and writes).

Import recognises either layout (and Google's older one) from the header row; unknown columns are ignored.
"""
import csv
import io
import re

from app import relations as rel

# ------------------------------------------------------------------ dates


def _parse_date(s: str):
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$", s)  # 1980-04-15, 1980-04 or 1980
    if m:
        return int(m.group(1)), int(m.group(2)) if m.group(2) else None, int(m.group(3)) if m.group(3) else None
    m = re.match(r"^\s*-{1,2}\s*(\d{1,2})-(\d{1,2})$", s)  # Google's yearless " --04-15"
    if m:
        return None, int(m.group(1)), int(m.group(2))
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)       # Outlook (US): 4/15/1980
    if m:
        y = int(m.group(3))
        return (None if y in (1604, 1900) else y), int(m.group(1)), int(m.group(2))
    return None


def _date_out(y, m, d, style: str) -> str:
    """A date with unknown parts: Google reads 1980-04-15, 1980-04, 1980 and --04-15; Outlook only takes a full date
    (1604 stands for no year), so a date without a month and day is left out there."""
    if style == "outlook":
        return f"{m}/{d}/{y or 1604}" if m and d else ""
    if not y:
        return f"--{m:02d}-{d:02d}"
    return f"{y:04d}" + (f"-{m:02d}" if m else "") + (f"-{d:02d}" if d else "")


def _blank_contact() -> dict:
    return {"name": {}, "emails": [], "phones": [], "addresses": [], "urls": [], "social": [], "dates": [], "tags": [],
            "relations": []}


def _lab(s: str | None) -> str | None:
    s = (s or "").strip().strip("* ").lower()
    return {"": None, "mobile": "mobile", "cell": "mobile", "home": "home", "work": "work", "other": "other", "main": "main",
            "home fax": "home fax", "work fax": "work fax", "pager": "pager", "custom": None}.get(s, s or None)


# ------------------------------------------------------------------ import

def parse(text: str) -> list[dict]:
    text = text.lstrip("﻿")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        return []
    heads = set(rows[0].keys())
    if "E-mail Address" in heads or "Business Phone" in heads or "Home Street" in heads:
        return [c for c in (_outlook_row(r) for r in rows) if c]
    return [c for c in (_google_row(r) for r in rows) if c]


def _g(r: dict, *keys) -> str:
    for k in keys:
        v = r.get(k)
        if v and v.strip():
            return v.strip()
    return ""


def _google_row(r: dict) -> dict | None:
    c = _blank_contact()
    c["name"] = {"given": _g(r, "First Name", "Given Name"), "additional": _g(r, "Middle Name", "Additional Name"),
                 "family": _g(r, "Last Name", "Family Name"), "prefix": _g(r, "Name Prefix"), "suffix": _g(r, "Name Suffix")}
    c["fn"] = _g(r, "Name", "File As")
    c["nickname"] = _g(r, "Nickname") or None
    c["phoneticGiven"] = _g(r, "Phonetic First Name", "Given Name Yomi") or None
    c["phoneticFamily"] = _g(r, "Phonetic Last Name", "Family Name Yomi") or None
    c["org"] = _g(r, "Organization Name", "Organization 1 - Name") or None
    c["title"] = _g(r, "Organization Title", "Organization 1 - Title") or None
    c["department"] = _g(r, "Organization Department", "Organization 1 - Department") or None
    c["notes"] = _g(r, "Notes") or None
    g = _g(r, "Gender").lower()
    c["gender"] = "M" if g == "male" else "F" if g == "female" else None
    d = _parse_date(_g(r, "Birthday"))
    if d:
        c["birthday"] = {"year": d[0], "month": d[1], "day": d[2]}
    labels = _g(r, "Labels", "Group Membership")
    c["tags"] = [t.strip().lstrip("* ") for t in labels.split(":::") if t.strip() and t.strip() not in ("* myContacts", "myContacts", "* starred", "starred")]
    if "starred" in labels:
        c["favorite"] = True
    for i in range(1, 11):
        p = f"E-mail {i}"
        for v in (r.get(f"{p} - Value") or "").split(":::"):
            if v.strip():
                c["emails"].append({"label": _lab(r.get(f"{p} - Label") or r.get(f"{p} - Type")), "value": v.strip(), "pref": 0})
        p = f"Phone {i}"
        for v in (r.get(f"{p} - Value") or "").split(":::"):
            if v.strip():
                c["phones"].append({"label": _lab(r.get(f"{p} - Label") or r.get(f"{p} - Type")), "value": v.strip(), "pref": 0})
        p = f"Address {i}"
        a = {"label": _lab(r.get(f"{p} - Label") or r.get(f"{p} - Type")), "street": _g(r, f"{p} - Street"), "city": _g(r, f"{p} - City"),
             "pobox": _g(r, f"{p} - PO Box"), "region": _g(r, f"{p} - Region"), "postcode": _g(r, f"{p} - Postal Code"),
             "country": _g(r, f"{p} - Country"), "ext": _g(r, f"{p} - Extended Address")}
        if not any(v for k, v in a.items() if k != "label") and _g(r, f"{p} - Formatted"):
            a["street"] = _g(r, f"{p} - Formatted")
        if any(v for k, v in a.items() if k != "label"):
            c["addresses"].append(a)
        p = f"Website {i}"
        for v in (r.get(f"{p} - Value") or "").split(":::"):
            if v.strip():
                lab = _lab(r.get(f"{p} - Label") or r.get(f"{p} - Type"))
                from app.vcard import social_from_url
                svc = social_from_url(v) or (lab if lab in ("linkedin", "facebook", "instagram") else None)
                if svc:
                    c["social"].append({"service": svc, "value": v.strip()})
                else:
                    c["urls"].append({"label": lab, "value": v.strip()})
        p = f"Relation {i}"
        if _g(r, f"{p} - Value"):
            t, gnd = rel.from_label(_g(r, f"{p} - Label", f"{p} - Type"))
            c["relations"].append({"type": t, "gender": gnd, "relatedName": _g(r, f"{p} - Value")})
        p = f"Event {i}"
        d = _parse_date(_g(r, f"{p} - Value"))
        if d:
            c["dates"].append({"label": (_g(r, f"{p} - Label", f"{p} - Type") or "other").lower(), "year": d[0], "month": d[1], "day": d[2]})
    if not (c["fn"] or any(c["name"].values()) or c.get("org") or c["emails"] or c["phones"]):
        return None
    return c


OUTLOOK_PHONES = [("Mobile Phone", "mobile"), ("Home Phone", "home"), ("Home Phone 2", "home"), ("Business Phone", "work"),
                  ("Business Phone 2", "work"), ("Primary Phone", "main"), ("Company Main Phone", "main"), ("Other Phone", "other"),
                  ("Business Fax", "work fax"), ("Home Fax", "home fax"), ("Other Fax", "fax"), ("Pager", "pager"),
                  ("Car Phone", "car"), ("Assistant's Phone", "assistant")]
OUTLOOK_ADDR = [("Home", "home"), ("Business", "work"), ("Other", "other")]


def _outlook_row(r: dict) -> dict | None:
    c = _blank_contact()
    c["name"] = {"given": _g(r, "First Name"), "additional": _g(r, "Middle Name"), "family": _g(r, "Last Name"),
                 "prefix": _g(r, "Title"), "suffix": _g(r, "Suffix")}
    c["nickname"] = _g(r, "Nickname") or None
    c["org"] = _g(r, "Company") or None
    c["department"] = _g(r, "Department") or None
    c["title"] = _g(r, "Job Title") or None
    c["notes"] = _g(r, "Notes") or None
    g = _g(r, "Gender").lower()
    c["gender"] = "M" if g == "male" else "F" if g == "female" else None
    d = _parse_date(_g(r, "Birthday"))
    if d and not (d[0] is None and d[1] == 1 and d[2] == 0):
        c["birthday"] = {"year": d[0], "month": d[1], "day": d[2]}
    d = _parse_date(_g(r, "Anniversary"))
    if d:
        c["dates"].append({"label": "anniversary", "year": d[0], "month": d[1], "day": d[2]})
    for k in ("E-mail Address", "E-mail 2 Address", "E-mail 3 Address"):
        if _g(r, k):
            c["emails"].append({"label": None, "value": _g(r, k), "pref": 1 if k == "E-mail Address" else 0})
    for k, lab in OUTLOOK_PHONES:
        if _g(r, k):
            c["phones"].append({"label": lab, "value": _g(r, k), "pref": 0})
    for pre, lab in OUTLOOK_ADDR:
        a = {"label": lab, "street": "\n".join(x for x in (_g(r, f"{pre} Street"), _g(r, f"{pre} Street 2"), _g(r, f"{pre} Street 3")) if x),
             "city": _g(r, f"{pre} City"), "region": _g(r, f"{pre} State"), "postcode": _g(r, f"{pre} Postal Code"),
             "country": _g(r, f"{pre} Country/Region", f"{pre} Country"), "pobox": _g(r, f"{pre} PO Box")}
        if any(v for k, v in a.items() if k != "label"):
            c["addresses"].append(a)
    if _g(r, "Web Page"):
        from app.vcard import social_from_url
        v = _g(r, "Web Page")
        svc = social_from_url(v)
        (c["social"] if svc else c["urls"]).append({"service": svc, "value": v} if svc else {"label": None, "value": v})
    for k, t in (("Spouse", "spouse"), ("Manager's Name", "manager"), ("Assistant's Name", "assistant"), ("Children", "child")):
        for name in re.split(r"[;,]", _g(r, k)):
            if name.strip():
                c["relations"].append({"type": t, "relatedName": name.strip()})
    c["tags"] = [t.strip() for t in re.split(r"[;,]", _g(r, "Categories")) if t.strip()]
    if not (any(c["name"].values()) or c.get("org") or c["emails"] or c["phones"]):
        return None
    return c


# ------------------------------------------------------------------ export

def export_google(contacts: list[dict]) -> str:
    n = lambda key: max([len(c.get(key) or []) for c in contacts] + [1])  # noqa: E731
    ne, np, na, nw, nr, nv = n("emails"), n("phones"), n("addresses"), max(n("urls") + n("social"), 1), n("relations"), n("dates")
    head = ["First Name", "Middle Name", "Last Name", "Phonetic First Name", "Phonetic Last Name", "Name Prefix", "Name Suffix",
            "Nickname", "File As", "Organization Name", "Organization Title", "Organization Department", "Birthday", "Notes", "Labels"]
    for i in range(1, ne + 1):
        head += [f"E-mail {i} - Label", f"E-mail {i} - Value"]
    for i in range(1, np + 1):
        head += [f"Phone {i} - Label", f"Phone {i} - Value"]
    for i in range(1, na + 1):
        head += [f"Address {i} - Label", f"Address {i} - Formatted", f"Address {i} - Street", f"Address {i} - City",
                 f"Address {i} - PO Box", f"Address {i} - Region", f"Address {i} - Postal Code", f"Address {i} - Country",
                 f"Address {i} - Extended Address"]
    for i in range(1, nr + 1):
        head += [f"Relation {i} - Label", f"Relation {i} - Value"]
    for i in range(1, nw + 1):
        head += [f"Website {i} - Label", f"Website {i} - Value"]
    for i in range(1, nv + 1):
        head += [f"Event {i} - Label", f"Event {i} - Value"]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(head)
    for c in contacts:
        nm = c.get("name") or {}
        b = c.get("birthday")
        row = [nm.get("given"), nm.get("additional"), nm.get("family"), c.get("phoneticGiven"), c.get("phoneticFamily"),
               nm.get("prefix"), nm.get("suffix"), c.get("nickname"), c.get("fn"), c.get("org"), c.get("title"), c.get("department"),
               _date_out(b.get("year"), b["month"], b["day"], "google") if b else "", c.get("notes"),
               " ::: ".join(["* myContacts"] + (["* starred"] if c.get("favorite") else []) + list(c.get("tags") or []))]
        for i in range(ne):
            e = (c.get("emails") or [])[i] if i < len(c.get("emails") or []) else None
            row += [(e.get("label") or "").title() if e else "", e["value"] if e else ""]
        for i in range(np):
            e = (c.get("phones") or [])[i] if i < len(c.get("phones") or []) else None
            row += [(e.get("label") or "").title() if e else "", e["value"] if e else ""]
        for i in range(na):
            a = (c.get("addresses") or [])[i] if i < len(c.get("addresses") or []) else None
            if a:
                fmt = "\n".join(x for x in (a.get("street"), " ".join(x for x in (a.get("city"), a.get("region"), a.get("postcode")) if x), a.get("country")) if x)
                row += [(a.get("label") or "").title(), fmt, a.get("street"), a.get("city"), a.get("pobox"), a.get("region"),
                        a.get("postcode"), a.get("country"), a.get("ext")]
            else:
                row += [""] * 9
        rels = c.get("relations") or []
        for i in range(nr):
            r = rels[i] if i < len(rels) else None
            row += [r.get("typeLabel") or rel.label(r["type"], r.get("relatedGender")) if r else "", (r.get("relatedFn") or r.get("relatedName") or "") if r else ""]
        webs = [((u.get("label") or "").title(), u["value"]) for u in c.get("urls") or []] + \
               [(s["service"].title(), s["value"]) for s in c.get("social") or []]
        for i in range(nw):
            row += list(webs[i]) if i < len(webs) else ["", ""]
        dates = c.get("dates") or []
        for i in range(nv):
            d = dates[i] if i < len(dates) else None
            row += [d["label"].title(), _date_out(d.get("year"), d["month"], d["day"], "google")] if d else ["", ""]
        w.writerow(["" if x is None else x for x in row])
    return out.getvalue()


OUTLOOK_HEAD = ["Title", "First Name", "Middle Name", "Last Name", "Suffix", "Nickname", "Company", "Department", "Job Title",
                "Business Street", "Business City", "Business State", "Business Postal Code", "Business Country/Region",
                "Home Street", "Home City", "Home State", "Home Postal Code", "Home Country/Region",
                "Other Street", "Other City", "Other State", "Other Postal Code", "Other Country/Region",
                "Business Fax", "Business Phone", "Business Phone 2", "Home Fax", "Home Phone", "Home Phone 2", "Mobile Phone",
                "Other Phone", "Pager", "Primary Phone", "Anniversary", "Assistant's Name", "Birthday", "Categories", "Children",
                "E-mail Address", "E-mail 2 Address", "E-mail 3 Address", "Gender", "Manager's Name", "Notes", "Spouse", "Web Page"]


def export_outlook(contacts: list[dict]) -> str:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=OUTLOOK_HEAD)
    w.writeheader()
    for c in contacts:
        nm = c.get("name") or {}
        row = {"Title": nm.get("prefix"), "First Name": nm.get("given"), "Middle Name": nm.get("additional"),
               "Last Name": nm.get("family"), "Suffix": nm.get("suffix"), "Nickname": c.get("nickname"), "Company": c.get("org"),
               "Department": c.get("department"), "Job Title": c.get("title"), "Notes": c.get("notes"),
               "Categories": ";".join(c.get("tags") or []),
               "Gender": {"M": "Male", "F": "Female"}.get(c.get("gender") or "", "Unspecified")}
        b = c.get("birthday")
        if b:
            row["Birthday"] = _date_out(b.get("year"), b["month"], b["day"], "outlook")
        for d in c.get("dates") or []:
            if d["label"] == "anniversary":
                row["Anniversary"] = _date_out(d.get("year"), d["month"], d["day"], "outlook")
        for i, e in enumerate((c.get("emails") or [])[:3]):
            row[["E-mail Address", "E-mail 2 Address", "E-mail 3 Address"][i]] = e["value"]
        slots = {"mobile": ["Mobile Phone"], "iphone": ["Mobile Phone"], "home": ["Home Phone", "Home Phone 2"],
                 "work": ["Business Phone", "Business Phone 2"], "home fax": ["Home Fax"], "work fax": ["Business Fax"],
                 "fax": ["Business Fax"], "pager": ["Pager"], "main": ["Primary Phone"]}
        for p in c.get("phones") or []:
            for col in slots.get((p.get("label") or "").lower(), []) + ["Other Phone"]:
                if not row.get(col):
                    row[col] = p["value"]
                    break
        for a in c.get("addresses") or []:
            pre = {"home": "Home", "work": "Business"}.get((a.get("label") or "").lower(), "Other")
            if row.get(f"{pre} Street") or row.get(f"{pre} City"):
                pre = "Other"
            if row.get(f"{pre} Street") or row.get(f"{pre} City"):
                continue
            row.update({f"{pre} Street": a.get("street"), f"{pre} City": a.get("city"), f"{pre} State": a.get("region"),
                        f"{pre} Postal Code": a.get("postcode"), f"{pre} Country/Region": a.get("country")})
        webs = [u["value"] for u in c.get("urls") or []] + [s["value"] for s in c.get("social") or []]
        if webs:
            row["Web Page"] = webs[0]
        for r in c.get("relations") or []:
            name = r.get("relatedFn") or r.get("relatedName")
            col = {"spouse": "Spouse", "partner": "Spouse", "manager": "Manager's Name", "assistant": "Assistant's Name", "child": "Children"}.get(r["type"])
            if col and name:
                row[col] = f"{row[col]};{name}" if row.get(col) else name
        w.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return out.getvalue()
