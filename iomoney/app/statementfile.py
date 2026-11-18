"""Holding the bank's own file against an account: a statement's PDF, or the CSV, OFX or QFX file from its website.

The file is read (statementpdf, importer) into what the bank says happened: lines of a day, an amount and a text,
the days they cover and, where the file gives them, the balance at the start and at the end. Each line is then looked
for among the account's transactions: the same amount, on the nearest day within a few (a bank and Monarch Money do
not always agree on the day), each transaction for one line only. A CSV, OFX or QFX file says which way the money
went, so there the sign counts too (and a file that writes money out as a positive number is turned around when that
fits better); a PDF often does not, so there the amount alone can do.

What comes out, for the Reconcile page: the transactions found (to tick), the lines the account does not have
(missing: with the transaction of nearly that day and name whose amount differs, when there is one), the lines it has
under a day outside the statement or still pending (elsewhere), and the transactions of those days the bank does not
show (extra). Nothing is changed and the file is not kept: the person looks, adds or corrects, and finishes."""
import datetime as dt
import re
from collections import defaultdict
from decimal import Decimal

from iosuite_shared.errors import Invalid

from app import db, importer, model, statementpdf, statements

NEAR = 5        # days a transaction may stand from the bank's line
DIFFERS = 3     # days within which a transaction of another amount is taken for the same one
MAX_LISTED = 500
BALANCE_HEADINGS = ("balance", "running balance", "running bal.", "running bal", "account balance", "ledger balance", "saldo", "solde")


# ------------------------------------------------------------------ the file, as lines

def _text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _ofx_days(text: str) -> tuple:
    out = []
    for tag in ("DTSTART", "DTEND"):
        m = re.search(rf"<{tag}>(\d{{8}})", text, re.I)
        try:
            out.append(importer.date(m[1], "ymd") if m else None)
        except ValueError:
            out.append(None)
    return tuple(out)


def _csv_balances(rows: list[dict], columns: list[str]) -> tuple | None:
    """(the balance before the first line in time, the balance after the last, which way the amounts move it: 1 or
    -1), from a column of the balance after each line; None without one, or when it does not follow the amounts."""
    low = [c.lower().strip() for c in columns]
    col = next((low.index(h) for h in BALANCE_HEADINGS if h in low), None)
    if col is None:
        return None
    got = []
    for r in rows:
        try:
            b = importer.amount(r["cells"][col]) if col < len(r["cells"]) else None
        except ValueError:
            b = None
        if b is not None:
            got.append((r["amount"], b))
    if not got:
        return None
    if len(got) == 1:
        return got[0][1] - got[0][0], got[0][1], 1
    pairs = len(got) - 1
    best = None
    for oldest_first in (True, False):
        for s in (1, -1):
            if oldest_first:
                n = sum(1 for i in range(1, len(got)) if got[i][1] == got[i - 1][1] + s * got[i][0])
            else:
                n = sum(1 for i in range(pairs) if got[i][1] == got[i + 1][1] + s * got[i][0])
            if best is None or n > best[0]:
                best = (n, oldest_first, s)
    n, oldest_first, s = best
    if n < pairs * 0.6:
        return None
    first, last = (got[0], got[-1]) if oldest_first else (got[-1], got[0])
    return first[1] - s * first[0], last[1], s


def _file(a: dict, data: bytes, order: str | None) -> dict:
    """{kind, start, end, opening, closing (as the file gives them, or None), lines: [{day, text, amount, signed,
    others}], dateOrder, guessed, problems, strict: the file says which way the money went}."""
    if data[:1024].lstrip().startswith(b"%PDF"):
        got = statementpdf.read(data, owed=not a["is_asset"], order=order)
        return {**got, "kind": "pdf", "problems": 0, "strict": False}
    if b"\x00" in data[:2000]:
        raise Invalid("This file is neither a PDF nor a text file: take the statement's PDF, or a CSV, OFX or QFX file from the bank's website")
    text = _text(data)
    if not text.strip():
        raise Invalid("The file is empty")
    if importer._is_ofx(text):
        got = importer._ofx(text)
        start, end = _ofx_days(text)
        closing = None if got["balance"] is None else got["balance"] if a["is_asset"] else abs(got["balance"])
        balances = None
    else:
        got = importer._csv(text, None, order)
        if got.get("needs"):
            raise Invalid("The file's columns could not be told apart: it needs a column of dates and one of amounts, with headings")
        start = end = closing = None
        balances = _csv_balances(got["rows"], got["columns"])
    rows = got["rows"]
    if not rows:
        raise Invalid("No transactions could be read from this file")
    days = [r["day"] for r in rows]
    if not (start and end and start <= min(days) and max(days) <= end <= dt.date.today() + dt.timedelta(days=1)):
        start, end = min(days), max(days)
    lines = [{"day": r["day"], "text": re.sub(r"\s+", " ", r["payee"] or r["notes"] or "").strip()[:255], "amount": r["amount"], "signed": True,
              "others": []} for r in rows if r["amount"]]
    return {"kind": got["kind"], "start": start, "end": end, "opening": None, "closing": closing, "balances": balances, "lines": lines,
            "dateOrder": got["dateOrder"], "guessed": got["guessed"], "problems": len(got["problems"]), "strict": True}


# ------------------------------------------------------------------ the lines against the account

def _candidates(a: dict, start: dt.date, end: dt.date, listed: set) -> list[dict]:
    """The transactions a line of the file may be: the ones the Reconcile page lists for these days (in: true), and
    around them the ones a few days before or after, and the pending ones."""
    rows = db.q("SELECT id, day, amount, pending, merchant, description FROM mny_transactions WHERE account_id = %s AND day BETWEEN %s AND %s",
                (a["id"], start - dt.timedelta(days=statements.EARLIER_DAYS), end + dt.timedelta(days=NEAR)))
    out = []
    for r in rows:
        inside = r["id"] in listed
        if not inside and r["day"] < start - dt.timedelta(days=NEAR):
            continue
        out.append({"id": r["id"], "day": r["day"], "amount": Decimal(r["amount"]), "in": inside, "pending": bool(r["pending"]),
                    "name": r["merchant"] or r["description"] or "", "words": _words(r["merchant"], r["description"])})
    return out


def _words(*texts) -> set:
    return set(re.findall(r"[a-z]{3,}", " ".join(t or "" for t in texts).lower()))


def _match(lines: list[dict], cands: list[dict], strict: bool, flip: bool = False) -> dict:
    """{the line's number: the transaction it is}. The nearest day first; a transaction the page lists before one it
    does not. strict: the sign counts for every line; otherwise for the lines that have one first, then the amount
    alone, then the line's further amounts."""
    by = defaultdict(list)
    for c in cands:
        by[abs(c["amount"])].append(c)
    got, used = {}, set()

    def go(amounts, signs: bool):
        for d in range(NEAR + 1):
            for n, ln in enumerate(lines):
                if n in got:
                    continue
                for amt in amounts(ln):
                    best = None
                    for c in by.get(abs(amt), ()):
                        if c["id"] in used or abs((c["day"] - ln["day"]).days) != d:
                            continue
                        if signs and (c["amount"] > 0) != ((-amt if flip else amt) > 0):
                            continue
                        rank = (not c["in"], c["pending"], c["id"])
                        if best is None or rank < best[0]:
                            best = (rank, c)
                    if best:
                        got[n] = best[1]
                        used.add(best[1]["id"])
                        break
    go(lambda ln: [ln["amount"]] if strict or ln["signed"] else [], True)
    if not strict:
        go(lambda ln: [ln["amount"]], False)
        go(lambda ln: ln["others"], False)
    return got


def _line(ln: dict, flip: bool = False) -> dict:
    return {"day": ln["day"].isoformat(), "text": ln["text"], "amount": model.n2(-ln["amount"] if flip else ln["amount"]), "signed": ln["signed"]}


def read(u: dict, a: dict, data: bytes, name: str | None = None, order: str | None = None, flip: str | None = None) -> dict:
    """The bank's file (a statement's PDF, or a CSV, OFX or QFX file) held against the account. order: how day and
    month stand in its dates (mdy, dmy, ymd), when the guess is wrong; flip: 1 or 0, whether the file writes money
    out as a positive number (CSV, OFX; as left out: whichever fits the account better).

    {kind: pdf, csv or ofx, name, start, end, opening, closing (None where the file does not give them), worked (true:
    the closing balance is the opening one ioMoney keeps plus the file's lines), adds (the lines add up to the two
    balances: true, false, or None when that cannot be told), total: the lines read, sum: what they add up to (None
    when the file does not say which way each went), matched: [ids of the transactions found, to tick], missing:
    [{day, text, amount, signed, differs?: {id, day, amount, name}}] the lines the account does not have, elsewhere:
    [{day, text, amount, id, at, why: before, after or pending}] the lines it has outside the statement, extra: [ids
    of the transactions of these days the file does not show], dateOrder, guessed, flipped, problems: the rows that
    could not be read}."""
    if not data:
        raise Invalid("The file is empty")
    f = _file(a, data, order if order in importer.ORDERS else None)
    start, end, lines = f["start"], f["end"], f["lines"]
    sign = Decimal(1) if a["is_asset"] else Decimal(-1)
    out = {"kind": f["kind"], "name": (name or "")[:200] or None, "start": start.isoformat() if start else None,
           "end": end.isoformat() if end else None, "opening": None, "closing": None, "worked": False, "adds": None, "total": len(lines),
           "sum": None, "matched": [], "missing": [], "elsewhere": [], "extra": [], "dateOrder": f["dateOrder"], "guessed": f["guessed"],
           "flipped": False, "problems": f["problems"]}
    if not (start and end):  # balances alone: nothing to compare
        out.update(opening=model.n2(f["opening"]), closing=model.n2(f["closing"]))
        return out
    if (end - start).days > 400:
        raise Invalid("The file covers more than 400 days: take one of a shorter time")
    listed = statements.lines(u, a, start, end)["items"]
    cands = _candidates(a, start, end, {t["id"] for t in listed})
    flipped = False
    if f["strict"]:
        if flip in ("0", "1"):
            flipped = flip == "1"
            got = _match(lines, cands, True, flipped)
        else:  # the way round that finds more
            got, other = _match(lines, cands, True), _match(lines, cands, True, True)
            if len(other) > len(got):
                got, flipped = other, True
    else:
        got = _match(lines, cands, False)
    out["flipped"] = flipped
    # the balances
    opening, closing = f["opening"], f["closing"]
    total = sum((-ln["amount"] if flipped else ln["amount"] for ln in lines), Decimal(0)) if all(ln["signed"] for ln in lines) else None
    out["sum"] = model.n2(total)
    if f.get("balances"):
        opening, closing, _ = f["balances"]
        if not a["is_asset"] and closing - opening != sign * (total or 0):  # what is owed, counted below zero in the file
            opening, closing = (-opening, -closing) if closing - opening == -sign * (total or 0) else (abs(opening), abs(closing))
    if total is not None and opening is None:
        if closing is not None:  # an OFX file: the balance at its end
            opening = closing - sign * total
        else:  # no balance in the file: from the one kept for the day before, the file's lines give the one at the end
            before = db.one("SELECT closing FROM mny_statements WHERE account_id = %s AND end_day = %s", (a["id"], start - dt.timedelta(days=1)))
            opening = Decimal(before["closing"]) if before else statements.balance_before(a, start)
            if opening is not None:
                closing, out["worked"] = opening + sign * total, True
    if total is not None and opening is not None and closing is not None and not out["worked"] and f["kind"] == "pdf":
        out["adds"] = closing - opening == sign * total
    out.update(opening=model.n2(opening), closing=model.n2(closing))
    # what was found, and where
    found = set()
    for n, c in sorted(got.items()):
        ln = lines[n]
        if c["in"]:
            out["matched"].append(c["id"])
        else:
            out["elsewhere"].append({**_line(ln, flipped), "id": c["id"], "at": c["day"].isoformat(),
                                     "why": "pending" if c["pending"] else "before" if c["day"] < start else "after"})
        found.add(c["id"])
    out["matched"].sort()
    # what the account does not have: with the transaction of another amount that looks like it
    left = [c for c in cands if c["in"] and c["id"] not in found and start <= c["day"] <= end]
    taken = set()
    for n, ln in enumerate(lines):
        if n in got:
            continue
        row = _line(ln, flipped)
        words = _words(ln["text"])
        amt = -ln["amount"] if flipped else ln["amount"]
        best = None
        for c in left:
            both = len(words & c["words"])
            away = abs((c["day"] - ln["day"]).days)
            if c["id"] in taken or not both or away > DIFFERS or (ln["signed"] and (c["amount"] > 0) != (amt > 0)):
                continue
            if best is None or (-both, away) < best[0]:
                best = ((-both, away), c)
        if best:
            c = best[1]
            taken.add(c["id"])
            row["differs"] = {"id": c["id"], "day": c["day"].isoformat(), "amount": model.n2(c["amount"]), "name": c["name"]}
        out["missing"].append(row)
    out["extra"] = [c["id"] for c in sorted(left, key=lambda c: (c["day"], c["id"]))]
    out["missingCount"], out["missing"] = len(out["missing"]), out["missing"][:MAX_LISTED]
    return out
