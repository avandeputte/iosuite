/* The wall display for an M5Stack Tab5 or a Waveshare ESP32-P4-WIFI6-Touch-LCD-7B (board.h): what the parts share.
 *
 * main.c      starts everything
 * settings.c  what is kept across restarts (NVS): Wi-Fi, the start page's address and the device's app password,
 *             the clock, the night, alarms, volume
 * net.c       Wi-Fi through the ESP32-C6, the clock from the network (SNTP)
 * api.c       HTTP to the start page with the device's app password
 * feed.c      the start page's wall feed (/api/wall/feed) every minute, and its photos (/api/wall/photo/<id>.jpg),
 *             decoded by the P4's JPEG engine
 * ui*.c       the screens (LVGL): the wall, the views a swipe away from it, setting up, settings, the panels that
 *             open over the wall
 * alarm.c     timers and alarms, and the sound (the board's speaker)
 * ota.c       a newer firmware from GitHub, over the air
 * power.c     the battery's level, on a board that measures it
 * boot.c      what stopped the last start, shown on the screen
 *
 * LVGL is not thread-safe: every LVGL call outside its own callbacks happens between ui_lock() and ui_unlock().
 */
#pragma once

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <time.h>
#include "lvgl.h"

#include "board.h"

/* The screens are laid out for the Tab5's 1280 × 720; P() brings a size to this board's screen (the 7B's 1024 × 600:
 * four fifths). Fonts take their size the same way (font_text and the others). */
#define WALL_W BOARD_W
#define WALL_H BOARD_H
#define P(n) ((n) * WALL_W / 1280)

/* ------------------------------------------------------------------ settings.c */

#define ALARMS 4

typedef struct {
    uint8_t hour, minute;
    uint8_t days;   /* bit 0 Sunday … bit 6 Saturday; 0: once, the next time it comes */
    bool on;
    char label[24];
} wall_alarm_t;

typedef struct {
    uint32_t version;
    char ssid[33];
    char wifi_pass[65];
    char server[128];      /* "http://192.168.1.20:8600" */
    char token[160];       /* the device's ioStart app password */
    char user[64];         /* whose it is */
    char tz[64];           /* the time zone (IANA) asked of the start page; "" its own */
    char posix[64];        /* the last POSIX TZ string it gave, so the clock is right before the network is up */
    bool clock24;
    bool flip;             /* landscape the other way round (the USB-C port on the other side) */
    uint8_t night_from, night_to;  /* hours; the same: no night */
    uint8_t day_bright, night_bright; /* percent; night 0: the screen goes off */
    uint8_t volume;        /* percent */
    bool auto_update;
    uint16_t snooze_min;
    wall_alarm_t alarms[ALARMS];
} wall_settings_t;

extern wall_settings_t S;
void settings_load(void);
void settings_save(void);
void settings_forget_sign_in(void);
void settings_reset(void);
/** The views (ui_views.c) not swiped to, a bit each; kept beside the rest, so adding it did not ask for a new set-up. */
extern uint32_t VIEWS_OFF;
void settings_save_views(void);

/* ------------------------------------------------------------------ net.c */

typedef enum { NET_OFF, NET_CONNECTING, NET_UP, NET_FAILED } net_state_t;

typedef struct {
    char ssid[33];
    int8_t rssi;
    bool open;
} net_ap_t;

void net_init(void);
void net_connect(const char *ssid, const char *pass);
net_state_t net_state(void);
const char *net_ip(void);
const char *net_why(void);
/** Looks for networks; blocks a few seconds; returns how many it put in out. */
int net_scan(net_ap_t *out, int max);
bool clock_is_set(void);
void clock_set_zone(const char *posix);

/* ------------------------------------------------------------------ api.c */

typedef struct {
    int status;            /* HTTP status; < 0: no answer (see why) */
    char *body;            /* NUL-terminated, in PSRAM; free with api_free */
    size_t len;
    char why[96];
    char type[48];         /* its Content-Type */
} api_resp_t;

/** method "GET" / "POST"; body JSON or NULL; max: the most it reads (bytes). Uses S.server and S.token unless
 *  base is given (setting up: an address not saved yet). */
api_resp_t api_request(const char *method, const char *path, const char *body, size_t max, const char *base);
/** The same with an Authorization header of its own ("Basic …": signing in with a name and a password). */
api_resp_t api_request_auth(const char *method, const char *path, const char *body, size_t max, const char *base,
                            const char *authorization);
void api_free(api_resp_t *r);
/** The address as typed ("192.168.1.20:8600", "start.example.com") made a URL; false when it cannot be one. */
bool api_normalize(const char *in, char *out, size_t n);

/* ------------------------------------------------------------------ feed.c */

typedef struct {
    char title[96];
    char place[64];
    char location[160];
    bool all_day;
    time_t s, e;
    char day[11], end_day[11];
    uint32_t color;
    bool has_color;
    /* what a tap on it adds, where ioCalendar has any */
    struct {
        char name[32];
        uint32_t color;
        bool has_color;
    } who[6];              /* the family members it is for */
    int nwho;
    char people[160];      /* the other people on it, "A, B" */
    char calendar[48];
    char notes[400];
    bool recurring;
} wall_event_t;

typedef struct {
    char date[11];
    int n;
    wall_event_t ev[8];
} wall_day_t;

typedef struct {
    char id[24];
    char title[96];
    bool late;
    uint32_t color;
    bool has_color;
    bool done;             /* ticked here; the next feed leaves it out */
} wall_task_t;

typedef struct {
    char id[64];
    char name[48];
    char text[32];
    char domain[24];
    char tap[8];           /* "toggle", "on", or "" when a tap does nothing */
    int on;                /* 1, 0, or -1 when it has no on and off */
} wall_ha_t;

typedef struct {
    time_t t;
    int temp, icon, rain;
    bool wet, has_temp;
} wall_hour_t;

typedef struct {
    char date[11];
    int max, min, icon, rain;
    bool has_temp;
} wall_wday_t;

typedef struct {
    char name[48];
    int in;
    char label[24];
    int turns;
} wall_bday_t;

typedef struct {
    char id[24];
    int year, ago;
} wall_photo_t;

typedef struct {
    bool ok;
    time_t fetched;
    char why[120];
    char zone[64], posix[64];
    bool imperial;
    char bg[8];            /* photos | sky | black */
    int every;             /* seconds per photo */
    char user[48], role[12];

    bool has_weather;
    int temp; bool has_temp;
    char wtext[48]; int wicon; bool wday;
    char place[64];
    char rain_what[8]; time_t rain_from, rain_until; int rain_mode; /* 0 none, 1 from, 2 until, 3 for hours */
    wall_hour_t hours[12]; int nhours;
    wall_wday_t wdays[5]; int nwdays;

    bool has_home;
    wall_ha_t ha[12]; int nha;
    char alerts[3][96]; int nalerts;

    wall_bday_t bdays[6]; int nbdays;

    bool has_today;
    wall_event_t today[12]; int ntoday, today_more;
    bool has_next; wall_event_t next;
    bool has_days;
    wall_day_t days[7]; int ndays;

    bool has_tasks;
    wall_task_t tasks[10]; int ntasks, tasks_more, overdue;

    wall_photo_t photos[24]; int nphotos;
    bool can_add_task, can_add_event, can_fav, can_home;
} wall_feed_t;

/** The feed the screens show (read it holding the UI lock); never NULL once feed_init ran. */
extern wall_feed_t *FEED;
/** Before any screen: an empty feed and the task behind feed_run. */
void feed_init(void);
/** Asking the start page, and the photos: once the network is set up. */
void feed_start(void);
/** Ask again now (after a change made here, or a tap on Refresh). */
void feed_refresh(void);
/** The next photo now (a tap on the background). */
void feed_next_photo(void);
/** The photo on screen, or NULL. */
const wall_photo_t *feed_current_photo(void);
/** Whether the photo on screen is a favorite (set by a hold). */
bool feed_photo_is_favorite(void);
void feed_set_photo_favorite(bool on);
/** Run fn(arg) on the feed's task (an HTTP call that should not hold up the screen). */
void feed_run(void (*fn)(void *), void *arg);

/* ------------------------------------------------------------------ ui.c and its parts */

void ui_lock(void);
void ui_unlock(void);
void ui_start(lv_display_t *disp);
/** The fonts: text sizes in pixels. */
const lv_font_t *font_text(int px);
const lv_font_t *font_bold(int px);
const lv_font_t *font_light(int px);
/** LVGL's own font, for a symbol (LV_SYMBOL_…) or the keyboard: the nearest size it has. */
const lv_font_t *font_symbols(int px);

void ui_show_setup(void);        /* Wi-Fi, address, sign-in */
void ui_show_wall(void);
void ui_wall_feed_changed(void); /* FEED was replaced */
void ui_wall_photo(const lv_image_dsc_t *img, const char *caption); /* a new photo to fade in; NULL: none */
void ui_wall_tick(void);         /* every second: the clock, timers */
void ui_wall_viewing(bool on);   /* a view is over the wall: its own parts go, the photo darkens */

/* the views a swipe away from the wall (ui_views.c) */
#define VIEWS 6
void ui_views_init(lv_obj_t *parent);
void ui_views_swipe(int dir);    /* 1: the next one, -1: the one before */
void ui_views_home(void);        /* back to the wall */
bool ui_views_showing(void);
void ui_views_reset(void);
void ui_views_tick(void);
const char *ui_views_name(int i);
bool ui_views_has(int i);        /* the start page has it for this person */
void views_poll(void);           /* on the feed's task, after each feed */
void ui_toast(const char *text);
void ui_show_settings(void);
void ui_open_event(const wall_event_t *ev);
void ui_open_add(void);
void ui_open_timers(void);
void ui_open_alarms(void);
void ui_ringing(bool on, const char *what);
void ui_wake(void);              /* a touch: full brightness for a while at night */
void ui_apply_brightness(void);
void ui_apply_rotation(void);
bool ui_screen_dark(void);      /* the night has turned the backlight off */

/* the parts screens are made of (ui.c) */
lv_obj_t *kit_label(lv_obj_t *p, const lv_font_t *f, lv_color_t c, const char *t);
lv_obj_t *kit_button(lv_obj_t *p, const char *text, lv_event_cb_t cb, void *ud, bool primary);
lv_obj_t *kit_textarea(lv_obj_t *p, const char *placeholder, bool password);
lv_obj_t *kit_keyboard(lv_obj_t *p, lv_obj_t *ta, lv_event_cb_t on_ready, void *ud);
/** A card over the wall (on the top layer) with a title and a close button; returns the card, a flex column. */
lv_obj_t *kit_panel(const char *title, int w, int h);
void kit_close_panel(void);
bool kit_panel_open(void);

/* time and text, as the person reads them */
void fmt_time(char *out, size_t n, time_t t);           /* "6:00 PM" / "18:00" */
void fmt_hour(char *out, size_t n, time_t t);           /* "6 PM" / "18" */
void fmt_event_when(char *out, size_t n, const wall_event_t *e);
void fmt_day_head(char *out, size_t n, const char *date);  /* "Tomorrow", "Friday", "Fri 28 Nov" */
lv_color_t color_hex(uint32_t rgb);

/* ------------------------------------------------------------------ alarm.c */

#define TIMERS 4

typedef struct {
    bool on;
    int64_t ends_ms;       /* esp_timer time it rings */
    int total_s;
    char label[24];
} wall_timer_t;

extern wall_timer_t TIMER[TIMERS];
void alarm_start(void);
void alarm_tick(void);           /* every second, holding the UI lock */
int timer_add(int seconds, const char *label);
void timer_cancel(int i);
bool alarm_ringing(void);
void alarm_stop(void);
void alarm_snooze(void);
/** The next alarm that is on: its time, or 0. */
time_t alarm_next(void);
void sound_beep(int ms);
void sound_set_volume(int pct);

/* ------------------------------------------------------------------ power.c */

void power_start(void);
void power_tick(void);           /* every ten seconds */
/** True when the board runs on its battery; pct: how full it is. False on USB power, with no battery, or on a board
 *  that cannot tell. */
bool power_on_battery(int *pct);
/** USB power is filling the battery (the level then shows with a charge mark). */
bool power_charging(void);
/** The readings as they are, for Settings: "7.62 V, -410 mA (out of the battery)". */
void power_text(char *out, size_t n);

/* ------------------------------------------------------------------ ota.c */

typedef enum { OTA_IDLE, OTA_CHECKING, OTA_NONE, OTA_FOUND, OTA_UPDATING, OTA_FAILED } ota_state_t;

void ota_start(void);
void ota_check_now(bool install);
ota_state_t ota_state(void);
const char *ota_text(void);
const char *wall_version(void);

/* ------------------------------------------------------------------ boot.c */

typedef enum { BOOT_BEGIN, BOOT_SCREEN, BOOT_SOUND, BOOT_ROTATE, BOOT_UI, BOOT_WIFI, BOOT_FEED, BOOT_OTA, BOOT_RUNNING } boot_step_t;

void boot_begin(void);              /* first thing: reads what the last run left */
void boot_step(boot_step_t s);      /* the step now starting */
bool boot_skip(boot_step_t s);      /* the last run stopped in this step: leave it out */
void boot_report(bool can_go_on);   /* the last stop, on the screen */
void boot_running(void);

#define TAG_WALL "wall"
