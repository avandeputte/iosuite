---
description: Run several ioThing apps on one machine or container, or add one later.
---

# Several apps on one host

Every app has its own default port and its own database name, so any number of them can share one machine, one
container or one database server:

| App | Port | Database | Folder (as root) |
| --- | --- | --- | --- |
| ioPix | 8600 | `iopix` | `/opt/iopix/app` |
| ioNotes | 8610 | `notes` | `/opt/ionotes/app` |
| ioCalendar | 8620 | `calendar` | `/opt/iocalendar/app` |
| ioSuite | 8630 | `suite` | `/opt/iosuite/app` |
| ioContacts | 8640 (LDAP 3890) | `contacts` | `/opt/iocontacts/app` |
| ioHealth | 8650 | `health` | `/opt/iohealth/app` |
| ioTasks | 8670 | `tasks` | `/opt/iotasks/app` |
| ioRecipe | 8690 | `recipe` | `/opt/iorecipe/app` |

## "Also install …?"

Whichever app you install first, its installer's last question puts others beside it:

=== "setup.sh"

    ```sh
    ./setup.sh --also iocalendar,iocontacts     # or --also all, or --also none
    ```

=== "Proxmox VE"

    ```sh
    IOSUITE_ALSO=iocalendar,iocontacts \
    bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/proxmox/ct/iosuite.sh)"
    ```

    Or tick them in the installer's checklist. ioPix's installer offers all the others; theirs leave out ioPix, whose
    installer is the one that mounts the photo library.

The questions every app shares are asked once: the database server (each app gets its own database on it, so the
database user needs rights on those names too, or give a database administrator), the Shared ioSuite database, the
sign-in domain and the admin. Each companion is fetched from GitHub into `/opt/<app>/app`, installed by its own
`setup.sh`, and gets its own service on its usual port. Afterwards each app updates itself as always.

ioPix installed this way starts without digiKam and without AI features; run its `setup.sh` again to add them.

## Adding an app to an existing install

Install the new app on its own, anywhere, and answer the Shared ioSuite database question with the one your other
apps use. That's all it takes for the accounts to be shared. To have one sign-in, give every app the same
`COOKIE_DOMAIN` (see [Reverse proxy and HTTPS](../run/reverse-proxy.md)).

## Docker

See [the whole suite in one stack](docker.md#the-whole-suite-in-one-stack), or run each app's own compose file with the
same `IOSUITE_DB_*` settings.
