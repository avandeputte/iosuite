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
