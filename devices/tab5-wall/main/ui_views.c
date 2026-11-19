/* The views beside the wall, a swipe away: the calendar's week, today's tasks, money, health, the papers to renew and
 * the weather. Each is one of the start page's TRMNL screens (/api/trmnl/<screen>: the same data, already worded, as
 * the person the device is signed in as), drawn here over the wall's photo, darkened. Which ones there are is the
 * start page's answer (/api/trmnl: the apps this person may see); which of those are swiped to is chosen in Settings.
 *
 * A swipe to the left goes to the next view, to the right to the one before; after the last comes the wall again.
 * A view left alone goes back to the wall by itself. */
#include <stdio.h>
#include <string.h>
#include "cJSON.h"
#include "esp_log.h"
#include "wall.h"
#include "icons.h"

#define TEXT lv_color_white()
#define DIM lv_color_hex(0xc3c7cf)
#define RED lv_color_hex(0xff7a6e)
#define SUNNY lv_color_hex(0xffd36b)
#define RAINY lv_color_hex(0x9fd0ff)

#define BODY_X P(48)
#define BODY_Y P(150)
#define BODY_W (WALL_W - 2 * P(48))
#define BODY_H (WALL_H - P(150) - P(56))
#define BACK_AFTER_MS 180000   /* left alone this long: the wall again */
#define FRESH_S 55             /* a view on screen is asked again this often */

typedef struct {
    const char *key, *name;
    void (*draw)(const cJSON *d);
} kind_t;

static void draw_calendar(const cJSON *d);
static void draw_tasks(const cJSON *d);
static void draw_money(const cJSON *d);
static void draw_health(const cJSON *d);
static void draw_docs(const cJSON *d);
static void draw_weather(const cJSON *d);

static const kind_t KINDS[VIEWS] = {
    {"calendar", "Calendar", draw_calendar}, {"tasks", "Tasks", draw_tasks}, {"money", "Money", draw_money},
    {"health", "Health", draw_health}, {"docs", "Documents", draw_docs}, {"weather", "Weather", draw_weather},
};

static lv_obj_t *layer, *title, *clock_lbl, *date_lbl, *body, *dots;
static int cur = -1;             /* the view on screen; -1: the wall */
static uint32_t avail;           /* the views the start page has for this person, a bit each */
static bool listed;
static time_t listed_at;
static cJSON *data[VIEWS];
static time_t got_at[VIEWS];
static char why[VIEWS][96];
static int shown_min = -1;

/* ------------------------------------------------------------------ small parts */

static lv_obj_t *label(lv_obj_t *parent, const lv_font_t *f, lv_color_t c, const char *text)
{
    lv_obj_t *l = lv_label_create(parent);
    lv_obj_set_style_text_font(l, f, 0);
    lv_obj_set_style_text_color(l, c, 0);
    lv_label_set_text(l, text ? text : "");
    return l;
}

/* nothing here takes a touch: a swipe or a tap on a view reaches the wall's screen, as on the wall itself */
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

/* one line of a given width, cut with "…" when it is too long; grow: takes what is left of its row instead */
static lv_obj_t *line(lv_obj_t *parent, const lv_font_t *f, lv_color_t c, const char *text, int w, bool grow)
{
    lv_obj_t *l = label(parent, f, c, text);
    lv_label_set_long_mode(l, LV_LABEL_LONG_DOT);
    lv_obj_set_height(l, lv_font_get_line_height(f));
    if (grow) {
        lv_obj_set_flex_grow(l, 1);
        lv_obj_set_style_min_width(l, P(60), 0);
    } else {
        lv_obj_set_width(l, w);
    }
    return l;
}

static lv_obj_t *head(lv_obj_t *parent, const char *text)
{
    lv_obj_t *l = label(parent, font_bold(20), DIM, text);
    lv_obj_set_style_text_letter_space(l, 2, 0);
    lv_obj_set_style_pad_bottom(l, P(6), 0);
    return l;
}

static void message(const char *text)
{
    lv_obj_t *l = label(body, font_text(30), DIM, text);
    lv_label_set_long_mode(l, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(l, BODY_W * 3 / 4);
    lv_obj_set_style_text_align(l, LV_TEXT_ALIGN_CENTER, 0);
    lv_obj_align(l, LV_ALIGN_CENTER, 0, -P(40));
}

static const char *str(const cJSON *o, const char *k)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    return cJSON_IsString(v) && v->valuestring ? v->valuestring : "";
}

static int num(const cJSON *o, const char *k)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    return cJSON_IsNumber(v) ? (int)v->valuedouble : 0;
}

static const cJSON *list(const cJSON *o, const char *k)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    return cJSON_IsArray(v) ? v : NULL;
}

static int count(const cJSON *a) { return a ? cJSON_GetArraySize(a) : 0; }

static void more_line(lv_obj_t *parent, int more)
{
    if (more > 0) lv_label_set_text_fmt(label(parent, font_text(22), DIM, ""), "+%d more", more);
}

/* the start page names a weather glyph by its place in its own list (app/trmnl.py: WX) */
static lv_obj_t *glyph(lv_obj_t *parent, int n, bool big)
{
    static const icon_kind_t MAP[] = {ICON_SUN, ICON_MOON, ICON_CLOUD, ICON_PARTLY_DAY, ICON_PARTLY_NIGHT, ICON_RAIN,
                                      ICON_THUNDER, ICON_SNOW, ICON_FOG, ICON_WIND, ICON_SUN};
    icon_kind_t k = n >= 0 && n < (int)(sizeof MAP / sizeof MAP[0]) ? MAP[n] : ICON_CLOUD;
    lv_obj_t *i = lv_image_create(parent);
    lv_image_set_src(i, big ? icons_big[k] : icons_small[k]);
    int px = big ? 112 : 52;
    if (P(px) != px) {
        lv_image_set_scale(i, 256 * P(px) / px);
        lv_obj_set_size(i, P(px), P(px));
        lv_image_set_inner_align(i, LV_IMAGE_ALIGN_CENTER);
    }
    lv_obj_set_style_image_recolor(i, k == ICON_MOON || k == ICON_PARTLY_NIGHT ? lv_color_hex(0xe8ecff) : SUNNY, 0);
    lv_obj_set_style_image_recolor_opa(i, LV_OPA_COVER, 0);
    return i;
}

/* ------------------------------------------------------------------ the calendar: today and the coming days */

static void draw_calendar(const cJSON *d)
{
    const cJSON *days = list(d, "days"), *day, *ev;
    if (!num(d, "count")) {
        message("Nothing on the calendar for the coming days");
        return;
    }
    const lv_font_t *ft = font_text(26), *fh = font_bold(26);
    int rh = lv_font_get_line_height(ft) + P(6), hh = lv_font_get_line_height(fh) + P(6), gap = P(18);
    /* as many events of each day as lets the whole week fit in three columns: a full week shows fewer per day */
    int cap = 6;
    for (; cap > 1; cap--) {
        int col = 0, y = 0, i = 0;
        cJSON_ArrayForEach(day, days) {
            int n = count(list(day, "events"));
            if (!n && i++) continue;
            i++;
            int h = hh + (n > cap ? cap + 1 : n ? n : 1) * rh;
            if (y && y + h > BODY_H) { col++; y = 0; }
            y += h + gap;
        }
        if (col < 3) break;
    }
    lv_obj_t *w = box(body);
    lv_obj_set_size(w, BODY_W, BODY_H);
    lv_obj_set_flex_flow(w, LV_FLEX_FLOW_COLUMN_WRAP);
    lv_obj_set_style_pad_row(w, gap, 0);
    lv_obj_set_style_pad_column(w, P(28), 0);
    int cw = (BODY_W - 2 * P(28)) / 3, i = 0;
    cJSON_ArrayForEach(day, days) {
        const cJSON *evs = list(day, "events");
        int n = count(evs), k = 0;
        if (!n && i++) continue;   /* an empty day is left out, but for today */
        i++;
        lv_obj_t *b = column(w, 0);
        lv_obj_set_width(b, cw);
        lv_obj_t *h = row(b, 12);
        lv_obj_set_height(h, hh);
        label(h, fh, TEXT, str(day, "label"));
        label(h, font_text(22), DIM, str(day, "date"));
        if (!n) line(b, ft, DIM, "Nothing left today", cw, false);
        cJSON_ArrayForEach(ev, evs) {
            if (k++ >= cap) break;
            lv_obj_t *r = row(b, 10);
            lv_obj_set_size(r, cw, rh);
            line(r, font_text(22), DIM, str(ev, "time"), P(98), false);
            char t[160];
            const char *place = str(ev, "place");
            snprintf(t, sizeof t, "%s%s%s", str(ev, "title"), place[0] ? " @ " : "", place);
            line(r, ft, TEXT, t, 0, true);
        }
        more_line(b, n - cap);
    }
}

/* ------------------------------------------------------------------ tasks: what is due today */

static void draw_tasks(const cJSON *d)
{
    const cJSON *tasks = list(d, "tasks"), *t;
    if (!count(tasks)) {
        message("Nothing due today");
        return;
    }
    lv_obj_t *w = box(body);
    lv_obj_set_size(w, BODY_W, BODY_H);
    lv_obj_set_flex_flow(w, LV_FLEX_FLOW_COLUMN_WRAP);
    lv_obj_set_style_pad_row(w, P(8), 0);
    lv_obj_set_style_pad_column(w, P(48), 0);
    const lv_font_t *f = font_text(28);
    /* one wide column while they fit in it, two beside each other from there */
    int rows = count(tasks) + (num(d, "more") > 0);
    int cw = rows * (lv_font_get_line_height(f) + P(8)) <= BODY_H ? BODY_W * 2 / 3 : (BODY_W - P(48)) / 2;
    cJSON_ArrayForEach(t, tasks) {
        bool late = cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(t, "late"));
        lv_obj_t *r = row(w, 16);
        lv_obj_set_width(r, cw);
        lv_obj_t *o = box(r);
        lv_obj_set_size(o, P(24), P(24));
        lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_border_width(o, 2, 0);
        lv_obj_set_style_border_color(o, late ? RED : DIM, 0);
        line(r, f, TEXT, str(t, "title"), 0, true);
        label(r, font_text(22), late ? RED : DIM, str(t, "when"));
    }
    if (num(d, "more") > 0) {
        lv_obj_t *r = row(w, 16);
        lv_obj_set_width(r, cw);
        more_line(r, num(d, "more"));
    }
}

/* ------------------------------------------------------------------ money: the week's bills, accounts running low */

static void draw_money(const cJSON *d)
{
    const cJSON *bills = list(d, "bills"), *low = list(d, "low"), *behind = list(d, "behind"), *x;
    lv_obj_t *w = row(body, 64);
    lv_obj_set_size(w, BODY_W, BODY_H);
    lv_obj_set_flex_align(w, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
    int lw = count(low) || count(behind) ? P(700) : BODY_W;
    lv_obj_t *l = column(w, 6);
    lv_obj_set_width(l, lw);
    head(l, "BILLS THIS WEEK");
    if (!count(bills)) line(l, font_text(28), DIM, "No bills this week", lw, false);
    cJSON_ArrayForEach(x, bills) {
        lv_obj_t *r = row(l, 16);
        lv_obj_set_width(r, lw);
        line(r, font_text(24), DIM, str(x, "day"), P(130), false);
        line(r, font_text(28), TEXT, str(x, "name"), 0, true);
        label(r, font_bold(28), TEXT, str(x, "amount"));
    }
    more_line(l, num(d, "more"));
    if (count(bills) && str(d, "total")[0]) {
        lv_obj_t *rule = box(l);
        lv_obj_set_size(rule, lw, 1);
        lv_obj_set_style_bg_color(rule, DIM, 0);
        lv_obj_set_style_bg_opa(rule, LV_OPA_50, 0);
        lv_obj_t *r = row(l, 16);
        lv_obj_set_width(r, lw);
        line(r, font_text(28), DIM, "In all", 0, true);
        label(r, font_bold(28), TEXT, str(d, "total"));
    }
    if (lw == BODY_W) return;
    lv_obj_t *rc = column(w, 6);
    lv_obj_set_flex_grow(rc, 1);
    if (count(low)) head(rc, "RUNNING LOW");
    cJSON_ArrayForEach(x, low) {
        lv_obj_t *t = label(rc, font_text(26), SUNNY, cJSON_IsString(x) ? x->valuestring : "");
        lv_label_set_long_mode(t, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(t, lv_pct(100));
    }
    if (count(behind)) lv_obj_set_style_pad_top(head(rc, "NOT UP TO DATE"), count(low) ? P(18) : 0, 0);
    cJSON_ArrayForEach(x, behind) {
        lv_obj_t *t = label(rc, font_text(26), TEXT, cJSON_IsString(x) ? x->valuestring : "");
        lv_label_set_long_mode(t, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(t, lv_pct(100));
    }
}

/* ------------------------------------------------------------------ health: steps, rings, sleep, the week */

static void draw_health(const cJSON *d)
{
    static const uint32_t RING[] = {0xff4f79, 0xa4e84a, 0x45d6e0};
    const cJSON *rings = list(d, "rings"), *week = list(d, "week"), *x;
    lv_obj_t *w = row(body, 56);
    lv_obj_set_size(w, BODY_W, BODY_H);
    lv_obj_set_flex_align(w, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);

    lv_obj_t *a = column(w, 0);
    lv_obj_set_width(a, P(380));
    label(a, font_light(92), TEXT, str(d, "steps"));
    label(a, font_text(26), DIM, "steps today");
    if (str(d, "sleep")[0]) {
        lv_obj_set_style_pad_top(head(a, "LAST NIGHT"), P(34), 0);
        label(a, font_text(36), TEXT, str(d, "sleep"));
        if (str(d, "in_bed")[0]) lv_label_set_text_fmt(label(a, font_text(22), DIM, ""), "asleep, %s in bed", str(d, "in_bed"));
    }

    if (count(rings)) {
        lv_obj_t *b = column(w, 22);
        lv_obj_set_width(b, P(330));
        int i = 0;
        cJSON_ArrayForEach(x, rings) {
            lv_color_t c = lv_color_hex(RING[i++ % 3]);
            lv_obj_t *r = row(b, 20);
            lv_obj_t *arc = lv_arc_create(r);
            lv_obj_set_size(arc, P(96), P(96));
            lv_obj_remove_style(arc, NULL, LV_PART_KNOB);
            lv_obj_remove_flag(arc, LV_OBJ_FLAG_CLICKABLE);
            lv_arc_set_rotation(arc, 270);
            lv_arc_set_bg_angles(arc, 0, 360);
            lv_arc_set_range(arc, 0, 100);
            lv_arc_set_value(arc, num(x, "pct"));
            lv_obj_set_style_arc_width(arc, P(13), LV_PART_MAIN);
            lv_obj_set_style_arc_width(arc, P(13), LV_PART_INDICATOR);
            lv_obj_set_style_arc_color(arc, c, LV_PART_MAIN);
            lv_obj_set_style_arc_opa(arc, LV_OPA_30, LV_PART_MAIN);
            lv_obj_set_style_arc_color(arc, c, LV_PART_INDICATOR);
            lv_obj_t *t = column(r, 0);
            label(t, font_text(22), DIM, str(x, "name"));
            const char *goal = str(x, "goal");
            lv_label_set_text_fmt(label(t, font_text(28), TEXT, ""), "%s%s%s %s", str(x, "value"), goal[0] ? " / " : "", goal, str(x, "unit"));
        }
    }

    if (count(week)) {
        lv_obj_t *c = column(w, 0);
        lv_obj_set_flex_grow(c, 1);
        head(c, "STEPS THIS WEEK");
        lv_obj_t *bars = row(c, 0);
        lv_obj_set_width(bars, lv_pct(100));
        lv_obj_set_flex_align(bars, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
        lv_obj_set_style_pad_top(bars, P(12), 0);
        cJSON_ArrayForEach(x, week) {
            lv_obj_t *col = column(bars, 8);
            lv_obj_set_flex_align(col, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
            lv_obj_set_size(col, P(48), P(300));
            int pct = num(x, "pct");
            lv_obj_t *bar = box(col);
            lv_obj_set_size(bar, P(34), pct > 2 ? P(250) * pct / 100 : P(5));
            lv_obj_set_style_radius(bar, P(8), 0);
            lv_obj_set_style_bg_color(bar, lv_color_white(), 0);
            lv_obj_set_style_bg_opa(bar, pct >= 100 ? LV_OPA_COVER : LV_OPA_60, 0);
            label(col, font_text(22), DIM, str(x, "day"));
        }
        if (str(d, "average")[0]) {
            lv_obj_t *l = label(c, font_text(24), DIM, "");
            lv_label_set_text_fmt(l, "%s a day on average", str(d, "average"));
            lv_obj_set_style_pad_top(l, P(16), 0);
        }
    }
}

/* ------------------------------------------------------------------ documents: the papers to renew */

static void draw_docs(const cJSON *d)
{
    const cJSON *items = list(d, "items"), *x;
    if (!count(items)) {
        message("No papers to renew");
        return;
    }
    lv_obj_t *w = column(body, 10);
    lv_obj_set_size(w, BODY_W, BODY_H);
    cJSON_ArrayForEach(x, items) {
        bool gone = cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(x, "expired"));
        lv_obj_t *r = row(w, 20);
        lv_obj_set_width(r, BODY_W);
        line(r, font_text(28), TEXT, str(x, "title"), 0, true);
        const char *who = str(x, "who"), *kind = str(x, "kind");
        char t[120];
        snprintf(t, sizeof t, "%s%s%s", who, who[0] && kind[0] ? " · " : "", kind);
        line(r, font_text(24), DIM, t, P(290), false);
        lv_obj_t *when = line(r, font_text(24), gone ? RED : TEXT, str(x, "when"), P(250), false);
        lv_obj_set_style_text_align(when, LV_TEXT_ALIGN_RIGHT, 0);
        lv_obj_t *on = line(r, font_text(22), DIM, str(x, "date"), P(160), false);
        lv_obj_set_style_text_align(on, LV_TEXT_ALIGN_RIGHT, 0);
    }
    more_line(w, num(d, "more"));
}

/* ------------------------------------------------------------------ the weather: now, the next hours, the days */

static void fact(char *out, size_t n, const char *name, const char *value)
{
    if (!value[0]) return;
    size_t l = strlen(out);
    snprintf(out + l, n - l, "%s%s %s", l ? "  ·  " : "", name, value);
}

static void draw_weather(const cJSON *d)
{
    const cJSON *hours = list(d, "hours"), *days = list(d, "days"), *x;
    lv_obj_t *w = row(body, 56);
    lv_obj_set_size(w, BODY_W, BODY_H);
    lv_obj_set_flex_align(w, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);

    int lw = P(700);
    lv_obj_t *a = column(w, 8);
    lv_obj_set_width(a, lw);
    lv_obj_t *now = row(a, 22);
    lv_obj_set_width(now, lw);
    glyph(now, num(d, "icon"), true);
    label(now, font_light(92), TEXT, str(d, "temp"));
    lv_obj_t *nc = column(now, 2);
    lv_obj_set_flex_grow(nc, 1);
    line(nc, font_text(30), TEXT, str(d, "text"), lv_pct(100), false);
    line(nc, font_text(24), DIM, str(d, "place"), lv_pct(100), false);
    char t[160] = "";
    fact(t, sizeof t, "Feels", str(d, "feels"));
    fact(t, sizeof t, "High", str(d, "hi"));
    fact(t, sizeof t, "Low", str(d, "lo"));
    if (t[0]) line(a, font_text(24), TEXT, t, lw, false);
    t[0] = 0;
    fact(t, sizeof t, "Wind", str(d, "wind"));
    fact(t, sizeof t, "Humidity", str(d, "humidity"));
    fact(t, sizeof t, "UV", str(d, "uv"));
    if (t[0]) line(a, font_text(24), DIM, t, lw, false);
    if (str(d, "note")[0]) line(a, font_text(26), RAINY, str(d, "note"), lw, false);
    if (count(hours)) {
        lv_obj_t *hr = row(a, 0);
        lv_obj_set_width(hr, lw);
        lv_obj_set_style_pad_top(hr, P(22), 0);
        lv_obj_set_flex_align(hr, LV_FLEX_ALIGN_SPACE_BETWEEN, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
        cJSON_ArrayForEach(x, hours) {
            lv_obj_t *c = column(hr, 4);
            lv_obj_set_flex_align(c, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_CENTER, LV_FLEX_ALIGN_CENTER);
            label(c, font_text(20), DIM, str(x, "time"));
            glyph(c, num(x, "icon"), false);
            label(c, font_bold(26), TEXT, str(x, "temp"));
            label(c, font_text(20), RAINY, str(x, "rain"));
        }
    }

    lv_obj_t *b = column(w, 14);
    lv_obj_set_flex_grow(b, 1);
    cJSON_ArrayForEach(x, days) {
        lv_obj_t *r = row(b, 14);
        lv_obj_set_width(r, lv_pct(100));
        line(r, font_text(28), TEXT, str(x, "day"), P(96), false);
        glyph(r, num(x, "icon"), false);
        lv_obj_t *rain = line(r, font_text(22), RAINY, str(x, "rain"), 0, true);
        lv_obj_set_style_min_width(rain, P(40), 0);
        lv_label_set_text_fmt(label(r, font_text(28), TEXT, ""), "%s", str(x, "hi"));
        line(r, font_text(28), DIM, str(x, "lo"), P(60), false);
    }
}

/* ------------------------------------------------------------------ which views, and the one on screen */

/* the views swiped to, in their order: what the start page has, less what Settings turned off */
static int pages(int out[VIEWS])
{
    int n = 0;
    for (int i = 0; i < VIEWS; i++) {
        if ((avail >> i & 1) && !(VIEWS_OFF >> i & 1)) out[n++] = i;
    }
    return n;
}

static void draw_dots(void)
{
    lv_obj_clean(dots);
    int p[VIEWS], n = pages(p);
    for (int i = -1; i < n; i++) {
        lv_obj_t *o = box(dots);
        lv_obj_set_size(o, P(11), P(11));
        lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, 0);
        lv_obj_set_style_bg_color(o, lv_color_white(), 0);
        lv_obj_set_style_bg_opa(o, i >= 0 && p[i] == cur ? LV_OPA_COVER : LV_OPA_30, 0);
    }
}

static void draw_clock(void)
{
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    shown_min = t.tm_min;
    char at[16] = "";
    if (clock_is_set()) fmt_time(at, sizeof at, now);
    lv_label_set_text(clock_lbl, at);
}

static void draw(void)
{
    if (cur < 0) return;
    lv_label_set_text(title, KINDS[cur].name);
    draw_dots();
    draw_clock();
    lv_obj_clean(body);
    const cJSON *d = data[cur];
    lv_label_set_text(date_lbl, d ? str(d, "date_short") : "");
    if (!d) message(why[cur][0] ? why[cur] : "Asking the start page…");
    else if (str(d, "missing")[0]) message(str(d, "missing"));
    else KINDS[cur].draw(d);
}

/* on the taps' task or the feed's: the view's data from the start page, then on screen if it is the one shown */
static void fetch(void *arg)
{
    int k = (int)(intptr_t)arg;
    if (k < 0 || k >= VIEWS || !S.token[0]) return;
    char path[160];
    snprintf(path, sizeof path, "/api/trmnl/%s?clock=%d%s%s", KINDS[k].key, S.clock24 ? 24 : 12, S.tz[0] ? "&tz=" : "", S.tz);
    api_resp_t r = api_request("GET", path, NULL, 32 * 1024, NULL);
    cJSON *j = r.status == 200 ? cJSON_Parse(r.body) : NULL;
    char w[96] = "";
    if (!j) {
        if (r.status == 200) strlcpy(w, "The start page's answer could not be read", sizeof w);
        else if (r.status == 404) strlcpy(w, "The start page does not have this view: it needs an update", sizeof w);
        else if (r.status > 0) snprintf(w, sizeof w, "The start page answered %d", r.status);
        else strlcpy(w, r.why[0] ? r.why : "No answer from the start page", sizeof w);
    }
    api_free(&r);
    ui_lock();
    cJSON *old = NULL;
    if (j) {
        old = data[k];
        data[k] = j;
        got_at[k] = time(NULL);
    }
    strlcpy(why[k], w, sizeof why[k]);
    /* what is on screen stays when the start page does not answer for a moment */
    if (cur == k && (j || !data[k])) draw();
    ui_unlock();
    if (old) cJSON_Delete(old);
}

static void show(int k)
{
    bool was = cur >= 0;
    cur = k;
    if (k < 0) {
        lv_obj_add_flag(layer, LV_OBJ_FLAG_HIDDEN);
        if (was) ui_wall_viewing(false);
        return;
    }
    lv_obj_remove_flag(layer, LV_OBJ_FLAG_HIDDEN);
    if (!was) ui_wall_viewing(true);
    draw();
    if (!data[k] || time(NULL) - got_at[k] > 20) feed_run(fetch, (void *)(intptr_t)k);
}

void ui_views_swipe(int dir)
{
    if (!layer) return;
    int p[VIEWS], n = pages(p);
    if (!n) {
        if (cur >= 0) show(-1);
        else ui_toast(!listed ? "The start page has not said yet which views there are" : avail ? "Every view is turned off in Settings" : "No other views: the start page has none of their apps for you");
        return;
    }
    int at = -1;
    for (int i = 0; i < n; i++) {
        if (p[i] == cur) at = i;
    }
    at += dir > 0 ? 1 : -1;
    if (at >= n) at = -1;        /* past the last: the wall again */
    else if (at < -1) at = n - 1;
    show(at < 0 ? -1 : p[at]);
}

void ui_views_home(void)
{
    if (layer && cur >= 0) show(-1);
}

bool ui_views_showing(void) { return cur >= 0; }

/* a new sign-in or another clock: nothing of what was read before */
void ui_views_reset(void)
{
    ui_views_home();
    for (int i = 0; i < VIEWS; i++) {
        if (data[i]) cJSON_Delete(data[i]);
        data[i] = NULL;
        got_at[i] = 0;
        why[i][0] = 0;
    }
    listed = false;
    avail = 0;
}

void ui_views_tick(void)
{
    if (!layer || cur < 0) return;
    if (lv_display_get_inactive_time(NULL) > BACK_AFTER_MS && !kit_panel_open()) {
        show(-1);
        return;
    }
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    if (t.tm_min != shown_min) draw_clock();
}

const char *ui_views_name(int i) { return i >= 0 && i < VIEWS ? KINDS[i].name : ""; }
bool ui_views_has(int i) { return i >= 0 && i < VIEWS && (avail >> i & 1); }

/* on the feed's task, after each feed: which views there are (now and then), and the one on screen once more */
void views_poll(void)
{
    if (!S.token[0] || net_state() != NET_UP) return;
    time_t now = time(NULL);
    ui_lock();
    bool ask = !listed || now - listed_at > 1800 || now < listed_at;
    int k = cur;
    bool stale = k >= 0 && now - got_at[k] >= FRESH_S;
    ui_unlock();
    if (ask) {
        api_resp_t r = api_request("GET", "/api/trmnl", NULL, 32 * 1024, NULL);
        cJSON *j = r.status == 200 ? cJSON_Parse(r.body) : NULL;
        if (j) {
            uint32_t m = 0;
            const cJSON *s;
            cJSON_ArrayForEach(s, list(j, "screens")) {
                for (int i = 0; i < VIEWS; i++) {
                    if (!strcmp(str(s, "key"), KINDS[i].key)) m |= 1u << i;
                }
            }
            cJSON_Delete(j);
            ui_lock();
            avail = m;
            listed = true;
            listed_at = now;
            if (cur >= 0) draw_dots();
            ui_unlock();
        } else {
            ESP_LOGW(TAG_WALL, "which views there are: %d %s", r.status, r.why);
        }
        api_free(&r);
    }
    if (stale) fetch((void *)(intptr_t)k);
}

/* ------------------------------------------------------------------ the layer the views are drawn on */

void ui_views_init(lv_obj_t *parent)
{
    layer = box(parent);
    lv_obj_set_size(layer, WALL_W, WALL_H);
    lv_obj_add_flag(layer, LV_OBJ_FLAG_HIDDEN);
    title = label(layer, font_light(92), TEXT, "");
    lv_obj_set_pos(title, P(48), P(18));
    lv_obj_t *tr = column(layer, 0);
    lv_obj_set_flex_align(tr, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_END, LV_FLEX_ALIGN_END);
    lv_obj_align(tr, LV_ALIGN_TOP_RIGHT, -P(48), P(36));
    clock_lbl = label(tr, font_light(46), TEXT, "");
    date_lbl = label(tr, font_text(26), DIM, "");
    body = box(layer);
    lv_obj_set_size(body, BODY_W, BODY_H);
    lv_obj_set_pos(body, BODY_X, BODY_Y);
    dots = row(layer, 12);
    lv_obj_align(dots, LV_ALIGN_BOTTOM_MID, 0, -P(20));
    cur = -1;
}
