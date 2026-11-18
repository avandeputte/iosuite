"""Reading a document off its scan: what is printed on it, and the facts that matter (its number, whose it is, when it
expires).

Three readers, the surest first:

- the barcode on the back of a US or Canadian driver's license or state ID (PDF417, the AAMVA standard): every field,
  exactly as the DMV wrote it (zxing-cpp; skipped when it is not installed);
- the machine-readable zone of a passport, an ID card or a visa (the two or three lines of <<< at the bottom, ICAO
  9303): the number, the names, the nationality, the birth and expiry dates, each checked against its check digit;
- the printed words (Tesseract, on this server: nothing leaves it), searched for labelled dates and numbers ("Expires
  03/14/2029", "Policy number H-55120", "Policy period 01/01/2026 to 01/01/2027") and the kind of document.

A PDF with text in it is read as it is; a scanned one is turned into pictures first (pdftoppm, from poppler-utils).
Nothing here touches the database: read() takes the bytes and gives back {text, found, ...}; app/files.py keeps it and
app/model.py applies it to the document.
"""
import datetime as dt
import io
import logging
import re
import shutil
import subprocess

from PIL import Image, ImageOps, UnidentifiedImageError

from app import config

log = logging.getLogger("iodocs.ocr")

TIMEOUT = 90          # seconds for one run of tesseract or pdftoppm
MAX_PAGES = 4         # pages of a scanned PDF that are read
MAX_SIDE = 3600       # a picture is made no larger than this before it is read
MIN_SIDE = 1600       # nor smaller (small photos read better made larger)
INK_SIDE = 4200       # the size the ink alone is read at (the small print under a passport's labels)
TEXT_PDF = 80         # characters a PDF's own text needs to be taken as it is


def tesseract() -> str | None:
    """The OCR program, when this server has it."""
    if (config.TESSERACT or "").lower() in ("off", "0", "no", "none"):
        return None
    return shutil.which(config.TESSERACT or "tesseract")


def available() -> dict:
    """What this server can read: {ocr, barcodes, pdf}."""
    import importlib.util
    bars = importlib.util.find_spec("zxingcpp") is not None
    return {"ocr": bool(tesseract()), "barcodes": bars, "pdf": bool(shutil.which("pdftoppm"))}


# ------------------------------------------------------------------ dates

MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}
MONTHS.update({"sept": 9, "janv": 1, "fev": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "aout": 8,
               "okt": 10, "dez": 12, "mrt": 3, "mei": 5, "maa": 3})
_MON = r"[A-Za-zéû]{3,9}\.?"
DATE = re.compile(
    r"(?P<iso>(?:19|20)\d\d[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01]))"
    r"|(?P<num>(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|[12]\d|3[01])[-/.](?:(?:19|20)\d\d|\d\d))(?!\d)"
    r"|(?P<dmy>(?:0?[1-9]|[12]\d|3[01])\s*(?:" + _MON + r")\s*(?:/\s*" + _MON + r"\s*)?,?\s*(?:19|20)\d\d)"
    r"|(?P<mdy>(?:" + _MON + r")\s*(?:0?[1-9]|[12]\d|3[01])(?:st|nd|rd|th)?,?\s*(?:19|20)\d\d)")


def _month(word: str) -> int | None:
    w = re.sub(r"[^a-zéû]", "", word.lower()).replace("é", "e").replace("û", "u")
    return MONTHS.get(w[:4]) or MONTHS.get(w[:3])


def _day(y: int, m: int, d: int) -> dt.date | None:
    try:
        x = dt.date(y, m, d)
    except ValueError:
        return None
    return x if 1900 <= x.year <= 2200 else None


def parse_date(s: str, us: bool = True) -> dt.date | None:
    """A day written any of the usual ways: 2029-03-14, 03/14/2029 (us: month first unless the first number is over
    12), 14.03.2029, 14 MAR 2029, 14 MAR/MARS 2029, March 14, 2029."""
    m = DATE.search(s or "")
    if not m:
        return None
    t = m.group(0)
    if m.group("iso"):
        y, mo, d = (int(x) for x in re.split(r"[-/.]", t))
        return _day(y, mo, d)
    if m.group("num"):
        a, b, y = (int(x) for x in re.split(r"[-/.]", t))
        y = y + (2000 if y < 70 else 1900) if y < 100 else y
        if "." in t or a > 12 or not us:
            a, b = b, a  # day first
        return _day(y, a, b) or _day(y, b, a)
    if m.group("dmy"):
        p = re.match(r"(\d+)\s*(" + _MON + r")", t)
        y = int(re.search(r"(19|20)\d\d$", t).group(0))
        mo = _month(p.group(2))
        return _day(y, mo, int(p.group(1))) if mo else None
    p = re.match(r"(" + _MON + r")\s*(\d+)", t)
    y = int(re.search(r"(19|20)\d\d$", t).group(0))
    mo = _month(p.group(1))
    return _day(y, mo, int(p.group(2))) if mo else None


# ------------------------------------------------------------------ the machine-readable zone (ICAO 9303)

COUNTRIES = {
    "USA": "United States", "CAN": "Canada", "MEX": "Mexico", "GBR": "United Kingdom", "IRL": "Ireland", "FRA": "France",
    "BEL": "Belgium", "NLD": "Netherlands", "LUX": "Luxembourg", "D": "Germany", "DEU": "Germany", "AUT": "Austria",
    "CHE": "Switzerland", "ITA": "Italy", "ESP": "Spain", "PRT": "Portugal", "DNK": "Denmark", "NOR": "Norway",
    "SWE": "Sweden", "FIN": "Finland", "ISL": "Iceland", "POL": "Poland", "CZE": "Czechia", "SVK": "Slovakia",
    "HUN": "Hungary", "ROU": "Romania", "BGR": "Bulgaria", "GRC": "Greece", "HRV": "Croatia", "SVN": "Slovenia",
    "EST": "Estonia", "LVA": "Latvia", "LTU": "Lithuania", "UKR": "Ukraine", "TUR": "Türkiye", "ISR": "Israel",
    "IND": "India", "CHN": "China", "JPN": "Japan", "KOR": "South Korea", "PHL": "Philippines", "VNM": "Vietnam",
    "AUS": "Australia", "NZL": "New Zealand", "ZAF": "South Africa", "BRA": "Brazil", "ARG": "Argentina", "COL": "Colombia",
    "CHL": "Chile", "PER": "Peru", "EGY": "Egypt", "MAR": "Morocco", "NGA": "Nigeria", "KEN": "Kenya", "SGP": "Singapore",
}
_WEIGHTS = (7, 3, 1)
_DIGITISH = str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5", "G": "6", "B": "8", "T": "7"})


def check_digit(s: str) -> str:
    total = 0
    for i, c in enumerate(s):
        v = int(c) if c.isdigit() else ord(c) - 55 if "A" <= c <= "Z" else 0
        total += v * _WEIGHTS[i % 3]
    return str(total % 10)


def _ok(field: str, digit: str) -> bool:
    return digit.translate(_DIGITISH) == check_digit(field)


def _digits(s: str) -> str:
    return s.translate(_DIGITISH)


def _mrz_date(s: str, future: bool) -> dt.date | None:
    s = _digits(s)
    if not re.fullmatch(r"\d{6}", s):
        return None
    yy, mm, dd = int(s[:2]), int(s[2:4]), int(s[4:])
    if future:  # an expiry: this century (a passport runs ten years at most)
        y = 2000 + yy
    else:       # a birth: the latest century that leaves it in the past
        y = 2000 + yy if 2000 + yy <= dt.date.today().year else 1900 + yy
    return _day(y, mm, dd)


# the second line of a passport's zone: birth date, its check digit, sex, expiry date (a US passport's often has a single
# < in it, since its number and personal number fill their fields)
_LINE2 = re.compile(r"[0-9OQDILZSGBT]{6}[0-9OQDILZSGBT<][MFX<][0-9OQDILZSGBT]{6}")


def _mrz_lines(text: str) -> list[str]:
    """The lines of the text that look like a machine-readable zone, cleaned up."""
    out = []
    for raw in (text or "").splitlines():
        s = raw.upper().replace("«", "<").replace("‹", "<").replace("(", "<").replace("[", "<").replace("{", "<")
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"[^A-Z0-9<]", "", s)
        if len(s) >= 28 and (s.count("<") >= 2 or re.match(r"[PIACV][A-Z<][A-Z<]{3}", s) or _LINE2.search(s)):
            out.append(s)
    return out


def _fit(s: str, n: int) -> str:
    return (s + "<" * n)[:n]


def _name(field: str) -> tuple[str, str]:
    """(given names, surname) of SURNAME<<GIVEN<NAMES, in the usual case."""
    sur, _, given = field.strip("<").partition("<<")
    words = given.split("<")
    tail = len(words)
    while tail and re.fullmatch(r"(C|K|L|E)\1*", words[tail - 1] or "C"):  # the filler <<< misread as CCC or KKK
        tail -= 1
    if any(len(w) >= 3 for w in words[tail:]):
        given = "<".join(words[:tail])
    clean = lambda x: " ".join(w.capitalize() for w in re.sub(r"<+", " ", x).replace("0", "O").split() if w)  # noqa: E731
    return clean(given), clean(sur)


def _country(code: str) -> str:
    code = code.replace("<", "")
    return COUNTRIES.get(code, code)


def _number(field: str, digit: str) -> tuple[str, bool]:
    """A document number and whether its check digit holds (after the usual misreadings, tried one at a time)."""
    if _ok(field, digit):
        return field.replace("<", ""), True
    if _ok(_digits(field), digit):
        return _digits(field).replace("<", ""), True
    return field.replace("<", ""), False


def parse_mrz(text: str) -> dict | None:
    """The facts of a passport's, an ID card's or a visa's machine-readable zone, found in the text; None without one.
    {kind, number, country, nationality, holder, given, surname, birthDate, sex, expiresOn, checked}"""
    lines = _mrz_lines(text)
    for i in range(len(lines)):
        a = lines[i]
        b = lines[i + 1] if i + 1 < len(lines) else ""
        c = lines[i + 2] if i + 2 < len(lines) else ""
        # TD1 (ID cards, the US passport card, residence cards): three lines of 30
        if c and 28 <= len(a) <= 32 and 28 <= len(b) <= 32 and 28 <= len(c) <= 32 and a[0] in "IACP":
            a, b, c = _fit(a, 30), _fit(b, 30), _fit(c, 30)
            number, ok_n = _number(a[5:14], a[14])
            given, sur = _name(c)
            r = {"names": c, "code": a[:2], "country": a[2:5], "number": number, "birth": b[0:6], "birth_ok": _ok(b[0:6], b[6]),
                 "sex": b[7], "expiry": b[8:14], "expiry_ok": _ok(b[8:14], b[14]), "nationality": b[15:18],
                 "given": given, "surname": sur, "number_ok": ok_n}
            return _mrz_out(r)
        if not b:
            continue
        # TD3 (passports): two lines of 44; TD2 (some ID cards and visas): two lines of 36
        for n in (44, 36):
            if n - 3 <= len(a) <= n + 2 and n - 3 <= len(b) <= n + 2 and a[0] in "PIACV":
                a2, b2 = _fit(a, n), _fit(b, n)
                if not (re.fullmatch(r"\d{6}", _digits(b2[13:19])) or re.fullmatch(r"\d{6}", _digits(b2[21:27]))):
                    continue  # a line of capitals above the zone, not its second line
                number, ok_n = _number(b2[0:9], b2[9])
                given, sur = _name(a2[5:])
                r = {"code": a2[:2], "country": a2[2:5], "number": number, "number_ok": ok_n, "nationality": b2[10:13],
                     "birth": b2[13:19], "birth_ok": _ok(b2[13:19], b2[19]), "sex": b2[20], "expiry": b2[21:27],
                     "expiry_ok": _ok(b2[21:27], b2[27]), "given": given, "surname": sur, "names": a2[5:]}
                return _mrz_out(r)
    return None


def _mrz_out(r: dict) -> dict | None:
    code = r["code"].replace("<", "")
    kind = ("passport" if code.startswith("P") else "visa" if code.startswith("V")
            else "residence" if code in ("C1", "IR", "AR", "RP") or (code.startswith("C") and r["country"] == "USA") else "id_card")
    if code == "IP" or (code.startswith("I") and r["country"] == "USA"):
        kind = "passport_card"
    holder = " ".join(x for x in (r["given"], r["surname"]) if x)
    out = {"kind": kind, "number": r["number"] or None, "country": _country(r["country"]), "holder": holder or None,
           "given": r["given"] or None, "surname": r["surname"] or None,
           "nationality": _country(r["nationality"]) or None, "sex": {"M": "M", "F": "F"}.get(r["sex"]),
           "birthDate": _mrz_date(r["birth"], False), "expiresOn": _mrz_date(r["expiry"], True),
           "checked": bool(r["number_ok"] and r["birth_ok"] and r["expiry_ok"]), "names": r.get("names")}
    if not (out["number"] or out["expiresOn"]):
        return None
    if not r["expiry_ok"] and out["expiresOn"] is None:
        out.pop("expiresOn")
    return out


# ------------------------------------------------------------------ the barcode of a North American license (AAMVA)

STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba", "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia", "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec", "SK": "Saskatchewan",
}


def _aamva_date(s: str, canada: bool) -> dt.date | None:
    s = re.sub(r"\D", "", s or "")[:8]
    if len(s) != 8:
        return None
    if canada or s[:2] in ("19", "20") and int(s[4:6] or 0) <= 31 and int(s[:4]) > 1900 and int(s[4:6] or 0) > 0 and int(s[2:4]) > 12:
        return _day(int(s[:4]), int(s[4:6]), int(s[6:]))
    return _day(int(s[4:]), int(s[:2]), int(s[2:4])) or _day(int(s[:4]), int(s[4:6]), int(s[6:]))


def parse_aamva(data: str) -> dict | None:
    """The fields of a driver's license or state ID barcode; None when the text is not one."""
    if not data or "ANSI" not in data[:40] and "AAMVA" not in data[:40] and not re.search(r"(?m)^(DL|ID)?DAQ", data):
        return None
    sub = "ID" if re.search(r"(?m)^IDD[A-Z]{2}|\nID\r?\n?DAQ|IDDAQ", data) and "DLDAQ" not in data else "DL"
    f = {}
    for line in re.split(r"[\r\n\x1e]+", data):
        if "ANSI" in line or "AAMVA" in line:  # the header, and the first field after the subfile's name on the same line
            h = re.search(r"(?:DL|ID)(?=DAQ|DCA|DCS|DAC|DBA|DBB|DCF|DAA)", line)
            line = line[h.end():] if h else ""
        m = re.match(r"(?:DL|ID|ZA|Z[A-Z])?(D[A-Z]{2})(.*)", line.strip())
        if m and m.group(1) not in f:
            f[m.group(1)] = m.group(2).strip()
    if "DAQ" not in f and "DBA" not in f:
        return None
    canada = f.get("DCG", "").upper().startswith("CAN")
    given = " ".join(x for x in (f.get("DAC") or f.get("DCT", "").replace(",", " "), f.get("DAD")) if x and x.upper() not in ("NONE", "UNAVL"))
    sur = f.get("DCS") or f.get("DAB") or ""
    if not (given or sur) and f.get("DAA"):
        sur, _, given = f["DAA"].partition(",")
    tc = lambda x: " ".join(w.capitalize() for w in re.split(r"[\s,]+", x or "") if w)  # noqa: E731
    state = f.get("DAJ", "").upper()
    address = ", ".join(tc(x) if i < 2 else x for i, x in enumerate((f.get("DAG"), f.get("DAI"), " ".join(y for y in (state, f.get("DAK", "")[:5]) if y))) if x)
    out = {"kind": "driver_license" if sub == "DL" else "id_card", "number": f.get("DAQ") or None,
           "issuer": STATES.get(state, state) or None, "country": "Canada" if canada else "United States",
           "holder": " ".join(x for x in (tc(given), tc(sur)) if x) or None, "given": tc(given) or None, "surname": tc(sur) or None,
           "birthDate": _aamva_date(f.get("DBB"), canada), "expiresOn": _aamva_date(f.get("DBA"), canada),
           "issuedOn": _aamva_date(f.get("DBD"), canada), "sex": {"1": "M", "2": "F", "M": "M", "F": "F"}.get(f.get("DBC", "")[:1]),
           "address": address or None, "class": f.get("DCA") or None,
           "restrictions": f.get("DCB") if f.get("DCB", "").upper() not in ("", "NONE") else None,
           "endorsements": f.get("DCD") if f.get("DCD", "").upper() not in ("", "NONE") else None,
           "checked": True}
    return out


def barcodes(im: Image.Image) -> list[str]:
    """The texts of the PDF417 (and QR) barcodes in a picture; [] without zxing-cpp."""
    try:
        import zxingcpp
    except ImportError:
        return []
    try:
        fmts = zxingcpp.BarcodeFormat.PDF417 | zxingcpp.BarcodeFormat.QRCode
        out = []
        for r in zxingcpp.read_barcodes(im, formats=fmts):
            raw = getattr(r, "bytes", None)
            t = raw.decode("latin-1") if raw else (r.text or "")
            for name, ch in (("<LF>", "\n"), ("<CR>", "\r"), ("<RS>", "\x1e"), ("<GS>", "\x1d")):  # as some versions spell them
                t = t.replace(name, ch)
            if t:
                out.append(t)
        return out
    except Exception as e:  # noqa: BLE001 - a picture it cannot read is no barcode
        log.debug("barcode reading failed: %s", e)
        return []


# ------------------------------------------------------------------ the printed words

KIND_WORDS = [  # (kind, pattern): the first that matches the text says what it is
    ("passport", r"\bpass\s?port\b|\bpasaporte\b|\bpasseport\b|\breisepass\b"),
    ("driver_license", r"driver'?s?\s*licen[cs]e|driving\s*licen[cs]e|\bdl\s*(no|#)|operator'?s?\s*licen[cs]e|permis\s*de\s*conduire|f[üu]hrerschein|rijbewijs"),
    ("residence", r"permanent\s*resident|resident\s*card|residence\s*permit|titre\s*de\s*s[ée]jour"),
    ("visa", r"\bvisa\b"),
    ("vehicle", r"vehicle\s*registration|registration\s*card|certificate\s*of\s*title|\bvin\b"),
    ("insurance", r"\binsurance\b|\binsured\b|\bpolicy\s*(number|no|period|holder)|declarations?\s*page|\bpremium\b"),
    ("birth", r"certificate\s*of\s*(live\s*)?birth|birth\s*certificate"),
    ("marriage", r"marriage\s*(certificate|license)|certificate\s*of\s*marriage"),
    ("medical", r"vaccination|immuni[sz]ation|vaccine|medical\s*card|health\s*card|medicare|medicaid"),
    ("id_card", r"identity\s*card|identification\s*card|carte\s*d'?identit[ée]|personalausweis|\bid\s*card\b"),
    ("property", r"\bdeed\b|lease\s*agreement|\bmortgage\b"),
    ("tax", r"\bform\s*w-?2\b|\b1099\b|tax\s*return|\birs\b"),
    ("education", r"\bdiploma\b|\btranscript\b|bachelor|master\s*of"),
]
# (\b and (?!ed): not "naissance", the French for birth, nor "expedición", the Spanish for issue, both on a US passport)
_LBL_EXP = r"(?:\bexp(?!ed)(?:ires|iry|iration|\.)?(?:\s*date)?|date\s*of\s*expiry|valid\s*(?:until|thru|through|to)|good\s*thru|renewal\s*date|expiration|\b4b\b)"
_LBL_ISS = r"(?:\biss(?:ued|ue)?(?:\s*(?:on|date))?|date\s*of\s*issue|issue\s*date|effective(?:\s*date)?|\b4a\b)"
_LBL_DOB = r"(?:dob|date\s*of\s*birth|birth\s*date|born)"
_LBL_NUM = (r"(?:policy\s*(?:no|number|#)|certificate\s*(?:no|number|#)|member\s*(?:id|no|number)|"
            r"licen[cs]e\s*(?:no|number|#)|lic\s*(?:no|#)|\bdln?\b|4d|document\s*(?:no|number)|passport\s*(?:no|number)|"
            r"card\s*(?:no|number)|registration\s*(?:no|number)|account\s*(?:no|number)|\bno\.)")
_PERIOD = re.compile(r"(?:policy|coverage|term)\s*(?:period|term|dates?)|effective\s*(?:dates?|from)", re.I)


def _after(text: str, label: str, want_date: bool = True, us: bool = True):
    """The first date (or number) written after the label, on its line or the next (OCR often puts an empty line
    between a label and what is written under it, as on a passport: "Date of issue/Date de délivrance/Fecha de
    expedición", then "24 JUL 2026")."""
    for m in re.finditer(label, text, re.I):
        rest = text[m.end():m.end() + 90]
        if want_date:
            para, _, more = rest.partition("\n\n")
            nxt = next((x for x in more.split("\n") if x.strip()), "")
            d = parse_date(para, us) or parse_date(nxt, us)
            if d:
                return d
        else:
            n = re.match(r"[\s.:#\-]*([A-Z0-9][A-Z0-9\-/ ]{2,24}[A-Z0-9])", rest, re.I)
            if n:
                words = re.sub(r"\s+", " ", n.group(1)).strip().split(" ")
                while words and not any(ch.isdigit() for ch in words[0]):  # "DLN 7654321", "No. 123": the label's tail
                    words.pop(0)
                v = " ".join(words)
                if sum(ch.isdigit() for ch in v) >= 3:
                    return words[0] if len(words[0]) >= 5 else v
    return None


def from_text(text: str) -> dict:
    """What the printed words say: {kind?, number?, issuedOn?, expiresOn?, birthDate?}."""
    t = text or ""
    low = t.lower()
    out = {}
    for kind, pat in KIND_WORDS:
        if re.search(pat, low):
            out["kind"] = kind
            break
    us = not re.search(r"\b(passeport|reisepass|paspoort|[ée]mis|g[üu]ltig|geldig)\b", low)
    p = _PERIOD.search(t)
    if p:  # "Policy period 01/01/2026 to 01/01/2027": the first two days after it
        dates = [d for d in (parse_date(m.group(0), us) for m in DATE.finditer(t[p.end():p.end() + 80])) if d]
        if len(dates) >= 2 and dates[0] < dates[1]:
            out["issuedOn"], out["expiresOn"] = dates[0], dates[1]
    out.setdefault("expiresOn", None)
    if not out.get("expiresOn"):
        out["expiresOn"] = _after(t, _LBL_EXP, True, us)
    if not out.get("issuedOn"):
        out["issuedOn"] = _after(t, _LBL_ISS, True, us)
    out["birthDate"] = _after(t, _LBL_DOB, True, us)
    out["number"] = _after(t, _LBL_NUM, False)
    return {k: v for k, v in out.items() if v}


_PAPERS = dict(KIND_WORDS)["passport"] + "|" + dict(KIND_WORDS)["id_card"]
_LBL_SUR = re.compile(r"\b(?:surname|last\s*name)\b", re.I)
_LBL_GIVEN = re.compile(r"\b(?:given\s*names?|first\s*names?)\b", re.I)
_CAPS = re.compile(r"[A-Z][A-Z'\-]*(?: [A-Z][A-Z'\-]*)*")


def _printed(text: str, label: re.Pattern) -> list[str]:
    """The words in capitals on the line under each such label ("Surname/Nom/Apellidos", then "DOE")."""
    out = []
    for m in label.finditer(text or ""):
        nxt = next((x for x in text[m.end():].split("\n")[1:4] if x.strip()), "")
        w = _CAPS.search(nxt)
        if w and w.group(0) not in out:
            out.append(w.group(0))
    return out


def _extras(field: str, sur: str, given: str) -> str | None:
    """The letters of the zone's name field that the printed names do not account for, or None when the printed names
    are not in it (the surname first, then the given names, in order)."""
    letters = re.sub(r"[^A-Z]", "", field or "")
    sur, given = re.sub(r"[^A-Z]", "", sur), re.sub(r"[^A-Z]", "", given)
    if not sur or not letters.startswith(sur):
        return None
    rest, extra, i = letters[len(sur):], [], 0
    for ch in rest:
        if i < len(given) and ch == given[i]:
            i += 1
        else:
            extra.append(ch)
    return "".join(extra) if i == len(given) else None


def better_names(mrz: dict, text: str) -> dict:
    """The zone's names put right from the printed ones when Tesseract read some of its <<< filler as letters (K, E, X,
    S, C, L): "DOE<K<JANE" for DOE<<JANE. Only when the printed names are the zone's own, letter for letter, in order."""
    if not mrz.get("names"):
        return mrz
    pairs = [(sur, given) for sur in _printed(text, _LBL_SUR) for given in _printed(text, _LBL_GIVEN) or [""]]
    for sur, given in pairs:
        extra = _extras(mrz["names"], sur, given)
        if extra is not None and all(ch in "KEXSCL" for ch in extra):
            break
    else:
        return mrz
    tc = lambda x: " ".join("-".join(p.capitalize() for p in w.split("-")) for w in x.split())  # noqa: E731
    out = {**mrz, "surname": tc(sur), "given": tc(given) if given else None}
    out["holder"] = " ".join(x for x in (out["given"], out["surname"]) if x)
    return out


_INNER = ("names", "dates")
_MON3 = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_WRITTEN = re.compile(r"(?<!\d)(\d\d)[ ./-]?(\d\d|[A-Za-z]{3})(?:/[A-Za-z]{3,4})?[ ./-]?(\d{4})(?!\d)")


def _years_before(expires: dt.date, years: int) -> dt.date:
    try:
        return expires.replace(year=expires.year - years)
    except ValueError:  # 29 February
        return expires.replace(year=expires.year - years, day=28)


def issued_from_expiry(text: str, expires: dt.date, times: int = 1) -> dt.date | None:
    """A passport's issue date, read against its checked expiry: passports run 10, 7 or 5 years (and some 6 or 3), and
    are issued the day after (or the day of) the same date that many years earlier. The day that fits is taken only when
    it is printed, and written out at least `times` times (each reading of the page adds its own copy: a figure
    misread once can make another day that fits, "10 04 2026" for a seven-year passport issued 10 04 2024)."""
    written = {}
    for m in _WRITTEN.finditer((text or "").upper()):
        w = m.group(1) + m.group(2) + m.group(3)
        written[w] = written.get(w, 0) + 1
    fits = []
    for years in (10, 7, 5, 6, 3):
        for later in (1, 0):
            d = _years_before(expires, years) + dt.timedelta(days=later)
            forms = {f"{d.day:02d}{d.month:02d}{d.year}", f"{d.month:02d}{d.day:02d}{d.year}", f"{d.day:02d}{_MON3[d.month - 1]}{d.year}"}
            if sum(written.get(f, 0) for f in forms) >= times and d not in fits:
                fits.append(d)
    return fits[0] if len(fits) == 1 else None


def _distance(a: str, b: str) -> int:
    """How many letters to change, add or take away to make one into the other (Levenshtein)."""
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]


def _names_part(field: str) -> str:
    """A zone's name field without its filler: the names end at the first <<< (two < at most part them), and what
    comes after it is filler misread as letters ("JOHN<<<<<<<CCESS<")."""
    return field.split("<<<")[0].strip("<")


def vote_names(found: list[dict]) -> dict | None:
    """The zone read best from several readings: those whose number and dates hold (check digits), and among them the
    names that agree most with the others' (Tesseract misreads a letter or a < differently each time)."""
    ok = [m for m in found if m and m.get("checked")]
    if not ok:
        return next((m for m in found if m), None)
    first = ok[0]
    same = [m for m in ok if (m["number"], m["expiresOn"]) == (first["number"], first["expiresOn"]) and m.get("names")]
    if len(same) < 2:
        return first
    parts = [_names_part(m["names"]) for m in same]
    best = min(range(len(parts)), key=lambda i: (sum(_distance(parts[i], p) for p in parts), "<<" not in parts[i]))
    given, sur = _name(parts[best])
    holder = " ".join(x for x in (given, sur) if x)
    return {**first, "given": given or None, "surname": sur or None, "holder": holder or None, "names": same[best]["names"]}


# ------------------------------------------------------------------ pictures and PDFs

def picture(raw: bytes) -> Image.Image | None:
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
        return ImageOps.exif_transpose(im)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def _prepared(im: Image.Image) -> Image.Image:
    g = im.convert("L")
    side = max(g.size)
    if side > MAX_SIDE:
        g.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    elif side < MIN_SIDE:
        f = MIN_SIDE / side
        g = g.resize((int(g.width * f), int(g.height * f)), Image.LANCZOS)
    return ImageOps.autocontrast(g, cutoff=1)


def _tess(im: Image.Image, psm: int = 3, mrz: bool = False) -> str:
    exe = tesseract()
    if not exe:
        return ""
    buf = io.BytesIO()
    im.save(buf, "PNG")
    cmd = [exe, "stdin", "stdout", "-l", config.OCR_LANGS or "eng", "--psm", str(psm)]
    if mrz:
        cmd = [exe, "stdin", "stdout", "-l", "eng", "--psm", str(psm), "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"]
    try:
        r = subprocess.run(cmd, input=buf.getvalue(), capture_output=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("tesseract did not finish: %s", e)
        return ""
    if r.returncode != 0:
        log.warning("tesseract: %s", r.stderr.decode("utf-8", "replace")[-300:])
    return r.stdout.decode("utf-8", "replace")


def _ink(im: Image.Image, level: float) -> Image.Image:
    """Only the printed ink of a picture, black on white: a passport's or an ID card's data is printed in black over a
    pale blue or green security pattern, which Tesseract otherwise reads as noise (and loses the dates in). The blue
    channel makes that pattern palest; level is a share of the Otsu threshold between ink and paper."""
    ch = im.split()[2] if im.mode == "RGB" else im.convert("L")
    ch = ImageOps.autocontrast(ch, cutoff=1)
    h = ch.histogram()
    total, s_all = sum(h), sum(i * n for i, n in enumerate(h))
    w = s = 0
    best, cut = -1.0, 128
    for t, n in enumerate(h):
        w += n
        if not w or w == total:
            continue
        s += t * n
        v = w * (total - w) * (s / w - (s_all - s) / (total - w)) ** 2
        if v > best:
            best, cut = v, t
    cut = int(cut * level)
    out = ch.point(lambda v: 255 if v > cut else 0)
    side = max(out.size)
    f = INK_SIDE / side
    return out.resize((int(out.width * f), int(out.height * f)), Image.LANCZOS) if f > 1 else out


def _words(im: Image.Image) -> list[tuple[int, int, int, int, str]]:
    """The words Tesseract finds in a picture, with their boxes: (left, top, width, height, text)."""
    exe = tesseract()
    if not exe:
        return []
    buf = io.BytesIO()
    im.save(buf, "PNG")
    try:
        r = subprocess.run([exe, "stdin", "stdout", "-l", "eng", "--psm", "3", "tsv"], input=buf.getvalue(),
                           capture_output=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired):
        return []
    out = []
    for line in r.stdout.decode("utf-8", "replace").splitlines()[1:]:
        c = line.split("\t")
        if len(c) >= 12 and c[11].strip():
            try:
                out.append((int(c[6]), int(c[7]), int(c[8]), int(c[9]), c[11].strip()))
            except ValueError:
                continue
    return out


def reread_dates(im: Image.Image, most: int = 8) -> str:
    """The dates on a picture read again one by one, each alone and large: small figures over a security pattern are
    misread in a reading of the whole page ("2026" for 2024) and seldom when read alone."""
    rgb = im.convert("RGB")
    ink = _ink(rgb, 0.75)
    f = ink.width / rgb.width
    words = _words(ink)
    blue = ImageOps.autocontrast(rgb.split()[2], cutoff=1)
    out = []
    for i, (left, top, w, h, word) in enumerate(words):
        if len(out) >= most:
            break
        if not re.fullmatch(r"[0-9OSIlZB]{4}[.,]?", word):
            continue
        row = [x for x in words[max(0, i - 2):i + 1] if abs(x[1] + x[3] / 2 - (top + h / 2)) < h]
        box = (int(min(x[0] for x in row) / f) - 6, int(min(x[1] for x in row) / f) - 6,
               int(max(x[0] + x[2] for x in row) / f) + 6, int(max(x[1] + x[3] for x in row) / f) + 6)
        c = blue.crop(box)
        if c.width < 8 or c.height < 4:
            continue
        c = c.resize((c.width * 3, c.height * 3), Image.LANCZOS)
        buf = io.BytesIO()
        c.save(buf, "PNG")
        try:
            r = subprocess.run([tesseract(), "stdin", "stdout", "-l", "eng", "--psm", "7", "-c",
                                "tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPRSTUVYabcdeghilnoprstuvy /."],
                               input=buf.getvalue(), capture_output=True, timeout=TIMEOUT)
        except (OSError, subprocess.TimeoutExpired):
            break
        t = r.stdout.decode("utf-8", "replace").strip()
        if t:
            out.append(t)
    return "\n".join(out)


def _score(text: str) -> int:
    return len(re.findall(r"[A-Za-z]{3,}", text))


def read_picture(im: Image.Image) -> tuple[str, dict | None, dict | None]:
    """(text, mrz facts, barcode facts) of one picture."""
    lic = None
    for code in barcodes(im):
        lic = parse_aamva(code)
        if lic:
            break
    g = _prepared(im)
    text = _tess(g)
    turn = 0
    if _score(text) < 6 and not lic:  # sideways or upside down: the turn that reads best
        best = (text, g, 0)
        for angle in (90, 270, 180):
            r = g.rotate(angle, expand=True)
            t = _tess(r)
            if _score(t) > _score(best[0]):
                best = (t, r, angle)
        text, g, turn = best
    zones = [parse_mrz(text)]
    if not zones[0] or not zones[0].get("checked"):
        # the zone again, alone and with only its own characters (also when the first reading saw no sign of one: on a
        # scan of the open booklet Tesseract can read the page above and skip the photo page altogether)
        bottom = g.crop((0, int(g.height * 0.55), g.width, g.height))
        zones.append(parse_mrz(_tess(bottom, psm=6, mrz=True)))
    mrz = vote_names(zones)
    if (mrz or re.search(_PAPERS, text, re.I)) and not lic:
        # a passport or an ID card: its dates again, from the ink alone, when the first reading lost them; the whole
        # picture, then its lower half (a scan of the open booklet: the photo page, whose zone is at the very bottom,
        # under the page facing it)
        rgb = im.convert("RGB").rotate(turn, expand=True) if turn else im.convert("RGB")
        w, h = rgb.size
        tries = [(rgb, 0.75), (rgb, 0.88), (rgb.crop((0, h // 2, w, h)), 0.75)]
        def settled():
            if mrz and mrz.get("checked"):
                return bool(issued_from_expiry(text, mrz["expiresOn"], 2))
            f = from_text(text)
            return bool(f.get("expiresOn") and f.get("issuedOn"))
        for part, level in tries:
            if settled():
                break
            more = _tess(_ink(part, level))
            text = text + "\n\n" + more
            zones.append(parse_mrz(more))
            mrz = vote_names(zones)
        if mrz and mrz.get("checked") and not settled():
            # the dates read again one by one: a reading of the whole page can misread a figure into another day
            # that also fits ("10 04 2026" for a seven-year passport issued 10 04 2024 fits a five-year one)
            mrz = {**mrz, "dates": reread_dates(rgb.crop((0, h // 2, w, h)))}
            text = text + "\n\n" + mrz["dates"]
    if not lic:  # a barcode on a turned picture
        for angle in (90, 270):
            for code in barcodes(im.rotate(angle, expand=True)):
                lic = parse_aamva(code)
                if lic:
                    break
            if lic:
                break
    return text, mrz, lic


def pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(raw))
        return "\n".join((p.extract_text() or "") for p in r.pages[:20])
    except Exception as e:  # noqa: BLE001 - a PDF pypdf cannot read is read as pictures
        log.debug("pdf text: %s", e)
        return ""


def pdf_pages(raw: bytes, pages: int = MAX_PAGES, dpi: int = 200) -> list[Image.Image]:
    """The first pages of a PDF as pictures (pdftoppm), else the pictures embedded in them (pypdf)."""
    exe = shutil.which("pdftoppm")
    out = []
    if exe:
        try:
            r = subprocess.run([exe, "-r", str(dpi), "-f", "1", "-l", str(pages), "-png", "-", "-"], input=raw,
                               capture_output=True, timeout=TIMEOUT)
            data = r.stdout
            sig = b"\x89PNG\r\n\x1a\n"
            for chunk in [c for c in data.split(sig) if c]:
                im = picture(sig + chunk)
                if im:
                    out.append(im)
            if out:
                return out
        except (OSError, subprocess.TimeoutExpired) as e:
            log.warning("pdftoppm did not finish: %s", e)
    try:
        from pypdf import PdfReader
        for p in PdfReader(io.BytesIO(raw)).pages[:pages]:
            for x in p.images[:2]:
                im = picture(x.data)
                if im:
                    out.append(im)
    except Exception as e:  # noqa: BLE001
        log.debug("pdf images: %s", e)
    return out


def read(raw: bytes, mime: str) -> dict:
    """{text, found, source, ocr}: what the file says and the facts made of it. found holds dates as date objects."""
    text, mrz, lic, ocr_ran = "", None, None, False
    if mime == "application/pdf":
        text = pdf_text(raw)
        if len(text.strip()) < TEXT_PDF:
            parts = []
            for im in pdf_pages(raw):
                t, m, b = read_picture(im)
                ocr_ran = True
                parts.append(t)
                mrz, lic = mrz or m, lic or b
            text = "\n".join(p for p in [text] + parts if p.strip())
        else:
            mrz = parse_mrz(text)
    else:
        im = picture(raw)
        if im is not None:
            text, mrz, lic = read_picture(im)
            ocr_ran = True
    if mrz:
        mrz = better_names(mrz, text)
    found = from_text(text)
    if mrz and mrz.get("expiresOn") and mrz.get("checked"):
        # the issue date in step with the checked expiry: read alone and large, or else in two readings of the page;
        # surer than the date under its label, which may have a figure misread
        fits = issued_from_expiry(mrz.get("dates") or "", mrz["expiresOn"]) or issued_from_expiry(text, mrz["expiresOn"], 2)
        if fits:
            found["issuedOn"] = fits
    if mrz:
        mrz = {k: v for k, v in mrz.items() if k not in _INNER}
    source = "text" if found else None
    for facts, src in ((mrz, "mrz"), (lic, "barcode")):
        if facts:
            found = {**found, **{k: v for k, v in facts.items() if v is not None}}
            source = src
    return {"text": text.strip()[:200_000], "found": found, "source": source, "ocr": ocr_ran or bool(text)}
