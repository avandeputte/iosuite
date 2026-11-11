# ioRecipe

*The family's recipes, in the ioThing suite (with [ioPix](https://github.com/avandeputte/iopix), [ioNote](https://github.com/avandeputte/ionote), [ioContact](https://github.com/avandeputte/iocontact), [ioCalendar](https://github.com/avandeputte/iocalendar), [ioTask](https://github.com/avandeputte/iotask), [ioHealth](https://github.com/avandeputte/iohealth) and the [ioSuite](https://github.com/avandeputte/iosuite) start page).*

A self-hosted recipe book: a web app for the whole family to keep recipes with their ingredients, steps and a photo, and to import a recipe from the web by its address. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL (the photos too), and the suite's shared library (`iosuite-shared`, in [iosuite-shared](https://github.com/avandeputte/iosuite-shared)).

## What it does

- **Recipes** with a title, a description, what they make (4, or 24 cookies), preparation and cooking time, **ingredients**, **steps**, notes, tags, and where they come from. In the ingredients and the steps, a line that ends with a colon ("For the icing:") is a heading.
- **A photo** for each recipe: upload one from the computer or take one with the phone. It is turned upright, made smaller and kept as a JPEG in the database, with a small copy for the cards.
- **Import from the web**: paste the address of a recipe page and ioRecipe fetches it and keeps the recipe it describes (title, ingredients, steps, times, servings, tags) with its picture and a link back. It reads the schema.org Recipe data that most recipe sites publish for search engines (JSON-LD or microdata), not the page's layout; where a page has none, it says so. Only addresses on the internet are fetched, never this machine or the home network.
- **The recipes as cards**, with their photo, how long they take and what they make: all of them, the family's, your own, or the ones with a tag; **search** finds words in the title, the ingredients, the steps, the notes and the tags.
- **Cooking from it**: the ingredients have boxes to tick off as they go in, a step is struck out with a click, and the page prints as the recipe alone (the ⋯ menu, or the browser's Print).
- **Family and private recipes**: a family recipe is seen by everyone; a private one only by its owner. A recipe can be moved from one to the other.
- **Roles as in the other io apps**: viewers only read the family's recipes, members (the default) also keep private recipes of their own, editors change the family's recipes too, admins also manage users and settings. The same accounts, passwords and app passwords as the other io apps; one sign-in for all of them with a shared cookie domain.
- **Settings › Security** and **Global settings** (suite admins): the whole suite's people and their role in every app, app passwords and sign-in at the proxy; the apps, keys and tokens; the same panel as on the start page and in every io app (iosuite-shared's `/api/suite-admin/ui.js`).
- Light and dark, phone-sized screens, installable as an app.

## Run

ioRecipe needs Python 3.10+, git (to install `iosuite-shared` from the [iosuite-shared](https://github.com/avandeputte/iosuite-shared) repository) and a MariaDB or MySQL database. Give it its own database
and user, for example:

```sql
CREATE DATABASE recipe CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'recipe'@'%' IDENTIFIED BY 'recipe';
GRANT ALL ON recipe.* TO 'recipe'@'%';
```

The accounts and the suite-wide settings live in the Shared ioSuite database (`iosuite`, user `iosuite`; the one every
app of the suite uses); a new install of the suite creates it the same way. The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iorecipe.sh` and `proxmox/install/iorecipe-install.sh` follow the community-scripts (ProxmoxVE) framework layout, as the other io apps do. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iorecipe/main/proxmox/ct/iorecipe.sh)"
```

It asks for the recipe database (host, port, database, user, password), the Shared ioSuite database, the web port (8690), the time zone, the public address behind your reverse proxy (optional), the domain the sign-in is shared on (optional) and the admin account; then the framework's own questions (resources, network). It creates a small Debian 13 container and runs the app's own `setup.sh` inside with those answers. The passwords reach `setup.sh` through its environment (a root-only file pushed in and removed again), never on a command line; the output is kept in `/opt/iorecipe/setup.log`. The container's `update` command pulls the latest code and keeps the settings. For unattended runs set `IORECIPE_DB` and `IORECIPE_SUITE_DB` (`host:port/db:user:password`), `IORECIPE_ADMIN` (`name:password`), `IORECIPE_PORT`, `IORECIPE_TIMEZONE`, `IORECIPE_PUBLIC_URL` and `IORECIPE_COOKIE_DOMAIN`.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iorecipe`) holds no data: everything is in the database.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iorecipe && cd iorecipe
./setup.sh          # asks for the databases, port, time zone and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

Its last question, "Also install …?" (flag `--also iocalendar,ionote`, `--also all`; `IORECIPE_ALSO` in the environment), puts
other apps of the suite in this same machine, beside ioRecipe (`/opt/iocalendar/app` next to `/opt/iorecipe/app`),
without asking the shared questions again: the same database server (each app gets its own database: `suite`,
`calendar`, `contacts`, `notes`, `health`, `iopix`, `tasks`, `recipe`; the user needs rights on those names too), the same Shared ioSuite
database, sign-in domain and admin (`iosuite-shared install`, from the shared library). Each app keeps its usual port
and updates itself as always. The Proxmox installer offers the same as a checklist, for one container with several apps.

The databases and users need not exist beforehand: give a MariaDB / MySQL administrator (the question after the
databases; flag `--db-admin USER:PASSWORD`, or `IORECIPE_DB_ADMIN`, also in the Proxmox installer) and `setup.sh` creates
the app's database and user, the Shared ioSuite database and user and, with other apps installed alongside, their
databases too, with the passwords you answered (`iosuite-shared provision`). Nothing is dropped, and the administrator's
password is used once and not written anywhere.

`setup.sh` offers 127.0.0.1, database `recipe`, user `recipe`, password `recipe` as the defaults; its flags
(`--db`, `--suite-db`, `--admin`, `--port`, `--public-url`, `--cookie-domain`, `--service`, `--yes`) are the same in
every app of the suite. `python -m app.cli import URL` (a recipe from the web) and `check` work from a shell;
accounts are the suite's: `.venv/bin/iosuite-shared --config . admin NAME --app iorecipe` (password from
`ADMIN_PASSWORD`, or asked for) and `.venv/bin/iosuite-shared --config . password NAME`.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment, which wins:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`recipe`) |
| `IOSUITE_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the Shared ioSuite database (`iosuite`, on `DB_HOST` unless set): accounts, passwords, sessions, app passwords, roles and suite-wide settings, shared by every app of the suite |
| `COOKIE_DOMAIN` | the domain the session cookie is shared on (`example.com`): signed in at `calendar.example.com`, signed in at `recipes.example.com` too |
| `HOST`, `PORT` | where the server listens (`0.0.0.0`, 8690; every app of the suite has its own port) |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | serve HTTPS directly instead of behind a reverse proxy |
| `TZ` | the time zone the server log is written in (default: the server's) |
| `PUBLIC_URL` | the address people use (behind a proxy), for the links the MCP tools give |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD` | sign-in at a reverse proxy, as in the other io apps (Cloudflare Access, Authelia, Authentik, oauth2-proxy…) |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `IORECIPE_REPO`, `IORECIPE_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iorecipe`, `main`) |
| `DATA_DIR` | where the app writes on its own: the log and the update result (`data/` in the app folder) |
| `LOG_FILE` | the server log shown at Settings › Server (`DATA_DIR/iorecipe.log`; `LOG_FILE=` with nothing after it: no file) |

## Updates

ioRecipe asks GitHub once a day whether the main branch has a newer version (only the public commit list is read;
nothing about the server is sent; Settings › Server switches it off, `UPDATE_CHECK=0` locks it off). Admins
then see a note with **Update now**, and **Settings › Server** has the version, **Check for updates**,
**Update now**, what the server runs on, the tail of the server log (`data/iorecipe.log`; `LOG_FILE` moves it, empty switches it
off) and **Restart**. The page is the same in every ioThing app: the panel (`/api/server/ui.js`), the version check, `update.sh`, the
restart and the log come from iosuite-shared, served at `/api/server` and `/api/log`. Updating runs the app's own
`update.sh`: the new version's Python packages first, then the code (a failed step leaves the running version as it
was), the database is brought up to date, and the service restarts; the page reloads when the new version answers. In
Docker, pull the image instead. From a shell: `./update.sh` (`--check` only looks, `IORECIPE_REF=<sha>` installs a
given commit).

Everything is under one Settings page (the sidebar and the avatar menu); a change is saved the moment it is made: your own tabs (account, display), then for admins server, and for suite admins security and global settings. Import from the web is a page of its own in the sidebar.

### Releases

Every version merged into main is released by itself: when `__version__` (app/__init__.py) has no GitHub release yet, CI tags it `v<version>`, publishes the image as `ghcr.io/avandeputte/iorecipe:v<version>` (and `latest`) and makes the release with the merge's message as notes. Bump the version in a change to release it.

## Reverse proxy and HTTPS

Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy Manager, HAProxy, Cloudflare Tunnel) when it
is reached from outside the home network: passwords and the session cookie travel with every request.

### Cloudflare Tunnel and Cloudflare Access

With a `cloudflared` tunnel in front, set `PUBLIC_URL` to the public address. To make people sign in at Cloudflare
Access first, add a self-hosted Access application for that hostname, then turn on Settings › Security ›
Sign-in at the proxy › Cloudflare Access with your team (`myteam.cloudflareaccess.com`) and the application's AUD tag
(one setting for the whole suite, kept in the Shared ioSuite database). ioRecipe checks Cloudflare's signed token and signs
the person in to the matching account (by email, then by name).

An AI assistant cannot open the Access sign-in page. Only if MCP is on, add a policy with the action **Bypass**
(Include: Everyone) for `/mcp` in the Access application: it stays protected by an app password as a Bearer token.
Everything else, the web app and `/api/`, stays behind Access. A script that calls `/api/` from outside needs a
Cloudflare service token (`CF-Access-Client-Id` and `CF-Access-Client-Secret` headers) allowed in the policy, as well
as an app password.

## API

| For | Standard | Where |
| --- | --- | --- |
| Web and JSON clients | **REST/JSON**: recipes (list, search, by tag, the family's or your own), one recipe, add, change, delete, its photo, import from a web address | `/api/`, OpenAPI docs at `/api/docs` |
| Recipes from other sites | **schema.org Recipe** (JSON-LD and microdata), read from the page at the address given | `POST /api/import` |
| AI assistants: Claude and anything else that speaks MCP | **Model Context Protocol** (streamable HTTP, and stdio) | `https://host/mcp` (switched on in Settings › Server) |

Settings › Account makes **app passwords**: one per program, revocable on its own, used with your user name for the
REST API (HTTP Basic, or `Authorization: Bearer <app password>`) and for MCP.

```sh
curl -u alex:APP-PASSWORD "https://recipes.example.com/api/recipes?q=chocolate&tag=cookies"
curl -u alex:APP-PASSWORD https://recipes.example.com/api/recipes/12
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"title": "Oat cookies", "servings": "24 cookies", "prepMinutes": 15, "cookMinutes": 12,
       "ingredients": ["200 g oats", "100 g butter", "1 egg"], "steps": ["Mix.", "Bake 12 minutes at 180 °C."],
       "tags": ["cookies"], "family": true}' https://recipes.example.com/api/recipes
curl -u alex:APP-PASSWORD -X PUT -H 'Content-Type: image/jpeg' --data-binary @cookies.jpg https://recipes.example.com/api/recipes/12/photo
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"url": "https://www.example.com/recipes/oat-cookies"}' https://recipes.example.com/api/import
```

`ingredients` and `steps` are lists of lines (or one text with a line each). `family` says where a new recipe goes:
`true` for the family's (editors and admins), `false` for a private one; left out, it is the family's for those who
may add there. A photo's address (`photo` in a recipe) changes whenever the picture does; `&size=small` gives the
card's copy.

## MCP server

ioRecipe is also an MCP server, as the other io apps are, so an assistant such as Claude can work with the recipes:
look them up by words or tag, read one in full, add and change them, import one from a web address, delete them, and,
for admins, check the server's health, look for a new version and install it.

It is off until an admin turns it on in **Settings › Server** (or `MCP=1` in the environment); off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account, with its rights.

```sh
claude mcp add --transport http iorecipe https://recipes.example.com/mcp --header "Authorization: Bearer APP-PASSWORD"
```

On the server itself, `.venv/bin/python -m app.mcp --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_recipes`, `search_recipes`, `get_recipe`; `create_recipe`, `update_recipe`,
`delete_recipe`, `import_recipe`; and for admins `diagnostics`, `list_accounts`, `check_for_update`, `update_server`.

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: a recipe's fields round-tripping, the search, tags and counts, who sees and changes what in each role, the
photo (resized, its address changing with it, refused when it is not a picture), reading recipes from web pages
(JSON-LD on its own and in a graph, with sections and HTML in the values; microdata; pages without a recipe;
addresses the server will not fetch), the import with its picture, and the MCP server (switch, sign-in, the tools).
CI runs them against MariaDB.

## Layout

```
app/main.py        the application: start-up (tables, first admin), who is asking, routes
app/api.py         the REST API: recipes, the photo, import from a web address
app/model.py       recipes in MariaDB: the fields, who sees and changes what, the search and the tags
app/scrape.py      import from the web: fetching a page and reading its schema.org Recipe (JSON-LD, microdata)
app/images.py      the photo: checked, turned upright, kept as two JPEGs
app/mcp/           the MCP server: base (the server, finding a recipe; who is asking comes from iosuite_shared.mcp), recipes and admin tools
app/access.py      who may call a route (the markers come from iosuite-shared)
app/users.py       accounts and app passwords (the suite's, through iosuite-shared)
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](LICENSE).
