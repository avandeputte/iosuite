# ioSuite Bookmarks: privacy

ioSuite Bookmarks is a browser extension that keeps a browser's bookmarks the same as the bookmarks of an ioSuite
start page, a self-hosted app that you (or someone in your household) run on your own server.

**What it reads and sends.** The browser's bookmarks (names, addresses, folders and their order), and nothing else.
They are sent only to the start page whose address you type into the extension, over the connection that address
uses (HTTPS when the address is https://). Bookmarks from that start page are written into the browser.

**Who receives it.** Only that server. The extension's author receives nothing: there is no analytics, no telemetry,
no advertising, no third-party service, and no server operated by the author.

**What it keeps in the browser.** The start page's address, the account name, an app password made for the extension
when you sign in (for bookmark sync only; you can remove it on the start page under Settings › Account), and a copy of
the bookmark tree as last synced, used to work out what changed. Signing out of the extension deletes all of it.

**Permissions.** `bookmarks` to read and change the browser's bookmarks; `storage` for the items above; `alarms` to
check for changes every minute; access to one site, the start page you name, asked for when you sign in. The
extension does not read your browsing history, the pages you visit, or any other site.

Questions: open an issue at <https://github.com/avandeputte/iosuite/issues>.
