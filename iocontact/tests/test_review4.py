"""Round four of the 14 November 2026 review: a long folded vCard line costs linear time, and somebody who may not
add contacts anywhere is refused before the body is read."""
import time

from app import vcard
from tests.test_review_fixes import member


def test_a_long_folded_line_is_read_in_linear_time():
    card = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ann\r\nNOTE:x" + "\r\n y" * 200_000 + "\r\nEND:VCARD\r\n"
    t = time.monotonic()
    c = vcard.parse(card)[0]
    assert time.monotonic() - t < 5 and c["notes"] == "x" + "y" * 200_000
    qp = "BEGIN:VCARD\r\nVERSION:2.1\r\nFN:Bob\r\nNOTE;ENCODING=QUOTED-PRINTABLE:caf=C3=\r\n=A9 au lait\r\nEND:VCARD\r\n"
    assert vcard.parse(qp)[0]["notes"] == "café au lait"
    plain = "BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Cy\r\nNOTE:ends with =\r\nTITLE:Boss\r\nEND:VCARD\r\n"  # not quoted-printable: no join
    assert vcard.parse(plain)[0]["title"] == "Boss"


def test_no_writable_book_is_refused_before_the_body(client, family_id):
    k, _uid, _own = member(client)
    assert k.post(f"/api/contacts?book={family_id}", json={"fn": "X"}).status_code == 403
