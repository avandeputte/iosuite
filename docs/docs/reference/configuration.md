---
description: config.env, the settings every ioThing app reads the same way, and the default ports.
---

# Configuration

Every app keeps its settings in **`config.env`** in its own folder: `KEY=value` lines, `#` for comments. The installers
write it; `config.env.example` in each app's folder lists every setting. Variables already in the environment (a
container's, a service's) win over the file. `config.env` holds passwords: keep it readable by the owner only.

## The names every app reads the same way

```sh
# the app's own database
DB_HOST=db.example.lan
DB_PORT=3306
DB_NAME=calendar
DB_USER=calendar
DB_PASSWORD=…

# the Shared ioSuite database (same server as DB_HOST / DB_PORT unless set)
IOSUITE_DB_HOST=…
IOSUITE_DB_PORT=3306
IOSUITE_DB_NAME=iosuite
IOSUITE_DB_USER=iosuite
IOSUITE_DB_PASSWORD=…

PUBLIC_URL=https://calendar.example.com   # the address people and the other apps reach it at
COOKIE_DOMAIN=example.com                 # one sign-in for every app under this domain
HOST=0.0.0.0                              # where the server listens (see below)
PORT=8620                                 # each app has its own default
INTERNAL_URL=http://192.168.1.151:8620    # where the app is inside the network (default: the host's LAN address)
TLS_CERT_FILE=… TLS_KEY_FILE=…            # serve HTTPS directly instead of behind a proxy
ADMIN_USER=…  ADMIN_PASSWORD=…            # the first admin, on an empty Shared ioSuite database
TZ=Europe/Brussels
LOG_FILE=…                                # the server log (default data/<app>.log; empty: none)
UPDATE_CHECK=0                            # lock this app's daily version check off
KEEP_DELETED_DAYS=90                      # how long what a deletion leaves behind is kept (apps that sync: see below)
MCP=1                                     # the MCP server on (apps that have one)
```

On/off switches take `1`/`0`, `true`/`false`, `yes`/`no` or `on`/`off`. Each app adds its own settings (the photo
folder and digiKam for ioPix, the LDAP port for ioContact...); see its README.

`HOST` is every address of the machine by default. Three other ways to set it:

| `HOST` | The app listens on |
| --- | --- |
| `127.0.0.1` | this machine only: for a reverse proxy on the same server, which is then the only way in |
| `192.168.1.151` | that one address, when the machine has several |
| `127.0.0.1,192.168.1.151` | each address named |

With `HOST=127.0.0.1` the suite's other apps on the same server still reach the app directly; apps on other machines
go through `PUBLIC_URL`, so set it. ioContact's LDAP directory listens where `HOST` says unless `LDAP_HOST` names
something else. In Docker, leave `HOST` alone and publish the port where you want it instead
(`ports: ["127.0.0.1:8620:8620"]`). Restart the app after changing it.

`KEEP_DELETED_DAYS` is for the apps that phones and other devices sync with. A deleted event (ioCalendar), task (ioTask) or contact
(ioContact) leaves a marker, so a device learns of the deletion at its next sync; the marker goes after this many days,
and a device that stayed away longer starts its sync over. ioNote keeps the text of a deleted note and its change log
that long (the trash shows 30 days); after that an empty marker stays.

There is no default password for the Shared ioSuite database: `IOSUITE_DB_PASSWORD` is set by the installer, or by you.

Settings that hold for the whole suite are not in `config.env` but in the Shared ioSuite database, changed in any app:
sign-in at the proxy and the addresses of your reverse proxies (Settings › Security), each app's default role and sign-in requirement (Settings › Global settings ›
Apps), and the keys for services outside the suite (Settings › Global settings › Keys and tokens).

## Default ports

| App | Port |
| --- | --- |
| ioPix | 8600 |
| ioNote | 8610 |
| ioCalendar | 8620 |
| ioStart | 8630 |
| ioContact | 8640 (LDAP 3890) |
| ioHealth | 8650 |
| ioDNS | 8660 |
| ioTask | 8670 |
| ioBackup | 8680 |
| ioRecipe | 8690 |
