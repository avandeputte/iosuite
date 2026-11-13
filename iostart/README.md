# ioStart

*The start page of the ioThing suite: one place with every io app ([ioPix](https://github.com/avandeputte/iosuite/tree/main/iopix),
[ioHealth](https://github.com/avandeputte/iosuite/tree/main/iohealth), [ioCalendar](https://github.com/avandeputte/iosuite/tree/main/iocalendar), [ioTask](https://github.com/avandeputte/iosuite/tree/main/iotask), [ioRecipe](https://github.com/avandeputte/iosuite/tree/main/iorecipe),
[ioContact](https://github.com/avandeputte/iosuite/tree/main/iocontact), [ioNote](https://github.com/avandeputte/iosuite/tree/main/ionote)).*

A self-hosted home page for the family: a tile per app, signed in with the suite's shared accounts ([`iosuite-shared`](https://github.com/avandeputte/iosuite/tree/main/shared)), so
one sign-in here is a sign-in everywhere the page links to. FastAPI and a single-page vanilla JS app, built the same
way as the other io apps, with its few settings in MariaDB / MySQL. For now the tiles are links; each one keeps room for
what the app will show on the start page later (today's events, the newest photos, last night's sleep…).

## What it does

- **A tile per app**, with the app's own icon and colours, that opens it. Each app registers itself, with its address,
  in the suite's list of apps in the Shared ioSuite database (`suite_apps`, iosuite-shared 0.3 and later), and the page
  reads it there and only there: nothing to type, nothing to override. ioStart registers itself the same way. An app
  that has not registered (not installed, or not started yet) has no tile; one the page has no widgets for gets a plain
  tile. Each person can hide tiles in Customize. What the tiles and cards show is asked of each app by this server
  with the viewer's own sign-in (so each person sees only what they may see there), on localhost when the app runs on
  the same machine, else at its LAN address, else its public one, with the suite's Cloudflare Access service token
  (Settings › Global settings › Keys and tokens) when one is set.
- **A search box** at the top (⌘K / Ctrl-K): as you type it lists the bookmarks that match, the people ioContact
  finds, and a row per app that searches itself (ioPix, ioCalendar and ioNote open on their own results). Arrows
  pick a row, Enter opens it. When nothing of the suite matches, Enter searches the web (DuckDuckGo, or the engine
  picked in Customize the page); a prefix picks a site (`g` Google, `w` Wikipedia, `yt` YouTube, `m` Maps, `gh`
  GitHub…, also as `!g`), and an address typed in full (`github.com`) opens.
- **Quick add**: type an event in the search box ("dinner fri 19:00", "dentist tomorrow 9am", "trip 24 dec",
  "call mum 14:30-15:00") and pick "Add to the calendar": a dialog shows the title, day and times it understood, and
  the calendar, then makes the event in ioCalendar with the viewer's own sign-in.
- **Live**: every five minutes, and when the tab is shown again, the page brings the tiles, the cards, the weather
  and the dots up to date in place; at midnight it is drawn anew for the new day.
- **A wall display** (the gear › Wall display, or `#/wall` as a tablet's home address): full screen, ioPix photos one
  after another behind a big clock, the date, the weather and its next hours, and today's and the coming days'
  events with the birthdays. It keeps the screen on where the browser allows it; Escape or the ✕ (shown on a touch)
  goes back.
- **A dot by each app's name**: green when the app answers its `/api/status`, red when it does not, and an "update"
  badge when the app tells the viewer (an admin there) that a newer version is out. Bookmarks the server cannot
  reach get a red dot too. The server asks each app once a minute and pings each bookmark every five (HEAD, redirects not followed; never its own address or a link-local one).
- **Your own page** (the gear next to the date › Customize the page): untick the tiles and cards you do not need, put the tiles and
  the cards (Birthdays, This week, the photo strip, the bookmarks) in your order, and pick your own photo strip
  ("Default" is the admin's choice). Saved per account, on top of the default the admin set in Settings › Home page.
- **The week ahead** under the tiles: a Birthdays card from ioContact (birthdays and anniversaries in the next 30
  days, with the contact's photo; a row opens the contact) and a This week card from ioCalendar (the coming seven
  days' events, day by day; a day opens in ioCalendar). Each stands no taller than the row of tiles, with "Show all"
  when there is more. With the Birthdays card on the page, the calendar's own "X's birthday" and anniversary events
  are left to it (the tile's Today and This week skip them). A card that its app cannot fill is left out.
- **A strip of photos** the width of the page under the tiles: ioPix's Rediscover (photos at random), or
  On this day; an admin picks which, or turns it off, in Settings › Home page.
- **A glimpse of each app on its tile**: ioPix shows photos taken on this day in earlier years (one per year, "3 years
  ago"), or a few picked at random (Rediscover) on a day without any; ioCalendar the rest of today (else the next event
  in the coming 60 days), in each calendar's colour; ioTask what is due today, the overdue tasks first, in each list's colour; ioHealth today's steps with the last seven days as bars, the
  move, exercise and stand rings, and last night's sleep. The
  server asks each app over its own API with the viewer's sign-in (the suite's session cookie, or the Basic / bearer
  credentials they came with), so everyone sees only what that app shows them; ioPix's thumbnails come through the
  start page too. An app that is down, or not open to that account, leaves its tile as it was. Nothing is kept.
- **The weather**, from AccuWeather: the conditions now, "Rain from 15:00" when the next hours bring some, and the
  five days ahead, at the top of the page; a click on the conditions opens the next 12 hours. Settings ›
  Weather (admins) takes a free API key from developer.accuweather.com and finds the place by its name. The server
  keeps a copy and asks AccuWeather at most every hour (conditions), 90 minutes (the next 12 hours) and 6 hours
  (forecast), and only while someone opens the page: 44 calls on a day the page stays open from morning to night, so
  a free key's 50 a day are enough; browsers never talk to AccuWeather.
- **Home Assistant**: a Home card with the entities an admin picks (lights, switches, locks, covers, scenes, sensors,
  people), each with its state; a tap toggles the ones the admin ticked "control", for editors and admins (a viewer sees the
  states and switches nothing, so a wall tablet that should switch lights signs in as an editor). Sensors ticked "wall" show on the
  wall display; the search box finds any entity by name and toggles the controllable ones; a line above the tiles
  points out what needs attention (an entity in the state the admin named, and built in: a leak, smoke, gas or CO
  sensor that is on, a problem or safety sensor, a battery at 15% or under). Settings › Home Assistant (admins) takes
  the address and a long-lived access token; the server makes every call with it, and browsers never see the token
  nor talk to Home Assistant. The server holds one websocket to Home Assistant for state changes and streams the card
  to every open page (server-sent events) when something on the card or one of the alerts changes, so a light switched
  at the wall shows within a second; without the
  websocket (HA_FEED=0, or an old install) the states come in one call kept five seconds.
- **Bookmarks**: one tree of folders and links, as a browser keeps them, on a page of its own
  (`#/bookmarks`, from the start page and the gear menu). Each person's bookmarks are their own (members, editors and
  admins keep some; nobody else sees them), and the start page's admins share folders and links with everyone (the
  people icon beside the house); only they change the shared ones. Others can add their own links in a shared folder
  and take a shared one off their own start page; their browsers put back what they change of the shared ones. The start page shows the part picked for it, as
  [homepage](https://gethomepage.dev/configs/bookmarks/) lays bookmarks out: the house on a folder shows it as a group
  with its links, the house on a link shows or hides just that one; each link has an icon, the name and the site. The icon is the site's
  own, as a browser finds it: the server asks the bookmarked page for its icon (`<link rel="icon">`, else
  `/favicon.ico`), keeps it in the database per site and serves it itself, so your browser asks the bookmarked sites
  nothing; a site without one shows a two-letter badge. An icon you give a link wins: an image address, a file name
  from the dashboard-icons collection (`github.png`), or a file of your own uploaded for the link (an SVG, which stays sharp at any size, or a PNG). The groups pack into columns (as many 250 px columns as
  fit). Editors and admins add, change, reorder and move folders and links (drag by the handle, with a mouse or a
  finger), import a bookmarks file a browser exported (HTML) or an XBEL file, and export either;
  `POST /api/bookmarks/import` still takes a homepage `bookmarks.yaml`.
- **The Bookmarks app** at `<address>/bookmarks`: the Bookmarks page as an app of its own, with its own name, icon
  and manifest (`static/bookmarks.webmanifest`), opening straight on the bookmarks. On an iPhone or iPad open that
  address (Safari, or Vivaldi, Chrome, Edge, Firefox) and choose Share › Add to Home Screen; on Android or a desktop,
  the browser's Install. It runs without the browser around it and fetches the tree each time it comes back to the
  front (no offline copy). On a phone it has a search box, rows to tap, a ⋯ menu per link and folder, and a short
  link form (the address; the name is the site's address when left empty). Sign-in is the page's own: behind
  Cloudflare Access a home-screen app signs in once by itself (it keeps its own cookies, apart from the browser's).
- **ioStart, the iPhone and iPad app** ([avandeputte/iostart-apps](https://github.com/avandeputte/iostart-apps)): the
  tree with search and editing, a share sheet entry that bookmarks the page open in any browser, and a built-in
  browser (WebKit) for opening bookmarks inside the app. It speaks the extension's API (`/dav/ext`) and signs in with
  the same one-tap flow.
- **Bookmark sync with browsers**: everything in the tree syncs, on the start page or not.
  - *The ioStart Bookmarks extension* (`static/extension`, Chrome, Edge and Firefox; its own README there): keeps the
    browser's own bookmarks the same as the tree, both ways, with nothing to configure but the address. The bookmarks
    bar is the top-level folder "Bookmarks bar", Firefox's bookmarks menu the folder "Bookmarks menu", Other bookmarks
    everything else at the top, so every browser shows the same. It sends what changed in the browser in one request
    (`/dav/ext`, `app/bookmarkext.py`) and makes the browser the tree that comes back, so a delete here or in another
    browser goes everywhere. One-click sign-in (the same flow as below: an app password of its own, for sync only).
    Download it from Settings › Bookmarks; `.github/workflows/extension.yml` packages each version as a release and,
    with an addons.mozilla.org API key in the repository's secrets, has Mozilla sign the Firefox file.
  - *Nextcloud Bookmarks API* at `<address>/dav/nextcloud` (REST v2: folders, bookmarks, tags, order, hashes, bulk
    import, the lock, and Nextcloud's sign-in flow for apps). [Floccus](https://floccus.org) (Firefox, Chrome, Edge,
    Android, iOS): add a *Nextcloud Bookmarks* account with that address and say yes on the page it opens; it gets an
    app password of its own, for sync only. Other clients written for Nextcloud Bookmarks sign in with the account's
    name and an app password.
  - *A bookmarks file over WebDAV* at `<address>/dav/bookmarks/`: `bookmarks.xbel` (XBEL) or `bookmarks.html`
    (the bookmarks HTML of browsers), for Floccus's WebDAV kind of account and anything else that syncs such a file.
    Name and app password; no passphrase (an encrypted file cannot be read, so it is refused).
  - App passwords live in the Shared ioSuite database like all others (Settings › Account, Settings › Security). A
    viewer's sync app can read; changing takes an editor or admin. Behind Cloudflare Access, `/dav/*` needs the same
    bypass as the other apps' CalDAV / CardDAV paths. A bookmark is in one folder (the same address in two folders is
    two bookmarks); bookmarklets and other non-web addresses sync but never show on the start page.
- **The suite's accounts**: the same sign-in as every io app (the account tiles, one click for a passwordless viewer),
  Settings › Account (display name, email, password) and Settings › Display (the theme, kept with the account), both
  iosuite-shared's panels, the same in every io app; every setting saves as soon as you change it. Accounts and roles
  are managed under Settings › Security (below). Sign-in at a reverse proxy (Cloudflare Access…) works as in the other apps.
- **Suite administration** (Settings › Security and Settings › Global settings, suite admins only): everything in the Shared ioSuite database for the
  whole suite. **People**: add, rename and delete accounts, email, sign-in list, suite admin, set or remove a password,
  their role in every app, their sessions (end one or all) and app passwords. **Roles**: a grid of everyone against
  every app (or "default", the app's default role). **App passwords**: everyone's, in every app, with their scope
  (everything, sync only, or read only), revoke one or make one for someone. **Keys and tokens**: every app's keys for
  services outside the suite (this page's Home Assistant token and AccuWeather key, ioPix's Google keys, the suite's
  Cloudflare Access service token), replace or clear, never shown back. The apps' own **service accounts**
  (`iocalendar-app`…, under People), with which apps read from each other without any setup. **Apps**: each app's default role (none makes it
  invitation-only) and sign-in requirement; forget an uninstalled app. **Sign-in at the proxy** for the whole suite. The
  panel is iosuite-shared's (`/api/suite-admin/ui.js` on `/api/suite-admin`), so every io app shows the same one.
- **Updates**: the daily version check, the note for admins and **Update now**, the server log and Restart under Settings › Server, as in every ioThing app.
- **Update every app at once**: Settings › Global settings › Updates (suite admins) shows each app's version against GitHub with **Check all now** and **Update all**; each app runs its own `update.sh`.
- **MCP** (`/mcp`, off until switched on at Settings › Server): `suite_versions` and `update_suite_apps` let an AI assistant do the same, signed in with a suite admin's user name and an ioStart app password (Settings › Account).
- Light and dark, a phone layout, installable as a web app (manifest and icons).

## Run

ioStart needs Python 3.10+ and a MariaDB or MySQL database. Give it its own database
and user, for example:

```sql
CREATE DATABASE suite CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'suite'@'%' IDENTIFIED BY 'suite';
GRANT ALL ON suite.* TO 'suite'@'%';
```

The accounts, and the settings the whole suite shares (such as the list of apps and where each one is), live in the
**Shared ioSuite database**, the one every io app uses (`iosuite`, user `iosuite`, by default); a new install of the
suite creates it the same way. The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iostart.sh` and `proxmox/install/iostart-install.sh` follow the community-scripts (ProxmoxVE) framework
layout, as the other io apps do. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/proxmox/ct/iostart.sh)"
```

It asks for the ioStart database (host, port, database, user, password), the Shared ioSuite database, the web port
(8630), the public address behind your reverse proxy (optional), the domain the sign-in is shared on (optional) and the
admin account, and which other apps of the suite go in the same container (ioCalendar, ioTask, ioRecipe, ioContact, ioNote, ioHealth:
they reuse those answers, each app with its own database on the same server, the same accounts and admin, each on its
usual port); then the framework's own questions (resources, network). It creates a small Debian 13 container and runs the app's own `setup.sh` inside with
those answers. The passwords reach `setup.sh` through its environment (a root-only file pushed in and removed again),
never on a command line; the output is kept in `/opt/iostart/setup.log`. The container's `update` command pulls the
latest code and keeps the settings. For unattended runs set `IOSTART_DB` and `IOSTART_SUITE_DB`
(`host:port/db:user:password`), `IOSTART_ADMIN` (`name:password`), `IOSTART_PORT`, `IOSTART_PUBLIC_URL` and
`IOSTART_COOKIE_DOMAIN`, and `IOSTART_ALSO=iocalendar,iocontact` (or `none`).

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iosuite/iostart`) holds no data: everything is in the database.

The whole suite in one stack, MariaDB included: [`docker-compose.yml`](../docker-compose.yml) at the root of the repository
starts a MariaDB with a database per app, ioStart, ioCalendar, ioTask, ioRecipe, ioContact, ioNote, ioHealth and ioPix (without
digiKam), with one Shared ioSuite database and one admin. Edit the passwords, the photos path and the time zone at
the top, then `docker compose up -d` there (or paste it as a stack in Dockge / Portainer).

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iostart
./setup.sh          # asks for the databases, port and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

`setup.sh` offers 127.0.0.1, database `suite`, user `suite`, password `suite` as the defaults; its flags (`--db`,
`--suite-db`, `--admin`, `--port`, `--public-url`, `--cookie-domain`, `--service`, `--yes`) are the same in every app of
the suite. Its last question, "Also install …?" (flag `--also iopix,ionote`, `--also all`), puts other apps of the
suite in this same machine, beside ioStart (`/opt/iocalendar/app` next to `/opt/iostart/app`), without asking the
shared questions again: the same database server (each app gets its own database: `calendar`, `tasks`, `contacts`, `notes`,
`health`, `iopix`; the user needs rights on those names too), the same Shared ioSuite database, sign-in domain and
admin. Each app keeps its usual port and updates itself as always. Accounts are the suite's: `.venv/bin/iosuite-shared --config . admin NAME --app iostart` (password from
`ADMIN_PASSWORD`, or asked for) and `.venv/bin/iosuite-shared --config . password NAME`.

The databases and users need not exist beforehand: give a MariaDB / MySQL administrator (the question after the
databases; flag `--db-admin USER:PASSWORD`, or `IOSTART_DB_ADMIN`, also in the Proxmox installer) and `setup.sh` creates
the app's database and user, the Shared ioSuite database and user and, with other apps installed alongside, their
databases too, with the passwords you answered (`iosuite-shared provision`). Nothing is dropped, and the administrator's
password is used once and not written anywhere.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment, which wins:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`suite`) |
| `IOSUITE_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the Shared ioSuite database (`iosuite`, on `DB_HOST` unless set): accounts, passwords, sessions, app passwords and roles, the suite-wide settings and the list of apps, shared with every io app |
| `COOKIE_DOMAIN` | the domain the session cookie is shared on (`example.com`): signed in at `home.example.com`, signed in at `photos.example.com` too |
| `HOST`, `PORT` | where the server listens (`0.0.0.0`, 8630; every app of the suite has its own port) |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | serve HTTPS directly instead of behind a reverse proxy |
| `PUBLIC_URL` | the address people use (behind a proxy); also what ioStart registers in the suite's list of apps |
| `ACCUWEATHER_API_KEY`, `ACCUWEATHER_LOCATION` | the weather: an AccuWeather key and a location key (or Settings › Home page, which finds the location from a city name) |
| `HA_URL`, `HA_TOKEN` | Home Assistant: its address (`http://homeassistant.local:8123`) and a long-lived access token (or Settings › Home Assistant) |
| `HA_FEED` | `0` turns off the websocket to Home Assistant (the page then polls every few seconds) |
| `SITE_ICONS` | `0`: the server does not fetch the bookmarked sites' icons (links show their badge, or the icon you gave them) |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD` | sign-in at a reverse proxy, as in the other io apps (Cloudflare Access, Authelia, Authentik, oauth2-proxy…) |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `IOSTART_REPO`, `IOSTART_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iosuite`, `main`) |
| `DATA_DIR` | where the app writes on its own: the log and the update result (`data/` in the app folder) |
| `LOG_FILE` | the server log shown at Settings › Server (`DATA_DIR/iostart.log`; `LOG_FILE=` with nothing after it: no file) |

## Updates

ioStart asks GitHub once a day whether the main branch has a newer version (only the public commit list is read;
nothing about the server is sent; Settings › Server switches it off, `UPDATE_CHECK=0` locks it off). Admins
then see a note with **Update now**, and **Settings › Server** has the version, **Check for updates**,
**Update now**, the tail of the server log (`data/iostart.log` in the app folder; `LOG_FILE` moves it, empty switches it
off) and **Restart**. The page is the same in every ioThing app: the version check, `update.sh`, the restart and the log
come from `iosuite_shared.updates` in iosuite-shared, served at `/api/server` and `/api/log`. Updating runs the app's own
`update.sh`: the new version's Python packages first, then the code (a failed step leaves the running
version as it was), the database is brought up to date, and the service restarts; the page reloads when the new version
answers. In Docker, pull the image instead. From a shell: `./update.sh` (`--check` only looks,
`IOSTART_REF=<sha>` installs a given commit).

ioNotes, ioTasks and ioContacts became ioNote, ioTask and ioContact. After updating them, move an existing install
(service, `/opt` folder, log and config.env names) once per machine with
[`tools/rename-install.sh`](tools/rename-install.sh):

```bash
curl -fsSLO https://raw.githubusercontent.com/avandeputte/iosuite/main/tools/rename-install.sh
sudo bash rename-install.sh --dry-run    # then without --dry-run
```

## Reverse proxy and HTTPS

Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy Manager, HAProxy, Cloudflare Tunnel), on a
host under the same `COOKIE_DOMAIN` as the apps, so the sign-in carries over.

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: status and sign-in, the tiles and where they point (this host, the forwarded host behind a proxy, Settings,
the environment), hiding an app, the weather (AccuWeather mocked: set-up, the place search, the server's copy and its
age, a stale reading when AccuWeather is down), Home Assistant (its API mocked: set-up, the card's entities and
their wording, the allowlist for switching, the search, the alerts), the tiles' glimpses (the apps' answers mocked: On this day and
Rediscover, the rest of today and what's next, steps and rings, an app that refuses or is down), the bookmarks (groups, links, order, moves, the homepage import) and
what a viewer may not change. CI runs them against MariaDB.

## Layout

```
app/main.py        the application: start-up (tables, first admin, the update check), the suite's middleware, status and routes
app/mcp.py         the MCP server (/mcp): suite_versions and update_suite_apps (iosuite_shared), suite admins only
app/access.py      who may call a route: the markers every /api route carries (public, signed_in, editor, admin)
app/api.py         the REST API: the apps and their settings (sign-in, accounts, status, the server, updates and the log: iosuite_shared's routers)
app/apps.py        the suite's apps as they registered (iosuite_shared.suite) and the order of their tiles
app/status.py      is each app up (its /api/status) and does it have an update; is each bookmark reachable
app/layout.py      each account's own layout: hidden tiles and cards, the tiles' order, the photo strip
app/widgets.py     what the tiles and cards show: ioPix, ioCalendar, ioTask, ioHealth and ioContact asked over their APIs with the viewer's sign-in
app/weather.py     AccuWeather: the settings, the place search, the cached conditions and forecast
app/homeassistant.py  Home Assistant: the settings, the chosen entities and their state, switching them, the search, the alerts
app/ha_feed.py     Home Assistant's websocket: state changes folded into the copy, streamed to the pages
app/bookmarks.py   the bookmark groups and links, and the homepage bookmarks.yaml import
app/auth.py        the shared accounts and the updater (iosuite-shared), as ioStart uses them
app/db.py          MariaDB access and the schema (the meta settings table, the bookmarks)
app/config.py      the settings: the suite's standard names (iosuite_shared.config) and ioStart's own
app/cli.py         python -m app.cli: migrate, check
app/__main__.py    python -m app: the server (HOST, PORT)
static/            the web app: index.html, app.js (one module, no build step), app.css, the icons (each app's tile shows the icon it registered, served by that app)
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

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](LICENSE).
