---
description: Run several ioThing apps on one machine or container, or add one later.
---

# Several apps on one host

Every app has its own default port and its own database name, so any number of them can share one machine, one
container or one database server:

| App | Port | Database | Folder (as root) |
| --- | --- | --- | --- |
| ioPix | 8600 | `iopix` | `/opt/iopix/app` |
| ioNote | 8610 | `notes` | `/opt/ionote/app` |
| ioCalendar | 8620 | `calendar` | `/opt/iocalendar/app` |
| ioStart | 8630 | `suite` | `/opt/iostart/app` |
| ioContact | 8640 (LDAP 3890) | `contacts` | `/opt/iocontact/app` |
| ioHealth | 8650 | `health` | `/opt/iohealth/app` |
| ioTask | 8670 | `tasks` | `/opt/iotask/app` |
| ioRecipe | 8690 | `recipe` | `/opt/iorecipe/app` |

## One line: install, add, remove, reconfigure

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash
```

On a new server this sets up ioStart and then shows the list of apps. Run it again at any time: it shows what is
installed. Tick an app to add it, untick one to remove it, type `r` and its number to answer its setup questions again
(port, public address, database...).

Removing an app stops it, deletes its program files and takes it out of the other apps' switchers. **Its database and
its data stay**, so adding it again brings everything back. Deleting those too is a separate question that you answer by
typing `DELETE`; the accounts, the photos and the backups are never touched.

Without questions: `... | bash -s -- --add iotask,ionote`, `--remove iohealth`, `--reconfigure iocalendar`, `--list`.

## How the apps are reached

A new install has every app on its own port, open to your network. In the list, `a` changes that for every app on the
server at once (`--reach` without questions):

| | `--reach` | What it sets |
| --- | --- | --- |
| Each app on its own port | `ports` | how a new install starts: `http://server:8620` for ioCalendar, and so on |
| One address | `one` | the start page answers for every app (`http://server:8630/calendar/`, `…/notes/`); the other apps listen on the server itself only |
| One address behind a reverse proxy on the server | `one-proxy` | the same, and the start page listens on the server itself only too: your Caddy or nginx does HTTPS with one site and one upstream |
| A reverse proxy on the server reaches each app | `proxy` | every app listens on the server itself only; the proxy has an upstream per app |

With `one-proxy` and `proxy` it also asks for the address the suite is at (`--address https://home.example.com`): the
start page's public address and, with `proxy`, every other app's folder of it (`https://home.example.com/calendar`),
for a proxy that serves one name with a folder per app. Leave it empty when each app has a name of its own; those
stay each app's own setting (`r` and its number). It then prints the Caddy site to paste.

```sh
... | bash -s -- --reach one
... | bash -s -- --reach one-proxy --address https://home.example.com
... | bash -s -- --yes --db ... --admin ... --add all --reach one     # a new server, no questions
```

The answer is written as `HOST` in each app's `config.env` and as the suite's one-address switch (Settings › Global
settings › Apps); the apps it changes are restarted, and an app you add later follows the others. ioContact's LDAP
directory is not HTTP and keeps listening where it did. See [Reverse proxy and HTTPS](../run/reverse-proxy.md) for
what each way means and the proxy's side of it.

## From an app's own installer

Whichever app you install first, its installer ends with the same list (`./setup.sh --apps` shows only the list), and
takes the lists as flags:

=== "setup.sh"

    ```sh
    ./setup.sh --also iocalendar,iocontact     # or --also all; --remove iohealth; --reconfigure iotask
    ```

=== "Proxmox VE"

    ```sh
    IOSUITE_ALSO=iocalendar,iocontact \
    bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iostart/proxmox/ct/iostart.sh)"
    ```

    Or tick them in the installer's checklist. ioPix's installer offers all the others; theirs leave out ioPix, whose
    installer is the one that mounts the photo library.

The questions every app shares are asked once: the database server (each app gets its own database on it, so the
database user needs rights on those names too, or give a database administrator), the Shared ioSuite database, the
sign-in domain and the admin. Each companion is fetched from GitHub into `/opt/<app>/app`, installed by its own
`setup.sh`, and gets its own service on its usual port. Afterwards each app updates itself as always.

ioPix installed this way starts without digiKam and without AI features; run its `setup.sh` again to add them.

## An app on another machine

Install the new app on its own, anywhere, and answer the Shared ioSuite database question with the one your other
apps use. That's all it takes for the accounts to be shared. To have one sign-in, give every app the same
`COOKIE_DOMAIN` (see [Reverse proxy and HTTPS](../run/reverse-proxy.md)).

## Docker

See [the whole suite in one stack](docker.md#the-whole-suite-in-one-stack), or run each app's own compose file with the
same `IOSUITE_DB_*` settings.
