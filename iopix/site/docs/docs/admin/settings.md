# Settings

**Settings** is the one place for everything an admin configures or runs, apart from the display choices every signed-in account can make for itself (the Display tab is all a non-admin sees).

## Display

| Setting | Does |
| --- | --- |
| Name | what iopix calls itself: the top of the page, the browser tab, the installed app. Left empty (or set to iopix in any capitalisation) it shows the wordmark **ioPix**, with a capital P like the other ioThing apps |
| Appearance | light (default), dark, or follow the device |
| Units | metric or imperial for distances and altitude |
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
| Place tags | create `Places/Country/Region/Town` tags from GPS positions |

## Library

The tools for the library itself, then where it is.

| Tool | Does |
| --- | --- |
| Import | add photos and videos, filed by date |
| File scanner | pick up files added, changed or removed outside iopix |
| Lossless JPEG edits | checks that the lossless rotate and crop tool is installed |
| Trash | everything in digiKam's trash |
| Library copy | iopix's own copy of the library, and when it was last compared with digiKam |
| Rescan the library now | rebuild the search index |
| Metadata consistency | compare database, sidecar and file, and fix what disagrees |
| Metadata quality | missing locations, face problems, and more |
| Duplicate files | sets of byte-identical files, from digiKam's fingerprints, and the space the extras take |
| Date suggestions | a year for each photo marked Date unknown, from every clue the library has about it; **Use** sets the date (see [AI results](../ai/results.md#date-suggestions)) |
| Place suggestions | a position for each photo without one, from the photos around it in time; **Use** sets it |
| Jersey numbers | the player a shirt number points to where the face is not named; **Tag** adds the person |
| Clothing matches | who is probably in a photo by what they wear, within one event; **Tag** adds the person |
| Wrongly rotated | photos that read as on their side or upside down, each shown righted; **Rotate** turns the file losslessly |
| Damaged files | read every file and find JPEGs that stop early, lack their end marker or hold damaged data, damaged PNGs, and pictures that cannot be decoded; a repair where there is one: adding a missing end marker, or cropping a photo whose bottom is missing to the part above the damage (the file copied first, undo in the edit log) |
| Pick labels | how many photos carry digiKam's Rejected, Pending and Accepted labels (iopix never sets them), and **Clear…** to take the chosen ones off every photo: digiKam's database backed up first, sidecars cleaned too, undo in the edit log |
| Edits waiting for digiKam | changes in sidecars not yet in digiKam's database, with **Apply to digiKam database** |
| Tag cover photos | choose a picture for every tag automatically |
| Edit log | every change to every photo, with Undo |

### Where the library is

| Setting | Does |
| --- | --- |
| digiKam database | SQLite folder or MariaDB/MySQL server, with **Test connection** |
| Album roots | where each of digiKam's photo folders is found on this machine |
| iopix database | the MariaDB/MySQL server holding iopix's own data, with **Test connection** and **Use this database**, which copies everything across and restarts iopix; the same panel is the set-up page shown when no database is configured (see [iopix's own database](../connect/iopix-database.md)) |
| Sync with digiKam | on, off, and the merge choices when turning it back on |
| Read-only mode | refuse every change, for everyone |

## AI

The content-search model, background threads (how many cores a job may use) and the switches for each analysis job; then one row per feature with its model or models (download, switch, remove, compare) and every background job with progress, **Check for new photos now** and **Run again from scratch**. See [AI analysis](../ai/overview.md).

## Storage and backups

The size of each part of the data folder, with what can be done about it on the same row, and the free space on the disk. The sizes are measured in the background and remembered for a few minutes, so the page opens quickly even with a large data folder. **Download a backup** offers:

- **digiKam database**: a consistent copy of `digikam4.db` as it is right now, or a fresh dump for MariaDB,
- **iopix data**: `viewer.sql`, a `mysqldump` of iopix's own database, the content-search embeddings files, and a README with the restore steps (`mariadb <database> < viewer.sql`).

## Server

The same panel in every ioThing app: the MCP server switch, the installed version with **Check for updates**, **Update now** and the daily check, the server log (filtered by level or text, with a download of the whole file), and **Restart**.

## Security

For suite admins, the same in every io app: people and their role in every app, roles, app passwords, and sign-in at the proxy. See [Users and sign-in](users.md).

## Global settings

For suite admins: the apps (default role, sign-in required) and the keys and tokens the whole suite uses.
