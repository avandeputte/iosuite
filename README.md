# ioSuite

*The start page of the iothing suite: one place with every io app ([ioPix](https://github.com/avandeputte/iopix),
[ioHealth](https://github.com/avandeputte/ioHealth), [ioCalendar](https://github.com/avandeputte/iocalendar),
[ioContacts](https://github.com/avandeputte/iocontacts), [ioNotes](https://github.com/avandeputte/ionotes)).*

A self-hosted home page for the family: a tile per app, signed in with the suite's shared accounts (`iothing-auth`), so
one sign-in here is a sign-in everywhere the page links to. FastAPI and a single-page vanilla JS app, built the same
way as the other io apps, with its few settings in MariaDB / MySQL. For now the tiles are links; each one keeps room for
what the app will show on the start page later (today's events, the newest photos, last night's sleep…).

## What it does

- **A tile per app**, with the app's own icon and colours, that opens it. The address of each app comes from the
  environment (`IOPIX_URL` and friends), from **Settings › Apps** (admins), or, failing both, from the host the page was
  opened on with the app's usual port (the one-box install): `http://<this host>:8600` for ioPix, `47800` ioHealth,
  `8620` ioCalendar, `8610` ioContacts and ioNotes. An app can be taken off the page in Settings.
- **A search box** at the top (⌘K / Ctrl-K): as you type it lists the bookmarks that match, the people ioContacts
  finds, and a row per app that searches itself (ioPix, ioCalendar and ioNotes open on their own results). Arrows
  pick a row, Enter opens it.
- **A dot by each app's name**: green when the app answers its `/api/status`, red when it does not, and an "update"
  badge when the app tells the viewer (an admin there) that a newer version is out. Bookmarks the server cannot
  reach get a red dot too. The server asks each app once a minute and pings each bookmark every five.
- **Your own page** (the account menu › Customize the page): untick the tiles and cards you do not need, order the
  tiles, and pick your own photo strip. Saved per account, on top of what the admin set in Settings › Apps.
- **The week ahead** under the tiles: a Birthdays card from ioContacts (birthdays and anniversaries in the next 30
  days, with the contact's photo; a row opens the contact) and a This week card from ioCalendar (the coming seven
  days' events, day by day; a day opens in ioCalendar). Each stands no taller than the row of tiles, with "Show all"
  when there is more. With the Birthdays card on the page, the calendar's own "X's birthday" and anniversary events
  are left to it (the tile's Today and This week skip them). A card that its app cannot fill is left out.
- **A strip of photos** the width of the page under the tiles: ioPix's Rediscover (photos at random), or
  On this day; an admin picks which, or turns it off, in Settings › Apps.
- **A glimpse of each app on its tile**: ioPix shows photos taken on this day in earlier years (one per year, "3 years
  ago"), or a few picked at random (Rediscover) on a day without any; ioCalendar the rest of today (else the next event
  in the coming 60 days), in each calendar's colour; ioHealth today's steps with the last seven days as bars, the
  move, exercise and stand rings, and last night's sleep. The
  server asks each app over its own API with the viewer's sign-in (the suite's session cookie, or the Basic / bearer
  credentials they came with), so everyone sees only what that app shows them; ioPix's thumbnails come through the
  start page too. An app that is down, or not open to that account, leaves its tile as it was. Nothing is kept.
- **The weather**, from AccuWeather: the conditions now and the five days ahead, at the top of the page. Settings ›
  Weather (admins) takes a free API key from developer.accuweather.com and finds the place by its name. The server
  keeps a copy and asks AccuWeather at most every 45 minutes (conditions) and 6 hours (forecast), and only while
  someone opens the page, so a free key's 50 calls a day are enough; browsers never talk to AccuWeather.
- **Bookmarks**, as [homepage](https://gethomepage.dev/configs/bookmarks/) lays them out: groups of links under the
  apps, each with a two-letter badge (or an icon: an image address, a file name from the dashboard-icons
  collection, `github.png`, or an SVG of your own uploaded for the link and kept in the database), the name and the
  site. Editors and admins add, change, reorder and move them in Settings › Bookmarks, or paste a homepage
  `bookmarks.yaml` to import it.
- **The suite's accounts**: the same sign-in as every io app (the account tiles, one click for a passwordless viewer),
  the account page (display name, email, password, sign out everywhere) and, for admins, the family's accounts and their
  role here. Sign-in at a reverse proxy (Cloudflare Access…) works as in the other apps.
- **Updates**: the daily version check, the note for admins and **Update now** in Settings › Server, as in ioCalendar.
- Light and dark, a phone layout, installable as a web app (manifest and icons).

## Updates

ioSuite asks GitHub once a day whether the main branch has a newer version (only the public commit list is read;
nothing about the server is sent; Settings › Server switches it off, `UPDATE_CHECK=0` locks it off). Admins then see a
note with **Update now**, and Settings › Server has the version, **Check for updates** and **Update now**. Updating runs
the app's own `update.sh`: the new version's Python packages first, then the code (a failed step leaves the running
version as it was), the database is brought up to date, and the service restarts; the page reloads when the new version
answers. In Docker, pull the image instead. From a shell: `./update.sh` (`--check` only looks,
`IOSUITE_REF=<sha>` installs a given commit).

## Run

ioSuite needs Python 3.10+, git (to install `iothing-auth`) and a MariaDB or MySQL database. Give it its own database
and user, for example:

```sql
CREATE DATABASE suite CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'suite'@'%' IDENTIFIED BY 'suite';
GRANT ALL ON suite.* TO 'suite'@'%';
```

The accounts live in the suite's shared `auth` database (the one the other io apps use); a new install of the suite
creates it the same way. The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iosuite.sh` and `proxmox/install/iosuite-install.sh` follow the community-scripts (ProxmoxVE) framework
layout, as the other io apps do. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/proxmox/ct/iosuite.sh)"
```

It asks for the ioSuite database (host, port, database, user, password), the shared accounts database, the web port
(8630), the public address behind your reverse proxy (optional) and the admin account; then the framework's own
questions (resources, network). It creates a small Debian 13 container and runs the app's own `setup.sh` inside with
those answers. The passwords reach `setup.sh` through its environment (a root-only file pushed in and removed again),
never on a command line; the output is kept in `/opt/iosuite/setup.log`. The container's `update` command pulls the
latest code and keeps the settings. For unattended runs set `IOSUITE_DB` and `IOSUITE_AUTH_DB`
(`host:port/db:user:password`), `IOSUITE_ADMIN` (`name:password`), `IOSUITE_PORT` and `IOSUITE_PUBLIC_URL`.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iosuite`) holds no data: everything is in the database.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite
./setup.sh          # asks for the databases, port and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

`setup.sh` offers 192.168.1.89, database `suite`, user `suite`, password `suite` as the defaults.
`python -m app.cli create-user NAME [viewer|editor|admin]` and `set-password NAME` work from a shell (the password from
`IOSUITE_PASSWORD` or asked for).

## Configuration

`iosuite.env` next to the app (written by `setup.sh`), or the environment:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`suite`) |
| `IOTHING_AUTH_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the suite's shared account database (`auth`): accounts, passwords, sessions, app passwords and roles, shared with every io app |
| `IOTHING_COOKIE_DOMAIN` | the domain the session cookie is shared on (`example.com`): signed in at `home.example.com`, signed in at `photos.example.com` too |
| `PORT` | web port for `run.sh` and the service (8630) |
| `PUBLIC_URL` | the address people use (behind a proxy) |
| `IOPIX_URL`, `IOHEALTH_URL`, `IOCALENDAR_URL`, `IOCONTACTS_URL`, `IONOTES_URL` | where each app is, as the family's browsers reach it (or Settings › Apps; empty: this host with the app's usual port) |
| `ACCUWEATHER_API_KEY`, `ACCUWEATHER_LOCATION` | the weather: an AccuWeather key and a location key (or Settings › Weather, which finds the location from a city name) |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD` | sign-in at a reverse proxy, as in the other io apps (Cloudflare Access, Authelia, Authentik, oauth2-proxy…) |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `IOSUITE_REPO`, `IOSUITE_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iosuite`, `main`) |

### HTTPS

Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy Manager, HAProxy, Cloudflare Tunnel), on a
host under the same `IOTHING_COOKIE_DOMAIN` as the apps, so the sign-in carries over.

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOTHING_TEST_DB=host:port:user:password
```

Covered: status and sign-in, the tiles and where they point (this host, the forwarded host behind a proxy, Settings,
the environment), hiding an app, the weather (AccuWeather mocked: set-up, the place search, the server's copy and its
age, a stale reading when AccuWeather is down), the tiles' glimpses (the apps' answers mocked: On this day and
Rediscover, the rest of today and what's next, steps and rings, an app that refuses or is down), the bookmarks (groups, links, order, moves, the homepage import) and
what a viewer may not change. CI runs them against MariaDB.

## Layout

```
app/main.py        the application: start-up (tables, first admin, the update check), who is asking, routes
app/api.py         the REST API: status, the apps and their settings, the server (version, updates)
app/apps.py        the catalogue of the suite's apps and where each one is (environment, Settings, this host)
app/status.py      is each app up (its /api/status) and does it have an update; is each bookmark reachable
app/layout.py      each account's own layout: hidden tiles and cards, the tiles' order, the photo strip
app/widgets.py     what the tiles and cards show: ioPix, ioCalendar, ioHealth and ioContacts asked over their APIs with the viewer's sign-in
app/weather.py     AccuWeather: the settings, the place search, the cached conditions and forecast
app/bookmarks.py   the bookmark groups and links, and the homepage bookmarks.yaml import
app/auth.py        the shared accounts (iothing-auth), as ioSuite uses them
app/users.py       accounts and roles, seen from ioSuite
app/db.py          MariaDB access and the schema (the meta settings table, the bookmarks)
app/config.py      settings from iosuite.env / the environment
app/updates.py     the version check and the self-update (update.sh)
app/cli.py         python -m app.cli: migrate, check, create-user, set-password
static/            the web app: index.html, app.js (one module, no build step), app.css, the icons (the apps' own under icons/apps/)
tests/             pytest, against a MariaDB of its own
setup.sh run.sh update.sh   install, start, update (Linux, Mac)
Dockerfile docker-compose.yml   the container
proxmox/           the Proxmox VE scripts (community-scripts layout)
```

### Growing the page

A tile is drawn from `/api/apps` (`app/apps.py`, `showHome` in `static/app.js`) and keeps a `.more` block under its
name, filled from `GET /api/widgets/<app>?tz=<IANA zone>` (`app/widgets.py`, `drawWidgets` in `static/app.js`). To give
another app a glimpse: a function in `app/widgets.py` that asks the app with `fetch()` (the viewer's credentials go
along) and returns what the tile needs, and a drawing function in `WIDGETS` in `static/app.js`. Images go through the
start page (its Content-Security-Policy allows only its own origin), as `/api/widgets/iopix/thumb/<id>` does.

## License

MIT.
