"""Reading passports and ID cards: a set of made-up ones, drawn here, laid out as different countries lay them out and
scanned or photographed the ways people do (the open booklet on a flatbed, a phone photo of the page, sideways, small).
No real document or person: every name, number and date is invented."""
import datetime as dt
import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from app import ocr

pytestmark = pytest.mark.skipif(not ocr.tesseract(), reason="needs tesseract")


def _font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    pytest.skip(f"needs one of the fonts {names}")


def sans(size):
    return _font(["DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"], size)


def zone_font(size):
    """OCR-B, the zone's own font (fonts-ocr-b), else a monospaced one."""
    return _font(["/usr/share/fonts/opentype/ocr-b/OCRB.otf", "OCRB.otf", "DejaVuSansMono.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"], size)


def yymmdd(d: dt.date) -> str:
    return d.strftime("%y%m%d")


def td3(country: str, surname: str, given: str, number: str, born: dt.date, sex: str, expires: dt.date, personal: str = ""):
    """The two lines of a passport's zone, with every check digit."""
    l1 = (f"P<{country}{surname.replace(' ', '<')}<<{given.replace(' ', '<')}" + "<" * 44)[:44]
    num = (number + "<" * 9)[:9]
    per = (personal + "<" * 14)[:14]
    l2 = (num + ocr.check_digit(num) + country + yymmdd(born) + ocr.check_digit(yymmdd(born)) + sex
          + yymmdd(expires) + ocr.check_digit(yymmdd(expires)) + per + ocr.check_digit(per))
    return l1, l2 + ocr.check_digit(l2[0:10] + l2[13:20] + l2[21:43])


def td1(country: str, surname: str, given: str, number: str, born: dt.date, sex: str, expires: dt.date):
    """The three lines of an ID card's zone."""
    num = (number + "<" * 9)[:9]
    l1 = (f"I<{country}{num}{ocr.check_digit(num)}" + "<" * 30)[:30]
    l2 = (yymmdd(born) + ocr.check_digit(yymmdd(born)) + sex + yymmdd(expires) + ocr.check_digit(yymmdd(expires))
          + country + "<" * 11)[:29]
    l2 += ocr.check_digit(l1[5:30] + l2[0:7] + l2[8:15] + l2[18:29])
    l3 = (f"{surname.replace(' ', '<')}<<{given.replace(' ', '<')}" + "<" * 30)[:30]
    return l1, l2, l3


def day_us(d: dt.date) -> str:
    return d.strftime("%d %b %Y").upper()


def day_eu(d: dt.date) -> str:
    return d.strftime("%d %m %Y")


def data_page(p: dict, width=1500, height=1060) -> Image.Image:
    """A passport's photo page: a pale security pattern, a photo box, labelled fields, the zone at the bottom."""
    im = Image.new("RGB", (width, height), p["paper"])
    dr = ImageDraw.Draw(im)
    for i in range(-height, width, 24):  # the guilloche
        dr.line([(i, 0), (i + height, height)], fill=p["pattern"], width=1)
        dr.line([(i + height, 0), (i, height)], fill=p["pattern"], width=1)
    dr.text((420, 30), p["title"], font=sans(34), fill=p["accent"])
    dr.rectangle([60, 130, 360, 520], fill=(200, 200, 205), outline=(150, 150, 160))  # the photo
    x, y = 420, 100
    for label, value in p["rows"]:
        dr.text((x, y), label, font=sans(18), fill=p["accent"])
        dr.text((x + 8, y + 22), value, font=sans(30), fill=(20, 20, 25))
        y += 66
    zone = p["zone"]
    zf = zone_font(42 if len(zone[0]) == 44 else 52)
    top = height - 60 * len(zone) - 30
    for i, line in enumerate(zone):
        dr.text((50, top + 60 * i), line, font=zf, fill=(15, 15, 20))
    return im


def us_passport(number="A12345678", surname="DOE", given="JANE ANN", born=dt.date(1980, 1, 1),
                issued=dt.date(2025, 3, 14), years=10, sex="F") -> tuple[dict, Image.Image]:
    expires = issued.replace(year=issued.year + years) - dt.timedelta(days=1)
    p = {"paper": (214, 226, 242), "pattern": (186, 202, 232), "accent": (60, 70, 120), "title": "UNITED STATES OF AMERICA",
         "rows": [("Passport No./No. du Passeport/No. de Pasaporte", number), ("Surname/Nom/Apellidos", surname),
                  ("Given names/Prénoms/Nombres", given), ("Date of birth/Date de naissance/Fecha de nacimiento", day_us(born)),
                  ("Date of issue/Date de délivrance/Fecha de expedición", day_us(issued)),
                  ("Date of expiration/Date d'expiration/Fecha de caducidad", day_us(expires))],
         "zone": td3("USA", surname, given, number, born, sex, expires, "9876543210123")}
    return {"number": number, "issuedOn": issued, "expiresOn": expires, "birthDate": born,
            "holder": f"{given.title()} {surname.title()}"}, data_page(p)


def eu_passport(number="XK1234567", surname="VAN DER BERG", given="ANNA MARIA", born=dt.date(1975, 6, 30),
                issued=dt.date(2024, 4, 10), years=7, country="UTO") -> tuple[dict, Image.Image]:
    expires = issued.replace(year=issued.year + years) - dt.timedelta(days=1)
    p = {"paper": (246, 228, 230), "pattern": (236, 204, 214), "accent": (140, 40, 90), "title": "UTOPIA  UTOPIE  UTOPIEN",
         "rows": [("N° du passeport/Passport no", number), ("1. Nom/Surname", surname), ("2. Prénoms/Given names", given),
                  ("4. Date de naissance/Date of birth", day_eu(born)), ("7. Date de délivrance/Date of issue", day_eu(issued)),
                  ("8. Date d'expiration/Date of expiry", day_eu(expires))],
         "zone": td3(country, surname, given, number, born, "F", expires)}
    return {"number": number, "issuedOn": issued, "expiresOn": expires, "birthDate": born,
            "holder": " ".join(w.title() for w in (given + " " + surname).split())}, data_page(p)


def booklet(page: Image.Image) -> Image.Image:
    """The open booklet on a flatbed: a busy page above the photo page."""
    w, h = page.size
    im = Image.new("RGB", (w, h * 2 + 20), (236, 236, 232))
    dr = ImageDraw.Draw(im)
    for y in range(60, h - 40, 34):
        dr.text((60, y), "WE THE PEOPLE OF UTOPIA, IN ORDER TO FORM A MORE PERFECT UNION " * 2, font=sans(16), fill=(150, 150, 160))
    im.paste(page, (0, h + 20))
    return im


def jpeg(im: Image.Image, quality=88) -> bytes:
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality)
    return out.getvalue()


def read(im: Image.Image) -> dict:
    got = ocr.read(jpeg(im), "image/jpeg")
    assert not set(got["found"]) & set(ocr._INNER), got["found"]
    return got["found"]


def check(found: dict, want: dict, issued=True):
    for k in ("number", "expiresOn", "birthDate", "holder"):
        assert found.get(k) == want[k], (k, found)
    if issued:
        assert found.get("issuedOn") == want["issuedOn"], found
    assert found["checked"] and found["kind"] == "passport"


# ---- the ways people scan and photograph them

def test_a_us_passport_booklet_on_a_flatbed():
    want, page = us_passport()
    check(read(booklet(page)), want)


def test_a_seven_year_passport_booklet():
    want, page = eu_passport()
    check(read(booklet(page)), want)


def test_a_five_year_childs_passport_photo_page():
    want, page = us_passport(number="C70224518", surname="ROE", given="TIM", born=dt.date(2016, 9, 2),
                             issued=dt.date(2023, 11, 20), years=5, sex="M")
    check(read(page), want)


def test_a_photo_with_the_page_high_up_in_it():
    want, page = eu_passport(number="ZZ9876543", surname="SMITH", given="JOHN", country="UTO")
    im = Image.new("RGB", (page.width, page.height * 2), (90, 80, 70))  # the table under it
    im.paste(page, (0, 80))
    check(read(im), want)


def test_a_photo_taken_sideways():
    want, page = us_passport(number="A55500011", surname="LEE", given="SAM")
    check(read(page.rotate(90, expand=True)), want, issued=False)


def test_a_small_phone_photo():
    want, page = us_passport(number="A40400404", surname="KIM", given="ALEX JO")
    small = page.resize((page.width * 2 // 3, page.height * 2 // 3), Image.LANCZOS)
    check(read(small), want, issued=False)


def test_an_id_card():
    born, expires = dt.date(1988, 2, 29), dt.date(2032, 5, 17)
    zone = td1("UTO", "DE LA CRUZ", "MARIA", "D23145890", born, "F", expires)
    card = Image.new("RGB", (1300, 820), (232, 238, 228))
    dr = ImageDraw.Draw(card)
    dr.text((60, 60), "IDENTITY CARD / CARTE D'IDENTITÉ", font=sans(36), fill=(40, 80, 60))
    for i, line in enumerate(zone):
        dr.text((70, 520 + 80 * i), line, font=zone_font(56), fill=(15, 15, 20))
    found = read(card)
    assert found["kind"] == "id_card" and found["number"] == "D23145890" and found["checked"], found
    assert found["expiresOn"] == expires and found["birthDate"] == born and found["holder"] == "Maria De La Cruz"


def test_a_letter_is_not_taken_for_a_passport():
    im = Image.new("RGB", (1400, 1800), "white")
    dr = ImageDraw.Draw(im)
    lines = ["ACME MUTUAL INSURANCE", "Policy Number: HO-5512-0098", "Policy period 01/01/2026 to 01/01/2027",
             "Dear policyholder, <<< please keep this letter >>> with your papers."] + ["Lorem ipsum dolor sit amet " * 3] * 20
    for i, t in enumerate(lines):
        dr.text((80, 80 + 60 * i), t, font=sans(28), fill="black")
    found = read(im)
    assert found.get("kind") == "insurance" and "checked" not in found and found.get("number") == "HO-5512-0098", found


# ---- the issue date: only when the readings agree

def test_the_issue_date_is_left_out_when_readings_disagree():
    exp = dt.date(2031, 4, 9)
    assert ocr.issued_from_expiry(["10 04 2024"], exp) == dt.date(2024, 4, 10)         # seven years
    assert ocr.issued_from_expiry(["10 APR 2021", "x"], exp) == dt.date(2021, 4, 10)   # ten years
    # one reading has a figure misread into a day a five-year passport would fit: not sure, so none
    assert ocr.issued_from_expiry(["10 04 2024", "10 04 2026", "10 04 2026"], exp) is None
    assert ocr.issued_from_expiry(["09 04 2031", "01 01 1990"], exp) is None           # the expiry is no issue date
    assert ocr.issued_from_expiry([], exp) is None


def test_the_zone_is_found_among_stray_lines():
    l1, l2 = td3("UTO", "DOE", "JOHN", "X98765432", dt.date(1990, 2, 15), "M", dt.date(2031, 4, 9))
    noise = "BEE<G0E06BNE42XIFAD646XFAORF86<4160B002E29<CIS"
    m = ocr.parse_mrz(f"{noise}\nJ {l1}\n<{l2}\n")
    assert m and m["checked"] and m["number"] == "X98765432" and m["holder"] == "John Doe", m


def test_a_booklet_scanned_upside_down():
    want, page = eu_passport(number="QR5550001", surname="NOVAK", given="EVA")
    check(read(booklet(page).rotate(180)), want, issued=False)
