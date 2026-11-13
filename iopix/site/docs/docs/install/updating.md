# Updating

## From the app

iopix is part of the ioThing suite, which has one version, the same for every app. **Settings › Global settings › Updates** (suite admins) shows the installed version and the newest one. **Update** installs it and restarts iopix, together with any other app of the suite you run; **Check now** looks again. The page follows along and reloads when the new version is up. **Settings › Server** shows the version iopix runs.

With **Check for a new version daily** on (the default), iopix asks once a day whether a newer version exists. Only the public list of versions is fetched; nothing about your install is sent. `UPDATE_CHECK=0` turns this off for good.

## From the command line

| Install | Command |
| --- | --- |
| Docker | `docker compose pull && docker compose up -d` |
| Proxmox container | `update` inside the container |
| Linux installer | `/opt/iopix/app/update.sh` |
| setup.sh checkout | `./update.sh` in the checkout |

`update.sh` fetches the new version, installs any new packages **before** switching over (so a failed install leaves the running version alone), keeps `config.env`, the data folder and the Python environment, and restarts the service.

| Option | Does |
| --- | --- |
| `--check` | only reports whether a newer version exists |
| `--force` | reinstalls even when nothing is newer |
| `IOPIX_REF=<commit>` | installs that exact version |

## Database changes

When a new version needs a different shape for iopix's own database, it converts it on the first start, after writing a dump to `db-backups/` in the data folder. digiKam's database is never changed by an update.

!!! note "Upgrading from a version before 1.113"
    From 1.113 iopix's own data lives on a MariaDB or MySQL server instead of the `viewer.db` file. After the update iopix shows a set-up page asking for a database and offers to import the file. See [iopix's own database](../connect/iopix-database.md).
