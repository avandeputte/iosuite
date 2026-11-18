"""Reading a bank's statement from its PDF: the days it covers, the balance at its start and at its end, and its lines.

A statement's PDF holds text laid out in columns, in a form each bank makes up. Nothing here knows a bank: the
text is read line by line (pypdf, with the columns kept where they stand) and what a statement always has is looked
for. The days it covers: two dates joined by "to", "through" or a dash, on a line that speaks of the statement or its
period first. The two balances: the amount after "beginning balance", "previous balance", "new balance", "ending
balance" and their like. Its lines: every line that starts with a date and holds an amount; a second date beside the
first (the day it was posted) is left out of the text, and an amount at the end of a line with two of them is the
balance after it. Which way the money went is told by the heading a line stands under ("Deposits", "Withdrawals",
"Purchases"), by the column it stands in ("Paid out", "Paid in"), by a minus, or best by the balance after it, where
the statement has them; otherwise it is not known, and the lines are matched by their amount alone.

A scanned statement (pictures of its pages) has no text and cannot be read. The file is read here and never kept."""
import datetime as dt
import io
import re
from decimal import Decimal

from iosuite_shared.errors import Invalid

from app import importer

MAX_PAGES = 80
MAX_LINES = 5000

_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_NUM = r"\d{4}[/.\-]\d{1,2}[/.\-]\d{1,2}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"
_NAMED = rf"{_MON} ?\d{{1,2}}(?:st|nd|rd|th)?,? ?\d{{4}}|\d{{1,2}}(?:st|nd|rd|th)?\.? ?{_MON},? ?\d{{4}}"
FULL = rf"(?:{_NUM}|{_NAMED})"                                                       # a date with its year
SHORT = rf"(?:\d{{1,2}}[/.\-]\d{{1,2}}\.?|{_MON} ?\d{{1,2}}|\d{{1,2}}\.? ?{_MON})"      # one without
_DATE = re.compile(rf"(?<![\w/.\-])(?:(?P<full>{FULL})|(?P<short>{SHORT}))(?![\w/\-]|\.\d)", re.I)
_JOIN = r"\s*(?:-|–|—|to|through|thru|until|till|bis|au|tot|t/m|al)\s*"
_RANGE = re.compile(rf"(?<![\w/.\-])(?P<a>{FULL}|{SHORT}){_JOIN}(?P<b>{FULL})(?![\w/\-])", re.I)
_PERIOD = re.compile(r"statement|period|billing|cycle|opening|closing|from|activity|zeitraum|periode|p[ée]riode|per[ií]odo", re.I)
# an amount: 1,234.56, 1.234,56, 1 234,56, with its sign before or after, in brackets, with a currency sign, CR or DR
MONEY = re.compile(r"(?<![\w.,/])(\(?[-+]?(?:[$€£] ?)?[-+]?(?:\d{1,3}(?:,\d{3})+\.\d{2}|\d{1,3}(?:[.' ]\d{3})+,\d{2}|\d{1,3}(?:'\d{3})+\.\d{2}|\d+[.,]\d{2})"
                   r"\)?(?:-(?![\d.])| ?(?:CR|DR)\b)?)(?![\d/]|[.,]\d)", re.I)

_OPENING = re.compile(r"(?:beginning|opening|previous|starting|prior|last)\s+(?:statement\s+|account\s+)?balance|balance\s+(?:brought\s+)?forward"
                      r"|balance\s+(?:at|on)\s+(?:the\s+)?(?:start|beginning)|balance\s+last\s+statement|alter\s+(?:konto)?saldo|ancien\s+solde"
                      r"|vorig\s+saldo|saldo\s+anterior|saldo\s+inicial", re.I)
_CLOSING = re.compile(r"(?:ending|closing|new|current\s+statement)\s+(?:statement\s+|account\s+)?balance|balance\s+carried\s+forward"
                      r"|balance\s+(?:at|on)\s+(?:the\s+)?(?:end|close)|balance\s+this\s+statement|statement\s+balance|neuer\s+(?:konto)?saldo"
                      r"|nouveau\s+solde|nieuw\s+saldo|saldo\s+final|saldo\s+actual", re.I)
_BALANCES = re.compile(r"daily\s+(?:ledger\s+|ending\s+)?balances?|balance\s+summary|daily\s+balance\s+(?:summary|information)", re.I)
# the headings lines stand under, and the columns they stand in: money that came in, money that went out
_IN = re.compile(r"deposits?|credits?|additions?|payments?\s+(?:and|&)\s+(?:other\s+)?credits?|paid\s+in|money\s+in|interest\s+(?:paid|earned)|gutschrift|haben|bij\b", re.I)
_OUT = re.compile(r"withdrawals?|debits?|purchases?|che(?:ck|que)s?(?:\s+paid)?|fees?|charges?|subtractions?|paid\s+out|money\s+out"
                  r"|interest\s+charged|cash\s+advances?|lastschrift|soll\b|af\b", re.I)
_PLAIN = re.compile(r"transactions?|activity|history|details", re.I)  # a heading that does not say which way
_COLUMNS = re.compile(r"date|description|details|particulars|balance|datum|omschrijving", re.I)
_CHECK = re.compile(rf"(\d{{3,9}})\*? +({FULL}|{SHORT}) +(\S+)", re.I)


# ------------------------------------------------------------------ the text of the file

def text_of(data: bytes) -> list[list[str]]:
    """The PDF's lines, read once with its columns kept where they stand and once plainly (some files read better
    one way than the other)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise Invalid("Reading a PDF needs the pypdf package: update ioMoney from Settings, or pip install pypdf") from None
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise Invalid("This PDF is locked with a password: save a copy without one first")
        pages = list(reader.pages)
    except Invalid:
        raise
    except Exception as e:  # noqa: BLE001 - a file pypdf cannot open is not a PDF, or a broken or locked one
        locked = "crypt" in str(e).lower() or "password" in str(e).lower()
        raise Invalid("This PDF is locked with a password: save a copy without one first" if locked
                      else "This file could not be read as a PDF") from None
    if len(pages) > MAX_PAGES:
        raise Invalid(f"A statement of at most {MAX_PAGES} pages")
    out = []
    for how in ({"extraction_mode": "layout"}, {}):
        lines: list[str] = []
        try:
            for p in pages:
                lines += (p.extract_text(**how) or "").splitlines()
        except Exception:  # noqa: BLE001 - one way of reading failed: the other may not
            lines = []
        out.append([ln.replace("\xa0", " ").replace("−", "-").rstrip() for ln in lines if ln.strip()][:MAX_LINES * 4])
    if not any(out):
        raise Invalid("This PDF holds no text: it is a scan (pictures of the pages), which cannot be read")
    return out


# ------------------------------------------------------------------ dates and amounts

def _clean(s: str) -> str:
    """A date as importer.date takes it: one space, no dot after the day."""
    s = re.sub(r"\s+", " ", s.strip())
    s = re.sub(rf"^({_MON})(\d)", r"\1 \2", s, flags=re.I)             # Oct5
    s = re.sub(rf"(\d)\.? ?({_MON})", r"\1 \2", s, flags=re.I)         # 5.Oct, 5Oct
    s = re.sub(r"(\d)(st|nd|rd|th)?,? ?(\d{4})$", r"\1 \3", s)          # Oct 5,2026
    return s.rstrip(".")


def _with_year(s: str, year: int) -> str:
    s = _clean(s)
    m = re.fullmatch(r"(\d{1,2})([/.\-])(\d{1,2})", s)
    return f"{s}{m[2]}{year}" if m else f"{s} {year}"


def _day(s: str, full: bool, order: str, around: tuple | None, today: dt.date) -> dt.date | None:
    """The date written as s; one without its year takes the year that puts it in (or nearest to) the days the
    statement covers, or, without those, the latest year that is not in the future."""
    try:
        if full:
            return importer.date(_clean(s), order)
        if around:
            lo, hi = around
            got = [importer.date(_with_year(s, y), order) for y in sorted({lo.year - 1, lo.year, hi.year})]
            return min(got, key=lambda d: 0 if lo <= d <= hi else min(abs((d - lo).days), abs((d - hi).days)))
        d = importer.date(_with_year(s, today.year), order)
        return d if d <= today + dt.timedelta(days=7) else importer.date(_with_year(s, today.year - 1), order)
    except ValueError:
        return None


def _money(tok: str, owed: bool = False) -> Decimal | None:
    """An amount as written. On a statement of what is owed, CR is money the bank owes (a negative balance)."""
    try:
        v = importer.amount(tok)
    except ValueError:
        return None
    if v is not None and owed and re.search(r"cr\.?$", tok.strip(), re.I):
        v = -abs(v)
    elif v is not None and owed and re.search(r"dr\.?$", tok.strip(), re.I):
        v = abs(v)
    return v


def _minus(tok: str) -> bool:
    t = tok.strip()
    return t.startswith("(") or "-" in t or bool(re.search(r"dr\.?$", t, re.I))


def _order(lines: list[str]) -> tuple[str, bool]:
    """How day and month stand: from the dates the lines start with and the ones written with their year."""
    found = []
    for ln in lines:
        first = _DATE.match(ln.strip())
        if first and not first["full"]:
            found.append(_with_year(first[0], 2000))
        found += [_clean(m[0]) for m in _DATE.finditer(ln) if m["full"]]
    return importer.order_of(found)


# ------------------------------------------------------------------ the statement

def _period(lines: list[str], order: str, today: dt.date) -> tuple | None:
    """(the first day, the last day): two dates joined, from a line that speaks of the statement's period before any other."""
    best = None
    for n, ln in enumerate(lines):
        for m in _RANGE.finditer(ln):
            b = _day(m["b"], True, order, None, today)
            if not b:
                continue
            a = _day(m["a"], bool(re.fullmatch(FULL, m["a"].strip(), re.I)), order, (b - dt.timedelta(days=370), b), today)
            if not a or a > b or (b - a).days > 400:
                continue
            rank = (0 if _PERIOD.search(ln[:m.start()]) or (n and _PERIOD.search(lines[n - 1]) and len(lines[n - 1]) < 80) else 1, n)
            if best is None or rank < best[0]:
                best = (rank, a, b)
        if best and best[0][0] == 0:
            break
    return (best[1], best[2]) if best else None


def _balance(lines: list[str], what, owed: bool, never=None) -> Decimal | None:
    """The first amount that follows these words: on their line, or alone on the next."""
    for n, ln in enumerate(lines):
        m = what.search(ln)
        if not m or (never and never.search(ln[:m.end()])):
            continue
        rest = _DATE.sub(lambda d: " " * len(d[0]) if d["full"] else d[0], ln[m.end():])
        got = MONEY.search(rest)
        if not got and n + 1 < len(lines) and MONEY.fullmatch(lines[n + 1].strip()):
            got = MONEY.search(lines[n + 1])
        v = _money(got[1], owed) if got else None
        if v is not None:
            return v
    return None


def _heading(ln: str) -> int | None:
    """Which way the money of the lines under this heading went (1 in, -1 out, 0 it does not say), or None: not a
    heading (a heading is a few words without a number)."""
    if re.search(r"\d", ln) or len(ln.split()) > 6:
        return None
    i, o = _IN.search(ln), _OUT.search(ln)
    if i and o:  # "Payments and other credits", "Checks and other debits": the first word says it; a table's headings say nothing
        return None if _COLUMNS.search(ln) else (1 if i.start() < o.start() else -1)
    return 1 if i else -1 if o else 0 if _PLAIN.search(ln) else None


def _columns(ln: str) -> tuple | None:
    """Where a table's column of money out and its column of money in end on the line, from its headings."""
    if MONEY.search(ln) or not _COLUMNS.search(ln):
        return None
    i, o = _IN.search(ln), _OUT.search(ln)
    return (o.end(), i.end()) if i and o else None


def parse(lines: list[str], owed: bool = False, today: dt.date = None, order: str = None) -> dict:
    """{start, end, opening, closing, lines: [{day, text, amount, signed, others}], dateOrder, guessed}. amount is as
    ioMoney counts it (money out negative) where the statement told which way it went (signed), otherwise as written
    without a sign; others: the further amounts of the line (the balance after it). owed: a statement of a card or
    a loan, where a minus is money paid in. order: how day and month stand (mdy, dmy, ymd), when the guess is wrong."""
    today = today or dt.date.today()
    lines = [ln.replace("\t", "    ").replace("\xa0", " ").replace("\u2212", "-").rstrip() for ln in lines if ln.strip()]
    order, guessed = (order, False) if order in importer.ORDERS else _order(lines)
    period = _period(lines, order, today)
    out = {"start": None, "end": None, "opening": _balance(lines, _OPENING, owed), "closing": _balance(lines, _CLOSING, owed, _OPENING),
           "lines": [], "dateOrder": order, "guessed": guessed}
    around = (period[0] - dt.timedelta(days=10), period[1] + dt.timedelta(days=10)) if period else None
    rows, way, cols, skip = [], None, None, False
    for ln in lines:
        body = ln.strip()
        first = _DATE.match(body)
        if not first:
            if _BALANCES.search(body):
                skip = True  # the balance of each day: dates and amounts that are no transactions
                continue
            c = _columns(ln)
            if c:
                cols, way, skip = c, None, False
                continue
            w = _heading(body)
            if w is not None:
                way, skip = w or None, False
            checks = [] if skip or not (way == -1 or re.search(r"che(?:ck|que)", body, re.I)) else _CHECK.findall(body)
            if checks and not re.sub(r"[\s*]", "", _CHECK.sub("", body)):  # check number, date, amount: one or several across the line
                for number, when, tok in checks:
                    rows.append((when, bool(re.fullmatch(FULL, when, re.I)), f"Check {number}", [tok], -1, None))
            continue
        if skip or (_OPENING.search(body) or _CLOSING.search(body)) and len(MONEY.findall(body)) == 1:
            continue
        indent = len(ln) - len(ln.lstrip())
        rest = body[first.end():]
        second = _DATE.match(rest.lstrip())
        if second:  # the day it was posted, beside the day it was made
            rest = rest.lstrip()[second.end():]
        toks = list(MONEY.finditer(rest))
        if not toks or _DATE.search(rest[toks[0].end():]):  # no amount, or dates after it: a row of daily balances
            continue
        text = re.sub(r"\s+", " ", MONEY.sub(" ", rest)).strip(" -|")
        at = None
        if cols:  # the column the amount ends in
            end = indent + len(body) - len(rest) + toks[0].end()
            near = min(cols, key=lambda c: abs(c - end))
            at = (-1 if near == cols[0] else 1) if abs(near - end) <= 14 and cols[0] != cols[1] else None
        rows.append((first[0], bool(first["full"]), text, [t[1] for t in toks], at if at is not None else way, toks[0][1]))
    if not period and rows:  # no days given: from the first line to the last
        days = [d for d in (_day(r[0], r[1], order, None, today) for r in rows) if d]
        period = (min(days), max(days)) if days else None
        around = (period[0] - dt.timedelta(days=10), period[1] + dt.timedelta(days=10)) if period else None
    marked = any(r[5] and _minus(r[5]) for r in rows)
    before = out["opening"]
    for when, full, text, toks, way_, tok in rows[:MAX_LINES]:
        day = _day(when, full, order, around, today)
        vals = [v for v in (_money(t) for t in toks) if v is not None]
        if not day or not vals or not vals[0] or (around and not around[0] <= day <= around[1]):
            continue
        sign = way_
        if len(vals) > 1:  # the balance after the line: which way it moved from the one before says it best
            after = _money(toks[-1], owed)
            if before is not None and abs(after - before) == abs(vals[0]):
                sign = (1 if after > before else -1) * (-1 if owed else 1)
            before = after
        else:
            before = None
        if sign is None and marked and tok:  # a statement that writes a minus: of an account, money out; of a card, money paid in
            sign = (-1 if _minus(tok) else 1) * (-1 if owed else 1)
        out["lines"].append({"day": day, "text": text[:255], "amount": abs(vals[0]) * sign if sign else abs(vals[0]), "signed": bool(sign),
                             "others": [abs(v) for v in vals[1:]]})
    if period:
        out["start"], out["end"] = period
    return out


def read(data: bytes, owed: bool = False, order: str = None) -> dict:
    """The statement in a PDF file: parse() of its text, read the way that gives the most (and pages: how many)."""
    best = None
    for lines in text_of(data):
        got = parse(lines, owed, order=order) if lines else None
        if got and (best is None or (len(got["lines"]), got["opening"] is not None, got["closing"] is not None)
                    > (len(best["lines"]), best["opening"] is not None, best["closing"] is not None)):
            best = got
    if not best or not (best["lines"] or best["closing"] is not None):
        raise Invalid("No statement could be read from this PDF: neither its lines nor its balances were found")
    return best
