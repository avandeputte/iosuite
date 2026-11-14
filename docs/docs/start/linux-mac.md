---
description: Install an ioThing app on any Linux machine or Mac with setup.sh.
---

# Any Linux or Mac

Every app is a folder of the suite's repository, with the same three scripts:

```sh
git clone https://github.com/avandeputte/iosuite && cd iosuite/iocalendar
./setup.sh          # asks the questions, installs, writes config.env, starts the service
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, the same settings
```

Replace `iocalendar` with `iopix`, `ionote`, `iostart`, `iocontact`, `iohealth`, `iotask` or `iorecipe`.

## What setup.sh does

It needs Python 3.10 or later (ioHealth: 3.11) and git, and asks for:

- the app's database (host, port, database, user, password), tests the connection and creates the database when the
  user may; ioNote also offers `--sqlite`;
- the Shared ioSuite database, the same way (database and user `iosuite` by default);
- a MariaDB / MySQL administrator, optional, to create the databases and users for you;
- the port (each app's own default), the public address and the sign-in domain (optional), an admin account;
- what is particular to the app: the photos and digiKam for ioPix (it also installs exiftool, ffmpeg and the other
  tools it needs, with apt, dnf, zypper, pacman or Homebrew), the time zone for ioCalendar, ioTask and ioHealth, the optional
  text recognition for ioNote...;
- last, **the list of the suite's apps on this machine**: press Enter for one app, tick others to add them. Running `./setup.sh --apps` later shows it again, to add, remove or reconfigure apps.

Then it makes a Python virtual environment in `.venv`, installs the packages, writes `config.env` (readable by the owner
only), creates the tables and the admin, and installs a service: systemd on Linux when run as root, launchd on a Mac.
Run it again at any time: it keeps what is there.

## Without questions

The flags are the same in every app: `--db`, `--suite-db`, `--admin`, `--port`, `--public-url`, `--cookie-domain`,
`--service`, `--also`, `--remove`, `--reconfigure`, `--db-admin`, `--yes`, plus the app's own (`./setup.sh --help`). Passwords can stay off the
command line in `IO<APP>_DB`, `IO<APP>_SUITE_DB`, `IO<APP>_ADMIN` and `IO<APP>_DB_ADMIN`:

```sh
IOCONTACT_DB=db.lan:3306/contacts:contacts:secret \
IOCONTACT_SUITE_DB=db.lan:3306/iosuite:iosuite:secret \
IOCONTACT_ADMIN=alex:secret ./setup.sh --yes --service
```

## Accounts from the command line

Each app's virtual environment has the suite's command-line tool:

```sh
.venv/bin/iosuite-shared --config . list                              # the accounts
ADMIN_PASSWORD=… .venv/bin/iosuite-shared --config . admin alex --app iocalendar
.venv/bin/iosuite-shared --config . password alex
```

See [Accounts and roles](../run/accounts.md).
