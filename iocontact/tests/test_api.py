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
    client.post("/api/users", json={"name": "kid", "password": "kidpass99", "role": "viewer"})
    mine = next(b for b in client.get("/api/books").json()["items"] if not b["shared"])
    mk(client, mine["id"], fn="Secret Friend")
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as k:
        assert k.post("/api/auth/login", json={"name": "kid", "password": "kidpass99"}).status_code == 200
        books = k.get("/api/books").json()["items"]
        assert {b["name"] for b in books} == {"Family", "Personal"} and mine["id"] not in [b["id"] for b in books]
        assert k.get("/api/contacts?q=secret").json()["total"] == 0
        assert k.post(f"/api/contacts?book={family_id}", json={"fn": "X"}).status_code == 403
        own = next(b for b in books if not b["shared"])
        assert k.post(f"/api/contacts?book={own['id']}", json={"fn": "My pal"}).status_code == 201
    # basic auth with an app password, and the bearer form
    pw = client.post("/api/app-passwords", json={"label": "phone"}).json()["password"]
    from fastapi.testclient import TestClient as T2
    with T2(app) as anon:
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
    assert dav["CardDAVPrincipalURL"] == "/dav/principals/alex/" and dav["CardDAVPassword"].startswith("iocontacts-")
    assert cal["PayloadType"] == "com.apple.subscribedcalendar.account" and cal["SubCalAccountHostName"].endswith("/family.ics")
    # the app password in the profile works for CardDAV
    client.cookies.clear()
    assert client.request("PROPFIND", "/dav/", auth=("alex", dav["CardDAVPassword"]), headers={"Depth": "0"}).status_code == 207
    labels = [x["label"] for x in client.get("/api/app-passwords", auth=("alex", dav["CardDAVPassword"])).json()["items"]]
    assert "Alex iPhone (profile)" in labels
    ask = plistlib.loads(client.post("/api/apple-profile", data={"password": "ask", "calendar": "none"}, auth=("alex", dav["CardDAVPassword"])).content)
    assert len(ask["PayloadContent"]) == 1 and "CardDAVPassword" not in ask["PayloadContent"][0]


def test_account_picker_and_one_click(client, family_id):
    """Like ioPix: the sign-in screen lists the accounts; a viewer without a password signs in with one click,
    but never from outside (through Cloudflare)."""
    client.post("/api/users", json={"name": "gran", "password": "granpass1", "role": "viewer"})
    client.post("/api/users", json={"name": "ed", "password": "edpass123", "role": "editor"})
    gran = next(u for u in client.get("/api/users").json()["items"] if u["name"] == "gran")
    ed = next(u for u in client.get("/api/users").json()["items"] if u["name"] == "ed")
    assert client.patch(f"/api/users/{ed['id']}", json={"password": ""}).status_code == 400  # only viewers
    assert client.patch(f"/api/users/{gran['id']}", json={"password": ""}).status_code == 200
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as anon:
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
    with TestClient(app) as dav:
        r = dav.get("/api/books", headers={"Authorization": "Basic " + base64.b64encode(b"gran:").decode()})
        assert r.status_code == 401


def test_page_stamps_the_version(client):
    from app import APP_VERSION
    html = client.get("/").text
    assert f'static/app.js?v={APP_VERSION}"' in html and f'static/app.css?v={APP_VERSION}"' in html
