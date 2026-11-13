---
description: Install an ioThing app in a Proxmox VE container with one command.
---

# Proxmox VE (LXC)

Every app has a container installer that follows the [community-scripts](https://community-scripts.github.io/ProxmoxVE/)
(ProxmoxVE) framework: the engine comes from community-scripts, the app's install script from its folder of the suite's repository. On
the Proxmox VE host, as root, run the line for the app you want:

| App | Command | Container by default |
| --- | --- | --- |
| ioPix | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iopix/proxmox/ct/iopix.sh)"` | 4 CPU, 4 GB, 16 GB |
| ioNote | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/ionote/proxmox/ct/ionote.sh)"` | 2 CPU, 2 GB, 8 GB |
| ioCalendar | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iocalendar/proxmox/ct/iocalendar.sh)"` | 1 CPU, 512 MB, 4 GB |
| ioStart | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iostart/proxmox/ct/iostart.sh)"` | 1 CPU, 512 MB, 4 GB |
| ioContact | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iocontact/proxmox/ct/iocontact.sh)"` | 1 CPU, 512 MB, 4 GB |
| ioHealth | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iohealth/proxmox/ct/iohealth.sh)"` | 2 CPU, 1 GB, 4 GB |
| ioTask | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iotask/proxmox/ct/iotask.sh)"` | 1 CPU, 512 MB, 4 GB |
| ioRecipe | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iorecipe/proxmox/ct/iorecipe.sh)"` | 1 CPU, 512 MB, 4 GB |

## What it asks

First the app's own questions, then the framework's (resources, network):

1. **The app's database**: host, port, database, user and password (MariaDB or MySQL). ioNote can use a SQLite file in
   the container instead; ioPix can install MariaDB in the container.
2. **The Shared ioSuite database**: the same five answers; database and user `iosuite` by default. Give every app the
   same one.
3. **A MariaDB / MySQL administrator** (optional): with one, the databases and users are created for you.
4. What is particular to the app: the photo folder and digiKam for ioPix, the family's time zone for ioCalendar and ioTask, the
   LDAP port for ioContact, which features to download for ioPix and ioNote...
5. The **public address** behind your reverse proxy and the **domain the sign-in is shared on** (both optional).
6. **The admin account**, used only when the Shared ioSuite database has no accounts yet.
7. **Also install in this container**: a checklist of the other apps. Leave it empty for one app.

It then creates a Debian 13 container (unprivileged, except an ioPix container that may write into your photo library)
and runs the app's own `setup.sh` inside with those answers: packages, settings, tables, admin and the service. The
passwords reach `setup.sh` through its environment, never on a command line. The output is kept in
`/opt/<app>/setup.log`; on a failure the last lines are shown with the command to run it again.

## Unattended

Every question has an environment variable, named after the app, for example for ioCalendar:

```sh
IOCALENDAR_DB=db.lan:3306/calendar:calendar:secret \
IOCALENDAR_SUITE_DB=db.lan:3306/iosuite:iosuite:secret \
IOCALENDAR_ADMIN=alex:secret IOCALENDAR_TIMEZONE=Europe/Brussels \
IOCALENDAR_ALSO=none \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iocalendar/proxmox/ct/iocalendar.sh)"
```

The common ones are `IO<APP>_DB`, `IO<APP>_SUITE_DB` (`host:port/database:user:password`), `IO<APP>_ADMIN`
(`name:password`), `IO<APP>_PORT`, `IO<APP>_PUBLIC_URL`, `IO<APP>_COOKIE_DOMAIN`, `IO<APP>_DB_ADMIN` and
`IO<APP>_ALSO`. Each app's README lists its own.

## Several apps in one container

Tick them in the "Also install" checklist, or set `IO<APP>_ALSO`:

```sh
IOSUITE_ALSO=iocalendar,iocontact \
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iostart/proxmox/ct/iostart.sh)"
```

Every app gets its own database on the same server, its usual port, and the same accounts and admin. ioPix's installer
can take the others into its container; the others' checklists don't offer ioPix, since only its installer mounts
the photo library. See [Several apps on one host](several-apps.md).

## Updating

Inside the container, `update` pulls the latest code of each app and keeps the settings and data. Or use
**Update** in the web app (Settings › Global settings › Updates). See [Updates](../run/updates.md).
