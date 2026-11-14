# ioBackup

*The database backups of the ioThing suite ([ioStart](https://github.com/avandeputte/iosuite/tree/main/iostart), [ioCalendar](https://github.com/avandeputte/iosuite/tree/main/iocalendar),
[ioContact](https://github.com/avandeputte/iosuite/tree/main/iocontact), [ioNote](https://github.com/avandeputte/iosuite/tree/main/ionote), [ioPix](https://github.com/avandeputte/iosuite/tree/main/iopix),
[ioHealth](https://github.com/avandeputte/iosuite/tree/main/iohealth), [ioTask](https://github.com/avandeputte/iosuite/tree/main/iotask), [ioDNS](https://github.com/avandeputte/iosuite/tree/main/iodns)).*

Backs up the MariaDB server the suite's apps keep their data on (and any other MariaDB or Galera server) on demand or
on a schedule, to a folder or Google Drive, keeps the newest *N* backups of each job, and **restores exactly what you
pick**: whole databases, single tables or views, stored routines, events, users and roles, onto the same server or
another, under the same name or a new one. An admin tool of the suite, for suite admins only: the gear menu of the
ioSuite start page lists it for them, nobody else sees it. FastAPI and a single-page vanilla JS app, built the same
way as the other io apps, signed in with the suite's shared accounts ([`iosuite-shared`](https://github.com/avandeputte/iosuite/tree/main/shared)),
with its own settings in MariaDB / MySQL. It grew out of [mariadb-backup](https://github.com/avandeputte/mariadb-backup),
whose backup files it reads and writes unchanged.

## What it does

- **Servers**: the MariaDB servers to back up and restore onto, by host and port or a socket on the same machine.
  *Test* shows the version, whether it is a Galera node and in which state, and its databases. *The suite's own
  database server* fills in the address the apps use.
- **Destinations**: a folder (a local disk, a mounted NAS share) or Google Drive (your own account with a device code,
  or a service account in a Shared Drive).
- **Backup jobs**: a server, *all databases* (new ones are picked up by themselves) or a list, with or without users and
  grants, a destination, a schedule (every few hours, daily, weekly, monthly, a cron expression, or on demand only) and
  **how many backups to keep**: after each good backup the older ones of that job beyond that number are deleted
  from the destination; 0 keeps them all.
- **Run now** on any job, or wait for the schedule. Every run, scheduled or by hand, is in **Activity** with its log,
  live while it runs, and can be cancelled.
- **Backups**: each destination's backups, to verify (every piece against its checksum), download, delete, or
  **restore**: tick databases (everything, or pick tables, views, routines, events), optionally under another name,
  tick users and roles, pick the server and the options (structure only, replace existing users, carry on past
  errors), review what it would overwrite there, and confirm.

Access: suite admins only (a backup holds everybody's data). Everybody else has no access, whatever role or default
role says, and ioBackup takes no roles. The servers' passwords and the Google
keys are kept with the suite's keys and tokens (start page: Settings › Global settings › Keys and tokens), never shown
back.

## What a backup is

One file, `<job>-<YYYYmmdd-HHMMSS>.mdbk.tar`, holding:

* one consistent `mariadb-dump --single-transaction` of all the job's databases (one snapshot across them), split into
  a gzip file per object so any piece can be restored on its own;
* `accounts.json`: every user (`SHOW CREATE USER`) and role with its grants;
* `manifest.json`: what is in it, the source server and its version, and a SHA-256 of every piece.

It is plain SQL inside a plain tar, readable without ioBackup, and `app/offline.py` restores it on any machine with
Python 3 and the MariaDB client, with no web app, database or settings (for when the machine that ran ioBackup is gone):

```sh
python3 -m app.offline list    Nightly-20261103-020000.mdbk.tar
python3 -m app.offline verify  Nightly-20261103-020000.mdbk.tar
python3 -m app.offline restore Nightly-20261103-020000.mdbk.tar --all -H db1 -u root -p
python3 -m app.offline restore Nightly-20261103-020000.mdbk.tar --db notes.nts_notes --rename notes=notes_old -H db1 -u root -p
python3 -m app.offline restore Nightly-20261103-020000.mdbk.tar --db notes --sql-out notes.sql   # just write the SQL
```

The `mysql` system database is not dumped; users, roles and grants are exported logically instead, which is what moves
cleanly between versions and servers. Server settings (`my.cnf`), plugins and binary logs are not part of a backup.
ioBackup's own settings live in its database (`backup`): back that up too, with any job on the same server.

## Galera

* Back up from one node. With *take this node out of flow control* on (the job's more options), the node sets
  `wsrep_desync=ON` while it dumps, so a long dump does not hold the cluster back, and turns it off again afterwards,
  also when the backup fails. The user then needs `SUPER`.
* Only InnoDB is covered by the snapshot and replicated by Galera; tables in other engines are named in the run's log
  and in the server's test.
* Dumps are taken with `--skip-add-locks`, so a restore never issues `LOCK TABLES`. Restore onto any one node: tables,
  rows, users and grants replicate to the rest of the cluster.

## Google Drive

**Your Google account.** Once, in the [Google Cloud console](https://console.cloud.google.com/): make (or pick) a
project, turn on the **Google Drive API**, set up the OAuth consent screen (External; add yourself as a test user, or
publish it) and make an **OAuth client ID** of the type **TVs and Limited Input devices**. In ioBackup, add a Google
Drive destination with that client ID and secret and a folder name, then **Sign in with Google**: open the address
shown on any device and type the code. ioBackup asks only for `drive.file`: it sees the folder and files it makes and
nothing else in your Drive. A consent screen left in *Testing* gives sign-ins that Google ends after 7 days: publish it
(`drive.file` needs no verification).

**A service account**, for a Google Workspace Shared Drive: make a service account and a JSON key, add the service
account to the Shared Drive as a Content manager, and give the ID of a folder in it. A service account has no storage
of its own, so a folder in a personal My Drive does not work.

Uploads are resumable and retried; a restore from Drive downloads the backup first (`CACHE_DIR`).

## Privileges

For backups:

```sql
CREATE USER 'backup'@'app-host' IDENTIFIED BY '...';
GRANT SELECT, SHOW VIEW, TRIGGER, EVENT, LOCK TABLES, SHOW DATABASES ON *.* TO 'backup'@'app-host';
-- Galera desync also needs: GRANT SUPER ON *.* TO 'backup'@'app-host';
```

`app-host` is the machine the app runs on (`localhost` when MariaDB is on the same machine); a user for any host (`'%'`)
with a password someone could guess is what to avoid. The installers make the user this way when given a MariaDB administrator.

A restore makes databases, users and grants: add the server you restore onto with an administrator's account (root…).
Stop the apps whose database you restore over, and start them again after.

## Run

ioBackup needs Python 3.10+, the MariaDB client programs (`mariadb-dump`, `mariadb`; `setup.sh` installs them) and a MariaDB or MySQL
database for its own settings. Give it its own database and user, for example:

```sql
CREATE DATABASE backup CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'backup'@'app-host' IDENTIFIED BY 'a-long-random-password';
GRANT ALL ON backup.* TO 'backup'@'app-host';
```

The accounts and the suite-wide settings live in the Shared ioSuite database (`iosuite`, user `iosuite`; the one every
app of the suite uses). The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iobackup.sh` and `proxmox/install/iobackup-install.sh` follow the community-scripts (ProxmoxVE) framework
layout, as the other io apps do. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iobackup/proxmox/ct/iobackup.sh)"
```

It asks for the ioBackup database, the Shared ioSuite database, the web port (8680), the time zone, the public address
behind your reverse proxy (optional), the domain the sign-in is shared on (optional), the admin account and which other
apps of the suite go in the same container, then runs the app's own `setup.sh` inside. For unattended runs set
`IOBACKUP_DB` and `IOBACKUP_SUITE_DB` (`host:port/db:user:password`), `IOBACKUP_ADMIN` (`name:password`), `IOBACKUP_PORT`,
`IOBACKUP_PUBLIC_URL` and `IOBACKUP_COOKIE_DOMAIN`. Local backups go to `/var/backups/iobackup` in the container: mount a
disk or a NAS share there (`pct set <id> -mp0 /mnt/backups,mp=/var/backups/iobackup`) so they do not live on the same
disk as the database.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iosuite/iobackup`) has the MariaDB client in it; mount the folder local backups go to at
`/backups`, and `/data` for the work space a backup is put together in.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iobackup
./setup.sh          # asks for the databases, port and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

`setup.sh` takes the same flags as in every app of the suite (`--db`, `--suite-db`, `--admin`, `--port`,
`--public-url`, `--cookie-domain`, `--db-admin`, `--also`, `--service`, `--yes`); `--also` installs other apps of the
suite beside it. From a shell: `python -m app.cli jobs`, `run JOB` (a backup now, without the web app), `runs`.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment,
which wins. The names are the suite's (`DB_*`, `IOSUITE_DB_*`, `PUBLIC_URL`, `COOKIE_DOMAIN`, `HOST`, `PORT`,
`TLS_*`, `TZ`, `ADMIN_USER` / `ADMIN_PASSWORD`, `UPDATE_CHECK`, `DATA_DIR`, `LOG_FILE`), plus:

| Setting | Meaning |
| --- | --- |
| `BACKUP_DIR` | the folder a new local destination suggests (`/var/backups/iobackup`; `/backups` in Docker) |
| `WORK_DIR` | where a backup is put together before it is stored; room for two compressed backups (`DATA_DIR/work`) |
| `CACHE_DIR` | where a backup read from Google Drive is kept while it is restored (`DATA_DIR/cache`) |
| `BACKGROUND` | `0` turns the queue and the scheduler off (nothing runs, no schedule fires) |
| `IOBACKUP_REPO`, `IOBACKUP_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iosuite`, `main`) |

Schedules run in `TZ` (or the host's time zone). The servers, destinations and jobs are set in the app itself.

## API

Everything the web app does is a JSON API under `/api/` (documented at `/api/docs`), open to any client signed in with
the user name and an app password (HTTP Basic or a bearer token): `GET /api/overview`, `POST /api/jobs/<id>/run`,
`GET /api/runs`, `GET /api/runs/<id>` (with its log), `GET /api/destinations/<id>/backups`,
`POST /api/destinations/<id>/backups/<name>/verify`, `POST .../preview` and `POST .../restore` (`{serverId, plan}`).

## Tests

```sh
pip install -e ".[test]"
IOSUITE_TEST_DB=127.0.0.1:3306:root:root python -m pytest -q tests
IOBACKUP_TEST_DB_HOST=127.0.0.1 IOBACKUP_TEST_DB_USER=root IOBACKUP_TEST_DB_PASSWORD=root tests/integration.sh
```

The dump splitting, the schedules and Google Drive (against a stand-in of its API) are tested without a database; the
API tests need a MariaDB (a Docker container, or the server `IOSUITE_TEST_DB` names) and the MariaDB client, and take
real backups of scratch databases there and restore them. `tests/integration.sh` loads a fixture with every kind of
object, backs it up, drops everything, restores it and compares.

## License

GPL-3.0-or-later.
