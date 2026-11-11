---
description: ioTasks, the family's task lists in the ioThing suite.
---

# ioTasks <small>tasks</small>

The family's task lists: a web app for everyone at home, and the standard protocol reminders apps already speak, so the
same lists show up in Apple Reminders on iPhone, iPad and Mac, in Tasks.org or jtx Board on Android, and in Thunderbird.

## What it does

- **Tasks** with notes, a due date (a day, or a day and a time), a priority, alerts and a link; **repeating tasks**
  that move on to their next date when you tick them off; **subtasks**.
- **Lists**: a shared Family list, a private Personal one for each account, and as many more as you like, each with its
  colour.
- **Today, Scheduled, All and Completed** across every list, with quick add and search.
- **Family members on tasks**: tag a task with who it's for, and show only one person's tasks.
- **Everywhere**: CalDAV (to-dos) for Apple Reminders, DAVx⁵ on Android and Thunderbird; an Apple configuration profile
  that sets up an iPhone in one step; a REST API with OpenAPI docs at `/api/docs`; an MCP server for AI assistants.

## On its own

ioTasks is a complete task manager for a family. It needs its database and the Shared ioSuite database, and HTTPS if
phones should sync away from home.

## In Apple Reminders

Settings › Apps and devices › *Download the profile* adds the account to an iPhone, iPad or Mac in one step; the lists
then appear in Reminders under "ioTasks". Reminders keeps the standard part of a task for an account that is not
iCloud: title, notes, due date and time, repeat, alert, priority and done. Subtasks made in ioTasks arrive as ordinary
tasks of the list, and Reminders' own tags, flags and sections stay on iCloud lists.

## With the other apps

- **ioSuite**: the tasks due today on the tile, the overdue ones first.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iotasks/main/proxmox/ct/iotasks.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iotasks/blob/main/docker-compose.yml): the image `ghcr.io/avandeputte/iotasks` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iotasks && cd iotasks && ./setup.sh` |
| Port | 8670 |
| Source | [github.com/avandeputte/iotasks](https://github.com/avandeputte/iotasks) |
