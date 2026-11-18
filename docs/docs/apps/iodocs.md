---
description: ioDocs, the family's passports, licenses, policies and certificates, in the ioThing suite.
---

# ioDocs <small>the family's papers</small>

A home for the family's papers: passports, ID cards, driver's licenses, visas, insurance policies, the car's
registration, birth and marriage certificates, wills and health cards. Each with its scans, who it belongs to, its
number and dates, and a reminder early enough to renew it. Drop a scan or a photo and ioDocs reads it, on your own
server, and fills the document in.

[The ioDocs page on the website, with more screenshots →](https://iosuite.iothing.net/ioDocs/)
{ .md-button }

![ioDocs: the family's documents, the soonest to expire first](../img/iodocs.jpg)

## What it does

- **Documents** of a kind (passport, passport card, ID card, driver's license, visa, residence permit, insurance
  policy, vehicle registration, health and vaccination, birth and marriage certificates, property, will and legal
  papers, tax, diplomas, memberships and cards), each with its number, issuer, country, the day it was issued and
  the day it expires, notes, and fields of your own (a policy's deductible, the agent's phone).
- **Scans and files**: the photo page, both sides of a card, a policy's PDF. Kept in the database, so there is
  nothing else to back up.
- **Reading scans**, on the server with Tesseract (no scan leaves it):
    - a passport's or ID card's **machine-readable lines** (the ‹‹‹ at the bottom of the photo page) give the kind, the
      number, the country, the name, the birth date and the expiry, each checked against its check digit;
    - the **barcode on the back of a US or Canadian driver's license** gives the number, the state, the dates, the
      address and the class, exactly;
    - anything else is read as text, for its number, its dates ("Policy period 01/01/2026 to 01/01/2027", "EXP") and its
      kind. The words read off a scan are found by the search, too.

    What is read fills in the fields still empty. Where a scan says otherwise than what you wrote, it is offered, to
    take or leave; nothing you wrote is overwritten.
- **Whose it is**: the family members it is for, from the suite's one family list, or none for the household's own
  (the home insurance). The sidebar's Family shows each person's documents.
- **To renew**: what has expired or comes within its reminder (each kind has its usual one, a passport nine months
  ahead and a policy one month; a document can have its own, or none), on a page of its own and in the morning
  notification to the document's people.
- **Renew**: the new one in place of the old one, which is archived and linked to it.
- **Who sees what**, per document: the whole family, its people and the grown-ups (the usual), or only its people (a
  will). New accounts have no role in ioDocs until an admin gives them one. Viewers look; members add documents and
  change their own; editors change everything they see.
- **The number masked** until Show, with Copy.
- **Everywhere**: a REST API with OpenAPI docs at `/api/docs`, and an MCP server for AI assistants.

## On its own

ioDocs needs its database and the Shared ioSuite database, and Tesseract on the server to read scans (`setup.sh`,
the Proxmox script and the Docker image install it). Reminders and their notifications work without any other app.

## With the other apps

- **ioCalendar**: the day each document expires shows on the calendar, for the people who see that document.
- **ioStart**: a *To renew* tile, the documents in the suite's search, and one sign-in for all the apps.
- **Linking**: a document can be linked to events, tasks, notes, contacts, things and transactions of the other apps
  (the car's registration to the car in ioThings, the policy to the insurer in ioContact).

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iodocs/proxmox/ct/iodocs.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iodocs/docker-compose.yml): the image `ghcr.io/avandeputte/iosuite/iodocs` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/iodocs && ./setup.sh` |
| Port | 8720 |
| Source | [iosuite/iodocs](https://github.com/avandeputte/iosuite/tree/main/iodocs) |
