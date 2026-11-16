"""The whole inventory as one PDF, to keep somewhere else (a cloud drive, a USB stick at work) for the day the house
burns down and the insurer asks what was in it.

What is in it:
- a first page: when it was made, how many things, what they cost all together, and that per place;
- a list of every thing (place, quantity, bought on, price, serial number), each name a link to its pages;
- each thing on its own pages: every detail, its own fields, who it is for, its photos, its maintenance log, then its
  receipts, warranty cards and manuals: pictures shown as they are, PDFs put in whole right after the thing's page.
  A file that is neither (a .docx, a picture this server cannot read) is named, so it can be found in ioThings.
The PDF's outline (the bookmarks of a PDF reader) has each place and each thing.

Photos are made smaller (PHOTO_SIDE) so a few hundred things stay a file one can mail or copy; receipts and warranty
cards keep more of their size (PAPER_SIDE), so the small print stays readable. PDFs go in as they are.

Making it takes a while (every photo is read from the database), so it is made in the background: start() begins it,
progress() says how far it got and, when done, file() gives the PDF. One at a time; the last one made is kept (in a
temporary folder) until the next one, or until the app restarts.

Text: DejaVu Sans when the system has it (most languages; Docker and the Proxmox installer add it, or
`apt install fonts-dejavu-core`), else Liberation or FreeSans; without any, the PDF's own Helvetica, which writes Western
European languages, with anything else replaced.
"""
import datetime as dt
import io
import logging
import os
import tempfile
import threading
from decimal import Decimal

from fpdf import FPDF
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from iosuite_shared.errors import Invalid

from app import db, files, model, upkeep

log = logging.getLogger("iothings")

PHOTO_SIDE = 1400
PAPER_SIDE = 2200
FONTS = [(f"{d}/DejaVuSans.ttf", f"{d}/DejaVuSans-Bold.ttf") for d in
         ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF", "/usr/local/share/fonts")] + [
         ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
         ("/usr/share/fonts/truetype/freefont/FreeSans.ttf", "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
         ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf")]
LETTER = {"USD", "CAD", "MXN"}  # where paper is Letter; A4 elsewhere
PAPERS = ("receipt", "warranty", "manual", "other")
NAMES = {"photo": "Photo", "manual": "Manual", "receipt": "Receipt", "warranty": "Warranty", "other": "File"}

_lock = threading.Lock()
_job: dict = {"state": "idle"}
_dir = tempfile.mkdtemp(prefix="iothings-pdf-")


# ---- money and dates in words

def _money(v, cur: str) -> str:
    if v is None:
        return ""
    v = Decimal(str(v))
    sign = {"USD": "$", "CAD": "$", "AUD": "$", "NZD": "$", "MXN": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "INR": "₹"}.get(cur)
    s = f"{v:,.0f}" if cur == "JPY" else f"{v:,.2f}"
    return f"{sign}{s}" if sign else f"{s} {cur}"


def _day(v) -> str:
    return v.strftime("%-d %b %Y") if isinstance(v, (dt.date, dt.datetime)) else (v or "")


# ---- pictures

def _picture(raw: bytes, side: int) -> tuple[bytes, int, int] | None:
    """(JPEG, width, height) of a picture, upright and at most `side` pixels on its long side; None when it is not a
    picture this server reads."""
    try:
        im = Image.open(io.BytesIO(raw))
        if im.width * im.height > files.MAX_PIXELS:
            return None
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            back = Image.new("RGB", im.size, (255, 255, 255))
            back.paste(im, mask=im.split()[-1])
            im = back
        else:
            im = im.convert("RGB")
        im.thumbnail((side, side), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82, optimize=True)
        return out.getvalue(), im.width, im.height
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


# ---- the document

class _Doc(FPDF):
    def __init__(self, paper: str, made: str):
        super().__init__(format=paper, unit="mm")
        self.made = made
        self.set_margins(16, 16, 16)
        self.set_auto_page_break(True, 18)
        self.set_title("Home inventory")
        self.set_creator("ioThings")
        self.uni = False
        for path, bold in FONTS:
            if os.path.exists(path):
                try:
                    self.add_font("Body", "", path)
                    self.add_font("Body", "B", bold if os.path.exists(bold) else path)
                    self.uni = True
                    break
                except Exception:  # a font it cannot read: the next one, or Helvetica
                    continue
        self.face = "Body" if self.uni else "Helvetica"

    def t(self, s) -> str:
        """Text the font can write."""
        s = "" if s is None else str(s)
        if self.uni:
            return s
        s = s.translate({0x2019: "'", 0x2018: "'", 0x201c: '"', 0x201d: '"', 0x2013: "-", 0x2014: "-", 0x2026: "...", 0x20ac: "EUR ", 0x20b9: "INR "})
        return s.encode("latin-1", "replace").decode("latin-1")

    def font(self, size: float, bold: bool = False, grey: bool = False):
        self.set_font(self.face, "B" if bold else "", size)
        self.set_text_color(*((110, 110, 110) if grey else (20, 20, 20)))

    def footer(self):
        self.set_y(-12)
        self.font(7.5, grey=True)
        self.cell(0, 5, self.t(f"Home inventory · ioThings · made {self.made}"), align="C")

    def line_of(self, text: str, size: float = 10, bold: bool = False, grey: bool = False, h: float = 5.2, link=None):
        self.font(size, bold, grey)
        self.multi_cell(0, h, self.t(text), align="L", new_x="LMARGIN", new_y="NEXT", link=link or "")

    def room(self, mm: float) -> None:
        if self.get_y() + mm > self.h - self.b_margin:
            self.add_page()


def _things(archived: bool) -> list[dict]:
    rows = model.find(archived="also" if archived else None, limit=5000)
    places = {x["id"]: x["path"] for x in model.locations()}
    for r in rows:
        r["place"] = places.get(r["location_id"]) or ""
    rows.sort(key=lambda r: (r["place"] == "", r["place"].lower(), r["name"].lower(), r["id"]))
    return rows


def _details(r: dict, cur: str, tags: dict, people: dict) -> list[tuple[str, str]]:
    w = model.warranty(r)
    warranty = ("Lifetime" if r["lifetime_warranty"] else f"until {_day(r['warranty_expires'])}" if r["warranty_expires"] else "")
    if w and w["state"] == "expired":
        warranty += " (ended)"
    rows = [("Quantity", str(r["quantity"]) if r["quantity"] != 1 else ""),
            ("Description", r["description"]), ("Manufacturer", r["manufacturer"]), ("Model", r["model_number"]),
            ("Serial number", r["serial_number"]), ("Asset ID", r["asset_id"]),
            ("Bought", _day(r["purchase_date"])), ("Price", _money(r["purchase_price"], cur)), ("Bought from", r["purchase_from"]),
            ("Warranty", warranty), ("Warranty details", r["warranty_details"]), ("Insured", "Yes" if r["insured"] else ""),
            ("Labels", ", ".join(x["name"] for x in tags.get(r["id"], []))),
            ("For", ", ".join(x.get("displayName") or x.get("name") or "" for x in people.get(r["id"], []))),
            ("Web page", r["url"])]
    if r["archived"]:
        rows.append(("Archived", "Yes" + (f", sold {_day(r['sold_date'])}" if r["sold_date"] else "")))
        rows += [("Sold for", _money(r["sold_price"], cur)), ("Sold to", r["sold_to"]), ("Sale notes", r["sold_notes"])]
    rows += [(f["name"], f["value"]) for f in r["fields"] or []]
    rows.append(("Notes", r["notes"]))
    return [(k, str(v)) for k, v in rows if v not in (None, "")]


def _table(pdf: _Doc, rows: list[tuple[str, str]]) -> None:
    key = 42
    for k, v in rows:
        pdf.room(6)
        y = pdf.get_y()
        pdf.font(9, grey=True)
        tall = 5 * len(pdf.multi_cell(key - 2, 5, pdf.t(k), align="L", dry_run=True, output="LINES"))
        pdf.multi_cell(key - 2, 5, pdf.t(k), align="L", new_x="RIGHT", new_y="TOP")
        pdf.set_x(pdf.l_margin + key)
        pdf.font(9.5)
        pdf.multi_cell(0, 5, pdf.t(v), align="L", new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(max(pdf.get_y(), y + tall) + 0.8)


def _photos(pdf: _Doc, pics: list[tuple[bytes, int, int]]) -> None:
    """Two to a row, each at most 75 mm high."""
    if not pics:
        return
    pdf.ln(2)
    gap = 5
    col = (pdf.epw - gap) / 2
    for i in range(0, len(pics), 2):
        row = pics[i:i + 2]
        sizes = []
        for _, w, h in row:
            ww = col if len(pics) > 1 else min(pdf.epw, 120)
            hh = ww * h / w
            if hh > 75:
                hh, ww = 75, 75 * w / h
            sizes.append((ww, hh))
        tall = max(s[1] for s in sizes)
        pdf.room(tall + 3)
        y = pdf.get_y()
        for n, ((raw, _, _), (ww, hh)) in enumerate(zip(row, sizes)):
            pdf.image(io.BytesIO(raw), x=pdf.l_margin + n * (col + gap), y=y, w=ww, h=hh)
        pdf.set_y(y + tall + gap)


def _paper(pdf: _Doc, raw: bytes, w: int, h: int, caption: str) -> None:
    """A receipt or warranty card as a picture: as large as fits, on a new page when it does not fit here."""
    ww = pdf.epw
    hh = ww * h / w
    most = pdf.h - pdf.t_margin - pdf.b_margin - 10
    if hh > most:
        hh, ww = most, most * w / h
    if pdf.get_y() + hh + 8 > pdf.h - pdf.b_margin:
        pdf.add_page()
    pdf.line_of(caption, 9, bold=True)
    pdf.image(io.BytesIO(raw), x=pdf.l_margin, y=pdf.get_y() + 1, w=ww, h=hh)
    pdf.set_y(pdf.get_y() + hh + 5)


def build(archived: bool = False, out_path: str | None = None, step=None) -> dict:
    """Make the PDF; {path, things, pages, files, missing}. step(done, total) is told after each thing."""
    cur = model.currency()
    made = dt.datetime.now().strftime("%-d %B %Y, %H:%M")
    pdf = _Doc("Letter" if cur in LETTER else "A4", made)
    things = _things(archived)
    ids = [r["id"] for r in things]
    tags, people = model._labels_of(ids), model._people_of(ids)
    links: dict = {}  # made once the first page is there (a link needs a page), aimed at each thing's page when it is made

    # ---- the first page
    pdf.add_page()
    links.update({r["id"]: pdf.add_link(page=1) for r in things})
    pdf.start_section("Summary")
    pdf.line_of("Home inventory", 24, bold=True, h=11)
    pdf.line_of(f"Made {made} by ioThings: {len(things)} things"
                + (" (archived and sold ones included)" if archived else " (archived and sold ones left out)") + ".", 10, grey=True)
    pdf.ln(4)
    total = sum((Decimal(str(r["purchase_price"])) for r in things if r["purchase_price"] is not None), Decimal(0))
    priced = sum(1 for r in things if r["purchase_price"] is not None)
    insured = sum(1 for r in things if r["insured"])
    papers = {r["item_id"]: r["n"] for r in db.q("SELECT item_id, COUNT(*) AS n FROM thg_files WHERE kind IN ('receipt', 'warranty') GROUP BY item_id")}
    _table(pdf, [("Things", str(len(things))), ("Paid for them", f"{_money(total, cur)} (the {priced} with a price)"),
                 ("With a receipt or warranty", str(sum(1 for r in things if papers.get(r["id"])))), ("Marked insured", str(insured))])
    by_place: dict = {}
    for r in things:
        p = by_place.setdefault(r["place"] or "No place", [0, Decimal(0)])
        p[0] += 1
        p[1] += Decimal(str(r["purchase_price"])) if r["purchase_price"] is not None else 0
    if by_place:
        pdf.ln(3)
        pdf.line_of("By place", 13, bold=True, h=7)
        for name, (n, v) in by_place.items():
            pdf.room(6)
            pdf.font(9.5)
            pdf.cell(pdf.epw - 60, 5.5, pdf.t(name))
            pdf.cell(20, 5.5, str(n), align="R")
            pdf.cell(40, 5.5, pdf.t(_money(v, cur) if v else ""), align="R", new_x="LMARGIN", new_y="NEXT")

    # ---- the list of everything
    pdf.add_page()
    pdf.start_section("Everything")
    pdf.line_of("Everything", 16, bold=True, h=9)
    cols = [("Thing", 0.40), ("Place", 0.24), ("Qty", 0.06), ("Bought", 0.14), ("Price", 0.16)]
    pdf.font(8.5, bold=True, grey=True)
    for name, f in cols:
        pdf.cell(pdf.epw * f, 6, pdf.t(name), align="R" if name in ("Qty", "Price") else "L")
    pdf.ln(6)
    for r in things:
        pdf.room(5.5)
        pdf.font(8.5)
        vals = [r["name"] + (" (archived)" if r["archived"] else ""), r["place"], str(r["quantity"]),
                _day(r["purchase_date"]), _money(r["purchase_price"], cur)]
        for (name, f), v in zip(cols, vals):
            w = pdf.epw * f
            v = pdf.t(v)
            while v and pdf.get_string_width(v) > w - 1.5:
                v = v[:-2] + "…" if pdf.uni else v[:-4] + "..."
            pdf.cell(w, 5, v, align="R" if name in ("Qty", "Price") else "L", link=links[r["id"]] if name == "Thing" else "")
        pdf.ln(5)

    # ---- each thing
    inserts: list[tuple[int, bytes, str]] = []  # (after this many pages, the PDF, its name)
    missing, nfiles = [], 0
    place = None
    for i, r in enumerate(things):
        pdf.add_page()
        pdf.set_link(links[r["id"]], page=pdf.page)
        if (r["place"] or "No place") != place:
            place = r["place"] or "No place"
            pdf.start_section(place, level=0)
        pdf.start_section(r["name"], level=1)
        pdf.line_of(r["name"], 17, bold=True, h=8.5)
        if r["place"]:
            pdf.line_of(r["place"], 10, grey=True)
        pdf.ln(2)
        _table(pdf, _details(r, cur, tags, people))
        listed = files.listed(r["id"])
        pics, papers_here, pdfs, other = [], [], [], []
        for f in listed:
            raw, mime, name = files.content(r["id"], f["id"])
            if f["kind"] == "photo":
                p = _picture(raw, PHOTO_SIDE)
                (pics.append(p) if p else other.append(f))
            elif mime == "application/pdf" or raw[:4] == b"%PDF":
                pdfs.append((f, raw))
            elif mime.startswith("image/") and (p := _picture(raw, PAPER_SIDE)):
                papers_here.append((f, p))
            else:
                other.append(f)
        _photos(pdf, pics)
        nfiles += len(pics)
        lines = upkeep.log_of(r["id"])
        if lines:
            pdf.room(14)
            pdf.line_of("Maintenance log", 11, bold=True, h=7)
            _table(pdf, [(_day(dt.date.fromisoformat(ln["date"])), ln["title"] + (f" ({_money(ln['cost'], cur)})" if ln["cost"] else "") + (f": {ln['notes']}" if ln["notes"] else ""))
                         for ln in lines])
        good = []
        for f, raw in sorted(pdfs, key=lambda x: PAPERS.index(x[0]["kind"]) if x[0]["kind"] in PAPERS else 9):
            try:
                n = len(PdfReader(io.BytesIO(raw)).pages)
                good.append((f, raw, n))
            except (PdfReadError, ValueError, OSError, KeyError, TypeError) as e:
                log.warning("PDF export: %s: %s: %s", r["name"], f["name"], e)
                other.append(f)
        if good:
            pdf.room(8 + 5 * len(good))
            pdf.ln(1)
            pdf.line_of("Put in whole after this thing's pages", 11, bold=True, h=7)
            for f, raw, n in good:
                pdf.line_of(f"{NAMES.get(f['kind'], 'File')}: {f['name']} ({n} page{'s' if n != 1 else ''})", 9.5)
        if other:
            pdf.room(8 + 5 * len(other))
            pdf.ln(1)
            pdf.line_of("Also kept in ioThings (not in this PDF)", 10, bold=True, h=6)
            for f in other:
                pdf.line_of(f"{NAMES.get(f['kind'], 'File')}: {f['name']}", 9, grey=True)
                missing.append(f"{r['name']}: {f['name']}")
        for f, (raw, w, h) in sorted(papers_here, key=lambda x: PAPERS.index(x[0]["kind"]) if x[0]["kind"] in PAPERS else 9):
            _paper(pdf, raw, w, h, f"{NAMES.get(f['kind'], 'File')}: {f['name']}")
            nfiles += 1
        for f, raw, n in good:
            inserts.append((pdf.page, raw, f["name"]))
            nfiles += 1
        if step:
            step(i + 1, len(things))

    # ---- the PDFs that came with the things, right after each thing's page
    main = io.BytesIO(pdf.output())
    writer = PdfWriter(clone_from=main)
    for after, raw, name in reversed(inserts):  # from the end, so the earlier positions stay right
        try:
            writer.merge(after, io.BytesIO(raw), import_outline=False)
        except Exception as e:  # a PDF pypdf cannot copy: named, the rest goes on
            log.warning("PDF export: %s: %s", name, e)
            missing.append(f"{name}: could not be put in")
    writer.add_metadata({"/Title": "Home inventory", "/Creator": "ioThings"})
    path = out_path or os.path.join(_dir, "inventory.pdf")
    with open(path, "wb") as fh:
        writer.write(fh)
    return {"path": path, "things": len(things), "pages": len(writer.pages), "files": nfiles, "missing": missing}


# ---- the job

def progress() -> dict:
    with _lock:
        out = {k: v for k, v in _job.items() if k != "path"}
    out["ready"] = out.get("state") == "done"
    return out


def start(u: dict, archived: bool = False, background: bool = True) -> dict:
    with _lock:
        if _job.get("state") == "running":
            raise Invalid("The PDF is being made already: it will be ready in a moment")
        _job.clear()
        _job.update(state="running", done=0, total=0, archived=bool(archived), by=u.get("displayName") or u.get("name"),
                    started=dt.datetime.now().isoformat(timespec="seconds"))
    if background:
        threading.Thread(target=_run, args=(archived,), name="pdf-export", daemon=True).start()
    else:
        _run(archived)
    return progress()


def _step(done: int, total: int) -> None:
    with _lock:
        _job.update(done=done, total=total)


def _run(archived: bool) -> None:
    try:
        tmp = os.path.join(_dir, "inventory.part.pdf")
        r = build(archived, tmp, _step)
        final = os.path.join(_dir, "inventory.pdf")
        os.replace(tmp, final)
        with _lock:
            _job.update(state="done", path=final, things=r["things"], pages=r["pages"], files=r["files"], missing=r["missing"][:300],
                        size=os.path.getsize(final), finished=dt.datetime.now().isoformat(timespec="seconds"))
    except Exception as e:
        log.exception("PDF export failed")
        with _lock:
            _job.update(state="failed", error=str(e) or e.__class__.__name__)


def file() -> tuple[str, str]:
    """(path, download name) of the last PDF made."""
    with _lock:
        path, when = _job.get("path"), _job.get("finished") or ""
    if _job.get("state") != "done" or not path or not os.path.exists(path):
        raise Invalid("No PDF has been made yet: make one first")
    return path, f"home-inventory-{when[:10] or dt.date.today().isoformat()}.pdf"
