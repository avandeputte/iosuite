"""Notifications from ioThings (iosuite_shared.push): at each person's morning time, the upkeep due today (or late) that
is not a task in ioTask (ioTask sends those itself), and the warranties that end in SOON_DAYS days, today or in a week.
Run every minute by the app; it does nothing while nobody has a device, and each person gets one message a day at most.
"""
import datetime as dt

from iosuite_shared import push

from app import db

APP = "iothings"
KIND = "things"
WARN_IN = (30, 7, 0)  # days before a warranty ends that it is mentioned


def today_for(day: dt.date) -> list[dict]:
    """What is worth a word this morning: [{text, item}]. The same for everyone (the things are everyone's)."""
    out = []
    for k in db.q("SELECT k.title, k.next_due, i.id, i.name FROM thg_upkeep k JOIN thg_items i ON i.id = k.item_id "
                  "WHERE i.archived = 0 AND k.task_id IS NULL AND k.next_due <= %s ORDER BY k.next_due", (day,)):
        late = (day - k["next_due"]).days
        out.append({"text": f"{k['name']}: {k['title']}" + (f" ({late} days late)" if late > 1 else " (since yesterday)" if late == 1 else ""),
                    "item": k["id"]})
    ends = [day + dt.timedelta(days=n) for n in WARN_IN]
    for i in db.q(f"SELECT id, name, warranty_expires FROM thg_items WHERE archived = 0 AND lifetime_warranty = 0 "
                  f"AND warranty_expires IN ({','.join(['%s'] * len(ends))}) ORDER BY warranty_expires", ends):
        n = (i["warranty_expires"] - day).days
        out.append({"text": f"{i['name']}: the warranty ends " + ("today" if n == 0 else f"in {n} days"), "item": i["id"]})
    return out


def run(now: dt.datetime = None) -> int:
    people = push.recipients(KIND)
    if not people:
        return 0
    now = now or dt.datetime.now()
    key = f"things:{now.date()}"
    sent = 0
    items = None
    for u in people:
        if not push.is_morning(u["id"], now) or push.was_sent(u["id"], key):
            continue
        items = today_for(now.date()) if items is None else items
        if not items:
            push.claim(u["id"], key)
            continue
        if len(items) == 1:
            title, body = items[0]["text"], "ioThings"
        else:
            title, body = f"{len(items)} things need you", "; ".join(x["text"] for x in items[:6])
        url = push.link(APP, f"#/item/{items[0]['item']}" if len(items) == 1 else "#/upkeep")
        sent += push.notify(u["id"], KIND, title, body, url=url, once=key, tag="things")
    return sent
