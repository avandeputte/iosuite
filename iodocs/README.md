# ioDocs

*The family's papers, in the ioThing suite (with [ioPix](https://github.com/avandeputte/iosuite/tree/main/iopix), [ioNote](https://github.com/avandeputte/iosuite/tree/main/ionote), [ioContact](https://github.com/avandeputte/iosuite/tree/main/iocontact), [ioCalendar](https://github.com/avandeputte/iosuite/tree/main/iocalendar), [ioTask](https://github.com/avandeputte/iosuite/tree/main/iotask), [ioRecipe](https://github.com/avandeputte/iosuite/tree/main/iorecipe), [ioThings](https://github.com/avandeputte/iosuite/tree/main/iothings), [ioMoney](https://github.com/avandeputte/iosuite/tree/main/iomoney), [ioHealth](https://github.com/avandeputte/iosuite/tree/main/iohealth) and the [ioStart](https://github.com/avandeputte/iosuite/tree/main/iostart) start page).*

A self-hosted home for the family's papers: passports, ID cards, driver's licenses, visas, insurance policies, the car's
registration, birth and marriage certificates, wills, health cards. Each one with its scans, who it belongs to, its
number and dates, and a reminder before it expires, early enough to renew it (a passport nine months ahead, a policy a
month). Drop a scan or a photo and it is **read**: the text off the page, the machine-readable lines of a passport or
an ID card, the barcode on the back of a US or Canadian driver's license, which fill the document in. FastAPI and a
single-page vanilla JS app, everything stored in MariaDB / MySQL (the scans too), Tesseract for the reading, and the
suite's shared library (`iosuite-shared`, in [shared](https://github.com/avandeputte/iosuite/tree/main/shared)).

## What it does

- **Documents** of a kind (passport, passport card, ID card, driver's license, visa, residence permit, insurance
  policy, vehicle registration, health and vaccination, birth, marriage, property, will and legal papers, tax,
  diplomas, memberships and cards, other), each with its title, number, issuer, country, the day it was issued and the
  day it expires, notes, fields of your own (a policy's deductible, the agent's phone) and its scans and files.
- **Whose it is**: the family members it is for (the suite's one family list), or none for the household's own papers
  (the home insurance). By person, by kind, and a search over everything, the text read off the scans included.
- **Who sees it**, per document: *the family* (everyone with a role here), *its people and the grown-ups* (the people
  it is for, whoever added it, and the editors and admins; the usual), or *private* (only its people and whoever added
  it: a will). New accounts have no role here (as in ioMoney): an admin gives one in Settings › Security.
- **Reading scans** (Tesseract on the server, `app/ocr.py`): a passport's or ID card's machine-readable zone (TD1, TD2
  and TD3, with their check digits) gives the kind, number, country, name, birth date, sex and the expiry; the PDF417
  barcode on the back of a North American license (AAMVA) gives the number, the state, the dates, the address and the
  class; anything else is read as text, for its dates (the policy period, "EXP", "4b"), its number and its kind. A PDF's
  own text is used when it has some, else its pages are read. What is read fills in the fields still empty, never
  over what you wrote: what differs is offered, to take or leave. **Read again** on any file.
- **To renew**: what has expired or is within its reminder (the kind's usual, or its own number of days, or none), on
  a page of its own and in the morning notification (web push, *Papers to renew*: on the reminder's first day, a week
  before, the day itself and the day after), to the document's people, or to the editors and admins for the
  household's papers.
- **Renew**: the new passport in place of the old one, which is archived and linked to it.
- **Number shown on demand**: a document's number is masked until **Show**, with **Copy**.
- **Who may do what**: viewers look; members add documents and change the ones they added or that are theirs; editors
  change everything they see; admins too, and the settings.
- **Linked items**: link a document to an event, a contact, a note, a thing or a transaction elsewhere in the suite.
- **AI assistants**: an MCP server ("when does Ava's passport expire?", "what's our car insurance policy number?").
- **With the other apps**: ioCalendar shows the day each document expires; the start page has a *To renew* tile and
  finds documents in its search box.
- **Settings › Security** and **Global settings** (suite admins): the suite's people, their role in every app, app
  passwords and sign-in at the proxy; the apps, keys and tokens (iosuite-shared's panel, the same in every app).
- Light and dark, phone-sized screens (a photo straight from the phone's camera), installable as an app.

## Run

ioDocs needs Python 3.10+, Tesseract and Poppler for reading scans (`apt install tesseract-ocr tesseract-ocr-eng
poppler-utils`; `setup.sh` installs them), and a MariaDB or MySQL database, its own (`iodocs`), beside the Shared ioSuite database
(`iosuite`) every app of the suite uses. The [one-line installer](../README.md#install) adds it to a server that has
other apps of the suite, with the same answers.

### Proxmox VE (LXC)

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iodocs/proxmox/ct/iodocs.sh)"
```

It asks for the database, the Shared ioSuite database, the port (8720), the time zone, the public address, the
sign-in domain and the admin, then makes a small Debian 13 container (1 CPU, 1 GB for reading scans, 8 GB: the files live in the
database) and runs `setup.sh` inside. For unattended runs: `IODOCS_DB` and `IODOCS_SUITE_DB`
(`host:port/db:user:password`), `IODOCS_ADMIN` (`name:password`), `IODOCS_DB_ADMIN`, `IODOCS_PORT`, `IODOCS_TIMEZONE`,
`IODOCS_PUBLIC_URL` and `IODOCS_COOKIE_DOMAIN`. Its checklist puts other apps of the suite in the same container.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iosuite/iodocs`) holds no data: everything is in the database.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iodocs
./setup.sh          # asks for the databases, port, time zone and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

`setup.sh`'s flags (`--db`, `--suite-db`, `--db-admin`, `--admin`, `--port`, `--public-url`, `--cookie-domain`,
`--timezone`, `--service`, `--yes`, `--also`, `--remove`, `--reconfigure`, `--apps`) are the same as in every app of
the suite; its last step is the list of the suite's apps on this machine, to add or remove one. From a shell:
`python -m app.cli check`, `python -m app.cli read SCAN.jpg` (what a scan would fill in).

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment,
which wins:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database (`iodocs`) |
| `IOSUITE_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the Shared ioSuite database (`iosuite`): accounts, sessions, app passwords, roles and suite-wide settings |
| `COOKIE_DOMAIN` | the domain the sign-in is shared on (`example.com`) |
| `HOST`, `PORT` | where the server listens (every address, 8720) |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | serve HTTPS directly instead of behind a reverse proxy |
| `TZ` | the time zone of the server log |
| `PUBLIC_URL` | the address people use, for links (the notifications, the MCP tools) |
| `MAX_FILE_MB` | the largest file that may be attached (100) |
| `TESSERACT`, `OCR_LANGS` | the Tesseract command (`off`: scans are kept, not read) and its languages (`eng`; `eng+fra`) |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `DATA_DIR`, `LOG_FILE` | where the app writes on its own (`data/`), and its log (`DATA_DIR/iodocs.log`) |

## Updates

The suite has one version and its apps are updated together: Settings › Global settings › Updates (suite admins, in
any app). Settings › Server shows the version, the server log and Restart. From a shell: `./update.sh`. In Docker,
pull the image.

## API

| For | Standard | Where |
| --- | --- | --- |
| Web and JSON clients | **REST/JSON**: documents (list, search, by kind, person or status), one document, add, change, renew, delete; its files (add, read, rename, put first, remove) | `/api/`, OpenAPI docs at `/api/docs` |
| ioCalendar and the start page | the documents that expire between two days | `GET /api/expiring?start=&end=` |
| AI assistants | **Model Context Protocol** (streamable HTTP, and stdio) | `https://host/mcp` (switched on in Settings › Server), or every app's tools at ioStart's `/mcp` |

Settings › Account makes **app passwords**, for the REST API (HTTP Basic, or `Authorization: Bearer <app password>`)
and for MCP.

```sh
curl -u alex:APP-PASSWORD "https://docs.example.com/api/documents?status=expiring"
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: application/json' \
  -d '{"kind": "passport", "people": ["Ava"], "number": "C70224518", "expiresOn": "2031-12-28"}' \
  https://docs.example.com/api/documents
curl -u alex:APP-PASSWORD -X POST -H 'Content-Type: image/jpeg' --data-binary @passport.jpg \
  "https://docs.example.com/api/documents/12/files?name=passport.jpg"     # read at once: {file, found, filled, differs}
```

The MCP tools: `overview`, `expiring`, `search_documents`, `get_document`, `scan_text`, `add_document`,
`update_document`, `renew_document`, `delete_document`, and for admins `diagnostics` and `list_accounts`.
