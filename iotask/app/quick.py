"""Smart quick add: one line of plain English becomes a task with a due date, a time, a repeat, a priority, a list and
the people it is for. "Pay rent every month on the 1st 9am !high" is the task "Pay rent", due on the next 1st at 9:00,
monthly, high priority.

What is understood (anything else stays in the title):
  when      today, tonight, tomorrow, monday (at the end, or after on / by / next / this), next week, this weekend,
            in 3 days, in 2 weeks, 15 nov, nov 15, the 15th, 2026-12-24, tomorrow morning
  time      9am, 9:30pm, 17:00, noon, at 5 (at the end)
  repeat    daily, every day, every weekday, weekly, every 2 weeks, every monday and thursday, monthly, every month on
            the 1st, yearly; "every 2 weeks after done" counts from the day the task is ticked off
  priority  !high !medium !low (or !!! !! !)
  list      #groceries (a list you may add to, by the start of its name)
  for       @emma (a family member, by the start of their name)
"""
import datetime as dt
import re

from dateutil import rrule as du_rrule
from dateutil.relativedelta import relativedelta

DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
SHORT_DAYS = {"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3, "fri": 4, "sat": 5, "sun": 6}
ALL_DAYS = {**DAYS, **SHORT_DAYS}
MONTHS = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8, "september": 9,
          "october": 10, "november": 11, "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
          "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12}
BYDAY = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "other": 2, "second": 2}
FREQ = {"day": "DAILY", "week": "WEEKLY", "month": "MONTHLY", "year": "YEARLY"}
PRIORITY = {"!!!": "high", "!!": "medium", "!": "low", "!high": "high", "!h": "high", "!medium": "medium", "!med": "medium",
            "!m": "medium", "!low": "low", "!l": "low"}
PARTS = {"morning": (9, 0), "afternoon": (14, 0), "evening": (18, 0), "night": (20, 0)}

_WD = "|".join(sorted(ALL_DAYS, key=len, reverse=True))
_FULL_WD = "|".join(DAYS)
_MON = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUM = r"\d{1,3}|" + "|".join(WORDS)
_UNIT = "day|week|month|year"
_ORD = r"(\d{1,2})(?:st|nd|rd|th)"
_TIME = r"(\d{1,2})(?:[:.](\d{2}))?\s*([ap])\.?m\.?(?![a-z])|([01]?\d|2[0-3]):([0-5]\d)(?!\d)"
_TAIL = re.compile(r"[\s,;:–-]+(?:on|at|by|due|for|from|starting|until|before|and|the|every|each)?$", re.I)


def _n(word: str | None) -> int:
    if not word:
        return 1
    word = re.sub(r"(st|nd|rd|th)$", "", word.lower()) if word[0].isdigit() else word.lower()
    return int(word) if word.isdigit() else WORDS.get(word, 1)


def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _pick(ref: str, items: list[dict], names) -> dict | None:
    """The one item whose name is ref, or starts with it (None when none does, or several do)."""
    k = _key(ref)
    if not k:
        return None
    exact = [x for x in items if any(_key(n) == k for n in names(x))]
    if len(exact) == 1:
        return exact[0]
    starts = [x for x in items if any(_key(n).startswith(k) for n in names(x))]
    return starts[0] if len(starts) == 1 else None


class _Line:
    """The text being read: take() cuts out what a pattern matched."""

    def __init__(self, text: str):
        self.s = " " + " ".join(text.split()) + " "

    def take(self, pattern: str):
        m = re.search(pattern, self.s, re.I)
        if m:
            self.s = self.s[:m.start()] + " " + self.s[m.end():]
        return m

    def title(self) -> str:
        s = " ".join(self.s.split())
        while True:
            t = _TAIL.sub("", s).strip(" ,;:–-")
            if t == s:
                return s
            s = t


def _weekday(today: dt.date, wd: int, nxt: bool = False) -> dt.date:
    """The coming such weekday (never today); with "next": the one in the week after this one."""
    d = today + dt.timedelta(days=(wd - today.weekday() - 1) % 7 + 1)
    if nxt and d.isocalendar()[:2] == today.isocalendar()[:2]:
        d += dt.timedelta(days=7)
    return d


def _monthday(today: dt.date, day: int) -> dt.date | None:
    """The coming such day of a month (today counts)."""
    for i in range(0, 13):
        try:
            d = (today + relativedelta(months=i)).replace(day=day)
        except ValueError:
            continue
        if d >= today:
            return d
    return None


def _date(today: dt.date, day: int, month: int, year: int | None) -> dt.date | None:
    try:
        if year:
            return dt.date(year, month, day)
        d = dt.date(today.year, month, day)
        return d if d >= today else dt.date(today.year + 1, month, day)
    except ValueError:
        return None


def _days(text: str) -> list[int]:
    return sorted({ALL_DAYS[w] for w in re.findall(_WD, text.lower())})


def _repeat(line: _Line, out: dict) -> dict:
    """The repeat, cut out of the line: out gets rrule or repeatAfter; what it says about the first date comes back."""
    hint = {}
    m = line.take(rf"\s(?:every\s+|each\s+)?(?:({_NUM})\s+)?({_UNIT})s?\s+after\s+(?:it\s+is\s+|it's\s+|i\s+|i'm\s+|being\s+)?"
                  r"(?:done|completion|completing|completed|finish(?:ed|ing)?|ticked\s+off|ticking\s+it\s+off)(?=\s)")
    if m:
        n = _n(m.group(1))
        out["repeatAfter"] = f"P{n}{m.group(2)[0].upper()}"
        return hint
    # every month on the 15th, monthly on the 1st, on the 1st of every month, every 15th
    m = (line.take(rf"\s(?:every\s+month|each\s+month|monthly)\s+on\s+(?:the\s+)?{_ORD}?(?(1)|(\d{{1,2}}))(?=\s)")
         or line.take(rf"\s(?:on\s+)?the\s+{_ORD}\s+of\s+(?:every|each)\s+month()(?=\s)")
         or line.take(rf"\s(?:every|each)\s+{_ORD}()(?=\s)"))
    if m:
        day = int(m.group(1) or m.group(2))
        if 1 <= day <= 31:
            out["rrule"] = f"FREQ=MONTHLY;BYMONTHDAY={day}"
            return hint
    m = line.take(rf"\s(?:every|each)\s+(other\s+|second\s+)?((?:{_WD})s?(?:\s*(?:,|and|&|\+)\s*(?:{_WD})s?)*)(?=\s)")
    if m:
        out["rrule"] = "FREQ=WEEKLY" + (";INTERVAL=2" if m.group(1) else "") + ";BYDAY=" + ",".join(BYDAY[d] for d in _days(m.group(2)))
        return hint
    if line.take(r"\s(?:every|each)\s+weekday(?=\s)|\sweekdays(?=\s)"):
        out["rrule"] = "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"
        return hint
    m = line.take(rf"\s(?:every|each)\s+(?:({_NUM})\s+)?({_UNIT})s?(?=\s)")
    if m:
        n = _n(m.group(1))
        out["rrule"] = f"FREQ={FREQ[m.group(2).lower()]}" + (f";INTERVAL={n}" if n > 1 else "")
        return hint
    m = line.take(r"\s(daily|weekly|biweekly|fortnightly|monthly|quarterly|yearly|annually)(?=\s)")
    if m:
        out["rrule"] = {"daily": "FREQ=DAILY", "weekly": "FREQ=WEEKLY", "biweekly": "FREQ=WEEKLY;INTERVAL=2",
                        "fortnightly": "FREQ=WEEKLY;INTERVAL=2", "monthly": "FREQ=MONTHLY", "quarterly": "FREQ=MONTHLY;INTERVAL=3",
                        "yearly": "FREQ=YEARLY", "annually": "FREQ=YEARLY"}[m.group(1).lower()]
    return hint


def _when(line: _Line, now: dt.datetime) -> tuple[dt.date | None, tuple | None, dt.datetime | None]:
    """The day, the time of day, or an exact moment ("in 2 hours"), cut out of the line."""
    today, day, time = now.date(), None, None
    m = line.take(rf"\sin\s+({_NUM})\s+(hour|hr|minute|min)s?(?=\s)")
    if m:
        at = now + dt.timedelta(**{"hours" if m.group(2).lower().startswith("h") else "minutes": _n(m.group(1))})
        return None, None, at.replace(second=0, microsecond=0)
    # a part of a day: tomorrow morning, friday evening, tonight
    m = (line.take(r"\s(?:(?:on|by|due)\s+)?(today|tomorrow|this)\s+(morning|afternoon|evening|night)(?=\s)")
         or line.take(rf"\s(?:on|by|due|next|this)\s+({_WD})\s+(morning|afternoon|evening|night)(?=\s)")
         or line.take(rf"\s({_FULL_WD})\s+(morning|afternoon|evening|night)\s*$"))
    if m:
        w = m.group(1).lower()
        day = today if w in ("today", "this") else today + dt.timedelta(days=1) if w == "tomorrow" else _weekday(today, ALL_DAYS[w])
        time = PARTS[m.group(2).lower()]
    elif line.take(r"\stonight(?=\s)"):
        day, time = today, PARTS["night"]
    # a clock time, with the weekday right before it ("friday 9am")
    tm = re.search(rf"\s(?:(?:on|by|due)\s+)?(?:(next|this)\s+)?({_WD})\s+(?:(?:at|@)\s*)?(?={_TIME})", line.s, re.I) if day is None else None
    if tm:
        day = _weekday(today, ALL_DAYS[tm.group(2).lower()], (tm.group(1) or "").lower() == "next")
        line.s = line.s[:tm.start()] + " " + line.s[tm.end():]
    m = line.take(rf"\s(?:(?:at|@|by|before)\s*)?(?:{_TIME})(?=[\s,.])")
    if m:
        if m.group(3):
            h = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0)
            if 1 <= int(m.group(1)) <= 12:
                time = (h, int(m.group(2) or 0))
        else:
            time = (int(m.group(4)), int(m.group(5)))
    elif line.take(r"\s(?:(?:at|by|before)\s+)?(?:noon|midday)(?=\s)"):
        time = (12, 0)
    if day is None:
        day = _day(line, today)
    return day, time, None


def _day(line: _Line, today: dt.date) -> dt.date | None:
    m = line.take(r"\s(?:(?:on|by|due|until|before)\s+)?(\d{4})-(\d{2})-(\d{2})(?=\s)")
    if m:
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    m = line.take(rf"\s(?:(?:on|by|due|until|before)\s+)?(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\.?(?:,?\s+(\d{{4}}))?(?=[\s,])")
    if m and _date(today, int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3)) if m.group(3) else None):
        return _date(today, int(m.group(1)), MONTHS[m.group(2).lower()], int(m.group(3)) if m.group(3) else None)
    m = line.take(rf"\s(?:(?:on|by|due|until|before)\s+)?({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?(?=[\s,])")
    if m and _date(today, int(m.group(2)), MONTHS[m.group(1).lower()], int(m.group(3)) if m.group(3) else None):
        return _date(today, int(m.group(2)), MONTHS[m.group(1).lower()], int(m.group(3)) if m.group(3) else None)
    m = line.take(rf"\s(?:(?:on|by|due|until|before)\s+)?the\s+{_ORD}(?=\s)")
    if m and 1 <= int(m.group(1)) <= 31:
        return _monthday(today, int(m.group(1)))
    if line.take(r"\s(?:the\s+)?day\s+after\s+tomorrow(?=\s)"):
        return today + dt.timedelta(days=2)
    m = line.take(r"\s(?:(?:by|due|until|before)\s+)?(today|tomorrow|tmrw)(?=[\s,])")
    if m:
        return today + dt.timedelta(days=0 if m.group(1).lower() == "today" else 1)
    m = line.take(rf"\sin\s+({_NUM})\s+({_UNIT})s?(?=\s)")
    if m:
        return today + relativedelta(**{m.group(2).lower() + "s": _n(m.group(1))})
    m = line.take(r"\s(?:(?:by|due|until|before)\s+)?(this|next)\s+weekend(?=\s)")
    if m:
        d = today + dt.timedelta(days=(5 - today.weekday()) % 7)
        return d + dt.timedelta(days=7 if m.group(1).lower() == "next" else 0)
    m = line.take(r"\s(?:(?:by|due|until|before)\s+)?next\s+(week|month)(?=\s)")
    if m:
        return today + dt.timedelta(days=7 - today.weekday()) if m.group(1).lower() == "week" else (today + relativedelta(months=1)).replace(day=1)
    if line.take(r"\s(?:(?:by|due|until|before)\s+)?(?:the\s+)?end\s+of\s+(?:the\s+|this\s+)?month(?=\s)"):
        return today + relativedelta(day=31)
    m = line.take(rf"\s(?:on|by|due|until|before|this|next)\s+(?:(next|this)\s+)?({_WD})(?=[\s,])")
    if m:
        return _weekday(today, ALL_DAYS[m.group(2).lower()], "next" in m.group(0).lower().split())
    m = line.take(rf"\s({_FULL_WD})\s*$")  # a weekday by itself counts at the end of the line only
    if m:
        return _weekday(today, DAYS[m.group(1).lower()])
    return None


def parse(text: str, now: dt.datetime, lists: list[dict] | None = None, members: list[dict] | None = None) -> dict:
    """The task a line describes: {title} and, when the line says so, due ('2026-11-12' or '2026-11-12T09:00', on the
    clock of now's time zone), rrule, repeatAfter, priority, listId and members (ids). now: the moment it is, in the
    time zone of whoever typed it. lists: the lists a task may go to; members: the family."""
    raw = " ".join((text or "").split())
    line, out = _Line(raw), {}
    for m in list(re.finditer(r"(?<=\s)(!{1,3}|![a-z]+)(?=\s)", line.s, re.I)):
        if m.group(1).lower() in PRIORITY:
            out["priority"] = PRIORITY[m.group(1).lower()]
            line.s = line.s.replace(m.group(0), " ", 1)
            break
    for m in list(re.finditer(r"(?<=\s)#([\w-]+)", line.s)):
        c = _pick(m.group(1), lists or [], lambda c: [c["name"]])
        if c and "listId" not in out:
            out["listId"] = c["id"]
            line.s = line.s.replace(m.group(0), " ", 1)
    for m in list(re.finditer(r"(?<=\s)@([\w-]+)", line.s)):
        who = _pick(m.group(1), members or [], lambda p: [p["displayName"], p["name"], *p["displayName"].split()])
        if who:
            out.setdefault("members", [])
            if who["id"] not in out["members"]:
                out["members"].append(who["id"])
            line.s = line.s.replace(m.group(0), " ", 1)
    _repeat(line, out)
    day, time, at = _when(line, now)
    if time is None and re.search(r"\sat\s+\d{1,2}\s*$", line.s, re.I):  # "at 5" counts at the end of the line only
        h = int(line.take(r"\sat\s+(\d{1,2})\s*$").group(1))
        time = (h + 12 if 1 <= h <= 7 else h, 0) if h <= 23 else None
        if day is None:
            day = _day(line, now.date())
    title = line.title()
    if not title:  # only dates and marks: a task needs a name, so the line is the name
        return {"title": raw}
    out["title"] = title
    rule = out.get("rrule")
    if at is not None:
        out["due"] = at.strftime("%Y-%m-%dT%H:%M")
        return out
    if day is None and rule:  # a repeat without a first date: its first turn from today on
        try:
            first = du_rrule.rrulestr(rule, dtstart=dt.datetime.combine(now.date(), dt.time(*(time or (23, 59)))))
            nxt = first.after(now.replace(tzinfo=None), inc=True)
            day = nxt.date() if nxt else now.date()
        except (ValueError, TypeError):
            day = now.date()
    if day is None and (time is not None or out.get("repeatAfter")):
        day = now.date()
        if time is not None and dt.datetime.combine(day, dt.time(*time)) <= now.replace(tzinfo=None):
            day += dt.timedelta(days=1)  # that time has passed today: tomorrow
    if day is not None:
        out["due"] = day.isoformat() + (f"T{time[0]:02d}:{time[1]:02d}" if time is not None else "")
    return out
