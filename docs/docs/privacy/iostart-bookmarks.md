# Privacy policy: ioStart Bookmarks

*Last updated 13 November 2026.*

ioStart Bookmarks is a browser extension (Chrome, Edge and other Chromium browsers; Firefox) that keeps a browser's
bookmarks the same as the bookmarks of an [ioStart](../apps/iostart.md) start page. ioStart is a self-hosted app:
you, or someone in your household, run it on your own server. The extension's author does not run a server for it.

## In short

The extension sends your bookmarks to one place only: the ioStart server whose address you type into it. Nothing is
sent to the extension's author or to anyone else. Nothing is sold, shared, or used for advertising.

## What it handles

- **Your browser's bookmarks**: names, addresses, folders and their order. It reads them to send changes to your
  start page, and writes the changes that come back from it.
- **Your sign-in for the start page**: the start page's address, your account name, and an app password that the
  start page makes for the extension when you sign in. The app password is for bookmark sync only; you can see and
  remove it on the start page under *Settings › Account*.

It does not read your browsing history, the pages you visit, your tabs, or any other site.

## Where it goes

- **To your start page only.** Bookmarks and the app password go to the address you typed, over the connection that
  address uses (HTTPS when it starts with `https://`). The browser asks you once to let the extension reach that one
  address; it has no access to any other site.
- **Nobody else.** No analytics, no telemetry, no crash reports, no advertising, no third-party services, and no
  remote code. The extension's author receives nothing.

What happens to your bookmarks on the start page is up to whoever runs that server; they stay in its database.

## What it keeps in the browser

The start page's address, your account name, the app password, and a copy of the bookmarks as last synced (used to
work out what changed). All of it is kept in the extension's own storage in your browser. *Sign out* in the
extension's settings deletes it, and so does removing the extension. Removing the app password on the start page
stops the extension from syncing at once.

## Permissions

| Permission | Why |
|---|---|
| `bookmarks` | Read the browser's bookmarks and apply the changes from your start page. |
| `storage` | Keep the items listed above. |
| `alarms` | Check once a minute whether the bookmarks changed on the start page. |
| Access to one site (asked when you sign in) | Talk to your start page. The address isn't known in advance because every start page is self-hosted, so nothing is granted at install. |

## Changes

If the extension ever handles other data or sends it anywhere else, this page will say so first, with a new date at
the top.

## Contact

Questions about this policy: open an issue at
[github.com/avandeputte/iosuite/issues](https://github.com/avandeputte/iosuite/issues). The extension's source is in
the same repository, in `iostart/static/extension/`.
