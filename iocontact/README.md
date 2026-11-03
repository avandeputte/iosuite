# ioContacts

*Contacts for the family, in the iothing suite (with [iopix](https://github.com/avandeputte/iopix) and ionotes).*

A self-hosted contact manager: a web app for the whole family, and the standard protocols every mail, contacts and calendar app already speaks, so the same contacts show up on phones, in Apple Contacts, Outlook, Thunderbird and anywhere else. FastAPI and a single-page vanilla JS app, with everything stored in MariaDB / MySQL.

## What it does

- **Contacts** with names (prefix, first, middle, last, suffix, nickname, maiden name, phonetic names), any number of phone numbers, emails and addresses (with labels and a preferred one), birthday (with or without the year), anniversaries and other dates, company, department, job title, social profiles (LinkedIn, Facebook, Instagram, X, Threads, Bluesky, Mastodon, TikTok, YouTube, GitHub, WhatsApp, Telegram, Signal and more), websites, labels, notes and a photo.
- **Relations** between contacts: parents, children, siblings, spouses and partners, grandparents, aunts and uncles, cousins, in-laws, step-family, godparents, friends, colleagues, managers… The other side is kept automatically (make Tim Mary's son and Mary becomes Tim's mother), labels follow the other person's gender (Brother, Sister, Sibling), and a **family tree** page lays the family out by generation. A relation can also name someone who is not a contact.
- **The family and private books**: everyone shares the Family address book; each account also has a private Personal one, and anyone can make more (shared or private). Roles as in iopix: viewers read the shared books (and change only their own), editors change shared contacts, admins also manage users and settings.
- **Birthdays**: the upcoming birthdays and anniversaries, with ages, and a **family birthday calendar** to subscribe to.
- **ioPix**: link a contact to a person named in ioPix. The face from ioPix becomes the avatar (or, with one click, the contact photo), the contact links to that person's photos, and *Link by name* links every contact whose name matches exactly one ioPix person. The ioPix people page lists everyone in ioPix and makes a contact from any of them.
- **Duplicates** (same name, email or phone) and merging, **bulk** favorite, label, move, export and delete, search across names, emails, phone digits, companies, addresses, labels and notes.
- Light and dark, phone-sized screens, installable as an app.

## Standards and APIs

| For | Standard | Where |
| --- | --- | --- |
| Contacts apps: Apple Contacts (Mac, iPhone, iPad), DAVx⁵ on Android, Thunderbird, Evolution, GNOME Contacts, KDE | **CardDAV** (RFC 6352) with sync-collection (RFC 6578), ctag, discovery via `/.well-known/carddav` (RFC 6764) and current-user-principal | `https://host/dav/` |
| Any app that reads contact files | **vCard 3.0** (RFC 2426) and **4.0** (RFC 6350), with Apple's extensions (relations, dates, social profiles and custom labels survive in Apple Contacts); vCard 2.1 is read | CardDAV, `/api/…?format=vcard`, import/export |
| Web and JSON clients | **REST/JSON** with **jCard** (RFC 7095) by content negotiation (`Accept: application/vcard+json` or `text/vcard; version=4.0`) | `/api/`, OpenAPI docs at `/api/docs` |
| Mail apps, desk phones, printers | **LDAP v3** (RFC 4511), read-only, inetOrgPerson plus Thunderbird's mozillaAbPersonAlpha attributes | port 3890 (389 in the Proxmox container) |
| Calendars: Apple Calendar, Google Calendar, Outlook, Thunderbird | **iCalendar** (RFC 5545) subscription of birthdays and anniversaries, yearly events | `/cal/<private token>/family.ics` |
| Moving in and out | vCard files, jCard, and **CSV in Google Contacts' and Outlook's layouts** | Import and export page, `/api/import`, `/api/export` |

Settings › Apps and devices shows the exact addresses to type, and makes **app passwords**: one per phone or app, revocable on its own, used with your user name for CardDAV, LDAP and the REST API (HTTP Basic, or `Authorization: Bearer <app password>`).

```sh
curl -u alex:ioc-xxxxxxxx-… -H 'Accept: application/vcard+json' https://contacts.example.com/api/contacts?q=smith
curl -u alex:ioc-xxxxxxxx-… https://contacts.example.com/api/contacts/12?format=vcard4
curl -u alex:ioc-xxxxxxxx-… -X POST -H 'Content-Type: text/vcard' --data-binary @card.vcf 'https://contacts.example.com/api/contacts?book=1'
```

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

It asks for the MariaDB host, port, database, user and password, the web port (8610), the LDAP port (389), the public address behind your reverse proxy (optional) and the admin account; then the framework's own questions (resources, network). It creates a small Debian 13 container (1 CPU, 512 MB, 4 GB disk by default) and runs the app's own `setup.sh` inside with those answers: packages, settings, tables, admin and the `iocontacts` service. The passwords reach `setup.sh` through its environment (a root-only file pushed in and removed again), never on a command line. The setup's output is kept in `/opt/iocontacts/setup.log`; on failure its last lines are shown with the command to run it again. The container's `update` command pulls the latest code and keeps the settings. For unattended runs set `IOCONTACTS_DB` (`host:port/db:user:password`), `IOCONTACTS_ADMIN` (`name:password`), `IOCONTACTS_PORT`, `IOCONTACTS_LDAP_PORT` and `IOCONTACTS_PUBLIC_URL`. The MariaDB user must be allowed to connect from the container's address.

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

`python -m app.cli create-user NAME [viewer|editor|admin]` and `set-password NAME` manage accounts from a shell (the password from `IOCONTACTS_PASSWORD` or asked for).

## Configuration

`iocontacts.env` next to the app (written by `setup.sh`), or the environment:

| Setting | Meaning |
| --- | --- |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | the MariaDB / MySQL database |
| `PORT` | web port for `run.sh` and the service (8610) |
| `LDAP_PORT`, `LDAP_HOST`, `LDAP_BASE` | the LDAP directory (3890, all addresses, `dc=iocontacts`); `LDAP_PORT=0` turns it off |
| `PUBLIC_URL` | the address people use (behind a proxy), for links in the calendar feed and Settings |
| `ADMIN_USER`, `ADMIN_PASSWORD` | the first admin, made on the first start when there are no accounts |
| `AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `CF_ACCESS_TEAM`, `CF_ACCESS_AUD` | sign-in at a reverse proxy, exactly as in iopix: Cloudflare Access (with token checking), Authelia, Authentik, oauth2-proxy… matched to accounts by email, then name |
| `IOPIX_URL`, `IOPIX_USER`, `IOPIX_PASSWORD`, `IOPIX_CF_CLIENT_ID`, `IOPIX_CF_CLIENT_SECRET` | ioPix (or Settings › ioPix) |

### ioPix

Settings › ioPix (admins) takes ioPix's address. ioContacts talks to ioPix from the server; browsers never need to reach it, so ioPix's LAN address is the simplest choice when both are at home. If ioPix has Require sign-in on, give an ioPix account (a viewer is enough). If the address goes through Cloudflare Access, create a service token (Zero Trust › Access › Service auth), allow it in the ioPix application's policy with a *Service Auth* rule, and enter its client ID and secret. The people list comes from ioPix's People (the named people with photos) and the faces from ioPix's face crops.

### HTTPS

Run it behind a reverse proxy that terminates HTTPS (Caddy, Nginx Proxy Manager, HAProxy, Cloudflare Tunnel), as iopix: iOS and macOS want HTTPS for CardDAV accounts outside the home network, and passwords travel with every CardDAV request. The LDAP directory speaks plain LDAP; keep it on the home network, or put a TLS proxy (stunnel, HAProxy, nginx stream) in front for `ldaps://`.

## Tests

```sh
pip install -e '.[test]'
DB_HOST=127.0.0.1 python -m pytest tests     # against a scratch database contacts_test (TEST_DB_NAME), dropped per test
```

Covered: vCard 2.1/3.0/4.0 and jCard reading and writing (an Apple Contacts card round-trips with relations, dates, social profiles, custom labels, photo and unknown properties), relations and their inverse side, search, content negotiation, Google and Outlook CSV import and every export format, roles and private books, app passwords over Basic and Bearer, the birthday calendar, duplicates and merging, CardDAV discovery, PUT with preconditions and UID conflicts, multiget, addressbook-query, sync-collection with deletions, and LDAP bind and search with substring, phone and size-limit cases. CI runs them against MariaDB.

## Layout

```
app/main.py        the application: start-up (tables, first admin, LDAP), who is asking, routes
app/api.py         the REST API, import/export, calendar feed and ioPix routes
app/carddav.py     CardDAV / WebDAV
app/ldapd.py       the LDAP directory (asyncio, its own BER)
app/vcard.py       vCard 2.1/3.0/4.0 and jCard
app/csvio.py       Google and Outlook CSV
app/model.py       address books and contacts in MariaDB, relations, duplicates, merging
app/relations.py   relation types, inverses and labels
app/calendar.py    the iCalendar birthday feed
app/iopix.py       the ioPix client
app/users.py       accounts, sessions, app passwords      app/proxyauth.py  sign-in at a reverse proxy
static/            the web app (index.html, app.js, app.css, icons)
proxmox/           the community-scripts LXC installer      setup.sh, run.sh, update.sh, Dockerfile
```

MIT licence.
