# Settings

**Settings** is one page in tabs, in the order every ioThing app uses: Account and Display for every signed-in account; Editing, Library, AI and Server for admins; Security and Global settings for suite admins. Each tab has its own address (`#/settings/display`, `#/settings/security/people`), and every setting saves as soon as you change it. The checks, suggestions and clean-up pages are on [Tools](#tools).

## Account

Your display name, email and password (the same panel in every io app), the person from People your account is linked to, and your app passwords: one per app or device (an MCP client, a script), revoked one at a time.

## Display

| Setting | Does |
| --- | --- |
| Name | what iopix calls itself: the top of the page, the browser tab, the installed app. Left empty (or set to iopix in any capitalisation) it shows the wordmark **ioPix**, with a capital P like the other ioThing apps |
| Theme | light, dark, or follow the device (the default) |
| Units | Automatic (from your region), Kilometres or Miles, for distances and altitude |
| Thumbnail badges | faces, place and favorite badges on thumbnails |
| Info panel | which sections the viewer's info panel shows |
| Map provider | OpenStreetMap, or Google Maps with your key |

Display choices are saved with your account when signed in, else in the browser.

## Editing

| Setting | Does |
| --- | --- |
| Write metadata into image files | also write changes into JPEG, PNG, TIFF and WebP files, not only sidecars |
| Sidecar file names | `photo.jpg.xmp` (digiKam's default) or `photo.xmp` |
| Metadata templates | creator, copyright and contact templates |

## Library

| Setting | Does |
| --- | --- |
| digiKam database | SQLite folder or MariaDB/MySQL server, with **Test connection** |
| Album roots | where each of digiKam's photo folders is found on this machine |
| iopix database | the MariaDB/MySQL server holding iopix's own data, with **Test connection** and **Use this database**, which copies everything across and restarts iopix; the same panel is the set-up page shown when no database is configured (see [iopix's own database](../connect/iopix-database.md)) |
| Sync with digiKam | on, off, and the merge choices when turning it back on |
| File scanner | pick up files added, changed or removed outside iopix: on or off, how often, **Scan now** |

## AI

The content-search model, background threads (how many cores a job may use) and the switches for each analysis job; then one row per feature with its model or models (download, switch, remove, compare) and every background job with progress, **Check for new photos now** and **Run again from scratch**. See [AI analysis](../ai/overview.md).

## Server

The same panel in every ioThing app: the MCP server switch, the installed version, the server log (filtered by level or text, with a download of the whole file), and **Restart**. Then **Download a backup**:

- **digiKam database**: a consistent copy of `digikam4.db` as it is right now, or a fresh dump for MariaDB,
- **iopix data**: `iopix.sql`, a `mysqldump` of iopix's own database, the content-search embeddings files, and a README with the restore steps (`mariadb <database> < iopix.sql`).

## Security

For suite admins, the same in every io app: people and their role in every app, roles, app passwords, and sign-in at the proxy. See [Users and sign-in](users.md).

## Global settings

For suite admins: the apps (default role, sign-in required) and the keys and tokens the whole suite uses.

## Tools

**Tools** (in the sidebar's Manage group, admins) gathers the checks, suggestions and clean-up, each summarised in a line with a link to its page.

| Tool | Does |
| --- | --- |
| Metadata consistency | compare database, sidecar and file, and fix what disagrees |
| Metadata quality | missing locations, face problems, and more |
| Duplicate files | sets of byte-identical files, from digiKam's fingerprints, and the space the extras take |
| Damaged files | read every file and find JPEGs that stop early, lack their end marker or hold damaged data, damaged PNGs, and pictures that cannot be decoded; a repair where there is one (the file copied first, undo in the edit log) |
| Date suggestions | a year for each photo marked Date unknown (see [AI results](../ai/results.md#date-suggestions)) |
| Place suggestions | a position for each photo without one, from the photos around it in time |
| Jersey numbers | the player a shirt number points to where the face is not named |
| Clothing matches | who is probably in a photo by what they wear, within one event |
| Wrongly rotated | photos that read as on their side or upside down; **Rotate** turns the file losslessly |
| Place tags | create `Places/Country/Region/Town` tags from GPS positions |
| Rescan the library | rebuild the search index |
| Edits waiting for digiKam | changes in sidecars not yet in digiKam's database, with **Apply to digiKam database** |
| Pick labels | how many photos carry digiKam's Rejected, Pending and Accepted labels (iopix never sets them), and **Clear…** to take the chosen ones off |
| Tag cover photos | choose a picture for every tag automatically |
