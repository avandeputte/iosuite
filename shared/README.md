# iosuite-shared

The suite's shared library: the Python package `iosuite-shared` (module `iosuite_shared`).

The Shared ioSuite database for the ioThing apps (ioPix, ioNote, ioContact): one account, one password, one session for
the whole suite. Signed in at `photo.example.com`, a person is signed in at `notes.example.com` too.

## What is shared, what is per app

| Shared (one row per person)            | Per app                                                   |
|----------------------------------------|-----------------------------------------------------------|
| name, display name, email, password    | role: `none`, `viewer`, `member`, `editor` or `admin`     |
| sessions (the `iothing_session` cookie): where each began and was last seen (address, through Cloudflare or not, web or which app, User-Agent) | settings (display preferences) and other per-user data    |
| suite admin flag, sign-in list flag    | app passwords (for CardDAV, LDAP, MCP clients…)           |
| proxy sign-in (Cloudflare Access…)     | `require_login`, `default_role` |

The roles, each able to do what the one before it does:

| Role | Can |
|------|-----|
| `none` | nothing: the app is not theirs |
| `viewer` | look at what is shared with everyone (the Family calendar, shared lists and address books, the photo library) and change nothing |
| `member` | also keep their own private things: calendars, lists, address books, notes, health data, favourites and albums (`access.member`, `users.is_member`) |
| `editor` | also change what is shared with everyone (`access.editor`, `users.can_write`) |
| `admin` | also the app's settings |

A **suite admin** is admin in every app and manages accounts. An account without a role row in an app holds the
app's `default_role` (`member` unless changed; set it to `none` to make an app invitation-only). An **admin tool**
(`Auth(..., admin_tool=True)`: ioDNS, ioBackup) is for suite admins only: everybody else is `none` there, whatever row
or default says, and it has no default role to set. A **passwordless** account signs in with one click on the LAN and
is a member at most, everywhere.

## Install

```
pip install git+https://github.com/avandeputte/iosuite/tree/main/shared.git
```

## Settings: config.env

Every app keeps its settings in `config.env` in its own folder (KEY=value lines, `#` comments; variables already in
the environment, such as a container's, win). The app reads it first, before anything else looks at a setting:

```python
from iosuite_shared import config as shared_config
shared_config.load_file(APP_DIR)            # APP_DIR/config.env into os.environ
globals().update(shared_config.standard("iocalendar", APP_DIR))   # APP_DIR, DATA_DIR, STATIC_DIR, LOG_FILE, HOST, PORT, PUBLIC_URL,
                                                                  # BASE_URL, TLS_*_FILE, MCP_FORCED, KEEP_DELETED_DAYS, ADMIN_USER/PASSWORD
DB = shared_config.own_db("calendar")       # the app's own database: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (no default password)
```

`DATA_DIR` (`APP_DIR/data` by default) is where an app writes on its own; the server log is `LOG_FILE`, `DATA_DIR/<app>.log`
by default (`LOG_FILE=` with nothing after it: none).

The names every app understands the same way:

```
DB_HOST=db.example.lan  DB_PORT=3306  DB_NAME=…  DB_USER=…  DB_PASSWORD=…   # the app's own database
IOSUITE_DB_HOST=…  IOSUITE_DB_PORT=…            # the Shared ioSuite database; default: DB_HOST and DB_PORT
IOSUITE_DB_NAME=iosuite  IOSUITE_DB_USER=iosuite  IOSUITE_DB_PASSWORD=…
PUBLIC_URL=https://notes.example.com             # the address people and the other apps reach the app at
COOKIE_DOMAIN=example.com                        # the session cookie is shared by every host under it; a LAN address gets its own
HOST=0.0.0.0  PORT=8610                          # where the server listens (each app has its own port, below)
INTERNAL_URL=http://192.168.1.151:8610          # where the app is inside the network; default: the host's LAN address and PORT
ADMIN_USER=…  ADMIN_PASSWORD=…                   # the first admin, on an empty Shared ioSuite database
TZ=Europe/Brussels  LOG_FILE=…  UPDATE_CHECK=0  MCP=1
```

`COOKIE_NAME` (default `iothing_session`) and `SESSION_DAYS` (30) rarely need changing. On/off switches take
1/0, true/false, yes/no or on/off (`config.env_flag`).

Default ports, different for every app so that all of them can run on one host (`suite.PORTS`):

| ioPix | ioNote | ioCalendar | ioSuite | ioContact | ioHealth | ioDNS | ioTask | ioBackup | ioRecipe |
|-------|---------|------------|---------|------------|----------|-------|---------|----------|----------|
| 8600  | 8610    | 8620       | 8630    | 8640 (LDAP 3890) | 8650 | 8660 | 8670 | 8680 | 8690 |

The database is the **Shared ioSuite database**: accounts, sessions, roles and app passwords, and the suite-wide
settings and list of apps. Its default name and account are `iosuite`; `IOSUITE_DB_*` are the only variables read.

Proxy sign-in (`AUTH_PROXY`, `AUTH_PROXY_HEADER`, `AUTH_PROXY_TRUSTED`, `AUTH_PROXY_CREATE`, `CF_ACCESS_TEAM`,
`CF_ACCESS_AUD`) is kept once for the whole suite in the Shared ioSuite database and read only from there; it is changed
in any app's Settings › Security › Sign-in at the proxy (`/api/suite-admin/proxy`, suite admins only: whoever sets
them decides who is signed in as whom, so an admin of one app has no route to them).
`config.env` and the environment are never read for them. A proxy that names the user in a header (every preset but
Cloudflare) needs its address in `AUTH_PROXY_TRUSTED`: the header is believed from there only, and with several apps on
one machine "this machine" would let any local process sign in as anyone. For Cloudflare the token is verified, so the
default (127.0.0.1 and ::1, where cloudflared runs) stands.

`AUTH_PROXY_TRUSTED` also decides whether a request comes from **inside the network or outside**
(`Proxy.external`, `auth.outside(request)`), with proxy sign-in on or off. Outside: through Cloudflare, from a public
address, forwarded by a listed proxy for a public address (the right-most address in `X-Forwarded-For` that is not a
listed proxy; what stands left of it is the visitor's own text), or forwarded by a proxy that is **not** listed (a
reverse proxy on another machine has a private address like any visitor of the network, so a request that carries
`X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Real-IP`, `Forwarded` or `Via` from an unlisted
address counts as outside). From outside, one-click sign-in to an account without a password is refused, the first
account cannot be made, and an install without accounts serves nothing but its sign-in screen (below). So a reverse
proxy on another machine goes into `AUTH_PROXY_TRUSTED`, and it has to send `X-Forwarded-For`.
`CF_ACCESS_AUD` takes one AUD tag or several (comma-separated): one Cloudflare Access application covering
`*.example.com` is the simple setup (one AUD), an application per host works too (one AUD each).

## In a FastAPI app

```python
from iosuite_shared.fastapi import Auth
from iosuite_shared import users

auth = Auth("iopix", read_only=lambda: appstate.read_only())
auth.decorate = lambda u: {**u, "person": users.get_value(u["id"], "iopix", "person")}   # optional extra fields
auth.write_role = "member"   # only in an app where everything is one's own (ioNote, ioHealth): canWrite in /me means member

app.middleware("http")(auth.middleware(open_paths=("/", "/index.html"), open_prefixes=("/static/", "/api/auth/"), before=my_gate))
app.include_router(auth.router())         # /api/auth/login, accounts, logout, me, settings, password, setup,
                                          #           sessions (list, DELETE one), app-passwords, suite
app.include_router(auth.users_router())   # /api/users: list, add, the role here (admins of this app); the rest of an account,
                                          #           its sessions and deleting it (suite admins)
app.include_router(auth.status_router(updater, extra=lambda request: {...}))   # GET /api/status (below)
app.include_router(auth.server_router(updater, log_file=LOG_FILE))   # /api/server, /api/log (below)
auth.install(app, limit_for=lambda path, ctype: 4 << 20)   # 400 for bad input, the headers, the body cap, the forwarded headers (below)

@router.post("/api/photos/tag", dependencies=[auth.access.editor_write])
def tag(request: Request):
    user = request.state.user          # {id, name, displayName, email, role, passwordless, suiteAdmin, ...} or None
```

`auth.access` gives `public`, `signed_in`, `member`, `member_write`, `editor`, `editor_write`, `admin`, `admin_write`, `suite_admin`; the
`_write` ones answer 403 while `read_only()` says so. A rule of the app's own gets a marker of its own,
`auth.access.custom("uploader", lambda user, request: ..., "Uploads need an editor")`, so the route says what it needs
instead of carrying `public` and checking inside. The marker is the check: a route does not test the role again in
its body. The JSON shapes are those of iopix's API, so its pages and the ionote/iocontact ones (which copied them)
keep working: `PATCH /api/users/{id}` changes an account, `DELETE /api/users/{id}` removes it;
`POST /api/auth/password {current, password}` changes the caller's own password (never removes it: that is an
admin's decision on the users route).

An account belongs to the whole suite, so an **admin of one app** only lists the accounts, adds one and sets an
account's role in that app (`PATCH /api/users/{id} {role}`, and the app's own fields through `auth.on_update`).
The name, email, display name, password, `listed`, `suiteAdmin`, the roles in other apps, the sessions and deleting
the account take a **suite admin** (403 otherwise): sign-in at a proxy finds an account by its email and name, and a
password opens every app.

**Before the first account** everything is open, to the network the server is on: a request from outside
(`auth.outside`, above) gets the app's shell and the sign-in routes and a 403 `{detail, unclaimed: true}` for
everything else, public routes included; every marker above `public` refuses it too; and `/api/auth/me` and
`/api/status` answer `requireLogin: true`, `unclaimed: true` and no rights, so the page shows the sign-in screen.

Wrong passwords are counted on every path: the sign-in route, HTTP Basic and bearer tokens (`Auth._authorization`)
and, through `users.attempt_wait / attempt_failed / attempt_succeeded`, an app's own server such as ioContact's LDAP.
After `users.LOCK_AFTER` failures for a (visitor, name) pair the next attempt waits (429 with `Retry-After`, before any
hash is computed); the name alone and the address alone have higher limits. The name's counter never holds up a
visitor who signed in to that account from the same address before (so guesses at a name cannot lock its owner
out), a bearer token has no name counter, and every counter starts over after a quiet quarter of an hour. A wrong
password repeated within a few seconds (a client with a stale one) is answered from memory without a hash.

Account passwords are hashed with Argon2id (`argon2-cffi`'s defaults, RFC 9106's low-memory profile: 64 MiB, 3
passes, 4 lanes; `iosuite_shared.passwords`). A hash with other parameters, or an `scrypt2$` hash from 0.28 and
before, is replaced at its account's next sign-in. App passwords are random (144 bits), so they are stored as a
SHA-256 (`passwords.token_hash`), as session tokens are; an `scrypt2$` app password moves over the first time it is
used. Test suites make hashing cheap with
`monkeypatch.setattr("iosuite_shared.passwords.HASHER", testing.FAST_HASHER)`.

The code is in three modules: `iosuite_shared.fastapi` (`Auth`: who is asking, the middleware, `install`),
`iosuite_shared.access` (the markers, the JSON body, the body cap) and `iosuite_shared.routers` (the routers);
`from iosuite_shared.fastapi import Auth, public_user, json_body, BodyCap` keeps working.

The Shared ioSuite database is reached through a small connection pool (`db.Pool`) of connections in autocommit
mode: a statement on its own is one round trip (no ping while the connection was used in the last 30 seconds, no
commit), and `tx()` begins and commits a transaction. An app uses `db.Database` for its own database:
`_db = db.Database(connect)`, then `_db.q`, `_db.one`, `_db.ex`, `_db.many` and `with _db.tx() as con:` (nested calls
on a thread share the transaction, and `q` / `ex` inside the block run in it).

Validation raises `iosuite_shared.Invalid` (a `ValueError`): `raise Invalid("A name is needed")` is a 400 with that
message. ioCalendar and ioContact share their WebDAV plumbing in `iosuite_shared.dav` (the `dav` extra).

A request to an address somebody else chose (a profile's link, a bookmark) goes through `iosuite_shared.outbound`:
`outbound.opener()` is an urllib opener whose connections go to the address that was checked, a redirect's too
(`outbound.public` by default: the internet only; `outbound.not_this_machine` lets the home network in), and
`outbound.check(url)` refuses a URL before anything is sent (`outbound.NotAllowed`, an `Invalid`).

A job that runs once a day (purging what was deleted `KEEP_DELETED_DAYS` ago) is started in the app's lifespan with
`task = chores.start(model.purge_deleted, name="purge of old deletion markers")` and stopped with `task.cancel()`: a
run that fails is logged and tried again at the next turn.

Per-user data: `users.get_settings(uid, app)`, `users.set_settings(uid, app, changes)`, and for anything else
`users.get_value / set_value(uid, app, key, value)` (JSON values).

## Suite administration

`app.include_router(auth.admin_router())` serves everything in the Shared ioSuite database to **suite admins** at
`/api/suite-admin` (module `iosuite_shared.admin`). Its screen ships here too, so every app shows the same one
(Settings › Security and Global settings, suite admins only): `GET /api/suite-admin/ui.js` is one ES module with its own styles that uses the
app's colour variables when it has them.

```js
const ui = await import(new URL('api/suite-admin/ui.js', document.baseURI).href);
ui.mount(el, { tab: 'security', sub: 'people', toast, onSub: (s) => history.replaceState(null, '', `#/settings/security/${s}`) });
// tab security (Security): people, family, roles, passwords, signin; tab global (Global settings): apps, updates, keys
```

The routes:

| Route | What |
|-------|------|
| `GET /api/suite-admin` | `{apps, users, roles, defaultRoles, me}`: every app the database knows (the registered ones, plus keys only seen in roles, settings or app passwords: `registered: false`) with `defaultRole`, `requireLogin` and counts; every account people use (never a service account) with `roles` (explicit, per app), `effective` (the role it holds in each app), `appPasswords`, `sessions`, `lastSeen` |
| `POST /api/suite-admin/users` | a new account: `{name, password ('': one-click, member at most), email, displayName, suiteAdmin, listed, roles: {app: role}}` |
| `PATCH /api/suite-admin/users/{id}` | any of those; `roles: {app: null}` removes the row, so the app's default role applies |
| `GET /api/suite-admin/users/{id}/data` | what deleting it would remove: `{apps: [{app, name, items: [{what, count, kept}], error}], shared}`, every app asked with the suite admin's own sign-in (`iosuite_shared.persondata`) |
| `DELETE /api/suite-admin/users/{id}` | the account, everywhere, with what the person kept in every app; answers what was removed (same shape; `pending` on an app that could not be reached and removes it at its next start) |
| `GET`/`DELETE /api/suite-admin/person-data/{id}` | this app's part alone: counted, or removed (the panel calls every app's) |
| `GET /api/suite-admin/family` | `{items, palette}`: every account people use with `inFamily`, `initials`, `color`, `colorPicked`, `contactId` (+ `contactName`), `photoPerson`, `hasFace` (the family, below) |
| `PATCH /api/suite-admin/family/{id}` | `{inFamily, color ('#rrggbb'; null: the next free one), contactId, photoPerson}` |
| `GET /api/suite-admin/family/contacts?q=` | cards in ioContact to link a member to (read from ioContact) |
| `GET`/`DELETE /api/suite-admin/users/{id}/sessions` | its sessions; end all, or one with `?session=` |
| `GET /api/suite-admin/app-passwords?user=&app=` | every app password (never the secret) |
| `POST /api/suite-admin/app-passwords` | `{userId, app, label, scope}`: a new one for that account, shown once |
| `PATCH /api/suite-admin/app-passwords/{id}` | `{scope}`: `''` everything, `dav` the app's sync protocols only |
| `DELETE /api/suite-admin/app-passwords/{id}` | revoke one |
| `PATCH /api/suite-admin/apps/{app}` | `{defaultRole: none/viewer/member/editor, requireLogin}` (an admin tool has no default role, and always requires sign-in: `requireLogin: false` is refused). Sign-in required is on unless turned off (a `require_login` row of `0`) |
| `DELETE /api/suite-admin/apps/{app}` | off the list (it registers again if it starts); `?data=1` also drops its roles, settings, app passwords and keys |
| `GET /api/suite-admin/keys?app=` | every app's keys and tokens (`iosuite_shared.credentials`), never the value: `{app ('' : the whole suite), appName, name, label, hint, set, env, envSet, updated, updatedBy}` |
| `PUT /api/suite-admin/keys/{app}/{name}` | `{value}`: replace it (`''` clears it); `_suite` for the whole suite's keys |
| `DELETE /api/suite-admin/keys/{app}/{name}` | clear it |
| `GET /api/suite-admin/updates` | the suite as one thing: `{installed, latest, status: current / update / updating / error, checked, behind, failed, canUpdate, autoCheck, apps}`; `apps` has every app's own line: its version and commit, whether it runs (`watching`), whether it is `behind`, its last update (`iosuite_shared.suiteupdates`, below) |
| `POST /api/suite-admin/updates` | `{action: check}` asks every app to look at GitHub again, `{action: update}` updates every app that is behind; `{autoCheck: bool}` is the daily check, one switch for the suite |

An app says what a person keeps in it with `auth.person_data = fn`, where `fn(user_id, remove)` returns
`[{"what": "private calendars", "count": 2}, {"what": "events they added to shared calendars", "count": 5, "kept": True}]`,
counting with `remove` False and removing (everything not `kept`) with `remove` True. What someone added to something
everyone shares is never removed. An app without one keeps nothing per person.

**The family** (`iosuite_shared.family`, Settings › Security › Family) is one list for every app: ioCalendar tags
events with its members, ioTask gives them tasks. Everyone with an account people use is in it unless a suite admin
took them out; each member has a colour (picked, else the next free one of `family.PALETTE` by their place in the
list), initials, their ioContact card (the account's "me" contact) and their person in ioPix's People. Every signed-in
account reads it at `GET /api/auth/family` (`[{id, name, displayName, initials, color, hasFace}]`) and a member's face
at `GET /api/auth/family/{id}/face` (their ioPix person's, else their card's photo), so the same person looks the same
in every app. An app calls `family.members()` and keeps the ones with a role there.

The usual rules hold: a one-click account is a member at most and has no app passwords, an admin tool takes no roles, the last suite admin stays, and
the signed-in admin cannot delete their own account, drop their own suite admin or remove their own password here.

## The status, the error answers, the headers and the body cap

`GET /api/status` answers everyone, sign-in required or not, with the same shape in every app, so the start page, the
containers' health checks and the apps' shells read it alike:

```
{ok, app, name, version, usersExist, requireLogin, signedIn, isAdmin, viaProxy, user: {id, name, displayName, email, role, suiteAdmin, passwordless} | null,
 commit (signed in), ...extra(request)}
```

`auth.install(app)` adds what every app's FastAPI gets the same way: `Invalid` or malformed JSON out of a route
answers `400 {"detail": "Bad request: ..."}`; any other `ValueError` does too, and is logged with its traceback,
since nothing meant it for the client (a `TypeError` is a bug and stays a 500 with its traceback;
`not_found=(MyNotFound,)` names exceptions that mean 404);
`X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`, `X-Frame-Options: SAMEORIGIN` and
`Content-Security-Policy: frame-ancestors 'self'` on everything, `Cache-Control: no-store` on
`/api/` and `no-cache` elsewhere unless the route set its own; a body cap: a request larger than
`limit_for(path, content_type)` bytes (`body_limit`, 4 MB, by default) is refused with 413 by its Content-Length
before it is read, and as it arrives when it comes chunked or longer than it said; and the forwarded headers
(`proxyauth.Forwarded`): the address the connection really came from is kept for proxy sign-in and the throttles, and
`X-Forwarded-For` / `X-Forwarded-Proto` are believed from this machine and from the reverse proxies listed in
`AUTH_PROXY_TRUSTED` (Settings › Security), the one list that says where the proxies are.
The apps start uvicorn with `proxy_headers=False`, so this is the one place the headers are read.

## MCP

Every app's MCP server is the same server over streamable HTTP at `/mcp`, on the app's own port, and an assistant
signs in like any other client: HTTP Basic with the user name and an app password, or a bearer app password
(Settings › Account › App passwords). Every tool acts as that account. The switch is the app's `mcp_enabled` setting (off
until an admin turns it on under Settings › Server; `MCP=1` in the environment keeps it on).

```python
from iosuite_shared import mcp as shared_mcp
server = shared_mcp.make_server("iocalendar", "ioCalendar", __version__, instructions="...")
mcp_on = lambda: shared_mcp.enabled(db.get_setting, config.MCP_FORCED)
app.middleware("http")(auth.middleware(..., open_prefixes=("/mcp",), before=auth.mcp_gate(mcp_on, on_user=shared_mcp.current_user.set)))
shared_mcp.mount(app, server)                              # the /mcp routes, ahead of the app's own
async with shared_mcp.running(server): yield               # in the lifespan

@server.tool(annotations=shared_mcp.READ_ONLY)             # READ_ONLY, WRITES, ADDS, DELETES, UPDATES
def overview():
    u = shared_mcp.who()                                   # or need_writer(), need_admin(); clamp(n, lo, hi) for page sizes
```

`auth.mcp_gate` answers 404 while the switch is off ("The MCP server is switched off (Settings › Server).") and 401 when
nobody is signed in; `shared_mcp.set_enabled(db.set_setting, on, forced)` saves the switch from `POST /api/server`.

## Settings › Account and Display

The account's own boxes look and work the same in every app: `static/account-panel.js`, at `GET /api/auth/ui.js`
(the Server panel shares its styles). The display name and email are saved when a field is left (`PATCH
/api/auth/me {displayName, email}`, then `auth.on_update(user_id, body)` for the app's own caches), the theme and
units go with the account's settings (`POST /api/auth/settings {theme, units}`), and the app passwords are the
account's own in this app.

```js
const ui = await import(new URL('api/auth/ui.js', document.baseURI).href);
await ui.mountAccount(el, { toast });                                  // You (display name, email) and Password
el.append(ui.box('theme', 'Appearance', ui.themeRow(theme, applyTheme)));   // Light, Dark, System
el.append(ui.box('tune', 'Units', ui.unitsRow(units, applyUnits)));    // Automatic, Kilometres, Miles
const pw = el.appendChild(document.createElement('div'));          // app passwords, below the account on Settings › Account
await ui.mountAppPasswords(pw, { toast, syncOnly: 'Calendar apps only (CalDAV)' });
```

`ui.box(icon, title, ...rows)` and `ui.row(label, hint, control)` draw the app's own Settings boxes in the same look.

## Notifications

Web push from any app to the people who turned it on (`iosuite_shared.push`). Settings › Account › Notifications
(part of `ui.mountAccount`, so every app has it; `ui.mountNotifications(el, {toast})` on its own) turns them on for
the device it is opened on and says what the account gets; one app per device is enough, since every app sends to
every device of the account and a tap opens the app the notification is about. On an iPhone or iPad it works in a
home-screen app (iOS 16.4 and later). The service worker (`/api/auth/push/sw.js`, `static/push-sw.js`) only shows
notifications: no fetch handler and no cache, and its scope is its own folder, so it never stands between an app and
its pages.

| Kind | From | When | Who |
|------|------|------|-----|
| `tasks` | ioTask | a task's alert goes off (a task with a time and no alert: when it falls due); at the person's morning time, what is due today and late | the members a task is tagged with, else the owner of its private list, else whoever added it |
| `events` | ioCalendar | an event's reminder goes off (an all-day event's counts from the start of its day) | the same rule, with calendars |
| `birthdays` | ioContact | at the person's morning time: today's birthdays ("Remind me" on) and anniversaries | whoever sees the address book |
| `health` | ioHealth | a sync brings today's value up to one of the account's daily "at least" goals (steps, minutes, kcal, hours, the rings) | the account itself |
| `backups` | ioBackup | a backup or restore fails | suite admins |
| `updates` | every app's daily check | a newer version of the suite is on GitHub | suite admins |

A kind is offered only to people who use its app (a role there that is not `none`, and the app installed); each can be
turned off, and the morning time (08:00 by default, the server's time zone) is the account's. A message that must go
out once (`once=` key) goes out once, whichever app or restart gets there, through `ios_push_sent`.

```python
from iosuite_shared import push
for u in push.recipients("tasks"):            # who has a device, may get the kind and wants it
    push.notify(u["id"], "tasks", "Pack the swim bag", "Due now", url=push.link("iotask", "#/today"), once=f"task:{uid}:{due}")
push.notify_admins("backups", "Backup failed: nightly", str(error))
push.is_morning(user_id)                       # the person's morning time came, within the last 6 hours
```

The sender's key (VAPID) is made the first time it is needed and kept with the suite's keys (Settings › Global
settings › Keys and tokens, "Notifications sender key"); clearing it there makes a new one, and every device has to
turn notifications on again. Messages are encrypted for the device (RFC 8291), so the push service between the
server and the device (Apple's, Google's, Mozilla's) cannot read them. A device the push service says is gone (404,
410) is removed.

| Route | What |
|---|---|
| `GET /api/auth/push` | `{key, morning, kinds: [{kind, label, hint, on, admin}], devices: [{id, label, app, appName, created, lastOk, endpointHash}]}` |
| `POST /api/auth/push/devices` | `{subscription: {endpoint, keys: {p256dh, auth}}, standalone}`: notifications on for this browser |
| `DELETE /api/auth/push/devices/{id}` | off for that device |
| `PUT /api/auth/push/prefs` | `{kinds: {kind: bool}, morning: "HH:MM"}` |
| `POST /api/auth/push/test` | a test to every device of the account: `{sent, devices}` |

## Updates, restart and the server log

The suite has one version: `iosuite_shared.__version__`, which every app reports as its own
(`from iosuite_shared import __version__` in the app's `app/__init__.py`). Bump that one line with every change that
reaches users, whichever app it is in. A newer version on GitHub is an update for every app, and the apps are updated
together.

Every app updates itself the same way, from `iosuite_shared.updates`: the installed commit, a daily check of GitHub
for a newer version, the app's own `update.sh`, a restart, and the tail of the server log. `Auth.server_router` serves
the app's own part at the same addresses in every app (admins only), with the panel that shows it: Settings › Server
is one ES module (`static/server-panel.js`, at `GET /api/server/ui.js`) that every app mounts in its Server tab, so
the page is the same everywhere.

```js
const ui = await import(new URL('api/server/ui.js', document.baseURI).href);
ui.mount(el, { toast });          // the MCP switch, the version, the server log, Restart
```

```python
from iosuite_shared.updates import Updater

updater = Updater("iocalendar", version=__version__, root=ROOT)   # repo avandeputte/iosuite, branch main, update.sh in ROOT
updater.start_daily()                                             # checks once a day while the suite's switch is on, and watches for requests
app.include_router(auth.server_router(updater, log_file=LOG_FILE,
    info=lambda: {"mcpEnabled": mcp_enabled(), "mcpLocked": MCP_FORCED},  # extra fields of GET /api/server: the MCP box
    apply=save_switches))                                         # the app's own switches in the POST body (raise Invalid to refuse)
```

| Route | What |
|---|---|
| `GET /api/server/ui.js` | the Settings › Server panel (it imports `GET /api/auth/ui.js`) |
| `GET /api/server` | `{name, version, installed, docker, canRun, repo, branch, progress, lastUpdate}` + `info()` |
| `POST /api/server {action: restart}` | ends the process; systemd, launchd or Docker starts it again. Other keys go to `apply(body)` |
| `GET /api/log?lines&level&contains&requests` | the tail of `log_file` (`level`: any, warning, error, auth) |
| `GET /api/log/download` | the whole file |

`update.sh` gets `<APP>_RESULT`, `<APP>_REPO`, `<APP>_BRANCH` and `<APP>_REF` in its environment (`IOCALENDAR_RESULT`…)
and writes `ok: …` or `error: …` to the result file before the restart. `<APP>_REPO` and `<APP>_BRANCH` in the app's
environment change what is followed; `UPDATE_CHECK=0` locks the daily check off for that app. It installs the tip of
the branch; another commit is installed from a shell on the server only (`<APP>_REF=<commit> ./update.sh`): GitHub
serves a fork's commits under the repository's address, so a commit id from a request could be anybody's code.

### One update for the suite

A suite admin checks and updates the suite in one place: Settings › Global settings › Updates in any app (one line,
one **Update** button, every app's own line under Details), or the start page's MCP tools `suite_version` and
`update_suite` (`shared_mcp.add_suite_update_tools(server)`). There is no update button per app. The apps do not call
each other for it: the request goes into `ios_updates` (one row per app) in the Shared ioSuite database, and
`updater.start_daily()` also watches the app's own row every ten seconds (`watch=False` leaves that out) and marks it
every minute, which is how the page tells the apps that run from the ones that stopped. A check asks GitHub, an update
runs `update.sh` (an app that cannot run it here, in Docker or without a .venv or write access, says so on its row). Each app
writes back its installed version and commit, the newest version on GitHub, whether it can update itself, and how its
last update went (running, ok, failed and the result line); after the restart the new process finishes that line from
the result file. `suiteupdates.summary()` makes one answer of the rows: the version the running apps have, the newest
one, and the apps still behind.

Every app's `update.sh` is the same script, rendered from `templates/update.sh`; only the block "the app" differs
(name, label, repository, the `server` subfolder for ioHealth, the files an installed copy gets, optional package
groups). Render it from a checkout of this repository:

    python3 templates/render-update.py <app dir> iopix ioPix avandeputte/iopix "" "app static pyproject.toml ..." [groups-file] [after-file]

A groups file holds one `  has <group> <module>` line per optional extra (`  has ocr rapidocr`); the after file is shell
that runs once the new code is in place. Change the template here, then render it into every app.

`updates.setup_log(LOG_FILE)` sets logging up the same way in every app: INFO to stderr, and a rotating copy of
everything (5 MB, 3 old files, uvicorn's lines included) in `LOG_FILE`, which `tail()` and `GET /api/log` read. The daily-check switch is a setting of the app in the Shared ioSuite
database; pass `settings=(get, set)` to keep it elsewhere.

## The suite's apps

Each app installs on its own, so the Shared ioSuite database also keeps the list of the suite's apps (table `ios_apps`), which
every app writes itself: no address to type into the start page or into another app.

```python
auth = Auth("iocalendar", app_label="ioCalendar", version=__version__, public_url=config.PUBLIC_URL,
            description="Calendar", color="#963522")
```

Every app serves its web app's files under `/static/` and its mark at `/static/icons/mark.svg` (`suite.ICON`,
`static/icons/mark.svg` in the repo), so the icon is not something an app passes.

At its first request (`auth.resolve()`, which `auth.middleware()` calls, and so does an app's own middleware) the app registers (name, version, description, colour, icon, and its `PUBLIC_URL` when it has
one), and the middleware keeps the best address one of its admins reaches it at (before the first account: anyone
inside the network): a host under `COOKIE_DOMAIN` over HTTPS beats a LAN name, which beats an IP address; loopback
and test hosts are never kept. A visitor's request never names it: the address is the request's Host header, which
a client sets to whatever it likes. `url` is the configured address, else
that one. `register=False` keeps an app out.

Each app also records where it is inside the network (`internal_url`, `internalUrl`): its `INTERNAL_URL`, else
`suite.local_url()`, made from the host's LAN address and `PORT` (`HOST` when it names an address; none when the
server listens on loopback only, or in a Docker container, where `INTERNAL_URL` has to say it). It is written at every
start, for reference only: nothing links to it, and `url` stays as above.

```python
from iosuite_shared import suite
suite.apps()            # [{app, name, description, version, color, icon, url, configuredUrl, seenUrl, internalUrl, adminTool, lastSeen, ...}]
suite.visible(user)     # the ones this account may use (below)
suite.url_of("iopix")   # "https://photo.example.com" or None
```

An account sees only the apps it has a role in: its own role there, else that app's default role, is not `none`
(somebody without ioHealth does not see ioHealth). An app made with `Auth(..., admin_tool=True)` (ioDNS, the tools
behind the scenes) is an **admin tool**: only its admins and the suite admins see it, and a switcher shows it apart,
under the apps and with a smaller icon (`adminTool` is true).

The list comes in one order everywhere: ioSuite (the start page) first, then the others by name. Every app's switcher
keeps that order and lists the app it is in too (marked as the current one), so the menu looks the same in each app.

App ids are the apps' names in lower case (`ionote`, `iotask`, `iocontact`...). Schema 8 moved what the shared tables kept
under the plural ids of before (`ionotes`, `iotasks`, `iocontacts`) to the singular ones, once, at the first start on 0.45.0.

Over HTTP: `GET /api/auth/suite` (signed in) lists the ones the account may use (`suite.visible`); `DELETE /api/auth/suite/{app}` (suite admins) forgets an
uninstalled one (it comes back if it starts again).

## Tests

`iosuite_shared.testing` gives every app's suite its MariaDB (`server()`, `fresh_database(name)`, `auth_env(name)`:
Docker, or `IOSUITE_TEST_DB=host:port:user:password`), `clean_shared_tables(auth)` to empty the shared tables between
tests, and two checks every app runs: `check_conventions(root, app, version, config)` (the suite's port, one version,
`config.env`) and `check_access_declared(app, access.declared)` (every API route carries an access marker; it walks included routers too, and fails when it finds no route to check). `api_routes(app)` lists every API route with its full path.

## Database naming convention

Every database in the suite follows the same rules, so the apps read alike and can all share one database:

| What | Rule |
|---|---|
| Tables | `<prefix>_<plural noun>`, snake_case. Prefixes: `ios_` (this library), `prt_` (ioSuite start page), `nts_` (ioNote), `pix_` (ioPix), `cal_` (ioCalendar), `con_` (ioContact), `hlt_` (ioHealth), `dns_` (ioDNS) |
| Child tables | `<prefix>_<parent singular>_<children>`: `con_contact_emails`, `pix_album_photos` |
| Keys | `id` (a natural key the devices sync by keeps its name: `uuid`); references `<table singular>_id` |
| Accounts | `user_id` (the row belongs to an account), `owner_id` (NULL: shared with everyone), `created_by` / `decided_by` (who did it) |
| Times | `<event>_at`: `created_at`, `updated_at`, `last_seen_at`; dates without a time `date` / `<event>_date` |
| Booleans | a bare adjective or `has_<thing>` (`deleted`, `shared`, `has_image`), TINYINT NOT NULL DEFAULT 0 |
| Order | `position` |
| Key/value tables | columns `name`, `value` (never `key`, a reserved word) |
| Per app | `<prefix>_settings (name, value, updated_at)` and `<prefix>_schema_version (version, applied_at)` |
| Indexes | `idx_<table>_<what>`, unique `uq_<table>_<what>` |
| Tables | InnoDB, utf8mb4, utf8mb4_unicode_ci |

Names a standard already gives are kept where a column holds that standard's field: iCalendar (`dtstart`, `rrule`),
vCard (`fn`), HealthKit (`start_date`), digiKam (ioPix's copy of the library).

`iosuite_shared.schema` has what the apps need for it: `tables` / `columns` / `indexes` say what a database has, and
`ensure_version_table` / `current_version` / `record_version` keep `<prefix>_schema_version`.

## App password scopes

Every app password has a **scope** (`ios_app_passwords.scope`): `''` (the default) reaches everything the account may;
`'dav'` reaches the app's sync protocols only, so a password lifted from a phone cannot open the REST API, MCP or the
web app. `Auth.scope_paths` says which path prefixes each scope may reach (by default `dav`: `/dav`,
`/.well-known/caldav`, `/.well-known/carddav`); the middleware answers 403 anywhere else. An app without DAV sets
`auth.scope_paths = {}`. A server outside FastAPI (ioContact's LDAP) calls `apppasswords.authenticate_scoped(name,
password, app)`, which returns `(user, scope)`, and checks the scope itself.

- `apppasswords.create(user_id, app, label, scope="")`, `list_for(...)` items carry `scope`
- `POST /api/auth/app-passwords {label, scope}`; `GET` lists them with `scope`, and `scopes` (what the app offers)
- `apppasswords.set_scope(app, prefix, scope)`: for an app moving a record of its own into the column

`'read'` (`apppasswords.READ`) may only read: GET and HEAD, in every app the same, anywhere but `/mcp`, `/dav` and
`/.well-known/` (no writes, no MCP, no sync). It is what the apps' own service accounts get (see App links below).

## Apple profiles

`iosuite_shared.appleprofile` builds the configuration profiles (`.mobileconfig`) that add an app's sync account to an
iPhone, iPad or Mac. `PROFILE_APPS` names the apps that sync (ioCalendar and ioTask over CalDAV, ioContact over
CardDAV); an app's own profile is made of `account(app, name, base, user, secret)` payloads and `build(...)`.

`app.include_router(auth.profile_router(base_url))` adds the downloads: `GET /profile/<token>/<file>` (short-lived
links made with `appleprofile.link(body, name)`, for a download that carries no cookie) and the **suite profile**,
one file with the account of every app in `PROFILE_APPS` that is in the suite's list and that the account may use:

- `GET /api/apple-profile/suite`: `{apps: [{app, name}]}`; the pages offer it when there are two or more
- `POST /api/apple-profile/suite` (form) and `POST /api/apple-profile/suite/link` (`{label, password}` → `{url}`)

An app password belongs to one app, so the suite profile holds one new `dav` password per app (`password: "new"`),
or none and the device asks for each (`"ask"`). The other apps' addresses come from the suite's list of apps.

## Keys and tokens

Every credential an app keeps for something outside the suite (the start page's Home Assistant token and AccuWeather
key, ioPix's Google Maps keys) lives in `ios_credentials`, one row per key the app declares, so Settings › Global settings ›
Keys and tokens shows and changes them all. Values never leave the server: the panel says whether one is set.

```python
from iosuite_shared import credentials
credentials.declare("iosuite", [{"name": "ha_token", "label": "Home Assistant token", "hint": "...", "env": "HA_TOKEN"}])  # at start
token = os.environ.get("HA_TOKEN") or credentials.get("iosuite", "ha_token")
credentials.put("iosuite", "ha_token", value, by=user["name"])  # '' clears it
```

An `env` variable that is set still wins inside the app; the panel shows that (`envSet`).

## App links

One app reading from another needs no setup (`iosuite_shared.links`): the other app is found in the suite's list
(called on localhost when it runs on the same machine, then at its internal address when it recorded one, then at
its `PUBLIC_URL`, each tried when the one before does not answer; never at the address it was merely reached at,
since the call carries credentials, so an app in a container needs `INTERNAL_URL` or `PUBLIC_URL` to be read from;
`links.url()` is the public one, for links people click), and the reader signs in as its own **service account**
(`users.service_account(app)`: `<app>-app`, on no sign-in screen, no password anyone knows, viewer in the other app)
with an app password of the other app with scope `read`. Both are made on first use; the password is kept in
`ios_credentials` (hidden from the keys list), and made again when the other app answers 401. The suite looks after
them itself: the Security panel and `/api/suite-admin` neither list nor change service accounts or their app passwords.

```python
from iosuite_shared import links
if links.available("iocontact"):
    data = links.json("iocalendar", "iocontact", "/api/contacts?q=ann")   # or links.get(...): the urllib response
links.url("iocontact")                                                    # for links people click
```

Behind Cloudflare Access, the whole suite's keys `cf_access_client_id` / `cf_access_client_secret` (a Cloudflare
Access service token, set on Settings › Global settings › Keys and tokens) go with every request. Service accounts are not in
`users.list_users()` (pass `services=True`), do not count for the first-run setup, and cannot sign in with a password.

**On a person's behalf.** A page that shows something of another app to the person looking (the start page's tiles,
the calendar's tasks, a recipe's shopping list, the linked items, what a person keeps in each app) asks with that
person's own sign-in instead, passed on as it came (the suite's session cookie, else the `Authorization` header), so
the other app answers with what they may see there and no app password is involved:

```python
tasks = links.as_viewer(request, "iotask", "/api/tasks", {"status": "open"}, user_agent="ioCalendar")   # its JSON
body, ctype = links.as_viewer(request, "iopix", "/thumb/5", raw=True, patient=True)                      # a picture
```

The addresses are asked in the same order, the one that answered last first. An answer that is not a 2xx is urllib's
`HTTPError` as the app gave it; `links.Unreachable` when it answered nowhere, and the app is then left alone for
`links.BREAK_S` seconds (`links.resting(app)` says so; `patient=True` for a request that should not count). This is
the one place such requests are made: an app does not build them itself.

Every request to another app, either way, goes out through `links.call()`: a redirect is followed on the host that
was asked and nowhere else, because urllib would carry the cookie, the app password and the Cloudflare Access secret
along to wherever it points (the sign-in page of a proxy in front of the app, say).

## Edge check of app passwords (Cloudflare Worker, optional)

Behind Cloudflare, a Worker on `/dav*` can turn a wrong app password away before it reaches the server. The apps keep
a Workers KV namespace up to date with a SHA-256 of each app password (never an account password), when it is made,
on its first use after each start, and when it or its account is deleted. It is off unless all three are set. They
are the whole suite's keys in the Shared ioSuite database (Settings › Global settings › Keys and tokens), so every app picks
them up within seconds, without a restart; a variable in an app's config.env wins:

```
iosuite-shared edge --account-id … --namespace-id … --token-file token.txt   # token: Account › Workers KV Storage › Edit
CF_KV_ACCOUNT_ID=…  CF_KV_NAMESPACE_ID=…  CF_KV_API_TOKEN=…                  # or per app, in config.env
```

The Worker, its `wrangler.toml`, the rollout (monitor, then enforce) and a WAF rate-limit rule are in
[cloudflare/edge-auth/](cloudflare/edge-auth/README.md).

## Command line

```
iosuite-shared init                          # the tables
iosuite-shared check                         # reach the database, count the accounts
ADMIN_PASSWORD=… iosuite-shared admin alex --app iocalendar   # an admin of the app (made when missing; the first account is a suite admin)
iosuite-shared --config /opt/iocalendar/app check             # the app's config.env first (what setup.sh does)
iosuite-shared list
iosuite-shared create alex --email a@b.c --suite-admin
iosuite-shared role alex ionote editor
iosuite-shared password alex
iosuite-shared edge [--apply]                # the edge check's KV namespace vs the app passwords (below)
```

### Several apps in one machine or container: `install`

```
ADMIN_PASSWORD=… iosuite-shared --config /opt/iosuite/app install iocalendar iocontact --admin alex --service --from iosuite
iosuite-shared --config /opt/iopix/app install all --no-service
```

Every app's `setup.sh` ends with the list of the suite's apps on the machine (`apps`, below), and takes `--also
iopix,ionote` (`--also all`; the `IO<APP>_ALSO` environment variable in the Proxmox installers). What is ticked or named comes here, so the questions every app
shares are asked once: `install` reads the calling app's config.env and hands each companion the same **app database
server** (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`; each app gets its own database name, `calendar`, `contacts`,
`notes`, `health`, `iopix`, `suite`, created when the user may, so the user needs rights on those names too), the same
**Shared ioSuite database** (`IOSUITE_DB_*`), the same sign-in domain (`COOKIE_DOMAIN`) and, with `--admin`, the same
admin account. Each companion is fetched from GitHub into `<base>/<app>/app` (`/opt/iocalendar/app` beside
`/opt/iosuite/app`, with its commit in `COMMIT`, the layout the Proxmox installers make), and its own `setup.sh --yes`
installs the packages, writes config.env, creates the tables and the systemd service. The passwords travel in the
environment (`IOCALENDAR_DB`, `IOCALENDAR_SUITE_DB`, `IOCALENDAR_ADMIN`, ...), never on a command line. What differs
per app keeps its default: the usual port, no public address, the machine's time zone; ioPix gets `--no-digikam`,
`--features none` and the photos folder of `--photos` (default `/library/photos`). An app already set up in its folder
is left alone. Afterwards each app updates itself as always (its `update.sh`, or Settings › Server in the web app).

### The same machine, later: `apps`, `remove`, reconfigure

```sh
iosuite-shared --config /opt/iostart/app apps                      # the list: tick, untick, r<number> to reconfigure
iosuite-shared --config /opt/iostart/app apps --list
iosuite-shared --config /opt/iostart/app apps --add iotask --remove iohealth --reconfigure iocalendar
iosuite-shared --config /opt/iostart/app apps --reach one          # how every app is reached: ports | one | one-proxy | proxy [--address URL]
iosuite-shared --config /opt/iostart/app remove iohealth [--delete-data] [--db-admin root]
```

`apps` is what `./setup.sh --apps`, the end of every `setup.sh` and the repository's `install.sh`
(`curl -fsSL …/install.sh | bash`, which also does the first install) run. An app is on the machine when
`<base>/<app>/app/config.env` exists.

**Removing** stops the app's service and deletes the unit (only when it points at that folder; the login item on a
Mac), deletes the program files (code, Python environment, config.env) and takes the app out of `ios_apps` and
`ios_updates`, so no switcher shows it and no app calls it. It keeps the app's database, its data folder, the
accounts' roles in the app, its keys and app passwords: adding the app again finds everything. `--delete-data`
(a separate question in the list, answered by typing `DELETE`) also drops the app's own database (as the app's user, or
as `--db-admin`) and deletes `<base>/<app>`. It never drops the Shared ioSuite database or a database another app on
the machine uses, never deletes a data folder outside `<base>/<app>`, the photos (`PHOTOS_ROOT`) or the backups
(`BACKUP_DIR`). The app the command runs from is removed by another app that stays; the last app is not removed.

**Reconfiguring** runs the app's own `setup.sh --also none` in its folder with the person at the keyboard: every
question again with the current answer as the default. Without questions, give that `setup.sh` the flags:
`sh /opt/iotask/app/setup.sh --yes --port 8700`.

### A MariaDB administrator makes the databases and users: `provision`

```
DB_ADMIN_PASSWORD=… iosuite-shared --config /opt/iosuite/app provision --admin root [--also iocalendar,ionote] [--dry-run]
DB_ADMIN_PASSWORD=… iosuite-shared --config /opt/iosuite/app install iocalendar --db-admin root ...
```

Every app's `setup.sh` asks, right after the database questions, for a MariaDB / MySQL administrator (flag
`--db-admin USER:PASSWORD`, or `IO<APP>_DB_ADMIN`; empty: the databases and users exist already). With one, `provision`
creates what config.env names: the app's own database and user (`DB_*`), the Shared ioSuite database and user
(`IOSUITE_DB_*`) and, with `--also`, the companions' databases for the same app user. Nothing is dropped: databases and
users are created when missing, the users' passwords are set to the ones answered, and each user gets all privileges
on its own databases only; users are made for `'%'` (and `'localhost'` when the server is this machine). The
administrator's password travels in `DB_ADMIN_PASSWORD`, never on a command line, and is not written anywhere.

## Tests

`pytest tests/test_updates.py` runs without a database. The rest of `pytest` needs a MariaDB of its own: a Docker container it starts itself (`iosuite-test-mariadb`, kept for the next
run), or the server named by `IOSUITE_TEST_DB=host:port:user:password` (a user that may create and drop databases).
It uses a database `iosuite_shared_test` there, dropped and made again per test, and never a live Shared ioSuite database;
without a test server it is skipped. The apps' suites use the same helper (`iosuite_shared.testing`).

## License

GPL-3.0-or-later (the GNU General Public License, version 3 or later), see [LICENSE](LICENSE).
