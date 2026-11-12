# ioSuite Bookmarks

A browser extension (Chrome, Edge and other Chromium browsers; Firefox) that keeps the browser's own bookmarks the same
as the ioSuite start page's bookmarks, both ways.

- The bookmarks bar ↔ the top-level folder **Bookmarks bar** (also found as "Bookmarks Toolbar" or "Favorites bar").
- Firefox's bookmarks menu ↔ the top-level folder **Bookmarks menu** (a folder in Other bookmarks in Chrome and Edge).
- Other bookmarks ↔ everything else at the top level.

It syncs a few seconds after a bookmark changes in the browser, every minute (one small request: "did anything
change?"), and when the browser starts. Deletes travel both ways. The first sync either brings both sides together
(folders matched by name, links by address, nothing doubled) or takes the start page's bookmarks as they are.

## Install

**Chrome, Edge**: download the .zip from the start page's Bookmarks page (or a release), unpack it, open
`chrome://extensions` (`edge://extensions`), turn on *Developer mode*, *Load unpacked*, pick the folder. Keep the
folder where it is: the browser loads the extension from it. To update, replace the folder's contents and press the
reload arrow on the extension's card.

**Firefox**: open the signed `.xpi` of a release (`extension-v…` in the repository's releases). Firefox only keeps
extensions Mozilla has signed; unsigned, it can be tried until the next restart from `about:debugging` › *This
Firefox* › *Load Temporary Add-on* (pick `manifest.json`).

Then type the start page's address, choose how the first sync goes, *Sign in*, and say yes in the tab that opens.
The extension gets an app password of its own, for sync only (Settings › Account on the start page lists and removes
it). The browser asks once whether the extension may reach that one address; it has no access to any other site.

## Signing and the stores

- **Firefox, signed for yourself** (not listed anywhere): make an API key at
  <https://addons.mozilla.org/developers/addon/api/key/> and put it in the repository's secrets as `AMO_JWT_ISSUER`
  and `AMO_JWT_SECRET`. The workflow `Browser extension` then has Mozilla sign each new version and attaches the
  `.xpi` to the release.
- **Chrome Web Store / Edge Add-ons** (optional; unpacked works without): a developer account (Chrome: a one-time
  fee), upload the .zip, visibility *Unlisted* or *Private*. The single purpose is bookmark sync; the host permission
  is optional and asked per site at sign-in.

## Files

`manifest.json` (Manifest V3, one for both browsers), `sync.js` (the sync engine; no browser globals, so
`tests/extension/e2e.js` runs it in node against the app), `background.js` (when to sync), `options.*` (sign in,
state), `popup.*`, `lib.js`, `style.css`, `icons/`. A new version: bump `version` in `manifest.json`.
