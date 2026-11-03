# ioCalendar

*The family calendar, in the iothing suite (with [iopix](https://github.com/avandeputte/iopix), ionotes and [iocontacts](https://github.com/avandeputte/iocontacts)).*

A self-hosted calendar: a web app for the whole family, and the standard protocols every calendar app already speaks, so the same events show up on phones, in Apple Calendar, Google Calendar, Outlook, Thunderbird and anywhere else. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL, and the suite's shared accounts (`iothing-auth`).

## What it does

- **Events** with a title, a place (address), start and end (or all day, over one day or many), a time zone, notes, the **people** who are there, **reminders**, a link, tentative or cancelled, busy or free.
- **Repeating events**: every day, week (on chosen days), weekday, month (on a date, or the second Tuesday, the last Friday…), year, every few of them, until a date or a number of times. Changing or deleting one asks, as phones do: **this one**, **this and later** (the series is split in two) or **all of them**. Exceptions made in other apps (moved or removed occurrences) are kept.
- **Calendars**: a shared **Family** calendar, a private **Personal** one for each account, and as many more as you like (shared or private), each with its colour. The calendars in the sidebar are check boxes: tick to show, untick to hide (remembered per account).
- **Views**: month, week, day and agenda, with a small month to jump around, drag and drop to move an event (to another day, or another time in the week and day views), a line at the current time, search across titles, places, people and notes, and keyboard shortcuts (`t` today, `n` new, `d`/`w`/`m`/`a` the views, ←/→ earlier and later, `/` search, `e` change the open event).
- **ioContacts (optional)**: the people on an event come from your contacts (picked as you type, with a link back to each), and a shared, read-only **Birthdays** calendar shows the birthdays and anniversaries kept in ioContacts, brought up to date every six hours.
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
(`.mobileconfig`) with the CalDAV account and a new app password for that device inside (or none, and the device asks).
Open the page in Safari on the iPhone, tap Download, then Settings › Profile Downloaded › Install.

Settings › Apps and devices shows the exact addresses to type, and makes **app passwords**: one per phone or app,
revocable on its own, used with your user name for CalDAV and the REST API (HTTP Basic, or
`Authorization: Bearer <app password>`).

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

The tools: `overview`, `list_calendars`, `agenda`, `search_events`, `get_event`, `get_ics`, `free_busy`,
`connection_details`; `create_event`, `update_event`, `delete_event`, `move_event`, `create_calendar`, `import_ics`; and
for admins `diagnostics`, `sync_birthdays`, `list_accounts`, `check_for_update`, `update_server`.

## Updates

ioCalendar asks GitHub once a day whether the main branch has a newer version (only the public commit list is read;
nothing about the server is sent; Settings › Server switches it off, `UPDATE_CHECK=0` locks it off). Admins then see a
note with **Update now**, and Settings › Server has the version, **Check for updates** and **Update now**. Updating runs
the app's own `update.sh`: the new version's Python packages first, then the code (a failed step leaves the running
version as it was), the database is brought up to date, and the service restarts; the page reloads when the new version
answers. In Docker, pull the image instead. From a shell: `./update.sh` (`--check` only looks,
`IOCALENDAR_REF=<sha>` installs a given commit).

## Run

ioCalendar needs Python 3.10+, git (to install `iothing-auth`) and a MariaDB or MySQL database. Give it its own database
and user, for example:

```sql
CREATE DATABASE calendar CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'calendar'@'%' IDENTIFIED BY 'calendar';
GRANT ALL ON calendar.* TO 'calendar'@'%';
```

The accounts live in the suite's shared `auth` database (the one ioPix, ioNotes and ioContacts use); a new install of
the suite creates it the same way. The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iocalendar.sh` and `proxmox/install/iocalendar-install.sh` follow the community-scripts (ProxmoxVE) framework layout, as the other io apps do. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iocalendar/main/proxmox/ct/iocalendar.sh)"
```

It asks for the calendar database (host, port, database, user, password), the shared accounts database, the web port (8620), the family's time zone, the public address behind your reverse proxy (optional) and the admin account; then the framework's own questions (resources, network). It creates a small Debian 13 container and runs the app's own `setup.sh` inside with those answers. The passwords reach `setup.sh` through its environment (a root-only file pushed in and removed again), never on a command line; the output is kept in `/opt/iocalendar/setup.log`. The container's `update` command pulls the latest code and keeps the settings. For unattended runs set `IOCALENDAR_DB` and `IOCALENDAR_AUTH_DB` (`host:port/db:user:password`), `IOCALENDAR_ADMIN` (`name:password`), `IOCALENDAR_PORT`, `IOCALENDAR_TIMEZONE` and `IOCALENDAR_PUBLIC_URL`.

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

`setup.sh` offers 192.168.1.89, database `calendar`, user `calendar`, password `calendar` as the defaults.
`python -m app.cli create-user NAME [viewer|editor|admin]`, `set-password NAME`, `import CALENDAR-ID FILE.ics` and
`sync-birthdays` work from a shell (the password from `IOCALENDAR_PASSWORD` or asked for).

## Configuration

`iocalendar.env` next to the app (written by `setup.sh`), or the environment:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`calendar`) |
| `IOTHING_AUTH_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the suite's shared account database (`auth`): accounts, passwords, sessions, app passwords and roles, shared with ioPix, ioNotes and ioContacts |
| `IOTHING_COOKIE_DOMAIN` | the domain the session cookie is shared on (`example.com`): signed in at `contacts.example.com`, signed in at `calendar.example.com` too |
| `PORT` | web port for `run.sh` and the service (8620) |
| `TIMEZONE` | the family's time zone (default: `TZ`, else the server's), for times written without one and all-day events |
| `PUBLIC_URL` | the address people use (behind a proxy), for links in Settings, the Apple profile and the MCP tools |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD` | sign-in at a reverse proxy, as in the other io apps (Cloudflare Access, Authelia, Authentik, oauth2-proxy…) |
| `IOCONTACTS_URL`, `IOCONTACTS_USER`, `IOCONTACTS_PASSWORD`, `IOCONTACTS_CF_CLIENT_ID`, `IOCONTACTS_CF_CLIENT_SECRET` | ioContacts (or Settings › ioContacts) |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `IOCALENDAR_MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `IOCALENDAR_REPO`, `IOCALENDAR_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iocalendar`, `main`) |

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

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOTHING_TEST_DB=host:port:user:password
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
app/mcp/           the MCP server: base (who is asking, finding events), read, write and admin tools
app/updates.py     the version check and running update.sh from the web app
app/users.py       accounts, app passwords and subscription tokens (the suite's, through iothing-auth)
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

MIT licence.
