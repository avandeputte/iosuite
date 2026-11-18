"""Demo data for iodocs (the iosuite_demo package): the Calloways' papers. Everyone's passport (Ava's about to run out,
Morgan's within its nine months), the parents' Oregon driver's licenses (Riley's due in six weeks), the children's
birth certificates, the marriage certificate, the house and car insurance, the car's registration, health cards,
Theo's vaccination record, a will kept private to the parents, and Riley's old passport, renewed. The scans are drawn
(marked SPECIMEN) with a machine-readable zone and a license barcode that ioDocs can read again; nothing real."""
import datetime as dt
import io

import iosuite_demo as demo

from app import files, model, ocr, users


def _font(size: int, bold: bool = False, mono: bool = False):
    from PIL import ImageFont
    for name in (("DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf") if mono else
                 ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"),):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _jpeg(img) -> bytes:
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88)
    return out.getvalue()


def _face(d, box, color):
    x0, y0, x1, y1 = box
    d.rectangle(box, fill=(225, 230, 236))
    cx, w = (x0 + x1) // 2, x1 - x0
    d.ellipse([cx - w // 4, y0 + w // 6, cx + w // 4, y0 + w // 6 + w // 2], fill=color)
    d.pieslice([x0 + w // 10, y1 - w // 2, x1 - w // 10, y1 + w // 3], 180, 360, fill=color)


def passport_page(p: dict, number: str, issued, expires) -> bytes:
    """The photo page of a made-up US passport, with a machine-readable zone whose check digits hold."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1600, 1100), (236, 241, 247))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1600, 110], fill=(28, 52, 98))
    d.text((50, 30), "PASSPORT   UNITED STATES OF AMERICA", font=_font(46, True), fill="white")
    _face(d, (60, 160, 470, 690), tuple(int(p["color"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))
    rows = [("Type / Code / Passport No.", f"P   USA   {number}"), ("Surname", demo.SURNAME.upper()), ("Given names", p["first"].upper()),
            ("Nationality", "UNITED STATES OF AMERICA"), ("Date of birth", demo.born(p).strftime("%d %b %Y").upper()),
            ("Sex", "F" if p["gender"] == "female" else "M"), ("Date of issue", issued.strftime("%d %b %Y").upper()),
            ("Date of expiration", expires.strftime("%d %b %Y").upper()), ("Authority", "United States Department of State")]
    y = 160
    for k, v in rows:
        d.text((520, y), k, font=_font(22), fill=(80, 90, 110))
        d.text((520, y + 26), v, font=_font(32, True), fill=(20, 24, 32))
        y += 64
    d.text((1150, 620), "SPECIMEN", font=_font(64, True), fill=(200, 60, 60))
    d.text((1150, 690), "ioSuite demo", font=_font(26), fill=(200, 60, 60))
    dob, exp = demo.born(p).strftime("%y%m%d"), expires.strftime("%y%m%d")
    sex = "F" if p["gender"] == "female" else "M"
    l2 = number + ocr.check_digit(number) + "USA" + dob + ocr.check_digit(dob) + sex + exp + ocr.check_digit(exp) + "<" * 15
    l2 = l2[:43] + ocr.check_digit(l2[0:10] + l2[13:20] + l2[21:43])
    l1 = (f"P<USA{demo.SURNAME.upper()}<<{p['first'].upper()}" + "<" * 44)[:44]
    d.rectangle([0, 900, 1600, 1100], fill=(250, 251, 252))
    d.text((40, 930), l1, font=_font(46, mono=True), fill="black")
    d.text((40, 1000), l2, font=_font(46, mono=True), fill="black")
    return _jpeg(img)


def license_front(p: dict, number: str, issued, expires) -> bytes:
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1500, 950), (229, 240, 232))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1500, 120], fill=(22, 96, 64))
    d.text((40, 30), "OREGON   DRIVER LICENSE", font=_font(52, True), fill="white")
    _face(d, (50, 170, 430, 660), tuple(int(p["color"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)))
    rows = [("4d DLN", number), ("1", demo.SURNAME.upper()), ("2", p["first"].upper()), ("8", "42 JUNIPER LANE, EUGENE OR 97405"),
            ("3 DOB", demo.born(p).strftime("%m/%d/%Y")), ("4b EXP", expires.strftime("%m/%d/%Y")), ("4a ISS", issued.strftime("%m/%d/%Y")),
            ("9 CLASS", "C")]
    y = 170
    for k, v in rows:
        d.text((480, y), k, font=_font(24), fill=(40, 90, 60))
        d.text((640, y - 6), v, font=_font(36, True), fill=(20, 24, 32))
        y += 70
    d.text((1000, 800), "SPECIMEN", font=_font(60, True), fill=(200, 60, 60))
    return _jpeg(img)


def license_back(p: dict, number: str, issued, expires) -> bytes | None:
    """The back: the AAMVA barcode with the same facts (None without zxing-cpp)."""
    try:
        import zxingcpp
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    sex = "2" if p["gender"] == "female" else "1"
    data = (f"@\n\x1e\rANSI 636029090002DL00410278ZO03190008DLDAQ{number}\nDCS{demo.SURNAME.upper()}\nDAC{p['first'].upper()}\n"
            f"DADNONE\nDBD{issued.strftime('%m%d%Y')}\nDBB{demo.born(p).strftime('%m%d%Y')}\nDBA{expires.strftime('%m%d%Y')}\n"
            f"DBC{sex}\nDAG42 JUNIPER LANE\nDAIEUGENE\nDAJOR\nDAK974050000\nDCAC\nDCBNONE\nDCDNONE\nDCGUSA\n\r")
    try:
        m = memoryview(zxingcpp.create_barcode(data, zxingcpp.BarcodeFormat.PDF417).to_image(scale=4))
        bar = Image.frombuffer("L", (m.shape[1], m.shape[0]), bytes(m), "raw", "L", 0, 1)
    except Exception:  # noqa: BLE001 - an older zxing-cpp makes no barcodes: no back then
        return None
    img = Image.new("RGB", (1500, 950), (246, 248, 246))
    img.paste(bar.convert("RGB").resize((1300, int(1300 * bar.height / bar.width))), (100, 260))
    ImageDraw.Draw(img).text((100, 120), "OREGON DMV   SPECIMEN", font=_font(40, True), fill=(22, 96, 64))
    return _jpeg(img)


def paper(title: str, lines: list[str], color: str = "#3b4a8c") -> bytes:
    """A one-page paper (a policy's declarations, a certificate) as a picture."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1240, 1600), "white")
    d = ImageDraw.Draw(img)
    rgb = tuple(int(color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    d.rectangle([0, 0, 1240, 150], fill=rgb)
    d.text((70, 45), title, font=_font(50, True), fill="white")
    y = 220
    for ln in lines:
        d.text((70, y), ln, font=_font(32, ln.isupper()), fill=(30, 34, 40))
        y += 58
    d.text((70, 1480), "SPECIMEN - made up for the ioSuite demo", font=_font(28, True), fill=(200, 60, 60))
    return _jpeg(img)


def seed(people: dict) -> None:
    m, r = users.get(people["morgan"]["id"]), users.get(people["riley"]["id"])
    fam = {p["key"]: p for p in demo.FAMILY}
    pid = {k: people[k]["id"] for k in people}

    def add(by, scans=(), **data):
        d = model.create(by, data)
        for name, raw in scans:
            if raw:
                files.add(by, d, raw, name, "image/jpeg")
        return d

    def passport(key, number, issued_days, expires_days, by=m):
        issued, expires = demo.day(issued_days), demo.day(expires_days)
        return add(by, [("Passport photo page.jpg", passport_page(fam[key], number, issued, expires))],
                   title=f"{fam[key]['first']}’s passport", kind="passport", number=number, issuer="U.S. Department of State",
                   country="United States", issuedOn=issued.isoformat(), expiresOn=expires.isoformat(), people=[pid[key]],
                   fields=[{"name": "Name", "value": demo.display_name(fam[key])},
                           {"name": "Date of birth", "value": demo.born(fam[key]).isoformat()},
                           {"name": "Nationality", "value": "United States"}])

    passport("morgan", "A31480261", -3400, 200)                 # within its nine months: "expiring"
    old = passport("riley", "A20577193", -3700, -20, by=r)      # ran out last month...
    model.renew(r, old, {"number": "B48810572", "issuedOn": demo.day(-35).isoformat(), "expiresOn": demo.day(3615).isoformat()})
    passport("ava", "C70224518", -1790, 40)                     # a child's passport, five years: renew now
    passport("theo", "C81153047", -700, 1120)

    for key, number, issued, expires, by in (("morgan", "7290315", -2200, 1100, m), ("riley", "5518842", -2900, 45, r)):
        iss, exp = demo.day(issued), demo.day(expires)
        add(by, [("License front.jpg", license_front(fam[key], number, iss, exp)), ("License back.jpg", license_back(fam[key], number, iss, exp))],
            title=f"{fam[key]['first']}’s driver’s license", kind="driver_license", number=number, issuer="Oregon",
            country="United States", issuedOn=iss.isoformat(), expiresOn=exp.isoformat(), people=[pid[key]],
            fields=[{"name": "Class", "value": "C"}, {"name": "Address", "value": "42 Juniper Lane, Eugene, OR 97405"}])

    for key in ("ava", "theo"):
        p = fam[key]
        add(m, [("Birth certificate.jpg", paper("CERTIFICATE OF LIVE BIRTH", [
            "State of Oregon - Center for Health Statistics", "", f"Name: {demo.display_name(p)}",
            f"Date of birth: {demo.born(p).strftime('%B %-d, %Y')}", "Place of birth: Eugene, Lane County, Oregon",
            "Parents: Morgan Calloway, Riley Calloway"], "#5f6b7a"))],
            title=f"{p['first']}’s birth certificate", kind="birth", issuer="Oregon Center for Health Statistics",
            country="United States", issuedOn=(demo.born(p) + dt.timedelta(days=12)).isoformat(), people=[pid[key]])
    add(m, [("Marriage certificate.jpg", paper("CERTIFICATE OF MARRIAGE", ["Lane County, Oregon", "",
        "Morgan Okafor and Riley Calloway", "were joined in marriage on June 14, 2010", "in Eugene, Oregon"], "#8a4b0f"))],
        title="Marriage certificate", kind="marriage", issuer="Lane County Clerk", country="United States",
        issuedOn="2010-06-18", people=[pid["morgan"], pid["riley"]])

    add(r, [("Declarations page.jpg", paper("JUNIPER MUTUAL - HOMEOWNERS POLICY", [
        "Declarations page", "", "Policy number: HO-4471-20931", f"Policy period: {demo.day(-200).strftime('%m/%d/%Y')} to {demo.day(165).strftime('%m/%d/%Y')}",
        "Named insured: Morgan and Riley Calloway", "Property: 42 Juniper Lane, Eugene OR 97405", "Dwelling: $520,000",
        "Personal property: $260,000", "Deductible: $1,000", "Claims: 1-800-555-0199"]))],
        title="Home insurance", kind="insurance", number="HO-4471-20931", issuer="Juniper Mutual", issuedOn=demo.day(-200).isoformat(),
        expiresOn=demo.day(165).isoformat(), visibility="family",
        fields=[{"name": "Claims phone", "value": "1-800-555-0199"}, {"name": "Deductible", "value": "$1,000"}])
    add(r, [("Insurance card.jpg", paper("CASCADE AUTO INSURANCE", ["Proof of insurance", "", "Policy number: CA-88120-77",
        f"Effective: {demo.day(-163).strftime('%m/%d/%Y')}  Expires: {demo.day(20).strftime('%m/%d/%Y')}",
        "Vehicle: Aurora Wayfarer Hybrid", "VIN AUR5WF1H7PX010203", "Drivers: Morgan Calloway, Riley Calloway"], "#0e7c86"))],
        title="Car insurance", kind="insurance", number="CA-88120-77", issuer="Cascade Auto Insurance",
        issuedOn=demo.day(-163).isoformat(), expiresOn=demo.day(20).isoformat(), people=[pid["morgan"], pid["riley"]],
        fields=[{"name": "Vehicle", "value": "Aurora Wayfarer Hybrid"}, {"name": "Roadside help", "value": "1-800-555-0177"}])
    add(r, title="Car registration", kind="vehicle", number="DEMO 042", issuer="Oregon DMV", country="United States",
        issuedOn=demo.day(-410).isoformat(), expiresOn=demo.day(320).isoformat(), people=[pid["morgan"], pid["riley"]],
        fields=[{"name": "Plate", "value": "DEMO 042"}, {"name": "VIN", "value": "AUR5WF1H7PX010203"}])
    for key in ("morgan", "riley", "ava", "theo"):
        add(m, title=f"{fam[key]['first']}’s health insurance card", kind="membership", number=f"WCH{900211 + len(key)}-0{len(key)}",
            issuer="Willamette Care Health Plan", people=[pid[key]], fields=[{"name": "Group", "value": "GRP-55120"}])
    add(m, [("Vaccination record.jpg", paper("IMMUNIZATION RECORD", [f"Name: {demo.display_name(fam['theo'])}",
        f"Date of birth: {demo.born(fam['theo']).isoformat()}", "", "DTaP: 5 doses (complete)", "MMR: 2 doses (complete)",
        "Polio: 4 doses (complete)", "Varicella: 2 doses (complete)", "Influenza: yearly"], "#146b5e"))],
        title="Theo’s vaccination record", kind="medical", issuer="Juniper Pediatrics", people=[pid["theo"]])
    add(m, title="Morgan’s Global Entry", kind="membership", number="98810233", issuer="U.S. Customs and Border Protection",
        issuedOn=demo.day(-1700).isoformat(), expiresOn=demo.day(130).isoformat(), people=[pid["morgan"]])
    add(m, title="Wills", kind="legal", issuer="Hale & Ortiz, attorneys", issuedOn=demo.day(-900).isoformat(),
        people=[pid["morgan"], pid["riley"]], visibility="private",
        notes="Originals in the safe deposit box at Cascade Credit Union, box 214. Executor: Daniel Okafor.")
    add(r, title="Ava’s school ID", kind="membership", number="JHS-2291", issuer="Juniper Hill Middle School",
        expiresOn=demo.day(230).isoformat(), people=[pid["ava"]])
