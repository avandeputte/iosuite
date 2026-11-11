---
description: Install an ioThing app on any Linux machine or Mac with setup.sh.
---

# Any Linux or Mac

Every app has the same three scripts in its repository:

```sh
git clone https://github.com/avandeputte/iocalendar && cd iocalendar
./setup.sh          # asks the questions, installs, writes config.env, starts the service
./run.sh            # or start it in the foreground
./update.sh         # later: the latest code, the same settings
```

Replace `iocalendar` with `iopix`, `ionotes`, `iosuite`, `iocontacts`, `iohealth` or `iotasks`.

## What setup.sh does

It needs Python 3.10 or later (ioHealth: 3.11) and git, and asks for:

- the app's database (host, port, database, user, password), tests the connection and creates the database when the
  user may; ioNotes also offers `--sqlite`;
- the Shared ioSuite database, the same way (database and user `iosuite` by default);
- a MariaDB / MySQL administrator, optional, to create the databases and users for you;
- the port (each app's own default), the public address and the sign-in domain (optional), an admin account;
- what is particular to the app: the photos and digiKam for ioPix (it also installs exiftool, ffmpeg and the other
  tools it needs, with apt, dnf, zypper, pacman or Homebrew), the time zone for ioCalendar, ioTasks and ioHealth, the optional
  text recognition for ioNotes...;
- **Also install other apps of the suite here?** Say no for one app.

Then it makes a Python virtual environment in `.venv`, installs the packages, writes `config.env` (readable by the owner
only), creates the tables and the admin, and installs a service: systemd on Linux when run as root, launchd on a Mac.
Run it again at any time: it keeps what is there.

## Without questions

The flags are the same in every app: `--db`, `--suite-db`, `--admin`, `--port`, `--public-url`, `--cookie-domain`,
`--service`, `--also`, `--db-admin`, `--yes`, plus the app's own (`./setup.sh --help`). Passwords can stay off the
command line in `IO<APP>_DB`, `IO<APP>_SUITE_DB`, `IO<APP>_ADMIN` and `IO<APP>_DB_ADMIN`:

```sh
IOCONTACTS_DB=db.lan:3306/contacts:contacts:secret \
IOCONTACTS_SUITE_DB=db.lan:3306/iosuite:iosuite:secret \
IOCONTACTS_ADMIN=alex:secret ./setup.sh --yes --service
```

## Accounts from the command line

Each app's virtual environment has the suite's command-line tool:

```sh
.venv/bin/iosuite-shared --config . list                              # the accounts
ADMIN_PASSWORD=… .venv/bin/iosuite-shared --config . admin alex --app iocalendar
.venv/bin/iosuite-shared --config . password alex
```

See [Accounts and roles](../run/accounts.md).
