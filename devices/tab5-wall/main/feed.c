/* The start page's wall feed, every minute (sooner after a change made here), and its photos, one every so often
 * (the person's choice on the start page: Customize › Wall display), cut by the start page to the screen's size and decoded
 * here by the P4's JPEG engine into one of two frame buffers in PSRAM, so the one on screen is never written while
 * it fades. A third task runs the taps' HTTP calls (feed_run), so the screen never waits on the network. */
#include <string.h>
#include <sys/time.h>
#include "cJSON.h"
#include "driver/jpeg_decode.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "wall.h"

wall_feed_t *FEED;
static TaskHandle_t feed_task, photo_task;
static QueueHandle_t jobs;

/* ------------------------------------------------------------------ JSON */

static void jstr(const cJSON *o, const char *k, char *out, size_t n)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    if (cJSON_IsString(v) && v->valuestring) {
        strlcpy(out, v->valuestring, n);
    } else if (cJSON_IsNumber(v)) {
        snprintf(out, n, "%lld", (long long)v->valuedouble);
    } else {
        out[0] = 0;
    }
}

static bool jnum(const cJSON *o, const char *k, int *out)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    if (cJSON_IsNumber(v)) {
        *out = (int)v->valuedouble;
        return true;
    }
    return false;
}

static int jint(const cJSON *o, const char *k, int def)
{
    int v;
    return jnum(o, k, &v) ? v : def;
}

static time_t jtime(const cJSON *o, const char *k)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    return cJSON_IsNumber(v) ? (time_t)v->valuedouble : 0;
}

static bool jbool(const cJSON *o, const char *k)
{
    return cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(o, k));
}

static bool jcolor(const cJSON *o, const char *k, uint32_t *out)
{
    const cJSON *v = cJSON_GetObjectItemCaseSensitive(o, k);
    if (!cJSON_IsString(v) || !v->valuestring || v->valuestring[0] != '#') return false;
    const char *s = v->valuestring + 1;
    size_t l = strlen(s);
    unsigned r, g, b;
    if (l == 6 && sscanf(s, "%2x%2x%2x", &r, &g, &b) == 3) {
        *out = (r << 16) | (g << 8) | b;
        return true;
    }
    if (l == 3 && sscanf(s, "%1x%1x%1x", &r, &g, &b) == 3) {
        *out = (r * 17 << 16) | (g * 17 << 8) | b * 17;
        return true;
    }
    return false;
}

static void parse_event(const cJSON *o, wall_event_t *e)
{
    memset(e, 0, sizeof *e);
    jstr(o, "title", e->title, sizeof e->title);
    jstr(o, "place", e->place, sizeof e->place);
    jstr(o, "location", e->location, sizeof e->location);
    e->all_day = jbool(o, "allDay");
    e->s = jtime(o, "s");
    e->e = jtime(o, "e");
    jstr(o, "day", e->day, sizeof e->day);
    jstr(o, "endDay", e->end_day, sizeof e->end_day);
    e->has_color = jcolor(o, "color", &e->color);
    const cJSON *x;
    cJSON_ArrayForEach(x, cJSON_GetObjectItemCaseSensitive(o, "who")) {
        if (e->nwho >= (int)(sizeof e->who / sizeof e->who[0])) break;
        jstr(x, "name", e->who[e->nwho].name, sizeof e->who[0].name);
        e->who[e->nwho].has_color = jcolor(x, "color", &e->who[e->nwho].color);
        if (e->who[e->nwho].name[0]) e->nwho++;
    }
    cJSON_ArrayForEach(x, cJSON_GetObjectItemCaseSensitive(o, "people")) {
        if (!cJSON_IsString(x) || !x->valuestring[0]) continue;
        if (e->people[0]) strlcat(e->people, ", ", sizeof e->people);
        strlcat(e->people, x->valuestring, sizeof e->people);
    }
    jstr(o, "calendar", e->calendar, sizeof e->calendar);
    jstr(o, "notes", e->notes, sizeof e->notes);
    e->recurring = jbool(o, "recurring");
}

static bool parse(const char *text, wall_feed_t *f)
{
    cJSON *root = cJSON_Parse(text);
    if (!root) {
        snprintf(f->why, sizeof f->why, "The start page's answer could not be read");
        return false;
    }
    const cJSON *z = cJSON_GetObjectItem(root, "zone");
    jstr(z, "name", f->zone, sizeof f->zone);
    jstr(z, "posix", f->posix, sizeof f->posix);
    char units[12];
    jstr(root, "units", units, sizeof units);
    f->imperial = !strcmp(units, "imperial");
    jstr(root, "bg", f->bg, sizeof f->bg);
    f->every = jint(root, "every", 60);
    if (f->every < 10) f->every = 10;
    const cJSON *u = cJSON_GetObjectItem(root, "user");
    jstr(u, "name", f->user, sizeof f->user);
    jstr(u, "role", f->role, sizeof f->role);
    time_t now = jtime(root, "now");
    if (now > 1700000000 && !clock_is_set()) {
        struct timeval tv = {.tv_sec = now};
        settimeofday(&tv, NULL);  /* until SNTP answers */
    }

    const cJSON *w = cJSON_GetObjectItem(root, "weather");
    if (cJSON_IsObject(w)) {
        f->has_weather = true;
        f->has_temp = jnum(w, "temp", &f->temp);
        jstr(w, "text", f->wtext, sizeof f->wtext);
        f->wicon = jint(w, "icon", 0);
        f->wday = !cJSON_IsFalse(cJSON_GetObjectItem(w, "day"));
        jstr(w, "place", f->place, sizeof f->place);
        const cJSON *rain = cJSON_GetObjectItem(w, "rain");
        if (cJSON_IsObject(rain)) {
            jstr(rain, "what", f->rain_what, sizeof f->rain_what);
            if (cJSON_GetObjectItem(rain, "from")) {
                f->rain_mode = 1;
                f->rain_from = jtime(rain, "from");
            } else if (cJSON_IsNumber(cJSON_GetObjectItem(rain, "until"))) {
                f->rain_mode = 2;
                f->rain_until = jtime(rain, "until");
            } else {
                f->rain_mode = 3;
            }
        }
        const cJSON *x;
        cJSON_ArrayForEach(x, cJSON_GetObjectItem(w, "hours")) {
            if (f->nhours >= 12) break;
            wall_hour_t *hh = &f->hours[f->nhours++];
            hh->t = jtime(x, "t");
            hh->has_temp = jnum(x, "temp", &hh->temp);
            hh->icon = jint(x, "icon", 0);
            hh->rain = jint(x, "rain", 0);
            hh->wet = jbool(x, "wet");
        }
        cJSON_ArrayForEach(x, cJSON_GetObjectItem(w, "days")) {
            if (f->nwdays >= 5) break;
            wall_wday_t *d = &f->wdays[f->nwdays++];
            jstr(x, "date", d->date, sizeof d->date);
            d->has_temp = jnum(x, "max", &d->max);
            jnum(x, "min", &d->min);
            d->icon = jint(x, "icon", 0);
            d->rain = jint(x, "rain", 0);
        }
    }

    const cJSON *home = cJSON_GetObjectItem(root, "home");
    if (cJSON_IsObject(home)) {
        f->has_home = true;
        const cJSON *x;
        cJSON_ArrayForEach(x, cJSON_GetObjectItem(home, "items")) {
            if (f->nha >= 12) break;
            wall_ha_t *a = &f->ha[f->nha++];
            jstr(x, "id", a->id, sizeof a->id);
            jstr(x, "name", a->name, sizeof a->name);
            jstr(x, "text", a->text, sizeof a->text);
            jstr(x, "domain", a->domain, sizeof a->domain);
            jstr(x, "tap", a->tap, sizeof a->tap);
            const cJSON *on = cJSON_GetObjectItem(x, "on");
            a->on = cJSON_IsTrue(on) ? 1 : cJSON_IsFalse(on) ? 0 : -1;
        }
        cJSON_ArrayForEach(x, cJSON_GetObjectItem(home, "alerts")) {
            if (f->nalerts >= 3) break;
            char n[48], t[44];
            jstr(x, "name", n, sizeof n);
            jstr(x, "text", t, sizeof t);
            snprintf(f->alerts[f->nalerts++], sizeof f->alerts[0], "%s: %s", n, t);
        }
    }

    const cJSON *x;
    cJSON_ArrayForEach(x, cJSON_GetObjectItem(root, "birthdays")) {
        if (f->nbdays >= 6) break;
        wall_bday_t *b = &f->bdays[f->nbdays++];
        jstr(x, "name", b->name, sizeof b->name);
        b->in = jint(x, "in", 0);
        jstr(x, "label", b->label, sizeof b->label);
        b->turns = jint(x, "turns", 0);
    }

    const cJSON *today = cJSON_GetObjectItem(root, "today");
    if (cJSON_IsArray(today)) {
        f->has_today = true;
        cJSON_ArrayForEach(x, today) {
            if (f->ntoday >= 12) break;
            parse_event(x, &f->today[f->ntoday++]);
        }
        f->today_more = jint(root, "todayMore", 0);
        const cJSON *next = cJSON_GetObjectItem(root, "next");
        if (cJSON_IsObject(next)) {
            f->has_next = true;
            parse_event(next, &f->next);
        }
    }
    const cJSON *days = cJSON_GetObjectItem(root, "days");
    if (cJSON_IsArray(days)) {
        f->has_days = true;
        cJSON_ArrayForEach(x, days) {
            if (f->ndays >= 7) break;
            wall_day_t *d = &f->days[f->ndays++];
            jstr(x, "date", d->date, sizeof d->date);
            const cJSON *e;
            cJSON_ArrayForEach(e, cJSON_GetObjectItem(x, "items")) {
                if (d->n >= 8) break;
                parse_event(e, &d->ev[d->n++]);
            }
        }
    }

    const cJSON *tasks = cJSON_GetObjectItem(root, "tasks");
    if (cJSON_IsObject(tasks)) {
        f->has_tasks = true;
        cJSON_ArrayForEach(x, cJSON_GetObjectItem(tasks, "items")) {
            if (f->ntasks >= 10) break;
            wall_task_t *t = &f->tasks[f->ntasks++];
            jstr(x, "id", t->id, sizeof t->id);
            jstr(x, "title", t->title, sizeof t->title);
            t->late = jbool(x, "late");
            t->has_color = jcolor(x, "color", &t->color);
        }
        f->tasks_more = jint(tasks, "more", 0);
        f->overdue = jint(tasks, "overdue", 0);
    }

    cJSON_ArrayForEach(x, cJSON_GetObjectItem(root, "photos")) {
        if (f->nphotos >= 24) break;
        wall_photo_t *p = &f->photos[f->nphotos++];
        jstr(x, "id", p->id, sizeof p->id);
        p->year = jint(x, "year", 0);
        p->ago = jint(x, "yearsAgo", 0);
    }

    const cJSON *can = cJSON_GetObjectItem(root, "can");
    f->can_add_task = jbool(can, "addTask");
    f->can_add_event = jbool(can, "addEvent");
    f->can_fav = jbool(can, "favorite");
    f->can_home = jbool(can, "home");
    cJSON_Delete(root);
    f->ok = true;
    return true;
}

/* ------------------------------------------------------------------ the feed */

static void fetch_once(void)
{
    if (!S.token[0] || net_state() != NET_UP) {
        return;
    }
    char path[128];
    snprintf(path, sizeof path, "/api/wall/feed%s%s", S.tz[0] ? "?tz=" : "", S.tz);
    api_resp_t r = api_request("GET", path, NULL, 256 * 1024, NULL);
    wall_feed_t *f = heap_caps_calloc(1, sizeof *f, MALLOC_CAP_SPIRAM);
    if (!f) {
        api_free(&r);
        return;
    }
    f->fetched = time(NULL);
    if (r.status == 401) {
        ESP_LOGW(TAG_WALL, "the start page no longer takes this app password: set up again");
        api_free(&r);
        heap_caps_free(f);
        settings_forget_sign_in();
        ui_lock();
        ui_show_setup();
        ui_unlock();
        return;
    }
    if (r.status == 200) {
        parse(r.body, f);
    } else {
        strlcpy(f->why, r.why[0] ? r.why : "No answer", sizeof f->why);
    }
    api_free(&r);
    if (!f->ok) {
        /* keep what is on screen; say that it is old */
        ui_lock();
        if (FEED->ok) {
            strlcpy(FEED->why, f->why, sizeof FEED->why);
        } else {
            *FEED = *f;
        }
        ui_wall_feed_changed();
        ui_unlock();
        heap_caps_free(f);
        return;
    }
    if (f->posix[0] && strcmp(f->posix, S.posix)) {
        strlcpy(S.posix, f->posix, sizeof S.posix);
        settings_save();
    }
    clock_set_zone(f->posix);
    ui_lock();
    /* a task ticked here that the start page has not caught up with yet stays ticked */
    for (int i = 0; i < f->ntasks; i++) {
        for (int j = 0; j < FEED->ntasks; j++) {
            if (FEED->tasks[j].done && !strcmp(FEED->tasks[j].id, f->tasks[i].id)) f->tasks[i].done = true;
        }
    }
    wall_feed_t *old = FEED;
    bool photos_changed = old->nphotos != f->nphotos || strcmp(old->bg, f->bg);
    FEED = f;
    ui_wall_feed_changed();
    ui_unlock();
    heap_caps_free(old);
    if (photos_changed && photo_task) {
        xTaskNotifyGive(photo_task);
    }
}

static void feed_loop(void *arg)
{
    for (;;) {
        fetch_once();
        views_poll();
        bool ok;
        ui_lock();
        ok = FEED->ok && !FEED->why[0];
        ui_unlock();
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(ok ? 60000 : 15000));
    }
}

void feed_refresh(void)
{
    if (feed_task) {
        xTaskNotifyGive(feed_task);
    }
}

/* ------------------------------------------------------------------ the photos */

static jpeg_decoder_handle_t jpeg;
static uint8_t *frame[2];
static size_t frame_size;
static uint8_t *in_buf;
static size_t in_size;
static lv_image_dsc_t dsc[2];
static int cur = -1;           /* the frame on screen */
static int shown = -1;         /* its index in FEED->photos */
static wall_photo_t shown_photo;
static bool has_shown;
static char favs[16][24];      /* the photos made favorites here this session */
static int nfavs;

const wall_photo_t *feed_current_photo(void)
{
    return has_shown ? &shown_photo : NULL;
}

bool feed_photo_is_favorite(void)
{
    if (!has_shown) return false;
    for (int i = 0; i < nfavs; i++) {
        if (!strcmp(favs[i], shown_photo.id)) return true;
    }
    return false;
}

void feed_set_photo_favorite(bool on)
{
    if (!has_shown) return;
    for (int i = 0; i < nfavs; i++) {
        if (!strcmp(favs[i], shown_photo.id)) {
            if (!on) {
                memmove(favs[i], favs[i + 1], (nfavs - i - 1) * sizeof favs[0]);
                nfavs--;
            }
            return;
        }
    }
    if (on) {
        if (nfavs == 16) {
            memmove(favs[0], favs[1], 15 * sizeof favs[0]);
            nfavs--;
        }
        strlcpy(favs[nfavs++], shown_photo.id, sizeof favs[0]);
    }
}

static bool photo_setup(void)
{
    if (jpeg) return true;
    jpeg_decode_engine_cfg_t ec = {.intr_priority = 0, .timeout_ms = 2000};
    if (jpeg_new_decoder_engine(&ec, &jpeg) != ESP_OK) {
        ESP_LOGE(TAG_WALL, "no JPEG engine");
        return false;
    }
    jpeg_decode_memory_alloc_cfg_t oc = {.buffer_direction = JPEG_DEC_ALLOC_OUTPUT_BUFFER};
    for (int i = 0; i < 2; i++) {
        /* the engine works in 16-pixel blocks: room for the screen rounded up to them (600 rows: 608) */
        frame[i] = jpeg_alloc_decoder_mem(((WALL_W + 15) & ~15) * ((WALL_H + 15) & ~15) * 2, &oc, &frame_size);
        if (!frame[i]) {
            ESP_LOGE(TAG_WALL, "no memory for the photos");
            return false;
        }
    }
    return true;
}

/* one photo: fetched, decoded into the frame not on screen, handed to the wall */
static bool show_photo(const wall_photo_t *p)
{
    char path[96];
    snprintf(path, sizeof path, "/api/wall/photo/%s.jpg?w=%d&h=%d", p->id, WALL_W, WALL_H);
    api_resp_t r = api_request("GET", path, NULL, 3 * 1024 * 1024, NULL);
    if (r.status != 200 || r.len < 100) {
        ESP_LOGW(TAG_WALL, "photo %s: %d %s", p->id, r.status, r.why);
        api_free(&r);
        return false;
    }
    if (r.len > in_size) {
        if (in_buf) free(in_buf);
        jpeg_decode_memory_alloc_cfg_t ic = {.buffer_direction = JPEG_DEC_ALLOC_INPUT_BUFFER};
        in_buf = jpeg_alloc_decoder_mem(r.len + 4096, &ic, &in_size);
        if (!in_buf) {
            in_size = 0;
            api_free(&r);
            return false;
        }
    }
    memcpy(in_buf, r.body, r.len);
    size_t len = r.len;
    api_free(&r);
    jpeg_decode_picture_info_t info;
    if (jpeg_decoder_get_info(in_buf, len, &info) != ESP_OK || info.width > WALL_W || info.height > WALL_H || !info.width || !info.height) {
        ESP_LOGW(TAG_WALL, "photo %s: not a JPEG of the screen's size", p->id);
        return false;
    }
    int next = cur == 0 ? 1 : 0;
    jpeg_decode_cfg_t dc = {
        .output_format = JPEG_DECODE_OUT_FORMAT_RGB565,
        .rgb_order = JPEG_DEC_RGB_ELEMENT_ORDER_BGR,  /* little endian: LVGL's RGB565 */
        .conv_std = JPEG_YUV_RGB_CONV_STD_BT601,
    };
    uint32_t out = 0;
    ui_lock();
    lv_image_cache_drop(&dsc[next]);  /* the buffer is about to change */
    ui_unlock();
    if (jpeg_decoder_process(jpeg, &dc, in_buf, len, frame[next], frame_size, &out) != ESP_OK) {
        ESP_LOGW(TAG_WALL, "photo %s: the JPEG engine refused it", p->id);
        return false;
    }
    /* the engine works in 16-pixel blocks: the rows are as wide as the picture rounded up */
    uint32_t w = (info.width + 15) & ~15u;
    dsc[next] = (lv_image_dsc_t){
        .header = {.magic = LV_IMAGE_HEADER_MAGIC, .cf = LV_COLOR_FORMAT_RGB565, .w = info.width, .h = info.height, .stride = w * 2},
        .data_size = w * info.height * 2,
        .data = frame[next],
    };
    char cap[40] = "";
    if (p->ago == 1) strlcpy(cap, "1 year ago today", sizeof cap);
    else if (p->ago > 1) snprintf(cap, sizeof cap, "%d years ago today", p->ago);
    else if (p->year > 0) snprintf(cap, sizeof cap, "%d", p->year);
    ui_lock();
    ui_wall_photo(&dsc[next], cap);
    shown_photo = *p;
    has_shown = true;
    ui_unlock();
    cur = next;
    return true;
}

static void photo_loop(void *arg)
{
    int wait_s = 2;
    for (;;) {
        ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(wait_s * 1000));
        wall_photo_t pick[3];
        int npick = 0;
        bool want = false;
        ui_lock();
        wait_s = FEED->ok ? FEED->every : 30;
        want = FEED->ok && !strcmp(FEED->bg, "photos") && FEED->nphotos > 0;
        if (want) {
            for (int k = 0; k < 3 && k < FEED->nphotos; k++) {
                pick[npick++] = FEED->photos[(shown + 1 + k) % FEED->nphotos];
            }
        } else if (has_shown) {
            ui_wall_photo(NULL, "");
            has_shown = false;
        }
        ui_unlock();
        if (!want || net_state() != NET_UP || !photo_setup()) {
            continue;
        }
        bool done = false;
        for (int k = 0; k < npick && !done; k++) {
            done = show_photo(&pick[k]);
        }
        ui_lock();
        if (done) {
            /* the position in the list: where the one shown is now */
            for (int i = 0; i < FEED->nphotos; i++) {
                if (!strcmp(FEED->photos[i].id, shown_photo.id)) shown = i;
            }
        } else {
            shown += npick;  /* none of them would come: the next ones next time */
            wait_s = 20;
        }
        if (FEED->nphotos) shown %= FEED->nphotos;
        if (FEED->nphotos == 1) wait_s = 600;
        ui_unlock();
    }
}

void feed_next_photo(void)
{
    if (photo_task) xTaskNotifyGive(photo_task);
}

/* ------------------------------------------------------------------ the taps' calls */

typedef struct {
    void (*fn)(void *);
    void *arg;
} job_t;

static void job_loop(void *arg)
{
    job_t j;
    for (;;) {
        if (xQueueReceive(jobs, &j, portMAX_DELAY)) {
            j.fn(j.arg);
        }
    }
}

void feed_run(void (*fn)(void *), void *arg)
{
    job_t j = {fn, arg};
    if (!jobs || xQueueSend(jobs, &j, 0) != pdTRUE) {
        ESP_LOGW(TAG_WALL, "busy: a tap was dropped");
    }
}

/* what the screens need from their first moment: a feed to read (empty), and the task that runs their calls */
void feed_init(void)
{
    FEED = heap_caps_calloc(1, sizeof *FEED, MALLOC_CAP_SPIRAM);
    assert(FEED);
    strlcpy(FEED->bg, "sky", sizeof FEED->bg);
    FEED->every = 60;
    jobs = xQueueCreate(8, sizeof(job_t));
    xTaskCreatePinnedToCore(job_loop, "taps", 8192, NULL, 4, NULL, 1);
}

void feed_start(void)
{
    xTaskCreatePinnedToCore(feed_loop, "feed", 12288, NULL, 4, &feed_task, 1);
    xTaskCreatePinnedToCore(photo_loop, "photos", 8192, NULL, 3, &photo_task, 1);
}
