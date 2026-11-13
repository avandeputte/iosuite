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

Each app's README has the details; the ways are the same in every app.

**One app, on any Linux or Mac.** Python 3.10+ and a MariaDB or MySQL database:

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iocalendar
./setup.sh
```

`setup.sh` asks for the database, makes the Python environment in the app's folder, installs the shared library from
`shared/` and offers a service. `./setup.sh --also iotask,ionote` installs other apps beside it, with the same
database server, sign-in domain and admin.

**The whole suite in Docker.** [`docker-compose.yml`](docker-compose.yml) here starts MariaDB and every app:

```sh
curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite/main/docker-compose.yml
docker compose up -d     # edit the CHANGE ME spots first
```

**One app in Docker.** The `docker-compose.yml` in the app's folder; the images are `ghcr.io/avandeputte/<app>`.

**Proxmox.** One container per app:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iocalendar/proxmox/ct/iocalendar.sh)"
```

## Update

Settings › Server › Update now in the app, or `./update.sh` in its folder. An app is updated when its own version or
the shared library's is newer; both always come from the same commit. Settings › Global settings › Updates on a
suite admin's page updates every app at once. Docker: `docker compose pull && docker compose up -d`.

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

Versions are per app (`<app>/app/__init__.py`, `shared/iosuite_shared/__init__.py`); a release is the tag
`<app>-v<version>`, which publishes the app's image.

## License

GPL-3.0-or-later; see [LICENSE](LICENSE).
