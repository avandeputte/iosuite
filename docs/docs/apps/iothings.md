---
description: ioThings, an inventory of everything you own, in the ioThing suite.
---

# ioThings <small>everything you own</small>

An inventory of everything the family owns and where it is: the appliances, the tools, the furniture, the electronics,
the car, the camping gear and what is stored in the attic, with
their manuals, receipts and warranties, and the upkeep they need (the boiler's yearly service, the car's MOT, the
fridge's water filter). It does what Homebox does, and brings a Homebox inventory over in one step.

[The ioThings page on the website, with more screenshots →](https://iosuite.iothing.net/ioThings/)
{ .md-button }

![ioThings: everything the household owns, by place and label, with upkeep and warranties](../img/iothings.jpg)

## What it does

- **Things** with a name, a description, how many, the maker, model and serial number, an asset id, a link, the
  purchase (when, where, for how much), the warranty (until when, or for life, and its details), whether it is
  insured, notes and fields of their own (filter size, paint colour, the code of the safe).
- **Places** as a tree (House / Kitchen / Drawer by the sink), and **labels** with a colour.
- **Whose it is**: mark a thing as one or more people's of the family (Emma's bike, Dad's laptop); the sidebar's
  Family shows each person's things. The same family, colours and faces as in ioTask and ioCalendar.
- **Files**: photos, manuals, receipts and warranty cards, dropped on the thing or taken with the phone. A PDF is
  kept as a manual and an image as a photo unless you say otherwise. They are kept in the database, so there is
  nothing else to back up.
- **Upkeep**: what a thing needs every so many days, weeks, months or years, and when it is next due. **Done**
  writes a line in the thing's maintenance log (when, by whom, what it cost) and moves the upkeep on.
- **Maintenance log**: the upkeep that was done, and one-off lines for a repair or a part replaced.
- **Warranties**: the ones that end within 30 days, on a page of their own and in the morning notification.
- **Archive** for a thing that was sold, given away or thrown out: it keeps its story, with who it went to and for
  how much.
- **The things as cards or a table**, sorted by name, the newest, the price, when they were bought or when their
  warranty ends; all of them, by place, by label, or found by words in any of their details.
- **Homebox, straight from the server**: give Homebox's address, email and password (used once, not kept) and
  everything comes over: the things, places, labels and fields, the photos, manuals, receipts and warranties, and the
  maintenance log. Running it again brings things up to date instead of adding them twice. The server must reach
  Homebox, so use its address on the home network when it sits behind Cloudflare Access.
- **Homebox's CSV**: Tools › Export inventory in Homebox gives a CSV file; Import and export in ioThings takes it, with its
  places, labels and fields (no files: Homebox's CSV has none). Importing the same file again changes what it brought instead of adding it twice. The
  export writes the same format, so the file also goes back into Homebox.
- **Who may do what**: viewers look; members add things, attach files and keep the upkeep and the log; editors
  change everything, the places and the labels.
- **Everywhere**: a REST API with OpenAPI docs at `/api/docs`, and an MCP server for AI assistants.

## On its own

ioThings is a complete home inventory. It needs its database and the Shared ioSuite database. Upkeep, its log and the
morning notifications work without any other app.

## With the other apps

- **ioStart**: a tile on the start page, the things in the suite's search, and one sign-in for all the apps.
- **ioTask**: an upkeep can also be a repeating task in one of your task lists. It repeats there as it does in
  ioThings. When the task is ticked off in ioTask, ioThings sees the new due day; **Done** in ioThings moves the task on.
- **Linking**: a thing can be linked to events, tasks, notes, contacts, recipes and photos of the other apps (the
  plumber in ioContact, the invoice in ioNote).
- **ioMoney**: link a thing to the transaction that paid for it. The thing then shows what was paid, when and from
  which account; in ioMoney the transaction shows the thing and how long its warranty runs, and keeps the receipt.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iothings/proxmox/ct/iothings.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iothings/docker-compose.yml): the image `ghcr.io/avandeputte/iosuite/iothings` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/iothings && ./setup.sh` |
| Port | 8700 |
| Source | [iosuite/iothings](https://github.com/avandeputte/iosuite/tree/main/iothings) |
