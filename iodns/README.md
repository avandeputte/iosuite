# ioDNS

*The DNS console of the ioThing suite ([ioStart](https://github.com/avandeputte/iosuite/tree/main/iostart), [ioCalendar](https://github.com/avandeputte/iosuite/tree/main/iocalendar),
[ioContact](https://github.com/avandeputte/iosuite/tree/main/iocontact), [ioNote](https://github.com/avandeputte/iosuite/tree/main/ionote), [ioPix](https://github.com/avandeputte/iosuite/tree/main/iopix), [ioHealth](https://github.com/avandeputte/iosuite/tree/main/iohealth)).*

One master list of the house's DNS names, kept in sync on every DNS server: two AdGuard Homes, a Pi-hole, the UniFi
gateway, Cloudflare. Add a name once, see where the servers disagree, pick who is right, push. FastAPI and a
single-page vanilla JS app, built the same way as the other io apps, signed in with the suite's shared accounts
([`iosuite-shared`](https://github.com/avandeputte/iosuite/tree/main/shared)), with its data in MariaDB / MySQL.

## What it does

- **A master list**: a row per name (`calendar.example.com`), with a note, and its records (A, AAAA, CNAME, or a Cloudflare
  Tunnel hostname) per **view**.
- **Views (split-horizon DNS)**: a view is one answer to "who is asking". Internal (the house), External (the internet)
  and Tailscale (the tailnet) to begin with; add more in Settings › Views. Each server answers for one view, so
  `calendar.example.com` can be `192.168.1.151` inside, a public address or a tunnel outside and `100.x` on the
  tailnet, all on one row. A name without an External record is never pushed to public DNS.
- **Compare**: per view, every server is read and compared with the master list name by name: in sync, missing on a
  server, different, or only on a server. Unreachable servers are shown, not fatal; a server only holds some types (or,
  for Cloudflare, some zones), and only those are compared.
- **Resolve**: a decision per name: use the master list, use one server's records (they become the master list's),
  delete everywhere, or leave it. A preview lists every change (the master list and each server's add / change /
  remove) before anything is done. **Push all** makes every server of a view hold the master list (and, if asked,
  removes the names only the servers hold). A changed address is changed in place where the server can (AdGuard
  Home, Cloudflare keeps its proxy setting), so the name never goes unanswered.
- **Push right away**: after an entry is added, changed, renamed or deleted (or the list is imported), ioDNS lists what
  that would change on the servers, in every view, and asks whether to push it now. **Later** leaves it for Compare.
- **Import** from any server, into its view of the master list: merge (add what is missing), merge with the server
  winning, or replace. Also export / import the whole list as JSON (Settings › Export and import).
- **Dynamic DNS**: a record's value can be "Public address": ioDNS finds the house's public IPv4 / IPv6 every few
  minutes (an address-echo service, the UniFi gateway's WAN address, or a page of your own) and, when it changes,
  updates those records and pushes them straight away (Cloudflare…).
- **Cloudflare Tunnel**: a name in the External view can be a tunnel's public hostname (`TUNNEL home|http://192.168.1.151:8620`:
  the tunnel and the service behind it) instead of an address. ioDNS keeps both halves as the dashboard does: the
  tunnel's ingress rule and the proxied CNAME to `<tunnel id>.cfargotunnel.com`. Existing hostnames are compared and
  imported like any other record; a rule with a path, the origin settings and the catch-all are left as they are.
- **Tailscale**: a record's value can be "Tailscale device": the device's tailnet address, read from the Tailscale API
  before every comparison, so the record follows the device. The Tailscale entry also sets up **split DNS** (send
  `example.com` queries on the tailnet to the DNS server that holds the Tailscale view).
- **History**: every change to the list, every push, import and dynamic DNS update, by whom.
- **A background check** compares every view every 30 minutes, so the sidebar shows which views have differences
  and each server's dot says whether it is reachable.
- **For suite admins only**: ioDNS is an **admin tool**, so only the suite admins can use it (everybody else has no
  access here, and it takes no roles or default role); only they see it in the start page and the app switchers, apart
  from the other apps. The servers' passwords and API keys are kept with the suite's
  keys and tokens in the Shared ioSuite database (Settings › Global settings), never shown back.
- **Updates, the server log and Restart** under Settings › Server, as in every ioThing app; light and dark, a phone layout,
  installable as a web app.

## DNS servers

| Kind | What ioDNS keeps there | How it signs in |
| --- | --- | --- |
| **AdGuard Home** | Filters › DNS rewrites (`/control/rewrite/*`) | the web interface's user and password |
| **Pi-hole v6** | Local DNS records and CNAME records (`/api/config/dns/hosts`, `cnameRecords`) | an app password (Settings › Web interface / API). Pi-hole 5 has no API for this. |
| **UniFi gateway** | the gateway's DNS records | an API key (Network 9.3 and later: Settings › Control Plane › Integrations), through the official integration API's DNS policies; or a local admin account, through the web app's static DNS |
| **Cloudflare DNS** | the zones' A, AAAA and CNAME records | an API token with Zone › DNS › Edit; list the zones (empty: every zone the token sees). New records proxied or not, as set. The tunnels' CNAMEs are left to the Cloudflare Tunnel entry. |
| **Cloudflare Tunnel** | the public hostnames of remotely managed tunnels (ingress rules) and their CNAMEs | an API token with Account › Cloudflare Tunnel › Edit and Zone › DNS › Edit; the account ID if the token sees several. Tunnels run from a config.yml can't be changed through the API and are left out. |
| **Tailscale** | nothing is pushed: device addresses and split DNS | an API access token (`tskey-api-…`) or an OAuth client secret |

Every server also has **Names to leave out** (`nas.example.com, *.guest.lan`): names it is never compared on or sent.
A UniFi gateway refuses a record for a name it answers itself (a client of a network with a domain name); ioDNS adds such a
name there by itself.

Adding another kind is one module in `app/providers/`: a `Provider` subclass that lists, adds and deletes records
(`app/providers/__init__.py` says how). A certificate of its own (a UniFi gateway's) is not checked unless asked.

## Run

ioDNS needs Python 3.10+ and a MariaDB or MySQL database. Give it its own database and user, for example:

```sql
CREATE DATABASE dns CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'dns'@'%' IDENTIFIED BY 'dns';
GRANT ALL ON dns.* TO 'dns'@'%';
```

The accounts and the suite-wide settings live in the Shared ioSuite database (`iosuite`, user `iosuite`; the one every
app of the suite uses). The tables are created on the first start and updated by later versions by themselves.

### Proxmox VE (LXC)

`proxmox/ct/iodns.sh` and `proxmox/install/iodns-install.sh` follow the community-scripts (ProxmoxVE) framework layout,
as the other io apps do. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iodns/proxmox/ct/iodns.sh)"
```

It asks for the ioDNS database, the Shared ioSuite database, the web port (8660), the time zone, the public address
behind your reverse proxy (optional), the domain the sign-in is shared on (optional), the admin account and which other
apps of the suite go in the same container, then runs the app's own `setup.sh` inside. For unattended runs set
`IODNS_DB` and `IODNS_SUITE_DB` (`host:port/db:user:password`), `IODNS_ADMIN` (`name:password`), `IODNS_PORT`,
`IODNS_PUBLIC_URL` and `IODNS_COOKIE_DOMAIN`.

### Docker

```sh
docker compose up -d     # edit the CHANGE ME spots in docker-compose.yml first
```

The image (`ghcr.io/avandeputte/iodns`) holds no data: everything is in the database.

### Any Linux or Mac

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iodns
./setup.sh          # asks for the databases, port and admin; installs a systemd service when run as root
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, same settings
```

`setup.sh` takes the same flags as in every app of the suite (`--db`, `--suite-db`, `--admin`, `--port`,
`--public-url`, `--cookie-domain`, `--db-admin`, `--also`, `--service`, `--yes`); `--also` installs other apps of the
suite beside it. From a shell: `python -m app.cli compare internal`, `push internal [--prune]`,
`import SERVER-ID [merge|overwrite|replace]`, `ddns [--push]`, `export`.

## Configuration

`config.env` in the app folder (written by `setup.sh`; `config.env.example` lists every setting), or the environment,
which wins. The names are the suite's (`DB_*`, `IOSUITE_DB_*`, `PUBLIC_URL`, `COOKIE_DOMAIN`, `HOST`, `PORT`,
`TLS_*`, `TZ`, `ADMIN_USER` / `ADMIN_PASSWORD`, `UPDATE_CHECK`, `DATA_DIR`, `LOG_FILE`), plus:

| Setting | Meaning |
| --- | --- |
| `CHECK_MINUTES` | how often every view is compared in the background (30; 0: only when someone looks) |
| `BACKGROUND` | `0` turns the background work off (the comparisons and dynamic DNS) |
| `IODNS_REPO`, `IODNS_BRANCH` | what the version check and `update.sh` follow (`avandeputte/iosuite`, `main`) |

The DNS servers, their passwords and keys, the views and dynamic DNS are set in the app itself.

## API

Everything the web app does is a JSON API under `/api/` (documented at `/api/docs`), open to any client signed in with
the user name and an app password (HTTP Basic or a bearer token): `GET /api/entries`, `POST /api/entries`,
`GET /api/sync/<view>`, `POST /api/sync/<view>/apply` (`{decisions: {name: master | server:<id> | delete | skip}, dryRun}`),
`POST /api/sync/<view>/push`, `POST /api/push` (`{names: [...] | null, dryRun}`: those names in every view), `POST /api/servers/<id>/import`, `POST /api/ddns/run`, `GET /api/history`.

## Tests

```sh
pip install -e ".[test]"
IOSUITE_TEST_DB=127.0.0.1:3306:root:root python -m pytest -q tests
```

The comparison and every provider (against a stand-in of its API) are tested without a database; the API tests need a
MariaDB (a Docker container, or the server `IOSUITE_TEST_DB` names) and use in-memory DNS servers (`tests/fake.py`).

## License

GPL-3.0-or-later.
