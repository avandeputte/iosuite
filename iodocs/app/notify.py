"""Notifications from ioDocs (iosuite_shared.push, kind "docs"): at each person's morning time, the documents they see
that reach their reminder today (the day the kind's lead time, or the document's own, begins), that expire in 7 days,
today, or that expired yesterday. Each document is told to the people it is for when they have an account with a role
here; a document that is nobody's in particular (the house insurance) goes to the editors and admins who see it.
Run every minute by the app; it does nothing while nobody has a device, and each person gets one message a day at most.
"""
import datetime as dt

from iosuite_shared import push

from app import db, model

APP = "iodocs"
KIND = "docs"
ALSO = (7, 0, -1)  # days before it expires (or after: -1) that a document is mentioned again


def due_on(day: dt.date) -> list[dict]:
    """The documents worth a word on this day: [{doc, days}]."""
    out = []
    for d in db.q("SELECT * FROM doc_documents WHERE archived = 0 AND expires_on IS NOT NULL AND expires_on BETWEEN %s AND %s",
                  (day - dt.timedelta(days=1), day + dt.timedelta(days=1100))):
        days = (d["expires_on"] - day).days
        lead = model.remind_days(d)
        if not lead:
            continue
        if days == lead or days in ALSO:
            out.append({"doc": d, "days": days})
    return out


def _words(x: dict) -> str:
    d, n = x["doc"], x["days"]
    when = ("expired yesterday" if n < 0 else "expires today" if n == 0 else "expires tomorrow" if n == 1
            else f"expires in {n} days" if n < 60 else f"expires on {d['expires_on'].strftime('%b %-d, %Y')}")
    return f"{d['title']} {when}"


def for_person(u: dict, items: list[dict]) -> list[dict]:
    """The ones this person hears about: the documents that are theirs, and those that are nobody's in particular when
    they are an editor or admin who sees them."""
    out = []
    people = model.people_of([x["doc"]["id"] for x in items])
    for x in items:
        ids = people.get(x["doc"]["id"], [])
        d = {**x["doc"], "_people": ids}
        if not model.can_see(u, d):
            continue
        if u["id"] in ids or (not ids and model.may_edit_all(u)):
            out.append(x)
    return out


def run(now: dt.datetime = None) -> int:
    people = push.recipients(KIND)
    if not people:
        return 0
    now = now or dt.datetime.now()
    key = f"docs:{now.date()}"
    sent = 0
    items = None
    for u in people:
        if not push.is_morning(u["id"], now) or push.was_sent(u["id"], key):
            continue
        items = due_on(now.date()) if items is None else items
        mine = for_person(u, items)
        if not mine:
            push.claim(u["id"], key)
            continue
        if len(mine) == 1:
            title, body = _words(mine[0]), "Time to renew it" if mine[0]["days"] <= 7 else "ioDocs"
            url = push.link(APP, f"#/doc/{mine[0]['doc']['id']}")
        else:
            title, body = f"{len(mine)} documents to renew", "; ".join(_words(x) for x in mine[:6])
            url = push.link(APP, "#/expiring")
        sent += push.notify(u["id"], KIND, title, body, url=url, once=key, tag="docs")
    return sent
