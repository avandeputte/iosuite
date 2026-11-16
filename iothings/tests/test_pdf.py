"""The whole inventory as one PDF: a summary, the list, each thing with its details, photos and log, its receipt as a
picture, its manual (a PDF) put in whole after its page, and a file that is neither named; archived things only when
asked."""
import io

from fpdf import FPDF
from PIL import Image
from pypdf import PdfReader

from app import pdf


def png(w=800, h=600, colour=(200, 60, 40)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(out, "PNG")
    return out.getvalue()


def manual(pages: int) -> bytes:
    d = FPDF()
    for i in range(pages):
        d.add_page()
        d.set_font("Helvetica", size=14)
        d.cell(0, 10, f"Manual page {i + 1}")
    return bytes(d.output())


def add_file(client, iid, name, raw, mime, kind=None):
    params = {"name": name, **({"kind": kind} if kind else {})}
    r = client.post(f"/api/items/{iid}/files", params=params, content=raw, headers={"Content-Type": mime})
    assert r.status_code in (200, 201), r.text
    return r.json()


def text_of(raw: bytes) -> str:
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(raw)).pages)


def test_the_inventory_as_one_pdf(client):
    assert client.get("/api/export-pdf").json()["state"] in ("idle", "done", "failed")
    tv = client.post("/api/items", json={"name": "Télévision OLED", "location": "Home / Living room", "purchasePrice": 1899.99,
                                         "purchaseDate": "2024-11-29", "serialNumber": "SN-TV-1", "manufacturer": "LG",
                                         "insured": True, "fields": [{"name": "Size", "value": "65 in"}]}).json()
    add_file(client, tv["id"], "front.png", png(), "image/png")
    add_file(client, tv["id"], "receipt.png", png(600, 1200, (250, 250, 250)), "image/png", "receipt")
    add_file(client, tv["id"], "manual.pdf", manual(3), "application/pdf", "manual")
    add_file(client, tv["id"], "notes.docx", b"PK\x03\x04 not really", "application/octet-stream", "other")
    client.post(f"/api/items/{tv['id']}/maintenance", json={"date": "2025-06-01", "title": "Wall mount checked", "cost": 40})
    sofa = client.post("/api/items", json={"name": "Sofa", "location": "Home / Living room", "purchasePrice": 1200}).json()
    old = client.post("/api/items", json={"name": "Old drill", "archived": True, "purchasePrice": 80}).json()
    assert sofa["id"] and old["id"]

    r = client.post("/api/export-pdf", json={})
    assert r.status_code in (200, 201), r.text
    j = r.json()
    while j["state"] == "running":
        import time
        time.sleep(0.2)
        j = client.get("/api/export-pdf").json()
    assert j["state"] == "done" and j["ready"], j
    assert (j["things"], j["files"]) == (2, 3), j
    assert j["missing"] == ["Télévision OLED: notes.docx"], j
    got = client.get("/api/export-pdf/file")
    assert got.status_code == 200 and got.headers["content-type"] == "application/pdf"
    assert "home-inventory-" in got.headers["content-disposition"]
    raw = got.content
    reader = PdfReader(io.BytesIO(raw))
    words = text_of(raw)
    assert "Home inventory" in words and "3,099.99" in words, "the total of what was paid"
    assert "SN-TV-1" in words and "65 in" in words and "Wall mount checked" in words
    assert "Old drill" not in words, "archived things only when asked"
    assert "Manual page 3" in words, "the manual is in it, whole"
    pages = [p.extract_text() or "" for p in reader.pages]
    tv_page = next(i for i, t in enumerate(pages) if "SN-TV-1" in t)
    first_manual = next(i for i, t in enumerate(pages) if "Manual page 1" in t)
    sofa_page = next(i for i, t in enumerate(pages) if t.strip().startswith("Sofa") or "\nSofa\n" in t and i > tv_page)
    assert tv_page < first_manual < sofa_page or sofa_page < tv_page < first_manual, "the manual comes right after its thing"
    outline = [o.title for o in reader.outline if not isinstance(o, list)]
    assert outline[:2] == ["Summary", "Everything"] and "Home / Living room" in outline

    pdf.start({"name": "alex"}, archived=True, background=False)
    assert "Old drill" in text_of(client.get("/api/export-pdf/file").content)


def test_a_viewer_may_make_it_too(client, as_user):
    client.post("/api/items", json={"name": "Lamp"})
    as_user("vic", "viewer")
    j = client.post("/api/export-pdf", json={}).json()
    assert j["state"] in ("running", "done")
