"""What a person keeps in ioCalendar, counted or removed when their account is deleted (iosuite_shared.persondata):
their private calendars with every event in them, outside calendars they subscribed to privately included (their subscription links are in the Shared ioSuite database, and go with the account). Events they put on a shared calendar
(the Family calendar) stay: the family still needs them."""

from app import db, model


def of(user_id: int, remove: bool) -> list:
    cals = [r["id"] for r in db.q("SELECT id FROM cal_calendars WHERE owner_id = %s", (user_id,))]
    events = db.one("SELECT count(*) AS n FROM cal_events e JOIN cal_calendars c ON c.id = e.calendar_id "
                    "WHERE c.owner_id = %s AND e.deleted = 0", (user_id,))["n"]
    shared = db.one("SELECT count(*) AS n FROM cal_events e JOIN cal_calendars c ON c.id = e.calendar_id "
                    "WHERE c.owner_id IS NULL AND e.created_by = %s AND e.deleted = 0", (user_id,))["n"]
    if remove:
        for cid in cals:
            model.delete_calendar(cid)  # its events' links to other items of the suite go too
    return [{"what": "private calendars", "one": "private calendar", "count": len(cals)},
            {"what": "events in them", "one": "event in them", "count": events},
            {"what": "events they added to shared calendars", "one": "event they added to a shared calendar", "count": shared, "kept": True}]
