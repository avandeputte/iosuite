---
description: ioTask, the family's task lists in the ioThing suite.
---

# ioTask <small>tasks</small>

The family's task lists: a web app for everyone at home, and the standard protocol reminders apps already speak, so the
same lists show up in Apple Reminders on iPhone, iPad and Mac, in Tasks.org or jtx Board on Android, and in Thunderbird.

## What it does

- **Tasks** with notes, a due date (a day, or a day and a time), a priority, alerts and a link; **repeating tasks**
  that move on to their next date when you tick them off; **subtasks**.
- **Quick add in plain words**: "Pay rent every month on the 1st 9am !high", "Call mom tomorrow 5pm @emma",
  "Milk #groceries". The line shows what it understood (the date, the repeat, the priority, the list, who it's for)
  before you press Enter.
- **Postpone** with one click: a task to tomorrow, the weekend or next week, and everything overdue to today in one
  go. Alerts move along.
- **Repeat after it's done**: "every 2 weeks after done" counts from the day you tick it off, not from the date it was
  due; for the things that slip (descaling the kettle, the filter, a haircut).
- **Your own order**: drag tasks within a list and the lists in the sidebar.
- **Activity and undo**: who added, changed, ticked off or deleted what, from the web app, a phone or an assistant.
  Every change can be taken back, right after it (a note with Undo) or later from the Activity page.
- **Templates**: save a list as a template (a packing list, the weekly clean) and add it to any list again, with its
  subtasks, due on a day you pick.
- **Print** a list as a checklist.
- **Lists**: a shared Family list, a private Personal one for each account, and as many more as you like, each with its
  colour.
- **Today, Scheduled, All and Completed** across every list, with quick add and search.
- **Family members on tasks**: tag a task with who it's for, and show only one person's tasks.
- **Everywhere**: CalDAV (to-dos) for Apple Reminders, DAVx⁵ on Android and Thunderbird; an Apple configuration profile
  that sets up an iPhone in one step; a REST API with OpenAPI docs at `/api/docs`; an MCP server for AI assistants.

## On its own

ioTask is a complete task manager for a family. It needs its database and the Shared ioSuite database, and HTTPS if
phones should sync away from home.

## In Apple Reminders

Settings › Apps and devices › *Download the profile* adds the account to an iPhone, iPad or Mac in one step; the lists
then appear in Reminders under "ioTask". Reminders keeps the standard part of a task for an account that is not
iCloud: title, notes, due date and time, repeat, alert, priority and done. Subtasks made in ioTask arrive as ordinary
tasks of the list, and Reminders' own tags, flags and sections stay on iCloud lists. A task that repeats after it's
done keeps doing so when it is ticked off in Reminders: ioTask brings it back with its next date.

## With the other apps

- **ioSuite**: the tasks due today on the tile, the overdue ones first.
- **ioCalendar**: the tasks that are due show on their day in the calendar, beside the events, and are ticked off there.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iotask/main/proxmox/ct/iotask.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iotask/blob/main/docker-compose.yml): the image `ghcr.io/avandeputte/iotask` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iotask && cd iotask && ./setup.sh` |
| Port | 8670 |
| Source | [github.com/avandeputte/iotask](https://github.com/avandeputte/iotask) |
