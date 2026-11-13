"""The bookmarks as a tree that browsers sync with: what the start page shows of it, the Nextcloud Bookmarks API as
Floccus uses it (its sign-in flow, the lock, folders, bookmarks, hashes, order, import), the bookmarks file over WebDAV
as Floccus uses that (lock file, .temp upload, MOVE, the size checks), and files in and out."""
import base64
import hashlib
import json
import re

from app import bookmarkfiles, bookmarks, bookmarksync, db

NC = "/dav/nextcloud/index.php/apps/bookmarks/public/rest/v2"
DAV = "/dav/bookmarks"


def _basic(name, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{name}:{pw}".encode()).decode()}


def _anon():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)  # no `with`: the app is started once per process


def _app_password(client, scope="dav"):
    r = client.post("/api/auth/app-passwords", json={"label": "Floccus", "scope": scope})
    assert r.status_code == 200, r.text
    return r.json()["password"]


def _sha(o):
    return hashlib.sha256(json.dumps(o, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def test_start_page_shows_only_what_is_picked(client):
    work = client.post("/api/bookmarks/groups", json={"name": "Work"}).json()  # made in Settings: on the start page
    menu = client.post("/api/bookmarks/groups", json={"name": "Bookmarks bar", "start": False}).json()
    sub = client.post("/api/bookmarks/groups", json={"name": "Recipes", "parentId": menu["id"], "start": False}).json()
    a = client.post(f"/api/bookmarks/groups/{work['id']}/links", json={"name": "Mail", "href": "mail.example.com"}).json()
    b = client.post(f"/api/bookmarks/groups/{work['id']}/links", json={"name": "Wiki", "href": "https://wiki.example.com"}).json()
    c = client.post(f"/api/bookmarks/groups/{menu['id']}/links", json={"name": "News", "href": "https://news.example.com"}).json()
    d = client.post(f"/api/bookmarks/groups/{sub['id']}/links", json={"name": "Bread", "href": "https://bread.example.com"}).json()
    assert a["onStart"] and a["start"] is None and not c["onStart"]
    shown = lambda: [(g["name"], [l["name"] for l in g["links"]]) for g in client.get("/api/bookmarks").json()["groups"]]  # noqa: E731
    assert shown() == [("Work", ["Mail", "Wiki"])]
    # one link hidden in a folder that is shown, one shown in a folder that is not
    assert client.patch(f"/api/bookmarks/links/{b['id']}", json={"start": False}).json()["onStart"] is False
    assert client.patch(f"/api/bookmarks/links/{d['id']}", json={"start": True}).json()["onStart"] is True
    assert shown() == [("Work", ["Mail"]), ("Recipes", ["Bread"])]
    # the whole folder, and back to "as its folder"
    assert client.patch(f"/api/bookmarks/groups/{menu['id']}", json={"start": True}).json()["start"] is True
    client.patch(f"/api/bookmarks/links/{b['id']}", json={"start": None})
    assert shown() == [("Work", ["Mail", "Wiki"]), ("Bookmarks bar", ["News"]), ("Recipes", ["Bread"])]
    # everything is in the tree, nested, whatever the start page shows
    t = client.get("/api/bookmarks/tree").json()
    assert t["count"] == 4 and [x["name"] for x in t["items"]] == ["Work", "Bookmarks bar"]
    bar = t["items"][1]["items"]
    assert [(x["type"], x["name"]) for x in bar] == [("folder", "Recipes"), ("bookmark", "News")] and bar[0]["items"][0]["start"] is True
    # a folder cannot go inside itself; a link moves to another folder; deleting a folder takes what is in it
    assert client.patch(f"/api/bookmarks/groups/{menu['id']}", json={"parentId": sub["id"]}).status_code == 400
    assert client.patch(f"/api/bookmarks/links/{c['id']}", json={"groupId": work["id"]}).json()["groupId"] == work["id"]
    assert client.delete(f"/api/bookmarks/groups/{menu['id']}").status_code == 200
    assert client.get("/api/bookmarks/tree").json()["count"] == 3


def test_nextcloud_sign_in_flow_gives_a_sync_only_app_password(client):
    anon = _anon()
    assert anon.get("/dav/nextcloud/status.php").json()["installed"] is True
    f = anon.post("/dav/nextcloud/index.php/login/v2", headers={"User-Agent": "Floccus bookmarks sync", "Host": "start.example.com"}).json()
    assert f["login"].startswith("http://start.example.com/dav/nextcloud/index.php/login/v2/flow/")
    poll = lambda: anon.post(f["poll"]["endpoint"].replace("http://start.example.com", ""), data={"token": f["poll"]["token"]})  # noqa: E731
    assert poll().status_code == 404
    page = f["login"].replace("http://start.example.com", "")
    assert "Sign in to ioSuite first" in anon.get(page).text  # nobody signed in: nothing to allow
    assert f'href="/?flow={page.rsplit("/", 1)[-1]}"' in anon.get(page).text  # the start page signs in and sends back here
    r = client.get(page)
    assert "Floccus bookmarks sync" in r.text and "alex" in r.text
    token = page.rsplit("/", 1)[-1]
    assert anon.post("/dav/nextcloud/index.php/login/v2/grant", data={"page": token}).status_code == 403
    assert client.post("/dav/nextcloud/index.php/login/v2/grant", data={"page": token}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert poll().status_code == 404
    assert "Done" in client.post("/dav/nextcloud/index.php/login/v2/grant", data={"page": token}).text
    got = poll().json()
    assert got["loginName"] == "alex" and got["appPassword"].startswith("iosuite-") and got["server"].endswith("/dav/nextcloud")
    assert poll().status_code == 404  # handed out once
    assert "no longer valid" in client.get(page).text
    auth = _basic("alex", got["appPassword"])
    caps = anon.get("/dav/nextcloud/ocs/v2.php/cloud/capabilities?format=json", headers=auth).json()["ocs"]["data"]["capabilities"]["bookmarks"]
    assert caps["hash-functions"] == ["sha256"] and caps["javascript-bookmarks"] is True
    assert anon.post(f"{NC}/lock", headers=auth).status_code == 200
    # for sync only: not the rest of the start page; listed with the account's app passwords, where it is revoked
    assert anon.get("/api/apps", headers=auth).status_code == 403
    mine = client.get("/api/auth/app-passwords").json()["items"]
    assert [(p["label"], p["scope"]) for p in mine] == [("Bookmark sync: Floccus bookmarks sync", "dav")]
    client.delete(f"/api/auth/app-passwords/{mine[0]['id']}")
    assert anon.get(f"{NC}/folder", headers=auth).status_code == 401


def test_nextcloud_api_as_floccus_uses_it(client):
    anon, auth = _anon(), _basic("alex", _app_password(client))
    r = anon.get(f"{NC}/folder")
    assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic")
    assert anon.get(f"{NC}/folder", headers=_basic("alex", "wrong")).status_code == 401
    get = lambda p: anon.get(NC + p, headers=auth).json()  # noqa: E731
    send = lambda m, p, body=None: anon.request(m, NC + p, headers=auth, json=body)  # noqa: E731
    # the lock: one client at a time; a second one is told to wait
    assert send("POST", "/lock").json() == {"status": "success"}
    assert send("POST", "/lock").status_code == 423
    # an empty server: the root's hash is that of no children
    assert get("/folder/-1/hash?hashFn=sha256")["data"] == _sha({"children": []})
    assert get("/bookmark?page=0&limit=300") == {"status": "success", "data": []}
    assert send("GET", "/folder/-1/hash?hashFn=murmur3a").status_code == 400
    # folders and bookmarks as the client creates them
    bar = send("POST", "/folder", {"parent_folder": -1, "title": "Bookmarks Bar"}).json()["item"]
    sub = send("POST", "/folder", {"parent_folder": bar["id"], "title": "Dév & <co>"}).json()["item"]
    assert sub["parent_folder"] == bar["id"] and bar["parent_folder"] == -1
    assert get("/bookmark?url=" + "https%3A%2F%2Fa.example%2F")["data"] == []  # never "exists already": no merging
    a = send("POST", "/bookmark", {"url": "https://a.example/", "title": "A", "folders": [bar["id"]]}).json()["item"]
    a2 = send("POST", "/bookmark", {"url": "https://a.example/", "title": "A again", "folders": [sub["id"]], "tags": ["x", "y"]}).json()["item"]
    js = send("POST", "/bookmark", {"url": "javascript:void(0)", "title": "Bookmarklet", "folders": ["-1"]}).json()["item"]
    assert a["id"] != a2["id"] and a["folders"] == [bar["id"]] and a2["tags"] == ["x", "y"] and js["folders"] == [-1] and js["target"] == "javascript:void(0)"
    assert send("POST", "/bookmark", {"url": "", "title": "nothing", "folders": [-1]}).status_code == 400
    assert send("POST", "/bookmark", {"url": "https://b.example", "title": "B", "folders": [99999]}).status_code == 404
    assert get(f"/bookmark/{a['id']}")["item"]["title"] == "A"
    # the tree, in layers
    kids = get("/folder/-1/children?layers=-1")["data"]
    assert [(k["type"], k["title"]) for k in kids] == [("folder", "Bookmarks Bar"), ("bookmark", "Bookmarklet")]
    assert [(k["type"], k["title"]) for k in kids[0]["children"]] == [("folder", "Dév & <co>"), ("bookmark", "A")]
    assert kids[0]["children"][0]["children"][0]["id"] == a2["id"]
    one = get("/folder/-1/children?layers=0")["data"]
    assert "children" not in one[0]
    assert "children" in get("/folder/-1/children?layers=1")["data"][0] and "children" not in get("/folder/-1/children?layers=1")["data"][0]["children"][0]
    assert get("/folder?root=-1&layers=-1")["data"][0]["children"][0]["title"] == "Dév & <co>"
    assert len(get("/bookmark?page=0&limit=300")["data"]) == 3 and get("/bookmark?page=1&limit=2")["data"][0]["id"]
    # the hashes are the ones Floccus computes for the same tree, so it skips what did not change
    h_a, h_a2, h_js = (_sha({"title": t, "url": u}) for t, u in (("A", "https://a.example/"), ("A again", "https://a.example/"), ("Bookmarklet", "javascript:void(0)")))
    h_sub = _sha({"title": "Dév & <co>", "children": [h_a2]})
    h_bar = _sha({"title": "Bookmarks Bar", "children": [h_sub, h_a]})
    assert get(f"/folder/{sub['id']}/hash?hashFn=sha256")["data"] == h_sub
    assert get("/folder/-1/hash?hashFn=sha256")["data"] == _sha({"children": [h_bar, h_js]})
    with_tags = _sha({"title": "Dév & <co>", "children": [_sha({"title": "A again", "url": "https://a.example/", "tags": ["x", "y"]})]})
    assert get(f"/folder/{sub['id']}/hash?hashFn=sha256&fields[]=title&fields[]=url&fields[]=tags")["data"] == with_tags
    # an update names the folders: the bookmark moves to the last; the order of a folder's children
    assert send("PUT", f"/bookmark/{a2['id']}", {"url": "https://a.example/2", "title": "A2", "folders": [bar["id"]], "tags": []}).json()["item"]["folders"] == [bar["id"]]
    assert send("PATCH", f"/folder/{bar['id']}/childorder", {"data": [{"id": str(a2["id"]), "type": "bookmark"}, {"id": f"{a['id']};{bar['id']}", "type": "bookmark"}, {"id": sub["id"], "type": "folder"}]}).status_code == 200
    assert [k["id"] for k in get(f"/folder/{bar['id']}/childorder")["data"]] == [a2["id"], a["id"], sub["id"]]
    assert send("PUT", f"/folder/{sub['id']}", {"parent_folder": -1, "title": "Dev"}).json()["item"]["parent_folder"] == -1
    assert send("PUT", f"/folder/{bar['id']}", {"parent_folder": bar["id"], "title": "x"}).status_code == 400
    # a subtree in one go (bulk import): answers with what it made
    html = bookmarkfiles.to_html([{"type": "folder", "id": 1, "title": "Imported", "children": [{"type": "bookmark", "id": 2, "title": "I", "url": "https://i.example", "tags": ["t"]}]}], 5)
    made = anon.post(f"{NC}/folder/{sub['id']}/import", headers=auth, files={"bm_import": ("upload.html", html, "text/html")}).json()["data"]
    assert made[0]["type"] == "folder" and made[0]["title"] == "Imported" and made[0]["children"][0]["url"] == "https://i.example"
    # removing: a bookmark from its folder (404 from another), a folder with what is in it
    assert send("DELETE", f"/folder/{sub['id']}/bookmarks/{a['id']}").status_code == 404
    assert send("DELETE", f"/folder/{bar['id']}/bookmarks/{a['id']}").json() == {"status": "success"}
    assert send("DELETE", f"/folder/{sub['id']}").status_code == 200 and send("DELETE", f"/folder/{sub['id']}").status_code == 404
    assert get("/tag") == [] and send("DELETE", "/lock").status_code == 200 and send("POST", "/lock").status_code == 200
    # nothing a browser synced is on the start page until it is picked; a bookmarklet never is
    assert client.get("/api/bookmarks").json() == {"groups": []}
    client.patch(f"/api/bookmarks/groups/{bar['id']}", json={"start": True})
    client.patch(f"/api/bookmarks/links/{js['id']}", json={"start": True})
    assert [(g["name"], [l["href"] for l in g["links"]]) for g in client.get("/api/bookmarks").json()["groups"]] == [("Bookmarks Bar", ["https://a.example/2"])]
    # a viewer's sync app reads, and is told it may not write
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    kid = _basic("kid", "secret123")
    assert anon.get(f"{NC}/folder/-1/children?layers=-1", headers=kid).status_code == 200
    assert anon.post(f"{NC}/bookmark", headers=kid, json={"url": "https://k.example", "title": "K", "folders": [-1]}).status_code == 403


FLOCCUS_XBEL = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xbel PUBLIC "+//IDN python.org//DTD XML Bookmark Exchange Language 1.0//EN//XML" "http://pyxml.sourceforge.net/topics/dtds/xbel.dtd">
<xbel version="1.0">
<!--- highestId :%(highest)d: for Floccus bookmark sync browser extension -->
%(body)s
</xbel>"""


def _xbel(body, highest):
    return FLOCCUS_XBEL % {"body": body, "highest": highest}


def test_webdav_file_as_floccus_uses_it(client):
    anon, auth = _anon(), _basic("alex", _app_password(client))
    req = lambda m, p, **kw: anon.request(m, f"{DAV}/{p}", headers={**auth, **kw.pop("headers", {})}, **kw)  # noqa: E731
    size = lambda p: int(re.search(r"getcontentlength[^>]*>(\d+)<", req("PROPFIND", p, headers={"Depth": "0"}).text).group(1))  # noqa: E731
    assert anon.request("PROPFIND", DAV + "/").status_code == 401
    assert req("PROPFIND", "", headers={"Depth": "0"}).status_code == 207  # the connection test
    # something made on the start page first
    g = client.post("/api/bookmarks/groups", json={"name": "Home"}).json()
    l = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Router", "href": "http://192.168.1.1"}).json()
    # a sync: the lock file, the file and its size
    assert req("GET", "bookmarks.xbel.lock").status_code == 404
    assert req("PUT", "bookmarks.xbel.lock", content="<html><body>I am a lock file</body></html>").status_code in (201, 204)
    r = req("GET", "bookmarks.xbel.lock")
    assert r.status_code == 200 and r.headers["last-modified"].endswith("GMT")
    assert client.get("/api/bookmarks/sync").json()["syncing"] is True
    r = req("GET", "bookmarks.xbel")
    assert r.status_code == 200 and bookmarkfiles.XBEL_HEAD in r.text and f'<bookmark href="http://192.168.1.1" id="{l["id"]}">' in r.text
    assert f"<!--- highestId :{l['id']}:" in r.text and size("bookmarks.xbel") == len(r.content)
    # the client adds a folder and two bookmarks under ids of its own, and uploads: .temp, its size, MOVE, the size again
    up = _xbel(f"""<folder id="{g['id']}">
  <title>Home</title>
  <bookmark href="http://192.168.1.1" id="{l['id']}">
    <title>Router &amp; modem</title>
  </bookmark>
  <bookmark href="javascript:alert(&apos;hi&apos;)" id="{l['id'] + 2}">
    <title>Bookmarklet</title>
  </bookmark>
</folder>
<folder id="{l['id'] + 1}">
  <title>Other bookmarks</title>
  <bookmark href="https://ünï.example/päth" id="{l['id'] + 3}">
    <title>Ünï</title>
  </bookmark>
</folder>""", l["id"] + 3)
    raw = up.encode()
    assert req("PUT", "bookmarks.xbel.temp", content=raw, headers={"Content-Type": "application/xml"}).status_code == 201
    assert size("bookmarks.xbel.temp") == len(raw)
    assert req("MOVE", "bookmarks.xbel.temp", headers={"Destination": "http://testserver/dav/bookmarks/bookmarks.xbel", "Overwrite": "T"}).status_code == 204
    assert size("bookmarks.xbel") == len(raw) and req("GET", "bookmarks.xbel.temp").status_code == 404
    assert req("DELETE", "bookmarks.xbel.lock").status_code == 204 and req("GET", "bookmarks.xbel.lock").status_code == 404
    # the tree is the file, under the client's ids; the start page keeps its picks and the link its icon fields
    t = client.get("/api/bookmarks/tree").json()
    assert [(x["id"], x["name"], x["start"]) for x in t["items"]] == [(g["id"], "Home", True), (l["id"] + 1, "Other bookmarks", False)]
    assert [(x["id"], x["name"]) for x in t["items"][0]["items"]] == [(l["id"], "Router & modem"), (l["id"] + 2, "Bookmarklet")]
    assert [x["name"] for x in client.get("/api/bookmarks").json()["groups"][0]["links"]] == ["Router & modem"]
    # the next sync gets back what it uploaded, byte for byte
    assert req("GET", "bookmarks.xbel").content == raw
    # then somebody adds a link on the start page: the file is written anew, with it, and the client's size check holds
    n = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "NAS", "href": "http://nas.lan"}).json()
    assert n["id"] == l["id"] + 4  # after the ids the client used
    r = req("GET", "bookmarks.xbel")
    assert f'id="{n["id"]}"' in r.text and size("bookmarks.xbel") == len(r.content) and f"highestId :{n['id']}:" in r.text
    assert [(i["type"], i["title"]) for i in bookmarkfiles.parse_xbel(r.text)] == [("folder", "Home"), ("folder", "Other bookmarks")]
    # while the client holds that copy, one more link appears on the start page; the client's upload (which removes
    # "Other bookmarks" and knows nothing of the new link) keeps the new link and removes the folder
    late = client.post(f"/api/bookmarks/groups/{g['id']}/links", json={"name": "Printer", "href": "http://printer.lan"}).json()
    up2 = _xbel(f"""<folder id="{g['id']}">
  <title>Home</title>
  <bookmark href="http://nas.lan" id="{n['id']}">
    <title>NAS</title>
  </bookmark>
  <bookmark href="http://192.168.1.1" id="{l['id']}">
    <title>Router &amp; modem</title>
  </bookmark>
  <bookmark href="https://new.example" id="{late['id']}">
    <title>Made in the browser, under an id the start page took meanwhile</title>
  </bookmark>
</folder>""", late["id"])
    assert req("PUT", "bookmarks.xbel", content=up2.encode()).status_code == 204
    assert size("bookmarks.xbel") == len(up2.encode())  # what it uploaded, for its check
    home = client.get("/api/bookmarks/tree").json()["items"]
    assert len(home) == 1
    names = {x["name"]: x["id"] for x in home[0]["items"]}
    assert set(names) == {"NAS", "Router & modem", "Printer", "Made in the browser, under an id the start page took meanwhile"}
    assert names["Printer"] == late["id"] and names["Made in the browser, under an id the start page took meanwhile"] > late["id"]
    assert [x["name"] for x in home[0]["items"]][:2] == ["NAS", "Router & modem"]
    r = req("GET", "bookmarks.xbel")  # not what was uploaded any more: written anew, with the link that was kept
    assert "http://printer.lan" in r.text and size("bookmarks.xbel") == len(r.content)
    # an encrypted file cannot be read: refused, nothing changes
    assert req("PUT", "bookmarks.xbel", content=json.dumps({"ciphertext": "abc", "salt": "def"})).status_code == 415
    assert client.get("/api/bookmarks/tree").json()["count"] == 4
    # the same tree as bookmarks HTML, which Floccus can sync instead; a file without ids matches what is there
    h = req("GET", "bookmarks.html")
    assert bookmarkfiles.HTML_HEAD in h.text and f'ID="{n["id"]}"' in h.text and size("bookmarks.html") == len(h.content)
    plain = bookmarkfiles.to_html(bookmarkfiles.parse_html(h.text))
    assert "ID=" not in plain and req("PUT", "bookmarks.html", content=plain.encode()).status_code == 204
    again = client.get("/api/bookmarks/tree").json()["items"][0]["items"]
    assert {x["name"]: x["id"] for x in again} == names
    assert req("PUT", "notes.txt", content=b"x").status_code == 404
    # a viewer reads the file and cannot upload one
    client.post("/api/users", json={"name": "kid", "password": "secret123", "role": "viewer"})
    assert anon.get(f"{DAV}/bookmarks.xbel", headers=_basic("kid", "secret123")).status_code == 200
    assert anon.put(f"{DAV}/bookmarks.xbel", headers=_basic("kid", "secret123"), content=up2.encode()).status_code == 403


def test_files_in_and_out(client):
    exported = """<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><H3 ADD_DATE="1700000000" PERSONAL_TOOLBAR_FOLDER="true">Bookmarks bar</H3>
    <DL><p>
        <DT><A HREF="https://example.com/?a=1&amp;b=2" ADD_DATE="1700000000" ICON="data:image/png;base64,AAAA">Example &amp; co</A>
        <DT><H3>Sub</H3>
        <DL><p>
            <DT><A HREF="https://deep.example/">Deep</A>
            <DD>a description some browsers add
        </DL><p>
    </DL><p>
    <DT><A HREF="https://top.example/">Top</A>
</DL><p>
"""
    r = client.post("/api/bookmarks/import", json={"file": exported})
    assert r.status_code == 200 and r.json() == {"groups": 2, "links": 3}
    t = client.get("/api/bookmarks/tree").json()["items"]
    assert [(x["type"], x["name"]) for x in t] == [("folder", "Bookmarks bar"), ("bookmark", "Top")]
    assert t[0]["items"][0]["href"] == "https://example.com/?a=1&b=2" and t[0]["items"][1]["items"][0]["name"] == "Deep"
    assert client.get("/api/bookmarks").json() == {"groups": []}  # a browser's bookmarks: none on the start page until picked
    assert client.post("/api/bookmarks/import", json={"file": "hello"}).status_code == 400
    out = client.get("/api/bookmarks/export.html")
    assert out.headers["content-disposition"] == 'attachment; filename="bookmarks.html"'
    assert [(x["type"], x["title"]) for x in bookmarkfiles.parse(out.text)] == [("folder", "Bookmarks bar"), ("bookmark", "Top")]
    x = bookmarkfiles.parse(client.get("/api/bookmarks/export.xbel").text)
    assert x[0]["children"][1]["children"][0]["url"] == "https://deep.example/" and x[0]["id"] == t[0]["id"]
    assert client.get("/api/bookmarks/export.pdf").status_code == 404
    s = client.get("/api/bookmarks/sync", headers={"host": "start.example.com"}).json()
    assert s["nextcloud"] == "http://start.example.com/dav/nextcloud" and s["webdav"] == "http://start.example.com/dav/bookmarks/" and s["syncing"] is False


def test_order_keeps_the_places_of_what_is_not_named(client):
    f = bookmarks.create(None, True, "F")["id"]
    a, sub, b, c = (bookmarks.create(f, k == "sub", k, None if k == "sub" else f"https://{k}.example")["id"] for k in ("a", "sub", "b", "c"))
    bookmarks.order(f, [c, a, b])  # the links, as Settings shows them apart from the folders
    assert [r["id"] for r in bookmarks.Tree().children(f)] == [c, sub, a, b]
    other = bookmarks.create(None, False, "o", "https://o.example")["id"]
    bookmarks.order(f, [a, other, c, b])  # one dragged in from elsewhere
    assert [r["id"] for r in bookmarks.Tree().children(f)] == [a, sub, other, c, b]
    assert bookmarks.Tree().by[other]["parent_id"] == f


def test_bookmarks_from_before_the_tree_are_carried_over(client):
    with db.tx() as con, con.cursor() as cur:
        cur.execute("CREATE TABLE prt_bookmark_groups (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(128) NOT NULL, position INT NOT NULL DEFAULT 0)")
        cur.execute("CREATE TABLE prt_bookmarks (id INT AUTO_INCREMENT PRIMARY KEY, group_id INT NOT NULL, name VARCHAR(128) NOT NULL, abbr VARCHAR(8) NULL, "
                    "url VARCHAR(2048) NOT NULL, description VARCHAR(512) NULL, icon VARCHAR(1024) NULL, position INT NOT NULL DEFAULT 0)")
        cur.execute("CREATE TABLE prt_bookmark_icons (bookmark_id INT PRIMARY KEY, svg MEDIUMTEXT NOT NULL, etag CHAR(16) NOT NULL)")
        cur.execute("INSERT INTO prt_bookmark_groups (id, name, position) VALUES (7, 'Later', 1), (9, 'First', 0)")
        cur.execute("INSERT INTO prt_bookmarks (id, group_id, name, abbr, url, description, icon, position) VALUES "
                    "(3, 9, 'Git', 'GH', 'https://github.com', 'Code', 'github.png', 1), (4, 9, 'Mail', 'MA', 'https://mail.example', NULL, NULL, 0), (5, 7, 'X', 'X', 'https://x.example', NULL, NULL, 0)")
        cur.execute("INSERT INTO prt_bookmark_icons VALUES (3, '<svg xmlns=''http://www.w3.org/2000/svg''/>', 'abcdabcdabcdabcd')")
    db.set_setting("bookmarks_carried", None)
    bookmarks.carry_over()
    bookmarks.carry_over()  # once
    gs = client.get("/api/bookmarks").json()["groups"]
    assert [(g["name"], [(l["name"], l["abbr"], l["description"]) for l in g["links"]]) for g in gs] == \
        [("First", [("Mail", "MA", "mail.example"), ("Git", "GH", "Code")]), ("Later", [("X", "X", "x.example")])]
    git = gs[0]["links"][1]
    assert git["icon"] == "github.png" and git["iconUrl"].endswith("v=abcdabcdabcdabcd") and client.get("/" + git["iconUrl"]).status_code == 200
    assert bookmarksync.items()[0]["title"] == "First"
