---
description: One account for every ioThing app, a role per app, suite admins and app passwords.
---

# Accounts and roles

The accounts live in the **Shared ioSuite database**, not in the apps. With one app that changes nothing you'd notice;
with several, everyone has **one name and one password for all of them**, and one sign-in when the apps share a domain.

## What is shared and what is per app

| Shared (one per person) | Per app |
| --- | --- |
| name, display name, email, password | the role: `none`, `viewer`, `editor` or `admin` |
| sessions (the `iothing_session` cookie) | settings and other per-person data |
| suite admin, shown on the sign-in screen or not | app passwords (each made in, and for, one app) |
| sign-in at the proxy (Cloudflare Access...) | sign-in required, default role |

- A **suite admin** is admin in every app and manages the accounts. The first account is one.
- An app's **admin** manages that app's settings, its updates and server log, and the accounts' roles there.
- An **editor** changes shared things (shared calendars, the Family address book); a **viewer** reads them and changes
  only their own. What is private stays private: notes and health data belong to one account, admins included.
- An account without a role in an app holds that app's **default role** (`viewer` unless changed). Set the default to
  `none` and the app is by invitation only.
- A **passwordless** account signs in with one click, on the home network only, and is a viewer at most everywhere:
  for a child, or a tablet on the kitchen wall.

## Where to manage them

In any app, as a suite admin: **Settings › Security** (People, Roles, App passwords, Sign-in at the proxy) and
**Settings › Global settings** (Apps, Keys and tokens). It is the same panel in every app, because it comes from the
suite's shared library. Everyone has **Settings › Account** (name, email, password, their app passwords) and
**Settings › Display** (the theme, kept with the account).

From a shell, in any app's folder:

```sh
.venv/bin/iosuite-shared --config . list
.venv/bin/iosuite-shared --config . create emma --email emma@example.com
.venv/bin/iosuite-shared --config . role emma iocalendar editor
.venv/bin/iosuite-shared --config . password emma
```

## Deleting someone

Delete an account under **Settings › Security › People**: open the person and press Delete. Before anything happens,
the panel asks every app what is only that person's and lists it: their private calendars, lists, address book,
recipes and cookbooks, notes, health data, favourites, private albums, own bookmarks and home page layout, and their
sessions, app passwords and notification devices. To go ahead you type their user name. Each app then removes its
part, the account goes, and the panel shows what was removed.

What they added to something everyone shares stays for the others: events on the Family calendar, tasks on a shared
list, family recipes, shared bookmarks and albums. An app that cannot be reached at that moment removes the person's
data the next time it starts.

## App passwords

Phones, sync apps, scripts and AI assistants sign in with an **app password** instead of your password: one per device
or tool, made under Settings › Account › App passwords, revocable on its own. Each has a scope:

| Scope | Reaches |
| --- | --- |
| everything | what the account may do: the REST API, MCP, sync |
| sync only | the app's sync protocols (CalDAV, CardDAV, LDAP) and nothing else |
| read only | GET requests, outside MCP and sync |

## Sessions and passwords

Sessions are random tokens in an HttpOnly cookie, valid for 30 days and renewed while in use; each records where it
began and was last seen. Passwords are hashed with Argon2id, and wrong passwords cost a growing wait. Sign out ends this
browser's session; an admin can end any session under Security › People.
