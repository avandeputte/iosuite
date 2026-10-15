# digiKam Viewer

A Google-Photos-style web front end for a digiKam library: FastAPI + a single-page vanilla JS app. It reads digiKam's database and your photos, keeps everything it builds in its own `data/` folder, and writes to the library only for the editing features you turn on.

## Run

```sh
git clone https://github.com/avandeputte/digikam-viewer && cd digikam-viewer
./setup.sh
```

`setup.sh` is the installer: it asks where the photos are, whether digiKam's database is the SQLite file or MySQL/MariaDB (and tests the connection), which features you want (content search, places, objects, text recognition, descriptions; each downloads its model), the port, an admin account, and whether to start the viewer at login (launchd on macOS, systemd on Linux). Then it creates the Python environment, installs the packages, downloads the models, writes `digikam-viewer.env`, creates the admin and starts the service. Run it again at any time to add a feature; it keeps what is there. Flags skip the questions (`./setup.sh --help`), e.g. `./setup.sh --yes --photos /srv/photos --mysql db:3306/digikam:digikam:secret --features search,places --admin alex:secret`.

It also installs what the viewer needs from the system when it is missing: Python 3.10+, `exiftool` (metadata editing), `ffmpeg` (video thumbnails) and the MariaDB client (`mysqldump`, to back a MySQL/MariaDB digiKam database up before writes), with Homebrew on macOS (offering to install Homebrew first) or apt/dnf/zypper/pacman on Linux (`--no-system-deps` to skip). Without the service, `./run.sh` starts it in the foreground.


## Optional features

All chosen in `setup.sh` (or later from Maintenance › AI analysis and models); each is a package plus a model downloaded into `data/models`:

| Feature | What it adds | Download |
| --- | --- | --- |
| Content search | find photos by what is in them; "Detected content" | SigLIP 2 base ~1.5 GB, or CLIP ViT-B/32 ~600 MB |
| Places | town, region, country for GPS positions, offline | GeoNames ~30 MB |
| Object detection | people, animals, vehicles, everyday objects with boxes | YOLOX-S 35 MB |
| Text in photos | signs, jerseys, documents searchable | RapidOCR ~60 MB |
| Photo descriptions | one sentence per photo, searchable | BLIP base ~950 MB plus PyTorch (CPU build ~1 GB) |


## Browsing

The viewer is a web app that installs like an app on a phone or tablet (PWA): open it in the browser and choose "Add to Home Screen" (iOS Safari) or "Install app" (Android Chrome, desktop Chrome/Edge). The layout adapts to narrow screens (bottom navigation, full-width info panel, swipe between photos); a service worker keeps the app shell available, but photos and search always come from the server, so nothing shown is ever stale.

- **Photos**: the whole library as one virtualised timeline grouped by day, with a year scrubber, three tile sizes and several sort orders.
- **Search**: instant suggestions for people, tags, albums, cameras, lenses, photographers, places, years and months; Enter for full-text search across file names, albums, titles, captions, tags, people, recognised text and descriptions. Every pick becomes a chip; chips combine. With content search on, "Photos that look like…" searches by description.
- **Filters**: every piece of metadata for the current results with live counts: type, rating, date range, years, people, tags, albums, location, camera, lens, ISO / aperture / focal length, photographer, file type, plus the analysis filters below.
- **Explore, People, Folders, Albums, Tags, Places, Map**: face-crop avatars from digiKam's face regions, the folder tree (digiKam's albums on disk; editors can create folders and upload photos into them, which digiKam then scans fully on its next start), the viewer's own albums (groupings that live only in the viewer), the full tag tree, places from country to town, and a clustered map of geotagged photos ("Day's trail" draws a day's route).
- **Explore** also lists: Duplicate files (byte-identical files, by digiKam's content hashes), Bursts & best shots, Events & trips, Detected content, Edited here not yet in digiKam.
- **Viewer**: zoom and pan (switches to the original file when zoomed in), keyboard and swipe navigation, a film strip of the neighbouring photos along the bottom edge, slideshow, face boxes, object boxes, video playback, download, Share (the device's own share sheet with the picture attached where the browser has one, else a menu with the links) and an info panel with all metadata, each value a link to matching photos.
- **Appearance**: Settings › Display chooses light, dark or the device's theme and whether thumbnails carry badges (faces, GPS, favorite); saved with the account when signed in, else in the browser. Light is the default; dark or following the device are a choice in Settings.
- **Smart albums**: any filter combination can be saved from the bar above the grid ("Save search") and appears under Albums as a smart album that updates itself; the timeline rail on the right shows a density ribbon (how many photos each month has), a marker naming the month you are at, and on hover a preview of that month with a few thumbnails; it also shows months when the list spans a few years, and a date box in the bar jumps to a day.
- **Keyboard tagging in the viewer**: 0–5 rate, L favorites, T opens the tag dialog (recent tags first), P names the next unnamed face (or lets you draw one), F/O toggle faces and objects, I the info panel.
- **Similar photos** (Explore › Duplicate files): resized, re-saved or burst-neighbour copies found from the content-search embeddings at a chosen strictness, sharpest copy first; the byte-identical sets stay above it. Nothing is ever deleted by the viewer.
- **Face grouping and suggestions** (People › Faces › Unnamed faces): with the SFace model (Maintenance › AI analysis and models, 37 MB) the unnamed faces digiKam found are shown in look-alike groups, each named or ignored in one go, and each group or face carries the viewer's own "looks like" guess (from the most recent confirmed faces of every named person) with a one-click name. A guess is written nowhere until you accept it.
- **Select, favorite, collect**: hover a tile and click its check mark (shift-click for a range, the check on a day header for the whole day, or "Select all"). The selection bar can favorite, add to an app album, tag, edit, set a location or download. Favorites and "My albums" live in `data/viewer.db`, never in digiKam.
- **Download as zip**: "Download" zips the originals of the current search, album or selection, keeping the album folder structure, optionally with XMP sidecars, streamed without temp files. The whole library is never offered as one download. Large downloads are split into parts of 1, 2, 4 or 8 GB (2 GB by default; the API accepts `part_mb` from 100 to 16000) that unzip into one folder.


## AI analysis and background jobs

All analysis runs locally and is stored in `data/viewer.db`; nothing is written to digiKam. New and changed photos are picked up automatically (the digiKam database is polled every `REINDEX_POLL` seconds, 20 by default). Maintenance › AI analysis shows every job with progress, "Check for new photos now" and "Run again from scratch".

Heavy work runs through one queue, one job at a time, in this order: thumbnails, sharpness/exposure/objects, content-search embeddings, text and face quality, descriptions. Each job may use `BG_THREADS` cores (default half the machine, changeable in Settings; a change applies when the next job starts), so the viewer and other apps stay responsive.

| Job | Needs | What you get |
| --- | --- | --- |
| Sharpness and exposure | nothing | measured on a ~1000 px decode: Sharpest / Blurry / Very dark / Very bright filters, "Sharpest first" sort; sharpness shown as a rank within your library |
| Object detection | `setup.sh` | YOLOX-S, 80 everyday object types with boxes; Objects and "people in the picture" filters; O in the viewer |
| Content search | `setup.sh` | SigLIP 2 or CLIP embeddings: text search by description, "More photos like this", Detected content, tag cover photos |
| Text in photos and face quality | `setup.sh` | RapidOCR text, searchable from the search box; face quality as the sharpness of digiKam's face regions.|
| Photo descriptions | `setup.sh` | one sentence per photo from BLIP base, through PyTorch on an Apple GPU when there is one, else on the CPU (about 0.5 s per photo); searchable and shown in the info panel. `CAPTIONS=0` turns the job off |

Derived from these:

- **Detected content**: Explore › Detected content files photos under 752 everyday subjects in 13 groups (landscapes, buildings, rooms, people, events, soccer, other sports, animals, food, vehicles and travel, objects, documents, photo style). These are guesses from the embeddings, not stored labels.
- **Bursts & best shots**: frames taken within 2 seconds on the same camera that also look alike (embedding similarity ≥ 0.80 when content search is on) are grouped; the best frame is the sharpest, nudged by face quality. "Show only the best frame of each burst" is a filter; with editing on, the rest of a burst can be rejected in one click.
- **Events & trips**: trips are runs of days photographed more than 75 km from the town where most of your photos are taken; events are other days with 20 or more photos, named after the title most of them share, else their main tag, else the town.
- **Search model**: `setup.sh` proposes SigLIP 2 (CLIP indexes about 4x faster); the Docker image and the installers download SigLIP 2 first and use it; with neither chosen the viewer uses CLIP. Switch between installed models under Maintenance › AI analysis; the library is re-indexed in the background and search switches when complete. You can switch back at any time.

## Updating

- **Standalone (checkout or the Linux installer):** `./update.sh` in the app folder (`/opt/digikam-viewer/app` after the installer). It pulls the latest code (git, or the GitHub tarball when there is no `.git`), keeps `digikam-viewer.env`, the data folder and the Python environment, reinstalls the package groups that are already installed, and restarts the service (launchd or systemd). `./update.sh --check` only reports; `--force` reinstalls even when nothing is newer; `DIGIKAM_VIEWER_REF=<sha>` installs that commit. When the installed commit is already the one asked for, the script says so and does not restart.
- **Proxmox:** `update` inside the container (the framework's command) runs the same script.
- **Docker:** `docker compose pull && docker compose up -d`.
- **From an MCP client (e.g. Claude):** the `check_for_update` and `update_viewer` tools (`update_viewer` takes an optional `ref`, the commit to install; give it the sha just pushed, because GitHub can still report the previous commit for a short while, and `check_for_update` then shows the outcome under `lastUpdate`); the latter needs the admin token shown under Maintenance › Viewer version › MCP update token (or `MCP_ADMIN_TOKEN` in the environment), because the MCP endpoint has no sign-in of its own; the diagnostics tools take the same token. Treat the token like a password.
- **From the app:** Maintenance › Viewer version shows the installed commit, "Check for updates" compares it with GitHub's main branch, and "Update now" runs `update.sh` (not in Docker, which says to pull instead). The viewer restarts itself when the update finishes.

## Users and permissions

Out of the box the viewer is open to anyone who can reach it. `setup.sh` asks for the admin account; Settings offers **Create the admin account** later (or set `ADMIN_USER` and `ADMIN_PASSWORD` for a container, or run `.venv/bin/python -m app.users create <name> <password> admin`). Once a user exists:

| Who | Can |
| --- | --- |
| Not signed in | browse and search everything, read-only; display settings stay in the browser |
| **viewer** | the same, plus settings, favorites and albums kept on the server (they follow the user to another device) |
| **viewer without a password** | the same; signs in with one click from the account picker (like a media-server profile). An account with no password can never be more than a viewer |
| **editor** | plus every library write: edits, tags, faces, place tags, GPS tracks, metadata sync, applying to digiKam's database |
| **admin** | plus settings, maintenance, models, backups, updates and managing users (Settings › Users) |

**Require sign-in** (Settings › Users) turns the open browsing off: visitors get the sign-in screen and nothing else; no thumbnail, preview or API answer is served without an account. With it on, an MCP client must send the admin token as a header, `Authorization: Bearer <token>` (in Claude Desktop's `mcp-remote` config: `"args": ["mcp-remote", "https://…/mcp", "--header", "Authorization: Bearer <token>"]`).

**Viewer database on MySQL/MariaDB** (Settings › Viewer database, admin): by default the viewer keeps its own data in `data/viewer.db` (SQLite). It can use a MySQL/MariaDB database of its own instead (give it its own database, e.g. `digikam_viewer`, not digiKam's): test the connection, tick "copy all the data" (and "drop and recreate" for a clean slate), and Switch; every row is copied across and the viewer restarts on the new database. The connection settings live in `data/viewer-db.json` (or `VIEWER_DB_TYPE`, `VIEWER_DB_HOST`, `VIEWER_DB_PORT`, `VIEWER_DB_DATABASE`, `VIEWER_DB_USER`, `VIEWER_DB_PASSWORD`), outside the database itself. If that server is unreachable at start, the viewer falls back to the SQLite file and says so in Settings. The backup zip always contains a SQLite copy, whichever is in use, so switching back is the same procedure in reverse.

Each account can be linked to a person from People (Settings › Users, or "Link to a person" in the account dialog): that person's face badge becomes the account's avatar in the account picker and the menu. Each account can also carry an optional email address (Settings › Users). The viewer does not use it yet; it is there so a reverse proxy that authenticates users (Authelia, Authentik, Cloudflare Access…) can later be mapped onto these accounts by the identity it passes.

Sign in from the person icon at the top right: the dialog shows a tile per account; a passwordless viewer signs in with one click, the others ask for their password. Sessions are signed HttpOnly cookies (secret in `data/secret`) valid for 30 days; passwords are scrypt-hashed and never stored in clear. The server enforces all of it: write endpoints answer 401/403 regardless of what the page shows. Read-only mode (an admin setting) still refuses library writes for everyone, editors included.

## Editing

Off by default in the sense that nothing is written until you act; `EDITING=0` removes the controls, `READ_ONLY=1` (or the switch in Settings › Display) locks the whole viewer to browsing and refuses every write endpoint.

Rating, title, caption and keyword tags can be changed in the info panel, with keys in the viewer, or for a whole selection with Edit. Dates, locations, metadata templates, place tags, GPX tracks, faces and the tag manager (below) use the same engine.

**Where edits go, in order:**

1. **XMP sidecar** (`photo.jpg.xmp`), rewritten with exiftool, setting the same fields digiKam writes (checked against digiKam 9.1.0: rating, titles, captions, every tag-path namespace, always the complete tag list). exiftool rewrites the whole sidecar in its own layout (same data, different formatting).
2. **Image file** (optional, Settings › Editing › "Write metadata into image files", like digiKam's "sidecar and file" mode): embedded XMP plus the EXIF, IPTC and JPEG-comment fields digiKam uses. JPEG, PNG, TIFF and WebP only. Only the metadata block changes; pixels are untouched. digiKam notices the changed files and rescans them.
3. **digiKam's database**, only when you ask: "N edits not in digiKam yet" in the left rail or Explore › "Apply edits to digiKam database". Requires digiKam closed (see `DIGIKAM_CHECK`), backs the database up first, applies everything in one transaction and checks integrity before committing. `DB_WRITE=0` disables this. Until then the viewer shows your change and remembers it in `data/viewer.db`; digiKam picks sidecar changes up itself with Item › Reread Metadata From File, at which point the remembered edit is dropped. If you change an edited item in digiKam before that, digiKam may write its own values over the sidecar.

Tag and face operations, place-tag creation and tag badges write the database directly (digiKam closed, backup first) because digiKam owns those tables.

### Dates, locations, templates, place tags, GPX, faces

The location dialog has a place search: an address or landmark ("Mt Lebanon High School") is looked up on OpenStreetMap's Nominatim through the server (one request per second, results cached; only the typed text is sent), and the result is placed on the map; without a connection it falls back to the offline GeoNames towns. A pasted "latitude, longitude" pair fills both fields.

Maps use OpenStreetMap by default (nothing to set up). Settings › Map provider can switch to **Google Maps** with your own API key: create a key in the Google Cloud console with the *Map Tiles API* and the *Geocoding API* enabled and billing on, restrict it to the viewer's address (HTTP referrer), and paste it in Settings (or set `GOOGLE_MAPS_API_KEY`). The server then creates the tile session and the browser loads Google's tiles; place search goes to Google's geocoder; the "open in" link in the info panel points at Google Maps. The key is stored in the viewer's settings and never shown back; if Google refuses the session, the viewer says so and falls back to OpenStreetMap.

- **Date and time**: info panel › "change", or Edit for a selection: set a date, or shift every photo by the same amount. Writes the EXIF, IPTC and XMP date tags digiKam's MetadataHub writes; `ImageInformation.creationDate` in the database.
- **Location**: "Set location on the map" / "change" (one photo), or select any number of photos and use **Set location** in the selection bar to geotag them all at once: click or drag on a map, type coordinates and altitude, copy from the previous photo, or remove. EXIF GPS block and XMP equivalents; `ImagePositions` in the database.
- **Metadata templates**: Settings › Metadata templates defines them; "Apply a metadata template" in the info panel and Edit dialog. Dublin Core, Photoshop, IPTC Core contact and IPTC fields; `ImageCopyright` rows as digiKam's `ItemCopyright::setFromTemplate` writes them. As in digiKam, applying a template sets every field, so blanks clear.
- **Tagging**: "Tag" on the selection bar, with recent tags and creation of new tags ("Parent/New tag" + Enter; digiKam closed).
- **Place tags**: Settings › Place tags, or "Add place tags from GPS positions" in the Tag dialog: creates `Places/Country/Region/Town` tags from the offline geocoder (digiKam closed) and assigns them through the normal edit path. Needs `setup.sh`.
- **GPX correlation**: Edit › "Correlate with GPS track": like digiKam's Geolocation Editor; interpolates between track points, with camera UTC offset, clock correction and maximum gap; preview before writing.
- **Faces**: F in the viewer. Unnamed faces, suggestions ("Name?") and ignored faces are shown next to confirmed ones, each with actions: confirm, name (person picker that can create a new person), ignore, forget the name, remove, and "Add a face" to draw a region. These mirror digiKam's `FaceTagsEditor` rows (`tagRegion`, `faceToTrain`, `autodetectedFace`, `autodetectedPerson`, `ignoredFace`), require digiKam closed, and rewrite the sidecar's `mwg-rs` and `MP` region structures as `MetadataHub::writeFaceTagsMap` does. The People page lists unnamed faces and suggestions to work through.

### Tag manager

Tags › "Manage tags" adds controls to create, rename, move (drag onto a parent or the "top level" zone) and delete keyword tags. Tag definitions live in digiKam's database, so digiKam must be closed and `digikam4.db` is backed up before every change. Renaming, moving or deleting a tag also rewrites the tag path in the sidecar of every photo carrying it or a sub-tag; this runs in the background, resumes after a restart, and backs each sidecar up first. People tags, digiKam's internal tags and tags with face or region data are left to digiKam.

**Badge and thumbnail photos:** the viewer shows the photo chosen in digiKam ("Set as Tag Thumbnail"). To change it here, show faces with F and click "use as badge", or use the photo button on a person or tag chip in the info panel. This writes `Tags.icon` (digiKam closed, backup first).

### Metadata consistency checker

Maintenance › Metadata consistency compares rating, title, caption and tags across digiKam's database, the XMP sidecar and the metadata embedded in the image file. A value absent in one place only counts as a disagreement when another place has one. Results are stored in `data/viewer.db`. "Check new and changed photos" scans what changed since the last check; "Re-check whole library" reads every sidecar and file; "Check the current search only" limits it to the active filters. To fix: select photos, choose the source copy, the targets and the fields, and press Sync. Writes go through the editing engine above (sidecar and file writes with backups; the database path requires digiKam closed and backs up first).

## Backups and what the app writes

Everything the app writes lives in `data/` (`DATA_DIR`), which must not be inside the digiKam or photo folders (the app refuses to start otherwise):

| Path | Contents | Safe to delete? |
| --- | --- | --- |
| `index.db` | search index, rebuilt in about a second whenever digiKam's database changes | yes |
| `cache/t`, `cache/p`, `cache/f` | grid thumbnails, viewer previews (pruned at startup past `PREVIEW_CACHE_MAX_MB`), face crops | yes |
| `viewer.db` | one SQLite file for everything the viewer keeps: favorites, app albums, users, settings, pending edits, the tag-manager queue, and the analysis results (sharpness, objects, text, descriptions, consistency). Installs from before v1.8 are migrated from `state.db` + `analysis.db` at the first start; the old files are parked in `db-backups/migrated-*/`. Absent when the viewer runs on MySQL/MariaDB (below) | **no** (the analysis part can be recomputed, slowly) |
| `viewer-db.json` | where the viewer's own database is, when it is on MySQL/MariaDB (Settings › Viewer database) | no |
| `secret` | the key that signs session cookies; deleting it signs everyone out | yes |
| `embeddings*.npz`, `concepts-*.npy` | content-search vectors per model | yes (recomputed) |
| `models/`, `geonames/`, `bin/` | downloaded models and data | yes (re-download) |
| `sidecar-backups/` | each sidecar as it was before the viewer's first change to it, mirroring the album folders; `tag-ops/<operation>/` for tag-manager rewrites (last 8 operations kept) | your call |
| `file-backups/` | the full original of each image file before its metadata was first rewritten (one per photo, never replaced) | your call |
| `db-backups/` | `digikam4-<time>.db` copies (or `digikam-mysql-<time>.sql` dumps) before every database write; the `digikam4-download-*.db` and `viewer-backup-*.zip` files made for the downloads below; `migrated-*/` with the pre-1.8 files. The last 10 of each kind are kept | your call |
| `viewer.log` | the server's own log lines, rotated (what Maintenance and the MCP `server_log` tool show) | yes |
| `server.log` | the service's output (launchd on macOS; systemd and Docker log elsewhere) | yes |

Every sidecar or file write goes through one function that refuses to proceed unless the backup exists and at least 2 GB of disk stays free. "Undo" in the info panel restores sidecar and file byte for byte. Sidecar and file backups are never deleted automatically; budget disk space for them. To roll back a database write, quit digiKam and copy a backup over `digikam4.db` (or restore the dump).

**Downloads** (Maintenance › Storage, admins): *digiKam database* gives a consistent copy of `digikam4.db` as it is right now (or a fresh `mysqldump` for MariaDB); *Viewer data (zip)* gives `viewer.db` as SQLite whichever database the viewer runs on, plus the `embeddings*.npz` content-search index and a `README.txt` with the restore steps (stop the viewer, copy the files into `data/`). Each download is also kept in `db-backups/`.

The digiKam database is opened read-only (SQLite `mode=ro` + `PRAGMA query_only`; a read-only session on MySQL) except for the explicit writes above. Photo and video files are only opened for reading unless in-file writing is on.

## digiKam on MySQL / MariaDB

digiKam can keep its database in MySQL or MariaDB. Every read and write goes through one layer (`app/dkdb.py`), configured with the `DIGIKAM_DB_*` variables below (or Maintenance › digiKam database); PyMySQL is part of the base install (`pyproject.toml`). Differences the layer handles: dates are UTC on MySQL and local time on SQLite; changes are detected by polling digiKam's scan timestamp and row counts instead of a file's mtime; digiKam's MySQL root tag (`_Digikam_root_tag_`) is treated as "no parent"; backups are `mysqldump`/`mariadb-dump` instead of a file copy. "Is digiKam running" cannot be seen across machines, so use `DIGIKAM_CHECK=ask`.

## Configuration

All settings are environment variables; `setup.sh` writes the ones it asks about to `digikam-viewer.env`. `app/config.py` is the source of truth for the first table (the last five rows live in `app/updates.py`, `app/mcp_server.py` and `app/vdb.py`), `app/dkdb.py` for the second.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DIGIKAM_DB_DIR` | `~/Pictures/digikamDB` | folder containing `digikam4.db` (SQLite) |
| `PHOTOS_ROOT` | `~/Pictures/photos` | photo folder, used when the library has one album root; otherwise digiKam's own per-root paths |
| | | Settings › Album roots maps each album root digiKam recorded (e.g. `/Users/alex/Pictures/photos`) to where it is mounted here (e.g. `/photos` in a container), per root; a saved mapping overrides `PHOTOS_ROOT` |
| `DATA_DIR` | `./data` | everything the app writes; must not be inside the two folders above |
| `AUTO_MODELS` | empty | models to download when missing at start, e.g. `siglip2,yolox,geonames` (keys as in Maintenance › AI analysis and models); set by `setup.sh` and the Docker image |
| `GOOGLE_MAPS_API_KEY` | unset | Google Maps API key (the Settings page can store one instead); used only when the map provider is set to Google |
| `ADMIN_USER` / `ADMIN_PASSWORD` | unset | create the admin account at start when no user exists yet (containers, installers) |
| `READ_ONLY` | `0` | `1` locks the viewer to browsing: every write endpoint is refused, whatever the settings say |
| `EDITING` | `1` | `0` removes metadata editing |
| `DB_WRITE` | `1` | `0` disables "Apply to digiKam database" |
| `DIGIKAM_CHECK` | `pgrep` | how to tell whether digiKam is running before a database write: `pgrep` looks for the process; `ask` (Docker) asks you to confirm it is closed, valid for 10 minutes |
| `SEMANTIC` | `1` | `0` turns content search off even when installed |
| `ANALYSIS` | `1` | `0` turns the background analysis jobs off |
| `CAPTIONS` | `1` | `0` turns the photo-description job off |
| `BG_THREADS` | half the cores | cores one background job may use (capped at cores − 1; also in Settings) |
| `PREWARM_WORKERS` / `ANALYSIS_WORKERS` | `BG_THREADS` | thread counts for the thumbnail pre-warm and the analysis job, if you want them different |
| `PREWARM` | `1` | build all grid thumbnails in the background after startup |
| `REINDEX_POLL` | `20` | seconds between checks for digiKam database changes |
| `THUMB_HEIGHT` / `THUMB_MAX_WIDTH` / `THUMB_QUALITY` | `360` / `1080` / `76` | grid thumbnail size and JPEG quality |
| `PREVIEW_SIZE` / `PREVIEW_QUALITY` | `2560` / `86` | viewer previews: long edge and JPEG quality |
| `PREVIEW_CACHE_MAX_MB` | `8000` | preview cache cap, pruned at startup |
| `EXIFTOOL` | unset | path to exiftool; otherwise the PATH, then digiKam's bundled copy |
| `HF_HUB_OFFLINE` | `1` once models exist | set by the app so the server never contacts the model hub; the download scripts set `0` for their one command |
| `MCP_ADMIN_TOKEN` | unset | the admin token for the MCP diagnostics and update tools (and for `/mcp` when sign-in is required); otherwise one is generated once and shown under Maintenance › Viewer version |
| `VIEWER_URL` | `http://localhost:8600` | the address used for the links in MCP results |
| `VIEWER_DB_TYPE` / `VIEWER_DB_HOST` / `VIEWER_DB_PORT` / `VIEWER_DB_DATABASE` / `VIEWER_DB_USER` / `VIEWER_DB_PASSWORD` | unset | the viewer's own database on MySQL/MariaDB instead of `data/viewer.db` (Settings › Viewer database writes the same thing to `data/viewer-db.json`) |
| `DIGIKAM_VIEWER_REPO` / `DIGIKAM_VIEWER_BRANCH` | `avandeputte/digikam-viewer` / `main` | where update checks and `update.sh` fetch from |

| Variable | Default | Meaning |
| --- | --- | --- |
| `DIGIKAM_DB_TYPE` | `sqlite` | `sqlite` or `mysql` (MariaDB too) |
| `DIGIKAM_DB_HOST` / `DIGIKAM_DB_PORT` | `127.0.0.1` / `3306` | server |
| `DIGIKAM_DB_NAME` / `DIGIKAM_DB_USER` / `DIGIKAM_DB_PASSWORD` | `digikam` / `digikam` / empty | database and account (the same ones digiKam uses) |
| `DIGIKAM_DB_BACKUP` | `auto` | before a write: `mysqldump`/`mariadb-dump` when installed, else the write is refused; `daily`: at most one dump a day for ordinary edits, always a fresh one before bulk or destructive operations (recommended for MariaDB; also in Maintenance › digiKam database); `skip` if the server is backed up another way |
| `DIGIKAM_DB_DUMP` | unset | a command writing a full dump to stdout, used instead of `mysqldump` (e.g. `docker exec mariadb mariadb-dump --single-transaction --routines --triggers -udigikam -pPASS digikam`) |

## Running in Docker

`docker-compose.yml` pulls the published image (`ghcr.io/avandeputte/digikam-viewer:latest`, built by the GitHub workflow for amd64 and arm64) and works as a stack in Dockge or Portainer: set the photos path, the database and the admin password and start it; `docker compose up -d --build` builds from the checkout instead. The image is public; no registry login is needed.

The stack mounts the photo folder read-only at `/library/photos`, keeps everything the viewer writes in the named volume `dkv-data` (mounted at `/data`), and is written for digiKam on MariaDB (`DIGIKAM_DB_*` in the `environment` block); for SQLite drop those lines and uncomment the mount of the digiKam folder at `/library/digikamDB`. `ADMIN_USER` / `ADMIN_PASSWORD` create the admin on the first start. The image (Debian slim, Python 3.12) contains ffmpeg, exiftool, libheif, the MariaDB client and, with the default build argument `AI=1`, the content-search, text-recognition and object-detection packages; `CAPTIONS=1` adds PyTorch (CPU build) and transformers for photo descriptions, which are slow without a GPU. The container's health check polls `/api/status`, which stays open when sign-in is required.

- **Models and data** are not in the image. Download them from Maintenance › AI analysis and models, or with `docker compose exec -e HF_HUB_OFFLINE=0 digikam-viewer python -m app.models download <clip|siglip2|yolox|geonames|blip>`. They land in `/data/models` and `/data/geonames` on the volume and survive rebuilds. `setup.sh` is for the `.venv` install, not the container.
- **Editing** needs the photos mount writable (drop `:ro`): sidecars are written next to the photos, and in-file writing rewrites the photos themselves.
- **Writing digiKam's database** ("Apply to digiKam database", tag manager, faces, place tags, badges, new folders and uploads) needs the digiKam folder writable too when digiKam uses SQLite. With MySQL the folder is not mounted at all (`DIGIKAM_DB_HOST: host.docker.internal` for a server on the Docker host); the image's `mariadb-dump` takes the backup before each write, or `DIGIKAM_DB_DUMP` names a command that does.
- A container cannot see the host's processes, so the Dockerfile sets `DIGIKAM_CHECK=ask`: before a database write the viewer asks you to confirm digiKam is closed.

The image holds no models. On its first start the container downloads the models named in `AUTO_MODELS` (default `siglip2,yolox,geonames`, about 1.6 GB) into the `/data` volume one after another; the library is browsable meanwhile and content search, objects and places switch on as each arrives. Later starts find them in the volume. `AUTO_MODELS=""` skips this; `blip` can be added when the image was built with `CAPTIONS=1`. The same variable works outside Docker (the Linux installer uses it).

## Linux installer

`installer/make-installer.sh` builds `dist/digikam-viewer-install.sh`, one self-extracting file (the app without models, about 200 KB). On the target machine, as root:

```sh
sh digikam-viewer-install.sh --photos /srv/photos --digikam-db /srv/digikamDB
```

It unpacks the app under `/opt/digikam-viewer/app`, then runs the app's own `setup.sh` there with the answers it was given: the system packages the viewer shells out to (python3 with venv, ffmpeg, exiftool, libheif, the MariaDB client) with apt, dnf, zypper or pacman; the venv and the Python packages; the features and their model downloads (`--features search,places,objects,ocr,captions`, `--features none` for browsing only, `--captions` for all of them; asked when not given); the admin account (`--admin NAME:PASS`, asked when not given); the settings in `/opt/digikam-viewer/app/digikam-viewer.env` with the data in `/opt/digikam-viewer/data`. Then it installs and starts a systemd service as the `digikam-viewer` user on port 8600. `--yes` takes every default; `--help` lists the rest (`--prefix`, `--data`, `--port`, `--host`, `--user`, `--mysql HOST:PORT/DB:USER:PASSWORD`, `--read-only`, `--no-service`, `--no-system-deps`). Running it again upgrades the code and keeps the data folder and the env file; so does `./update.sh` in `/opt/digikam-viewer/app`. Tested on Ubuntu 24.04 and Fedora 41. The GitHub workflow builds the installer on every push and attaches it to tagged releases.

## Proxmox VE (LXC)

`proxmox/ct/digikam-viewer.sh` and `proxmox/install/digikam-viewer-install.sh` follow the community-scripts (ProxmoxVE) framework layout, so they can be submitted upstream as they are. Until then the ct script points the framework at this repository for the install script (`COMMUNITY_SCRIPTS_URL`), while the engine itself comes from community-scripts. On the Proxmox host, as root:

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/digikam-viewer/main/proxmox/ct/digikam-viewer.sh)"
```

It asks about the app first: the photo folder and the digiKam folder on the host (or MariaDB host, port, database, user, password), whether the viewer may write into the library (yes: sidecar edits; the mounts are read/write and the container is created privileged, since an unprivileged container cannot write files owned by a host user), which features to install (each downloads its model), and the admin account; then the framework's own questions (resources, network). It creates a Debian 13 container (4 CPU, 4 GB, 16 GB disk by default), bind-mounts the library at `/library/photos` and `/library/digikamDB`, and runs the app's own `setup.sh` inside with those answers: packages, model downloads, settings, admin, and the `digikam-viewer` service on port 8600. For unattended runs set `DKV_PHOTOS`, `DKV_DB` (`sqlite:/path` or `mysql:host:port/db:user:pass`), `DKV_WRITE` (1/0), `DKV_FEATURES` and `DKV_ADMIN` in the environment. The setup's output inside the container is kept in `/opt/digikam-viewer/setup.log`; on failure its last lines are shown and the command to rerun it is printed. The container's `update` command pulls the latest code and keeps the settings and data. Because the container cannot see digiKam's process, `DIGIKAM_CHECK=ask` makes the viewer ask before database writes: the first write that needs digiKam closed (a badge, a tag, a face, applying edits) shows a confirmation; answering yes is remembered for 10 minutes. With MariaDB the question simply means "is every digiKam that uses this database closed?" I could not run these on a Proxmox host; they are checked for syntax and mirror the tested `setup.sh`.


## Reverse proxy and HTTPS (strongly recommended)

The viewer speaks plain HTTP on port 8600 and has no TLS of its own. Run it behind a reverse proxy that terminates HTTPS, such as [Caddy](https://caddyserver.com), [Nginx Proxy Manager](https://nginxproxymanager.com) or HAProxy, and reach it only through that. Besides encryption, HTTPS makes the browser treat the viewer as a secure context, which is what "Add to Home Screen" / "Install app" and the service worker need from any machine other than localhost. Caddy, with automatic certificates:

    photos.example.com {
        reverse_proxy localhost:8600
    }

Two things to keep in mind on any proxy:

- `/mcp` streams responses (server-sent events): the proxy must not buffer that path. Caddy passes streams through as is; with nginx / Nginx Proxy Manager add `proxy_buffering off;` and a long `proxy_read_timeout` for `location /mcp`.
- The web app enforces sign-in for every change, but the MCP endpoint's library tools answer **without** sign-in unless Require sign-in (Settings › Users) is on, in which case every `/mcp` request needs the admin token as a Bearer header. On a proxy that faces the internet, turn Require sign-in on, or restrict `/mcp` to your own networks or put basic authentication on it, or leave it LAN-only; otherwise anyone can read the library through it. Large uploads are not involved, but allow request bodies of a few MB for GPX files.

With the proxy in place the addresses in this README change from `http://<host>:8600/...` to `https://photos.example.com/...`; set `VIEWER_URL=https://photos.example.com` so links in MCP results use it too.

## MCP server

The viewer is also an [MCP](https://modelcontextprotocol.io) server, on the same port, at `/mcp` (streamable HTTP), so an assistant such as Claude can search and inspect the library through the running app; nothing is installed or downloaded. The library tools are read-only and need no sign-in (they show only what an anonymous visitor sees in the web app): `library_overview`, `search_photos` (every filter the web app has, plus `looks_like` text and `similar_to` a photo), `count_by`, `get_photo`, `list_people`, `list_tags`, `list_albums`, `list_places`, `list_app_albums`, `find_duplicates` and `view_photo` (the picture itself); results carry links into the viewer (`VIEWER_URL`). The tools for operating it take the admin token (Maintenance › Viewer version › MCP update token, or `MCP_ADMIN_TOKEN`) because they reveal paths, log lines and settings: `diagnostics` (version, platform, database, external tools, disk, job queue, models, settings without secrets), `server_log` (the viewer's rotating `data/viewer.log`, filterable), `job_queue`, `photo_file` (one photo's files, sidecar, cache and backups), and `update_viewer`, the one tool that changes something (it runs `update.sh`; `check_for_update` is open and reports the outcome under `lastUpdate`). With Require sign-in on, every `/mcp` request must carry `Authorization: Bearer <token>` (see Users and permissions).

    claude mcp add --transport http digikam-library http://localhost:8600/mcp
    claude mcp add --transport http digikam-library https://photos.example.com/mcp     # behind the reverse proxy

**Claude Desktop on another computer** (same network): Claude Desktop's "custom connectors" are reached from Anthropic's servers, so a LAN address cannot be added there. Use the `mcp-remote` bridge in its local configuration instead, which needs Node.js on that computer. Edit `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`), replacing the address with the viewer's host name or IP, then restart Claude Desktop:

    {
      "mcpServers": {
        "digikam-library": {
          "command": "npx",
          "args": ["-y", "mcp-remote", "https://photos.example.com/mcp"]
        }
      }
    }

That is the form behind the reverse proxy; without one, use `http://<host>:8600/mcp` and add `"--allow-http"` to the arguments, since the viewer itself speaks plain HTTP. The tools then appear in Claude Desktop's tool menu. To reach the endpoint from outside the home network it must sit behind the HTTPS proxy with Require sign-in on, so that `/mcp` answers only with the admin token (`"--header", "Authorization: Bearer <token>"` in the `mcp-remote` arguments); do not expose port 8600 to the internet as it is.

Other clients that take an MCP URL use `http://<host>:8600/mcp` directly (set `VIEWER_URL` if links in results should use a different address). Clients that only spawn stdio servers on the machine running the viewer can use `.venv/bin/python -m app.mcp_server` from the checkout; it is the same code.


## Tests

```sh
.venv/bin/python -m pytest tests
```

About 130 tests in ~65 s (the browser tests are most of that). At start the suite cuts a small scratch library (240 photos from a few albums: JPEG, HEIC, PNG, MOV, with faces, tags and GPS) from a real digiKam library by copying the database and letting digiKam's own cascade triggers remove the rest; every test runs against that copy with the viewer's data folder in a temporary directory, so nothing can touch the real library. `DIGIKAM_TEST_DB` and `DIGIKAM_TEST_ROOT` point it at another library (default: `~/Pictures/digikamDB/digikam4.db` and `~/Pictures/photos`). Covered: filters and search, the job queue, settings and read-only mode, the models registry (network stubbed), the read API, tag and face writes against digiKam's rows and backups, new folders and uploads, first-start model downloads and switching the search model, users and permissions, album roots and the digiKam database settings, the viewer database on SQLite and MySQL (the MySQL half runs when a test server is given) and the migration from `state.db` + `analysis.db`, map providers and place search, the MCP endpoint over HTTP, self-update, and browser tests with Playwright (headless Chromium; `python -m playwright install chromium` once) for the grid, lightbox, face toggle, People rows and menus, the person picker, read-only mode, Settings and Maintenance.

## Layout

```
app/            the server (FastAPI) and everything it does: index, search, edits, faces, tags, AI, users…
static/         the web app: one HTML page, app.js, app.css, icons, PWA manifest and service worker
tests/          pytest suite (API on a scratch library, browser tests with Playwright)
setup.sh        the installer: asks, installs, downloads, starts the service      run.sh: foreground start
update.sh       updates an installed copy in place (git or tarball), keeps settings and data
pyproject.toml  dependencies (base + optional groups)
Dockerfile, docker-compose.yml, .github/workflows/docker.yml   the container image; the workflow also runs the syntax checks and builds the installer
installer/      the self-extracting Linux installer (make-installer.sh builds dist/digikam-viewer-install.sh)
proxmox/        Proxmox VE LXC scripts in the community-scripts layout
```

Inside `app/`:

    app/config.py        paths and tunables (environment variables)
    app/main.py          FastAPI routes, zip download, background scheduling
    app/dkdb.py          digiKam database access for SQLite and MySQL/MariaDB, backups
    app/index.py         builds data/index.db from the digiKam database
    app/query.py         filter parameters to SQL (shared by web API and MCP)
    app/thumbs.py        thumbnails, previews, face crops, background pre-warm
    app/vdb.py           the viewer's own database: SQLite (data/viewer.db) or MySQL/MariaDB, one bridge for every module below
    app/state.py         favorites, app albums, settings, the pending-edit and tag-manager queues; migrates state.db + analysis.db
    app/folders.py       digiKam folders: New folder and uploads (Albums and Images rows digiKam completes on its next scan)
    app/jobs.py          the single background job queue
    app/edits.py         metadata edits to XMP sidecars and image files, with backups
    app/dbsync.py        applies pending edits to digiKam's database (on request, digiKam closed)
    app/tagmanager.py    create / rename / move / delete tags, tag badges
    app/facemgr.py       face management mirroring digiKam's FaceTagsEditor
    app/placetags.py     Places/Country/Region/Town tags from GPS
    app/gpx.py           GPX track correlation
    app/consistency.py   database / sidecar / file comparison and directional sync
    app/places.py        offline reverse geocoding (GeoNames)
    app/semantic.py      content search (CLIP or SigLIP 2)
    app/concepts.py      the Detected content vocabulary and tag cover picking
    app/analysis.py      background sharpness, OCR, object and caption analysis (tables in data/viewer.db)
    app/detector.py      YOLOX-S object detection
    app/caption.py       BLIP photo descriptions
    app/moments.py       bursts, events and trips
    app/models.py        model registry, checks for newer model versions, downloads (python -m app.models download <key>)
    app/updates.py       the viewer's own version: installed commit, GitHub check, running update.sh, the MCP admin token
    app/mcp_server.py    MCP server (served at /mcp by the app; stdio with python -m app.mcp_server)
    app/users.py         accounts, roles, sessions, per-user settings, person link and email
    app/geocode.py       place search for the location dialog (Nominatim / Google, offline towns)
    app/maps.py          map provider: OpenStreetMap or Google Maps tiles with the owner's key
