---
description: ioContacts, contacts for the family in the ioThing suite.
---

# ioContacts <small>contacts</small>

A contact manager for the whole family: a web app, and the standard protocols every mail, contacts and calendar app
already speaks, so the same contacts show up on phones, in Apple Contacts, Outlook, Thunderbird and anywhere else.

![ioContacts with a contact open](../img/iocontacts.jpg)

## What it does

- **Contacts** with every field a phone has: names, any number of phones, emails and addresses, birthdays,
  anniversaries, company, social profiles, websites, labels, notes.
- **Relations** between contacts, kept on both sides (make Tim Mary's son and Mary becomes Tim's mother), and a
  **family tree** laid out by generation.
- **Address books**: the shared Family book, a private Personal one for each account, and more as you like.
- **Clean up**: likely duplicates with the reasons, compare and merge (and undo), data quality checks with one-click
  fixes, and suggestions from public profiles that wait for you to accept them.
- **Everywhere**: CardDAV for Apple Contacts, DAVx⁵ on Android and Thunderbird; vCard 3.0 and 4.0; an LDAP directory
  for mail apps and printers; a family birthday calendar to subscribe to; a REST API.

## On its own

ioContacts is a complete family address book. It needs its database and the Shared ioSuite database, and HTTPS if
phones should sync away from home. The LDAP directory speaks plain LDAP: keep it on the home network.

## With the other apps

- **ioCalendar** shows the birthdays and anniversaries as a Birthdays calendar, and picks the people on an event
  from your contacts.
- **ioPix**: link a contact to a person named in ioPix and that face is the contact's photo, everywhere.
- **ioSuite**: a Birthdays card on the start page, and the search box finds people.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iocontacts/main/proxmox/ct/iocontacts.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iocontacts/blob/main/docker-compose.yml): the image `ghcr.io/avandeputte/iocontacts` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iocontacts && cd iocontacts && ./setup.sh` |
| Port | 8640 (LDAP 3890) |
| Source | [github.com/avandeputte/iocontacts](https://github.com/avandeputte/iocontacts) |
