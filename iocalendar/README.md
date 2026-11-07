# ioCalendar

*The family calendar, in the ioThing suite (with [ioPix](https://github.com/avandeputte/iopix), [ioNotes](https://github.com/avandeputte/ionotes), [ioContacts](https://github.com/avandeputte/iocontacts), [ioHealth](https://github.com/avandeputte/ioHealth) and the [ioSuite](https://github.com/avandeputte/iosuite) start page).*

A self-hosted calendar: a web app for the whole family, and the standard protocols every calendar app already speaks, so the same events show up on phones, in Apple Calendar, Google Calendar, Outlook, Thunderbird and anywhere else. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL, and the suite's shared library (`iosuite-shared`, in [iosuite-shared](https://github.com/avandeputte/iosuite-shared)).

## What it does

- **Events** with a title, a place (address), start and end (or all day, over one day or many), a time zone, notes, the **people** who are there, **reminders**, a link, tentative or cancelled, busy or free.
- **Repeating events**: every day, week (on chosen days), weekday, month (on a date, or the second Tuesday, the last Friday…), year, every few of them, until a date or a number of times. Changing or deleting one asks, as phones do: **this one**, **this and later** (the series is split in two) or **all of them**. Exceptions made in other apps (moved or removed occurrences) are kept.
- **Calendars**: a shared **Family** calendar, a private **Personal** one for each account, and as many more as you like (shared or private), each with its colour. The calendars in the sidebar are check boxes: tick to show, untick to hide (remembered per account).
- **Views**: month, week, day and agenda, with a small month to jump around, drag and drop to move an event (to another day, or another time in the week and day views), a line at the current time, search across titles, places, people and notes, and keyboard shortcuts (`t` today, `n` new, `d`/`w`/`m`/`a` the views, ←/→ earlier and later, `/` search, `e` change the open event).
- **ioContacts (optional)**: the people on an event come from your contacts (picked as you type, with a link back to each), and a shared, read-only **Birthdays** calendar shows the birthdays and anniversaries kept in ioContacts, brought up to date every six hours.
- **Public holidays**: a shared, read-only **Holidays** calendar with the public holidays of your country and, if you like, your state or province (Settings › Holidays; it starts with the country of the family's time zone, else the United States). Worked out on the server with the `holidays` package (nothing is fetched), last year to three years ahead, renewed daily; anyone can hide it in the sidebar.
- **Family members on events**: tag an event with the people of the family it is for ("For Emma"). The tags show as coloured initials on the calendar, the sidebar's Family list shows only one person's (or a few people's) events, and the tag is kept as an iCalendar `CATEGORIES` value with the member's name, so phones and calendar apps show it and a category typed there tags the event here too. The REST API, the subscription links (`?member=emma`) and MCP filter by member as well. Accounts that are not a person (an admin or service account) can be left out of the family in Settings › Users: they are not offered as a tag and get no private calendar.
- **Roles as in the other io apps**: viewers read the shared calendars (and change only their own), editors change shared events, admins also manage users and settings. The same accounts, passwords and app passwords as ioPix, ioNotes and ioContacts; one sign-in for all of them with a shared cookie domain.
- Light and dark, phone-sized screens, installable as an app.

No tasks or to-dos: those belong in their own app.

## Standards and APIs

| For | Standard | Where |
| --- | --- | --- |
| Calendar apps, two-way: Apple Calendar (Mac, iPhone, iPad), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Calendar, KDE, Outlook with a CalDAV add-in | **CalDAV** (RFC 4791) with sync-collection (RFC 6578), getctag, MKCALENDAR and extended MKCOL, PROPPATCH (name, colour, description, time zone), calendar-query with time ranges and `expand`, calendar-multiget, free-busy-query, If-Match / If-None-Match, discovery via `/.well-known/caldav` (RFC 6764) and current-user-principal | `https://host/dav/` |
| Any app that reads calendar files | **iCalendar** (RFC 5545): every event is kept as the iCalendar object it came in as, so properties ioCalendar does not edit (attachments, other apps' X- properties) survive a round trip; VTIMEZONE, RRULE / RDATE / EXDATE, RECURRENCE-ID overrides and VALARM included | CalDAV, `/api/events/<id>?format=ics`, import/export |
| Calendars that cannot sign in: Google Calendar, Outlook, Apple Calendar subscriptions | **iCalendar subscriptions** (`webcal://`) with a private token, one calendar or all of them, and **free/busy** (VFREEBUSY) | `/ics/<token>/<calendar>.ics`, `/ics/<token>/all.ics`, `/ics/<token>/freebusy.vfb` |
| Web and JSON clients | **REST/JSON** with **jCal** (RFC 7265) and iCalendar by content negotiation (`Accept: application/calendar+json` or `text/calendar`): occurrences in a range (repeating events expanded), events, calendars, free/busy, import/export | `/api/`, OpenAPI docs at `/api/docs` |
| iPhone, iPad and Mac in one step | **Apple configuration profile** (`com.apple.caldav.account`) | Settings › Apps and devices |
| AI assistants: Claude and anything else that speaks MCP | **Model Context Protocol** (streamable HTTP, and stdio) | `https://host/mcp` (switched on in Settings › Server) |

**iPhone, iPad and Mac in one step:** Settings › Apps and devices › *Download the profile* gives a configuration profile
(`.mobileconfig`) with the CalDAV account and a new CalDAV-only app password for that device inside (or none, and the device asks).
Open the page in Safari on the iPhone, tap Download, then Settings › Profile Downloaded › Install.

Settings › Apps and devices shows the exact addresses to type, and makes **app passwords**: one per phone or app,
revocable on its own, used with your user name for CalDAV and the REST API (HTTP Basic, or
`Authorization: Bearer <app password>`). An app password can be made **CalDAV only**: it opens `/dav` and nothing
else, so one lifted from a phone cannot reach the REST API, MCP or the web app (403). The Apple profile's password is
always CalDAV only; scripts and AI assistants need one without that limit.

```sh
curl -u alex:APP-PASSWORD "https://calendar.example.com/api/occurrences?start=2026-11-01&end=2026-12-01"
curl -u alex:APP-PASSWORD -H 'Accept: text/calendar' https://calendar.example.com/api/events/12
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"title": "Dentist", "start": "2026-11-12T09:00", "end": "2026-11-12T10:00", "location": "12 Oak Street", "reminders": [60]}' \
  https://calendar.example.com/api/events
curl -u alex:APP-PASSWORD -X PATCH -H 'Content-Type: application/json' -d '{"title": "Soccer (at the school)"}' \
  "https://calendar.example.com/api/events/7?scope=this&recurrenceId=2026-11-19T17:30:00-05:00"
```

## MCP server

ioCalendar is also an MCP server, as the other io apps are, so an assistant such as Claude can work with the calendars:
read the agenda, search events, find when people are free, add, change, move and delete events (one occurrence, the
ones after it, or the whole series), make calendars, import iCalendar files, and, for admins, check the server's health,
bring the birthdays up to date, look for a new version and install it.

It is off until an admin turns it on in **Settings › Server** (or `MCP=1` in the environment); off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Apps and devices), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account, with its rights.

```sh
claude mcp add --transport http iocalendar https://calendar.example.com/mcp --header "Authorization: Bearer APP-PASSWORD"
```

On the server itself, `.venv/bin/python -m app.mcp --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_calendars`, `list_family_members`, `agenda`, `search_events`, `get_event`, `get_ics`,
`free_busy`, `connection_details`; `create_event`, `update_event`, `delete_event`, `move_event`, `create_calendar`,
`import_ics`; and for admins `diagnostics`, `sync_birthdays`, `set_holidays`, `holiday_regions`, `list_accounts`,
`check_for_update`, `update_server`.

## Updates

ioCalendar asks GitHub once a day whether the main branch has a newer version (only the public commit list is read;
nothing about the server is sent; Maintenance › Updates and logs switches it off, `UPDATE_CHECK=0` locks it off). Admins
then see a note with **Update now**, and **Maintenance › Updates and logs** has the version, **Check for updates**,
**Update now**, the tail of the server log (`data/iocalendar.log`; `LOG_FILE` moves it, empty switches it
off) and **Restart**. The page is the same in every ioThing app: the version check, `update.sh`, the restart and the log
come from `iosuite_shared.updates` in iosuite-shared, served at `/api/server` and `/api/log`. Updating runs the app's own
`update.sh`: the new version's Python packages first, then the code (a failed step leaves the running version as it
was), the database is brought up to date, and the service restarts; the page reloads when the new version answers. In
Docker, pull the image instead. From a shell: `./update.sh` (`--check` only looks, `IOCALENDAR_REF=<sha>` installs a
given commit).

Settings is for what is configured (account, display, apps and devices, calendars, holidays, connected apps, users and
sign-in, server); Maintenance for what is run or checked (storage and backups, updates and logs). Admins reach both from
the sidebar and the avatar menu.

## Releases

Every version merged into main is released by itself: when `__version__` (app/__init__.py) has no GitHub release yet, CI tags it `v<version>`, publishes the image as `ghcr.io/avandeputte/iocalendar:v<version>` (and `latest`) and makes the release with the merge's message as notes. Bump the version in a change to release it.

## Run

ioCalendar needs Python 3.10+, git (to install `iosuite-shared` from the [iosuite-shared](https://github.com/avandeputte/iosuite-shared) repository) and a MariaDB or MySQL database. Give it its own database
and user, for example:

```sql
CREATE DATABASE calendar CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'calendar'@'%' IDENTIFIED BY 'calendar';
GRANT ALL ON calendar.* TO 'calendar'@'%';
```

The accounts and the suite-wide settings live in the Shared ioSuite database (`iosuite`, user `iosuite`; the one every
app of the suite uses); a new install of the suite creates it the same way. The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iocalendar.sh` and `proxmox/install/iocalendar-install.sh` follow the community-scripts (ProxmoxVE) framework layout, as the other io apps do. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iocalendar/main/proxmox/ct/iocalendar.sh)"
```

It asks for the calendar database (host, port, database, user, password), the Shared ioSuite database, the web port (8620), the family's time zone, the public address behind your reverse proxy (optional), the domain the sign-in is shared on (optional) and the admin account; then the framework's own questions (resources, network). It creates a small Debian 13 container and runs the app's own `setup.sh` inside with those answers. The passwords reach `setup.sh` through its environment (a root-only file pushed in and removed again), never on a command line; the output is kept in `/opt/iocalendar/setup.log`. The container's `update` command pulls the latest code and keeps the settings. For unattended runs set `IOCALENDAR_DB` and `IOCALENDAR_SUITE_DB` (`host:port/db:user:password`), `IOCALENDAR_ADMIN` (`name:password`), `IOCALENDAR_PORT`, `IOCALENDAR_TIMEZONE`, `IOCALENDAR_PUBLIC_URL` and `IOCALENDAR_COOKIE_DOMAIN`.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iocalendar`) holds no data: everything is in the database.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iocalendar && cd iocalendar
./setup.sh          # asks for the databases, port, time zone and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

Its last question, "Also install …?" (flag `--also iocalendar,ionotes`, `--also all`; `IOCALENDAR_ALSO` in the environment), puts
other apps of the suite in this same machine, beside ioCalendar (`/opt/iocalendar/app` next to `/opt/iocalendar/app`),
without asking the shared questions again: the same database server (each app gets its own database: `suite`,
`calendar`, `contacts`, `notes`, `health`, `iopix`; the user needs rights on those names too), the same Shared ioSuite
database, sign-in domain and admin (`iosuite-shared install`, from the shared library). Each app keeps its usual port
and updates itself as always. The Proxmox installer offers the same as a checklist, for one container with several apps.

The databases and users need not exist beforehand: give a MariaDB / MySQL administrator (the question after the
databases; flag `--db-admin USER:PASSWORD`, or `IOCALENDAR_DB_ADMIN`, also in the Proxmox installer) and `setup.sh` creates
the app's database and user, the Shared ioSuite database and user and, with other apps installed alongside, their
databases too, with the passwords you answered (`iosuite-shared provision`). Nothing is dropped, and the administrator's
password is used once and not written anywhere.

`setup.sh` offers 127.0.0.1, database `calendar`, user `calendar`, password `calendar` as the defaults; its flags
(`--db`, `--suite-db`, `--admin`, `--port`, `--public-url`, `--cookie-domain`, `--service`, `--yes`) are the same in
every app of the suite. `python -m app.cli import CALENDAR-ID FILE.ics`, `sync-birthdays` and `check` work from a shell;
accounts are the suite's: `.venv/bin/iosuite-shared --config . admin NAME --app iocalendar` (password from
`ADMIN_PASSWORD`, or asked for) and `.venv/bin/iosuite-shared --config . password NAME`.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment, which wins:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`calendar`) |
| `IOSUITE_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the Shared ioSuite database (`iosuite`, on `DB_HOST` unless set): accounts, passwords, sessions, app passwords, roles and suite-wide settings, shared by every app of the suite |
| `COOKIE_DOMAIN` | the domain the session cookie is shared on (`example.com`): signed in at `contacts.example.com`, signed in at `calendar.example.com` too |
| `HOST`, `PORT` | where the server listens (`0.0.0.0`, 8620; every app of the suite has its own port) |
| `FORWARDED_ALLOW_IPS` | the addresses that may pass on the visitor's address (`*`, or your reverse proxy's) |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | serve HTTPS directly instead of behind a reverse proxy |
| `TZ` | the family's time zone (default: the server's), for times written without one and all-day events |
| `PUBLIC_URL` | the address people use (behind a proxy), for links in Settings, the Apple profile and the MCP tools |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD` | sign-in at a reverse proxy, as in the other io apps (Cloudflare Access, Authelia, Authentik, oauth2-proxy…) |
| `IOCONTACTS_URL`, `IOCONTACTS_USER`, `IOCONTACTS_PASSWORD`, `IOCONTACTS_CF_CLIENT_ID`, `IOCONTACTS_CF_CLIENT_SECRET` | ioContacts (or Settings › ioContacts) |
| `HOLIDAYS_COUNTRY`, `HOLIDAYS_REGION`, `HOLIDAYS_LANGUAGE` | the first choice for Settings › Holidays: a two-letter country code (`off`: no Holidays calendar), a region code, the language of the names; until set, the country of `TZ`, else US |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `IOCALENDAR_REPO`, `IOCALENDAR_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iocalendar`, `main`) |
| `DATA_DIR` | where the app writes on its own: the log and the update result (`data/` in the app folder) |
| `LOG_FILE` | the server log shown at Maintenance › Updates and logs (`DATA_DIR/iocalendar.log`; `LOG_FILE=` with nothing after it: no file) |

### ioContacts

Settings › ioContacts (admins) takes ioContacts' address, a user name and an **app password made in ioContacts**
(Settings › Apps and devices there). ioCalendar talks to ioContacts from the server; browsers never need to reach it, so
the LAN address is the simplest choice. Behind Cloudflare Access, create a service token (Zero Trust › Access › Service
auth), allow it in the ioContacts application's policy, and enter its client ID and secret. Saving tests the connection
and fills the Birthdays calendar from ioContacts' birthday feed; it is brought up to date every six hours after that
(and from Settings › ioContacts or `python -m app.cli sync-birthdays`).

### HTTPS

Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy Manager, HAProxy, Cloudflare Tunnel): iOS and
macOS want HTTPS for CalDAV accounts outside the home network, and passwords travel with every CalDAV request.

### Cloudflare Tunnel and Cloudflare Access

With a `cloudflared` tunnel in front, set `PUBLIC_URL` to the public address. To make people sign in at Cloudflare
Access first, add a self-hosted Access application for that hostname, then turn on Settings › Users and sign-in ›
*Sign-in at the proxy* › Cloudflare Access with your team (`myteam.cloudflareaccess.com`) and the application's AUD tag
(or `AUTH_PROXY=cloudflare`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD`). ioCalendar checks Cloudflare's signed token and signs
the person in to the matching account (by email, then by name). This is saved for the whole suite.

Calendar apps cannot get through Access: Apple Calendar, DAVx⁵, Thunderbird and Google or Outlook subscriptions cannot
open the Access sign-in page or send a service token (so neither can the Apple profile). In the Access application, add
a policy with the action **Bypass** (Include: Everyone) for these paths, or a second Access application covering only
them with a Bypass policy:

| Path | Used by | Still protected by |
|---|---|---|
| `/dav/*` and `/.well-known/caldav` | CalDAV (Apple Calendar, the Apple profile, DAVx⁵, Thunderbird) | your user name and an app password |
| `/ics/*` | subscription links and free/busy | the private token in the link |
| `/mcp` | AI assistants (only if MCP is on) | an app password as a Bearer token |

Everything else, the web app and `/api/`, stays behind Access. A script that calls `/api/` from outside needs a
Cloudflare service token (`CF-Access-Client-Id` and `CF-Access-Client-Secret` headers) allowed in the policy, as well
as an app password.

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: calendars and roles, every event field round-tripping through JSON, iCalendar and jCal, all-day events,
repeating events with this / following / all changes and deletes, import and export, subscription links, free/busy,
app passwords, CalDAV discovery, PUT with preconditions, calendar-query with time ranges and expand, multiget,
sync-collection with deletions, MKCALENDAR, and the MCP server (switch, sign-in, the agenda, changing one occurrence, a
viewer's limits). CI runs them against MariaDB.

## Layout

```
app/main.py        the application: start-up (tables, first admin, birthdays sync), who is asking, routes
app/api.py         the REST API: calendars, events, occurrences, free/busy, import/export, subscriptions, Apple profile
app/caldav.py      CalDAV / WebDAV
app/ical.py        iCalendar and jCal: reading, indexing, expanding repeating events, editing, writing
app/model.py       calendars and events in MariaDB, sync tokens and tombstones for CalDAV
app/contacts.py    the ioContacts client: people and the Birthdays calendar
app/holiday.py     the Holidays calendar (country, region, language; filled daily)
app/members.py     family members on events (kept as CATEGORIES), and the member filter
app/mcp/           the MCP server: base (the server, finding events; who is asking comes from iosuite_shared.mcp), read, write and admin tools
app/access.py      who may call a route (the markers come from iosuite-shared)
app/users.py       accounts, app passwords and subscription tokens (the suite's, through iosuite-shared)
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

MIT licence.
