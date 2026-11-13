---
description: Run an ioThing app, or the whole suite, with Docker Compose.
---

# Docker

Every app is published as a public image for amd64 and arm64:

| App | Image | Compose file |
| --- | --- | --- |
| ioPix | `ghcr.io/avandeputte/iosuite/iopix` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iopix/docker-compose.yml) (MariaDB included) |
| ioNote | `ghcr.io/avandeputte/iosuite/ionote` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/ionote/docker-compose.yml) |
| ioCalendar | `ghcr.io/avandeputte/iosuite/iocalendar` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iocalendar/docker-compose.yml) |
| ioStart | `ghcr.io/avandeputte/iosuite/iostart` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iostart/docker-compose.yml) |
| ioContact | `ghcr.io/avandeputte/iosuite/iocontact` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iocontact/docker-compose.yml) |
| ioHealth | `ghcr.io/avandeputte/iosuite/iohealth` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iohealth/docker-compose.yml) |
| ioTask | `ghcr.io/avandeputte/iosuite/iotask` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iotask/docker-compose.yml) |
| ioRecipe | `ghcr.io/avandeputte/iosuite/iorecipe` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iorecipe/docker-compose.yml) |

## One app

```sh
mkdir iocalendar && cd iocalendar
curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite/main/iocalendar/docker-compose.yml
# fill in the CHANGE ME values: the databases, the admin, the time zone
docker compose up -d
```

The compose files work as a stack in Dockge or Portainer too. Except for ioPix, they expect a MariaDB or MySQL server
you already run; the images hold no data of their own (ioNote and ioPix keep a small volume for their data folder), so
a container can be replaced at will. Every image comes with a health check.

To share the accounts with apps you run elsewhere, give the container the same `IOSUITE_DB_*` settings as the others.

## The whole suite in one stack

[`docker-compose.yml`](https://github.com/avandeputte/iosuite/blob/main/docker-compose.yml) in
the ioSuite repository starts a MariaDB with a database per app, and ioStart, ioCalendar, ioTask, ioRecipe, ioContact, ioNote, ioHealth
and ioPix (without digiKam) with one Shared ioSuite database and one admin:

```sh
curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite/main/docker-compose.yml
# set the passwords, the photos folder and the time zone at the top, then
docker compose up -d
```

Remove the services you don't want; the rest keep working.

## Updating

```sh
docker compose pull && docker compose up -d
```

In a container, pulling the image takes the place of the web app's **Update**. Every version of the suite is tagged
as well (`v3.0.0`, the same tag on every app's image), if you'd rather pin one than follow `latest`.
