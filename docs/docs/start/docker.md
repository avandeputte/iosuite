---
description: Run an ioThing app, or the whole suite, with Docker Compose; the builder that writes the stack file for you.
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
| ioThings | `ghcr.io/avandeputte/iosuite/iothings` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iothings/docker-compose.yml) |
| ioMoney | `ghcr.io/avandeputte/iosuite/iomoney` | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iomoney/docker-compose.yml) |

## Build your stack

The [Docker Compose builder](https://iosuite.iothing.net/compose/) asks which apps you want, whether MariaDB goes in
the stack or you already run a server, the first admin, and how the suite is reached (one address or one per app,
plain HTTP, a Caddy container that gets the certificates, or your own reverse proxy). It writes one
`docker-compose.yml` with nothing left to edit:

```sh
docker compose up -d
docker compose logs setup     # what was set up; it ends with ok
```

The file's `setup` service runs before the apps at every start (`iosuite-shared stack`, which every image holds): it
makes the databases and users that are missing, the first admin, and writes how the suite is reached into the Shared
ioSuite database (the one-address switch and the reverse proxy addresses), so there is nothing to click afterwards.
What a suite admin changes under Settings later stays until the file says something new. The page works in your
browser alone: nothing you type is sent anywhere. To add or remove an app later, open your file on the page again;
it holds its own answers. Ticking *Fill it with demo data* adds a made-up family with something in every app
([Demo data](demo.md)).

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

The builder above writes this for your own answers. By hand:

[`docker-compose.yml`](https://github.com/avandeputte/iosuite/blob/main/docker-compose.yml) in
the ioSuite repository starts a MariaDB with a database per app, and ioStart, ioCalendar, ioTask, ioRecipe, ioThings, ioMoney, ioContact, ioNote, ioHealth
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
