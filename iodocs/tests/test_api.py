"""The REST API: documents, whose they are, who sees which, files, expiry, renewing, and reading a scan."""
import datetime as dt
import io

import pytest
from PIL import Image, ImageDraw, ImageFont

from iosuite_shared import testing

from app import model, notify, ocr
from conftest import sign_in

TODAY = dt.date.today()


def new(client, **kw):
    r = client.post("/api/documents", json={"title": "Passport", "kind": "passport", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def png(w=40, h=30) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), (200, 80, 20)).save(out, "PNG")
    return out.getvalue()


def days(n: int) -> str:
    return (TODAY + dt.timedelta(days=n)).isoformat()


def test_documents_expiry_and_search(client):
    p = new(client, number="X1234567", issuer="U.S. Department of State", country="United States", issuedOn="2020-01-02",
            expiresOn=days(100), fields={"Nationality": "USA"})
    assert p["kindLabel"] == "Passport" and p["expiry"]["state"] == "soon" and p["expiry"]["days"] == 100  # nine months ahead
    assert p["remindDefault"] == 270 and p["fields"] == [{"name": "Nationality", "value": "USA"}] and p["visibility"] == "people"
    pol = new(client, title="Home insurance", kind="Insurance policy", number="HO-55", expiresOn=days(101), visibility="family")
    assert pol["kind"] == "insurance" and pol["expiry"]["state"] == "ok"  # a policy: a month ahead
    old = new(client, title="Old license", kind="driver_license", expiresOn=days(-3))
    assert old["expiry"]["state"] == "expired"
    birth = new(client, title="Birth certificate", kind="birth")
    assert birth["expiry"] is None and birth["remindDefault"] is None
    # a reminder of its own: none
    assert client.patch(f"/api/documents/{p['id']}", json={"remindDays": 0}).json()["expiry"]["state"] == "ok"
    client.patch(f"/api/documents/{p['id']}", json={"remindDays": ""})
    titles = lambda **q: [x["title"] for x in client.get("/api/documents", params=q).json()["items"]]  # noqa: E731
    assert titles() == ["Old license", "Passport", "Home insurance", "Birth certificate"]  # soonest first, none last
    assert titles(status="expiring") == ["Old license", "Passport"] and titles(status="expired") == ["Old license"]
    assert titles(q="x1234567") == ["Passport"] and titles(q="state department") == ["Passport"] and titles(q="state birth") == []
    assert titles(q="usa") == ["Passport"] and titles(kind="insurance") == ["Home insurance"]
    s = client.get("/api/summary").json()
    assert s["counts"] == {"documents": 4, "soon": 1, "expired": 1, "archived": 0,
                           "kinds": {"passport": 1, "insurance": 1, "driver_license": 1, "birth": 1}}
    assert any(k["key"] == "driver_license" and k["remind"] == 60 for k in s["kinds"]) and "ocr" in s["reads"]
    exp = client.get("/api/expiring", params={"start": days(0), "end": days(200)}).json()["items"]
    assert [x["title"] for x in exp] == ["Passport", "Home insurance"] and "number" not in exp[0]
    # renew: the new one takes over, the old one is archived and points to it
    r = client.post(f"/api/documents/{p['id']}/renew", json={"number": "Y7654321", "expiresOn": days(3650)})
    assert r.status_code == 201
    nw = r.json()
    assert nw["title"] == "Passport" and nw["issuer"] == "U.S. Department of State" and nw["expiry"]["state"] == "ok"
    gone = client.get(f"/api/documents/{p['id']}").json()
    assert gone["archived"] and gone["renewedBy"] == nw["id"]
    assert client.get(f"/api/documents/{nw['id']}").json()["renews"][0]["id"] == p["id"]
    assert titles(status="archived") == ["Passport"]
    assert client.post("/api/documents", json={"kind": "nonsense"}).status_code == 400
    assert client.post("/api/documents", json={"kind": "visa", "expiresOn": "soon"}).status_code == 400
    blank = client.post("/api/documents", json={"kind": "visa"}).json()
    assert blank["title"] == "Visa"
    assert client.delete(f"/api/documents/{nw['id']}").status_code == 200
    assert client.get(f"/api/documents/{p['id']}").json()["renewedBy"] is None


def test_who_sees_which_document(client):
    testing.add_account(client, {"name": "riley", "password": "secret123", "role": "editor", "displayName": "Riley Calloway"})
    testing.add_account(client, {"name": "ava", "password": "secret123", "role": "member", "displayName": "Ava Calloway"})
    testing.add_account(client, {"name": "theo", "password": "secret123", "role": "viewer", "displayName": "Theo Calloway"})
    testing.add_account(client, {"name": "sam", "password": "secret123", "role": "none"})
    ava_pass = new(client, title="Ava's passport", people=["ava"])
    alex_lic = new(client, title="Alex's license", kind="driver_license", people=["alex"])
    house = new(client, title="House insurance", kind="insurance", visibility="family")
    medical = new(client, title="Alex's medical record", kind="medical", people=["alex"], visibility="private")

    def seen(name):
        sign_in(client, name)
        return sorted(x["title"] for x in client.get("/api/documents").json()["items"])
    assert seen("alex") == sorted([ava_pass["title"], alex_lic["title"], house["title"], medical["title"]])
    assert seen("riley") == sorted([ava_pass["title"], alex_lic["title"], house["title"]])  # an editor: all but private
    assert client.get(f"/api/documents/{medical['id']}").status_code == 404
    assert client.patch(f"/api/documents/{alex_lic['id']}", json={"number": "1"}).status_code == 200  # editors change them
    assert seen("ava") == sorted([ava_pass["title"], house["title"]])  # a member: their own and the family's
    assert client.patch(f"/api/documents/{ava_pass['id']}", json={"number": "P1"}).status_code == 200  # theirs: they change it
    assert client.patch(f"/api/documents/{house['id']}", json={"number": "P1"}).status_code == 403
    assert client.get(f"/api/documents/{alex_lic['id']}").status_code == 404
    mine = client.post("/api/documents", json={"title": "Library card", "kind": "membership"}).json()
    assert mine["writable"] and mine["mine"]
    # a member cannot make a document disappear from themself
    assert client.patch(f"/api/documents/{mine['id']}", json={"visibility": "private", "people": ["theo"]}).status_code == 200
    assert seen("theo") == sorted(["House insurance", "Library card"])  # Theo's now (a viewer: theirs and the family's)
    assert client.patch(f"/api/documents/{house['id']}", json={"number": "X"}).status_code == 403
    assert client.post("/api/documents", json={"title": "x"}).status_code == 403
    client.cookies.clear()  # no role here: no way in
    assert client.post("/api/auth/login", json={"name": "sam", "password": "secret123"}).status_code == 403
    # the family and their counts are what each one sees
    sign_in(client, "riley")
    fam = {m["name"]: m["count"] for m in client.get("/api/summary").json()["family"]}
    assert fam["ava"] == 1 and fam["alex"] == 1


def test_files_and_the_cover(client):
    d = new(client)
    r = client.post(f"/api/documents/{d['id']}/files", params={"name": "front.png", "read": "false"}, content=png(800, 500),
                    headers={"content-type": "image/png"})
    assert r.status_code == 201, r.text
    f = r.json()["file"]
    assert f["thumb"] and f["mime"] == "image/png"
    got = client.get(f"/api/documents/{d['id']}").json()
    assert got["cover"] == f"api/documents/{d['id']}/files/{f['id']}" and got["files"][0]["name"] == "front.png"
    small = client.get(f"/api/documents/{d['id']}/files/{f['id']}", params={"size": "small"})
    assert small.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/documents/{d['id']}/files/{f['id']}").content == png(800, 500)
    html = client.post(f"/api/documents/{d['id']}/files", params={"name": "x.html"}, content=b"<script>1</script>",
                       headers={"content-type": "text/html"}).json()["file"]
    dl = client.get(f"/api/documents/{d['id']}/files/{html['id']}")
    assert dl.headers["content-type"] == "application/octet-stream" and "attachment" in dl.headers["content-disposition"]
    assert client.delete(f"/api/documents/{d['id']}/files/{f['id']}").status_code == 200
    assert client.get(f"/api/documents/{d['id']}").json()["cover"] is None


# ---- reading scans

def _passport_scan() -> bytes:
    mono = ImageFont.truetype("DejaVuSansMono.ttf", 34) if _font("DejaVuSansMono.ttf") else None
    sans = ImageFont.truetype("DejaVuSans.ttf", 30) if _font("DejaVuSans.ttf") else None
    number, dob, exp = "E12345678", "120315", (TODAY + dt.timedelta(days=200)).strftime("%y%m%d")
    l2 = number + ocr.check_digit(number) + "USA" + dob + ocr.check_digit(dob) + "F" + exp + ocr.check_digit(exp) + "<" * 15
    l2 = l2[:43] + ocr.check_digit(l2[0:10] + l2[13:20] + l2[21:43])
    l1 = ("P<USACALLOWAY<<AVA<GRACE" + "<" * 44)[:44]
    im = Image.new("RGB", (1700, 900), "white")
    dr = ImageDraw.Draw(im)
    dr.text((60, 60), "PASSPORT  UNITED STATES OF AMERICA", font=sans, fill="black")
    dr.text((60, 720), l1, font=mono, fill="black")
    dr.text((60, 780), l2, font=mono, fill="black")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=92)
    return out.getvalue()


def _font(name):
    try:
        ImageFont.truetype(name, 10)
        return True
    except OSError:
        return False


def test_the_machine_readable_zone_and_dates():
    number, dob, exp = "L898902C3", "740812", "120415"
    l2 = number + ocr.check_digit(number) + "UTO" + dob + ocr.check_digit(dob) + "F" + exp + ocr.check_digit(exp) + "ZE184226B<<<<<1"
    text = "some words\nP<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n" + l2.replace("0", "O", 1) + "\n"
    m = ocr.parse_mrz(text)
    assert m["kind"] == "passport" and m["surname"] == "Eriksson" and m["given"] == "Anna Maria" and m["sex"] == "F"
    assert m["birthDate"] == dt.date(1974, 8, 12) and m["expiresOn"] == dt.date(2012, 4, 15)
    td1 = ("I<UTOD231458907<<<<<<<<<<<<<<<\n7408122F1204159UTO<<<<<<<<<<<6\nERIKSSON<<ANNA<MARIA<<<<<<<<<<\n")
    m = ocr.parse_mrz(td1)
    assert m["kind"] == "id_card" and m["number"] == "D23145890" and m["checked"] and m["holder"] == "Anna Maria Eriksson"
    assert ocr.parse_date("14 MAR/MARS 2029") == dt.date(2029, 3, 14) and ocr.parse_date("03/14/2029") == dt.date(2029, 3, 14)
    assert ocr.parse_date("14.03.2029") == dt.date(2029, 3, 14) and ocr.parse_date("March 14th, 2029") == dt.date(2029, 3, 14)
    t = ocr.from_text("ACME Mutual Insurance\nPolicy Number: HO-5512-0098\nPolicy period 01/01/2026 to 01/01/2027\n")
    assert t == {"kind": "insurance", "number": "HO-5512-0098", "issuedOn": dt.date(2026, 1, 1), "expiresOn": dt.date(2027, 1, 1)}
    t = ocr.from_text("OREGON DRIVER LICENSE\n4d DLN 7654321\n4b EXP 03/14/2029  3 DOB 07/21/1981\n4a ISS 03/14/2021")
    assert t["kind"] == "driver_license" and t["number"] == "7654321" and t["expiresOn"] == dt.date(2029, 3, 14)
    assert t["birthDate"] == dt.date(1981, 7, 21) and t["issuedOn"] == dt.date(2021, 3, 14)


def _us_passport_zone(number: str, dob: str, exp: str, personal: str) -> str:
    """Line two of a made-up passport's zone, check digits and all; a full personal number leaves a single <."""
    l2 = number + ocr.check_digit(number) + "USA" + dob + ocr.check_digit(dob) + "F" + exp + ocr.check_digit(exp)
    l2 += (personal + "<" * 14)[:14] + ocr.check_digit((personal + "<" * 14)[:14])
    return l2 + ocr.check_digit(l2[0:10] + l2[13:20] + l2[21:43])


def test_a_us_passport_page_as_tesseract_reads_it():
    # made-up data, laid out as Tesseract gives back a scanned US passport: labels in three languages with an empty
    # line before each value, "naissance" and "expedición" in the labels, the zone's second line with one < only and
    # some of its first line's <<< filler read as K
    l2 = _us_passport_zone("A12345678", "800101", "350313", "9876543210123")
    assert l2.count("<") == 1
    text = ("PASSPORT\nPASSEPORT/PASAPORTE\n\nPassport No./No. du Passeport/No. de Pasaporte\n\nA12345678\n\n"
            "Surname/Nom/Apellidos\n\nDOE\n\nGiven names/Prénoms/Nombres\nJANE-ANN MARIE ”\n\n"
            "Date of birth/Date de naissance/Fecha de nacimiento\n\n01 JAN 1980\n\nSex/Sexe/Sexo\n\nF\n\n"
            "Date of issue/Date de délivrance/Fecha de expedición\n\n14 MAR 2025\n\n"
            "Date of expiration/Date d'expiration/Fecha de caducidad\n\n13 MAR 2035\n\n"
            "P<USADOE<K<JANE<KANN<MARIE<<<<<<<<<K<<<KK<<\n" + l2 + "\n\n"
            "IF YOUR PASSPORT EXPIRES WITHIN SIX MONTHS OF YOUR DATE OF DEPARTURE,\n")
    t = ocr.from_text(text)
    assert t["issuedOn"] == dt.date(2025, 3, 14) and t["expiresOn"] == dt.date(2035, 3, 13), t
    assert t["birthDate"] == dt.date(1980, 1, 1)
    m = ocr.parse_mrz(text)
    assert m and m["checked"] and m["number"] == "A12345678" and m["expiresOn"] == dt.date(2035, 3, 13), m
    m = ocr.better_names(m, text)
    assert m["holder"] == "Jane-Ann Marie Doe" and m["surname"] == "Doe"
    # printed names that are not the zone's own leave the zone's alone
    assert ocr.better_names({**m, "holder": "x"}, text.replace("\nDOE\n", "\nROE\n"))["holder"] == "x"
    # the issue date with its label lost: ten years less a day before the expiry
    assert ocr.issued_from_expiry("01 JAN 1980\n14 MAR 2025 -\n13 MAR 2035", dt.date(2035, 3, 13)) == dt.date(2025, 3, 14)
    assert ocr.issued_from_expiry("01 JAN 1980", dt.date(2035, 3, 13)) is None


def _patterned_passport_scan() -> bytes:
    """A made-up US passport page printed over a pale blue security pattern, the whole open booklet as a flatbed scan
    gives it (an endorsements page above)."""
    sans = ImageFont.truetype("DejaVuSans.ttf", 24)
    big = ImageFont.truetype("DejaVuSans.ttf", 34)
    mono = ImageFont.truetype("DejaVuSansMono.ttf", 40)
    im = Image.new("RGB", (1500, 2060), (214, 226, 242))
    dr = ImageDraw.Draw(im)
    for i in range(-2060, 1500, 24):  # the guilloche: fine pale blue lines every way
        dr.line([(i, 0), (i + 2060, 2060)], fill=(184, 200, 232), width=1)
        dr.line([(i + 2060, 0), (i, 2060)], fill=(188, 204, 234), width=1)
    for y in range(1100, 1800, 16):  # and the microprint behind the data
        dr.text((520, y), "UNITEDSTATESOFAMERICA" * 3, font=ImageFont.truetype("DejaVuSans.ttf", 10), fill=(172, 188, 226))
    dr.text((200, 60), "IF YOUR PASSPORT EXPIRES WITHIN SIX MONTHS OF YOUR DATE OF DEPARTURE,", font=sans, fill=(40, 60, 120))
    dr.text((420, 120), "Endorsements / Mentions Spéciales / Anotaciones", font=sans, fill=(40, 60, 120))
    dr.text((100, 1040), "PASSPORT", font=sans, fill=(60, 70, 110))
    dr.text((440, 1040), "THE UNITED STATES OF AMERICA", font=big, fill=(60, 70, 110))
    rows = [("Passport No./No. du Passeport/No. de Pasaporte", "A12345678"), ("Surname/Nom/Apellidos", "DOE"),
            ("Given names/Prénoms/Nombres", "JANE-ANN MARIE"), ("Nationality/Nationalité/Nacionalidad", "UNITED STATES OF AMERICA"),
            ("Date of birth/Date de naissance/Fecha de nacimiento", "01 JAN 1980"), ("Sex/Sexe/Sexo", "F"),
            ("Place of birth/Lieu de naissance/Lugar de nacimiento", "OREGON, U.S.A."),
            ("Date of issue/Date de délivrance/Fecha de expedición", "14 MAR 2025"),
            ("Date of expiration/Date d'expiration/Fecha de caducidad", "13 MAR 2035"),
            ("Authority/Autorité/Autoridad", "UNITED STATES DEPARTMENT OF STATE")]
    y = 1110
    for label, value in rows:
        dr.text((480, y), label, font=ImageFont.truetype("DejaVuSans.ttf", 18), fill=(70, 80, 120))
        dr.text((480, y + 24), value, font=big, fill=(20, 20, 25))
        y += 72
    l2 = _us_passport_zone("A12345678", "800101", "350313", "9876543210123")
    dr.text((60, 1880), ("P<USADOE<<JANE<ANN<MARIE" + "<" * 44)[:44], font=mono, fill=(15, 15, 20))
    dr.text((60, 1950), l2, font=mono, fill=(15, 15, 20))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=88)
    return out.getvalue()


@pytest.mark.skipif(not ocr.tesseract() or not _font("DejaVuSans.ttf"), reason="needs tesseract and DejaVu fonts")
def test_a_scanned_us_passport_booklet():
    got = ocr.read(_patterned_passport_scan(), "image/jpeg")
    f = got["found"]
    assert got["source"] == "mrz" and f["kind"] == "passport" and f["number"] == "A12345678", f
    assert f["expiresOn"] == dt.date(2035, 3, 13) and f["issuedOn"] == dt.date(2025, 3, 14), f
    assert f["holder"] == "Jane-Ann Marie Doe" and f["birthDate"] == dt.date(1980, 1, 1), f
    assert "names" not in f


AAMVA = ("@\n\x1e\rANSI 636029090002DL00410278ZO03190008DLDAQK1234567\nDCSCALLOWAY\nDACRILEY\nDADJANE\nDBD03142022\n"
         "DBB07211981\nDBA07212030\nDBC2\nDAG42 JUNIPER LANE\nDAIEUGENE\nDAJOR\nDAK974010000\nDCAC\nDCBNONE\nDCDNONE\nDCGUSA\n\r")


def test_a_license_barcode():
    f = ocr.parse_aamva(AAMVA)
    assert f["kind"] == "driver_license" and f["number"] == "K1234567" and f["issuer"] == "Oregon" and f["holder"] == "Riley Jane Calloway"
    assert f["expiresOn"] == dt.date(2030, 7, 21) and f["issuedOn"] == dt.date(2022, 3, 14) and f["birthDate"] == dt.date(1981, 7, 21)
    assert f["address"] == "42 Juniper Lane, Eugene, OR 97401" and f["class"] == "C" and f["restrictions"] is None


@pytest.mark.skipif(not ocr.tesseract(), reason="needs tesseract")
def test_a_scan_fills_the_document_in(client):
    testing.add_account(client, {"name": "ava", "password": "secret123", "role": "member", "displayName": "Ava Calloway"})
    d = client.post("/api/documents", json={}).json()
    assert d["title"] == model.NEW_TITLE and d["kind"] == "other"
    r = client.post(f"/api/documents/{d['id']}/files", params={"name": "passport.jpg"}, content=_passport_scan(),
                    headers={"content-type": "image/jpeg"})
    assert r.status_code == 201, r.text
    got = r.json()
    assert got["source"] == "mrz" and got["found"]["number"] == "E12345678", got
    assert {"Kind", "Number", "Expires on", "Whose", "Title", "Details"} <= set(got["filled"])
    doc = client.get(f"/api/documents/{d['id']}").json()
    assert doc["kind"] == "passport" and doc["title"] == "Ava’s passport" and [m["name"] for m in doc["people"]] == ["ava"]
    assert doc["expiresOn"] == days(200) and doc["country"] == "United States"
    assert {"name": "Date of birth", "value": "2012-03-15"} in doc["fields"] and {"name": "Sex", "value": "Female"} in doc["fields"]
    assert doc["files"][0]["read"] and doc["files"][0]["hasText"]
    # read again after a change: what differs is offered, not overwritten
    client.patch(f"/api/documents/{d['id']}", json={"number": "E00000000"})
    again = client.post(f"/api/documents/{d['id']}/files/{doc['files'][0]['id']}/read").json()
    assert again["filled"] == [] and {"field": "number", "label": "Number", "value": "E12345678", "current": "E00000000"} in again["differs"]
    assert client.get(f"/api/documents/{d['id']}").json()["number"] == "E00000000"
    # the words on the scan are found by the search
    assert [x["id"] for x in client.get("/api/documents", params={"q": "united states america"}).json()["items"]] == [d["id"]]
    text = client.get(f"/api/documents/{d['id']}/files/{doc['files'][0]['id']}/text").json()["text"]
    assert "PASSPORT" in text


def test_reminders_go_to_whose_it_is(client, monkeypatch):
    testing.add_account(client, {"name": "riley", "password": "secret123", "role": "editor"})
    testing.add_account(client, {"name": "ava", "password": "secret123", "role": "member"})
    new(client, title="Ava's passport", people=["ava"], expiresOn=days(270))   # its reminder starts today
    new(client, title="House insurance", kind="insurance", expiresOn=days(7))  # a week to go, nobody's
    new(client, title="Riley's license", kind="driver_license", people=["riley"], expiresOn=days(59))  # not today
    due = notify.due_on(TODAY)
    assert sorted(x["doc"]["title"] for x in due) == ["Ava's passport", "House insurance"]
    from app import users
    ava, riley = users.find("ava"), users.find("riley")
    assert [x["doc"]["title"] for x in notify.for_person(ava, due)] == ["Ava's passport"]
    assert [x["doc"]["title"] for x in notify.for_person(riley, due)] == ["House insurance"]
    sent = []
    from iosuite_shared import push
    monkeypatch.setattr(push, "recipients", lambda kind: [ava, riley])
    monkeypatch.setattr(push, "is_morning", lambda uid, now=None: True)
    monkeypatch.setattr(push, "was_sent", lambda uid, key: False)
    monkeypatch.setattr(push, "notify", lambda uid, kind, title, body="", url=None, once=None, tag=None: sent.append((uid, title)) or 1)
    assert notify.run() == 2
    assert (ava["id"], "Ava's passport expires on " + (TODAY + dt.timedelta(days=270)).strftime("%b %-d, %Y")) in sent
    assert (riley["id"], "House insurance expires in 7 days") in sent


def test_a_deleted_person_takes_their_papers(client):
    testing.add_account(client, {"name": "ava", "password": "secret123", "role": "member"})
    testing.add_account(client, {"name": "riley", "password": "secret123", "role": "member"})
    own = new(client, title="Ava's passport", people=["ava"])
    both = new(client, title="Joint policy", kind="insurance", people=["ava", "riley"])
    sign_in(client, "ava")
    added = client.post("/api/documents", json={"title": "Ava's notes", "kind": "other"}).json()
    fam = client.post("/api/documents", json={"title": "Wi-Fi card", "kind": "other", "visibility": "family"}).json()
    from app import persondata, users
    uid = users.find("ava")["id"]
    counts = {x["what"]: x["count"] for x in persondata.of(uid, False)}
    assert list(counts.values()) == [2, 1, 1]
    persondata.of(uid, True)
    assert model.get(own["id"]) is None and model.get(added["id"]) is None
    assert model.people_of([both["id"]])[both["id"]] == [users.find("riley")["id"]]
    assert model.get(fam["id"])["created_by"] is None
