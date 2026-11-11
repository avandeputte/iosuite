"""Smart quick add (app/quick.py): what a line of plain English becomes, and what is left alone."""
import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from app import quick

NOW = dt.datetime(2026, 11, 11, 10, 0, tzinfo=ZoneInfo("Europe/Brussels"))  # a Wednesday morning
LISTS = [{"id": 1, "name": "Family"}, {"id": 2, "name": "Groceries"}, {"id": 3, "name": "Personal"}]
FAMILY = [{"id": 7, "name": "emma", "displayName": "Emma V"}, {"id": 8, "name": "alex", "displayName": "Alex"}]


@pytest.mark.parametrize("line, want", [
    ("Pay rent every month on the 1st 9am !high", {"title": "Pay rent", "due": "2026-12-01T09:00", "rrule": "FREQ=MONTHLY;BYMONTHDAY=1", "priority": "high"}),
    ("Call mom tomorrow 5pm", {"title": "Call mom", "due": "2026-11-12T17:00"}),
    ("Take out trash every tuesday and friday 7am", {"title": "Take out trash", "due": "2026-11-13T07:00", "rrule": "FREQ=WEEKLY;BYDAY=TU,FR"}),
    ("Dentist 15 nov 14:30 #personal @emma", {"title": "Dentist", "due": "2026-11-15T14:30", "listId": 3, "members": [7]}),
    ("Book flights in 2 weeks", {"title": "Book flights", "due": "2026-11-25"}),
    ("Submit report by friday", {"title": "Submit report", "due": "2026-11-13"}),
    ("Movie night friday", {"title": "Movie night", "due": "2026-11-13"}),
    ("Pack bags next friday", {"title": "Pack bags", "due": "2026-11-20"}),
    ("Email Bob monday 9am about roof", {"title": "Email Bob about roof", "due": "2026-11-16T09:00"}),
    ("Buy milk today", {"title": "Buy milk", "due": "2026-11-11"}),
    ("Meeting 9:30", {"title": "Meeting", "due": "2026-11-12T09:30"}),  # 9:30 has passed today
    ("Dinner at 7", {"title": "Dinner", "due": "2026-11-11T19:00"}),
    ("Lunch noon friday", {"title": "Lunch", "due": "2026-11-13T12:00"}),
    ("Haircut tomorrow morning", {"title": "Haircut", "due": "2026-11-12T09:00"}),
    ("Yoga tonight", {"title": "Yoga", "due": "2026-11-11T20:00"}),
    ("Call plumber in 2 hours", {"title": "Call plumber", "due": "2026-11-11T12:00"}),
    ("Clean gutters this weekend", {"title": "Clean gutters", "due": "2026-11-14"}),
    ("Renew passport end of month", {"title": "Renew passport", "due": "2026-11-30"}),
    ("Birthday card the 20th", {"title": "Birthday card", "due": "2026-11-20"}),
    ("Buy 2 tickets for Dec 5", {"title": "Buy 2 tickets", "due": "2026-12-05"}),
    ("Tax return 2027-04-15", {"title": "Tax return", "due": "2027-04-15"}),
    ("Standup every weekday 9:15am", {"title": "Standup", "due": "2026-11-12T09:15", "rrule": "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"}),
    ("Bins every other thursday", {"title": "Bins", "due": "2026-11-12", "rrule": "FREQ=WEEKLY;INTERVAL=2;BYDAY=TH"}),
    ("Check oil monthly", {"title": "Check oil", "due": "2026-11-11", "rrule": "FREQ=MONTHLY"}),
    ("Backup yearly on dec 31", {"title": "Backup", "due": "2026-12-31", "rrule": "FREQ=YEARLY"}),
    ("Water plants every 2 weeks after done", {"title": "Water plants", "due": "2026-11-11", "repeatAfter": "P2W"}),
    ("Swim bag @emma #fam !!", {"title": "Swim bag", "listId": 1, "members": [7], "priority": "medium"}),
    ("Pay bill !", {"title": "Pay bill", "priority": "low"}),
])
def test_what_a_line_says(line, want):
    assert quick.parse(line, NOW, LISTS, FAMILY) == want


@pytest.mark.parametrize("line", [
    "Read 1984", "Plan tomorrow's lunch", "Where I sat", "Buy cream for the sun", "Friday night dinner plan",
    "Meet at 5 Main Street", "Order #1234 follow up", "Ask @nobody about it", "Great idea!", "tomorrow",
])
def test_what_stays_a_title(line):
    assert quick.parse(line, NOW, LISTS, FAMILY) == {"title": line}
