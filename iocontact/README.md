# ioContacts

*Contacts for the family, in the ioThing suite (with [ioPix](https://github.com/avandeputte/iopix), [ioNotes](https://github.com/avandeputte/ionotes), [ioCalendar](https://github.com/avandeputte/iocalendar), [ioHealth](https://github.com/avandeputte/iohealth) and the [ioSuite](https://github.com/avandeputte/iosuite) start page).*

A self-hosted contact manager: a web app for the whole family, and the standard protocols every mail, contacts and calendar app already speaks, so the same contacts show up on phones, in Apple Contacts, Outlook, Thunderbird and anywhere else. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL, and the suite's shared library (`iosuite-shared`, in [iosuite-shared](https://github.com/avandeputte/iosuite-shared)).

## What it does

- **Contacts** with names (prefix, first, middle, last, suffix, nickname, maiden name, phonetic names), any number of phone numbers, emails and addresses (with labels and a preferred one), birthday (with or without the year), anniversaries and other dates, company, department, job title, social profiles (LinkedIn, Facebook, Instagram, X, Threads, Bluesky, Mastodon, TikTok, YouTube, GitHub, WhatsApp, Telegram, Signal and more), websites, labels, notes and a photo.
- **Relations** between contacts: parents, children, siblings, spouses and partners, grandparents, aunts and uncles, cousins, in-laws, step-family, godparents, friends, colleagues, managers… The other side is kept automatically (make Tim Mary's son and Mary becomes Tim's mother), labels follow the other person's gender (Brother, Sister, Sibling), and a **family tree** page lays the family out by generation. A relation can also name someone who is not a contact.
- **The family and private books**: everyone shares the Family address book; each account also has a private Personal one, and anyone can make more (shared or private). Roles as in iopix: viewers read the shared books (and change only their own), editors change shared contacts, admins also manage users and settings.
- **Sign-in as in iopix**: the sign-in screen is a pick list of the accounts (each with the face of the contact it is linked to as *me*). Sign-in, passwords, sessions, app passwords and the users admin are iosuite-shared's routes (`/api/auth/*`, `/api/users`), the same in every app; repeated wrong passwords are slowed down per visitor and name, at the web sign-in, over HTTP Basic / Bearer and at the LDAP bind. A viewer whose password an admin removed (Settings › Security › People › No password) signs in with one click, but only at home: from outside those accounts are not offered and their sessions do not work. *Other* types a user name.
- **Birthdays**: the upcoming birthdays and anniversaries, with ages, and a **family birthday calendar** to subscribe to.
- **ioPix**: link a contact to a person named in ioPix. The face from ioPix is the contact's photo, and the only one: ioContacts stores no photos of its own, and serves the ioPix face to the web app, phones (CardDAV), vCard exports and the LDAP directory (`jpegPhoto`). A photo in an imported or synced vCard is not kept. The contact links to that person's photos, and *Link by name* links every contact whose name matches exactly one ioPix person. The ioPix people page lists everyone in ioPix and makes a contact from any of them.
- **Duplicates** (same name, email or phone) and merging, **bulk** favorite, label, move, export and delete, search across names, emails, phone digits, companies, addresses, labels and notes.
- **Settings › Security** and **Global settings** (suite admins): the whole suite's people and their role in every app, app passwords and sign-in at the proxy; the apps, keys and tokens; the same panel as on the start page and in every io app (iosuite-shared's `/api/suite-admin/ui.js`).
- Light and dark, phone-sized screens, installable as an app.

## Run

ioContacts needs Python 3.10+ and a MariaDB or MySQL database. Give it its own database and user, for example:

```sql
CREATE DATABASE contacts CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'contacts'@'%' IDENTIFIED BY 'a-good-password';
GRANT ALL ON contacts.* TO 'contacts'@'%';
```

The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iocontacts.sh` and `proxmox/install/iocontacts-install.sh` follow the community-scripts (ProxmoxVE) framework layout, the same way as iopix, so they can be submitted upstream as they are. Until then the ct script points the framework at this repository for the install script (`COMMUNITY_SCRIPTS_URL`), while the engine itself comes from community-scripts. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iocontacts/main/proxmox/ct/iocontacts.sh)"
```

It asks for the MariaDB host, port, database, user and password, the Shared ioSuite database, the web port (8640), the LDAP port (389), the public address behind your reverse proxy (optional), the domain the sign-in is shared on (optional) and the admin account; then the framework's own questions (resources, network). It creates a small Debian 13 container (1 CPU, 512 MB, 4 GB disk by default) and runs the app's own `setup.sh` inside with those answers: packages, settings, tables, admin and the `iocontacts` service. The passwords reach `setup.sh` through its environment (a root-only file pushed in and removed again), never on a command line. The setup's output is kept in `/opt/iocontacts/setup.log`; on failure its last lines are shown with the command to run it again. The container's `update` command pulls the latest code and keeps the settings. For unattended runs set `IOCONTACTS_DB` and `IOCONTACTS_SUITE_DB` (`host:port/db:user:password`), `IOCONTACTS_ADMIN` (`name:password`), `IOCONTACTS_PORT`, `IOCONTACTS_LDAP_PORT`, `IOCONTACTS_PUBLIC_URL` and `IOCONTACTS_COOKIE_DOMAIN`. The MariaDB user must be allowed to connect from the container's address.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iocontacts`) holds no data: everything is in the database, so the container can be replaced at will.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iocontacts && cd iocontacts
./setup.sh          # asks for the database, ports and the admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

Its last question, "Also install …?" (flag `--also iocalendar,ionotes`, `--also all`; `IOCONTACTS_ALSO` in the environment), puts
other apps of the suite in this same machine, beside ioContacts (`/opt/iocalendar/app` next to `/opt/iocontacts/app`),
without asking the shared questions again: the same database server (each app gets its own database: `suite`,
`calendar`, `contacts`, `notes`, `health`, `iopix`; the user needs rights on those names too), the same Shared ioSuite
database, sign-in domain and admin (`iosuite-shared install`, from the shared library). Each app keeps its usual port
and updates itself as always. The Proxmox installer offers the same as a checklist, for one container with several apps.

The databases and users need not exist beforehand: give a MariaDB / MySQL administrator (the question after the
databases; flag `--db-admin USER:PASSWORD`, or `IOCONTACTS_DB_ADMIN`, also in the Proxmox installer) and `setup.sh` creates
the app's database and user, the Shared ioSuite database and user and, with other apps installed alongside, their
databases too, with the passwords you answered (`iosuite-shared provision`). Nothing is dropped, and the administrator's
password is used once and not written anywhere.

`setup.sh`'s flags (`--db`, `--suite-db`, `--admin`, `--port`, `--public-url`, `--cookie-domain`, `--service`, `--yes`) are the same in every app of the suite, plus `--ldap-port`. Accounts are the suite's: `.venv/bin/iosuite-shared --config . admin NAME --app iocontacts` (password from `ADMIN_PASSWORD`, or asked for) and `.venv/bin/iosuite-shared --config . password NAME`.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment, which wins:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database |
| `HOST`, `PORT` | where the server listens (`0.0.0.0`, 8640; every app of the suite has its own port) |
| `FORWARDED_ALLOW_IPS` | the addresses that may pass on the visitor's address and scheme (`X-Forwarded-For` / `-Proto`): `*`, or your reverse proxy's; read by the app itself (iosuite-shared), not by uvicorn |
| `TLS_CERT_FILE`, `TLS_KEY_FILE` | serve HTTPS directly instead of behind a reverse proxy |
| `LDAP_PORT`, `LDAP_HOST`, `LDAP_BASE` | the LDAP directory (3890, all addresses, `dc=iocontacts`); `LDAP_PORT=0` turns it off |
| `PUBLIC_URL` | the address people use (behind a proxy), for links in the calendar feed and Settings |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `IOSUITE_DB_HOST`, `_PORT`, `_NAME`, `_USER`, `_PASSWORD` | the Shared ioSuite database (MariaDB; by default on the contacts' server, database, user and password `iosuite`): accounts, passwords, sessions, app passwords, roles and the suite-wide settings, shared by every app of the suite (the `iosuite-shared` library, from [iosuite-shared](https://github.com/avandeputte/iosuite-shared)); only the role an account holds here and its "me" contact are ioContacts' own. `iosuite-shared migrate --iocontacts` folds a 0.3 install's `users` table into it |
| `COOKIE_DOMAIN` | the domain the session cookie is shared on (`example.com`): signed in at `photo.example.com`, signed in at `contacts.example.com` too |
| `AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD` | sign-in at a reverse proxy, exactly as in iopix: Cloudflare Access (with token checking), Authelia, Authentik, oauth2-proxy… matched to accounts by email, then name |
| `CF_KV_ACCOUNT_ID`, `CF_KV_NAMESPACE_ID`, `CF_KV_API_TOKEN` | optional edge check of app passwords: the Workers KV namespace a Cloudflare Worker on `/dav*` reads; normally stored once for the whole suite in Settings › Global settings › Keys and tokens, these override it ([setup](https://github.com/avandeputte/iosuite-shared/blob/main/cloudflare/edge-auth/README.md)) |
| `MCP` | `1` keeps the MCP server on, whatever the setting says |
| `MCP_USER` | the account `python -m app.mcp` (stdio) acts as |
| `UPDATE_CHECK` | `0` turns the daily version check off for good |
| `IOCONTACTS_REPO`, `IOCONTACTS_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iocontacts`, `main`) |
| `DATA_DIR` | where the app writes on its own: the log and the update result (`data/` in the app folder) |
| `LOG_FILE` | the server log shown at Settings › Server (`DATA_DIR/iocontacts.log`; `LOG_FILE=` with nothing after it: no file) |

### ioPix

Nothing to set up: ioContacts finds ioPix in the suite's list of apps (the Shared ioSuite database) and reads from it from the server as its own service account (`iocontacts-app`) with a read-only app password, both made by itself on first use and listed on the start page's Settings › Security, where a suite admin can revoke them (a new one is made the next time). Behind Cloudflare Access, the suite's Cloudflare Access service token (Settings › Global settings › Keys and tokens) goes along. The people list comes from ioPix's People (the named people with photos) and the faces from ioPix's face crops.

## Updates

ioContacts asks GitHub once a day whether the main branch has a newer version (only the public commit list is read;
nothing about the server is sent; Settings › Server switches it off, `UPDATE_CHECK=0` locks it off). Admins
then see a note with **Update now**, and **Settings › Server** has the version, **Check for updates**,
**Update now**, the tail of the server log (`data/iocontacts.log` in the app folder; `LOG_FILE` moves it, empty switches it
off) and **Restart**. The page is the same in every ioThing app: the version check, `update.sh`, the restart and the log
come from `iosuite_shared.updates` in iosuite-shared, served at `/api/server` and `/api/log`. Updating runs the app's own
`update.sh`: the new version's Python packages first, then the code (a failed step leaves the running version as it
was), the database is brought up to date, and the service restarts; the page reloads when the new version answers. The
MCP tools `check_for_update` and `update_server` do the same. In Docker, pull the image instead. From a shell:
`./update.sh` (`--check` only looks, `IOCONTACTS_REF=<sha>` installs a given commit).

Everything about the app is under one Settings page (the sidebar and the avatar menu): your own tabs (account, display,
apps and devices, address books), then for admins storage and backups and server, and for suite admins
security and global settings. Tidying the contacts is **Clean up** in the sidebar (below).

## Reverse proxy and HTTPS

Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy Manager, HAProxy, Cloudflare Tunnel), as iopix: iOS and macOS want HTTPS for CardDAV accounts outside the home network, and passwords travel with every CardDAV request. The LDAP directory speaks plain LDAP; keep it on the home network, or put a TLS proxy (stunnel, HAProxy, nginx stream) in front for `ldaps://`.

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
| Contacts apps: Apple Contacts (Mac, iPhone, iPad), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Contacts, KDE | **CardDAV** (RFC 6352) with sync-collection (RFC 6578), ctag, discovery via `/.well-known/carddav` (RFC 6764) and current-user-principal | `https://host/dav/` |
| Any app that reads contact files | **vCard 3.0** (RFC 2426) and **4.0** (RFC 6350), with Apple's extensions (relations, dates, social profiles and custom labels survive in Apple Contacts); vCard 2.1 is read | CardDAV, `/api/…?format=vcard`, import/export |
| Web and JSON clients | **REST/JSON** with **jCard** (RFC 7095) by content negotiation (`Accept: application/vcard+json` or `text/vcard; version=4.0`) | `/api/`, OpenAPI docs at `/api/docs` |
| Mail apps, desk phones, printers | **LDAP v3** (RFC 4511), read-only, inetOrgPerson plus Thunderbird's mozillaAbPersonAlpha attributes | port 3890 (389 in the Proxmox container) |
| Calendars: Apple Calendar, Google Calendar, Outlook, Thunderbird | **iCalendar** (RFC 5545) subscription of birthdays and anniversaries, yearly events | `/cal/<private token>/family.ics` |
| Moving in and out | vCard files, jCard, and **CSV in Google Contacts' and Outlook's layouts** | Import and export page, `/api/import`, `/api/export` |
| AI assistants: Claude and anything else that speaks MCP | **Model Context Protocol** (streamable HTTP, and stdio) | `https://host/mcp` (switched on in Settings › Server) |

**iPhone, iPad and Mac in one step:** Settings › Apps and devices › *Download the profile* gives a configuration profile
(`.mobileconfig`) with the CardDAV account and, if you like, the birthday calendar subscription (and the LDAP
directory for Mail on a Mac), with a new app password for that device inside (or none, and the device asks). That password works for CardDAV and LDAP
only, so a lost phone or a leaked profile file does not reach the web app, the REST API or MCP. Open the
page in Safari on the iPhone, tap Download, then Settings › Profile Downloaded › Install.

Settings › Apps and devices shows the exact addresses to type, and makes **app passwords**: one per phone or app, revocable on its own, used with your user name for CardDAV, LDAP and the REST API (HTTP Basic, or `Authorization: Bearer <app password>`). *Contacts apps only* (ticked by default) limits a password to CardDAV and LDAP: the web sign-in, the REST API and MCP answer it with 403. Untick it for a script or an AI assistant.

```sh
curl -u alex:iocontacts-xxxxxxxx-… -H 'Accept: application/vcard+json' https://contacts.example.com/api/contacts?q=smith
curl -u alex:iocontacts-xxxxxxxx-… https://contacts.example.com/api/contacts/12?format=vcard4
curl -u alex:iocontacts-xxxxxxxx-… -X POST -H 'Content-Type: text/vcard' --data-binary @card.vcf 'https://contacts.example.com/api/contacts?book=1'
```

## MCP server

ioContacts is also an MCP server, as iopix is, so an assistant such as Claude can work with the contacts: look people up,
read everything about one, add and correct contacts, link relatives and walk the family tree, list birthdays, find and
merge duplicates, import and export vCard and CSV, link contacts to ioPix people, and, for admins, check the server's
health, look for a new version and install it.

It is off until an admin turns it on in **Settings › Server** (or `MCP=1` in the environment); off, `/mcp` does not answer
at all. Every assistant signs in with an **app password** (Settings › Apps and devices), as HTTP Basic or
`Authorization: Bearer <app password>`, and acts as that account: it sees the shared books and that account's private
ones, and may change what the account may change in the web app. The server tools need an admin.

```sh
claude mcp add --transport http iocontacts https://contacts.example.com/mcp --header "Authorization: Bearer iocontacts-xxxxxxxx-…"
```

Apps that take a JSON configuration and only start local processes (Claude Desktop, for example) can reach it through
`mcp-remote`: `{"mcpServers": {"iocontacts": {"command": "npx", "args": ["-y", "mcp-remote", "https://contacts.example.com/mcp", "--header", "Authorization: Bearer ioc-…"]}}}`.
On the server itself, `.venv/bin/python -m app.mcp --user NAME` serves the same tools over stdio.

The tools: `overview`, `list_address_books`, `search_contacts`, `get_contact`, `get_contacts`, `get_vcard`, `view_photo`,
`get_relatives`, `family_tree`, `upcoming_dates`, `birthdays_in_month`, `list_labels`, `relation_types`, `social_services`,
`find_duplicates`, `export_contacts`, `connection_details`, `list_iopix_people`; `create_contact`, `update_contact`,
`delete_contact`, `add_relation`, `remove_relation`, `set_labels`, `set_favorite`, `move_contacts`, `merge_contacts`,
`import_contacts`, `link_iopix_person`, `auto_link_iopix`, `create_address_book`; upkeep:
`find_duplicates`, `preview_merge`, `merge_contacts`, `mark_not_duplicates`, `list_merges`, `undo_merge`,
`data_quality_report`, `fix_data_quality`; enrichment: `lookup_contact`, `suggest_contact_update`, `list_suggestions`
(an assistant proposes; only a person accepts, in the web app); and for admins `diagnostics`, `test_iopix`,
`list_accounts`, `check_for_update`, `update_server`. An app password cannot make more app passwords over MCP.

## Clean up and enrichment

**Clean up** in the web app's sidebar has four tabs, for everyone, on the address books they can see:

- **Duplicates.** Contacts that are probably one person, scored, with the reasons: the same email or phone (written with
  or without the country code), the same name (accents, case and swapped first and last names do not matter), a
  nickname (Bob for Robert, Liesbeth for Elisabeth…), a similar spelling, the same birthday or company. Other
  birthdays, other genders, a Sr./Jr. or a relation between the two count against. The first name has to fit: people
  in one household who share a last name, an address, a home phone or a family email are never offered as
  duplicates, and an email or number on three or more contacts is treated as the household's. **Compare and merge** shows them side by side: which to keep, and for every field where they
  disagree (name, birthday, company, ioPix person…) which value; phones, emails, addresses, profiles, labels and relations
  are combined, each with a box to leave one out. **Not duplicates** keeps two people apart for good.
- **Data quality.** Contacts without a name, email addresses and phone numbers that do not look right, impossible
  birthdays, NAMES IN CAPITALS, the same email or phone twice on a contact, relations to a name that is now a
  contact, numbers without the country code, contacts with no way to reach them; with
  one-click fixes where a fix is safe (capitalising, removing repeats, linking, adding the country code you give).
- **Suggestions.** Enrichment that waits for you: nothing changes a contact until you accept it (one by one, or all for
  a contact), and what you dismiss is not offered again. **Look up** on a contact (or *Look up all contacts*) asks the
  public interfaces that allow it: Gravatar by email (sent as a hash) for the name, job, company, place and the
  profiles the person verified there, and the contact's GitHub, Mastodon and Bluesky profiles. LinkedIn, Facebook,
  Instagram and X have no lookup apps may use; an assistant connected over MCP can research people there and file
  what it finds with `suggest_contact_update`, with the page it found it on.
- **Merge history.** Every merge keeps the contacts as they were, so **Undo** brings them back, relations included.

## Tests

```sh
pip install -e '.[test]'
python -m pytest tests     # on a test MariaDB of its own: a Docker container it starts, or IOSUITE_TEST_DB=host:port:user:password
```

Covered: vCard 2.1/3.0/4.0 and jCard reading and writing (an Apple Contacts card round-trips with relations, dates, social profiles, custom labels and unknown properties), relations and their inverse side, search, content negotiation, Google and Outlook CSV import and every export format, roles and private books, app passwords over Basic and Bearer and the CardDAV/LDAP-only limit, the birthday calendar, duplicates and merging, CardDAV discovery, PUT with preconditions and UID conflicts, multiget, addressbook-query, sync-collection with deletions, LDAP bind (and its throttle) and search with substring, phone and size-limit cases, CardDAV bodies with XML entities (refused), the MCP server (switch, sign-in, reading, changing, relations, a viewer's limits), duplicate scoring (nicknames, shared home numbers, other birthdays), merging with choices and undo, the data quality checks and fixes, and enrichment (lookups, suggestions that wait, accepting and dismissing, over MCP too). CI runs them against MariaDB.

## Layout

```
app/main.py        the application: start-up (tables, first admin, LDAP), the suite's middleware, status and routes
app/access.py      who may call a route: the markers every /api route carries (public, signed_in, admin)
app/config.py      the settings: the suite's standard names (iosuite_shared.config) and ioContacts' own
app/auth.py        iosuite-shared's Auth for this app, and the updater
app/api.py         the REST API, import/export, calendar feed and ioPix routes (sign-in and accounts: iosuite-shared's routers)
app/carddav.py     CardDAV / WebDAV
app/ldapd.py       the LDAP directory (asyncio, its own BER)
app/vcard.py       vCard 2.1/3.0/4.0 and jCard
app/csvio.py       Google and Outlook CSV
app/model.py       address books and contacts in MariaDB, relations, duplicates, merging
app/relations.py   relation types, inverses and labels
app/calendar.py    the iCalendar birthday feed
app/iopix.py       the ioPix client
app/quality.py     duplicates (scored), merging with choices and undo, data quality checks and fixes
app/enrich.py      enrichment: the public lookups and the suggestions queue
app/mcp/           the MCP server: base (who is asking, finding contacts), read, write and admin tools
app/users.py       accounts as ioContacts sees them (the Shared ioSuite database's, through iosuite-shared): roles, the "me" contact, every account's private book, the calendar links
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](LICENSE).
