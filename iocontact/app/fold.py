"""Accent- and case-insensitive text matching, so a search for "celia" finds "Célia" (and "orsted" finds "Ørsted").

fold() is for matching done in Python (LDAP filters, CardDAV text-match, ioPix people); searches in MariaDB compare
with db.search_collation(), an accent-insensitive collation, instead.
"""
import unicodedata

# Letters that Unicode does not decompose into a base letter plus a mark.
_EXTRA = str.maketrans({"ø": "o", "đ": "d", "ð": "d", "ł": "l", "ħ": "h", "ŧ": "t", "ı": "i", "ŀ": "l",
                        "æ": "ae", "œ": "oe", "þ": "th"})


def fold(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", (s or "").casefold())
    return "".join(ch for ch in s if not unicodedata.combining(ch)).translate(_EXTRA)
