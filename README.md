# ioSuite

*The ioThing suite: self-hosted apps for the family, with one sign-in.*

Every app is a folder of this repository. Each one installs and runs on its own, or together with the others; an
app that finds the others shows them in its app switcher and works with them. They share one set of accounts (the
Shared ioSuite database) through the library in [`shared/`](shared/).

| Folder | App | What it is | Port |
|---|---|---|---|
| [`iostart/`](iostart/) | ioStart | the start page: a tile per app, bookmarks | 8630 |
| [`iopix/`](iopix/) | ioPix | the photo library, with or without digiKam | 8600 |
| [`ionote/`](ionote/) | ioNote | notes | 8610 |
| [`iocalendar/`](iocalendar/) | ioCalendar | the family calendar, CalDAV | 8620 |
| [`iocontact/`](iocontact/) | ioContact | contacts, CardDAV | 8640 |
| [`iohealth/`](iohealth/) | ioHealth | health data from the iPhone | 8650 |
| [`iotask/`](iotask/) | ioTask | task lists, CalDAV for reminders apps | 8670 |
| [`iorecipe/`](iorecipe/) | ioRecipe | recipes | 8690 |
| [`iodns/`](iodns/) | ioDNS | admin tool: the DNS console | 8660 |
| [`iobackup/`](iobackup/) | ioBackup | admin tool: database backups | 8680 |
| [`shared/`](shared/) | iosuite-shared | the library every app uses: accounts, sign-in, roles, updates, the installer | |
| [`docs/`](docs/) | | the website, [iosuite.iothing.net](https://iosuite.iothing.net) | |

The iPhone, iPad, Mac and Apple TV apps are in [iosuite-apps](https://github.com/avandeputte/iosuite-apps).

## Install

**The suite on one server, one line.** On a Linux server with a MariaDB or MySQL database within reach:

```sh
curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/install.sh | bash
```

The first time it sets up ioStart (the start page) by asking its questions, then shows the list of apps to tick the
others; they share the database server, the Shared ioSuite database, the sign-in domain and the admin. **Run the same
line again at any time** to change what is on the server:

```
   1 [x] ioStart     iostart     port 8630  this app
   2 [x] ioCalendar  iocalendar  port 8620  installed
   3 [ ] ioContact   iocontact   port 8640
   ...
Numbers or names to tick or untick (e.g. 3 5), r and a number to change an installed app's settings (e.g. r2), Enter when it is right:
```

* **Tick** an app to add it.
* **Untick** an app to remove it: its service and program files go, and it leaves the other apps' switchers. Its
  database and its data stay, so adding it again later brings everything back. Deleting them as well is a separate
  question (type `DELETE`); the Shared ioSuite database (accounts, roles, keys), the photos and the backups are never
  touched.
* **`r` and the number** asks an installed app's setup questions again, the current answers as the defaults (port,
  public address, database, the app's own settings), and restarts it.
* **`a`** changes how every app is reached: each on its own port (how a new install starts), all at the start page's
  address in a folder each (`http://server:8630/calendar/`), or behind a reverse proxy on the server, with the apps
  listening on the server itself only. `--reach ports|one|one-proxy|proxy` and `--address URL` do it without questions.

Without questions: `... | bash -s -- --add iotask,ionote`, `--remove iohealth` (`--delete-data` to drop its database
and data too), `--reconfigure iocalendar`, `--list`; `--into DIR` when the apps are not in `/opt`. A first install
without questions passes the first app's `setup.sh` flags: `... | bash -s -- --yes --db HOST:3306/suite:suite:PASSWORD
--admin NAME:PASSWORD --db-admin root:PASSWORD --add all`. In an app's folder, `./setup.sh --apps` shows the same
list, and `./setup.sh --also`, `--remove` and `--reconfigure` take the same lists.

Each app's README has the details of the other ways; they are the same in every app.

**One app, on any Linux or Mac.** Python 3.10+ and a MariaDB or MySQL database:

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iocalendar
./setup.sh
```

`setup.sh` asks for the database, makes the Python environment in the app's folder, installs the shared library from
`shared/` and offers a service. It ends with the list of apps above, to add others beside it
(`./setup.sh --also iotask,ionote` without questions).

**The whole suite in Docker.** [`docker-compose.yml`](docker-compose.yml) here starts MariaDB and every app:

```sh
curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite/main/docker-compose.yml
docker compose up -d     # edit the CHANGE ME spots first
```

**One app in Docker.** The `docker-compose.yml` in the app's folder; the images are `ghcr.io/avandeputte/iosuite/<app>`.

**Proxmox.** One container per app:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iocalendar/proxmox/ct/iocalendar.sh)"
```

## Update

The suite has one version, the same for every app. Settings › Global settings › Updates (suite admins, in any app)
shows it against the newest one on GitHub and updates every app with one button; the start page tells suite admins
when a newer version is out. From a shell: `./update.sh` in an app's folder. Docker:
`docker compose pull && docker compose up -d`.

## Develop

```
<app>/app/            the FastAPI service
<app>/static/         the web app
<app>/tests/          pytest; a MariaDB at IOSUITE_TEST_DB for the tests that need one
<app>/setup.sh, run.sh, update.sh, Dockerfile, docker-compose.yml, proxmox/
shared/               the library (package iosuite_shared), its tests, and templates/ for the files every app has
.github/workflows/    one workflow per app, run when the app's folder or shared/ changes
```

In a checkout an app uses `../shared` as it is (`pip install -e ../shared`), so a change to the library is tested
with every app in the same pull request. `update.sh` is the same in every app, made from
`shared/templates/update.sh` by `shared/templates/render-update.py`.

The suite has one version, `__version__` in `shared/iosuite_shared/__init__.py`; every app reports it. Bump that one
line with every change that reaches users, whichever app it is in. On main, a new version becomes the release
`v<version>` and every app's image is tagged `v<version>` (and `latest`).

## License

GPL-3.0-or-later; see [LICENSE](LICENSE).
