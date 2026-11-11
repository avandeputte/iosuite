---
description: The app databases and the Shared ioSuite database, and how their tables are named.
---

# Databases

## Two kinds

**The app's own database** holds everything the app keeps: events, contacts, notes (pictures included), health
samples, the photo library's index. One per app, with its own user.

**The Shared ioSuite database** (`iosuite` by default) holds what is the same for every app:

- the accounts, their passwords (Argon2id), sessions and app passwords;
- each account's role in each app, and each app's default role and sign-in requirement;
- the list of installed apps: every app writes its name, version, colour, icon and address there when it starts, which
  is how the start page and the other apps find it without anyone typing an address;
- the suite-wide settings: sign-in at the proxy, keys and tokens.

With one app, the Shared ioSuite database is simply where its accounts live. With several, every app points at the same
one. It can sit on the same server as the app databases.

## Default names

| App | Database and user | Table prefix |
| --- | --- | --- |
| Shared ioSuite database | `iosuite` | `ios_` |
| ioPix | `iopix` | `pix_` |
| ioNotes | `notes` | `nts_` |
| ioCalendar | `calendar` | `cal_` |
| ioSuite (start page) | `suite` | `prt_` |
| ioContacts | `contacts` | `con_` |
| ioHealth | `health` | `hlt_` |
| ioTasks | `tasks` | `tsk_` |
| ioBackup | `backup` | `bkp_` |
| ioRecipe | `recipe` | `rcp_` |

Every table carries its app's prefix, so all of them could share one database if you wanted. The tables are created
on the first start, and every app keeps a `<prefix>_schema_version` table and brings its tables up to date by itself
when it is updated.

## Backups

Back up the databases with ioBackup, the suite's admin tool for database backups (its own app, on port 8680; see its
[README](https://github.com/avandeputte/iobackup)): it backs up the database server on a schedule to a folder or
Google Drive, keeps the newest few, and restores whole databases or single tables. Your usual MariaDB tools
(`mariadb-dump`) work too. The Shared ioSuite database belongs in every
backup: it has the accounts for all the apps. ioPix keeps its own data folder too (thumbnails, models, the edit log's
backups), and ioNotes can export every note to a file under Import and export.
