/* The panels that open over the wall: an event's details, quick add (a task or an event), timers, alarms, the alarm
 * ringing, and the settings. */
#include <string.h>
#include "cJSON.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "wall.h"

#define TEXT lv_color_white()
#define DIM lv_color_hex(0xb8bcc4)
#define ACCENT lv_color_hex(0x3f86c9)

static lv_obj_t *line(lv_obj_t *p, int px, lv_color_t c, const char *t)
{
    lv_obj_t *l = kit_label(p, font_text(px), c, t);
    lv_label_set_long_mode(l, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(l, lv_pct(100));
    return l;
}

static lv_obj_t *hrow(lv_obj_t *p, int gap)
{
    lv_obj_t *r = lv_obj_create(p);
    lv_obj_remove_style_all(r);
    lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(r, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_flex_align(r, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(r, P(gap), 0);
    lv_obj_set_style_pad_row(r, P(gap), 0);
    return r;
}

/* a chip: one of a few, the chosen one lit */
static lv_obj_t *chip(lv_obj_t *p, const char *text, lv_event_cb_t cb, void *ud, bool on)
{
    lv_obj_t *b = lv_button_create(p);
    lv_obj_set_height(b, P(64));
    lv_obj_set_style_pad_hor(b, P(24), 0);
    lv_obj_set_style_radius(b, P(32), 0);
    lv_obj_set_style_shadow_width(b, 0, 0);
    lv_obj_set_style_bg_color(b, on ? ACCENT : lv_color_hex(0x2a2c31), 0);
    lv_obj_t *l = kit_label(b, font_text(26), TEXT, text);
    lv_obj_center(l);
    if (cb) lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, ud);
    return b;
}

static void light_chips(lv_obj_t *row, lv_obj_t *on)
{
    for (uint32_t i = 0; i < lv_obj_get_child_count(row); i++) {
        lv_obj_t *c = lv_obj_get_child(row, i);
        lv_obj_set_style_bg_color(c, c == on ? ACCENT : lv_color_hex(0x2a2c31), 0);
    }
}

static void date_of(time_t t, char *out, size_t n)
{
    struct tm tm;
    localtime_r(&t, &tm);
    strftime(out, n, "%Y-%m-%d", &tm);
}

/* ------------------------------------------------------------------ an event */

void ui_open_event(const wall_event_t *ev)
{
    bool more = ev->nwho || ev->people[0] || ev->notes[0];
    lv_obj_t *c = kit_panel(ev->title, P(860), more ? P(620) : P(520));
    lv_obj_set_scroll_dir(c, LV_DIR_VER);
    char day[11], head[48], when[96];
    if (ev->all_day) {
        strlcpy(day, ev->day, sizeof day);
        fmt_day_head(head, sizeof head, day);
        if (ev->end_day[0] && strcmp(ev->end_day, ev->day)) {
            /* the end is the day after the last one */
            int y, m, d;
            char last[48] = "";
            if (sscanf(ev->end_day, "%d-%d-%d", &y, &m, &d) == 3) {
                struct tm t = {.tm_year = y - 1900, .tm_mon = m - 1, .tm_mday = d - 1, .tm_hour = 12};
                time_t tt = mktime(&t);
                char ld[11];
                date_of(tt, ld, sizeof ld);
                if (strcmp(ld, ev->day)) fmt_day_head(last, sizeof last, ld);
            }
            if (last[0]) snprintf(when, sizeof when, "%s to %s, all day", head, last);
            else snprintf(when, sizeof when, "%s, all day", head);
        } else {
            snprintf(when, sizeof when, "%s, all day", head);
        }
    } else {
        date_of(ev->s, day, sizeof day);
        fmt_day_head(head, sizeof head, day);
        char a[16], b[16] = "";
        fmt_time(a, sizeof a, ev->s);
        if (ev->e > ev->s) fmt_time(b, sizeof b, ev->e);
        if (b[0]) snprintf(when, sizeof when, "%s, %s – %s", head, a, b);
        else snprintf(when, sizeof when, "%s, %s", head, a);
    }
    lv_obj_t *r = hrow(c, 14);
    lv_obj_t *dot = lv_obj_create(r);
    lv_obj_remove_style_all(dot);
    lv_obj_set_size(dot, P(22), P(22));
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(dot, ev->has_color ? color_hex(ev->color) : DIM, 0);
    kit_label(r, font_text(32), TEXT, when);
    if (ev->nwho) {
        /* who of the family it is for, each in their colour */
        lv_obj_t *w = hrow(c, 12);
        for (int i = 0; i < ev->nwho; i++) {
            lv_obj_t *p = lv_obj_create(w);
            lv_obj_remove_style_all(p);
            lv_obj_set_size(p, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
            lv_obj_set_flex_flow(p, LV_FLEX_FLOW_ROW);
            lv_obj_set_flex_align(p, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
            lv_obj_set_style_pad_column(p, P(10), 0);
            lv_obj_set_style_pad_hor(p, P(18), 0);
            lv_obj_set_style_pad_ver(p, P(8), 0);
            lv_obj_set_style_radius(p, P(26), 0);
            lv_obj_set_style_bg_color(p, lv_color_hex(0x2a2c31), 0);
            lv_obj_set_style_bg_opa(p, LV_OPA_COVER, 0);
            lv_obj_t *d = lv_obj_create(p);
            lv_obj_remove_style_all(d);
            lv_obj_set_size(d, P(18), P(18));
            lv_obj_set_style_radius(d, LV_RADIUS_CIRCLE, 0);
            lv_obj_set_style_bg_opa(d, LV_OPA_COVER, 0);
            lv_obj_set_style_bg_color(d, ev->who[i].has_color ? color_hex(ev->who[i].color) : DIM, 0);
            kit_label(p, font_text(28), TEXT, ev->who[i].name);
        }
    }
    if (ev->people[0]) {
        line(c, 22, DIM, "With");
        line(c, 28, TEXT, ev->people);
    }
    if (ev->location[0]) {
        line(c, 22, DIM, "Where");
        line(c, 28, TEXT, ev->location);
    }
    if (ev->notes[0]) {
        line(c, 22, DIM, "Notes");
        line(c, 26, TEXT, ev->notes);
    }
    if (ev->calendar[0] || ev->recurring) {
        char t[80];
        snprintf(t, sizeof t, "%s%s%s", ev->calendar, ev->calendar[0] && ev->recurring ? "  ·  " : "", ev->recurring ? "Repeats" : "");
        line(c, 22, DIM, t);
    }
}

/* ------------------------------------------------------------------ quick add */

static lv_obj_t *add_ta, *add_kb, *add_status, *add_days, *add_times, *add_kinds;
static bool add_event_kind;
static int add_day;      /* 0 today, 1 tomorrow, … 6; -1: no date (a task) */
static int add_minutes;  /* the event's time of day; -1: all day */

typedef struct {
    bool event;
    char title[200];
    int day, minutes;
} add_job_t;

static void add_call(void *arg)
{
    add_job_t *j = arg;
    cJSON *o = cJSON_CreateObject();
    cJSON_AddStringToObject(o, "title", j->title);
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    t.tm_mday += j->day < 0 ? 0 : j->day;
    t.tm_hour = 12;
    t.tm_min = t.tm_sec = 0;
    t.tm_isdst = -1;
    time_t when = mktime(&t);
    char day[11];
    date_of(when, day, sizeof day);
    if (FEED->zone[0]) cJSON_AddStringToObject(o, "timezone", FEED->zone);
    const char *path;
    if (j->event) {
        path = "/api/widgets/iocalendar/events";
        if (j->minutes < 0) {
            cJSON_AddStringToObject(o, "start", day);
            cJSON_AddBoolToObject(o, "allDay", true);
        } else {
            char s[24], e[24];
            int end = j->minutes + 60;
            snprintf(s, sizeof s, "%sT%02d:%02d:00", day, j->minutes / 60, j->minutes % 60);
            if (end < 24 * 60) {
                snprintf(e, sizeof e, "%sT%02d:%02d:00", day, end / 60, end % 60);
                cJSON_AddStringToObject(o, "end", e);
            }
            cJSON_AddStringToObject(o, "start", s);
            cJSON_AddBoolToObject(o, "allDay", false);
        }
    } else {
        path = "/api/widgets/iotask/tasks";
        if (j->day >= 0) cJSON_AddStringToObject(o, "due", day);
    }
    char *body = cJSON_PrintUnformatted(o);
    cJSON_Delete(o);
    api_resp_t r = api_request("POST", path, body, 8192, NULL);
    cJSON_free(body);
    ui_lock();
    if (r.status == 200) {
        kit_close_panel();
        ui_toast(j->event ? "Added to ioCalendar" : "Added to ioTask");
    } else if (add_status && kit_panel_open()) {
        lv_label_set_text(add_status, r.why[0] ? r.why : "It was not added");
        lv_obj_set_style_text_color(add_status, lv_color_hex(0xffb4a8), 0);
    }
    ui_unlock();
    api_free(&r);
    free(j);
    feed_refresh();
}

static void on_add_go(lv_event_t *e)
{
    const char *t = lv_textarea_get_text(add_ta);
    while (*t == ' ') t++;
    if (!*t) {
        lv_label_set_text(add_status, "What is it?");
        return;
    }
    add_job_t *j = calloc(1, sizeof *j);
    if (!j) return;
    j->event = add_event_kind;
    strlcpy(j->title, t, sizeof j->title);
    j->day = add_day;
    j->minutes = add_minutes;
    lv_label_set_text(add_status, "Adding…");
    feed_run(add_call, j);
}

static void draw_add_options(void);

static void on_add_kind(lv_event_t *e)
{
    add_event_kind = (intptr_t)lv_event_get_user_data(e) == 1;
    if (add_event_kind && add_day < 0) add_day = 0;
    light_chips(add_kinds, lv_event_get_target(e));
    draw_add_options();
}

static void on_add_day(lv_event_t *e)
{
    add_day = (int)(intptr_t)lv_event_get_user_data(e);
    light_chips(add_days, lv_event_get_target(e));
}

static void on_add_time(lv_event_t *e)
{
    lv_obj_t *dd = lv_event_get_target(e);
    int i = lv_dropdown_get_selected(dd);
    add_minutes = i == 0 ? -1 : (6 * 60 + (i - 1) * 30);  /* All day, 6:00, 6:30 … 23:30 */
}

static void draw_add_options(void)
{
    lv_obj_clean(add_days);
    static const char *W[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
    if (!add_event_kind) chip(add_days, "No date", on_add_day, (void *)(intptr_t)-1, add_day == -1);
    time_t now = time(NULL);
    for (int d = 0; d < 7; d++) {
        char t[16];
        if (d == 0) strlcpy(t, "Today", sizeof t);
        else if (d == 1) strlcpy(t, "Tomorrow", sizeof t);
        else {
            time_t x = now + d * 86400;
            struct tm tm;
            localtime_r(&x, &tm);
            strlcpy(t, W[tm.tm_wday], sizeof t);
        }
        if (!add_event_kind && d > 1) break;  /* a task: today, tomorrow or none */
        chip(add_days, t, on_add_day, (void *)(intptr_t)d, add_day == d);
    }
    if (add_event_kind) lv_obj_remove_flag(add_times, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(add_times, LV_OBJ_FLAG_HIDDEN);
}

static void on_add_closed(lv_event_t *e)
{
    if (add_kb) {
        lv_obj_delete(add_kb);
        add_kb = NULL;
    }
    add_ta = add_status = add_days = add_times = add_kinds = NULL;
}

void ui_open_add(void)
{
    if (!FEED->can_add_task && !FEED->can_add_event) {
        ui_toast("Adding needs ioTask or ioCalendar on the start page");
        return;
    }
    lv_obj_t *c = kit_panel("Add", P(1220), P(400));
    lv_obj_align(c, LV_ALIGN_TOP_MID, 0, P(6));
    lv_obj_add_event_cb(lv_obj_get_parent(c), on_add_closed, LV_EVENT_DELETE, NULL);
    add_event_kind = !FEED->can_add_task;
    add_day = add_event_kind ? 0 : -1;
    add_minutes = -1;
    lv_obj_t *top = hrow(c, 10);
    add_kinds = top;
    if (FEED->can_add_task) chip(top, "A task", on_add_kind, (void *)0, !add_event_kind);
    if (FEED->can_add_event) chip(top, "An event", on_add_kind, (void *)1, add_event_kind);
    add_times = lv_dropdown_create(top);
    char opts[1400] = "All day";
    for (int m = 6 * 60; m < 24 * 60; m += 30) {
        char t[16];
        time_t now = time(NULL);
        struct tm tm;
        localtime_r(&now, &tm);
        tm.tm_hour = m / 60;
        tm.tm_min = m % 60;
        fmt_time(t, sizeof t, mktime(&tm));
        strlcat(opts, "\n", sizeof opts);
        strlcat(opts, t, sizeof opts);
    }
    lv_dropdown_set_options(add_times, opts);
    lv_obj_set_width(add_times, P(220));
    lv_obj_set_style_text_font(add_times, font_text(26), 0);
    lv_obj_set_style_text_font(lv_dropdown_get_list(add_times), font_text(26), 0);
    lv_obj_add_event_cb(add_times, on_add_time, LV_EVENT_VALUE_CHANGED, NULL);
    add_ta = kit_textarea(c, "What? e.g. Buy milk, Dentist", false);
    add_days = hrow(c, 10);
    add_status = kit_label(c, font_text(26), DIM, "");
    draw_add_options();
    add_kb = kit_keyboard(lv_layer_top(), add_ta, on_add_go, NULL);
    lv_obj_set_height(add_kb, P(300));
}

/* ------------------------------------------------------------------ timers */

static lv_obj_t *timer_list;

static void draw_timer_list(void);

static void on_timer_preset(lv_event_t *e)
{
    int s = (int)(intptr_t)lv_event_get_user_data(e);
    if (timer_add(s, "") < 0) ui_toast("Four timers at most");
    draw_timer_list();
}

static void on_timer_cancel(lv_event_t *e)
{
    timer_cancel((int)(intptr_t)lv_event_get_user_data(e));
    draw_timer_list();
}

static void draw_timer_list(void)
{
    if (!timer_list) return;
    lv_obj_clean(timer_list);
    int64_t now = esp_timer_get_time() / 1000;
    bool any = false;
    for (int i = 0; i < TIMERS; i++) {
        if (!TIMER[i].on) continue;
        any = true;
        lv_obj_t *r = hrow(timer_list, 16);
        int64_t left = (TIMER[i].ends_ms - now + 999) / 1000;
        if (left < 0) left = 0;
        lv_obj_t *l = kit_label(r, font_bold(40), TEXT, "");
        if (left >= 3600) lv_label_set_text_fmt(l, "%d:%02d:%02d", (int)(left / 3600), (int)(left / 60 % 60), (int)(left % 60));
        else lv_label_set_text_fmt(l, "%d:%02d", (int)(left / 60), (int)(left % 60));
        lv_obj_set_width(l, P(220));
        kit_label(r, font_text(26), DIM, "");
        kit_button(r, "Cancel", on_timer_cancel, (void *)(intptr_t)i, false);
    }
    if (!any) line(timer_list, 28, DIM, "No timer running. Tap a time to start one.");
}

static lv_timer_t *timer_refresh;

static void timers_tick(lv_timer_t *t)
{
    if (!kit_panel_open() || !timer_list) {
        lv_timer_delete(t);
        timer_refresh = NULL;
        return;
    }
    draw_timer_list();
}

static void on_timers_closed(lv_event_t *e)
{
    timer_list = NULL;
}

void ui_open_timers(void)
{
    lv_obj_t *c = kit_panel("Timers", P(1000), P(560));
    lv_obj_add_event_cb(lv_obj_get_parent(c), on_timers_closed, LV_EVENT_DELETE, NULL);
    lv_obj_t *r = hrow(c, 12);
    static const struct { const char *t; int s; } P[] = {
        {"1 min", 60}, {"3 min", 180}, {"5 min", 300}, {"10 min", 600}, {"15 min", 900}, {"20 min", 1200},
        {"30 min", 1800}, {"45 min", 2700}, {"1 hour", 3600}, {"2 hours", 7200},
    };
    for (size_t i = 0; i < sizeof P / sizeof P[0]; i++) chip(r, P[i].t, on_timer_preset, (void *)(intptr_t)P[i].s, false);
    timer_list = lv_obj_create(c);
    lv_obj_remove_style_all(timer_list);
    lv_obj_set_size(timer_list, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(timer_list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(timer_list, P(10), 0);
    lv_obj_set_style_pad_top(timer_list, P(10), 0);
    draw_timer_list();
    if (!timer_refresh) timer_refresh = lv_timer_create(timers_tick, 1000, NULL);
}

/* ------------------------------------------------------------------ alarms */

static void on_alarm_switch(lv_event_t *e)
{
    int i = (int)(intptr_t)lv_event_get_user_data(e);
    S.alarms[i].on = lv_obj_has_state(lv_event_get_target(e), LV_STATE_CHECKED);
    settings_save();
}

static void on_alarm_time(lv_event_t *e)
{
    int i = (int)(intptr_t)lv_event_get_user_data(e);
    int sel = lv_dropdown_get_selected(lv_event_get_target(e));  /* every 5 minutes */
    S.alarms[i].hour = sel / 12;
    S.alarms[i].minute = (sel % 12) * 5;
    S.alarms[i].on = true;
    settings_save();
    ui_open_alarms();  /* the switch shows it on */
}

static void on_alarm_day(lv_event_t *e)
{
    int v = (int)(intptr_t)lv_event_get_user_data(e);
    int i = v / 8, d = v % 8;
    S.alarms[i].days ^= (uint8_t)(1 << d);
    settings_save();
    lv_obj_t *b = lv_event_get_target(e);
    lv_obj_set_style_bg_color(b, S.alarms[i].days & (1 << d) ? ACCENT : lv_color_hex(0x2a2c31), 0);
}

void ui_open_alarms(void)
{
    lv_obj_t *c = kit_panel("Alarms", P(1180), P(660));
    lv_obj_set_scroll_dir(c, LV_DIR_VER);
    static char opts[24 * 12 * 12];
    opts[0] = 0;
    for (int m = 0; m < 24 * 60; m += 5) {
        char t[16];
        time_t now = time(NULL);
        struct tm tm;
        localtime_r(&now, &tm);
        tm.tm_hour = m / 60;
        tm.tm_min = m % 60;
        tm.tm_isdst = -1;
        fmt_time(t, sizeof t, mktime(&tm));
        if (m) strlcat(opts, "\n", sizeof opts);
        strlcat(opts, t, sizeof opts);
    }
    static const char *D = "SMTWTFS";
    for (int i = 0; i < ALARMS; i++) {
        wall_alarm_t *a = &S.alarms[i];
        lv_obj_t *r = hrow(c, 12);
        lv_obj_set_style_pad_ver(r, P(6), 0);
        lv_obj_t *sw = lv_switch_create(r);
        lv_obj_set_size(sw, P(100), P(54));
        if (a->on) lv_obj_add_state(sw, LV_STATE_CHECKED);
        lv_obj_add_event_cb(sw, on_alarm_switch, LV_EVENT_VALUE_CHANGED, (void *)(intptr_t)i);
        lv_obj_t *dd = lv_dropdown_create(r);
        lv_dropdown_set_options_static(dd, opts);
        lv_dropdown_set_selected(dd, a->hour * 12 + a->minute / 5);
        lv_obj_set_width(dd, P(210));
        lv_obj_set_style_text_font(dd, font_bold(30), 0);
        lv_obj_set_style_text_font(lv_dropdown_get_list(dd), font_text(28), 0);
        lv_obj_add_event_cb(dd, on_alarm_time, LV_EVENT_VALUE_CHANGED, (void *)(intptr_t)i);
        for (int d = 0; d < 7; d++) {
            char t[2] = {D[d], 0};
            lv_obj_t *b = lv_button_create(r);
            lv_obj_set_size(b, P(64), P(64));
            lv_obj_set_style_radius(b, P(32), 0);
            lv_obj_set_style_shadow_width(b, 0, 0);
            lv_obj_set_style_bg_color(b, a->days & (1 << d) ? ACCENT : lv_color_hex(0x2a2c31), 0);
            lv_obj_t *l = kit_label(b, font_bold(26), TEXT, t);
            lv_obj_center(l);
            lv_obj_add_event_cb(b, on_alarm_day, LV_EVENT_CLICKED, (void *)(intptr_t)(i * 8 + d));
        }
        kit_label(r, font_text(24), DIM, a->days ? "" : "once");
    }
    line(c, 24, DIM, "No day picked: the alarm rings once, the next time it comes. It rings on the speaker until you tap Stop or Snooze.");
}

/* ------------------------------------------------------------------ ringing */

static lv_obj_t *ring;

static void on_stop(lv_event_t *e) { alarm_stop(); }
static void on_snooze(lv_event_t *e) { alarm_snooze(); }

void ui_ringing(bool on, const char *what)
{
    if (!on) {
        if (ring) lv_obj_delete(ring);
        ring = NULL;
        return;
    }
    ui_wake();
    if (ring) lv_obj_delete(ring);
    ring = lv_obj_create(lv_layer_sys());
    lv_obj_remove_style_all(ring);
    lv_obj_set_size(ring, WALL_W, WALL_H);
    lv_obj_set_style_bg_color(ring, lv_color_hex(0x0b0d12), 0);
    lv_obj_set_style_bg_opa(ring, LV_OPA_90, 0);
    lv_obj_add_flag(ring, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_flex_flow(ring, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(ring, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_row(ring, P(30), 0);
    kit_label(ring, font_symbols(48), lv_color_hex(0xffd36b), LV_SYMBOL_BELL);
    char now[16];
    fmt_time(now, sizeof now, time(NULL));
    kit_label(ring, font_light(150), TEXT, now);
    kit_label(ring, font_text(40), TEXT, what);
    lv_obj_t *r = lv_obj_create(ring);
    lv_obj_remove_style_all(r);
    lv_obj_set_size(r, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(r, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(r, P(30), 0);
    bool alarm = what && strncmp(what, "Timer", 5) != 0;
    if (alarm) {
        char t[32];
        snprintf(t, sizeof t, "Snooze %d min", S.snooze_min);
        lv_obj_t *b = kit_button(r, t, on_snooze, NULL, false);
        lv_obj_set_size(b, P(360), P(120));
    }
    lv_obj_t *b = kit_button(r, "Stop", on_stop, NULL, true);
    lv_obj_set_size(b, P(360), P(120));
}

/* ------------------------------------------------------------------ settings */

static lv_obj_t *ota_lbl;
static lv_timer_t *ota_timer;

static void on_clock24(lv_event_t *e)
{
    S.clock24 = lv_obj_has_state(lv_event_get_target(e), LV_STATE_CHECKED);
    settings_save();
    ui_show_wall();
}

static void on_flip(lv_event_t *e)
{
    S.flip = lv_obj_has_state(lv_event_get_target(e), LV_STATE_CHECKED);
    settings_save();
    ui_apply_rotation();
}

static void on_auto(lv_event_t *e)
{
    S.auto_update = lv_obj_has_state(lv_event_get_target(e), LV_STATE_CHECKED);
    settings_save();
}

static void on_slider(lv_event_t *e)
{
    uint8_t *v = lv_event_get_user_data(e);
    *v = (uint8_t)lv_slider_get_value(lv_event_get_target(e));
    if (v == &S.volume) sound_set_volume(S.volume);
    if (lv_event_get_code(e) == LV_EVENT_RELEASED) {
        settings_save();
        if (v == &S.volume) sound_beep(150);
    }
    if (v == &S.day_bright || v == &S.night_bright) {
        /* a preview while it moves */
        ui_wake();
    }
}

static void on_hour(lv_event_t *e)
{
    uint8_t *v = lv_event_get_user_data(e);
    *v = (uint8_t)lv_dropdown_get_selected(lv_event_get_target(e));
    settings_save();
    ui_apply_brightness();
}

static void on_signout(lv_event_t *e)
{
    settings_forget_sign_in();
    kit_close_panel();
    ui_show_setup();
}

static void on_wifi(lv_event_t *e)
{
    kit_close_panel();
    ui_show_setup();
}

static void ota_tick(lv_timer_t *t)
{
    if (!kit_panel_open() || !ota_lbl) {
        lv_timer_delete(t);
        ota_timer = NULL;
        return;
    }
    lv_label_set_text(ota_lbl, ota_text());
}

static void on_check(lv_event_t *e)
{
    ota_check_now(true);
}

static void on_settings_closed(lv_event_t *e)
{
    ota_lbl = NULL;
}

/* a view's chip: lit while it is swiped to */
static void on_view(lv_event_t *e)
{
    int i = (int)(intptr_t)lv_event_get_user_data(e);
    VIEWS_OFF ^= 1u << i;
    settings_save_views();
    lv_obj_set_style_bg_color(lv_event_get_target(e), VIEWS_OFF >> i & 1 ? lv_color_hex(0x2a2c31) : ACCENT, 0);
}

static lv_obj_t *setting(lv_obj_t *c, const char *name)
{
    lv_obj_t *r = hrow(c, 18);
    lv_obj_set_style_pad_ver(r, P(6), 0);
    lv_obj_t *l = kit_label(r, font_text(28), TEXT, name);
    lv_obj_set_width(l, P(330));
    return r;
}

static lv_obj_t *slider(lv_obj_t *r, uint8_t *v, int min)
{
    lv_obj_t *s = lv_slider_create(r);
    lv_obj_set_size(s, P(460), P(24));
    lv_slider_set_range(s, min, 100);
    lv_slider_set_value(s, *v, LV_ANIM_OFF);
    lv_obj_add_event_cb(s, on_slider, LV_EVENT_VALUE_CHANGED, v);
    lv_obj_add_event_cb(s, on_slider, LV_EVENT_RELEASED, v);
    lv_obj_set_style_pad_ver(r, P(14), 0);
    return s;
}

static lv_obj_t *toggle(lv_obj_t *r, bool on, lv_event_cb_t cb)
{
    lv_obj_t *sw = lv_switch_create(r);
    lv_obj_set_size(sw, P(100), P(54));
    if (on) lv_obj_add_state(sw, LV_STATE_CHECKED);
    lv_obj_add_event_cb(sw, cb, LV_EVENT_VALUE_CHANGED, NULL);
    return sw;
}

void ui_show_settings(void)
{
    lv_obj_t *c = kit_panel("Settings", P(1180), P(680));
    lv_obj_add_event_cb(lv_obj_get_parent(c), on_settings_closed, LV_EVENT_DELETE, NULL);
    lv_obj_set_scroll_dir(c, LV_DIR_VER);
    char t[200];

    lv_obj_t *r = setting(c, "Signed in");
    snprintf(t, sizeof t, "%s at %s", S.user[0] ? S.user : "?", S.server);
    lv_obj_t *who = kit_label(r, font_text(26), DIM, t);
    lv_label_set_long_mode(who, LV_LABEL_LONG_DOT);
    lv_obj_set_width(who, P(500));
    kit_button(r, "Sign out", on_signout, NULL, false);

    r = setting(c, "Wi-Fi");
    snprintf(t, sizeof t, "%s%s%s", S.ssid, net_ip()[0] ? " · " : "", net_ip());
    lv_obj_t *wl = kit_label(r, font_text(26), DIM, t);
    lv_obj_set_width(wl, P(500));
    kit_button(r, "Change", on_wifi, NULL, false);

    r = setting(c, "24-hour clock");
    toggle(r, S.clock24, on_clock24);

    r = setting(c, "Brightness");
    slider(r, &S.day_bright, 5);

    static const char *hours = "0:00\n1:00\n2:00\n3:00\n4:00\n5:00\n6:00\n7:00\n8:00\n9:00\n10:00\n11:00\n12:00\n13:00\n14:00\n15:00\n16:00\n17:00\n18:00\n19:00\n20:00\n21:00\n22:00\n23:00";
    r = setting(c, "Night");
    kit_label(r, font_text(26), DIM, "from");
    lv_obj_t *dd = lv_dropdown_create(r);
    lv_dropdown_set_options_static(dd, hours);
    lv_dropdown_set_selected(dd, S.night_from);
    lv_obj_set_width(dd, P(150));
    lv_obj_add_event_cb(dd, on_hour, LV_EVENT_VALUE_CHANGED, &S.night_from);
    kit_label(r, font_text(26), DIM, "to");
    dd = lv_dropdown_create(r);
    lv_dropdown_set_options_static(dd, hours);
    lv_dropdown_set_selected(dd, S.night_to);
    lv_obj_set_width(dd, P(150));
    lv_obj_add_event_cb(dd, on_hour, LV_EVENT_VALUE_CHANGED, &S.night_to);
    kit_label(r, font_text(22), DIM, "the same: no night");

    r = setting(c, "Brightness at night");
    slider(r, &S.night_bright, 0);
    line(c, 22, DIM, "At night the screen dims (all the way down: off) and a touch lights it for half a minute.");

    r = setting(c, "Volume");
    slider(r, &S.volume, 0);

    r = setting(c, "Views");
    int views = 0;
    for (int i = 0; i < VIEWS; i++) {
        if (!ui_views_has(i)) continue;
        chip(r, ui_views_name(i), on_view, (void *)(intptr_t)i, !(VIEWS_OFF >> i & 1));
        views++;
    }
    if (!views) kit_label(r, font_text(26), DIM, "None yet: the start page has not said which there are");
    line(c, 22, DIM, "A swipe to the left or the right on the wall goes through the lit ones; after three minutes untouched, the wall is back.");

    r = setting(c, "Turn the screen around");
    toggle(r, S.flip, on_flip);

    r = setting(c, "Time zone");
    snprintf(t, sizeof t, "%s (the start page's)", FEED->zone[0] ? FEED->zone : "not known yet");
    kit_label(r, font_text(26), DIM, t);

    r = setting(c, "Power");
    power_text(t, sizeof t);
    kit_label(r, font_text(26), DIM, t);

    r = setting(c, "Firmware");
    snprintf(t, sizeof t, "Version %s", wall_version());
    kit_label(r, font_text(26), DIM, t);
    kit_button(r, "Check and update", on_check, NULL, false);
    ota_lbl = line(c, 24, DIM, ota_text());
    r = setting(c, "Update by itself");
    toggle(r, S.auto_update, on_auto);
    line(c, 22, DIM, "At night, when a new version is on GitHub.");
    if (!ota_timer) ota_timer = lv_timer_create(ota_tick, 1000, NULL);
}
