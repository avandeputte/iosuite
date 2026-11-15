"""Import from a running Homebox through its API: the things with their places, labels, fields, photos, attachments and
maintenance log, for both shapes of the API (/v1/items and the newer /v1/entities); a second run adds nothing twice."""
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from PIL import Image

from app import db, homebox_api
from conftest import sign_in


def png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (60, 40), (20, 120, 200)).save(out, "PNG")
    return out.getvalue()


PDF = b"%PDF-1.4\n%manual\n" + b"x" * 5000
PHOTO = png()


def homebox(shape: str):
    """A small Homebox: two places, two labels, a fridge (photo, manual, receipt, a done and a scheduled maintenance, a
    field) and an archived drill."""
    S = "items" if shape == "items" else "entities"
    tree = [{"id": "L1", "name": "Home", "type": "location", "children": [{"id": "L2", "name": "Kitchen", "type": "location", "children": []}]}]
    things = {
        "I1": {"id": "I1", "name": "Fridge", "description": "Big one", "quantity": 1, "manufacturer": "Samsung", "modelNumber": "RB38",
               "serialNumber": "SN1", "assetId": "000-001", "purchaseTime" if shape == "items" else "purchaseDate": "2023-05-02T00:00:00Z",
               "purchasePrice": 1299.5, "warrantyExpires": "2027-05-02T00:00:00Z", "lifetimeWarranty": False, "insured": True,
               "archived": False, "soldTime": "0001-01-01T00:00:00Z", "notes": "Defrost in spring",
               "location": {"id": "L2", "name": "Kitchen"}, ("labels" if shape == "items" else "tags"): [{"name": "Appliances"}],
               "fields": [{"name": "Filter", "type": "text", "textValue": "DA29"}, {"name": "Litres", "type": "number", "numberValue": 385}],
               "attachments": [{"id": "A1", "type": "photo", "title": "fridge.png", "primary": True, "mimeType": "image/png"},
                               {"id": "A2", "type": "manual", "title": "manual.pdf", "mimeType": "application/pdf"},
                               {"id": "A3", "type": "receipt", "title": "receipt.pdf", "mimeType": "application/pdf"},
                               {"id": "A4", "type": "thumbnail", "title": "thumb.webp"}]},
        "I2": {"id": "I2", "name": "Drill", "quantity": 2, "archived": True, "purchasePrice": 0, "location": {"id": "L1", "name": "Home"},
               "fields": [], "attachments": []},
    }
    files = {"A1": (PHOTO, "image/png"), "A2": (PDF, "application/pdf"), "A3": (PDF + b"r", "application/pdf")}
    seen = {"logins": 0}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype="application/json"):
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/v1/users/login":
                seen["logins"] += 1
                if body.get("password") != "pw":
                    return self.send(401, {"error": "nope"})
                return self.send(200, {"token": "Bearer T", "attachmentToken": "AT", "expiresAt": "x"})
            self.send(404, {})

        def do_GET(self):
            u = urlsplit(self.path)
            q = parse_qs(u.query)
            p = u.path
            if self.headers.get("Authorization") != "Bearer T":
                return self.send(401, {})
            if p == f"/api/v1/{'locations' if S == 'items' else 'entities'}/tree":
                return self.send(200, tree)
            if p == f"/api/v1/{'labels' if S == 'items' else 'tags'}":
                return self.send(200, [{"id": "T1", "name": "Appliances", "color": "#1a73e8"}, {"id": "T2", "name": "Tools", "color": "red"}])
            if p == f"/api/v1/{S}":
                rows = [{"id": k, "name": v["name"]} for k, v in things.items()]
                if S == "entities":
                    rows.append({"id": "L1", "name": "Home", "entityType": {"isLocation": True}})
                page, size = int(q["page"][0]), int(q["pageSize"][0])
                return self.send(200, {"items": rows[(page - 1) * size: page * size], "page": page, "pageSize": size, "total": len(rows)})
            parts = p.split("/")  # /api/v1/<S>/<id>[/maintenance|/attachments/<aid>]
            if len(parts) >= 5 and parts[3] == S and parts[4] in things:
                if len(parts) == 5:
                    return self.send(200, things[parts[4]])
                if parts[5] == "maintenance":
                    return self.send(200, [{"id": "M1", "name": "Defrost", "completedDate": "2025-04-01", "cost": "12.50", "description": "All good"},
                                           {"id": "M2", "name": "Service", "completedDate": "0001-01-01T00:00:00Z", "scheduledDate": "2027-01-01"}]
                                     if parts[4] == "I1" else [])
                if parts[5] == "attachments" and parts[6] in files:
                    raw, ctype = files[parts[6]]
                    return self.send(200, raw, ctype)
            self.send(404, {})

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


@pytest.mark.parametrize("shape", ["items", "entities"])
def test_import_from_a_homebox_server(client, shape):
    srv, seen = homebox(shape)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        bad = client.post("/api/import/homebox-server", json={"url": url, "username": "a@b.c", "password": "wrong"})
        assert bad.status_code == 400 and "did not accept" in bad.text
        assert client.get("/api/import/homebox-server").json()["state"] in ("idle", "done")
        homebox_api._job.clear()
        homebox_api._job["state"] = "idle"
        u = client.get("/api/auth/me").json()
        r = homebox_api.start(u.get("user", u), url, "a@b.c", "pw", background=False)
        assert r["state"] == "done", r
        assert (r["total"], r["added"], r["changed"], r["files"], r["log"]) == (2, 2, 0, 3, 1), r
        assert any("scheduled maintenance" in s for s in r["skipped"])
        items = {x["name"]: x for x in client.get("/api/items?archived=also").json()["items"]}
        f = client.get(f"/api/items/{items['Fridge']['id']}").json()
        assert f["location"]["path"] == "Home / Kitchen" and f["purchasePrice"] == 1299.5 and f["warrantyExpires"] == "2027-05-02"
        assert f["assetId"] == "000-001" and f["insured"] is True and [x["name"] for x in f["labels"]] == ["Appliances"]
        assert f["fields"] == [{"name": "Filter", "value": "DA29"}, {"name": "Litres", "value": "385"}]
        assert sorted((x["kind"], x["name"]) for x in f["files"]) == [("manual", "manual.pdf"), ("photo", "fridge.png"), ("receipt", "receipt.pdf")]
        assert f["photo"], "the photo is the card's picture"
        assert [(m["title"], m["date"], m["cost"]) for m in f["maintenance"]] == [("Defrost", "2025-04-01", 12.5)]
        d = client.get(f"/api/items/{items['Drill']['id']}").json()
        assert d["archived"] is True and d["quantity"] == 2 and d["purchasePrice"] is None and d["location"]["path"] == "Home"
        labels = {x["name"]: x for x in client.get("/api/labels").json()["items"]}
        assert labels["Appliances"]["color"] == "#1a73e8" and labels["Tools"]["color"] is None
        again = homebox_api.start(u.get("user", u), url, "a@b.c", "pw", background=False)
        assert (again["added"], again["changed"], again["files"], again["log"]) == (0, 2, 0, 0), again
        assert db.one("SELECT COUNT(*) AS n FROM thg_files")["n"] == 3
    finally:
        srv.shutdown()


def test_a_csv_import_is_taken_over_and_only_editors_may(client, as_user):
    srv, _ = homebox("items")
    url = f"http://127.0.0.1:{srv.server_address[1]}/api/v1"
    try:
        csv = "HB.import_ref,HB.location,HB.name\nr1,Home / Kitchen,Fridge\n"
        assert client.post("/api/import/homebox", content=csv.encode()).json()["added"] == 1
        u = client.get("/api/auth/me").json()
        r = homebox_api.start(u.get("user", u), url, "a@b.c", "pw", background=False)
        assert (r["added"], r["changed"]) == (1, 1), "the fridge from the CSV is the same fridge"
        assert db.one("SELECT COUNT(*) AS n FROM thg_items WHERE name = 'Fridge'")["n"] == 1
        as_user("meg", "member")
        assert client.post("/api/import/homebox-server", json={"url": url, "username": "a", "password": "pw"}).status_code == 403
        sign_in(client, "alex")
        assert client.post("/api/import/homebox-server", json={"url": "http://169.254.169.254", "username": "a", "password": "pw"}).status_code == 400
    finally:
        srv.shutdown()
