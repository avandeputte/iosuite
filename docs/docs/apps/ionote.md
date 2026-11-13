---
description: ioNote, notes, clipboard snippets and screenshots in the ioThing suite.
---

# ioNote <small>notes</small>

Your notes, clipboard snippets and screenshots, searchable everywhere. The server keeps them in its database, pictures
included, and gives you a web app; the **ionote apps for Mac, iPhone and iPad** keep a full copy and sync with it.

![ioNote with folders, tags and a note open](../img/ionote.jpg)

## What it does

- **Notes** with a title, text, tags, a folder, a pin and optionally a picture (a screenshot, a photo) with the text read
  from it.
- **Search** every word you type, in titles, text, tags and the text inside pictures, through MariaDB's full-text index.
- **Web app**: folders and tags in the sidebar, editing that saves as you type, pictures pasted or dropped anywhere
  become notes, a change log, trash, import and export.
- **On the Mac**: everything you copy and every screenshot lands in an Inbox on that Mac; keep what is worth keeping
  as a note. Right-click › Save to ionote in any app. On the **iPhone and iPad**: the same notes, paste and photos.
- **Offline**: the apps work without the server and send their changes when it is back.
- **Private**: every note belongs to the account that made it; nobody else sees it, admins included.

## On its own

ioNote is a complete notes app. It needs its database (MariaDB or MySQL, or a SQLite file for a quick try) and the
Shared ioSuite database for its accounts. Text recognition for pictures added in the web app is optional (RapidOCR,
about 60 MB); the Mac and iPhone read the text on the device.

## With the other apps

- **ioStart**: the start page's search box searches your notes.
- The same accounts and sign-in as every other app.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/ionote/proxmox/ct/ionote.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/ionote/docker-compose.yml): the image `ghcr.io/avandeputte/iosuite/ionote` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/ionote && ./setup.sh` |
| Port | 8610 |
| Source | [ionote](https://github.com/avandeputte/iosuite/tree/main/ionote) (server), [ionote-apps](https://github.com/avandeputte/iosuite-apps/tree/main/ionote) (Mac, iPhone, iPad) |

The Mac and iPhone apps are built from [ionote-apps](https://github.com/avandeputte/iosuite-apps/tree/main/ionote) with Xcode. See
[Phones, Macs and other apps](devices.md).
