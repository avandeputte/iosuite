/* The wall: as the start page's #/wall lays it out, on the Tab5's 1280 × 720 in landscape (every size goes through
 * P(), which brings it to another board's screen). A big clock and the date top left, the weather top right; today
 * and the coming days bottom left (a tap on Week: the whole week); today's tasks, the Home Assistant
 * things on the wall and the next hours bottom right. Behind it an ioPix photo every so often, a sky in the colours
 * of the hour and the weather, or black.
 *
 * Touch: a swipe to the left or the right goes to the views beside the wall (ui_views.c); an event opens its details; a task's circle ticks it off; a Home Assistant tile switches it; a tap on the
 * photo shows the next one and the bar (add, timers, alarms, favorite, settings). */
#include <string.h>
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "icons.h"
#include "wall.h"

#define TEXT lv_color_white()
#define DIM lv_color_hex(0xd8dbe2)
#define SUNNY lv_color_hex(0xffd36b)
#define RAINY lv_color_hex(0x9fd0ff)

static lv_obj_t *scr;
static lv_obj_t *sky, *img[2], *dim, *shade_top, *shade_bottom;
static int img_top = -1;
static lv_obj_t *top_left, *clock_lbl, *ampm_lbl, *date_lbl, *chips;
static lv_obj_t *wx_box, *wx_icon, *wx_temp, *wx_text, *wx_rain, *wx_days;
static lv_obj_t *agenda, *agenda_list, *tab_today, *tab_week;
static lv_obj_t *right, *tasks_box, *ha_box, *hours_box;
static lv_obj_t *caption, *status_pill, *bar, *fav_btn;
static lv_timer_t *bar_timer;
static bool week_view;
static bool viewing;   /* a view (ui_views.c) is over the wall */
static int shown_min = -1, shown_mday = -1;

/* ------------------------------------------------------------------ small parts */

static lv_obj_t *label(lv_obj_t *parent, const lv_font_t *f, lv_color_t c, const char *text)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_set_style_text_font(l, f, 0);
    lv_obj_set_style_text_color(l, c, 0);
    lv_label_set_text(l, text ? text : "");
    return l;
}

static lv_obj_t *box(lv_obj_t *parent)
{
    lv_obj_t *o = lv_obj_create(parent);
    lv_obj_remove_style_all(o);
    lv_obj_set_size(o, LV_SIZE_CONTENT, LV_SIZE_CONTENT);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_remove_flag(o, LV_OBJ_FLAG_CLICKABLE);
    return o;
}

static lv_obj_t *row(lv_obj_t *parent, int gap)
{
    lv_obj_t *o = box(parent);
    lv_obj_set_flex_flow(o, LV_FLEX_FLOW_ROW);
    lv_obj_set_flex_align(o, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    lv_obj_set_style_pad_column(o, P(gap), 0);
    return o;
}

static lv_obj_t *column(lv_obj_t *parent, int gap)
{
    lv_obj_t *o = box(parent);
    lv_obj_set_flex_flow(o, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(o, P(gap), 0);
    return o;
}

/* one line, cut with "…" when it is too long (LVGL cuts only a label whose height is fixed) */
static void one_line(lv_obj_t *l, const lv_font_t *f)
{
    lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
    lv_obj_set_height(l, lv_font_get_line_height(f));
}

static void shadow_text(lv_obj_t *l)
{
    /* the shades behind the text keep it readable on a bright photo (shades_for); nothing more to do per label */
    (void)l;
}

/* an icon drawn from px wide at want wide (both as on the Tab5's screen) */
static void icon_fit(lv_obj_t *i, int px, int want)
{
    if (P(want) == px) return;
    lv_image_set_scale(i, 256 * P(want) / px);
    lv_obj_set_size(i, P(want), P(want));
    lv_image_set_inner_align(i, LV_IMAGE_ALIGN_CENTER);
}

static lv_obj_t *weather_icon(lv_obj_t *parent, int n, bool day, bool big)
{
    lv_obj_t *i = lv_image_create(parent);
    icon_kind_t k = icon_for_accuweather(n, day);
    lv_image_set_src(i, big ? icons_big[k] : icons_small[k]);
    icon_fit(i, big ? 112 : 52, big ? 112 : 52);
    lv_obj_set_style_image_recolor(i, k == ICON_MOON || k == ICON_PARTLY_NIGHT ? lv_color_hex(0xe8ecff) : SUNNY, 0);
    lv_obj_set_style_image_recolor_opa(i, LV_OPA_COVER, 0);
    return i;
}

static void temp_text(char *out, size_t n, int t)
{
    snprintf(out, n, "%d°", t);
}

/* ------------------------------------------------------------------ the sky */

static lv_color_t muted(lv_color_t c, int how)
{
    /* toward grey: cloudy and rainy skies */
    uint8_t g = (uint8_t)((c.red * 3 + c.green * 6 + c.blue) / 10);
    return lv_color_mix(lv_color_make(g, g, g), c, (uint8_t)how);
}

static void paint_sky(void)
{
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    int h = t.tm_hour;
    uint32_t top, bottom;
    if (h >= 6 && h < 8) { top = 0x1c2a5a; bottom = 0xe48a6c; }        /* dawn */
    else if (h >= 8 && h < 17) { top = 0x1f5fa8; bottom = 0x9fc7ea; }  /* day */
    else if (h >= 17 && h < 20) { top = 0x1a1f4d; bottom = 0xc05a5a; } /* dusk */
    else { top = 0x050b1e; bottom = 0x2d1f3f; }                         /* night */
    if (FEED->has_weather && !FEED->wday && h >= 8 && h < 17) { top = 0x050b1e; bottom = 0x2d1f3f; }
    lv_color_t a = lv_color_hex(top), b = lv_color_hex(bottom);
    icon_kind_t k = FEED->has_weather ? icon_for_accuweather(FEED->wicon, FEED->wday) : ICON_SUN;
    if (k == ICON_CLOUD || k == ICON_FOG || k == ICON_PARTLY_DAY || k == ICON_PARTLY_NIGHT) { a = muted(a, 110); b = muted(b, 110); }
    else if (k == ICON_RAIN || k == ICON_THUNDER || k == ICON_SLEET) { a = lv_color_darken(muted(a, 80), 40); b = lv_color_darken(muted(b, 80), 50); }
    else if (k == ICON_SNOW) { a = muted(a, 70); b = lv_color_lighten(muted(b, 70), 40); }
    bool black = !strcmp(FEED->bg, "black");
    lv_obj_set_style_bg_color(sky, black ? lv_color_black() : a, 0);
    lv_obj_set_style_bg_grad_color(sky, black ? lv_color_black() : b, 0);
}

/* ------------------------------------------------------------------ the bar (a tap on the photo) */

static void bar_hide(lv_timer_t *t)
{
    lv_obj_add_flag(bar, LV_OBJ_FLAG_HIDDEN);
    bar_timer = NULL;
}

static void bar_show(void)
{
    lv_obj_remove_flag(bar, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(bar);
    bool photo = feed_current_photo() && FEED->can_fav;
    if (photo) lv_obj_remove_flag(fav_btn, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(fav_btn, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_text_color(lv_obj_get_child(fav_btn, 0), feed_photo_is_favorite() ? lv_color_hex(0xff6b81) : TEXT, 0);
    if (bar_timer) lv_timer_delete(bar_timer);
    bar_timer = lv_timer_create(bar_hide, 7000, NULL);
    lv_timer_set_repeat_count(bar_timer, 1);
}

typedef struct {
    char id[24];
    bool on;
} fav_job_t;

static void fav_call(void *arg)
{
    fav_job_t *j = arg;
    char path[80], body[24];
    snprintf(path, sizeof path, "/api/wall/photos/%s/favorite", j->id);
    snprintf(body, sizeof body, "{\"on\": %s}", j->on ? "true" : "false");
    api_resp_t r = api_request("POST", path, body, 4096, NULL);
    ui_lock();
    if (r.status == 200) ui_toast(j->on ? "Added to your favorites in ioPix" : "Taken out of your favorites");
    else ui_toast(r.why[0] ? r.why : "ioPix did not take it");
    if (r.status != 200) feed_set_photo_favorite(!j->on);
    ui_unlock();
    api_free(&r);
    free(j);
}

static void toggle_favorite(void)
{
    const wall_photo_t *p = feed_current_photo();
    if (!p || !FEED->can_fav) return;
    fav_job_t *j = calloc(1, sizeof *j);
    if (!j) return;
    strlcpy(j->id, p->id, sizeof j->id);
    j->on = !feed_photo_is_favorite();
    feed_set_photo_favorite(j->on);
    if (!lv_obj_has_flag(bar, LV_OBJ_FLAG_HIDDEN)) {
        lv_obj_set_style_text_color(lv_obj_get_child(fav_btn, 0), j->on ? lv_color_hex(0xff6b81) : TEXT, 0);
    }
    feed_run(fav_call, j);
}

static void on_bar(lv_event_t *e)
{
    intptr_t what = (intptr_t)lv_event_get_user_data(e);
    bar_hide(NULL);
    switch (what) {
    case 0: ui_open_add(); break;
    case 1: ui_open_timers(); break;
    case 2: ui_open_alarms(); break;
    case 3: toggle_favorite(); bar_show(); break;
    case 4: feed_refresh(); feed_next_photo(); ui_toast("Asking the start page again"); break;
    case 5: ui_show_settings(); break;
    }
}

static lv_obj_t *bar_button(const char *sym, const char *text, intptr_t what)
{
    lv_obj_t *b = lv_button_create(bar);
    lv_obj_set_size(b, P(150), P(110));
    lv_obj_set_style_radius(b, P(24), 0);
    lv_obj_set_style_bg_color(b, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(b, LV_OPA_60, 0);
    lv_obj_set_style_shadow_width(b, 0, 0);
    lv_obj_set_flex_flow(b, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(b, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
    label(b, font_symbols(36), TEXT, sym);
    label(b, font_text(22), DIM, text);
    lv_obj_add_event_cb(b, on_bar, LV_EVENT_CLICKED, (void *)what);
    return b;
}

/* ------------------------------------------------------------------ the background's touch */

static void on_background(lv_event_t *e)
{
    lv_event_code_t c = lv_event_get_code(e);
    if (lv_event_get_target(e) != scr) return;
    if (c == LV_EVENT_SHORT_CLICKED) {
        if (!lv_obj_has_flag(bar, LV_OBJ_FLAG_HIDDEN)) {
            bar_hide(NULL);
            return;
        }
        bar_show();
        if (feed_current_photo()) feed_next_photo();
    }
}

/* A swipe to the left or the right, wherever it starts (LVGL hands a gesture to the screen): the next view or the one
 * before (ui_views.c). The finger's lift is then not a tap as well. */
static void on_swipe(lv_event_t *e)
{
    lv_indev_t *in = lv_indev_active();
    lv_dir_t d = lv_indev_get_gesture_dir(in);
    if (d != LV_DIR_LEFT && d != LV_DIR_RIGHT) return;
    lv_indev_wait_release(in);
    if (!lv_obj_has_flag(bar, LV_OBJ_FLAG_HIDDEN)) lv_obj_add_flag(bar, LV_OBJ_FLAG_HIDDEN);
    ui_views_swipe(d == LV_DIR_LEFT ? 1 : -1);
}

/* ------------------------------------------------------------------ the agenda */

static void on_event_row(lv_event_t *e)
{
    const wall_event_t *ev = lv_event_get_user_data(e);
    ui_open_event(ev);
}

static void event_row(lv_obj_t *parent, const wall_event_t *ev, bool show_when)
{
    lv_obj_t *r = row(parent, 12);
    lv_obj_set_width(r, lv_pct(100));
    lv_obj_add_flag(r, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_pad_ver(r, P(3), 0);
    lv_obj_set_style_radius(r, P(12), 0);
    lv_obj_set_style_bg_color(r, lv_color_white(), LV_STATE_PRESSED);
    lv_obj_set_style_bg_opa(r, LV_OPA_20, LV_STATE_PRESSED);
    lv_obj_add_event_cb(r, on_event_row, LV_EVENT_CLICKED, (void *)ev);
    lv_obj_t *dot = box(r);
    lv_obj_set_size(dot, P(12), P(12));
    lv_obj_set_style_radius(dot, LV_RADIUS_CIRCLE, 0);
    lv_obj_set_style_bg_opa(dot, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(dot, ev->has_color ? color_hex(ev->color) : DIM, 0);
    char when[24];
    fmt_event_when(when, sizeof when, ev);
    lv_obj_t *w = label(r, font_text(24), DIM, show_when ? when : "");
    lv_obj_set_width(w, S.clock24 ? P(76) : P(112));
    /* "Dinner @ Nan Xiang Soup Dumplings" on one line; the place without what follows " - " (a branch, a town) */
    char line[176];
    if (ev->place[0]) {
        char place[64];
        strlcpy(place, ev->place, sizeof place);
        char *cut = strstr(place, " - ");
        if (cut && cut > place) *cut = 0;
        snprintf(line, sizeof line, "%s @ %s", ev->title, place);
    } else {
        strlcpy(line, ev->title, sizeof line);
    }
    lv_obj_t *t = label(r, font_text(28), TEXT, line);
    one_line(t, font_text(28));
    lv_obj_set_flex_grow(t, 1);
    lv_obj_set_style_min_width(t, P(80), 0);
    shadow_text(t);
}

static void head(lv_obj_t *parent, const char *text)
{
    lv_obj_t *l = label(parent, font_bold(20), DIM, text);
    lv_obj_set_style_text_letter_space(l, 2, 0);
    lv_obj_set_style_pad_top(l, P(10), 0);
}

static void muted_line(lv_obj_t *parent, const char *text)
{
    lv_obj_t *l = label(parent, font_text(26), DIM, text);
    one_line(l, font_text(26));
    lv_obj_set_width(l, lv_pct(100));
}

static void draw_agenda(void)
{
    lv_obj_clean(agenda_list);
    lv_obj_set_style_text_color(lv_obj_get_child(tab_today, 0), week_view ? DIM : TEXT, 0);
    lv_obj_set_style_bg_opa(tab_today, week_view ? LV_OPA_TRANSP : LV_OPA_40, 0);
    lv_obj_set_style_text_color(lv_obj_get_child(tab_week, 0), week_view ? TEXT : DIM, 0);
    lv_obj_set_style_bg_opa(tab_week, week_view ? LV_OPA_40 : LV_OPA_TRANSP, 0);
    if (!FEED->ok) {
        muted_line(agenda_list, FEED->why[0] ? FEED->why : "Asking the start page…");
        return;
    }
    if (!week_view) {
        for (int i = 0; i < FEED->nbdays; i++) {
            const wall_bday_t *b = &FEED->bdays[i];
            if (b->in > 1) continue;
            char t[96];
            if (!strcmp(b->label, "birthday")) {
                if (b->turns > 0) snprintf(t, sizeof t, "%s turns %d %s", b->name, b->turns, b->in ? "tomorrow" : "today");
                else snprintf(t, sizeof t, "%s's birthday %s", b->name, b->in ? "tomorrow" : "today");
            } else {
                snprintf(t, sizeof t, "%s · %s %s", b->name, b->label, b->in ? "tomorrow" : "today");
            }
            lv_obj_t *l = label(agenda_list, font_text(26), SUNNY, t);
            one_line(l, font_text(26));
            lv_obj_set_width(l, lv_pct(100));
        }
        if (FEED->has_today) {
            bool headed = FEED->ntoday == 0;
            if (headed) head(agenda_list, "TODAY");
            if (FEED->ntoday == 0) {
                char t[160];
                if (FEED->has_next) {
                    char d[40];
                    if (FEED->next.all_day) {
                        fmt_day_head(d, sizeof d, FEED->next.day);
                    } else {
                        char dd[11];
                        struct tm tm;
                        localtime_r(&FEED->next.s, &tm);
                        strftime(dd, sizeof dd, "%Y-%m-%d", &tm);
                        fmt_day_head(d, sizeof d, dd);
                    }
                    snprintf(t, sizeof t, "Nothing more today · next: %s, %s", FEED->next.title, d);
                } else {
                    strlcpy(t, "Nothing more today", sizeof t);
                }
                muted_line(agenda_list, t);
            }
            /* a birthday already said in the line above is not listed again as the calendar's all-day event */
            bool said = false;
            for (int i = 0; i < FEED->nbdays; i++) said |= FEED->bdays[i].in == 0;
            for (int i = 0; i < FEED->ntoday; i++) {
                const wall_event_t *ev = &FEED->today[i];
                if (said && ev->all_day && (strstr(ev->title, "birthday") || strstr(ev->title, "Birthday"))) continue;
                if (!headed) head(agenda_list, "TODAY");
                headed = true;
                event_row(agenda_list, ev, true);
            }
            if (FEED->today_more) {
                char t[24];
                snprintf(t, sizeof t, "+%d more", FEED->today_more);
                muted_line(agenda_list, t);
            }
        }
        /* the next two days with something on */
        int shown = 0;
        for (int d = 0; d < FEED->ndays && shown < 2; d++) {
            if (!FEED->days[d].n) continue;
            char h[40];
            fmt_day_head(h, sizeof h, FEED->days[d].date);
            for (char *p = h; *p; p++) if (*p >= 'a' && *p <= 'z') *p -= 32;
            head(agenda_list, h);
            for (int i = 0; i < FEED->days[d].n && i < 3; i++) event_row(agenda_list, &FEED->days[d].ev[i], true);
            shown++;
        }
        if (!FEED->has_today && !FEED->has_days) muted_line(agenda_list, "No calendar here (ioCalendar)");
    } else {
        if (!FEED->has_days) {
            muted_line(agenda_list, "No calendar here (ioCalendar)");
            return;
        }
        if (!FEED->ndays) muted_line(agenda_list, "Nothing in the coming week");
        for (int d = 0; d < FEED->ndays; d++) {
            char h[40];
            fmt_day_head(h, sizeof h, FEED->days[d].date);
            for (char *p = h; *p; p++) if (*p >= 'a' && *p <= 'z') *p -= 32;
            head(agenda_list, h);
            for (int i = 0; i < FEED->days[d].n; i++) event_row(agenda_list, &FEED->days[d].ev[i], true);
        }
    }
    lv_obj_scroll_to_y(agenda_list, 0, LV_ANIM_OFF);
}

static void on_tab(lv_event_t *e)
{
    week_view = (intptr_t)lv_event_get_user_data(e) == 1;
    draw_agenda();
}

static lv_obj_t *tab(lv_obj_t *parent, const char *text, intptr_t which)
{
    lv_obj_t *b = box(parent);
    lv_obj_add_flag(b, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_set_style_pad_hor(b, P(18), 0);
    lv_obj_set_style_pad_ver(b, P(5), 0);
    lv_obj_set_style_radius(b, P(18), 0);
    lv_obj_set_style_bg_color(b, lv_color_black(), 0);
    label(b, font_bold(22), TEXT, text);
    lv_obj_add_event_cb(b, on_tab, LV_EVENT_CLICKED, (void *)which);
    return b;
}

/* ------------------------------------------------------------------ tasks */

typedef struct {
    char id[24];
} task_job_t;

static void task_call(void *arg)
{
    task_job_t *j = arg;
    char path[80];
    snprintf(path, sizeof path, "/api/wall/tasks/%s/done", j->id);
    api_resp_t r = api_request("POST", path, "{}", 4096, NULL);
    ui_lock();
    if (r.status != 200) {
        for (int i = 0; i < FEED->ntasks; i++) {
            if (!strcmp(FEED->tasks[i].id, j->id)) FEED->tasks[i].done = false;
        }
        ui_toast(r.why[0] ? r.why : "ioTask did not take it");
        ui_wall_feed_changed();
    }
    ui_unlock();
    api_free(&r);
    free(j);
    feed_refresh();
}

static void on_task(lv_event_t *e)
{
    wall_task_t *t = lv_event_get_user_data(e);
    if (t->done) return;
    t->done = true;
    task_job_t *j = calloc(1, sizeof *j);
    if (!j) return;
    strlcpy(j->id, t->id, sizeof j->id);
    feed_run(task_call, j);
    sound_beep(40);
    ui_wall_feed_changed();
}

static void draw_tasks(void)
{
    lv_obj_clean(tasks_box);
    if (!FEED->has_tasks) {
        lv_obj_add_flag(tasks_box, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_remove_flag(tasks_box, LV_OBJ_FLAG_HIDDEN);
    char h[48];
    int open = 0;
    for (int i = 0; i < FEED->ntasks; i++) open += !FEED->tasks[i].done;
    if (FEED->overdue) snprintf(h, sizeof h, "TASKS TODAY · %d LATE", FEED->overdue);
    else strlcpy(h, "TASKS TODAY", sizeof h);
    head(tasks_box, h);
    if (!FEED->ntasks) {
        muted_line(tasks_box, "Nothing due today");
        return;
    }
    int n = 0;
    for (int i = 0; i < FEED->ntasks && n < 4; i++) {
        wall_task_t *t = &FEED->tasks[i];
        lv_obj_t *r = row(tasks_box, 14);
        lv_obj_set_width(r, lv_pct(100));
        lv_obj_add_flag(r, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_set_style_pad_ver(r, P(4), 0);
        lv_obj_add_event_cb(r, on_task, LV_EVENT_CLICKED, t);
        lv_obj_t *c = box(r);
        lv_obj_set_size(c, P(34), P(34));
        lv_obj_set_style_radius(c, LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_border_width(c, P(3), 0);
        lv_obj_set_style_border_color(c, t->has_color ? color_hex(t->color) : DIM, 0);
        if (t->done) {
            lv_obj_set_style_bg_opa(c, LV_OPA_COVER, 0);
            lv_obj_set_style_bg_color(c, t->has_color ? color_hex(t->color) : DIM, 0);
            lv_obj_t *ok = label(c, font_symbols(20), lv_color_black(), LV_SYMBOL_OK);
            lv_obj_center(ok);
        }
        lv_obj_t *l = label(r, font_text(28), t->done ? DIM : (t->late ? lv_color_hex(0xffb4a8) : TEXT), t->title);
        lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
        lv_obj_set_flex_grow(l, 1);
        if (t->done) lv_obj_set_style_text_decor(l, LV_TEXT_DECOR_STRIKETHROUGH, 0);
        n++;
    }
    int more = FEED->ntasks - n + FEED->tasks_more;
    if (more > 0) {
        char m[24];
        snprintf(m, sizeof m, "+%d more", more);
        muted_line(tasks_box, m);
    }
    (void)open;
}

/* ------------------------------------------------------------------ Home Assistant */

typedef struct {
    char id[64];
    char tap[8];
} ha_job_t;

static void ha_call(void *arg)
{
    ha_job_t *j = arg;
    char path[112];
    snprintf(path, sizeof path, "/api/ha/%s/%s", j->id, j->tap);
    api_resp_t r = api_request("POST", path, "{}", 8192, NULL);
    if (r.status != 200) {
        ui_lock();
        ui_toast(r.why[0] ? r.why : "Home Assistant did not take it");
        ui_unlock();
    }
    api_free(&r);
    free(j);
    vTaskDelay(pdMS_TO_TICKS(800));
    feed_refresh();
}

static void on_ha(lv_event_t *e)
{
    wall_ha_t *a = lv_event_get_user_data(e);
    if (!a->tap[0]) {
        ui_toast(FEED->can_home ? "Home Assistant: this one is not switched from the start page" : "Switching takes an editor's account");
        return;
    }
    ha_job_t *j = calloc(1, sizeof *j);
    if (!j) return;
    strlcpy(j->id, a->id, sizeof j->id);
    strlcpy(j->tap, a->tap, sizeof j->tap);
    if (!strcmp(a->tap, "toggle") && a->on >= 0) {
        a->on = !a->on;  /* at once on screen; the feed says what it really is */
        strlcpy(a->text, a->on ? "On" : "Off", sizeof a->text);
        ui_wall_feed_changed();
    }
    sound_beep(30);
    feed_run(ha_call, j);
}

static void draw_ha(void)
{
    lv_obj_clean(ha_box);
    if (!FEED->has_home || (!FEED->nha && !FEED->nalerts)) {
        lv_obj_add_flag(ha_box, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_remove_flag(ha_box, LV_OBJ_FLAG_HIDDEN);
    for (int i = 0; i < FEED->nalerts; i++) {
        lv_obj_t *l = label(ha_box, font_bold(26), lv_color_hex(0xffb4a8), "");
        lv_label_set_text_fmt(l, LV_SYMBOL_WARNING "  %s", FEED->alerts[i]);
        lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
        lv_obj_set_width(l, P(540));
    }
    for (int i = 0; i < FEED->nha && i < 6; i++) {
        wall_ha_t *a = &FEED->ha[i];
        lv_obj_t *b = column(ha_box, 2);
        lv_obj_set_size(b, P(172), P(84));
        lv_obj_add_flag(b, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_set_style_pad_all(b, P(12), 0);
        lv_obj_set_style_radius(b, P(18), 0);
        lv_obj_set_style_bg_color(b, a->on == 1 ? SUNNY : lv_color_black(), 0);
        lv_obj_set_style_bg_opa(b, a->on == 1 ? LV_OPA_80 : LV_OPA_40, 0);
        lv_obj_set_style_bg_opa(b, LV_OPA_COVER, LV_STATE_PRESSED);
        lv_color_t fg = a->on == 1 ? lv_color_black() : TEXT;
        lv_obj_t *n = label(b, font_text(22), fg, a->name);
        lv_label_set_long_mode(n, LV_LABEL_LONG_DOT);
        lv_obj_set_width(n, lv_pct(100));
        lv_obj_t *s = label(b, font_bold(28), fg, a->text);
        lv_label_set_long_mode(s, LV_LABEL_LONG_DOT);
        lv_obj_set_width(s, lv_pct(100));
        lv_obj_add_event_cb(b, on_ha, LV_EVENT_CLICKED, a);
    }
}

/* ------------------------------------------------------------------ the weather */

static void draw_weather(void)
{
    if (!FEED->has_weather) {
        lv_obj_add_flag(wx_box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(hours_box, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_remove_flag(wx_box, LV_OBJ_FLAG_HIDDEN);
    icon_kind_t k = icon_for_accuweather(FEED->wicon, FEED->wday);
    lv_image_set_src(wx_icon, icons_big[k]);
    icon_fit(wx_icon, 112, 112);
    lv_obj_set_style_image_recolor(wx_icon, k == ICON_MOON || k == ICON_PARTLY_NIGHT ? lv_color_hex(0xe8ecff) : SUNNY, 0);
    char t[16];
    if (FEED->has_temp) temp_text(t, sizeof t, FEED->temp);
    else strlcpy(t, "–", sizeof t);
    lv_label_set_text(wx_temp, t);
    lv_label_set_text(wx_text, FEED->wtext);
    char rain[64] = "", at[16];
    if (FEED->rain_mode == 1) { fmt_hour(at, sizeof at, FEED->rain_from); snprintf(rain, sizeof rain, "%s from %s", FEED->rain_what, at); }
    else if (FEED->rain_mode == 2) { fmt_hour(at, sizeof at, FEED->rain_until); snprintf(rain, sizeof rain, "%s until %s", FEED->rain_what, at); }
    else if (FEED->rain_mode == 3) snprintf(rain, sizeof rain, "%s for hours", FEED->rain_what);
    lv_label_set_text(wx_rain, rain);
    if (rain[0]) lv_obj_remove_flag(wx_rain, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_add_flag(wx_rain, LV_OBJ_FLAG_HIDDEN);

    lv_obj_clean(wx_days);
    for (int i = 1; i < FEED->nwdays && i < 5; i++) {
        const wall_wday_t *d = &FEED->wdays[i];
        lv_obj_t *c = column(wx_days, 2);
        lv_obj_set_width(c, P(104));
        lv_obj_set_flex_align(c, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        int y, m, dd;
        char wd[8] = "";
        if (sscanf(d->date, "%d-%d-%d", &y, &m, &dd) == 3) {
            struct tm a = {.tm_year = y - 1900, .tm_mon = m - 1, .tm_mday = dd, .tm_hour = 12};
            mktime(&a);
            static const char *W[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
            strlcpy(wd, W[a.tm_wday], sizeof wd);
        }
        label(c, font_text(24), DIM, wd);
        weather_icon(c, d->icon, true, false);
        char mm[24];
        if (d->has_temp) snprintf(mm, sizeof mm, "%d° %d°", d->max, d->min);
        else mm[0] = 0;
        label(c, font_text(24), TEXT, mm);
    }

    lv_obj_clean(hours_box);
    if (!FEED->nhours) {
        lv_obj_add_flag(hours_box, LV_OBJ_FLAG_HIDDEN);
        return;
    }
    lv_obj_remove_flag(hours_box, LV_OBJ_FLAG_HIDDEN);
    /* a low strip: the hour, a small icon, the temperature; the chance of rain only in an hour that has one */
    for (int i = 0; i < FEED->nhours && i < 8; i++) {
        const wall_hour_t *hh = &FEED->hours[i];
        lv_obj_t *c = column(hours_box, 0);
        lv_obj_set_size(c, P(60), LV_SIZE_CONTENT);
        lv_obj_set_flex_align(c, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
        lv_obj_set_style_pad_ver(c, 2, 0);
        lv_obj_set_style_radius(c, P(10), 0);
        if (hh->wet) {
            lv_obj_set_style_bg_opa(c, LV_OPA_30, 0);
            lv_obj_set_style_bg_color(c, lv_color_hex(0x5096ff), 0);
        }
        char at[12];
        if (hh->wet && hh->rain) snprintf(at, sizeof at, "%d%%", hh->rain);
        else fmt_hour(at, sizeof at, hh->t);
        label(c, font_text(16), hh->wet && hh->rain ? RAINY : DIM, at);
        lv_obj_t *i2 = weather_icon(c, hh->icon, true, false);
        icon_fit(i2, 52, 26);
        char tt[12] = "";
        if (hh->has_temp) temp_text(tt, sizeof tt, hh->temp);
        label(c, font_text(20), TEXT, tt);
    }
}

/* ------------------------------------------------------------------ the clock and the chips */

static void open_timers(lv_event_t *e) { ui_open_timers(); }
static void open_alarms(lv_event_t *e) { ui_open_alarms(); }

static void draw_chips(void)
{
    lv_obj_clean(chips);
    int64_t now = esp_timer_get_time() / 1000;
    for (int i = 0; i < TIMERS; i++) {
        if (!TIMER[i].on) continue;
        int64_t left = (TIMER[i].ends_ms - now + 999) / 1000;
        if (left < 0) left = 0;
        lv_obj_t *c = row(chips, 8);
        lv_obj_add_flag(c, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_set_style_pad_hor(c, P(14), 0);
        lv_obj_set_style_pad_ver(c, P(4), 0);
        lv_obj_set_style_radius(c, P(24), 0);
        lv_obj_set_style_bg_color(c, lv_color_black(), 0);
        lv_obj_set_style_bg_opa(c, LV_OPA_50, 0);
        lv_obj_add_event_cb(c, open_timers, LV_EVENT_CLICKED, NULL);
        label(c, font_symbols(20), SUNNY, LV_SYMBOL_LOOP);
        lv_obj_t *l = label(c, font_bold(26), TEXT, "");
        if (left >= 3600) lv_label_set_text_fmt(l, "%d:%02d:%02d", (int)(left / 3600), (int)(left / 60 % 60), (int)(left % 60));
        else lv_label_set_text_fmt(l, "%d:%02d", (int)(left / 60), (int)(left % 60));
        if (TIMER[i].label[0]) label(c, font_text(22), DIM, TIMER[i].label);
    }
    int pct;
    if (power_on_battery(&pct)) {
        /* running on the battery: how full it is; red when it is nearly empty */
        lv_obj_t *c = row(chips, 8);
        lv_obj_set_style_pad_hor(c, P(14), 0);
        lv_obj_set_style_pad_ver(c, P(4), 0);
        lv_obj_set_style_radius(c, P(24), 0);
        lv_obj_set_style_bg_color(c, lv_color_black(), 0);
        lv_obj_set_style_bg_opa(c, LV_OPA_40, 0);
        lv_color_t col = pct <= 15 ? lv_color_hex(0xff6b5e) : TEXT;
        if (power_charging()) label(c, font_symbols(20), col, LV_SYMBOL_CHARGE);
        label(c, font_symbols(20), col, pct > 80 ? LV_SYMBOL_BATTERY_FULL : pct > 55 ? LV_SYMBOL_BATTERY_3 : pct > 30 ? LV_SYMBOL_BATTERY_2 : pct > 10 ? LV_SYMBOL_BATTERY_1 : LV_SYMBOL_BATTERY_EMPTY);
        lv_label_set_text_fmt(label(c, font_text(22), col, ""), "%d%%", pct);
    }
    time_t next = alarm_next();
    if (next) {
        lv_obj_t *c = row(chips, 8);
        lv_obj_add_flag(c, LV_OBJ_FLAG_CLICKABLE);
        lv_obj_set_style_pad_hor(c, P(14), 0);
        lv_obj_set_style_pad_ver(c, P(4), 0);
        lv_obj_set_style_radius(c, P(24), 0);
        lv_obj_set_style_bg_color(c, lv_color_black(), 0);
        lv_obj_set_style_bg_opa(c, LV_OPA_40, 0);
        lv_obj_add_event_cb(c, open_alarms, LV_EVENT_CLICKED, NULL);
        label(c, font_symbols(20), TEXT, LV_SYMBOL_BELL);
        char at[16];
        fmt_time(at, sizeof at, next);
        time_t t = time(NULL);
        char txt[40];
        if (next - t < 86400) snprintf(txt, sizeof txt, "%s", at);
        else {
            struct tm tm;
            localtime_r(&next, &tm);
            static const char *W[] = {"Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"};
            snprintf(txt, sizeof txt, "%s %s", W[tm.tm_wday], at);
        }
        label(c, font_text(22), TEXT, txt);
    }
}

void ui_wall_tick(void)
{
    if (!scr || lv_screen_active() != scr) return;
    ui_views_tick();
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    if (t.tm_min != shown_min) {
        shown_min = t.tm_min;
        if (!clock_is_set()) {
            lv_label_set_text(clock_lbl, "--:--");
            lv_label_set_text(ampm_lbl, "");
        } else if (S.clock24) {
            lv_label_set_text_fmt(clock_lbl, "%d:%02d", t.tm_hour, t.tm_min);
            lv_label_set_text(ampm_lbl, "");
        } else {
            int h = t.tm_hour % 12;
            lv_label_set_text_fmt(clock_lbl, "%d:%02d", h ? h : 12, t.tm_min);
            lv_label_set_text(ampm_lbl, t.tm_hour < 12 ? "AM" : "PM");
        }
        if (t.tm_mday != shown_mday && clock_is_set()) {
            shown_mday = t.tm_mday;
            static const char *W[] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};
            static const char *M[] = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"};
            lv_label_set_text_fmt(date_lbl, "%s, %s %d", W[t.tm_wday], M[t.tm_mon], t.tm_mday);
        }
        if (t.tm_min % 10 == 0) paint_sky();
    }
    bool any = alarm_next() != 0 || power_on_battery(NULL);
    for (int i = 0; i < TIMERS; i++) any |= TIMER[i].on;
    static bool had;
    if (any || had) draw_chips();
    had = any;
    /* the status: old news, or no network */
    char st[140] = "";
    if (net_state() != NET_UP) snprintf(st, sizeof st, LV_SYMBOL_WIFI "  %s", net_why()[0] ? net_why() : "No Wi-Fi yet");
    else if (FEED->why[0] && FEED->ok) {
        char at[16];
        fmt_time(at, sizeof at, FEED->fetched);
        snprintf(st, sizeof st, LV_SYMBOL_WARNING "  %s (as of %s)", FEED->why, at);
    }
    if (st[0]) {
        lv_label_set_text(status_pill, st);
        lv_obj_remove_flag(status_pill, LV_OBJ_FLAG_HIDDEN);
    } else {
        lv_obj_add_flag(status_pill, LV_OBJ_FLAG_HIDDEN);
    }
}

/* ------------------------------------------------------------------ the photo */

static void fade_cb(void *o, int32_t v)
{
    lv_obj_set_style_opa(o, (lv_opa_t)v, 0);
}

static void fade_done(lv_anim_t *a)
{
    int other = img_top == 0 ? 1 : 0;
    lv_obj_add_flag(img[other], LV_OBJ_FLAG_HIDDEN);
}

/* The shades over the photo, as dark as the photo is bright: white text on a dark photo needs little, on snow, sand
 * or a white sky a lot. Three of them: one over the whole photo (none on a dark one), one behind the clock and the
 * weather, one behind the agenda and the tasks. */
enum { SH_ALL, SH_TOP, SH_BOTTOM, SH_N };
static const int SH_PLAIN[SH_N] = {0, 140, 190};   /* no photo: the sky, or black */
static const int SH_VIEW[SH_N] = {205, 0, 0};      /* under a view: the photo far back, evenly */
static int sh_now[SH_N] = {0, 140, 190}, sh_from[SH_N], sh_to[SH_N];

static void shades_set(const int v[SH_N])
{
    lv_obj_set_style_bg_opa(dim, (lv_opa_t)v[SH_ALL], 0);
    lv_obj_set_style_bg_main_opa(shade_top, (lv_opa_t)v[SH_TOP], 0);
    lv_obj_set_style_bg_grad_opa(shade_bottom, (lv_opa_t)v[SH_BOTTOM], 0);
    memcpy(sh_now, v, sizeof sh_now);
}

static void shades_cb(void *o, int32_t t)
{
    int v[SH_N];
    for (int i = 0; i < SH_N; i++) v[i] = sh_from[i] + (sh_to[i] - sh_from[i]) * t / 256;
    shades_set(v);
}

static void shades_go(const int to[SH_N])
{
    memcpy(sh_from, sh_now, sizeof sh_from);
    memcpy(sh_to, to, sizeof sh_to);
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, dim);
    lv_anim_set_exec_cb(&a, shades_cb);
    lv_anim_set_values(&a, 0, 256);
    lv_anim_set_duration(&a, 900);
    lv_anim_start(&a);
}

/* How bright rows y0 to y1 of a photo (RGB565) are, 0 to 255: its mean brightness, pulled up by the share of it
 * that is bright enough to wash white text out, so a photo half snow and half forest counts as bright. */
static int brightness(const lv_image_dsc_t *im, int y0, int y1)
{
    int w = im->header.w, h = im->header.h;
    if (y0 < 0) y0 = 0;
    if (y1 > h) y1 = h;
    uint32_t sum = 0, bright = 0, n = 0;
    for (int y = y0; y < y1; y += 6) {
        const uint16_t *row = (const uint16_t *)(im->data + (size_t)y * im->header.stride);
        for (int x = 0; x < w; x += 6) {
            uint16_t p = row[x];
            int l = (((p >> 11) & 31) * 8 * 3 + ((p >> 5) & 63) * 4 * 6 + (p & 31) * 8) / 10;
            sum += l;
            if (l > 160) bright++;
            n++;
        }
    }
    if (!n) return 0;
    int mean = sum / n, share = bright * 255 / n;
    return mean > share ? mean : (mean + share) / 2;
}

static int between(int v, int lo, int hi) { return v < lo ? lo : v > hi ? hi : v; }

static void shades_for(const lv_image_dsc_t *im)
{
    if (viewing) {
        shades_go(SH_VIEW);
        return;
    }
    if (!im) {
        shades_go(SH_PLAIN);
        return;
    }
    int h = im->header.h;
    int all = brightness(im, 0, h), top = brightness(im, 0, h * 45 / 100), bottom = brightness(im, h * 38 / 100, h);
    int to[SH_N] = {
        between((all - 70) * 9 / 10, 0, 110),
        between(140 + (top - 70) * 8 / 10, 140, 225),
        between(190 + (bottom - 70) * 5 / 10, 190, 240),
    };
    shades_go(to);
}

void ui_wall_photo(const lv_image_dsc_t *im, const char *cap)
{
    if (!scr) return;
    if (!im) {
        shades_for(NULL);
        lv_obj_add_flag(img[0], LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(img[1], LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text(caption, "");
        img_top = -1;
        return;
    }
    int next = img_top == 0 ? 1 : 0;
    lv_image_set_src(img[next], im);
    lv_obj_set_style_opa(img[next], LV_OPA_TRANSP, 0);
    lv_obj_remove_flag(img[next], LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_to_index(img[next], 2);  /* above the other photo, under the shades */
    img_top = next;
    shades_for(im);
    lv_anim_t a;
    lv_anim_init(&a);
    lv_anim_set_var(&a, img[next]);
    lv_anim_set_exec_cb(&a, fade_cb);
    lv_anim_set_values(&a, LV_OPA_TRANSP, LV_OPA_COVER);
    lv_anim_set_duration(&a, 900);
    lv_anim_set_completed_cb(&a, fade_done);
    lv_anim_start(&a);
    lv_label_set_text(caption, cap ? cap : "");
}

/* ------------------------------------------------------------------ the whole */

void ui_wall_viewing(bool on)
{
    if (!scr) return;
    viewing = on;
    lv_obj_t *parts[] = {top_left, wx_box, agenda, right, caption};
    for (size_t i = 0; i < sizeof parts / sizeof parts[0]; i++) {
        if (on) lv_obj_add_flag(parts[i], LV_OBJ_FLAG_HIDDEN);
        else lv_obj_remove_flag(parts[i], LV_OBJ_FLAG_HIDDEN);
    }
    shades_for(img_top >= 0 ? lv_image_get_src(img[img_top]) : NULL);
    if (!on) ui_wall_feed_changed();
}

void ui_wall_feed_changed(void)
{
    if (!scr) return;
    paint_sky();
    draw_weather();
    draw_agenda();
    draw_tasks();
    draw_ha();
    bool none = !FEED->has_tasks && !(FEED->has_home && (FEED->nha || FEED->nalerts)) && !FEED->nhours;
    if (none || viewing) lv_obj_add_flag(right, LV_OBJ_FLAG_HIDDEN);
    else lv_obj_remove_flag(right, LV_OBJ_FLAG_HIDDEN);
    ui_wall_tick();
}

static void build(void)
{
    scr = lv_obj_create(NULL);
    lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(scr, lv_color_black(), 0);
    lv_obj_add_event_cb(scr, on_background, LV_EVENT_SHORT_CLICKED, NULL);
    lv_obj_add_event_cb(scr, on_swipe, LV_EVENT_GESTURE, NULL);

    sky = box(scr);
    lv_obj_set_size(sky, WALL_W, WALL_H);
    lv_obj_set_style_bg_opa(sky, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_grad_dir(sky, LV_GRAD_DIR_VER, 0);
    for (int i = 0; i < 2; i++) {
        img[i] = lv_image_create(scr);
        lv_obj_set_size(img[i], WALL_W, WALL_H);
        lv_obj_add_flag(img[i], LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(img[i], LV_OBJ_FLAG_CLICKABLE);
    }
    dim = box(scr);
    lv_obj_set_size(dim, WALL_W, WALL_H);
    lv_obj_set_style_bg_color(dim, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(dim, LV_OPA_TRANSP, 0);
    shade_top = box(scr);
    lv_obj_set_size(shade_top, WALL_W, P(320));
    lv_obj_set_style_bg_color(shade_top, lv_color_black(), 0);
    lv_obj_set_style_bg_grad_color(shade_top, lv_color_black(), 0);
    lv_obj_set_style_bg_grad_dir(shade_top, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(shade_top, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_main_opa(shade_top, 140, 0);
    lv_obj_set_style_bg_grad_opa(shade_top, 0, 0);
    shade_bottom = box(scr);
    lv_obj_set_size(shade_bottom, WALL_W, P(500));   /* from a little above the agenda */
    lv_obj_align(shade_bottom, LV_ALIGN_BOTTOM_MID, 0, 0);
    lv_obj_set_style_bg_color(shade_bottom, lv_color_black(), 0);
    lv_obj_set_style_bg_grad_color(shade_bottom, lv_color_black(), 0);
    lv_obj_set_style_bg_grad_dir(shade_bottom, LV_GRAD_DIR_VER, 0);
    lv_obj_set_style_bg_opa(shade_bottom, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_main_opa(shade_bottom, 0, 0);
    lv_obj_set_style_bg_grad_opa(shade_bottom, 190, 0);
    lv_obj_set_style_bg_grad_stop(shade_bottom, 90, 0);   /* at its darkest from the agenda's third row down */
    shades_set(SH_PLAIN);

    /* the clock, the date, the chips: top left */
    lv_obj_t *tl = top_left = column(scr, 0);
    lv_obj_set_pos(tl, P(48), P(20));
    lv_obj_t *cr = row(tl, 14);
    lv_obj_set_flex_align(cr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
    clock_lbl = label(cr, font_light(150), TEXT, "--:--");
    lv_obj_set_style_text_letter_space(clock_lbl, -P(3), 0);
    ampm_lbl = label(cr, font_light(46), TEXT, "");
    lv_obj_set_style_pad_bottom(ampm_lbl, P(22), 0);
    /* the date, and beside it the timers running and the next alarm */
    lv_obj_t *dr = row(tl, 18);
    date_lbl = label(dr, font_text(36), TEXT, "");
    chips = row(dr, 10);

    /* the weather: top right */
    wx_box = column(scr, 10);
    lv_obj_set_flex_align(wx_box, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
    lv_obj_align(wx_box, LV_ALIGN_TOP_RIGHT, -P(44), P(34));
    lv_obj_t *now = row(wx_box, 18);
    wx_icon = lv_image_create(now);
    lv_obj_set_style_image_recolor_opa(wx_icon, LV_OPA_COVER, 0);
    lv_obj_t *nc = column(now, 0);
    wx_temp = label(nc, font_light(92), TEXT, "");
    wx_text = label(nc, font_text(28), TEXT, "");
    wx_rain = label(nc, font_text(26), RAINY, "");
    wx_days = row(wx_box, 4);

    /* the agenda: bottom left */
    agenda = column(scr, 6);
    lv_obj_set_size(agenda, P(660), WALL_H - P(280) - P(20));   /* down to the screen's edge, whatever its height */
    lv_obj_set_pos(agenda, P(40), P(280));
    lv_obj_add_flag(agenda, LV_OBJ_FLAG_CLICKABLE);
    lv_obj_t *tabs = row(agenda, 6);
    tab_today = tab(tabs, "Today", 0);
    tab_week = tab(tabs, "Week", 1);
    agenda_list = column(agenda, 2);
    lv_obj_set_width(agenda_list, lv_pct(100));
    lv_obj_set_flex_grow(agenda_list, 1);
    lv_obj_add_flag(agenda_list, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_scroll_dir(agenda_list, LV_DIR_VER);
    lv_obj_set_scrollbar_mode(agenda_list, LV_SCROLLBAR_MODE_OFF);
    lv_obj_add_flag(agenda_list, LV_OBJ_FLAG_CLICKABLE);

    /* tasks, Home Assistant, the next hours: bottom right */
    right = column(scr, 14);
    lv_obj_set_width(right, P(548));
    lv_obj_set_flex_align(right, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
    lv_obj_align(right, LV_ALIGN_BOTTOM_RIGHT, -P(40), -P(28));
    tasks_box = column(right, 2);
    lv_obj_set_width(tasks_box, lv_pct(100));
    ha_box = row(right, 10);
    lv_obj_set_width(ha_box, lv_pct(100));
    lv_obj_set_flex_flow(ha_box, LV_FLEX_FLOW_ROW_WRAP);
    lv_obj_set_flex_align(ha_box, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
    lv_obj_set_style_pad_row(ha_box, P(10), 0);
    hours_box = row(right, 2);

    caption = label(scr, font_text(22), DIM, "");
    lv_obj_align(caption, LV_ALIGN_BOTTOM_RIGHT, -P(16), -P(4));

    ui_views_init(scr);   /* over the wall's own parts, under the status and the bar */

    status_pill = label(scr, font_text(24), TEXT, "");
    lv_obj_set_style_bg_color(status_pill, lv_color_hex(0x40140f), 0);
    lv_obj_set_style_bg_opa(status_pill, LV_OPA_80, 0);
    lv_obj_set_style_pad_hor(status_pill, P(18), 0);
    lv_obj_set_style_pad_ver(status_pill, P(8), 0);
    lv_obj_set_style_radius(status_pill, P(20), 0);
    lv_obj_set_style_max_width(status_pill, P(760), 0);
    lv_label_set_long_mode(status_pill, LV_LABEL_LONG_DOT);
    lv_obj_align(status_pill, LV_ALIGN_TOP_MID, 0, P(8));
    lv_obj_add_flag(status_pill, LV_OBJ_FLAG_HIDDEN);

    bar = row(scr, 14);
    lv_obj_set_style_pad_all(bar, P(14), 0);
    lv_obj_set_style_radius(bar, P(30), 0);
    lv_obj_set_style_bg_color(bar, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(bar, LV_OPA_50, 0);
    bar_button(LV_SYMBOL_PLUS, "Add", 0);
    bar_button(LV_SYMBOL_LOOP, "Timer", 1);
    bar_button(LV_SYMBOL_BELL, "Alarms", 2);
    fav_btn = bar_button(LV_SYMBOL_IMAGE, "Favorite", 3);
    bar_button(LV_SYMBOL_REFRESH, "Refresh", 4);
    bar_button(LV_SYMBOL_SETTINGS, "Settings", 5);
    lv_obj_align(bar, LV_ALIGN_CENTER, 0, 0);
    lv_obj_add_flag(bar, LV_OBJ_FLAG_HIDDEN);
}

void ui_show_wall(void)
{
    if (!scr) build();
    ui_views_reset();
    shown_min = shown_mday = -1;
    lv_screen_load(scr);
    ui_wall_feed_changed();
    feed_refresh();
}
