---
title: The ioThing suite
description: Self-hosted apps for the family. Install one, or all of them.
---

# The ioThing suite

Small self-hosted apps for the family, each one a complete product on its own:

| App | What it is | Default port | Source |
| --- | --- | --- | --- |
| [ioPix](apps/iopix.md) | Photos: a web app for a photo library, with or without digiKam | 8600 | [iopix](https://github.com/avandeputte/iopix) |
| [ioNotes](apps/ionotes.md) | Notes, clipboard snippets and screenshots, with Mac and iPhone apps | 8610 | [ionotes](https://github.com/avandeputte/ionotes) |
| [ioCalendar](apps/iocalendar.md) | The family calendar, over CalDAV on every phone | 8620 | [iocalendar](https://github.com/avandeputte/iocalendar) |
| [ioSuite](apps/iosuite.md) | The start page: a tile per app, search, weather, bookmarks | 8630 | [iosuite](https://github.com/avandeputte/iosuite) |
| [ioContacts](apps/iocontacts.md) | Contacts for the family, over CardDAV and LDAP | 8640 | [iocontacts](https://github.com/avandeputte/iocontacts) |
| [ioHealth](apps/iohealth.md) | Apple Health data in your own database, with a fitness web app | 8650 | [iohealth](https://github.com/avandeputte/iohealth) |
| [ioTasks](apps/iotasks.md) | The family's task lists, in Apple Reminders and every tasks app over CalDAV | 8670 | [iotasks](https://github.com/avandeputte/iotasks) |
| [ioRecipe](apps/iorecipe.md) | The family's recipes, with photos and import from the web | 8690 | [iorecipe](https://github.com/avandeputte/iorecipe) |

!!! tip "You don't need the whole suite"
    Every app installs, runs and updates on its own. If all you want is a photo app, install ioPix and stop there:
    nothing else is required, and nothing is missing. Add another app later, or never.
    [One app or all of them](start/one-or-all.md) explains what changes when you do.

## What they have in common

Every app is built the same way, so what you learn in one holds in the others:

- **A small web server** (Python, FastAPI) with its own single-page web app: light and dark, a real phone layout,
  installable on a home screen.
- **Its own MariaDB or MySQL database**, plus one **Shared ioSuite database** for the accounts. With a single app,
  that is simply where its accounts live. With several, they all point at the same one, and everyone has one account
  for all of them. See [Databases](reference/databases.md).
- **The same installers**: a one-line Proxmox VE container, a Docker image (amd64 and arm64), or `setup.sh` on any
  Linux or Mac. See [Requirements](start/requirements.md).
- **The same Settings**: Account and Display for everyone; Server (version, updates, log, restart) for admins;
  Security and Global settings for suite admins.
- **Updates from the web app**: a daily check, then **Update now** under Settings › Server. See [Updates](run/updates.md).
- **An MCP server** at `/mcp` in ioPix, ioNotes, ioCalendar, ioTasks, ioRecipe and ioContacts, so an AI assistant such as Claude can
  work with them as you, with an app password. See [AI assistants](run/assistants.md).
- **Free and open source**, GPL-3.0-or-later.

## Where to start

1. [One app or all of them](start/one-or-all.md): decide what you need.
2. [Requirements](start/requirements.md): a database server and somewhere to run the app.
3. Install it: [Proxmox VE](start/proxmox.md), [Docker](start/docker.md) or [any Linux or Mac](start/linux-mac.md).
4. [First run](start/first-run.md): sign in, make accounts, put it behind HTTPS.
