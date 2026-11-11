---
description: ioCalendar, the family calendar of the ioThing suite.
---

# ioCalendar <small>calendar</small>

The family calendar: a web app for the whole family, and the standard protocols every calendar app already speaks, so
the same events show up on phones, in Apple Calendar, Google Calendar, Outlook, Thunderbird and anywhere else.

![ioCalendar's week view, each event tagged with the family member it is for](../img/iocalendar-week.jpg)

## What it does

- **Events** with a place, people, reminders, notes and a link; all-day and multi-day; **repeating events** of every
  kind, with "this one, this and later, or all of them" when you change one.
- **Calendars**: a shared Family calendar, a private Personal one for each account, and as many more as you like, each
  with its colour.
- **Family members on events**: tag an event with who it's for, and show only one person's events.
- **Public holidays** of one or more countries (and a region), worked out on the server, nothing fetched.
- **Views**: month, week, day and agenda, drag and drop, search, keyboard shortcuts.
- **Everywhere**: CalDAV for Apple Calendar, DAVx⁵ on Android, Thunderbird and Outlook; an Apple configuration profile
  that sets up an iPhone in one step; private `webcal://` subscription links for Google Calendar and Outlook; free/busy;
  a REST API with OpenAPI docs at `/api/docs`.

## On its own

ioCalendar is a complete family calendar. It needs its database and the Shared ioSuite database, and HTTPS if phones
should sync away from home.

## With the other apps

- **ioContacts**: a read-only **Birthdays** calendar with the birthdays and anniversaries kept in ioContacts, brought up
  to date every six hours; the people on an event come from your contacts.
- **ioTasks**: the tasks that are due show on their day, beside the events, in the month, week, day and agenda views.
  Tick one off right on the calendar; a repeating task moves on to its next day.
- **ioSuite**: today's events on the tile, a This week card, and "Quick add" from the search box ("dentist tomorrow 9am").

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iocalendar/main/proxmox/ct/iocalendar.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iocalendar/blob/main/docker-compose.yml): the image `ghcr.io/avandeputte/iocalendar` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iocalendar && cd iocalendar && ./setup.sh` |
| Port | 8620 |
| Source | [github.com/avandeputte/iocalendar](https://github.com/avandeputte/iocalendar) |
