"""Bringing a bank's file into an account kept by hand: a CSV export, or an OFX / QFX file ("Quicken", "Money").

The file is read here, never kept. An OFX or QFX file says what each field is. A CSV file does not: the columns are
guessed from their headings (the date, the amount or a money-out and a money-in column, the payee, a note, a
category) and from what they hold, and a person can say otherwise (mapping); so is the order of day and month in its
dates, and whether money out is written as a positive number (flip). A first pass (preview) shows what the file
holds and how much of it is new; the second one adds it.

What is already in the account is skipped: a transaction of the same day and amount (two of the same in the file and
one in the account: one is new), and anything an OFX file names by the same id as before. What comes in is the
account's own from then on (source manual), with the bank's text kept beside the payee, and goes through the
household's rules like any new transaction."""
import csv
import datetime as dt
import hashlib
import html
import io
import re
from collections import Counter
from decimal import Decimal, InvalidOperation

from iosuite_shared.errors import Invalid

from app import db, model

MAX_ROWS = 20000
SAMPLE = 12
FIELDS = ("date", "amount", "debit", "credit", "type", "payee", "notes", "category")
# a column's heading, as banks write it, for each field (the first that is found wins, in this order)
HEADINGS = {
    "date": ("transaction date", "trans date", "trans. date", "date", "posted date", "posting date", "post date", "booking date",
             "value date", "datum", "buchungstag", "date operation", "fecha"),
    "amount": ("amount", "transaction amount", "amt", "amount (usd)", "amount (eur)", "bedrag", "betrag", "montant", "importe", "value"),
    "debit": ("debit", "debits", "withdrawal", "withdrawals", "paid out", "money out", "debit amount", "withdrawal amount", "af", "soll"),
    "credit": ("credit", "credits", "deposit", "deposits", "paid in", "money in", "credit amount", "deposit amount", "bij", "haben"),
    "type": ("type", "transaction type", "debit/credit", "dr/cr", "credit debit indicator", "af bij"),
    "payee": ("payee", "merchant", "description", "name", "transaction description", "original description", "details", "narrative",
              "omschrijving", "verwendungszweck", "libelle", "concepto", "memo"),
    "notes": ("memo", "notes", "note", "reference", "extended description"),
    "category": ("category",),
}
MONTHS = {m: n for n, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}
ORDERS = ("mdy", "dmy", "ymd")


# ------------------------------------------------------------------ the pieces

def amount(v) -> Decimal | None:
    """A number as a bank writes it: 1,234.56, 1.234,56, (12.00), 12.00-, -12, $ 12, 12 CR / DR. None when empty."""
    s = str(v or "").strip()
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    m = re.search(r"\b(cr|dr)\.?$", s, re.I)
    if m:
        neg = neg or m[1].lower() == "dr"
        s = s[:m.start()]
    s = re.sub(r"[^\d,.\-+]", "", s)
    if s.endswith("-"):
        neg, s = True, s[:-1]
    if s.startswith("-"):
        neg, s = not neg, s[1:]
    s = s.lstrip("+")
    if "," in s and "." in s:  # the last of the two is the decimal mark
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:  # 12,50 is twelve and a half; 1,250 and 1,250,000 are thousands
        s = s.replace(",", ".") if re.fullmatch(r"\d+,\d{1,2}", s) else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(f"not an amount: {v}") from None
    if not d.is_finite() or abs(d) > model.MAX_AMOUNT:
        raise ValueError(f"not an amount: {v}")
    return (-d if neg else d).quantize(model.CENT)


def _parts(s: str) -> tuple | None:
    """A date's three numbers as written (a month by name becomes its number, marked), or None."""
    s = s.strip()
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
    if m:
        return ("ymd", int(m[1]), int(m[2]), int(m[3]))
    s = re.split(r"[T ]\d{1,2}:\d{2}", s)[0].strip()  # a time after it
    m = re.fullmatch(r"(\d{1,4})[./\-](\d{1,2})[./\-](\d{1,4})", s)
    if m:
        a, b, c = int(m[1]), int(m[2]), int(m[3])
        return ("ymd", a, b, c) if len(m[1]) == 4 else (None, a, b, c)
    m = re.fullmatch(r"([A-Za-z]{3})[a-z]*\.?[ \-/](\d{1,2})(?:st|nd|rd|th)?,?[ \-/](\d{2,4})", s)  # Jan 5, 2026
    if m and m[1].lower() in MONTHS:
        return ("mdy", MONTHS[m[1].lower()], int(m[2]), int(m[3]))
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?[ \-/]([A-Za-z]{3})[a-z]*\.?,?[ \-/](\d{2,4})", s)  # 5 Jan 2026
    if m and m[2].lower() in MONTHS:
        return ("dmy", int(m[1]), MONTHS[m[2].lower()], int(m[3]))
    return None


def date(v, order: str = "mdy") -> dt.date:
    """A date as a bank writes it; order: how day and month stand when the date does not say (mdy, dmy)."""
    p = _parts(str(v or ""))
    if not p:
        raise ValueError(f"not a date: {v}")
    known, a, b, c = p
    o = known or order
    y, m, d = (a, b, c) if o == "ymd" else (c, a, b) if o == "mdy" else (c, b, a)
    if y < 100:
        y += 2000 if y < 70 else 1900
    try:
        return dt.date(y, m, d)
    except ValueError:
        raise ValueError(f"not a date: {v}") from None


def order_of(values: list) -> tuple[str, bool]:
    """How day and month stand in these dates (mdy, dmy or ymd), and whether that was a guess (every one of them
    reads both ways)."""
    first_big = second_big = False
    for v in values:
        p = _parts(str(v or ""))
        if not p:
            continue
        if p[0]:
            if p[0] == "ymd":
                return "ymd", False
            continue
        first_big = first_big or p[1] > 12
        second_big = second_big or p[2] > 12
    if first_big and not second_big:
        return "dmy", False
    if second_big and not first_big:
        return "mdy", False
    dotted = sum(1 for v in values if "." in str(v or "")) > len(values) / 2
    return ("dmy" if dotted else "mdy"), True


# ------------------------------------------------------------------ OFX / QFX

def _is_ofx(text: str) -> bool:
    head = text[:2000].upper()
    return "<OFX" in head or "OFXHEADER" in head


def _ofx_field(block: str, tag: str) -> str | None:
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, re.I)
    return html.unescape(m[1]).strip() or None if m else None


def _ofx(text: str) -> dict:
    rows, problems = [], []
    for n, block in enumerate(re.findall(r"<STMTTRN>(.*?)(?=<STMTTRN>|</STMTTRN>|</BANKTRANLIST>|$)", text, re.I | re.S), 1):
        try:
            when = _ofx_field(block, "DTPOSTED") or _ofx_field(block, "DTUSER") or ""
            day = date(when[:8], "ymd")
            amt = amount(_ofx_field(block, "TRNAMT"))
            if amt is None:
                raise ValueError("no amount")
        except ValueError as e:
            problems.append({"line": n, "why": str(e)})
            continue
        name, memo = _ofx_field(block, "NAME"), _ofx_field(block, "MEMO")
        rows.append({"line": n, "day": day, "amount": amt, "payee": name or memo, "notes": memo if name and memo and memo != name else None,
                     "category": None, "fitid": _ofx_field(block, "FITID")})
    bal = None
    m = re.search(r"<LEDGERBAL>(.*?)(?=</LEDGERBAL>|<AVAILBAL>|</STMTRS>|</CCSTMTRS>|$)", text, re.I | re.S)
    if m:
        try:
            bal = amount(_ofx_field(m[1], "BALAMT"))
        except ValueError:
            bal = None
    return {"kind": "ofx", "rows": rows, "problems": problems, "balance": bal, "columns": [], "mapping": {}, "dateOrder": "ymd",
            "guessed": False, "sample": []}


# ------------------------------------------------------------------ CSV

def _table(text: str) -> list[list[str]]:
    text = text.lstrip("﻿")
    head = "\n".join(text.splitlines()[:30])
    delim = max(",;\t|", key=lambda d: head.count(d))
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), delimiter=delim)]
    return [r for r in rows if any(r)]


def _looks(cells: list[str], what) -> float:
    """The share of the cells (that hold something) which what() takes."""
    got = [c for c in cells if c]
    if not got:
        return 0.0
    ok = 0
    for c in got:
        try:
            ok += 1 if what(c) is not None else 0
        except ValueError:
            pass
    return ok / len(got)


def _guess(table: list[list[str]]) -> tuple[int, list[str], dict]:
    """(the row the data starts at, the columns' names, the mapping guessed)."""
    width = max(len(r) for r in table)
    head = None
    for n, r in enumerate(table[:25]):  # the headings: the first row that names a date and something else we know
        low = [c.lower().strip() for c in r]
        if any(c in HEADINGS["date"] for c in low) and sum(1 for c in low if any(c in h for h in HEADINGS.values())) >= 2:
            head = n
            break
    mapping: dict = {}
    if head is not None:
        cols = [c or f"Column {i + 1}" for i, c in enumerate(table[head] + [""] * (width - len(table[head])))]
        low = [c.lower().strip() for c in cols]
        for f in FIELDS:
            for h in HEADINGS[f]:
                if h in low and low.index(h) not in mapping.values():
                    mapping[f] = low.index(h)
                    break
        start = head + 1
    else:  # no headings we know: by what the columns hold (the first row may still be headings in other words)
        body = table[1:201] if len(table) > 1 else table
        col = lambda i: [r[i] if i < len(r) else "" for r in body]  # noqa: E731
        dates = [i for i in range(width) if _looks(col(i), lambda c: _parts(c)) > 0.9]
        if dates:
            mapping["date"] = dates[0]
        nums = [i for i in range(width) if i not in dates and _looks(col(i), amount) > 0.9 and any(c for c in col(i))]
        if nums:
            mapping["amount"] = nums[0]
        texts = [i for i in range(width) if i not in dates and i not in nums]
        if texts:
            mapping["payee"] = max(texts, key=lambda i: sum(len(c) for c in col(i)))
        first = table[0] + [""] * (width - len(table[0]))
        named = bool(dates) and len(table) > 1 and not _parts(first[dates[0]])
        cols = [c or f"Column {i + 1}" for i, c in enumerate(first)] if named else [f"Column {i + 1}" for i in range(width)]
        start = 1 if named else 0
    if "amount" in mapping and ("debit" in mapping and "credit" in mapping):
        mapping.pop("amount")  # a money-out and a money-in column say more than one amount
    return start, cols, mapping


def _mapping(v, width: int) -> dict:
    if not isinstance(v, dict):
        raise Invalid("mapping: which column is what ({date, amount, debit, credit, type, payee, notes, category})")
    out = {}
    for f in FIELDS:
        if v.get(f) in (None, ""):
            continue
        try:
            i = int(v[f])
        except (TypeError, ValueError):
            raise Invalid(f"mapping.{f}: a column's number") from None
        if not 0 <= i < width:
            raise Invalid(f"mapping.{f}: the file has {width} columns")
        out[f] = i
    return out


def _csv(text: str, mapping=None, order: str = None, flip: bool = False) -> dict:
    table = _table(text)
    if not table:
        raise Invalid("The file is empty")
    start, cols, guessed = _guess(table)
    m = _mapping(mapping, len(cols)) if mapping else guessed
    body = table[start:]
    cell = lambda r, f: (r[m[f]] if f in m and m[f] < len(r) else "")  # noqa: E731
    out = {"kind": "csv", "rows": [], "problems": [], "balance": None, "columns": cols, "mapping": m,
           "sample": [r + [""] * (len(cols) - len(r)) for r in body[:5]]}
    if "date" not in m or not ("amount" in m or "debit" in m or "credit" in m):
        out.update(dateOrder=order or "mdy", guessed=True, needs="Say which column holds the date and which the amount")
        return out
    found, unsure = order_of([cell(r, "date") for r in body[:500]])
    out.update(dateOrder=order if order in ORDERS else found, guessed=unsure and order not in ORDERS)
    for n, r in enumerate(body, start + 1):
        if len(out["rows"]) >= MAX_ROWS:
            raise Invalid(f"At most {MAX_ROWS} transactions in one file")
        try:
            day = date(cell(r, "date"), out["dateOrder"])
            if "amount" in m and cell(r, "amount"):
                amt = amount(cell(r, "amount"))
                kind = cell(r, "type").lower()
                if kind:  # a column that says which way the money went: the amount's own sign does not count
                    if re.match(r"(d|dr|debit|withdraw\w*|af|out)\b", kind):
                        amt = -abs(amt)
                    elif re.match(r"(c|cr|credit|deposit\w*|bij|in)\b", kind):
                        amt = abs(amt)
            else:
                out_, in_ = amount(cell(r, "debit")), amount(cell(r, "credit"))
                if out_ is None and in_ is None:
                    raise ValueError("no amount")
                amt = abs(in_ or Decimal(0)) - abs(out_ or Decimal(0))
            if flip:
                amt = -amt
        except ValueError as e:
            if any(r):
                out["problems"].append({"line": n + 1, "why": str(e)})
            continue
        out["rows"].append({"line": n + 1, "day": day, "amount": amt, "payee": cell(r, "payee") or None, "notes": cell(r, "notes") or None,
                            "category": cell(r, "category") or None, "fitid": None})
    return out


# ------------------------------------------------------------------ what is new

def _ext(aid: int, fitid: str | None) -> str | None:
    if not fitid:
        return None
    return f"imp:{aid}:{fitid}" if len(fitid) <= 40 else f"imp:{aid}:{hashlib.sha1(fitid.encode()).hexdigest()}"


def _split(a: dict, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """(the rows that are new, the ones the account has already)."""
    if not rows:
        return [], []
    lo, hi = min(r["day"] for r in rows), max(r["day"] for r in rows)
    have = db.q("SELECT day, amount, external_id FROM mny_transactions WHERE account_id = %s AND day BETWEEN %s AND %s", (a["id"], lo, hi))
    ids = {r["external_id"] for r in have if r["external_id"]}
    ids |= {r["external_id"] for r in db.q("SELECT external_id FROM mny_transactions WHERE account_id = %s AND external_id LIKE %s",
                                           (a["id"], f"imp:{a['id']}:%"))}
    left = Counter((r["day"], Decimal(r["amount"])) for r in have)
    new, dup = [], []
    for r in rows:
        k = (r["day"], r["amount"])
        if _ext(a["id"], r["fitid"]) in ids:
            dup.append(r)
            if left[k] > 0:
                left[k] -= 1
        elif left[k] > 0:
            left[k] -= 1
            dup.append(r)
        else:
            new.append(r)
    return new, dup


def _row(r: dict, new: bool) -> dict:
    return {"line": r["line"], "day": r["day"].isoformat(), "amount": model.n2(r["amount"]), "payee": r["payee"], "notes": r["notes"],
            "category": r["category"], "new": new}


def run(u: dict, a: dict, b: dict) -> dict:
    """{name?, text: the file, mapping? (CSV: {date, amount | debit and credit, type, payee, notes, category}: each a
    column's number from 0), dateOrder? (mdy, dmy, ymd), flip? (money out is written as a positive number),
    duplicates? (true: add what the account has already too), balance?: move (the account's balance moves by what
    is added; as left out), keep, or file (the balance an OFX file gives), preview? (true: add nothing)}.
    {kind, columns, mapping, dateOrder, guessed, sample, total, new, duplicates, problems, from, to, rows: the first
    few, fileBalance, added?: how many came in}."""
    model._need(model.can_write(u, a))
    if a["source"] != "manual":
        raise Invalid("Monarch Money keeps this account: a file goes into an account kept by hand")
    if a.get("track") != "transactions":
        raise Invalid("This account follows its value alone: change it to follow its transactions first")
    text = b.get("text")
    if not isinstance(text, str) or not text.strip():
        raise Invalid("The file is empty")
    if "\x00" in text[:2000]:
        raise Invalid("This is not a text file: export CSV, OFX or QFX from the bank")
    got = _ofx(text) if _is_ofx(text) else _csv(text, b.get("mapping"), b.get("dateOrder"), bool(model.flag(b.get("flip"))))
    if got["kind"] == "ofx" and model.flag(b.get("flip")):
        for r in got["rows"]:
            r["amount"] = -r["amount"]
    rows = got["rows"]
    if len(rows) > MAX_ROWS:
        raise Invalid(f"At most {MAX_ROWS} transactions in one file")
    new, dup = _split(a, rows)
    add = rows if model.flag(b.get("duplicates")) else new
    fresh = {id(r) for r in new}
    out = {"kind": got["kind"], "columns": got["columns"], "mapping": got["mapping"], "dateOrder": got["dateOrder"],
           "guessed": got["guessed"], "sample": got["sample"], "needs": got.get("needs"), "total": len(rows), "new": len(new),
           "duplicates": len(dup), "problems": got["problems"][:20], "problemCount": len(got["problems"]),
           "from": min((r["day"] for r in rows), default=None), "to": max((r["day"] for r in rows), default=None),
           "sum": model.n2(sum((r["amount"] for r in add), Decimal(0))), "fileBalance": model.n2(got["balance"]),
           "rows": [_row(r, id(r) in fresh) for r in rows[:SAMPLE]]}
    out["from"], out["to"] = (out["from"].isoformat() if out["from"] else None), (out["to"].isoformat() if out["to"] else None)
    if model.flag(b.get("preview")) or got.get("needs"):
        return out
    how = b.get("balance") or "move"
    if how not in ("move", "keep", "file"):
        raise Invalid("balance: move, keep or file")
    if how == "file" and got["balance"] is None:
        raise Invalid("This file does not give the account's balance")
    out["added"] = _add(u, a, add)
    if how == "move" and add:
        model._move_balance(a["id"], sum((r["amount"] for r in add), Decimal(0)))
    elif how == "file":
        bal = got["balance"]
        model.set_balance(a["id"], dt.date.today(), bal if a["is_asset"] else abs(bal), "manual")
    return out


def _add(u: dict, a: dict, rows: list[dict]) -> int:
    from app import transfers
    if not rows:
        return 0
    rules = db.q("SELECT * FROM mny_rules WHERE enabled = 1 ORDER BY position, id")
    groups: dict = {}

    def group(cat):
        if cat not in groups:
            groups[cat] = model._group_of_category(cat)
        return groups[cat]
    ids, used = [], set()
    with db.tx():
        for r in rows:
            payee = re.sub(r"\s+", " ", r["payee"] or "").strip()[:255] or None
            ch = model._rule_changes(rules, {"account_id": a["id"], "amount": r["amount"], "merchant": payee, "description": payee})
            cat = (r["category"] or "")[:128] or ch.get("category")
            merchant = ch.get("merchant", payee)
            ext = _ext(a["id"], r["fitid"])
            if ext in used or (ext and db.one("SELECT 1 AS x FROM mny_transactions WHERE source = 'manual' AND external_id = %s", (ext,))):
                ext = None  # asked to add what is there already: the id stays with the first
            used.add(ext)
            notes = (r["notes"] or "")[:4000] or None
            grp = group(cat) if cat else None
            ids.append(db.ex("INSERT INTO mny_transactions (account_id, source, external_id, day, amount, merchant, description, category, "
                             "category_group, notes, hidden, words, created_by) VALUES (%s, 'manual', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                             (a["id"], ext, r["day"], r["amount"], merchant, payee, cat, grp, notes, ch.get("hidden", 0),
                              model.words(merchant, payee, cat, grp, notes, a["name"]), u["id"])))
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        transfers.link(f"t.id IN ({db.marks(len(part))})", part)
    return len(ids)
