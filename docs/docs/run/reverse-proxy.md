---
description: HTTPS for the ioThing apps behind Caddy, nginx, HAProxy or Traefik, and one sign-in across them.
---

# Reverse proxy and HTTPS

Every app speaks plain HTTP on its port. To reach it from outside your network, put a reverse proxy in front that
terminates HTTPS: Caddy, nginx (or Nginx Proxy Manager), HAProxy, Traefik, or a [Cloudflare Tunnel](cloudflare.md).
Phones want HTTPS for CalDAV and CardDAV accounts away from home, and the browser wants it to install the web app.

## A name per app

Give each app a host name under one domain, for example:

| App | Address | Upstream |
| --- | --- | --- |
| ioPix | `photos.example.com` | `192.168.1.10:8600` |
| ioNote | `notes.example.com` | `192.168.1.10:8610` |
| ioCalendar | `calendar.example.com` | `192.168.1.10:8620` |
| ioStart | `home.example.com` | `192.168.1.10:8630` |
| ioContact | `contacts.example.com` | `192.168.1.10:8640` |
| ioHealth | `health.example.com` | `192.168.1.10:8650` |
| ioTask | `tasks.example.com` | `192.168.1.10:8670` |
| ioRecipe | `recipes.example.com` | `192.168.1.10:8690` |

and set in each app's `config.env`:

```sh
PUBLIC_URL=https://calendar.example.com   # the address people and the other apps reach it at
COOKIE_DOMAIN=example.com                 # one sign-in for every app under example.com
```

With `COOKIE_DOMAIN`, someone signed in at `photos.example.com` is signed in at `calendar.example.com` too. Without it,
each app keeps its own sign-in (still with the same accounts). `PUBLIC_URL` is the address the app lists in the suite's
list of apps, so the start page and the other apps link to the right place; unset, the app keeps the best address it
has been reached at.

## Or one name, an app per folder

The apps can also share one address, each in a folder of it: `https://home.example.com/calendar/`,
`https://home.example.com/notes/` and so on, with one certificate, one DNS name and one port. Each app still runs on
its own port; the proxy picks the app by the first part of the path. Put the folder in each app's `PUBLIC_URL`:

```sh
PUBLIC_URL=https://home.example.com/calendar   # ioCalendar's config.env; no COOKIE_DOMAIN needed, it is one host
```

The app then writes that folder into everything it hands out (the CalDAV and CardDAV links, the addresses under
Settings, the links in notifications), and the proxy may either take the folder off the path or leave it on: both
work. In Caddy:

```caddy
home.example.com {
    redir /calendar /calendar/
    handle_path /calendar/* {
        reverse_proxy 192.168.1.10:8620
    }
    redir /notes /notes/
    handle_path /notes/* {
        reverse_proxy 192.168.1.10:8610
    }
    # ... one pair per app
}
```

and in nginx, with the same `proxy_set_header` lines as [below](#nginx) in each (the app knows its folder by the
`Host` it is asked for; no trailing slash after the port, so the folder stays on the path):

```nginx
location = /calendar { return 308 /calendar/; }
location /calendar/  { proxy_pass http://192.168.1.10:8620; proxy_set_header Host $host; }
location = /notes    { return 308 /notes/; }
location /notes/     { proxy_pass http://192.168.1.10:8610; proxy_set_header Host $host; }
```

A proxy that cannot be told the public address can send `X-Forwarded-Prefix: /calendar` instead (Traefik's
StripPrefix does it by itself); it is believed from the proxies listed under Settings › Security. Reached straight on
its own port (`http://192.168.1.10:8620`), an app answers at the root as before.

Two things differ from a name per app. Phones find a CalDAV or CardDAV account by asking the host for
`/.well-known/caldav`, which belongs to the whole host: send it to the app that should answer
(`redir /.well-known/caldav /calendar/dav/ 301`), and give the others their full address
(`https://home.example.com/tasks/dav/`). And devices set up with the old addresses need the new one once.

## Tell the apps where the proxy is

A reverse proxy on another machine connects from a private address, like any visitor in your home. The apps have to
know which address is the proxy to tell someone at home from someone on the internet. Until they do, **everyone who
comes through the proxy counts as outside your network**, which is the safe side: from outside, the first account
cannot be made, an install without accounts shows nothing but its sign-in screen, and an account without a password
gets no one-click sign-in.

Set it once for the whole suite, as a suite admin, in any app: **Settings › Security › Sign-in at the proxy ›
Reverse proxy addresses**. Enter the address the proxy connects from (`192.168.1.2`), several of them, or a network
(`172.18.0.0/16` for a Docker network). Leave *Proxy* at Off unless the proxy also signs people in
([below](#sign-in-at-the-proxy)).

- The proxy must send `X-Forwarded-For`: Caddy, Traefik and Nginx Proxy Manager do by themselves, nginx with the
  `proxy_set_header` line below, HAProxy with `option forwardfor`. The app reads the visitor's address from it: a
  private address is at home, a public one is outside.
- A proxy on the same machine as the apps (`127.0.0.1`) is known already; nothing to set.
- A [Cloudflare Tunnel](cloudflare.md) needs nothing here: what comes through Cloudflare is always outside.
- On a new install, make the first account before any of this, at the server's own address
  (`http://192.168.1.10:8620`) and not through the proxy: see [First run](../start/first-run.md).

## Caddy

Caddy gets a certificate by itself:

```
calendar.example.com {
    reverse_proxy 192.168.1.10:8620
}
health.example.com {
    reverse_proxy 192.168.1.10:8650
}
```

## nginx

```nginx
server {
    listen 443 ssl;
    server_name calendar.example.com;
    # ssl_certificate / ssl_certificate_key ...
    client_max_body_size 100m;
    location / {
        proxy_pass http://192.168.1.10:8620;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    location /mcp {
        proxy_pass http://192.168.1.10:8620;
        proxy_buffering off;              # MCP streams its answers
        proxy_read_timeout 1h;
    }
}
```

## Things to know on any proxy

- **`/mcp` streams** (server-sent events): the proxy must not buffer that path.
- **`X-Forwarded-For` and `X-Forwarded-Proto`** tell the app the visitor's address and that the request came over
  HTTPS (which marks the session cookie Secure). The apps believe them from the proxies they were told about, the
  reverse proxy addresses [above](#tell-the-apps-where-the-proxy-is), and from a proxy on the same machine; from
  anyone else they are ignored. That one list decides both what the app shows and logs as the visitor's address and
  whether a visitor counts as inside your network.
- **ioHealth** takes the phone's uploads on the same port; batches are compressed and normally well under 1 MB.
- **ioContact's LDAP** is not HTTP: keep it on the home network, or put a TLS proxy (stunnel, HAProxy, nginx stream)
  in front for `ldaps://`.
- An app can serve HTTPS itself instead: `TLS_CERT_FILE` and `TLS_KEY_FILE`.

## Sign-in at the proxy

When the proxy already makes people sign in (Cloudflare Access, Authelia, Authentik, oauth2-proxy...), the apps can take
that sign-in instead of asking again: the proxy names the person in a header, and the app signs in the account with
that email (or name). It is one setting for the whole suite, under **Settings › Security › Sign-in at the proxy** in
any app:

| Setting | |
| --- | --- |
| Proxy | `cloudflare`, `haproxy`, `nginx`, `caddy`, `traefik` or `header` |
| Header | the header with the user (`Remote-User`, `X-Forwarded-User`, `X-Auth-Request-Email`...; for Cloudflare `Cf-Access-Authenticated-User-Email`) |
| Reverse proxy addresses | the addresses the proxy connects from ([above](#tell-the-apps-where-the-proxy-is)): the header is believed from there only, and a proxy that names the user in a header cannot be saved without them |
| New people | `viewer` or `editor` to make an account for someone the proxy lets in, `deny` for a "No access" page |
| Cloudflare team and AUD | for Cloudflare Access: the signed token is checked against your team's keys |

The header must not be fakeable: the proxy must replace it on every request, and the app must be reachable only
through the proxy. The apps' own sign-in keeps working beside it, for anyone the proxy doesn't vouch for.
