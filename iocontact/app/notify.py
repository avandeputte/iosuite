"""Notifications from ioContact (iosuite_shared.push): at each person's morning time, whose birthday (the contacts
with "Remind me" on) or anniversary it is today, in the address books they see. Run every minute by the app; it does
nothing while nobody has a device, and each person gets one message a day at most.
"""
import datetime as dt

from iosuite_shared import push

from app import model

APP = "iocontact"


def _line(x: dict) -> str:
    if x["label"] == "birthday":
        return f"{x['fn']} turns {x['turns']}" if x.get("turns") else f"{x['fn']}’s birthday"
    return f"{x['fn']}: {x['turns']} years married" if x.get("turns") else f"{x['fn']}: anniversary"


def today_for(user: dict) -> list:
    """Today's birthdays (with "Remind me") and anniversaries in the books this account sees."""
    books = [b["id"] for b in model.books_for(user)]
    return [x for x in model.upcoming(books, days=0) if x["inDays"] == 0 and
            (x["remind"] is not False if x["label"] == "birthday" else "anniversary" in (x["label"] or "").lower())]


def run(now: dt.datetime = None) -> int:
    people = push.recipients("birthdays")
    if not people:
        return 0
    now = now or dt.datetime.now()
    key = f"birthdays:{now.date()}"
    sent = 0
    for u in people:
        if not push.is_morning(u["id"], now) or push.was_sent(u["id"], key):
            continue
        items = today_for(u)
        if not items:
            push.claim(u["id"], key)
            continue
        lines = [_line(x) for x in items]
        if len(items) == 1:
            title, body = lines[0] + " today", "Say happy birthday!" if items[0]["label"] == "birthday" else ""
        else:
            title, body = f"{len(items)} birthdays and anniversaries today", ", ".join(lines)
        url = push.link(APP, f"#/c/{items[0]['contactId']}" if len(items) == 1 else "")
        sent += push.notify(u["id"], "birthdays", title, body, url=url, once=key, tag="birthdays")
    return sent
