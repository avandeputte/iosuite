"""The family calendar: birthdays and anniversaries as an iCalendar feed (RFC 5545) that Apple Calendar, Google Calendar,
Outlook and Thunderbird subscribe to. Every event recurs yearly, so the feed stays valid for years."""
import datetime as dt

from app import db

NAMES = {"birthday": "Birthday", "anniversary": "Anniversary"}


def _esc(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    out, cur, size = [], "", 0
    for ch in line:
        n = len(ch.encode())
        if size + n > 74:
            out.append(cur)
            cur, size = " ", 1
        cur += ch
        size += n
    out.append(cur)
    return "\r\n".join(out)


def feed(book_ids: list[int], title: str = "Family birthdays", base_url: str = "") -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//iothing//ioContacts//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{_esc(title)}", "X-WR-CALDESC:Birthdays and anniversaries from ioContacts",
             "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H"]
    if book_ids:
        marks = ",".join(["%s"] * len(book_ids))
        rows = db.q(f"SELECT c.id, c.uid, c.fn, c.bday_year AS y, c.bday_month AS m, c.bday_day AS d, 'birthday' AS label, c.updated "
                    f"FROM contacts c WHERE c.book_id IN ({marks}) AND c.deleted = 0 AND c.bday_month IS NOT NULL "
                    f"AND c.bday_remind = 1 UNION ALL SELECT c.id, c.uid, c.fn, x.year, x.month, x.day, x.label, c.updated FROM contact_dates x "
                    f"JOIN contacts c ON c.id = x.contact_id WHERE c.book_id IN ({marks}) AND c.deleted = 0",
                    (*book_ids, *book_ids))
    else:
        rows = []
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for r in rows:
        y = r["y"] or 2000  # a yearless date starts in a leap year, so 29 February works
        try:
            start = dt.date(y, r["m"], r["d"])
        except ValueError:
            continue
        kind = NAMES.get(r["label"], r["label"].title())
        summary = f"{r['fn']}'s {kind.lower()}" if r["label"] == "birthday" else f"{r['fn']}: {kind}"
        lines += ["BEGIN:VEVENT", f"UID:{r['uid']}-{r['label'].replace(' ', '-')}@iocontacts", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{start:%Y%m%d}", f"DTEND;VALUE=DATE:{start + dt.timedelta(days=1):%Y%m%d}",
                  "RRULE:FREQ=YEARLY", f"SUMMARY:{_esc(summary)}", "TRANSP:TRANSPARENT",
                  f"CATEGORIES:{'BIRTHDAY' if r['label'] == 'birthday' else 'ANNIVERSARY'}"]
        if r["y"]:
            what = "Born" if r["label"] == "birthday" else "Since"
            lines.append(f"DESCRIPTION:{_esc(f'{what} {r[chr(121)]}')}")
        if base_url:
            lines.append(f"URL:{base_url}/#/c/{r['id']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"
