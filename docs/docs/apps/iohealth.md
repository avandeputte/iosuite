---
description: ioHealth, Apple Health data on your own server, with the ioHealthSync iPhone app.
---

# ioHealth <small>health</small>

Copies your Apple Health data, all of it or just the types you pick, into your own MariaDB database, and gives you a
fitness web app on top of it. Nothing goes through a cloud service: the **ioHealthSync** iPhone app uploads straight to
your server.

![The ioHealth dashboard: activity rings, last night's sleep and the trend of every metric](../img/iohealth.jpg)

## What it does

- **Dashboard**: today's rings and the last week's, last night's sleep, every metric against your usual, recent
  workouts, and a heads-up list (resting heart rate up, HRV down, glucose lows, goal streaks).
- **Metrics**: chart any synced type over any range, zoom and pan, stack or overlay several, compare with a year
  earlier, goal lines.
- **Workouts** with their GPS routes on a map, splits, heart rate zones, training load; **Sleep** stages per night;
  **Glucose** from a CGM or meter; **Correlations** between any two metrics; **Records**.
- **Per person**: everyone in the household syncs into their own account and sees only their own data.
- CSV export of any chart, PDF of any page, and a JSON API with app passwords for scripts.

![ioHealth's sleep page](../img/iohealth-sleep.jpg)

## On its own

ioHealth is a complete fitness web app. It needs its database, the Shared ioSuite database, and the ioHealthSync app
on each iPhone. Health data only exists on the iPhone, so the app is iPhone only. The phone allows plain `http://` only
to addresses on your own network; anything else must be HTTPS.

## With the other apps

- **ioSuite**: today's steps with the last seven days as bars, the move, exercise and stand rings, and last night's
  sleep on the ioHealth tile.
- The same accounts as every other app: each person signs in to ioHealthSync with their suite account.

## Install

| | |
| --- | --- |
| Proxmox VE | `bash -c "$(curl -fsSL https://raw.githubusercontent.com/avandeputte/iohealth/main/proxmox/ct/iohealth.sh)"` |
| Docker | [docker-compose.yml](https://github.com/avandeputte/iohealth/blob/main/docker-compose.yml): the image `ghcr.io/avandeputte/iohealth` |
| Any Linux or Mac | `git clone https://github.com/avandeputte/iohealth && cd iohealth && ./setup.sh` |
| Port | 8650 (the web app and the phone's uploads) |
| Source | [iohealth](https://github.com/avandeputte/iohealth) (server), [iohealth-apps](https://github.com/avandeputte/iohealth-apps) (the ioHealthSync iPhone app) |

The iPhone app is built from [iohealth-apps](https://github.com/avandeputte/iohealth-apps) with Xcode. See
[Phones, Macs and other apps](devices.md).
