"""Schedules: the job form's choices (hourly, daily, weekly, monthly or a cron expression) as a five-field cron
expression, and when such an expression next fires. Plain Python, no database: the tests use it on its own."""
import datetime as _dt


def _field(spec, lo, hi):
    vals = set()
    for part in spec.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/", 1)
            step = int(st)
            if step < 1:
                raise ValueError("bad step")
        if part in ("*", ""):
            a, b = lo, hi
        elif "-" in part:
            a, b = (int(x) for x in part.split("-", 1))
        else:
            a = b = int(part)
            if step > 1:
                b = hi
        if a < lo or b > hi or a > b:
            raise ValueError("%s out of range %d-%d" % (part, lo, hi))
        vals.update(range(a, b + 1, step))
    return vals


class Cron:
    """Five-field cron: minute hour day-of-month month day-of-week (0 or 7 = Sunday)."""

    def __init__(self, expr):
        parts = (expr or "").split()
        if len(parts) != 5:
            raise ValueError("a cron expression has five fields")
        self.minutes = _field(parts[0], 0, 59)
        self.hours = _field(parts[1], 0, 23)
        self.dom = _field(parts[2], 1, 31)
        self.months = _field(parts[3], 1, 12)
        dow = _field(parts[4], 0, 7)
        self.dow = {0 if d == 7 else d for d in dow}
        self.dom_any, self.dow_any = parts[2] == "*", parts[4] == "*"

    def _day_ok(self, d):
        if d.month not in self.months:
            return False
        cron_dow = (d.weekday() + 1) % 7  # Python Monday=0 -> cron Monday=1
        in_dom, in_dow = d.day in self.dom, cron_dow in self.dow
        if self.dom_any and self.dow_any:
            return True
        if self.dom_any:
            return in_dow
        if self.dow_any:
            return in_dom
        return in_dom or in_dow  # classic cron: either restriction matches

    def matches(self, t):
        return t.minute in self.minutes and t.hour in self.hours and self._day_ok(t)

    def next_after(self, t):
        t = t.replace(second=0, microsecond=0) + _dt.timedelta(minutes=1)
        for _ in range(366 * 2):
            if self._day_ok(t):
                for h in sorted(self.hours):
                    if h < t.hour:
                        continue
                    for m in sorted(self.minutes):
                        if h == t.hour and m < t.minute:
                            continue
                        return t.replace(hour=h, minute=m)
            t = (t + _dt.timedelta(days=1)).replace(hour=0, minute=0)
        return None


def schedule_to_cron(s):
    """The UI's schedule form -> a cron expression ('' means run only by hand)."""
    s = s or {}
    mode = s.get("mode") or "manual"
    if mode == "manual":
        return ""
    if mode == "cron":
        Cron(s.get("cron") or "")
        return s["cron"].strip()
    if mode == "hourly":
        every = int(s.get("every") or 1)
        return "%d */%d * * *" % (int(s.get("minute") or 0), every) if every > 1 else "%d * * * *" % int(s.get("minute") or 0)
    hh, mm = (int(x) for x in (s.get("time") or "02:00").split(":"))
    if mode == "daily":
        return "%d %d * * *" % (mm, hh)
    if mode == "weekly":
        days = sorted({int(d) % 7 for d in (s.get("days") or [0])})
        return "%d %d * * %s" % (mm, hh, ",".join(str(d) for d in days))
    if mode == "monthly":
        return "%d %d %d * *" % (mm, hh, int(s.get("day") or 1))
    raise ValueError("unknown schedule mode %r" % mode)


def next_after(expr, now=None):
    """The next time the expression fires after now (a naive local datetime), or None."""
    if not expr:
        return None
    try:
        return Cron(expr).next_after(now or _dt.datetime.now())
    except ValueError:
        return None
