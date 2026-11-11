---
description: Run an ioThing app, or the whole suite, with Docker Compose.
---

# Docker

Every app is published as a public image for amd64 and arm64:

| App | Image | Compose file |
| --- | --- | --- |
| ioPix | `ghcr.io/avandeputte/iopix` | [docker-compose.yml](https://github.com/avandeputte/iopix/blob/main/docker-compose.yml) (MariaDB included) |
| ioNotes | `ghcr.io/avandeputte/ionotes` | [docker-compose.yml](https://github.com/avandeputte/ionotes/blob/main/docker-compose.yml) |
| ioCalendar | `ghcr.io/avandeputte/iocalendar` | [docker-compose.yml](https://github.com/avandeputte/iocalendar/blob/main/docker-compose.yml) |
| ioSuite | `ghcr.io/avandeputte/iosuite` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/docker-compose.yml) |
| ioContacts | `ghcr.io/avandeputte/iocontacts` | [docker-compose.yml](https://github.com/avandeputte/iocontacts/blob/main/docker-compose.yml) |
| ioHealth | `ghcr.io/avandeputte/iohealth` | [docker-compose.yml](https://github.com/avandeputte/iohealth/blob/main/docker-compose.yml) |
| ioTasks | `ghcr.io/avandeputte/iotasks` | [docker-compose.yml](https://github.com/avandeputte/iotasks/blob/main/docker-compose.yml) |
| ioRecipe | `ghcr.io/avandeputte/iorecipe` | [docker-compose.yml](https://github.com/avandeputte/iorecipe/blob/main/docker-compose.yml) |

## One app

```sh
mkdir iocalendar && cd iocalendar
curl -fsSLO https://raw.githubusercontent.com/avandeputte/iocalendar/main/docker-compose.yml
# fill in the CHANGE ME values: the databases, the admin, the time zone
docker compose up -d
```

The compose files work as a stack in Dockge or Portainer too. Except for ioPix, they expect a MariaDB or MySQL server
you already run; the images hold no data of their own (ioNotes and ioPix keep a small volume for their data folder), so
a container can be replaced at will. Every image comes with a health check.

To share the accounts with apps you run elsewhere, give the container the same `IOSUITE_DB_*` settings as the others.

## The whole suite in one stack

[`docker/suite/docker-compose.yml`](https://github.com/avandeputte/iosuite/blob/main/docker/suite/docker-compose.yml) in
the ioSuite repository starts a MariaDB with a database per app, and ioSuite, ioCalendar, ioTasks, ioRecipe, ioContacts, ioNotes, ioHealth
and ioPix (without digiKam) with one Shared ioSuite database and one admin:

```sh
curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite/main/docker/suite/docker-compose.yml
# set the passwords, the photos folder and the time zone at the top, then
docker compose up -d
```

Remove the services you don't want; the rest keep working.

## Updating

```sh
docker compose pull && docker compose up -d
```

In a container, pulling the image takes the place of the web app's **Update now**. Released versions are tagged as
well, if you'd rather pin one than follow `latest`.
