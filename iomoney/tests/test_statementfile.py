"""The bank's own file held against an account: a statement's PDF read for its days, its balances and its lines, a
CSV or OFX file from the bank's website, and what the Reconcile page gets back (what to tick, what the account does
not have, what the bank does not show). Made-up banks and payees throughout."""
import datetime as dt
from decimal import Decimal

from app import statementfile, statementpdf
from conftest import sign_in
from test_api import add
from test_tidy import D, TODAY, get, tx

AT = dt.date(2026, 11, 18)
US = """
Northfield Bank                                         Statement period
Account number: 000123                                  October 1, 2026 through October 31, 2026

Account summary
Beginning balance on October 1                             $2,150.00
Deposits and other credits                                 +3,200.00
Withdrawals and other debits                               -1,284.35
Ending balance on October 31                               $4,065.65

Deposits and other credits
Date     Description                                           Amount
10/02    PAYROLL ACME WIDGETS                                3,000.00
10/20    MOBILE DEPOSIT                                        200.00

Withdrawals and other debits
Date     Description                                           Amount
10/03    CHECKCARD 1002 GREEN GROCER #12                        84.35
10/05    RENT PAYMENT OAK ST                                 1,100.00
10/15    CITY WATER AUTOPAY                                     60.00

Checks paid
Number    Date      Amount         Number    Date      Amount
1041      10/09      25.00         1042*     10/28      15.00

Daily ledger balances
Date      Balance       Date      Balance
10/02    5,150.00      10/15    3,880.65
10/03    5,065.65      10/20    4,080.65
"""
CARD = """
Harbor Card                 Opening/Closing Date 09/12/26 - 10/11/26
Previous Balance                 $412.20
Payments, Credits               -$412.20
Purchases                       +$236.49
New Balance                      $236.49
ACCOUNT ACTIVITY
Date of
Transaction   Merchant Name or Transaction Description          $ Amount
09/20         Payment Thank You - Web                            -412.20
09/14  09/15       BOOK BARN 555-0100 OR                             31.49
09/30  10/01       GAS N GO #44                                      55.00
10/03  10/04       PIZZA PLACE                                      150.00
"""
EU = """
Kontoauszug                      01.10.2026 bis 31.10.2026
Alter Saldo                                          1.250,00
Datum     Buchungstext                    Soll        Haben        Saldo
02.10.    Gehalt Beispiel GmbH                        2.500,00     3.750,00
05.10.    Miete Oktober                   900,00                   2.850,00
17.10.    Supermarkt Nord                  64,30                   2.785,70
Neuer Saldo                                          2.785,70
"""


def pdf(lines):
    """A PDF of these lines in a fixed-width face (what a bank's statement is, without the bank)."""
    esc = lambda s: s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")  # noqa: E731
    body = ("BT /F1 9 Tf 11 TL 36 760 Td " + " ".join(f"({esc(ln)}) Tj T*" for ln in lines) + " ET").encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(body), body), b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    out, at = b"%PDF-1.4\n", []
    for n, o in enumerate(objs, 1):
        at.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (n, o)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(b"%010d 00000 n \n" % o for o in at)
    return out + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)


def lines_of(r):
    return [(ln["day"].isoformat()[5:], str(ln["amount"]), ln["text"]) for ln in r["lines"]]


def send(client, a, data, **q):
    return client.post(f"/api/accounts/{a['id']}/statement/read", params=q, content=data, headers={"Content-Type": "application/octet-stream"})


def test_a_statements_text_is_read():
    # a bank's: the period in words, the balances from the summary, the lines under headings that say which way; the
    # checks across the line; the balance of each day is no transaction
    r = statementpdf.parse(US.splitlines(), today=AT)
    assert (r["start"], r["end"], r["opening"], r["closing"]) == (dt.date(2026, 10, 1), dt.date(2026, 10, 31), Decimal("2150.00"), Decimal("4065.65"))
    assert lines_of(r) == [("10-02", "3000.00", "PAYROLL ACME WIDGETS"), ("10-20", "200.00", "MOBILE DEPOSIT"),
                           ("10-03", "-84.35", "CHECKCARD 1002 GREEN GROCER #12"), ("10-05", "-1100.00", "RENT PAYMENT OAK ST"),
                           ("10-15", "-60.00", "CITY WATER AUTOPAY"), ("10-09", "-25.00", "Check 1041"), ("10-28", "-15.00", "Check 1042")]
    assert all(ln["signed"] for ln in r["lines"]) and r["dateOrder"] == "mdy" and not r["guessed"]
    assert sum(ln["amount"] for ln in r["lines"]) == r["closing"] - r["opening"]
    # a card's: two dates on a line (the second is left out), a minus is money paid in, what is owed is the balance
    r = statementpdf.parse(CARD.splitlines(), owed=True, today=AT)
    assert (r["start"], r["end"], r["opening"], r["closing"]) == (dt.date(2026, 9, 12), dt.date(2026, 10, 11), Decimal("412.20"), Decimal("236.49"))
    assert lines_of(r) == [("09-20", "412.20", "Payment Thank You - Web"), ("09-14", "-31.49", "BOOK BARN 555-0100 OR"),
                           ("09-30", "-55.00", "GAS N GO #44"), ("10-03", "-150.00", "PIZZA PLACE")]
    # day first, a comma for the cents, money out and money in in columns of their own, the balance after each line
    r = statementpdf.parse(EU.splitlines(), today=AT)
    assert (r["start"], r["end"], r["opening"], r["closing"], r["dateOrder"]) == (dt.date(2026, 10, 1), dt.date(2026, 10, 31), Decimal("1250.00"), Decimal("2785.70"), "dmy")
    assert lines_of(r) == [("10-02", "2500.00", "Gehalt Beispiel GmbH"), ("10-05", "-900.00", "Miete Oktober"), ("10-17", "-64.30", "Supermarkt Nord")]
    assert r["lines"][0]["others"] == [Decimal("3750.00")]
    # no period given and nothing that says which way: the days of the lines, the amounts as written
    r = statementpdf.parse(["Jan 5, 2026   CORNER CAFE          12.50", "Jan 9, 2026   BIKE SHOP           140.00    1,010.00"], today=AT)
    assert (r["start"], r["end"]) == (dt.date(2026, 1, 5), dt.date(2026, 1, 9)) and r["opening"] is None
    assert [(str(ln["amount"]), ln["signed"], ln["others"]) for ln in r["lines"]] == [("12.50", False, []), ("140.00", False, [Decimal("1010.00")])]
    # nothing but the balance after each line: which way it moved says which way the money went
    r = statementpdf.parse(["Opening balance 1,000.00", "03/02/2026 CORNER CAFE 50.00 950.00", "03/09/2026 ACME WIDGETS 400.00 1,350.00"], today=AT)
    assert [(str(ln["amount"]), ln["signed"]) for ln in r["lines"]] == [("-50.00", True), ("400.00", True)]
    # a date without its year at the turn of the year takes the year of the statement's days
    r = statementpdf.parse(["Statement period 12/15/2025 - 01/14/2026", "12/30  SKI PASS  80.00", "01/02  GYM  30.00"], today=AT)
    assert [ln["day"].isoformat() for ln in r["lines"]] == ["2025-12-30", "2026-01-02"]
    # amounts as banks write them
    found = [m[1] for m in statementpdf.MONEY.finditer("05.10.2026 x 1,234.56 y (12.00) z 1.234,56 w -$5.00 v 7.25CR u 3.50- t 12/25 s 1 250,00")]
    assert found == ["1,234.56", "(12.00)", "1.234,56", "-$5.00", "7.25CR", "3.50-", "1 250,00"]


def statement(a_start, a_end, opening, closing, rows):
    us = lambda d: dt.date.fromisoformat(d).strftime("%m/%d")  # noqa: E731
    long = lambda d: dt.date.fromisoformat(d).strftime("%B %-d, %Y")  # noqa: E731
    return ["Northfield Bank", f"Statement period   {long(a_start)} through {long(a_end)}",
            f"Beginning balance      ${opening:,.2f}", f"Ending balance         ${closing:,.2f}", "",
            "Date     Description                           Amount", *[f"{us(d)}    {text:<34}{amount:>10,.2f}" for d, text, amount in rows]]


def test_a_statement_pdf_against_the_account(client, as_user):
    a = add(client, balance=1000)
    rent = tx(client, a, -700, "Oak Street Rentals", 30)
    pay = tx(client, a, 1500, "Acme Widgets", 28)
    cafe1 = tx(client, a, -4.5, "Corner Cafe", 25)
    cafe2 = tx(client, a, -4.5, "Corner Cafe", 21)
    grocer = tx(client, a, -45, "Green Grocer", 20)       # the bank says 54.00
    late = tx(client, a, -60, "City Water", 8)            # here two days after the statement's last day
    only = tx(client, a, -12, "Only here", 18)
    rows = [(D(30), "RENT OAK STREET", 700), (D(27), "PAYROLL ACME WIDGETS", 1500), (D(25), "CORNER CAFE 0012", 4.5), (D(22), "CORNER CAFE 0012", 4.5),
            (D(20), "GREEN GROCER #12", 54), (D(15), "BANK FEE", 3), (D(10), "CITY WATER AUTOPAY", 60)]
    data = pdf(statement(D(31), D(10), 500.00, 1174.00, rows))  # 500 - 700 + 1500 - 4.5 - 4.5 - 54 - 3 - 60
    r = send(client, a, data, name="october.pdf")
    assert r.status_code == 200, r.text
    r = r.json()
    assert (r["kind"], r["name"], r["start"], r["end"], r["opening"], r["closing"], r["total"]) == ("pdf", "october.pdf", D(31), D(10), 500, 1174, 7)
    assert r["matched"] == [rent["id"], pay["id"], cafe1["id"], cafe2["id"]]  # the payroll a day off, each coffee its own
    assert [(x["day"], x["text"], x["amount"], x["signed"]) for x in r["missing"]] == [(D(20), "GREEN GROCER #12", 54, False), (D(15), "BANK FEE", 3, False)]
    assert r["missing"][0]["differs"] == {"id": grocer["id"], "day": D(20), "amount": -45, "name": "Green Grocer"} and "differs" not in r["missing"][1]
    assert [(x["text"], x["id"], x["at"], x["why"]) for x in r["elsewhere"]] == [("CITY WATER AUTOPAY", late["id"], D(8), "after")]
    assert r["extra"] == [grocer["id"], only["id"]] and r["missingCount"] == 2 and r["sum"] is None and r["adds"] is None
    # nothing was changed, and the file is not kept
    assert not get(client, rent["id"])["reconciled"] and client.get(f"/api/accounts/{a['id']}/statements").json()["items"] == []
    # the fee added, the grocer's amount put right: what the page ticks now adds up but for the one after the last day
    fee = tx(client, a, -3, "Bank fee", 15)
    assert client.patch(f"/api/transactions/{grocer['id']}", json={"amount": -54}).status_code == 200
    r = send(client, a, data).json()
    assert r["matched"] == [rent["id"], pay["id"], cafe1["id"], cafe2["id"], grocer["id"], fee["id"]] and r["missing"] == [] and r["extra"] == [only["id"]]
    body = {"start": r["start"], "end": r["end"], "opening": r["opening"], "closing": r["closing"], "ids": r["matched"]}
    assert client.post(f"/api/accounts/{a['id']}/statements", json=body).status_code == 400  # 60 short: the water bill
    assert client.post(f"/api/accounts/{a['id']}/statements", json={**body, "anyway": True}).json()["difference"] == -60
    # a viewer may hold a file against what they can see; someone else's private account is not there
    mine = add(client, name="Mine", household=False)
    as_user("viv", "viewer")
    assert send(client, a, data).status_code == 200 and send(client, mine, data).status_code == 404
    sign_in(client, "alex")
    # what cannot be read says why
    assert "could not be read as a PDF" in send(client, a, b"%PDF-1.4 not really").json()["detail"]
    assert "a scan" in send(client, a, pdf([])).json()["detail"]
    assert "No statement could be read" in send(client, a, pdf(["Dear customer,", "thank you for banking with us."])).json()["detail"]
    assert send(client, a, b"").status_code == 400 and "neither a PDF nor a text file" in send(client, a, b"PK\x03\x04\x00\x00\x00zip").json()["detail"]


def test_the_banks_csv_against_the_account(client):
    a = add(client, balance=1000)
    rent = tx(client, a, -700, "Oak Street Rentals", 30)
    pay = tx(client, a, 1500, "Acme Widgets", 28)
    back = tx(client, a, 20, "Shoe Shed", 26)             # a refund: the same amount as the purchase beside it
    shoes = tx(client, a, -20, "Shoe Shed", 26)
    only = tx(client, a, -12, "Only here", 18)
    us = lambda n: (TODAY - dt.timedelta(days=n)).strftime("%m/%d/%Y")  # noqa: E731
    # the newest first, with the balance after each line
    rows = [(us(12), "BANK FEE", "-3.00", "1,292.00"), (us(26), "SHOE SHED RETURN", "20.00", "1,295.00"), (us(26), "SHOE SHED", "-20.00", "1,275.00"),
            (us(27), "PAYROLL ACME WIDGETS", "1,500.00", "1,295.00"), (us(30), "RENT OAK STREET", "-700.00", "-205.00")]
    csv = "Date,Description,Amount,Running Bal.\n" + "\n".join(f'{d},{text},"{amount}","{balance}"' for d, text, amount, balance in rows)
    r = send(client, a, csv.encode(), name="export.csv").json()
    assert (r["kind"], r["start"], r["end"], r["opening"], r["closing"], r["total"], r["sum"]) == ("csv", D(30), D(12), 495, 1292, 5, 797)
    assert r["matched"] == [rent["id"], pay["id"], back["id"], shoes["id"]] and not r["worked"] and not r["flipped"]
    assert [(x["day"], x["text"], x["amount"], x["signed"]) for x in r["missing"]] == [(D(12), "BANK FEE", -3, True)] and r["extra"] == [only["id"]]
    # a file without a balance: the one at the end is the one kept for the day before plus the file's lines
    plain = "Date,Description,Amount\n" + "\n".join(f'{d},{text},"{amount}"' for d, text, amount, _ in rows)
    r = send(client, a, plain.encode()).json()
    assert r["matched"] == [rent["id"], pay["id"], back["id"], shoes["id"]] and r["sum"] == 797
    assert (r["opening"], r["closing"], r["worked"]) == (1000, 1797, True)  # 1788 today, less the 788 its transactions moved it by
    # a card whose file writes a purchase as a positive number: turned around, since that is how it fits
    card = add(client, name="Card", kind="credit", balance=80)
    buy = tx(client, card, -80, "Shoe Shed", 5)
    paid = tx(client, card, 50, "Payment", 3)
    ccsv = f"Transaction Date,Description,Amount\n{us(5)},SHOE SHED,80.00\n{us(3)},PAYMENT THANK YOU,-50.00\n{us(2)},PARKING,6.00\n"
    r = send(client, card, ccsv.encode()).json()
    assert r["flipped"] and r["matched"] == [buy["id"], paid["id"]] and [(x["text"], x["amount"]) for x in r["missing"]] == [("PARKING", -6)]
    assert send(client, card, ccsv.encode(), flip="0").json()["matched"] == []
    assert client.get(f"/api/accounts/{card['id']}").json()["balance"] == 110  # owed: 80, the shoes on top, the payment off
    assert (r["opening"], r["closing"], r["worked"]) == (80, 116, True)        # and the parking the file has
    # an OFX file: its days and the balance at its end; the one at the start follows from its lines
    ymd = lambda n: (TODAY - dt.timedelta(days=n)).strftime("%Y%m%d")  # noqa: E731
    ofx = (f"OFXHEADER:100\n<OFX><BANKTRANLIST><DTSTART>{ymd(31)}<DTEND>{ymd(11)}"
           f"<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>{ymd(30)}<TRNAMT>-700.00<FITID>1<NAME>RENT OAK STREET</STMTTRN>"
           f"<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>{ymd(28)}<TRNAMT>1500.00<FITID>2<NAME>PAYROLL</STMTTRN></BANKTRANLIST>"
           f"<LEDGERBAL><BALAMT>1300.00<DTASOF>{ymd(11)}</LEDGERBAL></OFX>")
    r = send(client, a, ofx.encode()).json()
    assert (r["kind"], r["start"], r["end"], r["opening"], r["closing"]) == ("ofx", D(31), D(11), 500, 1300) and r["matched"] == [rent["id"], pay["id"]]
    assert r["extra"] == [back["id"], shoes["id"], only["id"]]
    # day and month that read both ways: guessed, and said otherwise
    amb = "Date,Description,Amount\n03/04/2026,X,-1.00\n05/06/2026,Y,-2.00\n"
    r = send(client, a, amb.encode()).json()
    assert r["guessed"] and (r["dateOrder"], r["start"], r["end"]) == ("mdy", "2026-03-04", "2026-05-06")
    assert send(client, a, amb.encode(), order="dmy").json()["start"] == "2026-04-03"
    assert "No transactions" in send(client, a, b"Date,Description,Amount\n").json()["detail"]


def test_a_line_is_one_transaction():
    c = lambda i, day, amount, inside=True: {"id": i, "day": dt.date(2026, 10, day), "amount": Decimal(amount), "in": inside,  # noqa: E731
                                             "name": "", "words": set()}
    ln = lambda day, amount, signed=True, others=(): {"day": dt.date(2026, 10, day), "text": "", "amount": Decimal(amount), "signed": signed,  # noqa: E731
                                                      "others": [Decimal(o) for o in others]}
    ids = lambda got: {n: x["id"] for n, x in got.items()}  # noqa: E731
    # the nearest day wins, whatever the order of the lines; six days off is another transaction
    assert ids(statementfile._match([ln(10, -5), ln(12, -5), ln(25, -5)], [c(1, 12, -5), c(2, 9, -5), c(3, 19, -5)], True)) == {0: 2, 1: 1}
    # which way counts where the file says it; a PDF that does not is matched by the amount, then by the line's other amounts
    assert ids(statementfile._match([ln(10, 5)], [c(1, 10, -5)], True)) == {} and ids(statementfile._match([ln(10, 5)], [c(1, 10, -5)], True, flip=True)) == {0: 1}
    assert ids(statementfile._match([ln(10, 5, False)], [c(1, 10, -5)], False)) == {0: 1}
    assert ids(statementfile._match([ln(10, "1.08", False, ["45.00"])], [c(1, 11, -45)], False)) == {0: 1}
    # one the page lists before one it does not
    assert ids(statementfile._match([ln(10, -5)], [c(1, 10, -5, False), c(2, 10, -5), c(3, 10, -5)], True)) == {0: 2}
