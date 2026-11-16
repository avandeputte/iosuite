# ioThings

*Everything you own, in the ioThing suite (with [ioPix](https://github.com/avandeputte/iosuite/tree/main/iopix), [ioNote](https://github.com/avandeputte/iosuite/tree/main/ionote), [ioContact](https://github.com/avandeputte/iosuite/tree/main/iocontact), [ioCalendar](https://github.com/avandeputte/iosuite/tree/main/iocalendar), [ioTask](https://github.com/avandeputte/iosuite/tree/main/iotask), [ioRecipe](https://github.com/avandeputte/iosuite/tree/main/iorecipe), [ioMoney](https://github.com/avandeputte/iosuite/tree/main/iomoney), [ioHealth](https://github.com/avandeputte/iosuite/tree/main/iohealth) and the [ioStart](https://github.com/avandeputte/iosuite/tree/main/iostart) start page).*

A self-hosted inventory of everything you own, in place of Homebox: what the family has and where it is (the appliances,
the tools, the furniture, the electronics, the car, the books, the camping gear, what is stored in the attic), with the manuals, receipts, photos and warranties, and the upkeep each thing
needs (the boiler's yearly service, the car's MOT, the fridge's water filter) with a maintenance log. FastAPI and a
single-page vanilla JS app, with everything stored in MariaDB / MySQL (the files too), and the suite's shared library
(`iosuite-shared`, in [shared](https://github.com/avandeputte/iosuite/tree/main/shared)).

## What it does

- **Things** with a name, a description, how many, maker, model and serial number, an asset id, a link, the purchase
  (when, where, the price), the warranty (until a day, or for life, and its details), insured or not, notes, and
  **fields of their own** (filter size, paint colour, the code of the safe). Searching finds words in any of them, in
  the place and in the labels.
- **Places** as a tree (House / Kitchen / Drawer by the sink): deleting one moves what was in it one level up.
  **Labels** with a colour. Both in the sidebar, with how many things each holds.
- **Whose it is**: a thing can be marked as one or more people's of the family (Emma's bike, Dad's laptop, the
  children's games console); marked as nobody's, it is the household's. The family is the suite's one list
  (Settings › Security › Family, suite admins), with the same colours, initials and faces as in ioTask and
  ioCalendar, and everyone in it can be given a thing, whether or not they use ioThings. The sidebar's **Family**
  lists each person with how many things are theirs and shows them; the cards and the table show their faces;
  searching a name ("emma", "emma's") finds their things too. The REST API (`people` on a thing, `?person=` on the
  list) and the MCP tools (`people`, `search_items(person=...)`) do the same.
- **Files**: photos (turned upright, with a small copy for the cards), manuals, receipts, warranty cards and anything
  else, picked, dropped on the thing or taken with the phone. Up to `MAX_FILE_MB` each (100). They are kept in the
  database in 4 MB parts, so a backup of the database has them and nothing else needs one.
- **Upkeep**: what a thing needs every so many days, weeks, months or years, and when it is next due. **Done** (the
  day, the cost, who did it) writes a line in the thing's **maintenance log** and moves the upkeep on (a month after
  31 January is the last day of February). The Upkeep page lists everything by when it is due: late, this week, this
  month, later. One-off lines (a repair, a part replaced) go in the log too.
- **ioTask**, when it is part of the suite: an upkeep can also be a repeating task in one of your task lists (made as
  you, with a link back to the thing). Ticked off in ioTask, the new due day shows in ioThings the next time the thing
  is opened; **Done** in ioThings moves the task on; removing the upkeep removes its task. Nothing to set up.
- **Warranties**: a badge on each thing, a page of the ones ending within 30 days, and a word in the morning
  notification 30 days, 7 days and on the day before one ends.
- **Archive** for a thing sold, given away or thrown out: it keeps its story, and who it went to for how much.
- **The things as cards or a table**, by name, the newest, recently changed, price, when bought or when the warranty
  ends; what they cost together on the front page. **Duplicate** makes the next one of a kind quickly. **Print** gives
  one thing on paper.
- **For the insurer: everything in one PDF** (Import and export, anyone): every thing with all its details, photos,
  maintenance log, and its receipts, warranties and manuals (pictures shown, PDFs put in whole after the thing's page),
  behind a front page with the total paid and a list of everything that links to each thing. The PDF's bookmarks go
  by place and thing. Keep it away from the house and make a new one now and then. Photos are made smaller so the
  file stays easy to copy; a file that is neither a picture nor a PDF is named so it can be found here. It is made in
  the background; the last one is kept until the next one or a restart. DejaVu Sans writes it when the system has it
  (Docker and the Proxmox installer add `fonts-dejavu-core`), Helvetica otherwise.
- **Homebox, straight from the server** (editors, Import and export › From a Homebox server): give Homebox's address
  and the email and password you sign in to it with, and ioThings reads everything through Homebox's API: the things
  with all their details, the places, the labels with their colours, the own fields, the **photos, manuals, receipts
  and warranties**, and the completed **maintenance log**. It runs in the background with its progress on the page.
  Running it again brings things up to date (the same bytes, the same log line are not added twice), and things from
  an earlier CSV import are taken over (same name, same place). The Homebox password is used for the import and not
  kept. Both shapes of Homebox's API are read: `/api/v1/items` (up to v0.2x) and the newer `/api/v1/entities`.
  Maintenance that was only scheduled is listed as left out (add it as upkeep). The server must reach Homebox: one
  behind Cloudflare Access needs the address it has on the home network.
- **Homebox's CSV**: Tools › Export inventory in Homebox gives a CSV file; Import and export takes it, with its places
  (made as needed), labels and `HB.field.*` fields. Importing the same file again changes what it brought instead of
  adding it twice (Homebox's `HB.import_ref`). The export writes Homebox's format, so it goes back into Homebox, or
  into a spreadsheet. Homebox's CSV has no photos, manuals or log: the import from the server brings those.
- **Notifications** (Settings › Account › Notifications): at your morning time, the upkeep that is due and is not an
  ioTask task (ioTask reminds of those itself), and the warranties ending.
- **Linked**: a thing can be linked to events, tasks, notes, contacts, recipes and photos of the other apps, and they
  to it; the start page's search finds things too. Linked to the ioMoney transaction that paid for it, the thing
  shows the amount, the day and the account, and the transaction shows the thing with how long its warranty runs.
- **Roles as in the other io apps**: viewers look; members (the default) add things, attach files and keep the upkeep
  and the log; editors change and delete everything, and keep the places and labels in order; admins also choose the
  currency (Settings › Things) and run the server. The same accounts, passwords and app passwords as the other io apps.
- **Settings › Security** and **Global settings** (suite admins): the suite's people, their role in every app, app
  passwords and sign-in at the proxy; the apps, keys and tokens (iosuite-shared's panel, the same in every app).
- Light and dark, phone-sized screens, installable as an app.

## Run

ioThings needs Python 3.10+ and a MariaDB or MySQL database, its own (`things`), beside the Shared ioSuite database
(`iosuite`) every app of the suite uses. The [one-line installer](../README.md#install) adds it to a server that has
other apps of the suite, with the same answers.

### Proxmox VE (LXC)

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iothings/proxmox/ct/iothings.sh)"
```

It asks for the database, the Shared ioSuite database, the port (8700), the time zone, the public address, the
sign-in domain and the admin, then makes a small Debian 13 container (1 CPU, 512 MB, 8 GB: the files live in the
database) and runs `setup.sh` inside. For unattended runs: `IOTHINGS_DB` and `IOTHINGS_SUITE_DB`
(`host:port/db:user:password`), `IOTHINGS_ADMIN` (`name:password`), `IOTHINGS_DB_ADMIN`, `IOTHINGS_PORT`, `IOTHINGS_TIMEZONE`,
`IOTHINGS_PUBLIC_URL` and `IOTHINGS_COOKIE_DOMAIN`. Its checklist puts other apps of the suite in the same container.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iosuite/iothings`) holds no data: everything is in the database.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iothings
./setup.sh          # asks for the databases, port, time zone and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

`setup.sh`'s flags (`--db`, `--suite-db`, `--db-admin`, `--admin`, `--port`, `--public-url`, `--cookie-domain`,
`--timezone`, `--service`, `--yes`, `--also`, `--remove`, `--reconfigure`, `--apps`) are the same as in every app of
the suite; its last step is the list of the suite's apps on this machine, to add or remove one. From a shell:
`python -m app.cli check`, `python -m app.cli import-homebox export.csv [NAME]`.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment,
which wins:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`iothings`) |
| `IOSUITE_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the Shared ioSuite database (`iosuite`): accounts, sessions, app passwords, roles and suite-wide settings |
| `COOKIE_DOMAIN` | the domain the sign-in is shared on (`example.com`) |
| `HOST`, `PORT` | where the server listens (every address, 8700) |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | serve HTTPS directly instead of behind a reverse proxy |
| `TZ` | the time zone of the server log |
| `PUBLIC_URL` | the address people use, for links (the ioTask task's link back, the MCP tools) |
| `MAX_FILE_MB` | the largest file that may be attached (100) |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `DATA_DIR`, `LOG_FILE` | where the app writes on its own (`data/`), and its log (`DATA_DIR/iothings.log`) |

## Updates

The suite has one version and its apps are updated together: Settings › Global settings › Updates (suite admins, in
any app). Settings › Server shows the version, the server log and Restart. From a shell: `./update.sh`. In Docker,
pull the image.

## API

| For | Standard | Where |
| --- | --- | --- |
| Web and JSON clients | **REST/JSON**: things (list, search, by place or label, archived), one thing, add, change, duplicate, delete, its files, upkeep and log; places and labels | `/api/`, OpenAPI docs at `/api/docs` |
| Inventory PDF | everything, photos and papers included, as one PDF | `POST`/`GET /api/export-pdf`, `GET /api/export-pdf/file` |
| Homebox | Homebox's CSV, in and out; everything from a Homebox server, files and log too | `POST /api/import/homebox`, `GET /api/export.csv`, `POST`/`GET /api/import/homebox-server` |
| AI assistants | **Model Context Protocol** (streamable HTTP, and stdio) | `https://host/mcp` (switched on in Settings › Server), or every app's tools at ioStart's `/mcp` |

Settings › Account makes **app passwords**, for the REST API (HTTP Basic, or `Authorization: Bearer <app password>`)
and for MCP.

```sh
curl -u alex:APP-PASSWORD "https://things.example.com/api/items?q=boiler"
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"name": "Dishwasher", "manufacturer": "Bosch", "location": "House / Kitchen", "warrantyExpires": "2028-06-01"}' \
  https://things.example.com/api/items
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: text/csv' --data-binary @homebox.csv https://things.example.com/api/import/homebox
```

The MCP tools: `overview`, `search_items`, `get_item`, `create_item`, `update_item`, `delete_item`, `list_locations`,
`create_location`, `warranties_ending`, `list_upkeep`, `add_upkeep`, `upkeep_done`, `log_maintenance`, `diagnostics`.
