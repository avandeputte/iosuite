import io


def mk(client, book, **kw):
    r = client.post(f"/api/contacts?book={book}", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def test_relations_keep_their_inverse(client, family_id):
    mom = mk(client, family_id, fn="Mary Doe", gender="F")
    kid = mk(client, family_id, fn="Tim Doe", gender="M", relations=[{"type": "parent", "relatedId": mom["id"]}])
    assert kid["relations"][0]["typeLabel"] == "Mother"
    m = client.get(f"/api/contacts/{mom['id']}").json()
    assert [(r["type"], r["relatedId"], r["typeLabel"]) for r in m["relations"]] == [("child", kid["id"], "Son")]
    # picking "Sister" for someone with no gender sets it
    sis = mk(client, family_id, fn="Sue Doe")
    kid = client.put(f"/api/contacts/{kid['id']}", json={**kid, "relations": kid["relations"] + [{"type": "sibling", "relatedId": sis["id"], "gender": "F"}]}).json()
    assert client.get(f"/api/contacts/{sis['id']}").json()["gender"] == "F"
    assert {r["typeLabel"] for r in kid["relations"]} == {"Mother", "Sister"}
    # removing it removes the inverse
    kid["relations"] = [r for r in kid["relations"] if r["type"] != "sibling"]
    client.put(f"/api/contacts/{kid['id']}", json=kid)
    assert client.get(f"/api/contacts/{sis['id']}").json()["relations"] == []
    # deleting a contact drops relations pointing at it
    client.delete(f"/api/contacts/{mom['id']}")
    assert client.get(f"/api/contacts/{kid['id']}").json()["relations"] == []
    fam = client.get(f"/api/contacts/{kid['id']}/family").json()
    assert fam["root"] == kid["id"]


def test_search_formats_and_negotiation(client, family_id):
    mk(client, family_id, fn="Ann Lee", emails=[{"value": "ann@x.org"}], phones=[{"value": "+1 (555) 222-3333"}], tags=["Book club"])
    mk(client, family_id, fn="Zed Moe")
    assert client.get("/api/contacts?q=ann").json()["total"] == 1
    assert client.get("/api/contacts?q=2223333").json()["total"] == 1
    assert client.get("/api/contacts?tag=Book club").json()["total"] == 1
    r = client.get("/api/contacts", headers={"Accept": "text/vcard"})
    assert r.text.count("BEGIN:VCARD") == 2 and "version=3.0" in r.headers["content-type"]
    r = client.get("/api/contacts", headers={"Accept": "application/vcard+json"})
    assert r.json()[0][0] == "vcard"
    # create from a vCard body and from a jCard body
    r = client.post(f"/api/contacts?book={family_id}", content="BEGIN:VCARD\r\nVERSION:4.0\r\nFN:Viv Card\r\nEND:VCARD\r\n",
                    headers={"Content-Type": "text/vcard"})
    assert r.status_code == 201 and r.json()["name"]["given"] == "Viv"
    r = client.post(f"/api/contacts?book={family_id}", json=["vcard", [["fn", {}, "text", "Jay Card"]]],
                    headers={"Content-Type": "application/vcard+json"})
    assert r.status_code == 201 and r.json()["fn"] == "Jay Card"


def test_import_export(client, family_id):
    google = ("First Name,Last Name,Birthday,E-mail 1 - Label,E-mail 1 - Value,Phone 1 - Label,Phone 1 - Value,"
              "Relation 1 - Label,Relation 1 - Value,Website 1 - Label,Website 1 - Value,Labels\n"
              "Kim,Park, --05-06,* Home,kim@x.org,Mobile,555 1000,Brother,Lee Park,Profile,https://linkedin.com/in/kim,* myContacts ::: Golf\n"
              "Lee,Park,1990-01-02,,,,,,,,,\n")
    r = client.post("/api/import", data={"book": str(family_id)}, files={"file": ("g.csv", io.BytesIO(google.encode()), "text/csv")})
    assert r.json()["created"] == 2
    kim = client.get("/api/contacts?q=kim").json()["items"][0]
    k = client.get(f"/api/contacts/{kim['id']}").json()
    assert k["birthday"] == {"year": None, "month": 5, "day": 6}
    assert k["social"][0]["service"] == "linkedin" and k["tags"] == ["Golf"]
    assert k["relations"][0]["relatedFn"] == "Lee Park" and k["relations"][0]["typeLabel"] in ("Brother", "Sibling")
    outlook = ("First Name,Last Name,E-mail Address,Mobile Phone,Home City,Birthday,Spouse\n"
               "Ola,Nord,ola@x.org,123,Oslo,3/4/1970,Kari Nord\n")
    r = client.post("/api/import", data={"book": str(family_id)}, files={"file": ("o.csv", io.BytesIO(outlook.encode()), "text/csv")})
    assert r.json()["created"] == 1
    ola = client.get("/api/contacts?q=ola").json()["items"][0]
    assert ola["birthday"] == {"year": 1970, "month": 3, "day": 4}
    for fmt in ("vcf", "vcf4", "jcard", "csv-google", "csv-outlook"):
        r = client.get(f"/api/export?format={fmt}")
        assert r.status_code == 200 and "Ola" in r.text
    # re-importing our own vCard export updates rather than duplicates
    vcf = client.get("/api/export?format=vcf").content
    r = client.post("/api/import", data={"book": str(family_id)}, files={"file": ("x.vcf", io.BytesIO(vcf), "text/vcard")})
    assert r.json()["created"] == 0 and r.json()["updated"] == 3


def test_roles_and_private_books(client, family_id):
    client.post("/api/users", json={"name": "kid", "password": "kidpass99", "role": "member"})
    mine = next(b for b in client.get("/api/books").json()["items"] if not b["shared"])
    mk(client, mine["id"], fn="Secret Friend")
    from fastapi.testclient import TestClient
    from app.main import app
    k = TestClient(app)  # no lifespan: the session's app is already running
    assert k.post("/api/auth/login", json={"name": "kid", "password": "kidpass99"}).status_code == 200
    books = k.get("/api/books").json()["items"]
    assert {b["name"] for b in books} == {"Family", "Personal"} and mine["id"] not in [b["id"] for b in books]
    assert k.get("/api/contacts?q=secret").json()["total"] == 0
    assert k.post(f"/api/contacts?book={family_id}", json={"fn": "X"}).status_code == 403
    own = next(b for b in books if not b["shared"])
    assert k.post(f"/api/contacts?book={own['id']}", json={"fn": "My pal"}).status_code == 201
    # basic auth with an app password, and the bearer form
    pw = client.post("/api/auth/app-passwords", json={"label": "phone"}).json()["password"]
    from fastapi.testclient import TestClient as T2
    anon = T2(app)  # no lifespan: the session's app is already running
    assert anon.get("/api/books").status_code == 401
    assert anon.get("/api/books", auth=("alex", pw)).status_code == 200
    assert anon.get("/api/books", headers={"Authorization": f"Bearer {pw}"}).status_code == 200
    assert anon.get("/api/books", auth=("alex", "nope")).status_code == 401


def test_calendar_and_duplicates(client, family_id):
    mk(client, family_id, fn="Gran Ma", birthday={"year": 1940, "month": 2, "day": 29}, dates=[{"label": "anniversary", "month": 7, "day": 1}])
    mk(client, family_id, fn="Dup One", emails=[{"value": "same@x.org"}])
    mk(client, family_id, fn="Dup Two", emails=[{"value": "SAME@x.org"}])
    info = client.get("/api/connect").json()
    r = client.get(info["calendar"]["family"].split("testserver")[1])
    assert r.status_code == 200 and "RRULE:FREQ=YEARLY" in r.text and "Gran Ma's birthday" in r.text and "DTSTART;VALUE=DATE:19400229" in r.text
    assert client.get("/cal/bogus/family.ics").status_code == 404
    groups = client.get("/api/duplicates").json()["groups"]
    assert len(groups) == 1 and len(groups[0]["contacts"]) == 2 and "same email same@x.org" in groups[0]["pairs"][0]["reasons"]
    keep, other = groups[0]["contacts"][0]["id"], groups[0]["contacts"][1]["id"]
    merged = client.post("/api/contacts/merge", json={"keep": keep, "others": [other]}).json()
    assert len(merged["emails"]) == 1 and client.get(f"/api/contacts/{other}").status_code == 404


def test_apple_profile(client):
    import plistlib
    r = client.post("/api/apple-profile", data={"label": "Alex iPhone", "password": "new", "calendar": "family"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-apple-aspen-config")
    p = plistlib.loads(r.content)
    dav, cal = p["PayloadContent"]
    assert dav["PayloadType"] == "com.apple.carddav.account" and dav["CardDAVUsername"] == "alex"
    assert dav["CardDAVPrincipalURL"] == "/dav/principals/alex/" and dav["CardDAVPassword"].startswith("iocontact-")
    assert cal["PayloadType"] == "com.apple.subscribedcalendar.account" and cal["SubCalAccountHostName"].endswith("/family.ics")
    # the app password in the profile works for CardDAV
    client.cookies.clear()
    assert client.request("PROPFIND", "/dav/", auth=("alex", dav["CardDAVPassword"]), headers={"Depth": "0"}).status_code == 207
    # ...and nothing else: not the API, MCP or the sign-in form
    assert client.get("/api/auth/app-passwords", auth=("alex", dav["CardDAVPassword"])).status_code == 403
    assert client.post("/api/auth/login", json={"name": "alex", "password": dav["CardDAVPassword"]}).status_code == 401
    assert client.post("/api/auth/login", json={"name": "alex", "password": "secret123"}).status_code == 200
    items = client.get("/api/auth/app-passwords").json()["items"]
    assert [x["scope"] for x in items if x["label"] == "Alex iPhone (profile)"] == ["dav"]
    ask = plistlib.loads(client.post("/api/apple-profile", data={"password": "ask", "calendar": "none"}).content)
    assert len(ask["PayloadContent"]) == 1 and "CardDAVPassword" not in ask["PayloadContent"][0]



def test_apple_profile_link_needs_no_cookie(client):
    """The Home Screen app opens a download in a sheet without its cookies: the profile comes from a short-lived link,
    the same profile (one app password) each time it is opened, and a made-up link gives nothing."""
    import plistlib
    r = client.post("/api/apple-profile/link", json={"label": "iPhone", "password": "new", "calendar": "none"}).json()
    assert r["url"].startswith("profile/") and r["url"].endswith(".mobileconfig")
    client.cookies.clear()
    first, again = client.get(r["url"]), client.get(r["url"])
    assert first.status_code == 200 and first.headers["content-type"].startswith("application/x-apple-aspen-config")
    assert first.content == again.content
    pw = plistlib.loads(first.content)["PayloadContent"][0]["CardDAVPassword"]
    assert client.request("PROPFIND", "/dav/", auth=("alex", pw), headers={"Depth": "0"}).status_code == 207
    assert client.get("/profile/not-a-token/x.mobileconfig").status_code == 404

def test_account_picker_and_one_click(client, family_id):
    """Like ioPix: the sign-in screen lists the accounts; a viewer without a password signs in with one click,
    but never from outside (through Cloudflare)."""
    client.post("/api/users", json={"name": "gran", "password": "granpass1", "role": "viewer"})
    client.post("/api/users", json={"name": "ed", "password": "edpass123", "role": "editor"})
    gran = next(u for u in client.get("/api/users").json()["users"] if u["name"] == "gran")
    ed = next(u for u in client.get("/api/users").json()["users"] if u["name"] == "ed")
    assert client.patch(f"/api/users/{ed['id']}", json={"password": ""}).status_code == 400  # only viewers
    assert client.patch(f"/api/users/{gran['id']}", json={"password": ""}).status_code == 200
    from fastapi.testclient import TestClient
    from app.main import app
    anon = TestClient(app)  # no lifespan: the session's app is already running
    acc = {a["name"]: a for a in anon.get("/api/auth/accounts").json()["accounts"]}
    assert acc["gran"]["passwordless"] and not acc["ed"]["passwordless"] and "pw_hash" not in acc["gran"]
    out = {"cf-connecting-ip": "1.2.3.4"}
    assert "gran" not in [a["name"] for a in anon.get("/api/auth/accounts", headers=out).json()["accounts"]]
    assert anon.post("/api/auth/login", json={"name": "ed"}).status_code == 401
    assert anon.post("/api/auth/login", json={"name": "gran"}, headers=out).status_code == 403
    assert anon.get("/api/auth/accounts/%d/photo" % gran["id"]).status_code == 404
    assert anon.post("/api/auth/login", json={"name": "gran"}).status_code == 200
    assert anon.get("/api/status").json()["user"]["name"] == "gran"
    assert anon.get("/api/status", headers=out).json()["user"] is None  # the session does not work from outside
    # an empty password never works for HTTP Basic (CardDAV, LDAP)
    import base64
    dav = TestClient(app)  # no lifespan: the session's app is already running
    r = dav.get("/api/books", headers={"Authorization": "Basic " + base64.b64encode(b"gran:").decode()})
    assert r.status_code == 401


def test_page_stamps_the_version(client):
    from app import __version__
    html = client.get("/").text
    assert f'static/app.js?v={__version__}"' in html and f'static/app.css?v={__version__}"' in html


def test_registers_in_the_suite(client):
    """The first request writes ioContact's row in the suite's list of apps (iosuite-shared ios_apps)."""
    from iosuite_shared import suite
    from app import __version__
    client.get("/api/books")
    me = suite.get("iocontact")
    assert me is not None
    assert me["name"] == "ioContact" and me["version"] == __version__
    assert me["description"] == "Contacts" and me["color"] == "#4f2f7d"


def test_suite_apps_for_the_app_switcher(client):
    """The app mark becomes a menu of the suite's other apps: the page has the phone's button, may show their icons
    (other origins), and /api/auth/suite lists them with an address and an absolute icon."""
    from iosuite_shared import suite
    html = client.get("/").text
    assert 'id="suitebtn"' in html and "img-src 'self' data: blob: https:" in html
    client.get("/api/books")
    suite.register("iopix", name="ioPix", url="https://photo.example.net", color="#123456")
    r = client.get("/api/auth/suite").json()
    assert r["app"] == "iocontact"
    other = [a for a in r["items"] if a["app"] != r["app"]]
    assert [(a["name"], a["url"], a["icon"]) for a in other] == [("ioPix", "https://photo.example.net", "https://photo.example.net/static/icons/mark.svg")]


def test_birthday_without_reminder(client, family_id):
    """An unchecked "Remind me" keeps the birthday on the contact, in vCard and on the Birthdays page; only the
    calendar feed leaves it out."""
    import datetime as dt
    soon = dt.date.today() + dt.timedelta(days=3)
    on = mk(client, family_id, fn="Remind Yes", birthday={"year": 1980, "month": soon.month, "day": soon.day})
    off = mk(client, family_id, fn="Remind No", birthday={"year": 1981, "month": soon.month, "day": soon.day}, birthdayRemind=False)
    assert on["birthdayRemind"] is True and off["birthdayRemind"] is False and off["birthday"]["year"] == 1981
    flags = {x["fn"]: x["remind"] for x in client.get("/api/upcoming?days=10").json()["items"]}
    assert flags["Remind Yes"] is True and flags["Remind No"] is False
    info = client.get("/api/connect").json()
    ics = client.get(info["calendar"]["family"].split("testserver")[1]).text
    assert "Remind Yes's birthday" in ics and "Remind No" not in ics
    assert "BDAY" in client.get(f"/api/contacts/{off['id']}", headers={"Accept": "text/vcard"}).text
    # a CardDAV client (or anything else that does not know the flag) writing the card back keeps it off
    r = client.put(f"/dav/addressbooks/alex/family/{off['href']}", content=client.get(f"/dav/addressbooks/alex/family/{off['href']}", auth=("alex", "secret123")).text,
                   headers={"Content-Type": "text/vcard"}, auth=("alex", "secret123"))
    assert r.status_code in (201, 204), r.text
    assert client.get(f"/api/contacts/{off['id']}").json()["birthdayRemind"] is False
    back = client.put(f"/api/contacts/{off['id']}", json={**client.get(f"/api/contacts/{off['id']}").json(), "birthdayRemind": True}).json()
    assert back["birthdayRemind"] is True
    # the Birthdays page toggles it with a PATCH of only the flag
    assert client.patch(f"/api/contacts/{off['id']}", json={"birthdayRemind": False}).json()["birthdayRemind"] is False
    ics = client.get(info["calendar"]["family"].split("testserver")[1]).text
    assert "Remind No" not in ics and client.get(f"/api/contacts/{off['id']}").json()["birthday"]["year"] == 1981
    assert client.patch(f"/api/contacts/{off['id']}", json={"birthdayRemind": True}).json()["birthdayRemind"] is True
    assert "Remind No's birthday" in client.get(info["calendar"]["family"].split("testserver")[1]).text


def test_the_shell_its_files_and_the_icon_are_public(client):
    """The suite's layout: the page at /, every file it names under /static/, the mark at suite.ICON."""
    import re
    from iosuite_shared import suite
    html = client.get("/").text
    paths = re.findall(r'(?:src|href)="(static/[^"?]+)', html)
    paths += [i["src"] for i in client.get("/manifest.webmanifest").json()["icons"]]
    assert paths and all(p.startswith("static/") for p in paths)
    for p in ["/" + p for p in paths] + [suite.ICON, "/static/icons/apple-touch-icon.png"]:
        assert client.get(p).status_code == 200, p


def test_iopix_face_reaches_birthdays_and_family(client, family_id):
    """A contact linked to an ioPix person shows that face on the birthdays page,
    in the family tree and on relation chips, as in the contact list."""
    import datetime as dt
    soon = dt.date.today() + dt.timedelta(days=2)
    kid = mk(client, family_id, fn="Face Kid", birthday={"year": 2010, "month": soon.month, "day": soon.day},
             iopix={"personId": 4242, "name": "Face Kid"})
    mom = mk(client, family_id, fn="Face Mom", relations=[{"type": "child", "relatedId": kid["id"]}])
    up = {x["fn"]: x for x in client.get("/api/upcoming?days=10").json()["items"]}
    assert up["Face Kid"]["iopixPersonId"] == 4242 and up["Face Kid"]["hasPhoto"] is True
    rel = client.get(f"/api/contacts/{mom['id']}").json()["relations"]
    assert rel[0]["relatedIopixPersonId"] == 4242
    nodes = {n["fn"]: n for n in client.get(f"/api/contacts/{mom['id']}/family").json()["nodes"]}
    assert nodes["Face Kid"]["iopixPersonId"] == 4242


def test_implied_relations_show_and_can_be_saved(client, family_id):
    mom = mk(client, family_id, fn="Imp Mom", gender="F")
    aunt = mk(client, family_id, fn="Imp Aunt", gender="F", relations=[{"type": "sibling", "relatedId": mom["id"]}])
    bob = mk(client, family_id, fn="Imp Bob", gender="M", relations=[{"type": "parent", "relatedId": mom["id"]}])
    ann = mk(client, family_id, fn="Imp Ann", gender="F", relations=[{"type": "sibling", "relatedId": bob["id"]}])
    a = client.get(f"/api/contacts/{ann['id']}").json()
    got = {(r["typeLabel"], r["relatedFn"], r["viaFn"]) for r in a["impliedRelations"]}
    assert got == {("Mother", "Imp Mom", "Imp Bob"), ("Aunt", "Imp Aunt", "Imp Mom")}
    assert [r["type"] for r in a["relations"]] == ["sibling"]  # nothing stored
    fam = client.get(f"/api/contacts/{ann['id']}/family").json()
    assert {(e["to"], e["type"]) for e in fam["edges"] if e.get("implied")} == {(mom["id"], "parent"), (aunt["id"], "aunt_uncle")}
    assert aunt["id"] in {n["id"] for n in fam["nodes"]}
    # saved, it is stated (with its inverse) and no longer implied
    payload = {**a, "relations": [{"type": r["type"], "relatedId": r["relatedId"]} for r in a["relations"]] + [{"type": "parent", "relatedId": mom["id"]}]}
    client.put(f"/api/contacts/{ann['id']}", json=payload)
    a = client.get(f"/api/contacts/{ann['id']}").json()
    assert {r["typeLabel"] for r in a["relations"]} == {"Brother", "Mother"}
    assert [r["relatedFn"] for r in a["impliedRelations"]] == ["Imp Aunt"]
    assert "Imp Ann" in {r["relatedFn"] for r in client.get(f"/api/contacts/{mom['id']}").json()["relations"]}


def test_partial_birthdays(client, family_id):
    """Alex: a birthday can be saved as just the year, month and year, day and month, or the full date. Only
    birthdays with a month and day go into the feeds (upcoming, calendar); every form survives export and import."""
    import datetime as dt
    soon = dt.date.today() + dt.timedelta(days=3)
    y = mk(client, family_id, fn="Year Only", birthday={"year": 1950})
    ym = mk(client, family_id, fn="Year Month", birthday={"year": 1960, "month": soon.month})
    md = mk(client, family_id, fn="Month Day", birthday={"month": soon.month, "day": soon.day})
    full = mk(client, family_id, fn="Full Date", birthday={"year": 1970, "month": soon.month, "day": soon.day})
    assert y["birthday"] == {"year": 1950, "month": None, "day": None}
    assert ym["birthday"] == {"year": 1960, "month": soon.month, "day": None}
    assert md["birthday"] == {"year": None, "month": soon.month, "day": soon.day}
    assert full["birthday"] == {"year": 1970, "month": soon.month, "day": soon.day}
    # a day without a month, or a month alone, is not a date
    assert mk(client, family_id, fn="No Date", birthday={"day": 4})["birthday"] is None
    assert mk(client, family_id, fn="No Date 2", birthday={"month": 4})["birthday"] is None
    assert mk(client, family_id, fn="Day Dropped", birthday={"year": 1980, "day": 4})["birthday"] == {"year": 1980, "month": None, "day": None}
    # the list carries them too, and the family graph
    byname = {c["fn"]: c["birthday"] for c in client.get("/api/contacts").json()["items"]}
    assert byname["Year Only"] == {"year": 1950, "month": None, "day": None} and byname["Month Day"]["day"] == soon.day
    # feeds: only a month and day make a date to remind of
    up = {x["fn"] for x in client.get("/api/upcoming?days=10").json()["items"]}
    assert {"Month Day", "Full Date"} <= up and not {"Year Only", "Year Month"} & up
    ics = client.get(client.get("/api/connect").json()["calendar"]["family"].split("testserver")[1]).text
    assert "Full Date's birthday" in ics and "Month Day's birthday" in ics and "Year Only" not in ics and "Year Month" not in ics
    # exports keep every form, and importing them back changes nothing
    for fmt in ("vcf", "vcf4", "jcard", "csv-google"):
        r = client.get(f"/api/export?format={fmt}")
        assert r.status_code == 200
        body = r.content
        name = "x.vcf" if fmt in ("vcf", "vcf4") else "x.json" if fmt == "jcard" else "x.csv"
        r = client.post("/api/import", data={"book": str(family_id)}, files={"file": (name, io.BytesIO(body), "text/plain")})
        assert r.status_code == 200, r.text
        after = {c["fn"]: c["birthday"] for c in client.get("/api/contacts").json()["items"]}
        assert after == byname, (fmt, after)
    vcf3 = client.get("/api/export?format=vcf").text
    assert "X-IOCONTACT-BDAY:1950" in vcf3 and f"X-IOCONTACT-BDAY:1960-{soon.month:02d}" in vcf3
    assert f"BDAY;X-APPLE-OMIT-YEAR=1604:1604-{soon.month:02d}-{soon.day:02d}" in vcf3
    csvg = client.get("/api/export?format=csv-google").text
    assert "1950" in csvg and f"1960-{soon.month:02d}" in csvg and f"--{soon.month:02d}-{soon.day:02d}" in csvg
    # Outlook's CSV only has room for a full date
    csvo = client.get("/api/export?format=csv-outlook").text
    assert f"{soon.month}/{soon.day}/1970" in csvo and "1950" not in csvo
    # editing to another partial form, and clearing
    y2 = client.put(f"/api/contacts/{y['id']}", json={**y, "birthday": {"month": 3, "day": 4}}).json()
    assert y2["birthday"] == {"year": None, "month": 3, "day": 4}
    assert client.put(f"/api/contacts/{y['id']}", json={**y2, "birthday": None}).json()["birthday"] is None


def test_iopix_is_the_only_photo_source(client, family_id, monkeypatch):
    """Contacts keep no photo of their own: uploads are gone, a vCard's PHOTO is dropped, and the linked ioPix face
    is served as the photo everywhere (the photo endpoint, vCard export, the account tile)."""
    from app import iopix
    face = b"\xff\xd8\xff\xe0fakejpeg"
    monkeypatch.setattr(iopix, "settings", lambda: {"url": "https://iopix.example"})
    monkeypatch.setattr(iopix, "face", lambda pid: (face, "image/jpeg") if pid == 77 else None)
    card = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Pic Person\r\nN:Person;Pic;;;\r\nPHOTO;ENCODING=b;TYPE=JPEG:/9j/4AAQ\r\nEND:VCARD\r\n"
    r = client.post(f"/api/contacts?book={family_id}", content=card, headers={"Content-Type": "text/vcard"})
    assert r.status_code == 201 and r.json()["hasPhoto"] is False
    cid = r.json()["id"]
    assert client.get(f"/api/contacts/{cid}/photo").status_code == 404
    assert client.put(f"/api/contacts/{cid}/photo", files={"file": ("a.jpg", face, "image/jpeg")}).status_code in (404, 405)
    assert client.post(f"/api/contacts/{cid}/photo/from-iopix").status_code in (404, 405)
    assert "PHOTO" not in client.get(f"/api/contacts/{cid}", headers={"Accept": "text/vcard"}).text
    linked = client.patch(f"/api/contacts/{cid}", json={"iopix": {"personId": 77, "name": "Pic Person"}}).json()
    assert linked["hasPhoto"] is True
    got = client.get(f"/api/contacts/{cid}/photo")
    assert got.status_code == 200 and got.content == face
    assert "PHOTO" in client.get(f"/api/contacts/{cid}", headers={"Accept": "text/vcard"}).text
    from app import db
    assert not db.q("SHOW COLUMNS FROM con_contacts LIKE 'photo%%'")  # there is nowhere to keep one


def test_protocols_only_app_password(client, app):
    from fastapi.testclient import TestClient as T2
    from app import users
    limited = client.post("/api/auth/app-passwords", json={"label": "phone", "scope": "dav"}).json()["password"]
    full = client.post("/api/auth/app-passwords", json={"label": "script"}).json()["password"]
    anon = T2(app)
    # CardDAV and its discovery work
    assert anon.request("PROPFIND", "/dav/", auth=("alex", limited), headers={"Depth": "0"}).status_code == 207
    assert anon.get("/.well-known/carddav", auth=("alex", limited), follow_redirects=False).status_code in (301, 302, 307, 308)
    # the REST API (Basic or Bearer), the account routes and MCP do not
    assert anon.get("/api/books", auth=("alex", limited)).status_code == 403
    assert anon.get("/api/books", headers={"Authorization": f"Bearer {limited}"}).status_code == 403
    assert anon.get("/api/auth/me", auth=("alex", limited)).status_code == 403
    assert anon.post("/mcp", headers={"Authorization": f"Bearer {limited}"}, json={}).status_code == 403
    assert anon.post("/api/auth/login", json={"name": "alex", "password": limited}).status_code == 401
    # LDAP binds take it
    assert users.ldap_bind("alex", limited)["name"] == "alex" and users.ldap_bind("alex", full)["name"] == "alex"
    assert users.ldap_bind("alex", "secret123") is None, "never the account's own password: LDAP is not encrypted"
    assert users.authenticate("alex", limited) is None
    # an app password without the limit still works everywhere
    assert anon.get("/api/books", auth=("alex", full)).status_code == 200
    assert anon.get("/api/books", auth=("alex", "nope")).status_code == 401
    assert {p["label"]: p["scope"] for p in client.get("/api/auth/app-passwords").json()["items"]} == {"phone": "dav", "script": ""}
    assert client.post("/api/auth/app-passwords", json={"label": "x", "scope": "bogus"}).status_code == 400


def test_iopix_is_found_in_the_suite(client, monkeypatch):
    from iosuite_shared import links, suite
    from app import iopix
    assert iopix.public_settings()["enabled"] is False
    suite.register("iopix", name="ioPix", url="https://photo.example.net", version="1")
    assert iopix.public_settings() == {"url": "https://photo.example.net", "enabled": True}
    seen = []

    class R:
        def read(self):
            return b'{"tags": [{"id": 5, "name": "Ann", "person": true, "n": 3}]}'
    monkeypatch.setattr(links, "get", lambda app, provider, path, **kw: seen.append((app, provider, path)) or R())
    assert [p["name"] for p in iopix.people(force=True)] == ["Ann"] and seen == [("iocontact", "iopix", "/api/meta")]


def test_suite_admin_panel(client):
    """Settings › Security: iosuite-shared's panel and API answer a suite admin, not an app admin."""
    r = client.get("/api/suite-admin/ui.js")  # the first account (alex) is a suite admin
    assert r.status_code == 200 and "export async function mount" in r.text
    assert any(u["name"] == "alex" for u in client.get("/api/suite-admin").json()["users"])
    assert client.post("/api/users", json={"name": "ann", "password": "secret123", "role": "admin"}).status_code == 200
    client.cookies.clear()
    assert client.post("/api/auth/login", json={"name": "ann", "password": "secret123"}).status_code == 200
    assert client.get("/api/suite-admin/ui.js").status_code == 403


def test_settings_server_is_the_shared_panel(client):
    """Settings › Server is iosuite-shared's panel: its module, and the MCP box, with no This server box."""
    assert "export async function mount" in client.get("/api/server/ui.js").text
    s = client.get("/api/server").json()
    assert s["name"] == "ioContact" and "mcpEnabled" in s and s["mcpAbout"]
    assert "about" not in s
    assert client.post("/api/auth/logout_all").status_code in (404, 405)  # Sign out is the only sign out


def test_profile_for_all_apps_that_sync(client):
    """With another app that syncs in the suite, one profile sets up both, each account with an app password of its
    own app; this app's own profile stays, and with no other app there is no such choice."""
    import plistlib
    from iosuite_shared import suite
    assert [a["app"] for a in client.get("/api/apple-profile/suite").json()["apps"]] == ["iocontact"]
    assert client.post("/api/apple-profile/suite/link", json={}).status_code == 409
    suite.register("iocalendar", name="ioCalendar", url="https://other.example.com")
    assert sorted(a["app"] for a in client.get("/api/apple-profile/suite").json()["apps"]) == sorted(["iocontact", "iocalendar"])
    r = client.post("/api/apple-profile/suite/link", json={"label": "iPhone", "password": "new"}).json()
    assert r["url"].endswith("/iosuite-alex.mobileconfig")
    p = plistlib.loads(client.get(r["url"]).content)
    assert p["PayloadDisplayName"].startswith("ioSuite for ")
    own = next(x for x in p["PayloadContent"] if x.get("CardDAVAccountDescription") == "ioContact")
    other = next(x for x in p["PayloadContent"] if x is not own)
    assert other["CalDAVHostName"] == "other.example.com" and other["CalDAVPassword"].startswith("iocalendar-")
    pw = own["CardDAVPassword"]
    assert pw.startswith("iocontact-")
    client.cookies.clear()
    assert client.request("PROPFIND", "/dav/", auth=("alex", pw), headers={"Depth": "0"}).status_code == 207
    assert client.request("PROPFIND", "/dav/", auth=("alex", other["CalDAVPassword"]), headers={"Depth": "0"}).status_code == 401


def test_a_shared_address_book_never_takes_the_address_of_a_private_one(client):
    """CardDAV lists a person's own address books and the shared ones under one home: two with one address, and one hides the other."""
    import pytest
    from iosuite_shared import Invalid, users
    from app import db, model
    ann = users.create("ann", "secret123", "member", "iocontact")["id"]
    mine = model.create_book(ann, "Trips")
    shared = model.create_book(None, "Trips")
    again = model.create_book(ann, "Trips")
    slugs = {r["id"]: r["slug"] for r in db.q("SELECT id, slug FROM con_address_books WHERE id IN (%s, %s, %s)", (mine, shared, again))}
    assert slugs[mine] == "trips" and len(set(slugs.values())) == 3, slugs
    with pytest.raises(Invalid):
        model.create_book(None, "Other", slug="trips")  # a CardDAV client's own choice of address: refused the same way
