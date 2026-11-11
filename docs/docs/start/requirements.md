---
description: What every ioThing app needs to run.
---

# Requirements

## A database server

Every app keeps its data in **MariaDB or MySQL**, in two databases:

| Database | Default name and user | Holds |
| --- | --- | --- |
| the app's own | `iopix`, `notes`, `calendar`, `suite`, `contacts`, `health` or `tasks` | everything the app keeps |
| the **Shared ioSuite database** | `iosuite` | accounts, sessions, roles, app passwords, the suite-wide settings and the list of installed apps |

Both can live on the same server, and the Shared ioSuite database is one per household: every app you install points at
the same one. With a single app, it is simply where that app's accounts are. More in [Databases](../reference/databases.md).

The databases and users don't have to exist beforehand. Every installer asks, right after the database questions, for
a MariaDB / MySQL **administrator** (for example `root`): give one and it creates the app's database and user and the
Shared ioSuite database and user, with the passwords you answered. Nothing is dropped, and the administrator's password
is used once and not written anywhere. Leave it empty when the databases exist already.

To make them yourself instead:

```sql
CREATE DATABASE calendar CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'calendar'@'%' IDENTIFIED BY 'a-good-password';
GRANT ALL ON calendar.* TO 'calendar'@'%';

CREATE DATABASE iosuite CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'iosuite'@'%' IDENTIFIED BY 'another-good-password';
GRANT ALL ON iosuite.* TO 'iosuite'@'%';
```

The tables are created on the first start, and later versions bring them up to date by themselves. The database users
must be allowed to connect from where the app runs (a container has an address of its own).

!!! note "Exceptions"
    **ioNote** can keep its notes in a SQLite file instead (`--sqlite`, for a quick try); its accounts are still in
    the Shared ioSuite database. **ioPix** reads your photos from a folder (and digiKam's database, if you use
    digiKam) and keeps what it builds in its own database and data folder; its Docker stack ships a MariaDB of its own.

## Somewhere to run the app

Pick one; every app offers all three.

| Way | What it takes | Guide |
| --- | --- | --- |
| **Proxmox VE** | a Proxmox VE host. One command creates an unprivileged Debian 13 container and installs the app inside | [Proxmox VE](proxmox.md) |
| **Docker** | Docker with Compose, amd64 or arm64. The images are public on `ghcr.io/avandeputte/` | [Docker](docker.md) |
| **Any Linux or Mac** | Python 3.10 or later (ioHealth: 3.11), git. `setup.sh` makes a virtual environment and a systemd service (launchd on a Mac) | [Any Linux or Mac](linux-mac.md) |

Each app is small: the Proxmox containers for ioCalendar, ioTask, ioRecipe, ioContact, ioNote, ioHealth and ioSuite default to 1 or 2 CPUs and 512 MB to 2 GB of memory. ioPix
is the exception when its AI features are on (content search, faces, objects, text in photos): its container defaults to
4 CPUs and 4 GB, and the models it downloads take a few GB of disk.

## A port per app

Every app has its own default port, so all of them can run on one host:

| ioPix | ioNote | ioCalendar | ioSuite | ioContact | ioHealth | ioTask | ioRecipe |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 8600 | 8610 | 8620 | 8630 | 8640 | 8650 | 8670 | 8690 |

ioContact also serves an LDAP directory, on port 3890 by default (the Proxmox installer offers 389).

## For use outside your home network

A reverse proxy that terminates HTTPS (Caddy, nginx, HAProxy, Traefik) or a Cloudflare Tunnel, and a domain to put the
apps under. Phones want HTTPS for CalDAV and CardDAV accounts away from home. See [Reverse proxy and HTTPS](../run/reverse-proxy.md).
