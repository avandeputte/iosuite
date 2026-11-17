"""The receipts of a transaction: a picture of the till slip, the PDF of the invoice.

The bytes are kept in the database (mny_receipt_parts, in parts of PART_BYTES), so the suite's database backup
(ioBackup) holds them too and nothing lives beside the app. A receipt is a picture or a PDF, told by its first bytes
(not by what the upload says it is), and is served as it came. Whoever sees the transaction sees its receipts; whoever
may change it adds and removes them. They go with the transaction when it is deleted; when Monarch gives a
transaction a new id (a pending one that posted), the sync carries them over to it (carry)."""
import mimetypes
import re

from iosuite_shared import related
from iosuite_shared.errors import Invalid

from app import config, db, model

PART_BYTES = 4 * 1024 * 1024
MAX_RECEIPTS = 20   # of one transaction
KIND = "transaction"  # what a transaction is called among the suite's linked items (iosuite_shared.related)
CARRY_DAYS = 10     # how far from the old one's day the transaction that took its place may be
# shown in the browser as they are; a picture the browser may not draw (HEIC) is a download
INLINE = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp"}


def sniff(raw: bytes) -> str | None:
    """What the bytes are: a PDF or a picture, or None."""
    if raw[:5] == b"%PDF-":
        return "application/pdf"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[4:8] == b"ftyp" and raw[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"heim", b"heis"):
        return "image/heic"
    return None


def _name(v: str | None, mime: str) -> str:
    s = re.sub(r"[\x00-\x1f/\\]+", " ", str(v or "")).strip()[:255]
    return s or "receipt" + (mimetypes.guess_extension(mime) or "")


def _public(r: dict) -> dict:
    return {"id": r["id"], "name": r["name"], "mime": r["mime"], "size": int(r["size"]), "url": f"api/receipts/{r['id']}",
            "added": r["created_at"].isoformat() if r.get("created_at") else None}


def of(ids: list) -> dict:
    """{transaction id: its receipts, the first added first: [{id, name, mime, size, url, added}]}."""
    ids = [int(i) for i in ids]
    out: dict = {}
    if not ids:
        return out
    for r in db.q("SELECT id, transaction_id, name, mime, size, created_at FROM mny_receipts "
                  f"WHERE transaction_id IN ({db.marks(len(ids))}) ORDER BY transaction_id, id", ids):
        out.setdefault(r["transaction_id"], []).append(_public(r))
    return out


def mark(items: list[dict]) -> list[dict]:
    """Each transaction (as tx_public gives it) with receipts: its receipts, or [] without any."""
    got = of([t["id"] for t in items])
    for t in items:
        t["receipts"] = got.get(t["id"], [])
    return items


def add(u: dict, t: dict, raw: bytes, name: str | None) -> dict:
    """Keep a receipt with the transaction: the receipt as listed."""
    model._need(model.can_write(u, t))
    if not raw:
        raise Invalid("The file is empty")
    if len(raw) > config.MAX_RECEIPT_BYTES:
        raise Invalid(f"Receipts up to {config.MAX_RECEIPT_BYTES // (1024 * 1024)} MB")
    mime = sniff(raw)
    if not mime:
        raise Invalid("A receipt is a picture (JPEG, PNG, WebP, GIF, HEIC) or a PDF")
    with db.tx():
        if db.one("SELECT COUNT(*) AS n FROM mny_receipts WHERE transaction_id = %s", (t["id"],))["n"] >= MAX_RECEIPTS:
            raise Invalid(f"A transaction holds at most {MAX_RECEIPTS} receipts")
        rid = db.ex("INSERT INTO mny_receipts (transaction_id, name, mime, size, created_by) VALUES (%s, %s, %s, %s, %s)",
                    (t["id"], _name(name, mime), mime, len(raw), u.get("id")))
        for i in range(0, len(raw), PART_BYTES):
            db.ex("INSERT INTO mny_receipt_parts (receipt_id, n, data) VALUES (%s, %s, %s)", (rid, i // PART_BYTES, raw[i:i + PART_BYTES]))
    return _public(db.one("SELECT id, name, mime, size, created_at FROM mny_receipts WHERE id = %s", (rid,)))


def _row(u: dict, rid) -> tuple[dict, dict]:
    """(the receipt, its transaction), for someone who sees the transaction."""
    r = db.one("SELECT id, transaction_id, name, mime, size, created_at FROM mny_receipts WHERE id = %s", (int(rid),))
    if not r:
        raise model.NotFound("No such receipt")
    try:
        return r, model.transaction(u, r["transaction_id"])
    except model.NotFound:
        raise model.NotFound("No such receipt") from None


def content(u: dict, rid) -> tuple[bytes, str, str]:
    """(bytes, type, name) of a receipt."""
    r, _t = _row(u, rid)
    parts = db.q("SELECT data FROM mny_receipt_parts WHERE receipt_id = %s ORDER BY n", (r["id"],))
    return b"".join(bytes(p["data"]) for p in parts), r["mime"], r["name"]


def remove(u: dict, rid) -> None:
    r, t = _row(u, rid)
    model._need(model.can_write(u, t))
    db.ex("DELETE FROM mny_receipts WHERE id = %s", (r["id"],))


# ------------------------------------------------------------------ when transactions go

def forget(tids) -> None:
    """Transactions are going (deleted, or their account is): their links to the suite's other items go too. Their
    receipts go with them by themselves."""
    tids = [int(i) for i in tids]
    if tids:
        related.forget_many(KIND, related.having(KIND, tids))


def carry(gone: list[int], seen: set) -> int:
    """Monarch no longer has these transactions; the ones it sent this time have the ids in seen. A pending
    transaction that posted comes back under another id: what was kept with the old one here (its receipts, its own
    tags, its links to the suite's other items, its split when the amount stayed) moves to the one that took its place: in
    the same account, within CARRY_DAYS, of the same amount, or of the same payee and nearly the amount (a tip
    added). How many were carried over; the links of the others are removed."""
    gone = [int(i) for i in gone]
    if not gone:
        return 0
    marks = db.marks(len(gone))
    kept = {r["transaction_id"] for r in db.q(f"SELECT DISTINCT transaction_id FROM mny_receipts WHERE transaction_id IN ({marks})", gone)}
    linked = {int(i) for i in related.having(KIND, gone)}
    split = {r["transaction_id"] for r in db.q(f"SELECT DISTINCT transaction_id FROM mny_splits WHERE transaction_id IN ({marks})", gone)}
    tagged = {r["transaction_id"] for r in db.q(f"SELECT DISTINCT transaction_id FROM mny_tags WHERE transaction_id IN ({marks})", gone)}
    want = sorted(kept | linked | split | tagged)
    n, taken = 0, set(gone)
    for old in (db.q(f"SELECT id, account_id, day, amount, merchant FROM mny_transactions WHERE id IN ({db.marks(len(want))}) ORDER BY id", want) if want else []):
        cands = db.q("SELECT id, day, amount, merchant, external_id FROM mny_transactions WHERE source = 'monarch' AND account_id = %s "
                     "AND day BETWEEN DATE_SUB(%s, INTERVAL %s DAY) AND DATE_ADD(%s, INTERVAL %s DAY)",
                     (old["account_id"], old["day"], CARRY_DAYS, old["day"], CARRY_DAYS))

        def fits(c, old=old):
            if c["id"] in taken or c["external_id"] not in seen:
                return False
            if c["amount"] == old["amount"]:
                return True
            a, b = float(old["amount"]), float(c["amount"])
            same = (old["merchant"] or "").strip().lower() == (c["merchant"] or "").strip().lower() and old["merchant"]
            return bool(same) and a * b > 0 and abs(b - a) <= 0.3 * abs(a)
        cands = sorted((c for c in cands if fits(c)), key=lambda c: (c["amount"] != old["amount"], abs((c["day"] - old["day"]).days), c["id"]))
        if not cands:
            continue
        new = cands[0]
        taken.add(new["id"])
        with db.tx():
            db.ex("UPDATE mny_receipts SET transaction_id = %s WHERE transaction_id = %s", (new["id"], old["id"]))
            db.ex("UPDATE IGNORE mny_tags SET transaction_id = %s WHERE transaction_id = %s", (new["id"], old["id"]))
            if old["id"] in split and new["amount"] == old["amount"] and not db.one("SELECT 1 AS x FROM mny_splits WHERE transaction_id = %s LIMIT 1", (new["id"],)):
                db.ex("UPDATE mny_splits SET transaction_id = %s WHERE transaction_id = %s", (new["id"], old["id"]))
                db.ex("UPDATE mny_transactions SET edited = 1 WHERE id = %s", (new["id"],))
                moved_split = True
            else:
                moved_split = False
        if moved_split or old["id"] in tagged:
            from app import splits
            splits.rewords(new["id"])
        if old["id"] in linked:
            related.move(KIND, old["id"], new["id"])
            linked.discard(old["id"])
        n += 1
    related.forget_many(KIND, linked)
    return n
