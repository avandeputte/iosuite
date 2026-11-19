/* Setting up, on the device itself: the Wi-Fi (a network from the list and its password), the start page's address
 * inside the network, then signing in. Signing in: the display shows a code and a QR code of the start page's
 * #/pair/<code>; someone signed in there lets it in, and it gets an ioStart app password of theirs. Or, instead, a
 * name and a password typed here once: they are sent to the start page's /api/auth/app-passwords, which makes the app
 * password; the password itself is not kept. */
#include <string.h>
#include "cJSON.h"
#include "esp_log.h"
#include "mbedtls/base64.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "wall.h"

#define TEXT lv_color_white()
#define DIM lv_color_hex(0xb8bcc4)
#define BAD lv_color_hex(0xffb4a8)
#define LABEL_FOR_DEVICE "Wall display (" BOARD_NAME ")"

static lv_obj_t *scr, *card, *kb;
static net_ap_t aps[24];
static int naps;
static char chosen_ssid[33];
static char base[128];
static char pair_token[64], pair_code[16], pair_url[200];
static volatile bool pairing;   /* the poll runs while this is on */
static int pair_gen;            /* a new code stops the old poll */

static void step_wifi(void);
static void step_address(void);
static void step_pair(void);
static void step_password(void);

/* ------------------------------------------------------------------ the frame */

static lv_obj_t *page(const char *title, const char *hint, bool with_keyboard)
{
    if (!scr) {
        scr = lv_obj_create(NULL);
        lv_obj_set_style_bg_color(scr, lv_color_hex(0x0b0d12), 0);
        lv_obj_set_style_bg_grad_color(scr, lv_color_hex(0x1d2f5e), 0);
        lv_obj_set_style_bg_grad_dir(scr, LV_GRAD_DIR_VER, 0);
        lv_obj_remove_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
    }
    lv_obj_clean(scr);
    kb = NULL;
    card = lv_obj_create(scr);
    lv_obj_remove_style_all(card);
    lv_obj_set_size(card, P(1040), with_keyboard ? P(360) : P(640));
    lv_obj_align(card, LV_ALIGN_TOP_MID, 0, with_keyboard ? P(14) : P(40));
    lv_obj_set_flex_flow(card, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(card, P(14), 0);
    lv_obj_t *t = kit_label(card, font_bold(44), TEXT, title);
    (void)t;
    if (hint) {
        lv_obj_t *h = kit_label(card, font_text(28), DIM, hint);
        lv_label_set_long_mode(h, LV_LABEL_LONG_WRAP);
        lv_obj_set_width(h, lv_pct(100));
    }
    if (lv_screen_active() != scr) lv_screen_load(scr);
    return card;
}

static lv_obj_t *buttons(lv_obj_t *parent)
{
    lv_obj_t *r = lv_obj_create(parent);
    lv_obj_remove_style_all(r);
    lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(r, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(r, P(16), 0);
    lv_obj_set_style_pad_top(r, P(8), 0);
    return r;
}

static lv_obj_t *status_line(lv_obj_t *parent)
{
    lv_obj_t *l = kit_label(parent, font_text(28), DIM, "");
    lv_label_set_long_mode(l, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(l, lv_pct(100));
    return l;
}

/* ------------------------------------------------------------------ 1. Wi-Fi */

static lv_obj_t *wifi_list, *wifi_status, *pass_ta;

static void on_network(lv_event_t *e);

static void scan_done(void *arg)
{
    if (lv_screen_active() != scr || !wifi_list) return;
    lv_obj_clean(wifi_list);
    if (!naps) {
        lv_label_set_text(wifi_status, "No networks found. Tap Look again.");
        return;
    }
    lv_label_set_text(wifi_status, "");
    for (int i = 0; i < naps; i++) {
        lv_obj_t *b = lv_button_create(wifi_list);
        lv_obj_set_size(b, lv_pct(100), P(72));
        lv_obj_set_style_radius(b, P(16), 0);
        lv_obj_set_style_shadow_width(b, 0, 0);
        lv_obj_set_style_bg_color(b, lv_color_hex(0x1b1d22), 0);
        lv_obj_set_style_bg_color(b, lv_color_hex(0x33363d), LV_STATE_PRESSED);
        lv_obj_t *l = kit_label(b, font_text(30), TEXT, aps[i].ssid);
        lv_obj_align(l, LV_ALIGN_LEFT_MID, P(8), 0);
        const char *bars = aps[i].rssi > -55 ? "Strong" : aps[i].rssi > -70 ? "Good" : "Weak";
        lv_obj_t *r = kit_label(b, font_text(24), DIM, "");
        lv_label_set_text_fmt(r, "%s%s", aps[i].open ? "Open · " : "", bars);
        lv_obj_align(r, LV_ALIGN_RIGHT_MID, -P(8), 0);
        lv_obj_add_event_cb(b, on_network, LV_EVENT_CLICKED, (void *)(intptr_t)i);
    }
}

static void scan_job(void *arg)
{
    naps = net_scan(aps, 24);
    ui_lock();
    scan_done(NULL);
    ui_unlock();
}

static void on_rescan(lv_event_t *e)
{
    if (wifi_status) lv_label_set_text(wifi_status, "Looking for networks…");
    feed_run(scan_job, NULL);
}

static void wifi_wait_job(void *arg)
{
    /* up to 25 s for the network to answer */
    for (int i = 0; i < 50; i++) {
        vTaskDelay(pdMS_TO_TICKS(500));
        net_state_t s = net_state();
        if (s == NET_UP || s == NET_FAILED) break;
    }
    ui_lock();
    if (lv_screen_active() == scr) {
        if (net_state() == NET_UP) {
            step_address();
        } else {
            step_wifi();
            lv_label_set_text_fmt(wifi_status, "Could not join %s: %s", chosen_ssid, net_why()[0] ? net_why() : "no answer");
            lv_obj_set_style_text_color(wifi_status, BAD, 0);
        }
    }
    ui_unlock();
}

static void connect_now(const char *pass)
{
    net_connect(chosen_ssid, pass);
    lv_obj_t *c = page("Joining the network", NULL, false);
    lv_obj_t *l = status_line(c);
    lv_label_set_text_fmt(l, "Joining %s…", chosen_ssid);
    lv_obj_t *sp = lv_spinner_create(c);
    lv_obj_set_size(sp, P(80), P(80));
    feed_run(wifi_wait_job, NULL);
}

static void on_pass_ready(lv_event_t *e)
{
    connect_now(lv_textarea_get_text(pass_ta));
}

static void on_pass_join(lv_event_t *e)
{
    connect_now(lv_textarea_get_text(pass_ta));
}

static void on_back_to_wifi(lv_event_t *e)
{
    step_wifi();
}

static void on_network(lv_event_t *e)
{
    int i = (int)(intptr_t)lv_event_get_user_data(e);
    strlcpy(chosen_ssid, aps[i].ssid, sizeof chosen_ssid);
    if (aps[i].open) {
        connect_now("");
        return;
    }
    char t[80];
    snprintf(t, sizeof t, "The password of %s", chosen_ssid);
    lv_obj_t *c = page(t, NULL, true);
    pass_ta = kit_textarea(c, "Password", true);
    if (!strcmp(chosen_ssid, S.ssid)) lv_textarea_set_text(pass_ta, S.wifi_pass);
    lv_obj_t *b = buttons(c);
    kit_button(b, "Join", on_pass_join, NULL, true);
    kit_button(b, "Back", on_back_to_wifi, NULL, false);
    kb = kit_keyboard(scr, pass_ta, on_pass_ready, NULL);
}

static void on_wifi_skip(lv_event_t *e)
{
    step_address();
}

static void step_wifi(void)
{
    lv_obj_t *c = page("Wi-Fi", "Pick the network this display joins. It needs to reach the start page.", false);
    wifi_status = status_line(c);
    lv_label_set_text(wifi_status, "Looking for networks…");
    wifi_list = lv_obj_create(c);
    lv_obj_remove_style_all(wifi_list);
    lv_obj_set_size(wifi_list, lv_pct(100), P(360));
    lv_obj_set_flex_flow(wifi_list, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(wifi_list, P(8), 0);
    lv_obj_set_scroll_dir(wifi_list, LV_DIR_VER);
    lv_obj_t *b = buttons(c);
    kit_button(b, "Look again", on_rescan, NULL, false);
    if (net_state() == NET_UP) {
        char t[64];
        snprintf(t, sizeof t, "Keep %s", S.ssid);
        kit_button(b, t, on_wifi_skip, NULL, true);
    }
    feed_run(scan_job, NULL);
}

/* ------------------------------------------------------------------ 2. the start page's address */

static lv_obj_t *addr_ta, *addr_status;

typedef struct {
    char base[128];
} check_job_t;

static void pair_poll_job(void *arg);

static void check_job(void *arg)
{
    check_job_t *j = arg;
    /* the start page answers /api/status to anyone; then a code for this display */
    api_resp_t r = api_request("GET", "/api/status", NULL, 8192, j->base);
    bool ok = r.status == 200 && r.body && strstr(r.body, "\"version\"");
    char why[120];
    strlcpy(why, r.why[0] ? r.why : "That does not look like the start page", sizeof why);
    api_free(&r);
    if (ok) {
        r = api_request("POST", "/api/wall/pair", "{\"label\": \"" LABEL_FOR_DEVICE "\"}", 8192, j->base);
        ok = false;
        if (r.status == 200) {
            cJSON *o = cJSON_Parse(r.body);
            const cJSON *t = cJSON_GetObjectItem(o, "token"), *c = cJSON_GetObjectItem(o, "code"), *u = cJSON_GetObjectItem(o, "approveUrl");
            if (cJSON_IsString(t) && cJSON_IsString(c)) {
                strlcpy(pair_token, t->valuestring, sizeof pair_token);
                strlcpy(pair_code, c->valuestring, sizeof pair_code);
                strlcpy(pair_url, cJSON_IsString(u) ? u->valuestring : "", sizeof pair_url);
                ok = true;
            }
            cJSON_Delete(o);
        } else if (r.status == 404) {
            strlcpy(why, "The start page is too old for a wall display: update it first", sizeof why);
        } else {
            strlcpy(why, r.why, sizeof why);
        }
        api_free(&r);
    }
    ui_lock();
    if (lv_screen_active() == scr) {
        if (ok) {
            strlcpy(base, j->base, sizeof base);
            step_pair();
        } else if (addr_status) {
            lv_label_set_text(addr_status, why);
            lv_obj_set_style_text_color(addr_status, BAD, 0);
        }
    }
    ui_unlock();
    free(j);
}

static void on_addr_next(lv_event_t *e)
{
    check_job_t *j = calloc(1, sizeof *j);
    if (!j) return;
    if (!api_normalize(lv_textarea_get_text(addr_ta), j->base, sizeof j->base)) {
        lv_label_set_text(addr_status, "Type the address, e.g. 192.168.1.20:8600");
        free(j);
        return;
    }
    lv_label_set_text_fmt(addr_status, "Asking %s…", j->base);
    lv_obj_set_style_text_color(addr_status, DIM, 0);
    feed_run(check_job, j);
}

static void on_addr_back(lv_event_t *e)
{
    step_wifi();
}

static void step_address(void)
{
    pairing = false;
    lv_obj_t *c = page("The start page's address",
                       "As you reach it at home, with its port: e.g. 192.168.1.20:8600 or start.local:8600. An address behind "
                       "Cloudflare Access does not work here (the display cannot sign in there).", true);
    addr_ta = kit_textarea(c, "192.168.1.20:8600", false);
    if (S.server[0]) lv_textarea_set_text(addr_ta, S.server);
    addr_status = status_line(c);
    lv_obj_t *b = buttons(c);
    kit_button(b, "Next", on_addr_next, NULL, true);
    kit_button(b, "Wi-Fi", on_addr_back, NULL, false);
    kb = kit_keyboard(scr, addr_ta, on_addr_next, NULL);
}

/* ------------------------------------------------------------------ 3. signing in: the code */

static lv_obj_t *pair_status;

static void signed_in(const char *token, const char *user)
{
    strlcpy(S.server, base, sizeof S.server);
    strlcpy(S.token, token, sizeof S.token);
    strlcpy(S.user, user ? user : "", sizeof S.user);
    settings_save();
    pairing = false;
    ui_show_wall();
    char t[96];
    snprintf(t, sizeof t, "Signed in as %s", S.user[0] ? S.user : "you");
    ui_toast(t);
    feed_refresh();
}

static void pair_poll_job(void *arg)
{
    int gen = (int)(intptr_t)arg;
    char path[120];
    snprintf(path, sizeof path, "/api/wall/pair/%s", pair_token);
    for (int i = 0; pairing && gen == pair_gen && i < 200; i++) {  /* ten minutes, every three seconds */
        api_resp_t r = api_request("GET", path, NULL, 8192, base);
        if (r.status == 200) {
            cJSON *o = cJSON_Parse(r.body);
            const cJSON *pw = cJSON_GetObjectItem(o, "password"), *nm = cJSON_GetObjectItem(o, "name");
            if (cJSON_IsString(pw)) {
                ui_lock();
                signed_in(pw->valuestring, cJSON_IsString(nm) ? nm->valuestring : "");
                ui_unlock();
            }
            cJSON_Delete(o);
            api_free(&r);
            return;
        }
        bool gone = r.status == 404;
        api_free(&r);
        if (gone) {
            ui_lock();
            if (pairing && gen == pair_gen && pair_status) {
                lv_label_set_text(pair_status, "The code has expired. Tap New code.");
                lv_obj_set_style_text_color(pair_status, BAD, 0);
            }
            ui_unlock();
            return;
        }
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
}

static void new_code_job(void *arg)
{
    check_job_t *j = calloc(1, sizeof *j);
    if (!j) return;
    strlcpy(j->base, base, sizeof j->base);
    check_job(j);
}

static void on_new_code(lv_event_t *e)
{
    pairing = false;
    feed_run(new_code_job, NULL);
}

static void on_use_password(lv_event_t *e)
{
    pairing = false;
    step_password();
}

static void on_pair_back(lv_event_t *e)
{
    pairing = false;
    step_address();
}

static void step_pair(void)
{
    lv_obj_t *c = page("Let this display in", NULL, false);
    lv_obj_t *r = lv_obj_create(c);
    lv_obj_remove_style_all(r);
    lv_obj_set_size(r, lv_pct(100), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(r, LV_FLEX_FLOW_ROW);
    lv_obj_set_style_pad_column(r, P(40), 0);
    lv_obj_t *qr = lv_qrcode_create(r);
    lv_qrcode_set_size(qr, P(300));
    lv_qrcode_set_dark_color(qr, lv_color_black());
    lv_qrcode_set_light_color(qr, lv_color_white());
    lv_obj_set_style_border_color(qr, lv_color_white(), 0);
    lv_obj_set_style_border_width(qr, P(14), 0);
    const char *url = pair_url[0] ? pair_url : base;
    lv_qrcode_update(qr, url, strlen(url));
    lv_obj_t *col = lv_obj_create(r);
    lv_obj_remove_style_all(col);
    lv_obj_set_size(col, P(640), LV_SIZE_CONTENT);
    lv_obj_set_flex_flow(col, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_style_pad_row(col, P(14), 0);
    lv_obj_t *h = kit_label(col, font_text(28), DIM, "Scan this with your phone, or open the start page, go to the address below and type the code. Sign in there as the person whose calendar this wall shows.");
    lv_label_set_long_mode(h, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(h, lv_pct(100));
    char code[16];
    snprintf(code, sizeof code, "%.4s-%.4s", pair_code, pair_code + 4);
    lv_obj_t *cl = kit_label(col, font_bold(84), TEXT, code);
    lv_obj_set_style_text_letter_space(cl, P(6), 0);
    char where[180];
    snprintf(where, sizeof where, "%s/#/pair", base);
    lv_obj_t *w = kit_label(col, font_text(26), DIM, where);
    lv_label_set_long_mode(w, LV_LABEL_LONG_WRAP);
    lv_obj_set_width(w, lv_pct(100));
    pair_status = status_line(col);
    lv_label_set_text(pair_status, "Waiting for the start page…");
    lv_obj_t *b = buttons(c);
    kit_button(b, "New code", on_new_code, NULL, false);
    kit_button(b, "Use a password instead", on_use_password, NULL, false);
    kit_button(b, "Address", on_pair_back, NULL, false);
    pairing = true;
    pair_gen++;
    feed_run(pair_poll_job, (void *)(intptr_t)pair_gen);
}

/* ------------------------------------------------------------------ 3b. signing in: a name and a password */

static lv_obj_t *name_ta, *pw_ta, *pw_status;

typedef struct {
    char name[64], pw[128];
} pw_job_t;

static void password_job(void *arg)
{
    pw_job_t *j = arg;
    char both[200], b64[300], auth[320];
    snprintf(both, sizeof both, "%s:%s", j->name, j->pw);
    size_t n = 0;
    mbedtls_base64_encode((unsigned char *)b64, sizeof b64, &n, (const unsigned char *)both, strlen(both));
    b64[n] = 0;
    snprintf(auth, sizeof auth, "Basic %s", b64);
    memset(both, 0, sizeof both);
    memset(j->pw, 0, sizeof j->pw);
    api_resp_t r = api_request_auth("POST", "/api/auth/app-passwords", "{\"label\": \"" LABEL_FOR_DEVICE "\"}", 8192, base, auth);
    memset(auth, 0, sizeof auth);
    char pw[160] = "", user[64] = "", why[120] = "";
    if (r.status == 200) {
        cJSON *o = cJSON_Parse(r.body);
        const cJSON *p = cJSON_GetObjectItem(o, "password"), *u = cJSON_GetObjectItem(o, "name");
        if (cJSON_IsString(p)) strlcpy(pw, p->valuestring, sizeof pw);
        if (cJSON_IsString(u)) strlcpy(user, u->valuestring, sizeof user);
        cJSON_Delete(o);
    } else {
        strlcpy(why, r.status == 401 ? "Wrong name or password" : r.why, sizeof why);
    }
    api_free(&r);
    ui_lock();
    if (pw[0]) {
        signed_in(pw, user[0] ? user : j->name);
    } else if (lv_screen_active() == scr && pw_status) {
        lv_label_set_text(pw_status, why);
        lv_obj_set_style_text_color(pw_status, BAD, 0);
    }
    ui_unlock();
    free(j);
}

static void on_pw_go(lv_event_t *e)
{
    pw_job_t *j = calloc(1, sizeof *j);
    if (!j) return;
    strlcpy(j->name, lv_textarea_get_text(name_ta), sizeof j->name);
    strlcpy(j->pw, lv_textarea_get_text(pw_ta), sizeof j->pw);
    if (!j->name[0] || !j->pw[0]) {
        free(j);
        lv_label_set_text(pw_status, "Your name and password, please");
        return;
    }
    lv_textarea_set_text(pw_ta, "");
    lv_label_set_text(pw_status, "Signing in…");
    lv_obj_set_style_text_color(pw_status, DIM, 0);
    feed_run(password_job, j);
}

static void on_name_ready(lv_event_t *e)
{
    lv_keyboard_set_textarea(kb, pw_ta);
    lv_obj_add_state(pw_ta, LV_STATE_FOCUSED);
    lv_obj_remove_state(name_ta, LV_STATE_FOCUSED);
}

static void on_kb_ready(lv_event_t *e)
{
    if (lv_keyboard_get_textarea(kb) == name_ta) on_name_ready(e);
    else on_pw_go(e);
}

static void on_ta_focus(lv_event_t *e)
{
    if (kb) lv_keyboard_set_textarea(kb, lv_event_get_target(e));
}

static void on_pw_back(lv_event_t *e)
{
    step_pair();
}

static void step_password(void)
{
    lv_obj_t *c = page("Sign in with a password", "Once: the display keeps an app password of yours instead (Settings › Account on the start page lists it).", true);
    name_ta = kit_textarea(c, "Name", false);
    if (S.user[0]) lv_textarea_set_text(name_ta, S.user);
    pw_ta = kit_textarea(c, "Password", true);
    lv_obj_add_event_cb(name_ta, on_ta_focus, LV_EVENT_FOCUSED, NULL);
    lv_obj_add_event_cb(pw_ta, on_ta_focus, LV_EVENT_FOCUSED, NULL);
    pw_status = status_line(c);
    lv_obj_t *b = buttons(c);
    kit_button(b, "Sign in", on_pw_go, NULL, true);
    kit_button(b, "Use a code", on_pw_back, NULL, false);
    lv_obj_set_height(c, P(470));
    kb = kit_keyboard(scr, name_ta, on_kb_ready, NULL);
    lv_obj_set_height(kb, P(250));
}

/* ------------------------------------------------------------------ the way in */

void ui_show_setup(void)
{
    kit_close_panel();
    if (net_state() != NET_UP && !S.ssid[0]) {
        step_wifi();
    } else if (!S.server[0] || net_state() != NET_UP) {
        if (net_state() == NET_UP) step_address();
        else step_wifi();
    } else {
        strlcpy(base, S.server, sizeof base);
        step_address();
    }
}
