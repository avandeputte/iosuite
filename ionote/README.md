# ioNotes

*Your notes, clipboard snippets and screenshots, searchable everywhere.*

The server behind ionotes: a web app for reading, writing and organising notes from any browser, and the API the
ionotes apps for Mac and iPhone/iPad use ([ionotes-apps](https://github.com/avandeputte/ionotes-apps)). Everything is kept
in one MariaDB/MySQL database, pictures included. It is built the same way as its sibling
[iopix](https://github.com/avandeputte/iopix): FastAPI with a single-page vanilla JS app, the same accounts, roles
and sign-in (Cloudflare Access too), the same installer, updater, Docker image and MCP server.

## What it does

- **Notes**: a title, text, tags, a folder, a pin, and optionally a picture (a screenshot, a photo) with the text
  read from it. Notes come from the Mac (clipboard, screenshots, right-click › Save to ionotes), the iPhone (paste,
  photos, the share sheet), the web app, or an assistant through MCP.
- **Web app**: folders and tags in the sidebar (right-click one to rename it, give it a colour or delete it; drag a
  note onto a folder to file it), all notes / pinned / pictures / no folder / trash, sorting, full-text search,
  editing that saves as you type, pictures pasted (⌘V) or dropped anywhere become notes, copy text or picture,
  download. Installs like an app on a phone (PWA); light, dark or the device's theme. Laid out like iopix: the
  sidebar (dockable) has the views, Folders, Tags and Manage (trash, change log, import and export), with Settings at its
  foot; the search, New note and your account are along the top. On a phone the sidebar is a bottom bar with More.
- **Markdown and checklists**: a note's text is shown formatted (headings, **bold**, lists, links, code, quotes), and
  `- [ ]` lines are boxes you tick right there, on the list card as progress (2/5). The pencil (or a click on the text)
  edits it; Enter continues a list, ⇧⌘L makes the lines a checklist.
- **Attached files**: besides its picture a note holds up to 50 files (PDFs, more pictures, documents; up to
  `MAX_IMAGE_MB` each), kept in the database too. A PDF's text, a text file's and (with RapidOCR) a picture's are read
  for search. Drop files on an open note to attach them, or on the list to make a note of each.
- **Templates** (Manage › Templates, New note ▾): a title, text, tags and a folder for new notes; `{{date}}`,
  `{{time}}`, `{{datetime}}`, `{{weekday}}`, `{{month}}`, `{{year}}`, `{{tomorrow}}` and `{{yesterday}}` are filled in
  when a note is made. The apps sync them.
- **Related notes and suggestions**: under each note, the notes most like it (words and tags in common), and the tags
  and folder those notes suggest for it, one click to apply.
- **Trash**: deleted notes stay 30 days, then they are deleted for good (text, picture, files; a tombstone stays so
  every device drops the note too). Empty trash and Delete for good do it at once.
- **Search**: every word you type must match (prefix) in the title, the text, the text in the picture or the tags,
  or in one of its attached files, through MariaDB's full-text index.
- **Text in pictures**: read on the device where the picture was taken (Apple's Vision framework, on the Mac and
  iPhone), and sent along; for pictures added in the web app the server reads it itself with RapidOCR.
- **Settings**: Account (with your app passwords) and Display for everyone signed in (the same panels as every io app), Server for admins; a change is saved the moment it is made.
- **Settings › Security** (suite admins): the whole suite's people and their role in every app, app passwords, keys and tokens, the apps (default role, sign-in required) and sign-in at the proxy; the same panel as on the start page and in every io app (iosuite-shared's `/api/suite-admin/ui.js`).
- **Offline**: the apps keep a full copy and send their changes when the server can be reached; the API settles
  conflicts per note by the time of the edit (below).
- **The clipboard Inbox stays on each device.** Only notes you save go to the server.

## Run

```sh
git clone https://github.com/avandeputte/ionotes && cd ionotes
./setup.sh
```

Its last question, "Also install …?" (flag `--also iocalendar,ionotes`, `--also all`; `IONOTES_ALSO` in the environment), puts
other apps of the suite in this same machine, beside ionotes (`/opt/iocalendar/app` next to `/opt/ionotes/app`),
without asking the shared questions again: the same database server (each app gets its own database: `suite`,
`calendar`, `contacts`, `notes`, `health`, `iopix`; the user needs rights on those names too), the same Shared ioSuite
database, sign-in domain and admin (`iosuite-shared install`, from the shared library). Each app keeps its usual port
and updates itself as always. The Proxmox installer offers the same as a checklist, for one container with several apps.

The databases and users need not exist beforehand: give a MariaDB / MySQL administrator (the question after the
databases; flag `--db-admin USER:PASSWORD`, or `IONOTES_DB_ADMIN`, also in the Proxmox installer) and `setup.sh` creates
the app's database and user, the Shared ioSuite database and user and, with other apps installed alongside, their
databases too, with the passwords you answered (`iosuite-shared provision`). Nothing is dropped, and the administrator's
password is used once and not written anywhere.

`setup.sh` is the installer: it asks where the MariaDB/MySQL database is (host, port, database, user, password;
it tests the connection and creates the database when the user may), where the **Shared ioSuite database** is
(below; database and user `iosuite` by default, tested and created the same way), the port (8610), whether pictures added in the
web app should have their text read (RapidOCR, ~60 MB), an admin account, and whether to start ionotes at login
(launchd on macOS, systemd on Linux). Then it creates the Python environment, installs the packages, writes
`config.env`, creates the tables and the admin, and starts the service. Run it again at any time. Flags skip the
questions (`./setup.sh --help`), e.g.

```sh
IONOTES_DB=db.example.lan:3306/notes:notes:secret IONOTES_SUITE_DB=db.example.lan:3306/iosuite:iosuite:secret \
  IONOTES_ADMIN=alex:secret ./setup.sh --yes --features ocr
```

(the passwords in the environment stay off the command line). Without the service, `./run.sh` starts it in the
foreground. `--sqlite` keeps everything in a SQLite file in the data folder instead, for a quick try.

The database user needs to create tables in its database (`GRANT ALL ON notes.* TO 'notes'@'%'`). Pictures are
stored in the database: MariaDB's `max_allowed_packet` (16 MB by default) must be larger than the largest picture
(`MAX_IMAGE_MB`, 15 MB); `setup.sh` warns when it is not.

### Proxmox VE (LXC)

`proxmox/ct/ionotes.sh` and `proxmox/install/ionotes-install.sh` follow the community-scripts (ProxmoxVE) framework
layout, the same as iopix's, so they can be submitted upstream as they are. Until then the ct script points the
framework at this repository for the install script (`COMMUNITY_SCRIPTS_URL`), while the engine itself comes from
community-scripts. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/ionotes/main/proxmox/ct/ionotes.sh)"
```

It asks about the app first: whether the notes live in MariaDB/MySQL (host, port, database, user, password; the
defaults are 127.0.0.1, 3306, `notes`, `notes`) or in a SQLite file in the container, where the Shared ioSuite
database is (host, port, database, user, password; database and user `iosuite` by default), whether pictures added in
the web app get their text read (RapidOCR), and the admin account; then the framework's own questions (resources,
network). It creates an unprivileged Debian 13 container (2 CPU, 2 GB, 8 GB disk by default) and runs the app's own
`setup.sh` inside with those answers: packages, settings, tables, admin, and the `ionotes` service on port 8610.
For unattended runs set `IONOTES_DB` (`sqlite` or `host:port/db:user:pass`), `IONOTES_SUITE_DB`
(`host:port/db:user:pass`), `IONOTES_FEATURES` (`ocr` or `none`)
`IONOTES_ADMIN` (`name:password`, or empty for none yet), `IONOTES_PUBLIC_URL` and `IONOTES_COOKIE_DOMAIN` in the environment. The passwords reach `setup.sh`
inside the container through its environment (a root-only file pushed in and removed again), not on a command line.
The setup's output is kept in `/opt/ionotes/setup.log`; on failure its last lines are shown and the command to rerun
it is printed. The container's `update` command runs `update.sh`, which keeps the settings and data. The scripts are
checked for syntax in CI and drive the tested `setup.sh`; they have not been run on a Proxmox host yet.

### Docker

`docker-compose.yml` pulls the published image (`ghcr.io/avandeputte/ionotes:latest`, built by the GitHub workflow
for amd64 and arm64) and works as a stack in Dockge or Portainer: set the database and the admin password and start
it; `docker compose up -d --build` builds from the checkout instead. The container runs as its own user (uid 1000);
the named volume `ionotes-data` at `/data` only holds the session secret and the log, since everything else is in
the database. The image includes RapidOCR (build argument `OCR=0` leaves it out). The health check polls
`/api/status`, which stays open when sign-in is required.

## Configuration

The settings are in `config.env` in the app folder (`setup.sh` writes it; every app of the suite uses the same file
name and the same names), or in the environment, which wins. `config.env.example` lists them all.

| Variable | Default | |
| --- | --- | --- |
| `DB_TYPE` | `sqlite` | `mysql` for MariaDB/MySQL (setup.sh writes it) |
| `DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | | the database |
| `HOST` / `PORT` | `0.0.0.0` / `8610` | where the server listens (every app of the suite has its own port) |
| `TLS_CERT_FILE` / `TLS_KEY_FILE` | | HTTPS served directly instead of behind a reverse proxy |
| `DATA_DIR` | `./data` | what the app writes on its own: the log, the update result (and the SQLite file) |
| `LOG_FILE` | `DATA_DIR/ionotes.log` | the server log (empty: none) |
| `PUBLIC_URL` | | the address ionotes is reached at, for links in MCP answers and the suite's list of apps |
| `COOKIE_DOMAIN` | | the domain the sign-in is shared on (e.g. `example.com`); a LAN address outside it gets a cookie of its own |
| `ADMIN_USER` / `ADMIN_PASSWORD` | | the first admin, created on a first start with no accounts |
| `IOSUITE_DB_HOST` / `_PORT` / `_NAME` / `_USER` / `_PASSWORD` | `DB_HOST` / `DB_PORT` / `iosuite` / `iosuite` / none | the Shared ioSuite database (MariaDB): accounts, sessions, suite-wide settings |
| `TZ` | | the time zone |
| `OCR` | `1` | `0`: the server never reads text in pictures (the apps still do) |
| `MAX_IMAGE_MB` | `15` | the largest picture a note may carry (and at most 40 megapixels) |
| `KEEP_DELETED_DAYS` | `90` | how long the change log's entries and the names of deleted folders are kept; after that only an empty marker stays, so devices still learn of the deletion (a deleted note goes sooner: after its 30 days in the trash) |
| `MCP` / `MCP_USER` | | `MCP=1` keeps the endpoint on whatever Settings says; the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `1` | `0`: never ask GitHub for a newer version (Settings › Server) |
| `AUTH_PROXY`... | `off` | sign-in at a reverse proxy, above |

## Updates

- **Standalone:** `./update.sh` fetches the latest code (git, or the GitHub tarball), installs the packages the new
  version asks for and only then moves the code in, then restarts the service. `--check` only reports. Settings ›
  Server › Update now runs the same script; the page (the same in every ioThing app: it comes from
  iosuite-shared, at `/api/server/ui.js`, `/api/server` and `/api/log`) also has the tail of the server log
  (`data/ionotes.log`) and Restart. A daily check (on by default; `UPDATE_CHECK=0` locks it off, the page switches it
  off) shows admins a card when a newer version exists, with Update now right on it (dismissed per version).
- **Proxmox:** `update` inside the container (the framework's command) runs the same script.
- **Docker:** `docker compose pull && docker compose up -d`.
- **From an MCP client:** `check_for_update` and `update_ionotes` (as an admin).

## Reverse proxy and HTTPS

ionotes speaks plain HTTP on port 8610. Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy
Manager, HAProxy, a Cloudflare Tunnel) and reach it only through that; `/mcp` streams responses, so the proxy must not
buffer that path.

When the proxy already makes people sign in, ionotes takes that sign-in, exactly as iopix does: the proxy passes who
signed in in a header, and ionotes treats that person as signed in when an account exists for them (matched on the
account's email address, then its name). Settings › Security › Sign-in at the proxy (saved there, the settings are kept in the
Shared ioSuite database for the whole suite: one Cloudflare Access application covering every app, set up once), or
in `config.env`, which wins:

| Variable | |
| --- | --- |
| `AUTH_PROXY` | `cloudflare`, `haproxy`, `nginx`, `caddy`, `traefik` or `header`; `off` by default |
| `AUTH_PROXY_HEADER` | the header(s) with the user; default for `cloudflare`: `Cf-Access-Authenticated-User-Email`; for the others: `Remote-User`, `X-Forwarded-User`, `X-Auth-Request-User`, `X-Auth-Request-Email`, `X-Forwarded-Email` |
| `AUTH_PROXY_TRUSTED` | addresses or networks the proxy connects from; default `127.0.0.1,::1` |
| `AUTH_PROXY_CREATE` | `viewer` or `editor`: create an account for someone the proxy lets in who has none; `deny`: a "No access" page; empty: the sign-in screen |
| `CF_ACCESS_TEAM` / `CF_ACCESS_AUD` | your Cloudflare Access team domain and the application's AUD tag: the signed token Cloudflare adds to every request (`Cf-Access-Jwt-Assertion`) is checked against your team's keys, and the email is taken from it. The recommended setup for a Cloudflare Tunnel |

The header is believed only from the proxy: a request that reaches ionotes any other way is ignored, whatever headers
it carries. From outside (through Cloudflare), one-click accounts without a password do not work. The Mac and iPhone
apps sign in through the same page; for unattended use through Cloudflare they take a Cloudflare Access **service
token** (client ID and secret, kept in the Keychain), as the iopix apps do.

## Users and permissions

Accounts are the **ioThing suite's shared accounts**, kept in the **Shared ioSuite database** (a MariaDB database
shared with iopix and ioContacts, used through the ioSuite shared library, [`iosuite-shared`](https://github.com/avandeputte/iosuite-shared); besides the accounts it holds sessions,
roles, the suite's list of apps and the suite-wide settings), so one name, password and session serve every app, and
someone signed in at `photo.example.com` is signed in at `notes.example.com` too when the apps share a domain
(`COOKIE_DOMAIN`). What is ionotes' own is kept per app: the role an account holds here and its settings. A
*suite admin* is admin in every app. Point ionotes at that database with `IOSUITE_DB_HOST`, `IOSUITE_DB_PORT`,
`IOSUITE_DB_NAME`, `IOSUITE_DB_USER` and `IOSUITE_DB_PASSWORD` in `config.env` (database and user `iosuite` and the notes' server by
default; the tables are created at start; `iosuite-shared migrate --ionotes`
folds a 1.0 install's `user_accounts` table into it). Settings › Server › This server shows which database it is. Out of the box ionotes is open to anyone who can reach it;
`setup.sh` (or `ADMIN_USER` / `ADMIN_PASSWORD`, or the person icon in the web app) creates the admin. Once an
account exists:

**Notes are private to each account.** Every note, folder, tag colour and change-log line belongs to the account
that made it; nobody else sees, searches, syncs, exports or changes it, admins included (their extra rights are
about the server, not other people's notes). The notes made while the install was still open (before the first
account) stay with the open install: export them before making the first account and import them after. A note id that belongs to another account is answered as if it did not exist.

| Who | Can |
| --- | --- |
| Not signed in | nothing but the sign-in screen (there are no shared notes to read) |
| **viewer** | read and search their own notes; their own settings kept on the server |
| **viewer without a password** | the same; signs in with one click from the account picker, on the home network only |
| **editor** | plus every change to their own notes, folders and tags, and export/import of them (Import and export; the Mac and iPhone apps sign in as an editor) |
| **admin** | plus settings, accounts, updates and the server log |

**Sign-in required** (Settings › Global settings › Apps) also closes the open routes to visitors, but for the app shell, `/api/status` and the sign-in routes (the MCP endpoint wants an app password either way).
Sessions are random tokens in an HttpOnly cookie (`iothing_session`, shared by the apps on the domain) valid for
30 days and renewed while in use; each records where it began and was last seen (address, through Cloudflare or
not, web or which app): `GET /api/auth/sessions` for your own, `GET /api/users/<id>/sessions` for admins. Passwords
are Argon2id-hashed; wrong passwords cost a growing wait. Write requests from another site are refused.

ionotes writes its row in the **suite's list of apps** (iosuite-shared's `suite_apps` table: name, version, colour,
icon, address) on its first request, so ioSuite's start page and the other apps find it without anyone typing an
address. The address is `PUBLIC_URL` when set, otherwise the best one ionotes is reached at (a host under
`COOKIE_DOMAIN` over HTTPS beats a LAN name, which beats an IP address).

## API

Every route is under `/api`; `GET /api/docs` lists them. JSON in and out; times are seconds since 1970 (UTC); ids are
UUID strings the device chooses (`UUID().uuidString`).

| | |
| --- | --- |
| `GET /api/status` | version, whether sign-in is required, and (signed in) the current `rev` |
| `POST /api/auth/login` `{name, password}` | signs in; the session cookie follows. `GET /api/auth/me`, `POST /api/auth/logout` |
| `GET /api/sync?since=<rev>&limit=500` | every note, folder, tag colour and template changed after `rev`, deletions included (`deleted: true`), oldest change first; ask again with `since=<rev>` while `more` is true. A new device starts from 0 |
| `PUT /api/notes/{id}` | create or update a note: any of `title, body, ocrText, source, sourceApp, createdAt, tags, pinned, folderID, deleted`, plus `updatedAt`, when the edit was made on the device |
| `POST /api/sync/push` `{notes:[], folders:[], tags:[]}` | a device's queued offline changes in one request; each answered with `ok` or `stale` and the server's copy |
| `PUT /api/notes/{id}/image` | the picture as the raw body (`Content-Type: image/png`...); `GET` it back, or `/thumb` for a 480 px JPEG. `imageSHA` on the note changes with the picture |
| `DELETE /api/notes/{id}?ts=` | to the trash (a tombstone that syncs); `POST /api/notes/{id}/restore` |
| `PUT /api/folders/{id}` `{name, color, deleted, updatedAt}` | folders; `PUT /api/tags/{name}/color` `{color, updatedAt}` for tag colours |
| `GET /api/notes?q=&folder=&tag=&pinned=&image=&sort=` | search and list (the web app's view) |
| `PUT /api/notes/{id}/attachments/{aid}?name=` | attach a file (raw body, its `Content-Type`; `X-Ionotes-Text`: text the device read from it, percent-encoded). Each note lists its files under `attachments` (`id, name, mime, bytes, sha, width, height`); `GET …/{aid}` (`?download=1`), `…/{aid}/thumb`, `…/{aid}/text`, `PATCH {name}`, `DELETE` |
| `PUT /api/templates/{id}` `{name, title, body, tags, folderID, deleted, updatedAt}` | templates (also in `/api/sync` as `templates`, and in a push); `POST /api/notes {template: id}` makes a note from one |
| `GET /api/notes/{id}/related` | notes like this one, and the tags and folder they suggest: `{notes, tags, folder}` |
| `POST /api/trash/empty`, `DELETE /api/trash/{id}` | delete for good; notes in the trash are purged after 30 days anyway (they sync as tombstones with nothing in them) |

**Conflicts**: each note, folder and tag colour is settled on its own by `updatedAt`. The server never takes an `updatedAt` later than its own clock, so a device whose clock runs ahead does not win every conflict. A change older than what the
server has is answered with 409 (or `stale` in a push) and the server's copy, which the device then keeps. An empty
`ocrText` never erases text read earlier. Every change gets a new `rev`, from one counter, which is what `since` counts.

## MCP server

Settings › Server turns on an MCP endpoint at `/mcp` (off by default), the same in every app of the
suite. An assistant such as Claude can then:

- read: `notes_overview`, `search_notes` (words, folder, tag, pinned, picture, source, dates, sort), `get_note`,
  `view_note_image` (the picture itself, small or large), `read_attachment` (a file's text, or the picture),
  `list_folders`, `list_tags`, `list_templates`, `recent_changes`, `list_trash`
- help: `related_notes` (notes like one, with the tags and folder they suggest), `suggest_organization` (tags and
  folders for unfiled notes), `notes_digest` (a period's notes with their text, to summarise); and three prompts the
  client can offer: *Summarise a note*, *Weekly review*, *Tidy up unfiled notes*
- write, as an editor: `create_note` (optionally with a picture, or from a template), `update_note` (replace or append
  text, tags, folder, pin), `organize_notes` (many notes at once), `delete_note`, `restore_note`, `manage_folder`,
  `manage_tag`, `manage_template`, `attach_file`, `remove_attachment`, `empty_trash`
- operate, as an admin: `diagnostics`, `server_log`, `check_for_update`, `update_ionotes` (the tip of the branch only)

Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account: notes are private to each account, so it sees and
changes that account's notes and nothing else (`notes_overview` names the account). Off, `/mcp` does not answer at all.

```sh
claude mcp add --transport http ionotes https://notes.example.com/mcp --header "Authorization: Bearer ionotes-xxxxxxxx-…"
```

Apps that take a JSON configuration and only start local processes (Claude Desktop, for example) can reach it through
`mcp-remote`: `{"mcpServers": {"ionotes": {"command": "npx", "args": ["-y", "mcp-remote", "https://notes.example.com/mcp", "--header", "Authorization: Bearer ionotes-…"]}}}`.
`python -m app.mcp --user NAME` (or `MCP_USER`) serves the same tools on stdio, as that account.

## Export, import and backups

Import and export (the sidebar) › Export downloads every note as Markdown (with front matter: id, dates, tags, source) next to its picture and its files,
in a directory per folder, plus `notes.json` with everything. Such a zip imports again on any ionotes server (Import
and export › Import): records keep their ids, and a newer copy on the server wins (a zip from another account on the same server comes in as new notes). For backups, back the database up
(`mariadb-dump --single-transaction notes`): notes, pictures, accounts and settings are all in it.

## Tests

`pip install -e '.[test]' && pytest tests` (SQLite for the notes), and `IONOTES_TEST_DB=mysql pytest tests` with a
MariaDB database `notes_test` for the user `notes`/`notes` on 127.0.0.1 (`IONOTES_TEST_DB_HOST` and friends change that).
The Shared ioSuite database always goes to a test MariaDB of its own: a Docker container the suite starts
(`iosuite-test-mariadb`), or `IOSUITE_TEST_DB=host:port:user:password`; never a live `iosuite` database.
CI runs both.

## Layout

```
app/
  main.py          the FastAPI app: the suite's middleware (who is asking, require sign-in, cross-site writes), whose notes, status, /mcp, static files
  access.py        who may call a route: the markers every /api route carries
  config.py        the settings: the suite's standard names (iosuite_shared.config) and ioNotes' own
  db.py            the database (MariaDB/MySQL or SQLite), its tables, the rev counter
  notes.py         notes, folders, tag colours, templates, search, related notes, the trash, sync and conflicts
  images.py        pictures as BLOBs with a thumbnail
  attachments.py   files attached to notes (PDFs and the like), with the text read from them
  ocr.py           RapidOCR for pictures added in the web app
  backup.py        export and import
  auth.py          accounts, sessions and roles, the updater (iosuite-shared; proxy sign-in: iosuite_shared.proxyauth through auth.proxy)
  routes/          the HTTP API
  mcp/             the MCP server: read, write and operator tools
proxmox/           Proxmox VE LXC scripts in the community-scripts layout
static/            the web app (index.html, app.css, js/*.js modules, service worker, icons)
tests/             pytest; IONOTES_TEST_DB=mysql runs them on MariaDB
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](LICENSE).
