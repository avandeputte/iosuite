---
description: ioBackup, the admin tool of the ioThing suite that backs up and restores the MariaDB databases.
---

# ioBackup <small>admin tool: database backups</small>

Backs up the MariaDB server the apps keep their data on (and any other MariaDB or Galera server), on demand or on a
schedule, to a folder or Google Drive. It keeps the newest few backups of each job and restores exactly what you
pick: whole databases, single tables, users and roles.

!!! note "An admin tool"
    ioBackup is a utility for the person who runs the servers, not an app for the family. Only suite admins can open
    it (a backup holds everybody's data); they find it on the start page and in the app switcher. Nobody else sees it, and
    it takes no roles.

## What it does

- **Servers**: the MariaDB servers to back up and restore onto. *Test* shows the version, whether it is a Galera node,
  and its databases. *The suite's own database server* fills in the address the apps use.
- **Destinations**: a folder (a local disk, a mounted NAS share) or Google Drive (your own account, or a service
  account in a Shared Drive).
- **Backup jobs**: a server, all databases (new ones are picked up by themselves) or a list, with or without users and
  grants, a destination, a schedule (every few hours, daily, weekly, monthly, a cron expression, or on demand only)
  and **how many backups to keep**.
- **Run now** on any job. Every run is in **Activity** with its log, live while it runs, and can be cancelled.
- **Backups**: each destination's backups, to verify (every piece against its checksum), download, delete or restore.
- **Restore what you pick**: whole databases or single tables, views, routines and events, under the same name or a
  new one, with users and roles, onto the same server or another. You review what it would overwrite before you
  confirm.

## What a backup is

One file, `<job>-<date>-<time>.mdbk.tar`: one consistent `mariadb-dump` snapshot of all the job's databases, split
into a gzip file per object so any piece can be restored alone, plus the users, roles and grants, and a manifest with
a SHA-256 of every piece. It is plain SQL inside a plain tar, readable without ioBackup.

If the machine that ran ioBackup is gone, `app/offline.py` restores a backup on any machine with Python 3 and the
MariaDB client, with no web app, database or settings:

```sh
python3 -m app.offline list    Nightly-20261103-020000.mdbk.tar
python3 -m app.offline restore Nightly-20261103-020000.mdbk.tar --all -H db1 -u root -p
```

Server settings (`my.cnf`), plugins and binary logs are not part of a backup. ioBackup's own settings live in its
database (`backup`): include it in a job too.

## Before a restore

Stop the apps whose database you restore over, and start them again after. A restore makes databases, users and
grants, so add the server you restore onto with an administrator's account.

## On its own

ioBackup works without any other app of the suite, for any MariaDB or Galera server. It needs its database, the
Shared ioSuite database for its admin account, and the MariaDB client programs (`setup.sh` installs them, and the
Docker image has them).

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iobackup/proxmox/ct/iobackup.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iobackup/docker-compose.yml): the image `ghcr.io/avandeputte/iosuite/iobackup` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/iobackup && ./setup.sh` |
| Port | 8680 |
| Source | [iosuite/iobackup](https://github.com/avandeputte/iosuite/tree/main/iobackup) |

The [README](https://github.com/avandeputte/iosuite/tree/main/iobackup) covers Galera, Google Drive and the database
privileges a backup user needs.
