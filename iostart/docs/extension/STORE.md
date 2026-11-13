# Publishing ioStart Bookmarks to the Chrome Web Store

Everything the store's forms ask for. The package is the `.zip` of the newest `extension-v…` release (or the download
on the start page's Bookmarks page). Chrome, Edge, Vivaldi, Brave and Opera all install from the Chrome Web Store.

## Once

1. Register as a developer at <https://chrome.google.com/webstore/devconsole> (Google account, one-time US$5 fee,
   2-step verification on the account).
2. *New item* › upload the `.zip`.
3. Fill in the forms below, then *Submit for review*. A first review usually takes a few days.

## Store listing

- **Name**: ioStart Bookmarks (from the manifest)
- **Summary**: Keeps this browser's bookmarks the same as your ioStart page's, both ways. (from the manifest)
- **Description**:

  > ioStart Bookmarks keeps this browser's own bookmarks the same as the bookmarks of your ioStart page, both
  > ways. Add, change, move or delete a bookmark in one browser, or on the start page, and every browser follows
  > within a minute.
  >
  > • The bookmarks bar, Other bookmarks and (in Firefox) the bookmarks menu line up the same way in every browser.
  > • One-click sign-in: type your start page's address and say yes. No passwords to copy.
  > • The first sync brings both sides together without doubling or deleting anything, or takes the start page's
  >   bookmarks as they are.
  > • Works in Chrome, Edge, Vivaldi, Brave and other Chromium browsers.
  > • No ads, no tracking, no nags. Your bookmarks go to your own server and nowhere else.
  >
  > Requires an ioStart page (self-hosted, open source): https://github.com/avandeputte/iosuite

- **Category**: Workflow & Planning (or Tools)
- **Language**: English
- **Icon**: `static/extension/icons/128.png`
- **Screenshots** (1280×800): `store-1-sign-in.png`, `store-2-in-sync.png`, `store-3-in-sync-dark.png` in this folder
- **Small promo tile** (440×280, optional): `store-promo-440x280.png`
- **Homepage / support URL**: <https://github.com/avandeputte/iosuite>

## Privacy practices tab

- **Single purpose**: Synchronise the browser's bookmarks with the user's own self-hosted ioStart page.
- **Permission justifications**
  - `bookmarks`: reads the browser's bookmarks to send changes to the user's start page, and creates, changes, moves
    and removes bookmarks to apply the changes that come back. This is the extension's whole function.
  - `storage`: keeps the start page's address, the sign-in made for the extension and the last synced state.
  - `alarms`: checks once a minute whether the bookmarks changed on the start page.
  - Host permission (optional `http://*/*`, `https://*/*`): the start page is self-hosted, so its address is not
    known in advance. Nothing is granted at install; when the user signs in, access to that one address is requested
    and nothing else is ever requested.
- **Remote code**: No, I am not using remote code.
- **Data usage**: tick **Authentication information** (it keeps the sign-in made for it on your start page). The
  form has no box for bookmarks; the nearest is **Web history**, and ticking it is the cautious choice. Leave the
  others unticked. Then certify the three statements (not sold, not used for anything but the single purpose, not
  used for creditworthiness). What it handles goes only to the server the user names (see the privacy policy).
- **Privacy policy URL**: <https://iosuite.iothing.net/docs/privacy/iostart-bookmarks/> (source: `docs/docs/privacy/iostart-bookmarks.md`)

## Distribution tab

- **Visibility**: *Unlisted* (anyone with the link can install; it does not show in search) or *Public*.
- Regions: all.

## New versions, automatically

The workflow `Browser extension` uploads and publishes each new extension version when the repository has these
secrets (Settings › Secrets and variables › Actions):

- `CWS_EXTENSION_ID`: the item's id (the 32 letters in its store address), known after the first upload by hand.
- `CWS_CLIENT_ID`, `CWS_CLIENT_SECRET`, `CWS_REFRESH_TOKEN`: an OAuth client for the Chrome Web Store API, made as
  described at <https://github.com/fregante/chrome-webstore-upload-keys>.

Without them, upload the new release's `.zip` under *Package* › *Upload new package*. Every update is reviewed again,
usually within a day.

## Microsoft Edge Add-ons (optional)

Edge installs from the Chrome Web Store too. Its own store takes the same `.zip` and the same texts at
<https://partner.microsoft.com/dashboard/microsoftedge> (free).
