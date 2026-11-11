import re

PF = """<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav" xmlns:cs="http://calendarserver.org/ns/">
<d:prop><d:current-user-principal/><card:addressbook-home-set/><d:resourcetype/><d:displayname/><cs:getctag/><d:sync-token/><d:getetag/></d:prop></d:propfind>"""


def dav(c, method, path, body=None, depth="1", **h):
    headers = {"Depth": depth, "Content-Type": "application/xml", **h}
    return c.request(method, path, content=body, headers=headers, auth=("alex", "secret123"))


def test_discovery_and_sync(client, family_id):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)  # no lifespan: the session's app is already running
    assert c.request("PROPFIND", "/dav/").status_code == 401
    assert c.request("PROPFIND", "/.well-known/carddav", follow_redirects=False).status_code == 301
    r = dav(c, "PROPFIND", "/dav/", PF, depth="0")
    assert r.status_code == 207 and "/dav/principals/alex/" in r.text
    r = dav(c, "PROPFIND", "/dav/principals/alex/", PF, depth="0")
    assert "/dav/addressbooks/alex/" in r.text
    r = dav(c, "PROPFIND", "/dav/addressbooks/alex/", PF)
    assert "/dav/addressbooks/alex/family/" in r.text and "addressbook" in r.text and "/dav/addressbooks/alex/personal/" in r.text
    tok0 = re.search(r"<d:sync-token>([^<]+)</d:sync-token>", r.text).group(1)
    assert dav(c, "PROPFIND", "/dav/addressbooks/bob/", PF).status_code == 403

    card = "BEGIN:VCARD\r\nVERSION:3.0\r\nUID:abc-123\r\nFN:Dav Person\r\nN:Person;Dav;;;\r\nEMAIL;TYPE=INTERNET:dav@x.org\r\nEND:VCARD\r\n"
    r = c.put("/dav/addressbooks/alex/family/abc-123.vcf", content=card, headers={"Content-Type": "text/vcard", "If-None-Match": "*"},
              auth=("alex", "secret123"))
    assert r.status_code == 201
    etag = r.headers["etag"]
    r = c.put("/dav/addressbooks/alex/family/abc-123.vcf", content=card, headers={"If-None-Match": "*"}, auth=("alex", "secret123"))
    assert r.status_code == 412
    r = c.put("/dav/addressbooks/alex/family/other.vcf", content=card, auth=("alex", "secret123"))
    assert r.status_code == 409  # same UID twice
    r = c.get("/dav/addressbooks/alex/family/abc-123.vcf", auth=("alex", "secret123"))
    assert r.status_code == 200 and "FN:Dav Person" in r.text and r.headers["etag"] == etag
    r = c.get("/dav/addressbooks/alex/family/abc-123.vcf", headers={"Accept": "text/vcard; version=4.0"}, auth=("alex", "secret123"))
    assert "VERSION:4.0" in r.text

    sync = f"""<d:sync-collection xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:sync-token>{tok0}</d:sync-token>
    <d:sync-level>1</d:sync-level><d:prop><d:getetag/></d:prop></d:sync-collection>"""
    r = dav(c, "REPORT", "/dav/addressbooks/alex/family/", sync)
    assert r.status_code == 207 and "abc-123.vcf" in r.text
    tok1 = re.search(r"<d:sync-token>([^<]+)</d:sync-token>", r.text).group(1)

    mg = """<card:addressbook-multiget xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><d:getetag/>
    <card:address-data content-type="text/vcard" version="4.0"/></d:prop><d:href>/dav/addressbooks/alex/family/abc-123.vcf</d:href>
    <d:href>/dav/addressbooks/alex/family/nope.vcf</d:href></card:addressbook-multiget>"""
    r = dav(c, "REPORT", "/dav/addressbooks/alex/family/", mg)
    assert "VERSION:4.0" in r.text and "404 Not Found" in r.text

    qy = """<card:addressbook-query xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav"><d:prop><d:getetag/></d:prop>
    <card:filter><card:prop-filter name="EMAIL"><card:text-match match-type="contains">dav@</card:text-match></card:prop-filter></card:filter>
    </card:addressbook-query>"""
    r = dav(c, "REPORT", "/dav/addressbooks/alex/family/", qy)
    assert "abc-123.vcf" in r.text

    r = c.delete("/dav/addressbooks/alex/family/abc-123.vcf", auth=("alex", "secret123"))
    assert r.status_code == 204
    r = dav(c, "REPORT", "/dav/addressbooks/alex/family/", sync.replace(tok0, tok1))
    assert "abc-123.vcf" in r.text and "404 Not Found" in r.text
    assert tok1.startswith("urn:x-iocontact:sync:")
    r = dav(c, "REPORT", "/dav/addressbooks/alex/family/", sync.replace(tok0, "http://bogus/1"))
    assert r.status_code == 403 and "valid-sync-token" in r.text


def test_web_edits_show_up_over_dav(client, family_id):
    c = client.post(f"/api/contacts?book={family_id}", json={"fn": "Web Made", "phones": [{"label": "mobile", "value": "1"}]}).json()
    r = dav(client, "PROPFIND", "/dav/addressbooks/alex/family/", PF)
    assert c["href"] in r.text
    r = client.get(f"/dav/addressbooks/alex/family/{c['href']}", auth=("alex", "secret123"))
    assert "TEL;TYPE=CELL:1" in r.text


def test_phone_round_trip_keeps_relations_single(client, family_id):
    """An iPhone saves a card back with the relation twice (the name with its label, and the bare link to the contact,
    its type gone) and with its own item1.X-... property: the relation stays one, and the groups do not collide."""
    from fastapi.testclient import TestClient
    from app.main import app
    from tests.test_api import mk
    c = TestClient(app)
    mom = mk(client, family_id, fn="Mary Doe", gender="F")
    mk(client, family_id, fn="Mary Doe")  # a namesake: the name alone no longer says who the mother is
    kid = mk(client, family_id, fn="Tim Doe", relations=[{"type": "parent", "relatedId": mom["id"]}])
    href = f"/dav/addressbooks/alex/family/{kid['uid']}.vcf"
    card = c.get(href, auth=("alex", "secret123")).text
    assert "item1.X-ABRELATEDNAMES:Mary Doe" in card
    sent = re.sub(r"RELATED;X-IOCONTACT-TYPE=parent:", "RELATED:", card).replace(
        "END:VCARD", "item1.X-ADDRESSING-GRAMMAR:abcd\r\nX-IMAGETYPE:PHOTO\r\nX-IMAGEHASH:kQQW==\r\nEND:VCARD")
    assert sent != card
    r = c.put(href, content=sent, headers={"Content-Type": "text/vcard"}, auth=("alex", "secret123"))
    assert r.status_code in (200, 201, 204), r.text
    k = client.get(f"/api/contacts/{kid['id']}").json()
    assert [(x["type"], x.get("relatedId")) for x in k["relations"]] == [("parent", mom["id"])]
    back = c.get(href, auth=("alex", "secret123")).text
    assert "item1.X-ADDRESSING-GRAMMAR:abcd" in back and "X-IMAGEHASH" not in back and "X-IMAGETYPE" not in back
    assert "item1.X-ABRELATEDNAMES" not in back and "item2.X-ABRELATEDNAMES:Mary Doe" in back
    assert back.endswith("END:VCARD\r\n")
