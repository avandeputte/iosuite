---
description: The first sign-in, the first accounts, and what to set next.
---

# First run

## Open the app

Open `http://<host>:<port>`, with the app's port: ioPix 8600, ioNotes 8610, ioCalendar 8620, ioSuite 8630, ioContacts 8640, ioHealth 8650.

The sign-in screen is the same in every app: a tile per account (a click and a password), or *Other* to type a name.

- **The installer made an admin** (you answered the admin question, or set `ADMIN_USER` / `ADMIN_PASSWORD`): sign in
  with it. The first account in a Shared ioSuite database is a **suite admin**: admin in every app, and the one who
  manages the accounts.
- **No account yet**: the app offers to create the first one, right there in the browser. That works only from inside
  your network (or on the server itself), never through a reverse proxy from outside.
- **Another app already uses this Shared ioSuite database**: the accounts are there. Sign in with yours.

## Make the accounts

As a suite admin, open **Settings › Security › People** in any app:

- add an account for each person (name, display name, email, password), or a **passwordless viewer** for a child or a
  kitchen tablet: one click to sign in, on the home network only, and a viewer at most everywhere;
- set each person's role per app under **Roles** (viewer, editor, admin, or none), or leave the app's default;
- decide under **Settings › Global settings › Apps** whether an app is open to everyone with an account (its default
  role) or by invitation only (default role `none`), and whether it requires a sign-in at all.

See [Accounts and roles](../run/accounts.md).

## Next

- Put the app behind HTTPS: [Reverse proxy and HTTPS](../run/reverse-proxy.md), or [Cloudflare Tunnel and Access](../run/cloudflare.md).
- Connect your devices: [Phones, Macs and other apps](../apps/devices.md).
- Settings › Server shows the version and has **Check for updates**: [Updates](../run/updates.md).
- Optionally, let an AI assistant in: [AI assistants (MCP)](../run/assistants.md).
