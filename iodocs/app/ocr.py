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


def _mrz_lines(text: str) -> list[str]:
    """The lines of the text that look like a machine-readable zone, cleaned up."""
    out = []
    for raw in (text or "").splitlines():
        s = raw.upper().replace("«", "<").replace("‹", "<").replace("(", "<").replace("[", "<").replace("{", "<")
        s = re.sub(r"\s+", "", s)
        s = re.sub(r"[^A-Z0-9<]", "", s)
        if len(s) >= 28 and (s.count("<") >= 2 or re.match(r"[PIACV][A-Z<][A-Z<]{3}", s)):
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
            r = {"code": a[:2], "country": a[2:5], "number": number, "birth": b[0:6], "birth_ok": _ok(b[0:6], b[6]),
                 "sex": b[7], "expiry": b[8:14], "expiry_ok": _ok(b[8:14], b[14]), "nationality": b[15:18],
                 "given": given, "surname": sur, "number_ok": ok_n}
            return _mrz_out(r)
        if not b:
            continue
        # TD3 (passports): two lines of 44; TD2 (some ID cards and visas): two lines of 36
        for n in (44, 36):
            if n - 3 <= len(a) <= n + 2 and n - 3 <= len(b) <= n + 2 and a[0] in "PIACV":
                a2, b2 = _fit(a, n), _fit(b, n)
                number, ok_n = _number(b2[0:9], b2[9])
                given, sur = _name(a2[5:])
                r = {"code": a2[:2], "country": a2[2:5], "number": number, "number_ok": ok_n, "nationality": b2[10:13],
                     "birth": b2[13:19], "birth_ok": _ok(b2[13:19], b2[19]), "sex": b2[20], "expiry": b2[21:27],
                     "expiry_ok": _ok(b2[21:27], b2[27]), "given": given, "surname": sur}
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
           "checked": bool(r["number_ok"] and r["birth_ok"] and r["expiry_ok"])}
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
_LBL_EXP = r"(?:exp(?:ires|iry|iration|\.)?(?:\s*date)?|date\s*of\s*expiry|valid\s*(?:until|thru|through|to)|good\s*thru|renewal\s*date|expiration|4b)"
_LBL_ISS = r"(?:iss(?:ued|ue)?(?:\s*(?:on|date))?|date\s*of\s*issue|issue\s*date|effective(?:\s*date)?|4a)"
_LBL_DOB = r"(?:dob|date\s*of\s*birth|birth\s*date|born)"
_LBL_NUM = (r"(?:policy\s*(?:no|number|#)|certificate\s*(?:no|number|#)|member\s*(?:id|no|number)|"
            r"licen[cs]e\s*(?:no|number|#)|lic\s*(?:no|#)|\bdln?\b|4d|document\s*(?:no|number)|passport\s*(?:no|number)|"
            r"card\s*(?:no|number)|registration\s*(?:no|number)|account\s*(?:no|number)|\bno\.)")
_PERIOD = re.compile(r"(?:policy|coverage|term)\s*(?:period|term|dates?)|effective\s*(?:dates?|from)", re.I)


def _after(text: str, label: str, want_date: bool = True, us: bool = True):
    """The first date (or number) written after the label, on its line or the next."""
    for m in re.finditer(label, text, re.I):
        rest = text[m.end():m.end() + 60]
        if want_date:
            d = parse_date(rest.split("\n\n")[0], us)
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
    if _score(text) < 6 and not lic:  # sideways or upside down: the turn that reads best
        best = (text, g)
        for angle in (90, 270, 180):
            r = g.rotate(angle, expand=True)
            t = _tess(r)
            if _score(t) > _score(best[0]):
                best = (t, r)
        text, g = best
    mrz = parse_mrz(text)
    if (not mrz or not mrz.get("checked")) and (_mrz_lines(text) or re.search(r"\bpass\s?port\b", text, re.I)):
        # the zone again, alone and with only its own characters
        bottom = g.crop((0, int(g.height * 0.55), g.width, g.height))
        again = parse_mrz(_tess(bottom, psm=6, mrz=True))
        if again and (not mrz or again.get("checked")):
            mrz = again
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
    found = from_text(text)
    source = "text" if found else None
    for facts, src in ((mrz, "mrz"), (lic, "barcode")):
        if facts:
            found = {**found, **{k: v for k, v in facts.items() if v is not None}}
            source = src
    return {"text": text.strip()[:200_000], "found": found, "source": source, "ocr": ocr_ran or bool(text)}
