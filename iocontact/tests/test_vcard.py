from app import vcard

APPLE = """BEGIN:VCARD\r
VERSION:3.0\r
PRODID:-//Apple Inc.//iPhone OS 18.0//EN\r
N:Appleseed;Johnny;Q.;Dr.;Jr.\r
FN:Dr. Johnny Q. Appleseed Jr.\r
NICKNAME:Jo\r
ORG:Apple Inc.;Design\r
TITLE:Designer\r
EMAIL;type=INTERNET;type=HOME;type=pref:johnny@example.com\r
item1.EMAIL;type=INTERNET:jq@school.edu\r
item1.X-ABLabel:school\r
TEL;type=CELL;type=VOICE;type=pref:+1 (555) 000-1111\r
TEL;type=HOME;type=FAX:555-2222\r
item2.ADR;type=HOME;type=pref:;;1 Infinite Loop;Cupertino;CA;95014;United States\r
item2.X-ABADR:us\r
BDAY;X-APPLE-OMIT-YEAR=1604:1604-03-21\r
item3.X-ABDATE;type=pref:2010-09-04\r
item3.X-ABLabel:_$!<Anniversary>!$_\r
item4.X-ABRELATEDNAMES;type=pref:Jane Appleseed\r
item4.X-ABLabel:_$!<Sister>!$_\r
item5.X-ABRELATEDNAMES:Cousin Carl\r
item5.X-ABLabel:cousin\r
X-SOCIALPROFILE;type=linkedin;x-user=johnnyq:http://www.linkedin.com/in/johnnyq\r
X-SOCIALPROFILE;type=instagram;x-user=jq:x-apple:jq\r
item6.URL;type=pref:https://johnny.example\r
item6.X-ABLabel:_$!<HomePage>!$_\r
URL:https://www.facebook.com/johnny.q\r
NOTE:Line one\\nLine two\\, with comma\r
CATEGORIES:Family,Friends\r
X-CUSTOM-THING;foo=bar:keep me\r
PHOTO;ENCODING=b;TYPE=JPEG:/9j/4AAQ\r
END:VCARD\r
"""


def test_apple_card():
    c = vcard.parse(APPLE)[0]
    assert c["name"] == {"family": "Appleseed", "given": "Johnny", "additional": "Q.", "prefix": "Dr.", "suffix": "Jr."}
    assert c["org"] == "Apple Inc." and c["department"] == "Design"
    assert c["emails"][0] == {"label": "home", "value": "johnny@example.com", "pref": 1}
    assert c["emails"][1]["label"] == "school"
    assert c["phones"][1]["label"] == "home fax"
    assert c["addresses"][0]["city"] == "Cupertino"
    assert c["birthday"] == {"year": None, "month": 3, "day": 21}
    assert c["dates"] == [{"label": "anniversary", "year": 2010, "month": 9, "day": 4}]
    assert {(r["type"], r["relatedName"], r.get("gender")) for r in c["relations"]} == {("sibling", "Jane Appleseed", "F"), ("cousin", "Cousin Carl", None)}
    svc = {s["service"]: s["value"] for s in c["social"]}
    assert svc["linkedin"] == "http://www.linkedin.com/in/johnnyq" and svc["instagram"] == "jq" and "facebook" in svc
    assert c["urls"] == [{"label": "homepage", "value": "https://johnny.example"}]
    assert c["notes"] == "Line one\nLine two, with comma"
    assert c["tags"] == ["Family", "Friends"]
    assert c["photo"]["type"] == "image/jpeg"
    assert any("X-CUSTOM-THING" in x for x in c["extra"])


def test_roundtrip_both_versions():
    c = vcard.parse(APPLE)[0]
    c["photoData"] = c.pop("photo")
    for v in ("3.0", "4.0"):
        text = vcard.from_contact(c, v)
        assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
        back = vcard.parse(text)[0]
        assert back["name"] == c["name"]
        assert back["birthday"] == c["birthday"]
        assert back["dates"] == c["dates"]
        assert back["notes"] == c["notes"]
        assert sorted(e["value"] for e in back["emails"]) == sorted(e["value"] for e in c["emails"])
        assert sorted(s["service"] for s in back["social"]) == sorted(s["service"] for s in c["social"])
        assert {r["type"] for r in back["relations"]} == {"sibling", "cousin"}
        assert back["photo"]["data"] == c["photoData"]["data"]
        assert any("X-CUSTOM-THING" in x for x in back["extra"])


def test_vcard21_quoted_printable():
    text = "BEGIN:VCARD\r\nVERSION:2.1\r\nN;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:M=C3=BCller;J=C3=BCrgen\r\nTEL;CELL:123\r\nEND:VCARD\r\n"
    c = vcard.parse(text)[0]
    assert c["name"]["family"] == "Müller" and c["phones"][0]["label"] == "mobile"


def test_jcard_roundtrip():
    c = vcard.parse(APPLE)[0]
    j = vcard.to_jcard(c)
    assert j[0] == "vcard" and ["version", {}, "text", "4.0"] in j[1]
    back = vcard.from_jcard(j)
    assert back["name"] == c["name"] and back["birthday"] == c["birthday"]


def test_many_cards_and_folding():
    long = "x" * 200 + "é" * 50
    c = {"fn": long, "name": {"given": long}, "emails": [], "phones": []}
    text = vcard.from_contact(c) * 3
    cards = vcard.parse(text)
    assert len(cards) == 3 and cards[0]["fn"] == long


def test_partial_birthdays():
    """A birthday can be a year, a year and month, a month and day, or all three. vCard 4 writes each form as RFC 6350
    has it; vCard 3 has no partial dates, so a year (and month) travels in X-IOCONTACT-BDAY, which a full BDAY beats."""
    def card(bday, version="4.0"):
        return f"BEGIN:VCARD\r\nVERSION:{version}\r\nFN:Pat\r\n{bday}\r\nEND:VCARD\r\n"
    assert vcard.parse(card("BDAY:1980"))[0]["birthday"] == {"year": 1980, "month": None, "day": None}
    assert vcard.parse(card("BDAY:1980-05"))[0]["birthday"] == {"year": 1980, "month": 5, "day": None}
    assert vcard.parse(card("BDAY:--0517"))[0]["birthday"] == {"year": None, "month": 5, "day": 17}
    assert vcard.parse(card("BDAY:19800517"))[0]["birthday"] == {"year": 1980, "month": 5, "day": 17}
    assert vcard.parse(card("X-IOCONTACT-BDAY:1980", "3.0"))[0]["birthday"] == {"year": 1980, "month": None, "day": None}
    both = card("X-IOCONTACT-BDAY:1980\r\nBDAY:1981-05-17", "3.0")
    assert vcard.parse(both)[0]["birthday"] == {"year": 1981, "month": 5, "day": 17}
    for b, v4, v3 in (({"year": 1980, "month": None, "day": None}, "BDAY:1980", "X-IOCONTACT-BDAY:1980"),
                      ({"year": 1980, "month": 5, "day": None}, "BDAY:1980-05", "X-IOCONTACT-BDAY:1980-05"),
                      ({"year": None, "month": 5, "day": 17}, "BDAY:--0517", "BDAY;X-APPLE-OMIT-YEAR=1604:1604-05-17"),
                      ({"year": 1980, "month": 5, "day": 17}, "BDAY:19800517", "BDAY:1980-05-17")):
        c = {"fn": "Pat", "name": {"given": "Pat"}, "birthday": b}
        t4, t3 = vcard.from_contact(c, "4.0"), vcard.from_contact(c, "3.0")
        assert v4 in t4 and v3 in t3, (b, t4, t3)
        assert vcard.parse(t4)[0]["birthday"] == b and vcard.parse(t3)[0]["birthday"] == b
        if "X-IOCONTACT" in v3:
            assert "BDAY" not in t3.replace("X-IOCONTACT-BDAY", "")
        j = vcard.to_jcard(vcard.parse(t4)[0])
        assert vcard.from_jcard(j)["birthday"] == b
        jd = [p for p in j[1] if p[0] == "bday"][0][3]
        assert jd in ("1980", "1980-05", "--05-17", "1980-05-17"), jd


def test_a_line_that_is_kept_as_it_came_stays_the_same_however_often_the_card_is_saved():
    """What ioContact does not model is written back as received: escaped again, every save doubled its backslashes."""
    line = r"X-CUSTOM-THING;TYPE=home:one\, two\; three\\four\nfive"
    text = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ann Example\r\nN:Example;Ann;;;\r\nitem1." + line + "\r\nEND:VCARD\r\n"
    c = vcard.parse(text)[0]
    assert c["extra"] == ["item1." + line]
    for _ in range(3):
        c = vcard.parse(vcard.from_contact(c, "4.0"))[0]
    assert c["extra"] == ["item1." + line]
