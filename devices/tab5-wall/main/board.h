/* The board this firmware is built for (WALL_BOARD, see ../CMakeLists.txt): what differs between them. Both are an
 * ESP32-P4 with its Wi-Fi on an ESP32-C6, a MIPI-DSI touch screen and a speaker, and both come with a board package
 * that offers the same calls (bsp/esp-bsp.h): the screen through esp_lvgl_port, the speaker through esp_codec_dev.
 *
 *   tab5         M5Stack Tab5: 5 inch, 1280 × 720 (a 720 × 1280 panel on its side), ES8388, the C6 behind a power switch
 *   waveshare7b  Waveshare ESP32-P4-WIFI6-Touch-LCD-7B: 7 inch, 1024 × 600 (EK79007, GT911 touch), ES8311
 */
#pragma once

#if defined(WALL_BOARD_WAVESHARE7B)

#define BOARD_NAME "Waveshare 7B"
#define BOARD_W 1024
#define BOARD_H 600
/* the panel is landscape as it is; the other way round is half a turn */
#define BOARD_ROTATION(flip) ((flip) ? LV_DISPLAY_ROTATION_180 : LV_DISPLAY_ROTATION_0)
/* the C6 is powered with the board */
#define BOARD_WIFI_ON() ((void)0)
/* a battery can be connected, but nothing on the board measures it */
#define BOARD_BATTERY 0

#else

#define BOARD_NAME "Tab5"
#define BOARD_W 1280
#define BOARD_H 720
/* a portrait panel turned on its side */
#define BOARD_ROTATION(flip) ((flip) ? LV_DISPLAY_ROTATION_270 : LV_DISPLAY_ROTATION_90)
/* the C6 has its own power switch on the Tab5's I/O expander */
#define BOARD_WIFI_ON() bsp_feature_enable(BSP_FEATURE_WIFI, true)
/* a power monitor on the battery's line (power.c) */
#define BOARD_BATTERY 1

#endif

/* the app's file in the release wall-latest, which a device updates itself from (ota.c): each board, and each
 * chip revision that needs a build of its own, has one */
#ifndef WALL_OTA_FILE
#define WALL_OTA_FILE "iowall.bin"
#endif
