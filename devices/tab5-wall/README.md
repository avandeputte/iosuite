# The wall on an M5Stack Tab5

Firmware that puts the start page's wall (`#/wall`) on an [M5Stack Tab5](https://docs.m5stack.com/en/core/Tab5)
(ESP32-P4, 5-inch 1280 × 720 touch screen), on USB power and always on.

- **The wall:** clock and date, the weather now with the coming hours and days and a rain note, today's events
  with their places ("6:00 PM Dinner @ Nan Xiang Dumpling") and the week's (swipe between them), birthdays,
  today's tasks, Home Assistant tiles, and ioPix photos behind it all (or a sky, or black: the start page's wall
  setting).
- **Touch:** tap an event for its details, tick a task done, tap a Home Assistant tile to switch it, tap the
  background for the next photo, hold it to make the photo a favorite in ioPix. Add a task or an event with the
  on-screen keyboard.
- **Timers and an alarm clock** on the Tab5's speaker (four of each; alarms by weekday or once, snooze).
- **Night:** dims from 22:00 to 06:00 by default (or turns the screen off); a touch lights it for 30 seconds.
  Hours and brightness are in Settings on the device.
- **Updates itself** at 3 AM from the release `wall-latest` (Settings turns that off). A firmware that does not
  run for a minute is rolled back.

## Install it

From Chrome or Edge on a computer: **[iosuite.iothing.net/wall/](https://iosuite.iothing.net/wall/)**.

1. Connect the Tab5 with a USB-C cable that carries data.
2. Hold the reset button about two seconds, until the green light inside blinks fast (download mode).
3. Press Install, pick the port, wait about a minute, then press reset once.
4. On the Tab5: pick the Wi-Fi, type the start page's address (`192.168.1.20:8600`, or `https://start.example.com`
   when no sign-in page such as Cloudflare Access stands in front of it), then let it in. Scan the QR code with
   your phone, or open the start page at `#/pair` and type the code. Or sign in on the Tab5 with your name and
   password. The Tab5 gets an app password of yours ("Wall display (Tab5)", in Settings › Account), so it sees what
   you see. Remove that password and the Tab5 goes back to setting up.

Without a browser that writes to USB: `esptool.py --chip esp32p4 write_flash 0x0 iowall-full.bin` with the file
from the [release](https://github.com/avandeputte/iosuite/releases/tag/wall-latest).

## Build it

ESP-IDF 5.4 (`.github/workflows/tab5-wall.yml` builds it with 5.4.2):

```sh
cd devices/tab5-wall
idf.py set-target esp32p4
idf.py build flash monitor
```

The components come from Espressif's registry (`main/idf_component.yml`): the Tab5's board package, LVGL 9.3, and
ESP-Hosted 1.4 with esp_wifi_remote for the Wi-Fi on the Tab5's ESP32-C6. A build made by hand is version `dev` and
never updates itself; `WALL_VERSION=1.2 idf.py build` gives it a version.

| File | What |
|---|---|
| `main/main.c` | starts everything |
| `main/settings.c` | what is kept across restarts (NVS) |
| `main/net.c` | Wi-Fi, the clock (SNTP) |
| `main/api.c` | HTTP to the start page with the device's app password |
| `main/feed.c` | `/api/wall/feed` every minute, the photos (`/api/wall/photo/<id>.jpg`, the P4's JPEG decoder), taps |
| `main/ui.c`, `ui_wall.c`, `ui_setup.c`, `ui_panels.c` | the screens (LVGL) |
| `main/alarm.c` | timers, alarms, the sound |
| `main/ota.c` | updates from the release `wall-latest` |
| `main/icons.c` | the weather icons, made by `tools/make_icons.py` |
| `main/fonts/` | Inter (SIL Open Font License, `OFL.txt`) |

The server side is in the start page: `iostart/app/wall.py`.
