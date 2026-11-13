---
description: Connect phones, Macs, calendar, reminders and contacts apps to the ioThing apps.
---

# Phones, Macs and other apps

## Every app, in the browser

Every web app has a phone layout and installs like an app: in Safari on the iPhone, Share › Add to Home Screen; in
Chrome on Android, the menu › Install app. Light, dark or the device's theme, kept with your account. Installing needs
HTTPS (or `localhost`).

## Native apps

| App | Device | What it does | Source |
| --- | --- | --- | --- |
| **ionote** | Mac, iPhone, iPad | the clipboard Inbox and screenshots on the Mac, notes everywhere, synced with the ioNote server and usable offline | [ionote-apps](https://github.com/avandeputte/ionote-apps) |
| **ioHealthSync** | iPhone | copies Apple Health data to the ioHealth server: everything or the types you pick, incremental, in the background | [iohealth-apps](https://github.com/avandeputte/iohealth-apps) |

Both are built from source with Xcode and XcodeGen (`brew install xcodegen`, then `xcodegen generate`); each
repository's README has the steps. They sign in with your suite account. Behind Cloudflare Access, ionote takes a
Cloudflare Access service token; ioHealthSync's uploads (`/v1/`) need a bypass rule or a service token (see
[Cloudflare](../run/cloudflare.md)).

## Calendars, tasks and contacts on every device

ioCalendar, ioTask and ioContact speak the standards phones and desktop apps already use. Settings › Apps and devices in each
app shows the exact addresses to type.

| On | ioCalendar | ioTask | ioContact |
| --- | --- | --- | --- |
| iPhone, iPad, Mac | CalDAV, or the **configuration profile** from Settings › Apps and devices (one tap, with a device-only app password inside) | Apple Reminders over CalDAV, or its configuration profile | CardDAV, or its configuration profile |
| Android | CalDAV with DAVx⁵ | CalDAV with DAVx⁵ and Tasks.org or jtx Board | CardDAV with DAVx⁵ |
| Thunderbird, Evolution, GNOME, KDE | CalDAV | CalDAV (to-dos) | CardDAV, LDAP |
| Google Calendar, Outlook | a private `webcal://` subscription link (read-only) | | vCard export |
| Mail apps, desk phones, printers | | | the LDAP directory (read-only) |

Sign these in with your user name and an **app password** (Settings › Account › App passwords), one per device, so
losing a phone means revoking one password. An app password can be limited to the sync protocols only; the ones in the
Apple profiles always are. Away from home, phones need HTTPS: see [Reverse proxy and HTTPS](../run/reverse-proxy.md).
