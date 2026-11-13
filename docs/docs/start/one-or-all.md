---
description: What a single ioThing app needs, what you gain by adding another, and what stays separate.
---

# One app or all of them

There is no suite to install first, no central server, and no app that depends on another. **Each app is the whole
product for what it does.** Pick the one you need; the rest are optional.

## Just one app

A single app needs:

- somewhere to run: a Proxmox VE container, a Docker host, or any Linux machine or Mac;
- a MariaDB or MySQL server with two databases on it: the app's own, and the **Shared ioSuite database** that holds its
  accounts. The installer can create both for you (give it a database administrator once). ioNote can even keep its
  notes in a SQLite file instead.

That's all. A photo app alone is a perfectly good install:

```sh
# on a Proxmox VE host, as root
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iopix/proxmox/ct/iopix.sh)"
```

The app does not look for the others, does not show empty spaces for them, and does not need the
[ioStart start page](../apps/iostart.md). Its Settings show Security and Global settings to suite admins all the same:
those manage the accounts in the Shared ioSuite database, whether one app uses them or seven.

| You want | Install |
| --- | --- |
| A web app for your photos (with digiKam, or without) | [ioPix](../apps/iopix.md) |
| Notes and clipboard snippets on your Mac and iPhone | [ioNote](../apps/ionote.md) (the server) and the Mac / iPhone app |
| A family calendar on every phone | [ioCalendar](../apps/iocalendar.md) |
| Shared task lists, in Apple Reminders too | [ioTask](../apps/iotask.md) |
| The family's recipes, typed in or imported from the web | [ioRecipe](../apps/iorecipe.md) |
| A family address book on every phone and in every mail app | [ioContact](../apps/iocontact.md) |
| Your Apple Health data, kept and charted at home | [ioHealth](../apps/iohealth.md) and the ioHealthSync iPhone app |

## Adding another app later

Install the second app the same way, and give it the **same Shared ioSuite database** (the installer asks for it). From
then on:

- **Everyone already has an account.** The accounts, passwords and app passwords are the Shared ioSuite database's, so
  the new app knows everybody. Each person gets the app's default role there (viewer, unless an admin changes it in
  Settings › Global settings › Apps).
- **One sign-in covers both** when they share a domain: set `COOKIE_DOMAIN=example.com` in each app and a person signed
  in at `photos.example.com` is signed in at `calendar.example.com` too.
- **They find each other.** Every app writes its name, address, version and icon in the suite's list of apps when it
  starts, so nobody types an address into another app.

Nothing about the first app changes, and neither app needs the other to keep running.

## What some apps add to each other

These are extras, switched on by having both apps; neither app needs the other:

| Together | You get |
| --- | --- |
| ioContact + ioCalendar | a read-only **Birthdays** calendar with the birthdays and anniversaries from ioContact; the people on an event are picked from your contacts |
| ioPix + ioContact | link a contact to a person named in ioPix: that face becomes the contact's photo, on phones (CardDAV) and in the LDAP directory too |
| ioStart + any app | a tile per app on the start page with what matters today: the next events, the tasks due, photos from this day, today's steps and last night's sleep |
| ioStart + ioCalendar | "Quick add": type "dinner fri 19:00" in the start page's search box to make the event |
| any two | the same accounts and roles, one admin panel, the same Settings, one sign-in |

## All of them at once

Every installer ends with **"Also install …?"**: tick the other apps and they go in the same machine or container,
each with its own database and port, with the shared answers (database server, Shared ioSuite database, sign-in domain,
admin) asked only once. Or run the [whole-suite Docker stack](docker.md#the-whole-suite-in-one-stack), MariaDB
included. See [Several apps on one host](several-apps.md).

## Removing an app

Stop it and remove it the way you installed it (delete the container, the stack, or the service and its folder). The
other apps don't notice. The app's row stays in the suite's list of apps until a suite admin forgets it under Settings ›
Global settings › Apps, which can also drop the roles, settings, app passwords and keys it kept in the Shared ioStart
database. Its own database is left for you to drop.
