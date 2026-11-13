---
description: ioDNS, the admin tool of the ioThing suite that keeps the house's DNS names in sync on every DNS server.
---

# ioDNS <small>admin tool: DNS</small>

One master list of the house's DNS names, kept in sync on every DNS server: AdGuard Home, Pi-hole, a UniFi gateway,
Cloudflare. Add a name once, see where the servers disagree, pick who is right, push.

!!! note "An admin tool"
    ioDNS is a utility for the person who runs the servers, not an app for the family. Only suite admins can open it;
    they find it on the start page and in the app switcher. Nobody else sees it, and it takes no roles.

## What it does

- **A master list**: a row per name (`calendar.example.com`) with a note and its records (A, AAAA, CNAME, or a
  Cloudflare Tunnel hostname).
- **Views (split-horizon DNS)**: Internal (the house), External (the internet) and Tailscale (the tailnet) to begin
  with, and more of your own. One name can be `192.168.1.151` at home, a tunnel outside and `100.x` on the tailnet,
  all on one row. A name without an External record never reaches public DNS.
- **Compare**: every server is read and compared with the master list, name by name: in sync, missing, different, or
  only on a server. A server that can't be reached is shown as such and doesn't stop the rest.
- **Resolve and push**: per name, use the master list, use one server's records, delete everywhere or leave it. A
  preview lists every change before anything is done. **Push all** makes every server of a view hold the master list.
- **Push right away**: after you add, change or delete a name, ioDNS shows what that changes on the servers and asks
  whether to push it now.
- **Import** from any server, and export or import the whole list as JSON.
- **Dynamic DNS**: a record can be "Public address". ioDNS finds the house's public address every few minutes and
  updates and pushes those records when it changes.
- **Cloudflare Tunnel**: a name in the External view can be a tunnel's public hostname. ioDNS keeps the tunnel's
  ingress rule and its proxied CNAME together, as the Cloudflare dashboard does.
- **Tailscale**: a record can be "Tailscale device" and follows that device's tailnet address; split DNS for the
  tailnet is set up from the same place.
- **History** of every change, push, import and dynamic DNS update, and by whom.
- **A background check** every 30 minutes, so the sidebar shows which views have differences.

## DNS servers

| Kind | What ioDNS keeps there | How it signs in |
| --- | --- | --- |
| AdGuard Home | Filters › DNS rewrites | the web interface's user and password |
| Pi-hole v6 | Local DNS records and CNAME records | an app password (Pi-hole 5 has no API for this) |
| UniFi gateway | the gateway's DNS records | an API key (Network 9.3 and later), or a local admin account |
| Cloudflare DNS | the zones' A, AAAA and CNAME records | an API token with Zone › DNS › Edit |
| Cloudflare Tunnel | the public hostnames of remotely managed tunnels | an API token with Account › Cloudflare Tunnel › Edit and Zone › DNS › Edit |
| Tailscale | nothing is pushed: device addresses and split DNS | an API access token or an OAuth client secret |

The servers' passwords and API keys are kept with the suite's keys and tokens in the Shared ioSuite database, and are
never shown back. Every server also has **Names to leave out**: names it is never compared on or sent.

## On its own

ioDNS works without any other app of the suite. It needs its database and the Shared ioSuite database, where its
admin account lives.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iosuite/main/iodns/proxmox/ct/iodns.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iosuite/blob/main/iodns/docker-compose.yml): the image `ghcr.io/avandeputte/iosuite/iodns` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iosuite && cd iosuite/iodns && ./setup.sh` |
| Port | 8660 |
| Source | [iosuite/iodns](https://github.com/avandeputte/iosuite/tree/main/iodns) |

The [README](https://github.com/avandeputte/iosuite/tree/main/iodns) has the details of each kind of server.
