---
description: Run the ioThing apps behind a Cloudflare Tunnel and Cloudflare Access.
---

# Cloudflare Tunnel and Access

A [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) publishes the apps
without opening a port on your router, and [Cloudflare Access](https://developers.cloudflare.com/cloudflare-one/policies/access/)
makes people sign in at Cloudflare before a request reaches them. The apps work with both, and the Access setup is
done once for the whole suite.

## The tunnel

In Cloudflare Zero Trust › Networks › Tunnels, create a tunnel, run `cloudflared` on a machine in your network, and add
a public hostname per app pointing at its address and port (`calendar.example.com` → `http://192.168.1.10:8620`, and so
on; see the table in [Reverse proxy and HTTPS](reverse-proxy.md#a-name-per-app)). Set `PUBLIC_URL` and `COOKIE_DOMAIN`
in each app as described there.

## Access: one application for every app

1. In Zero Trust › Access › Applications, add a **self-hosted** application for `*.example.com` (or one per host) with
   a policy that lets your family in.
2. Copy the application's **AUD tag** (Overview › Application Audience tag).
3. In any app, as a suite admin: **Settings › Security › Sign-in at the proxy** › Cloudflare Access, with your team
   (`myteam.cloudflareaccess.com`) and the AUD tag. Several AUD tags, comma-separated, if you made an application
   per host.

That setting is kept in the Shared ioSuite database, so every app picks it up. Each app checks the signed token
Cloudflare adds to every request (`Cf-Access-Jwt-Assertion`) against your team's keys and signs in the account with that
email, then that name. Sign out also ends the Access session. Turn on **Sign-in required** (Settings › Global settings ›
Apps) as well, so nobody gets in without it. Requests through Cloudflare never get one-click sign-in for passwordless
accounts.

## Paths that must bypass Access

Phones and sync apps can't open the Access sign-in page. Add a policy with the action **Bypass** (Include: Everyone)
for these paths, or a second Access application covering only them. They stay protected by the apps' own sign-in:

| App | Path | Used by | Still protected by |
| --- | --- | --- | --- |
| ioCalendar | `/dav/*`, `/.well-known/caldav` | CalDAV clients and the Apple profile | user name and app password |
| ioCalendar | `/ics/*` | subscription links and free/busy | the private token in the link |
| ioTask | `/dav/*`, `/.well-known/caldav` | Apple Reminders, other CalDAV clients and the Apple profile | user name and app password |
| ioTask | `/profile/*` | the Apple profile's download link | the short-lived secret in the link |
| ioContact | `/dav/*`, `/.well-known/carddav` | CardDAV clients and the Apple profile | user name and app password |
| ioHealth | `/v1/*` | the ioHealthSync iPhone app (or give it a service token) | user name and password |
| ioPix, ioNote, ioCalendar, ioTask, ioRecipe, ioContact | `/mcp` | AI assistants, if MCP is on | an app password |

Everything else, the web apps and `/api/`, stays behind Access. A script calling `/api/` from outside needs a Cloudflare
**service token** (`CF-Access-Client-Id` and `CF-Access-Client-Secret`) allowed in the policy, as well as an app password.
The ionote Mac and iPhone apps take a service token in their settings. The ioStart start page asks the other apps for its
tiles with the suite's service token (Settings › Global settings › Keys and tokens) when they are only reachable through
Access.

## Optional: checking app passwords at the edge

Since `/dav*` bypasses Access, a small **Cloudflare Worker** can check the app password there and turn wrong ones away
before they reach your server. The apps keep a Workers KV namespace up to date with a SHA-256 of each app password
(never an account password). Store the three settings once under Settings › Global settings › Keys and tokens:

```sh
iosuite-shared edge --account-id … --namespace-id … --token-file token.txt
```

The Worker, its `wrangler.toml`, the rollout (monitor first, then enforce) and a WAF rate-limit rule are in
[iosuite-shared's cloudflare/edge-auth](https://github.com/avandeputte/iosuite/blob/main/shared/cloudflare/edge-auth/README.md).
Once it enforces, sync clients must use an app password, not the account password.
