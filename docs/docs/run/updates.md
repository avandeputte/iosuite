---
description: How every ioThing app checks for and installs its updates.
---

# Updates

Every app updates itself, on its own schedule, the same way.

## In the web app

Once a day each app asks GitHub whether the main branch has a newer version of the app or of the suite's shared
library (only the public commit list is read; nothing about your server is sent). Admins then see a note with **Update now**. **Settings › Server** has:

- the installed version, **Check for updates** and **Update now**;
- the daily check, on or off (`UPDATE_CHECK=0` in `config.env` locks it off);
- what the server runs on: the database, the time zone, the address;
- the tail of the server log, and **Restart**.

Updating runs the app's own `update.sh`: the new version's Python packages first, then the code (the app's folder and
the shared library, from the same commit) (a failed step leaves the running version as it was), the database is brought up to date, and the service restarts. The page reloads when the
new version answers.

## From a shell

```sh
cd /opt/iocalendar/app      # or wherever the app is
./update.sh                 # the latest code, the same settings
./update.sh --check         # only look
```

In a Proxmox container, `update` does the same for every app in it.

## In Docker

Pull the image instead: `docker compose pull && docker compose up -d`.

## Apps are independent

Updating one app never updates another, and the apps don't need to run the same version: each install carries its own
copy of the suite's shared library, from the same commit as the app. Update them one at a time, whenever suits you, or
all at once from Settings › Global settings › Updates.
