---
description: One version for the whole suite, and one button that updates every app.
---

# Updates

The suite has one version, the same for every app, and the apps are updated together.

## In the web app

Once a day each app asks GitHub whether the main branch has a newer version (only the public commit list is read;
nothing about your server is sent). When there is one, suite admins see a note on the start page, and **Settings ›
Global settings › Updates** (in any app) has:

- the installed version and the newest one, with **Update** and **Check now**;
- the daily check, on or off for the whole suite (`UPDATE_CHECK=0` in an app's `config.env` locks it off for that app);
- **Details**: every app's own line, with its version and how its last update went. It opens by itself when an app
  failed or was left behind.

**Update** has every app run its own `update.sh`: the new version's Python packages first, then the code (the app's
folder and the shared library, from the same commit; a failed step leaves the running version as it was), the database
is brought up to date, and the service restarts. The page follows along and reloads when the apps are back.

**Settings › Server** in each app shows the version that app runs, the tail of its server log, and **Restart**.

## From a shell

```sh
cd /opt/iocalendar/app      # or wherever the app is
./update.sh                 # the latest code, the same settings
./update.sh --check         # only look
```

In a Proxmox container, `update` does the same for every app in it.

## In Docker

Pull the image instead: `docker compose pull && docker compose up -d`.

## One version

Every install carries its own copy of the suite's shared library, from the same commit as the app, and the version is
that library's. An app that was not running during an update is simply behind: the Updates page says so under
Details, and **Update** brings it along.
