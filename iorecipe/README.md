# ioRecipe

*The family's recipes, in the ioThing suite (with [ioPix](https://github.com/avandeputte/iopix), [ioNote](https://github.com/avandeputte/ionote), [ioContact](https://github.com/avandeputte/iocontact), [ioCalendar](https://github.com/avandeputte/iocalendar), [ioTask](https://github.com/avandeputte/iotask), [ioHealth](https://github.com/avandeputte/iohealth) and the [ioSuite](https://github.com/avandeputte/iosuite) start page).*

A self-hosted recipe book: a web app for the whole family to keep recipes with their ingredients, steps and photos, to import a recipe from the web by its address, from pasted text, from a photo or from a file, and to cook, shop and print from it. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL (the photos too), and the suite's shared library (`iosuite-shared`, in [iosuite-shared](https://github.com/avandeputte/iosuite-shared)).

## What it does

- **Recipes** with a title, a description, what they make (4, or 24 cookies), preparation and cooking time, **ingredients**, **steps**, notes, tags, and where they come from. In the ingredients and the steps, a line that ends with a colon ("For the icing:") is a heading.
- **Photos**: as many as you like for a recipe (the first is the one on its card) and one for any step, uploaded from the computer or taken with the phone. Each is turned upright, made smaller and kept as a JPEG in the database, with a small copy for the cards.
- **Import from the web**: paste the address of a recipe page and ioRecipe fetches it, the way a browser asks for a page, and keeps the recipe on it (title, ingredients, steps, times, servings, tags) with its picture and a link back. It reads the schema.org Recipe data that most recipe sites publish for search engines; where a page has none, it reads the page as a person would: the lists a recipe plugin marks as ingredients and instructions, or the text under an "Ingredients" heading. A page that still gives no complete recipe is read by a small AI model that runs inside the app, on your own server (see [Reading a page with AI](#reading-a-page-with-ai)).
- **Import from pasted text or a photo**: paste a recipe from a message or a document, or give a photo of one (a page of a cookbook, a card, a screenshot): the text is made into a draft that opens in the recipe form, to be looked over before it is saved. A photo is read on the server itself, by Tesseract (see [Reading a photo of a recipe](#reading-a-photo-of-a-recipe)); it goes nowhere else.
- **Export and import as a file**: one recipe, a cookbook or everything you see as a `.zip` (the recipes, their photos, your favourites and ratings, their cookbooks), to keep safe or to import into another ioRecipe. The same import takes **Mealie**'s recipes: a recipe's JSON, a `.zip` of them with their pictures, or a Mealie backup.
- **The recipes as cards**, with their photo, how long they take and what they make: all of them, the family's, your own, your favourites, the ones with a tag or in a cookbook, by title, the newest or the best rated first; **search** finds words in the title, the ingredients, the steps, the notes and the tags.
- **Favourites and ratings**: the heart makes a recipe one of your favourites, the stars are your rating (1 to 5). Both are yours alone; everyone sees the average of the ratings.
- **Cookbooks**: recipes grouped under a name (Baking, Weeknights, To try). A family cookbook is everyone's and holds family recipes; a cookbook of your own may hold the family's recipes and yours. A recipe can be in several.
- **Cooking from it**: the amounts follow the servings you want (half, double, ten times: `1 1/2 cups` becomes `3 cups`, `2-3 tbsp` becomes `4-6 tbsp`), the ingredients have boxes to tick off as they go in, a step is struck out with a click, and **Print** gives the recipe alone on paper, with the amounts as they are shown.
- **The shopping list**, when [ioTask](https://github.com/avandeputte/iotask) is part of the suite: a recipe's ingredients (for the servings shown, without the ones ticked off) become tasks in one of your lists there. Nothing to set up; ioTask is asked as you.
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
| `OCR_LANGUAGES` | the languages a photo of a recipe is read in, as Tesseract's codes (`eng+nld+fra`); left out, every language installed |
| `AI`, `AI_MODEL`, `AI_TIMEOUT` | the AI model on this server that reads a web page without recipe data: `AI=0` turns it off; another GGUF model (a file, or its address); the seconds a page may take (300) |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `IORECIPE_REPO`, `IORECIPE_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iorecipe`, `main`) |
| `DATA_DIR` | where the app writes on its own: the log, the update result and the AI model (`data/` in the app folder) |
| `LOG_FILE` | the server log shown at Settings › Server (`DATA_DIR/iorecipe.log`; `LOG_FILE=` with nothing after it: no file) |

### Reading a page with AI

Most recipe pages are imported without it. For the ones that are not (a recipe told as a story, a layout ioRecipe
cannot make out), ioRecipe has a small language model **inside the app, on your own server**: when a page has no
recipe data and its own lists and headings give no complete recipe, the model reads the page's text and returns
the recipe as the page words it. Nothing is sent to an AI service; there is none behind this.

- The runtime is [llama.cpp](https://github.com/ggml-org/llama.cpp) (through `llama-cpp-python`). It is in the Docker
  image; `setup.sh` and the Proxmox installer compile it on the server, which takes a few minutes. By hand:
  `.venv/bin/python -m pip install -e '.[ai]'` (needs a C++ compiler and `cmake`).
- The model is Qwen2.5 1.5B Instruct (Apache 2.0), one file of about 1 GB, fetched once from Hugging Face into
  `DATA_DIR/models` when the app first starts with the runtime. With Docker, keep `/app/data` on a volume (the
  `docker-compose.yml` here does) so an update does not fetch it again.
- A page takes a minute or so of the server's processor, in a process of its own, and about 2 GB of memory while it
  is read. Lines the model gives that are not on the page are dropped.
- `AI=0` in `config.env` turns it off. `AI_MODEL` names another GGUF model (a file on the server, or its web
  address): a larger one reads better and slower. `AI_TIMEOUT` is the seconds a page may take (300).

Some sites test for a person's browser and refuse a server whatever it sends. The import says so; copy the page's
text and use Import › Pasted text for those.

### Reading a photo of a recipe

Import › Photo reads the text on a picture with [Tesseract](https://github.com/tesseract-ocr/tesseract), a program
of its own that runs on the server: the photo is not sent anywhere. The Docker image and the Proxmox container come
with it (English, Dutch, French and German); `setup.sh` installs it where it can. Without it, everything else works
and the Photo tab says what is missing. To add it, or another language, by hand:

```sh
sudo apt-get install tesseract-ocr tesseract-ocr-nld tesseract-ocr-fra    # Debian, Ubuntu (tesseract-ocr-<code> per language)
brew install tesseract tesseract-lang                                      # macOS
```

Print reads well; handwriting mostly does not. What comes out is a draft in the recipe form, never a saved recipe.

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
| Web and JSON clients | **REST/JSON**: recipes (list, search, by tag, cookbook, the family's, your own or your favourites), one recipe, add, change, delete, its photos, your favourite and rating, cookbooks, import and export | `/api/`, OpenAPI docs at `/api/docs` |
| Recipes from other sites | **schema.org Recipe** (JSON-LD and microdata) read from the page at the address given; without it, the page's own lists and text, or the AI model on the server | `POST /api/import` |
| Recipes as files | a `.zip` with `recipes.json` and `photos/`; in: that, a Mealie export or backup, a recipe as JSON | `GET /api/export`, `POST /api/import/file` |
| The shopping list | ioTask's REST API, asked as the person signed in | `POST /api/recipes/{id}/shopping` |
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
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: image/jpeg' --data-binary @cookies.jpg https://recipes.example.com/api/recipes/12/photos
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: image/jpeg' --data-binary @dough.jpg "https://recipes.example.com/api/recipes/12/photos?step=1"
curl -u alex:APP-PASSWORD -X PUT -H 'Content-Type: application/json' -d '{"favourite": true, "rating": 5}' https://recipes.example.com/api/recipes/12/mark
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"url": "https://www.example.com/recipes/oat-cookies"}' https://recipes.example.com/api/import
curl -u alex:APP-PASSWORD -o recipes.zip https://recipes.example.com/api/export
curl -u alex:APP-PASSWORD -X POST --data-binary @mealie-export.zip "https://recipes.example.com/api/import/file?family=true"
```

`ingredients` and `steps` are lists of lines (or one text with a line each). `family` says where a new recipe goes:
`true` for the family's (editors and admins), `false` for a private one; left out, it is the family's for those who
may add there. A recipe's `photos` are its own, in their order, then its steps' (`step`: the step's place in `steps`,
from 0); `photo` is the one its card shows, and `?size=small` gives a picture's small copy. `POST /api/import/text`
(`{text}`) and `POST /api/import/photo` (the picture as the body) save nothing: they answer with a `draft`, the
fields `POST /api/recipes` takes.

## MCP server

ioRecipe is also an MCP server, as the other io apps are, so an assistant such as Claude can work with the recipes:
look them up by words, tag or cookbook, read one in full, add and change them, import one from a web address, mark
favourites and rate them, keep cookbooks, delete them, and,
for admins, check the server's health, look for a new version and install it.

It is off until an admin turns it on in **Settings › Server** (or `MCP=1` in the environment); off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Account › App passwords), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account, with its rights.

```sh
claude mcp add --transport http iorecipe https://recipes.example.com/mcp --header "Authorization: Bearer APP-PASSWORD"
```

On the server itself, `.venv/bin/python -m app.mcp --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_recipes`, `search_recipes`, `get_recipe`; `create_recipe`, `update_recipe`,
`delete_recipe`, `import_recipe`, `mark_recipe`; `list_cookbooks`, `create_cookbook`, `add_to_cookbook`,
`remove_from_cookbook`, `delete_cookbook`; and for admins `diagnostics`, `list_accounts`, `check_for_update`, `update_server`.

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: a recipe's fields round-tripping, the search, tags and counts, who sees and changes what in each role, the
photos (resized, in their order, a step's following its step, refused when not a picture), favourites and ratings,
cookbooks, reading recipes from web pages
(JSON-LD on its own and in a graph, with sections and HTML in the values; microdata; pages without a recipe;
addresses the server will not fetch), the import with its picture, a recipe out of plain text and off a photo (where
Tesseract is installed), an export coming back whole, Mealie's recipes and backup, the shopping list, and the MCP
server (switch, sign-in, the tools).
CI runs them against MariaDB.

## Layout

```
app/main.py        the application: start-up (tables, first admin), who is asking, routes
app/api.py         the REST API: recipes, photos, favourites and ratings, cookbooks, import, export, the shopping list
app/model.py       recipes in MariaDB: the fields, who sees and changes what, the search and the tags, photos, marks, cookbooks
app/scrape.py      import from the web: fetching a page and reading its schema.org Recipe (JSON-LD, microdata), else its lists and text
app/ai.py          a page's text read by a small AI model on this server (llama.cpp), where nothing else found the recipe
app/textimport.py  a recipe out of plain text (pasted, or read off a photo)
app/ocr.py         the text on a photo, read by Tesseract on this server
app/portable.py    recipes as files: the export, and imports of it and of Mealie's
app/shopping.py    the ingredients as tasks in ioTask, asked as the person signed in
app/images.py      a photo: checked, turned upright, kept as two JPEGs
app/mcp/           the MCP server: base (the server, finding a recipe; who is asking comes from iosuite_shared.mcp), recipes and admin tools
app/access.py      who may call a route (the markers come from iosuite-shared)
app/users.py       accounts and app passwords (the suite's, through iosuite-shared)
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](LICENSE).
