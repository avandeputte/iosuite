/* What every screen shares: the lock, the fonts (Inter, drawn at any size by Tiny TTF, with LVGL's Montserrat behind
 * it for the symbols), the brightness and the night, the screen's turn, a toast, and times and dates as people read
 * them. */
#include <string.h>
#include "bsp/esp-bsp.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "wall.h"

extern const uint8_t inter_regular_start[] asm("_binary_Inter_Regular_ttf_start");
extern const uint8_t inter_regular_end[] asm("_binary_Inter_Regular_ttf_end");
extern const uint8_t inter_bold_start[] asm("_binary_Inter_SemiBold_ttf_start");
extern const uint8_t inter_bold_end[] asm("_binary_Inter_SemiBold_ttf_end");
extern const uint8_t inter_light_start[] asm("_binary_InterDisplay_Light_ttf_start");
extern const uint8_t inter_light_end[] asm("_binary_InterDisplay_Light_ttf_end");

static lv_display_t *DISP;

void ui_lock(void) { bsp_display_lock(0); }
void ui_unlock(void) { bsp_display_unlock(); }

/* ------------------------------------------------------------------ fonts */

typedef struct {
    int kind, px;
    lv_font_t *f;
} font_slot_t;

static font_slot_t fonts[48];   /* every size the screens ask for: one past the last would be made anew each time */
static int nfonts;

/* px: on this screen already */
static const lv_font_t *symbols_for(int px)
{
    if (px >= 44) return &lv_font_montserrat_48;
    if (px >= 32) return &lv_font_montserrat_36;
    if (px >= 26) return &lv_font_montserrat_28;
    if (px >= 22) return &lv_font_montserrat_24;
    if (px >= 18) return &lv_font_montserrat_20;
    return &lv_font_montserrat_16;
}

const lv_font_t *font_symbols(int px) { return symbols_for(P(px)); }

static const lv_font_t *font_of(int kind, int px)
{
    px = P(px);
    for (int i = 0; i < nfonts; i++) {
        if (fonts[i].kind == kind && fonts[i].px == px) return fonts[i].f;
    }
    const uint8_t *a = kind == 0 ? inter_regular_start : kind == 1 ? inter_bold_start : inter_light_start;
    const uint8_t *b = kind == 0 ? inter_regular_end : kind == 1 ? inter_bold_end : inter_light_end;
    /* the clock's digits are few and large: a small glyph cache does; text gets more */
    lv_font_t *f = lv_tiny_ttf_create_data_ex(a, b - a, px, LV_FONT_KERNING_NONE, px > 100 ? 24 : 256);
    if (!f) {
        ESP_LOGE(TAG_WALL, "font %d at %d px could not be made", kind, px);
        return symbols_for(px);
    }
    f->fallback = symbols_for(px);
    if (nfonts < (int)(sizeof fonts / sizeof fonts[0])) {
        fonts[nfonts++] = (font_slot_t){kind, px, f};
    }
    return f;
}

const lv_font_t *font_text(int px) { return font_of(0, px); }
const lv_font_t *font_bold(int px) { return font_of(1, px); }
const lv_font_t *font_light(int px) { return font_of(2, px); }

lv_color_t color_hex(uint32_t rgb) { return lv_color_hex(rgb); }

/* ------------------------------------------------------------------ times and dates */

static const char *WEEKDAYS[] = {"Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"};
static const char *MONTHS[] = {"January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"};

void fmt_time(char *out, size_t n, time_t t)
{
    struct tm tm;
    localtime_r(&t, &tm);
    if (S.clock24) {
        snprintf(out, n, "%d:%02d", tm.tm_hour, tm.tm_min);
    } else {
        int h = tm.tm_hour % 12;
        snprintf(out, n, "%d:%02d %s", h ? h : 12, tm.tm_min, tm.tm_hour < 12 ? "AM" : "PM");
    }
}

void fmt_hour(char *out, size_t n, time_t t)
{
    struct tm tm;
    localtime_r(&t, &tm);
    if (S.clock24) {
        snprintf(out, n, "%d:00", tm.tm_hour);
    } else {
        int h = tm.tm_hour % 12;
        snprintf(out, n, "%d %s", h ? h : 12, tm.tm_hour < 12 ? "AM" : "PM");
    }
}

static int days_from_today(const char *date)
{
    int y, m, d;
    if (sscanf(date, "%d-%d-%d", &y, &m, &d) != 3) return 99;
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    struct tm a = {.tm_year = y - 1900, .tm_mon = m - 1, .tm_mday = d, .tm_hour = 12};
    struct tm b = {.tm_year = t.tm_year, .tm_mon = t.tm_mon, .tm_mday = t.tm_mday, .tm_hour = 12};
    return (int)((mktime(&a) - mktime(&b) + 43200) / 86400);
}

void fmt_day_head(char *out, size_t n, const char *date)
{
    int in = days_from_today(date);
    int y, m, d;
    if (in == 0) { strlcpy(out, "Today", n); return; }
    if (in == 1) { strlcpy(out, "Tomorrow", n); return; }
    if (sscanf(date, "%d-%d-%d", &y, &m, &d) != 3) { strlcpy(out, date, n); return; }
    struct tm a = {.tm_year = y - 1900, .tm_mon = m - 1, .tm_mday = d, .tm_hour = 12};
    mktime(&a);
    if (in > 1 && in < 7) snprintf(out, n, "%s", WEEKDAYS[a.tm_wday]);
    else snprintf(out, n, "%.3s %d %s", WEEKDAYS[a.tm_wday], d, MONTHS[m - 1]);
}

void fmt_event_when(char *out, size_t n, const wall_event_t *e)
{
    if (e->all_day) {
        strlcpy(out, "All day", n);
    } else {
        fmt_time(out, n, e->s);
    }
}

/* ------------------------------------------------------------------ brightness, the night, the turn */

static int64_t woken_until;  /* a touch at night: full brightness till then (µs) */

static bool night_now(void)
{
    if (S.night_from == S.night_to || !clock_is_set()) return false;
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    int h = t.tm_hour;
    return S.night_from < S.night_to ? (h >= S.night_from && h < S.night_to) : (h >= S.night_from || h < S.night_to);
}

static int bright_shown = -1;

void ui_apply_brightness(void)
{
    int want = S.day_bright;
    if (night_now() && esp_timer_get_time() > woken_until && !alarm_ringing()) {
        want = S.night_bright;
    }
    if (want < 0) want = 0;
    if (want > 100) want = 100;
    if (want == bright_shown) return;
    if (want == 0) {
        bsp_display_backlight_off();
    } else {
        if (bright_shown == 0) bsp_display_backlight_on();
        bsp_display_brightness_set(want);
    }
    bright_shown = want;
}

bool ui_screen_dark(void)
{
    return bright_shown == 0;
}

void ui_wake(void)
{
    woken_until = esp_timer_get_time() + 30LL * 1000000;
    ui_apply_brightness();
}

void ui_apply_rotation(void)
{
    bsp_display_rotate(DISP, BOARD_ROTATION(S.flip));
}

/* ------------------------------------------------------------------ a toast */

static lv_obj_t *toast;
static lv_timer_t *toast_timer;

static void toast_gone(lv_timer_t *t)
{
    if (toast) lv_obj_add_flag(toast, LV_OBJ_FLAG_HIDDEN);
    toast_timer = NULL;
}

void ui_toast(const char *text)
{
    if (!toast) {
        toast = lv_label_create(lv_layer_top());
        lv_obj_set_style_bg_color(toast, lv_color_hex(0x202020), 0);
        lv_obj_set_style_bg_opa(toast, LV_OPA_90, 0);
        lv_obj_set_style_text_color(toast, lv_color_white(), 0);
        lv_obj_set_style_text_font(toast, font_text(26), 0);
        lv_obj_set_style_pad_hor(toast, P(28), 0);
        lv_obj_set_style_pad_ver(toast, P(16), 0);
        lv_obj_set_style_radius(toast, P(32), 0);
        lv_obj_set_style_max_width(toast, P(1000), 0);
        lv_label_set_long_mode(toast, LV_LABEL_LONG_WRAP);
        lv_obj_align(toast, LV_ALIGN_BOTTOM_MID, 0, -P(40));
    }
    lv_label_set_text(toast, text);
    lv_obj_remove_flag(toast, LV_OBJ_FLAG_HIDDEN);
    lv_obj_move_foreground(toast);
    lv_obj_align(toast, LV_ALIGN_BOTTOM_MID, 0, -P(40));
    if (toast_timer) lv_timer_delete(toast_timer);
    toast_timer = lv_timer_create(toast_gone, 3500, NULL);
    lv_timer_set_repeat_count(toast_timer, 1);
}

/* ------------------------------------------------------------------ the second's tick */

static void tick(lv_timer_t *t)
{
    alarm_tick();
    ui_wall_tick();
    static int n;
    if (++n % 10 == 0) {
        ui_apply_brightness();
        power_tick();
    }
}

/* any touch: the night's dim screen lights up; the first touch on a dark screen does nothing else */
static void on_any_press(lv_event_t *e)
{
    bool was_dark = ui_screen_dark();
    ui_wake();
    if (was_dark) {
        lv_indev_t *in = lv_indev_active();
        if (in) lv_indev_wait_release(in);
    }
}

void ui_start(lv_display_t *disp)
{
    DISP = disp;
    ui_apply_rotation();
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_black(), 0);
    lv_indev_t *in = bsp_display_get_input_dev();
    if (in) lv_indev_add_event_cb(in, on_any_press, LV_EVENT_PRESSED, NULL);
    lv_timer_create(tick, 1000, NULL);
    ui_apply_brightness();
    if (S.server[0] && S.token[0]) {
        ui_show_wall();
    } else {
        ui_show_setup();
    }
}

/* ------------------------------------------------------------------ the parts the screens and panels are made of */

lv_obj_t *kit_label(lv_obj_t *p, const lv_font_t *f, lv_color_t c, const char *t)
{
    lv_obj_t *l = lv_label_create(p);
    lv_obj_set_style_text_font(l, f, 0);
    lv_obj_set_style_text_color(l, c, 0);
    lv_label_set_text(l, t ? t : "");
    return l;
}

lv_obj_t *kit_button(lv_obj_t *p, const char *text, lv_event_cb_t cb, void *ud, bool primary)
{
    lv_obj_t *b = lv_button_create(p);
    lv_obj_set_height(b, P(76));
    lv_obj_set_style_pad_hor(b, P(34), 0);
    lv_obj_set_style_radius(b, P(38), 0);
    lv_obj_set_style_shadow_width(b, 0, 0);
    lv_obj_set_style_bg_color(b, primary ? lv_color_hex(0x3f86c9) : lv_color_hex(0x33363d), 0);
    lv_obj_set_style_bg_color(b, primary ? lv_color_hex(0x2c6aa6) : lv_color_hex(0x4a4e57), LV_STATE_PRESSED);
    lv_obj_t *l = kit_label(b, font_bold(28), lv_color_white(), text);
    lv_obj_center(l);
    if (cb) lv_obj_add_event_cb(b, cb, LV_EVENT_CLICKED, ud);
    return b;
}

lv_obj_t *kit_textarea(lv_obj_t *p, const char *placeholder, bool password)
{
    lv_obj_t *ta = lv_textarea_create(p);
    lv_textarea_set_one_line(ta, true);
    lv_textarea_set_password_mode(ta, password);
    lv_textarea_set_placeholder_text(ta, placeholder);
    lv_obj_set_width(ta, lv_pct(100));
    lv_obj_set_style_text_font(ta, font_text(30), 0);
    lv_obj_set_style_bg_color(ta, lv_color_hex(0x1b1d22), 0);
    lv_obj_set_style_text_color(ta, lv_color_white(), 0);
    lv_obj_set_style_border_color(ta, lv_color_hex(0x4a4e57), 0);
    lv_obj_set_style_border_color(ta, lv_color_hex(0x3f86c9), LV_STATE_FOCUSED);
    lv_obj_set_style_radius(ta, P(14), 0);
    lv_obj_set_style_pad_all(ta, P(16), 0);
    lv_obj_set_style_text_color(ta, lv_color_hex(0x8a8f98), LV_PART_TEXTAREA_PLACEHOLDER);
    return ta;
}

lv_obj_t *kit_keyboard(lv_obj_t *p, lv_obj_t *ta, lv_event_cb_t on_ready, void *ud)
{
    lv_obj_t *kb = lv_keyboard_create(p);
    lv_obj_set_size(kb, WALL_W, P(330));
    lv_obj_align(kb, LV_ALIGN_BOTTOM_MID, 0, 0);
    /* the built-in font: every key is drawn again at each press, and this one needs no rasterizing */
    lv_obj_set_style_text_font(kb, font_symbols(28), 0);
    lv_obj_set_style_text_font(kb, font_symbols(28), LV_PART_ITEMS);
    lv_obj_set_style_bg_color(kb, lv_color_hex(0x111215), 0);
    lv_obj_set_style_bg_color(kb, lv_color_hex(0x2a2c31), LV_PART_ITEMS);
    lv_obj_set_style_text_color(kb, lv_color_white(), LV_PART_ITEMS);
    lv_keyboard_set_textarea(kb, ta);
    if (on_ready) lv_obj_add_event_cb(kb, on_ready, LV_EVENT_READY, ud);
    return kb;
}

static lv_obj_t *panel;

static void on_panel_close(lv_event_t *e)
{
    kit_close_panel();
}

void kit_close_panel(void)
{
    if (panel) {
        lv_obj_delete(panel);
        panel = NULL;
    }
}

bool kit_panel_open(void)
{
    return panel != NULL;
}

lv_obj_t *kit_panel(const char *title, int w, int h)
{
    kit_close_panel();
    panel = lv_obj_create(lv_layer_top());
    lv_obj_remove_style_all(panel);
    lv_obj_set_size(panel, WALL_W, WALL_H);
    lv_obj_set_style_bg_color(panel, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_60, 0);
    lv_obj_add_flag(panel, LV_OBJ_FLAG_CLICKABLE);  /* a tap beside the card closes it */
    lv_obj_add_event_cb(panel, on_panel_close, LV_EVENT_SHORT_CLICKED, NULL);
    lv_obj_t *card = lv_obj_create(panel);
    lv_obj_set_size(card, w, h);
    lv_obj_center(card);
    lv_obj_set_style_bg_color(card, lv_color_hex(0x16181c), 0);
    lv_obj_set_style_bg_opa(card, LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(card, 0, 0);
    lv_obj_set_style_radius(card, P(28), 0);
    lv_obj_set_style_pad_all(card, P(30), 0);
    lv_obj_set_style_pad_row(card, P(16), 0);
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_t *top = lv_obj_create(card);
    lv_obj_remove_style_all(top);
    lv_obj_set_size(top, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_t *t = kit_label(top, font_bold(36), lv_color_white(), title);
    lv_label_set_long_mode(t, LV_LABEL_LONG_DOT);
    lv_obj_set_width(t, w - P(160));
    lv_obj_align(t, LV_ALIGN_LEFT_MID, 0, 0);
    lv_obj_t *x = lv_button_create(top);
    lv_obj_set_size(x, P(64), P(64));
    lv_obj_set_style_radius(x, P(32), 0);
    lv_obj_set_style_bg_color(x, lv_color_hex(0x33363d), 0);
    lv_obj_set_style_shadow_width(x, 0, 0);
    lv_obj_align(x, LV_ALIGN_RIGHT_MID, 0, 0);
    lv_obj_t *xl = kit_label(x, font_symbols(28), lv_color_white(), LV_SYMBOL_CLOSE);
    lv_obj_center(xl);
    lv_obj_add_event_cb(x, on_panel_close, LV_EVENT_CLICKED, NULL);
    return card;
}
