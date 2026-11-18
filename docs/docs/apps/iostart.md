---
description: ioStart, the start page of the ioThing suite.
---

# ioStart <small>start page</small>

A self-hosted home page for the family: a tile per installed app, with what matters today on it. **It is optional**:
every app works without it. It earns its place once you run two or more apps.

[The ioStart page on the website, with more screenshots →](https://iosuite.iothing.net/ioStart/)
{ .md-button }

![The ioStart start page: a tile per app with today on it, birthdays, the week ahead and bookmarks](../img/iostart.jpg)

## What it does

- **A tile per app**, found by itself: every app registers in the suite's list of apps, so there is nothing to type.
  An app that isn't installed has no tile.
- **A glimpse of each app**: ioPix's photos from this day in earlier years, ioCalendar's rest of today, ioTask's tasks due today, ioHealth's
  steps, rings and sleep, ioMoney's bills due this week (with a warning when an account is about to run low or a bank
  link is behind); each person sees only what that app shows them.
- **The week ahead**: a Birthdays card (ioContact) and a This week card (ioCalendar).
- **A search box** (⌘K / Ctrl-K) across the apps and bookmarks (people, events, tasks, recipes, notes, things,
  payees and transactions, the people, albums and places of your photos), the web as a fallback, and **Quick add**:
  "dinner fri 19:00" makes an event, "t buy milk sat" a task, "n the gate code is 4411" a note.
- **Tidy up** on the Bookmarks page: finds the links that no longer work, the ones that moved (the new address is one
  click away) and the same address kept twice.
- **Weather** (AccuWeather, a free key), **Home Assistant** entities you can switch from the page, and **bookmarks**.
- **A wall display** for a tablet: photos behind a big clock, the weather, today's and the coming days' events.
- **Your own page**: each person hides and orders tiles and cards.
- **One MCP server for the whole suite** (off until an admin turns it on under Settings › Server): connect an AI
  assistant here once and it gets every app's tools, each app still deciding what you may do there. See
  [AI assistants](../run/assistants.md).
- **One address for the whole suite**, when a suite admin turns it on: the start page answers for every app, each in
  a folder (`…/calendar/`, `…/notes/`), so one name, one certificate and one port reach them all. See
  [Reverse proxy and HTTPS](../run/reverse-proxy.md#one-address-without-a-proxy-the-start-page-answers-for-every-app).

## Bookmarks in your browser

The **ioStart Bookmarks** extension keeps a browser's own bookmarks the same as the start page's, both ways: the
bookmarks bar, Other bookmarks (and Firefox's bookmarks menu) match folders on the start page, and an add, change or
delete in one browser reaches every other browser within a minute.

- **Chrome, Edge, Vivaldi, Brave, Opera**: [install it from the Chrome Web Store](https://chromewebstore.google.com/detail/iosuite-bookmarks/nldealkpbjiholobfadimblcmdlphkoe).
- **Firefox**: open the signed `.xpi` of the newest `extension-v…` [release](https://github.com/avandeputte/iosuite/releases?q=extension).

Then type the start page's address in the extension, choose how the first sync goes, and sign in: it gets an app
password of its own, for bookmark sync only. Settings › Bookmarks on the start page also takes Floccus and other apps
that sync over Nextcloud Bookmarks or WebDAV. What it sends and keeps: [privacy policy](../privacy/iostart-bookmarks.md).

## With the other apps

ioStart is all about them: it shows a tile and widgets for each app it finds, asks each app with the viewer's own
sign-in, and leaves a tile as it was when its app is down.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iostart/proxmox/ct/iostart.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iostart/docker-compose.yml), or the [whole suite in one stack](../start/docker.md#the-whole-suite-in-one-stack) |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/iostart && ./setup.sh` |
| Port | 8630 |
| Source | [iosuite/iostart](https://github.com/avandeputte/iosuite/tree/main/iostart) |

Its Proxmox installer is a convenient place to start with several apps: tick the others in its checklist.
