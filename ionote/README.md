# ionotes

*Your notes, clipboard snippets and screenshots, searchable everywhere.*

The server behind ionotes: a web app for reading, writing and organising notes from any browser, and the API the
ionotes apps for Mac and iPhone/iPad use ([ionotes-apps](https://github.com/avandeputte/ionotes-apps)). Everything is kept
in one MariaDB/MySQL database, pictures included. It is built the same way as its sibling
[iopix](https://github.com/avandeputte/iopix): FastAPI with a single-page vanilla JS app, the same accounts, roles
and sign-in (Cloudflare Access too), the same installer, updater, Docker image and MCP server.

- **Notes**: a title, text, tags, a folder, a pin, and optionally a picture (a screenshot, a photo) with the text
  read from it. Notes come from the Mac (clipboard, screenshots, right-click › Save to ionotes), the iPhone (paste,
  photos, the share sheet), the web app, or an assistant through MCP.
- **Web app**: folders and tags in the sidebar (right-click one to rename it, give it a colour or delete it; drag a
  note onto a folder to file it), all notes / pinned / pictures / no folder / trash, sorting, full-text search,
  editing that saves as you type, pictures pasted (⌘V) or dropped anywhere become notes, copy text or picture,
  download. Installs like an app on a phone (PWA); light, dark or the device's theme.
- **Search**: every word you type must match (prefix) in the title, the text, the text in the picture or the tags,
  through MariaDB's full-text index.
- **Text in pictures**: read on the device where the picture was taken (Apple's Vision framework, on the Mac and
  iPhone), and sent along; for pictures added in the web app the server reads it itself with RapidOCR.
- **Offline**: the apps keep a full copy and send their changes when the server can be reached; the API settles
  conflicts per note by the time of the edit (below).
- **The clipboard Inbox stays on each device.** Only notes you save go to the server.

## Run

```sh
git clone https://github.com/avandeputte/ionotes && cd ionotes
./setup.sh
```

`setup.sh` is the installer: it asks where the MariaDB/MySQL database is (host, port, database, user, password;
it tests the connection and creates the database when the user may), the port (8610), whether pictures added in the
web app should have their text read (RapidOCR, ~60 MB), an admin account, and whether to start ionotes at login
(launchd on macOS, systemd on Linux). Then it creates the Python environment, installs the packages, writes
`ionotes.env`, creates the tables and the admin, and starts the service. Run it again at any time. Flags skip the
questions (`./setup.sh --help`), e.g.

```sh
IONOTES_MYSQL=192.168.1.89:3306/notes:notes:secret IONOTES_ADMIN=alex:secret ./setup.sh --yes --features ocr
```

(the passwords in the environment stay off the command line). Without the service, `./run.sh` starts it in the
foreground. `--sqlite` keeps everything in a SQLite file in the data folder instead, for a quick try.

The database user needs to create tables in its database (`GRANT ALL ON notes.* TO 'notes'@'%'`). Pictures are
stored in the database: MariaDB's `max_allowed_packet` (16 MB by default) must be larger than the largest picture
(`MAX_IMAGE_MB`, 15 MB); Settings › Database warns when it is not.

## Running in Docker

`docker-compose.yml` pulls the published image (`ghcr.io/avandeputte/ionotes:latest`, built by the GitHub workflow
for amd64 and arm64) and works as a stack in Dockge or Portainer: set the database and the admin password and start
it; `docker compose up -d --build` builds from the checkout instead. The container runs as its own user (uid 1000);
the named volume `ionotes-data` at `/data` only holds the session secret and the log, since everything else is in
the database. The image includes RapidOCR (build argument `OCR=0` leaves it out). The health check polls
`/api/status`, which stays open when sign-in is required.

## Users and permissions

The same model as iopix, down to the database tables (`user_accounts`, `app_settings`), so the two can later share
one set of accounts. Out of the box ionotes is open to anyone who can reach it; `setup.sh` (or `ADMIN_USER` /
`ADMIN_PASSWORD`, or the person icon in the web app) creates the admin. Once an account exists:

| Who | Can |
| --- | --- |
| Not signed in | read and search the notes |
| **viewer** | the same, plus their own settings kept on the server |
| **viewer without a password** | the same; signs in with one click from the account picker, on the home network only |
| **editor** | plus every change to notes, folders and tags (the Mac and iPhone apps sign in as an editor) |
| **admin** | plus settings, accounts, export/import, the MCP token, updates and the server log |

**Require sign-in** (Settings › Sign-in) turns the open reading off: visitors get the sign-in screen and nothing else.
Sessions are signed HttpOnly cookies (secret in `data/secret`) valid for 30 days and renewed while in use; passwords
are scrypt-hashed; wrong passwords cost a growing wait. **Read-only** (Settings, or `READ_ONLY=1`) refuses every
change, for everyone. Write requests from another site are refused.

## Reverse proxy, HTTPS and Cloudflare Access

ionotes speaks plain HTTP on port 8610. Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy
Manager, HAProxy, a Cloudflare Tunnel) and reach it only through that; `/mcp` streams responses, so the proxy must not
buffer that path.

When the proxy already makes people sign in, ionotes takes that sign-in, exactly as iopix does: the proxy passes who
signed in in a header, and ionotes treats that person as signed in when an account exists for them (matched on the
account's email address, then its name). Settings › Sign-in at the proxy, or in `ionotes.env`:

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

## The API (for the apps)

Every route is under `/api`; `GET /api/docs` lists them. JSON in and out; times are seconds since 1970 (UTC); ids are
UUID strings the device chooses (`UUID().uuidString`).

| | |
| --- | --- |
| `GET /api/status` | version, whether sign-in is required, and (signed in) the current `rev` |
| `POST /api/auth/login` `{name, password}` | signs in; the session cookie follows. `GET /api/auth/me`, `POST /api/auth/logout` |
| `GET /api/sync?since=<rev>&limit=500` | every note, folder and tag colour changed after `rev`, deletions included (`deleted: true`), oldest change first; ask again with `since=<rev>` while `more` is true. A new device starts from 0 |
| `PUT /api/notes/{id}` | create or update a note: any of `title, body, ocrText, source, sourceApp, createdAt, tags, pinned, folderID, deleted`, plus `updatedAt`, when the edit was made on the device |
| `POST /api/sync/push` `{notes:[], folders:[], tags:[]}` | a device's queued offline changes in one request; each answered with `ok` or `stale` and the server's copy |
| `PUT /api/notes/{id}/image` | the picture as the raw body (`Content-Type: image/png`...); `GET` it back, or `/thumb` for a 480 px JPEG. `imageSHA` on the note changes with the picture |
| `DELETE /api/notes/{id}?ts=` | to the trash (a tombstone that syncs); `POST /api/notes/{id}/restore` |
| `PUT /api/folders/{id}` `{name, color, deleted, updatedAt}` | folders; `PUT /api/tags/{name}/color` `{color, updatedAt}` for tag colours |
| `GET /api/notes?q=&folder=&tag=&pinned=&image=&sort=` | search and list (the web app's view) |

**Conflicts**: each note, folder and tag colour is settled on its own by `updatedAt`. A change older than what the
server has is answered with 409 (or `stale` in a push) and the server's copy, which the device then keeps. An empty
`ocrText` never erases text read earlier. Every change gets a new `rev`, from one counter, which is what `since` counts.

## MCP server

Settings › MCP server turns on an MCP endpoint at `/mcp` (off by default), in the same shape as iopix's. An assistant
such as Claude can then:

- read: `notes_overview`, `search_notes` (words, folder, tag, pinned, picture, source, dates, sort), `get_note`,
  `view_note_image` (the picture itself, small or large), `list_folders`, `list_tags`, `recent_changes`, `list_trash`
- write, with the admin token: `create_note` (optionally with a picture), `update_note` (replace or append text, tags,
  folder, pin), `organize_notes` (many notes at once), `delete_note`, `restore_note`, `manage_folder`, `manage_tag`
- operate, with the admin token: `diagnostics`, `server_log`, `proxy_signin`, `check_for_update`, `update_ionotes`

The admin token is shown to admins under Settings › MCP server (or set `MCP_ADMIN_TOKEN`). With Require sign-in on,
every `/mcp` request needs it as `Authorization: Bearer <token>` (Claude Desktop with `mcp-remote`:
`"args": ["mcp-remote", "https://notes.example.com/mcp", "--header", "Authorization: Bearer <token>"]`).
`python -m app.mcp` serves the same tools on stdio. Treat the token like the admin password.

## Export, import and backups

Settings › Export downloads every note as Markdown (with front matter: id, dates, tags, source) next to its picture,
in a directory per folder, plus `notes.json` with everything. Such a zip imports again on any ionotes server (admins,
Settings › Import): records keep their ids, and a newer copy on the server wins. For backups, back the database up
(`mariadb-dump --single-transaction notes`): notes, pictures, accounts and settings are all in it.

## Updating

- **Standalone:** `./update.sh` fetches the latest code (git, or the GitHub tarball), installs the packages the new
  version asks for and only then moves the code in, then restarts the service. `--check` only reports. Settings ›
  ionotes version › Update now runs the same script; a daily check (on by default; `UPDATE_CHECK=0` locks it off)
  shows admins when a newer version exists.
- **Docker:** `docker compose pull && docker compose up -d`.
- **From an MCP client:** `check_for_update` and `update_ionotes` (with the admin token).

## Settings

| Variable | Default | |
| --- | --- | --- |
| `DB_TYPE` | `sqlite` | `mysql` for MariaDB/MySQL (setup.sh writes it) |
| `DB_HOST` / `DB_PORT` / `DB_DATABASE` / `DB_USER` / `DB_PASSWORD` | | the database |
| `PORT` | `8610` | |
| `DATA_DIR` | `./data` | the session secret, the log (`ionotes.log`) and settings saved from the web app |
| `APP_URL` | `http://localhost:8610` | the address ionotes is reached at, for links in MCP answers |
| `ADMIN_USER` / `ADMIN_PASSWORD` | | the first admin, created on a first start with no accounts |
| `READ_ONLY` | `0` | nothing can be changed, by anyone |
| `OCR` | `1` | `0`: the server never reads text in pictures (the apps still do) |
| `MAX_IMAGE_MB` | `15` | the largest picture a note may carry |
| `MCP` / `MCP_ADMIN_TOKEN` | | `MCP=1` keeps the endpoint on whatever Settings says; the token, instead of a generated one |
| `UPDATE_CHECK` | `1` | `0`: never ask GitHub for a newer version |
| `AUTH_PROXY`... | `off` | sign-in at a reverse proxy, above |

## How it is put together

```
app/
  main.py          the FastAPI app: who is asking (cookie or proxy), require sign-in, cross-site writes, /mcp, static files
  db.py            the database (MariaDB/MySQL or SQLite), its tables, the rev counter
  notes.py         notes, folders, tag colours, search, sync and conflicts
  images.py        pictures as BLOBs with a thumbnail
  ocr.py           RapidOCR for pictures added in the web app
  backup.py        export and import
  users.py, proxyauth.py, access.py   accounts, sessions, roles and proxy sign-in (from iopix)
  updates.py       the version check, update.sh, the MCP admin token
  routes/          the HTTP API
  mcp/             the MCP server: read, write and operator tools
static/            the web app (index.html, app.css, js/*.js modules, service worker, icons)
tests/             pytest; IONOTES_TEST_DB=mysql runs them on MariaDB
```

Tests: `pip install -e '.[test]' && pytest tests` (SQLite), and `IONOTES_TEST_DB=mysql pytest tests` with a MariaDB
database `notes_test` for the user `notes`/`notes` on 127.0.0.1 (`IONOTES_TEST_DB_HOST` and friends change that).
CI runs both.
