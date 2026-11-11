# ioTasks

*The family's task lists, in the ioThing suite (with [ioPix](https://github.com/avandeputte/iopix), [ioNotes](https://github.com/avandeputte/ionotes), [ioContacts](https://github.com/avandeputte/iocontacts), [ioCalendar](https://github.com/avandeputte/iocalendar), [ioHealth](https://github.com/avandeputte/iohealth) and the [ioSuite](https://github.com/avandeputte/iosuite) start page).*

Self-hosted task lists: a web app for the whole family, and the standard protocol reminders apps already speak, so the same lists show up in Apple Reminders on iPhone, iPad and Mac, in Tasks.org or jtx Board on Android, in Thunderbird and anywhere else that syncs to-dos over CalDAV. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL, and the suite's shared library (`iosuite-shared`, in [iosuite-shared](https://github.com/avandeputte/iosuite-shared)).

## What it does

- **Tasks** with a title, notes, a due date (a day, or a day and a time), a **priority**, **alerts**, a link, and a box to tick them off.
- **Repeating tasks**: every day, weekday, week, two weeks, month or year, every so many of them (and whatever rule another app gave it). Ticking one off moves it on to its next date, as Apple Reminders does, instead of closing it; a rule with a number of times counts down.
- **Repeat after completion**: "two weeks after I tick it off" instead of "every two weeks": the task comes back that long after the day it was done, at its usual time. Reminders has no such repeat, so the rule is ioTasks' own (`X-IOTASKS-AFTER-DONE:P2W` on the task); a task ticked off on a phone still comes back.
- **Subtasks**: a task under another one, shown indented under it with a count (2/5). Deleting or moving a task takes its subtasks along.
- **Lists**: a shared **Family** list, a private **Personal** one for each account, and as many more as you like (shared or private), each with its colour and its count of open tasks (red when something is overdue).
- **Today, Scheduled, All and Completed** across every list you see: Today has what is due today and what is overdue, Scheduled everything with a date, day by day. "Today" is the day where you are, not where the server is.
- **Smart quick add**: type a line on top of any list and press Enter. Plain English becomes the task's fields: "Pay rent every month on the 1st 9am !high" is *Pay rent*, due on the next 1st at 9:00, monthly, high priority. It reads when (`tomorrow 5pm`, `friday`, `15 nov`, `in 2 weeks`, `the 20th`, `tonight`), how often (`daily`, `every monday and thursday`, `every 2 weeks after done`), how important (`!high`, `!!`), which list (`#groceries`) and for whom (`@emma`); what it understood shows under the line while you type, and the rest is the title. It can be switched off in Settings › Display.
- **Postpone**: a button on every task that is due puts it off to tomorrow, the weekend or next week (it keeps its time, and its alerts move along), and "Move all to today" on Overdue does that for everything that is late. The task form has the same days one click away.
- **Order by hand**: a list can be sorted by due date or put in your own order by dragging (a task takes its subtasks along; subtasks move within their task). The order is kept as `X-APPLE-SORT-ORDER`, the property Apple Reminders uses for its manual order. Lists are dragged into order too, in the sidebar or in Settings › Lists.
- **Activity and undo**: who added, changed, ticked off, moved or deleted what, in the web app, in a reminders app or through an assistant, per list or for all of them. Every change can be taken back: **Undo** shows for ten seconds after a change, and on the Activity page for as long as the task is still as that change left it. Deleting a task with its subtasks, "Clear completed" or adding a template is one step, undone as one.
- **Templates**: save a list's tasks (with notes, priorities, links, people and subtasks) as a template, and add them to a list again later, or start a new list with them: the packing list, the weekly shop. Shared with everyone, or your own.
- **Print**: a list prints as a checklist (the list's ⋯ menu, or the browser's Print).
- **Family members on tasks**: tag a task with the people of the family it is for. The tags show as coloured initials, the sidebar's Family list shows only one person's (or a few people's) tasks, and the tag is kept as an iCalendar `CATEGORIES` value with the member's name. The REST API (`?member=emma`) and MCP filter by member as well. Accounts that are not a person (an admin or service account) can be left out of the family in Settings › Family: they are not offered as a tag and get no private list.
- **Search** across titles and notes, **import** of .ics files with to-dos, **export** of each list, and keyboard shortcuts (`n` new, `t` today, `s` scheduled, `a` all, `/` search).
- **Roles as in the other io apps**: viewers read the shared lists (and change only their own), editors change shared tasks, admins also manage users and settings. The same accounts, passwords and app passwords as the other io apps; one sign-in for all of them with a shared cookie domain.
- **Settings › Security** and **Global settings** (suite admins): the whole suite's people and their role in every app, app passwords and sign-in at the proxy; the apps, keys and tokens; the same panel as on the start page and in every io app (iosuite-shared's `/api/suite-admin/ui.js`).
- Light and dark, phone-sized screens, installable as an app.

No events: those belong in [ioCalendar](https://github.com/avandeputte/iocalendar).

## Run

ioTasks needs Python 3.10+, git (to install `iosuite-shared` from the [iosuite-shared](https://github.com/avandeputte/iosuite-shared) repository) and a MariaDB or MySQL database. Give it its own database
and user, for example:

```sql
CREATE DATABASE tasks CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tasks'@'%' IDENTIFIED BY 'tasks';
GRANT ALL ON tasks.* TO 'tasks'@'%';
```

The accounts and the suite-wide settings live in the Shared ioSuite database (`iosuite`, user `iosuite`; the one every
app of the suite uses); a new install of the suite creates it the same way. The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iotasks.sh` and `proxmox/install/iotasks-install.sh` follow the community-scripts (ProxmoxVE) framework layout, as the other io apps do. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iotasks/main/proxmox/ct/iotasks.sh)"
```

It asks for the tasks database (host, port, database, user, password), the Shared ioSuite database, the web port (8670), the family's time zone, the public address behind your reverse proxy (optional), the domain the sign-in is shared on (optional) and the admin account; then the framework's own questions (resources, network). It creates a small Debian 13 container and runs the app's own `setup.sh` inside with those answers. The passwords reach `setup.sh` through its environment (a root-only file pushed in and removed again), never on a command line; the output is kept in `/opt/iotasks/setup.log`. The container's `update` command pulls the latest code and keeps the settings. For unattended runs set `IOTASKS_DB` and `IOTASKS_SUITE_DB` (`host:port/db:user:password`), `IOTASKS_ADMIN` (`name:password`), `IOTASKS_PORT`, `IOTASKS_TIMEZONE`, `IOTASKS_PUBLIC_URL` and `IOTASKS_COOKIE_DOMAIN`.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iotasks`) holds no data: everything is in the database.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iotasks && cd iotasks
./setup.sh          # asks for the databases, port, time zone and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

Its last question, "Also install …?" (flag `--also iocalendar,ionotes`, `--also all`; `IOTASKS_ALSO` in the environment), puts
other apps of the suite in this same machine, beside ioTasks (`/opt/iocalendar/app` next to `/opt/iotasks/app`),
without asking the shared questions again: the same database server (each app gets its own database: `suite`,
`calendar`, `contacts`, `notes`, `health`, `iopix`, `tasks`; the user needs rights on those names too), the same Shared ioSuite
database, sign-in domain and admin (`iosuite-shared install`, from the shared library). Each app keeps its usual port
and updates itself as always. The Proxmox installer offers the same as a checklist, for one container with several apps.

The databases and users need not exist beforehand: give a MariaDB / MySQL administrator (the question after the
databases; flag `--db-admin USER:PASSWORD`, or `IOTASKS_DB_ADMIN`, also in the Proxmox installer) and `setup.sh` creates
the app's database and user, the Shared ioSuite database and user and, with other apps installed alongside, their
databases too, with the passwords you answered (`iosuite-shared provision`). Nothing is dropped, and the administrator's
password is used once and not written anywhere.

`setup.sh` offers 127.0.0.1, database `tasks`, user `tasks`, password `tasks` as the defaults; its flags
(`--db`, `--suite-db`, `--admin`, `--port`, `--public-url`, `--cookie-domain`, `--service`, `--yes`) are the same in
every app of the suite. `python -m app.cli import LIST-ID FILE.ics` and `check` work from a shell;
accounts are the suite's: `.venv/bin/iosuite-shared --config . admin NAME --app iotasks` (password from
`ADMIN_PASSWORD`, or asked for) and `.venv/bin/iosuite-shared --config . password NAME`.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment, which wins:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`tasks`) |
| `IOSUITE_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the Shared ioSuite database (`iosuite`, on `DB_HOST` unless set): accounts, passwords, sessions, app passwords, roles and suite-wide settings, shared by every app of the suite |
| `COOKIE_DOMAIN` | the domain the session cookie is shared on (`example.com`): signed in at `calendar.example.com`, signed in at `tasks.example.com` too |
| `HOST`, `PORT` | where the server listens (`0.0.0.0`, 8670; every app of the suite has its own port) |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | serve HTTPS directly instead of behind a reverse proxy |
| `TZ` | the family's time zone (default: the server's), for times written without one and for "today" when a client does not say where it is |
| `PUBLIC_URL` | the address people use (behind a proxy), for links in Settings, the Apple profile and the MCP tools |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD` | sign-in at a reverse proxy, as in the other io apps (Cloudflare Access, Authelia, Authentik, oauth2-proxy…) |
| `CF_KV_ACCOUNT_ID`, `CF_KV_NAMESPACE_ID`, `CF_KV_API_TOKEN` | optional edge check of app passwords: the Workers KV namespace a Cloudflare Worker on `/dav*` reads; normally stored once for the whole suite in Settings › Global settings › Keys and tokens, these override it ([setup](https://github.com/avandeputte/iosuite-shared/blob/main/cloudflare/edge-auth/README.md)) |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `KEEP_DELETED_DAYS` | how long a deleted task's marker is kept, so phones learn of the deletion at their next sync (`90`); a client that stayed away longer starts its sync over. The activity log is kept as long |
| `MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `IOTASKS_REPO`, `IOTASKS_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iotasks`, `main`) |
| `DATA_DIR` | where the app writes on its own: the log and the update result (`data/` in the app folder) |
| `LOG_FILE` | the server log shown at Settings › Server (`DATA_DIR/iotasks.log`; `LOG_FILE=` with nothing after it: no file) |

## Updates

ioTasks asks GitHub once a day whether the main branch has a newer version (only the public commit list is read;
nothing about the server is sent; Settings › Server switches it off, `UPDATE_CHECK=0` locks it off). Admins
then see a note with **Update now**, and **Settings › Server** has the version, **Check for updates**,
**Update now**, what the server runs on, the tail of the server log (`data/iotasks.log`; `LOG_FILE` moves it, empty switches it
off) and **Restart**. The page is the same in every ioThing app: the panel (`/api/server/ui.js`), the version check, `update.sh`, the
restart and the log come from iosuite-shared, served at `/api/server` and `/api/log`. Updating runs the app's own
`update.sh`: the new version's Python packages first, then the code (a failed step leaves the running version as it
was), the database is brought up to date, and the service restarts; the page reloads when the new version answers. In
Docker, pull the image instead. From a shell: `./update.sh` (`--check` only looks, `IOTASKS_REF=<sha>` installs a
given commit).

Everything is under one Settings page (the sidebar and the avatar menu); a change is saved the moment it is made: your own tabs (account, display, apps and
devices, lists), then for admins family and server (with Export: each list as an
.ics file), and for suite admins security and global settings. Import is a page of its own in the sidebar.

### Releases

Every version merged into main is released by itself: when `__version__` (app/__init__.py) has no GitHub release yet, CI tags it `v<version>`, publishes the image as `ghcr.io/avandeputte/iotasks:v<version>` (and `latest`) and makes the release with the merge's message as notes. Bump the version in a change to release it.

## Reverse proxy and HTTPS

Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy Manager, HAProxy, Cloudflare Tunnel): iOS and
macOS want HTTPS for CalDAV accounts outside the home network, and passwords travel with every CalDAV request.

### Cloudflare Tunnel and Cloudflare Access

With a `cloudflared` tunnel in front, set `PUBLIC_URL` to the public address. To make people sign in at Cloudflare
Access first, add a self-hosted Access application for that hostname, then turn on Settings › Security ›
Sign-in at the proxy › Cloudflare Access with your team (`myteam.cloudflareaccess.com`) and the application's AUD tag
(one setting for the whole suite, kept in the Shared ioSuite database). ioTasks checks Cloudflare's signed token and signs
the person in to the matching account (by email, then by name).

Reminders apps cannot get through Access: Apple Reminders, DAVx⁵ and Thunderbird cannot open the Access sign-in page or
send a service token (so neither can the Apple profile). In the Access application, add a policy with the action
**Bypass** (Include: Everyone) for these paths, or a second Access application covering only them with a Bypass policy:

| Path | Used by | Still protected by |
|---|---|---|
| `/dav/*` and `/.well-known/caldav` | CalDAV (Apple Reminders, the Apple profile, DAVx⁵, Thunderbird) | your user name and an app password |
| `/profile/*` | the Apple profile's download link | the short-lived secret in the link (the request log keeps the address without it) |
| `/mcp` | AI assistants (only if MCP is on) | an app password as a Bearer token |

Everything else, the web app and `/api/`, stays behind Access. A script that calls `/api/` from outside needs a
Cloudflare service token (`CF-Access-Client-Id` and `CF-Access-Client-Secret` headers) allowed in the policy, as well
as an app password.

### Checking app passwords at Cloudflare (optional)

Cloudflare Access can't check what DAV clients send, so `/dav*` bypasses it. A small Cloudflare Worker on `/dav*` can
check the app password there instead and turn wrong ones away before they reach the server. With the edge check's three
settings stored for the whole suite (Settings › Global settings › Keys and tokens), the app keeps the Worker's KV namespace up to date with a SHA-256 of each app password (never the account
password). The Worker, the rollout (monitor first, then enforce) and a WAF rate-limit rule for `/dav*` are in
[iosuite-shared's cloudflare/edge-auth](https://github.com/avandeputte/iosuite-shared/blob/main/cloudflare/edge-auth/README.md). Once it enforces, DAV clients must sign in with an app password, not the
account password.

## API

| For | Standard | Where |
| --- | --- | --- |
| Reminders and tasks apps, two-way: Apple Reminders (iPhone, iPad, Mac), DAVx⁵ with Tasks.org, jtx Board or OpenTasks on Android, Thunderbird, Evolution, GNOME, KDE | **CalDAV** (RFC 4791) with to-dos (`VTODO`): each list is a calendar collection that takes only to-dos, which is how Reminders tells a task list from a calendar; sync-collection (RFC 6578), getctag, MKCALENDAR and extended MKCOL (a list made in Reminders is made here), PROPPATCH (name, colour, description, order), calendar-query, calendar-multiget, If-Match / If-None-Match, discovery via `/.well-known/caldav` (RFC 6764) and current-user-principal | `https://host/dav/` |
| Any app that reads calendar files | **iCalendar** (RFC 5545): every task is kept as the `VTODO` it came in as, so properties ioTasks does not edit (other apps' X- properties, Apple's sort order) survive a round trip; `DUE`, `RRULE`, `VALARM`, `PRIORITY`, `RELATED-TO` (subtasks) and `CATEGORIES` included | CalDAV, `/api/tasks/<id>?format=ics`, import/export |
| Web and JSON clients | **REST/JSON**, and iCalendar by content negotiation (`Accept: text/calendar`): lists, tasks with filters (due, a range of days, status, member, words), a task from one line of plain English (`{"text": …}`, previewed by `/api/quick`), ticking off, postponing, subtasks, the order by hand, the activity log and undo, templates, import/export | `/api/`, OpenAPI docs at `/api/docs` |
| iPhone, iPad and Mac in one step | **Apple configuration profile** (`com.apple.caldav.account`) | Settings › Apps and devices |
| AI assistants: Claude and anything else that speaks MCP | **Model Context Protocol** (streamable HTTP, and stdio) | `https://host/mcp` (switched on in Settings › Server) |

**iPhone, iPad and Mac in one step:** Settings › Apps and devices › *Download the profile* gives a configuration profile
(`.mobileconfig`) with the CalDAV account and a new CalDAV-only app password for that device inside (or none, and the device asks).
Open the page in Safari on the iPhone, tap Download, then Settings › Profile Downloaded › Install. The lists then appear
in Reminders under the account "ioTasks".

What Reminders keeps for an account that is not iCloud is the standard part: title, notes, due date and time, repeat,
alert, priority, done. Subtasks made here arrive there as ordinary tasks of the list, and Reminders' own tags, flags
and sections stay on iCloud lists.

Settings › Apps and devices shows the exact addresses to type; Settings › Account makes **app passwords**: one per phone or app,
revocable on its own, used with your user name for CalDAV and the REST API (HTTP Basic, or
`Authorization: Bearer <app password>`). An app password can be made **CalDAV only**: it opens `/dav` and nothing
else, so one lifted from a phone cannot reach the REST API, MCP or the web app (403). The Apple profile's password is
always CalDAV only; scripts and AI assistants need one without that limit. The scope is kept with the password in
the Shared ioSuite database (`ios_app_passwords.scope`), the same for every app of the suite.

```sh
curl -u alex:APP-PASSWORD "https://tasks.example.com/api/tasks?due=today"
curl -u alex:APP-PASSWORD -H 'Accept: text/calendar' https://tasks.example.com/api/tasks/12
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"title": "Take out the bins", "due": "2026-11-12T19:00", "rrule": "FREQ=WEEKLY", "priority": "high"}' \
  https://tasks.example.com/api/tasks
curl -u alex:APP-PASSWORD -X POST https://tasks.example.com/api/tasks/7/complete
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"text": "Call the bank tomorrow 5pm !high", "timezone": "Europe/Brussels"}' https://tasks.example.com/api/tasks
curl -u alex:APP-PASSWORD "https://tasks.example.com/api/tasks?from=2026-11-16&to=2026-11-22"   # due that week
curl -u alex:APP-PASSWORD "https://tasks.example.com/api/activity?limit=20"
```

Every change answers with `undo`, the step it was; `POST /api/undo/<step>` takes it back (400 once the task was changed again).

## MCP server

ioTasks is also an MCP server, as the other io apps are, so an assistant such as Claude can work with the lists:
read what is due, search tasks, add, change, tick off, move and delete them, make lists, add a template's tasks,
import iCalendar files, see who did what lately and take a change back (undo), and, for admins, check the server's
health, look for a new version and install it.

It is off until an admin turns it on in **Settings › Server** (or `MCP=1` in the environment); off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account, with its rights.

```sh
claude mcp add --transport http iotasks https://tasks.example.com/mcp --header "Authorization: Bearer APP-PASSWORD"
```

On the server itself, `.venv/bin/python -m app.mcp --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_lists`, `list_family_members`, `list_tasks`, `search_tasks`, `get_task`, `get_ics`,
`connection_details`; `create_task`, `update_task`, `complete_task`, `delete_task`, `move_task`, `create_list`,
`import_ics`; and for admins `diagnostics`, `list_accounts`, `check_for_update`, `update_server`.

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: lists and roles, every task field round-tripping through JSON and iCalendar, the due filters and counts,
ticking off (and a repeating task moving on), subtasks, family members, import and export, the Apple profile, app
passwords, CalDAV discovery, PUT with preconditions (and events refused), calendar-query, multiget, sync-collection
with deletions, MKCALENDAR and PROPPATCH, and the MCP server (switch, sign-in, the tools). CI runs
them against MariaDB.

## Layout

```
app/main.py        the application: start-up (tables, first admin), who is asking, routes
app/api.py         the REST API: lists, tasks, ticking off, postponing, activity and undo, templates, import/export, connection details, Apple profile
app/caldav.py      CalDAV / WebDAV (to-dos)
app/ical.py        iCalendar: reading, indexing, editing and writing VTODOs, moving a repeating task on
app/quick.py       smart quick add: a line of plain English as a task's fields
app/model.py       lists and tasks in MariaDB, sync tokens and tombstones for CalDAV, the activity log and undo, the order by hand, templates
app/members.py     family members on tasks (kept as CATEGORIES), and the member filter
app/mcp/           the MCP server: base (the server, finding tasks; who is asking comes from iosuite_shared.mcp), read, write and admin tools
app/access.py      who may call a route (the markers come from iosuite-shared)
app/users.py       accounts and app passwords (the suite's, through iosuite-shared)
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](LICENSE).
