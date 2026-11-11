---
description: ioPix, the photo app of the ioThing suite.
---

# ioPix <small>photos</small>

A web app for a photo library, for browsing, searching and managing photos from any browser. It started as a web
companion for a [digiKam](https://www.digikam.org) library, and works just as well without digiKam: point it at a
folder of photos and it keeps the library itself.

![ioPix Explore: library totals, photos from this day in past years and a shuffle of older ones](../img/iopix-explore.jpg)

**The full ioPix guide is at [iopix.net](https://iopix.net/docs/)**; this page is the short version.

## What it does

- **Browse** by date, folder, album, person, place and tag; a viewer with an info panel (rating, caption, faces,
  tags, location); a map of every geotagged photo; places worked out offline from GPS positions.
- **Search** by what is in the photos (content search), by text in them, by objects and faces, with models that run on
  your own server. Each feature is optional and downloads its model when you turn it on.
- **Edit** ratings, titles, captions, tags, dates, locations and faces, written to sidecars or into the files, the way
  digiKam writes them, with an edit log and undo for every change.
- **People**: name the faces in your photos; with ioContact, a person can be a contact's photo.

![The ioPix viewer with its info panel](../img/iopix-viewer.jpg)

## On its own

ioPix is a complete photo app. It needs the photos (a folder, read-only unless you turn on editing), a MariaDB or MySQL
database for what it builds, and the Shared ioSuite database for its accounts. digiKam is optional.

## With the other apps

- **ioContact** can link a contact to a person named in ioPix; the face becomes the contact's photo.
- **ioSuite** shows photos taken on this day in earlier years on the ioPix tile, and a strip of photos under the
  tiles.
- The start page's search box searches ioPix too.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iopix/main/proxmox/ct/iopix.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iopix/blob/main/docker-compose.yml): the image `ghcr.io/avandeputte/iopix`, with a MariaDB service |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iopix && cd iopix && ./setup.sh` |
| Port | 8600 |
| Source | [github.com/avandeputte/iopix](https://github.com/avandeputte/iopix) |

The Proxmox installer bind-mounts the photo folder (and digiKam's database folder) into the container. See
[iopix.net › Install](https://iopix.net/docs/) for digiKam on SQLite or MariaDB, the AI models and the album roots.
