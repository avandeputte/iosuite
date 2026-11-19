/* Timers and alarms, and the sound: a tone made here, played on the board's speaker (its codec through the board
 * package). The sound has its own task so a ring never holds up the screen. */
#include <math.h>
#include <string.h>
#include "bsp/esp-bsp.h"
#include "esp_codec_dev.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "wall.h"

#define RATE 16000
#define RING_MAX_S (10 * 60)   /* a ring nobody stops ends by itself after ten minutes */

wall_timer_t TIMER[TIMERS];

static esp_codec_dev_handle_t spk;
static QueueHandle_t sound_q;   /* int: ms of a beep; 0 stop; -1 ring */
static volatile bool ringing;
static int64_t ring_started;
static int64_t snooze_until;     /* esp_timer ms; 0: none */
static char ring_what[32];
static int last_minute = -1;    /* the minute the alarms were last looked at */

static int64_t now_ms(void) { return esp_timer_get_time() / 1000; }

/* ------------------------------------------------------------------ sound */

static int16_t *tone;            /* 100 ms of an 880 Hz tone, stereo, faded in and out */
static const int TONE_N = RATE / 10;

static void make_tone(void)
{
    tone = heap_caps_malloc(TONE_N * 2 * sizeof(int16_t), MALLOC_CAP_SPIRAM);
    if (!tone) return;
    for (int i = 0; i < TONE_N; i++) {
        float env = 1.0f;
        int fade = RATE / 200;
        if (i < fade) env = (float)i / fade;
        if (i > TONE_N - fade) env = (float)(TONE_N - i) / fade;
        int16_t v = (int16_t)(sinf(2 * (float)M_PI * 880 * i / RATE) * 12000 * env);
        tone[2 * i] = tone[2 * i + 1] = v;
    }
}

static void play(int ms)
{
    if (!spk || !tone) return;
    for (int done = 0; done < ms; done += 100) {
        esp_codec_dev_write(spk, tone, TONE_N * 2 * sizeof(int16_t));
    }
}

static void quiet(int ms)
{
    static int16_t zero[RATE / 50 * 2];  /* 20 ms */
    if (!spk) {
        vTaskDelay(pdMS_TO_TICKS(ms));
        return;
    }
    for (int done = 0; done < ms; done += 20) esp_codec_dev_write(spk, zero, sizeof zero);
}

static void sound_task(void *arg)
{
    for (;;) {
        int what;
        if (xQueueReceive(sound_q, &what, portMAX_DELAY) != pdTRUE) continue;
        if (what > 0) {
            play(what < 100 ? 100 : what);
            continue;
        }
        while (what == -1 && ringing) {
            /* beep beep beep, a breath, and again */
            for (int i = 0; i < 3 && ringing; i++) {
                play(200);
                quiet(120);
            }
            quiet(700);
            int next;
            if (xQueueReceive(sound_q, &next, 0) == pdTRUE && next == 0) break;
        }
    }
}

void sound_set_volume(int pct)
{
    if (spk) esp_codec_dev_set_out_vol(spk, pct < 0 ? 0 : pct > 100 ? 100 : pct);
}

void sound_beep(int ms)
{
    if (!sound_q || ringing) return;
    xQueueSend(sound_q, &ms, 0);
}

/* ------------------------------------------------------------------ ringing */

static void ring(const char *what)
{
    strlcpy(ring_what, what && what[0] ? what : "Alarm", sizeof ring_what);
    ringing = true;
    ring_started = now_ms();
    snooze_until = 0;
    int r = -1;
    if (sound_q) xQueueSend(sound_q, &r, 0);
    ui_ringing(true, ring_what);   /* alarm_tick runs holding the UI lock */
}

static void unring(void)
{
    ringing = false;
    int z = 0;
    if (sound_q) xQueueSend(sound_q, &z, 0);
    ui_ringing(false, NULL);
}

bool alarm_ringing(void) { return ringing; }

/* the buttons on the ringing screen (LVGL callbacks: the lock is held) */
void alarm_stop(void)
{
    snooze_until = 0;
    unring();
}

void alarm_snooze(void)
{
    char what[32];
    strlcpy(what, ring_what, sizeof what);
    unring();
    snooze_until = now_ms() + (int64_t)(S.snooze_min ? S.snooze_min : 9) * 60000;
    strlcpy(ring_what, what, sizeof ring_what);
}

/* ------------------------------------------------------------------ timers */

int timer_add(int seconds, const char *label)
{
    for (int i = 0; i < TIMERS; i++) {
        if (TIMER[i].on) continue;
        TIMER[i].on = true;
        TIMER[i].total_s = seconds;
        TIMER[i].ends_ms = now_ms() + (int64_t)seconds * 1000;
        strlcpy(TIMER[i].label, label ? label : "", sizeof TIMER[i].label);
        return i;
    }
    return -1;
}

void timer_cancel(int i)
{
    if (i >= 0 && i < TIMERS) TIMER[i].on = false;
}

/* ------------------------------------------------------------------ alarms */

static bool alarm_on_day(const wall_alarm_t *a, int wday)
{
    return a->days == 0 || (a->days & (1 << wday));
}

time_t alarm_next(void)
{
    if (!clock_is_set()) return 0;
    time_t now = time(NULL), best = 0;
    struct tm t;
    localtime_r(&now, &t);
    for (int i = 0; i < ALARMS; i++) {
        const wall_alarm_t *a = &S.alarms[i];
        if (!a->on) continue;
        for (int d = 0; d < 8; d++) {
            struct tm c = t;
            c.tm_mday += d;
            c.tm_hour = a->hour;
            c.tm_min = a->minute;
            c.tm_sec = 0;
            c.tm_isdst = -1;
            time_t at = mktime(&c);
            if (at <= now) continue;
            struct tm w;
            localtime_r(&at, &w);
            if (!alarm_on_day(a, w.tm_wday)) continue;
            if (!best || at < best) best = at;
            break;
        }
    }
    if (snooze_until) {
        time_t s = now + (time_t)((snooze_until - now_ms()) / 1000);
        if (!best || s < best) best = s;
    }
    return best;
}

/* every second, holding the UI lock */
void alarm_tick(void)
{
    int64_t ms = now_ms();
    for (int i = 0; i < TIMERS; i++) {
        if (TIMER[i].on && ms >= TIMER[i].ends_ms) {
            TIMER[i].on = false;
            char what[32];
            snprintf(what, sizeof what, "Timer%s%s", TIMER[i].label[0] ? ": " : " done", TIMER[i].label);
            ring(what);
        }
    }
    if (ringing && ms - ring_started > RING_MAX_S * 1000LL) unring();
    if (snooze_until && ms >= snooze_until && !ringing) {
        char what[32];
        strlcpy(what, ring_what, sizeof what);
        ring(what);
    }
    if (!clock_is_set()) return;
    time_t now = time(NULL);
    struct tm t;
    localtime_r(&now, &t);
    int minute = t.tm_yday * 1440 + t.tm_hour * 60 + t.tm_min;
    if (minute == last_minute) return;
    bool first = last_minute < 0;
    last_minute = minute;
    if (first && t.tm_sec > 5) return;   /* just started, a minute half gone: not rung late */
    for (int i = 0; i < ALARMS; i++) {
        wall_alarm_t *a = &S.alarms[i];
        if (!a->on || a->hour != t.tm_hour || a->minute != t.tm_min || !alarm_on_day(a, t.tm_wday)) continue;
        if (a->days == 0) {
            a->on = false;   /* once: done */
            settings_save();
        }
        ring(a->label[0] ? a->label : "Alarm");
        break;
    }
}

void alarm_start(void)
{
    make_tone();
    spk = bsp_audio_codec_speaker_init();   /* I2S, the codec and the amplifier */
    if (spk) {
        esp_codec_dev_sample_info_t fs = {
            .sample_rate = RATE,
            .channel = 2,
            .bits_per_sample = 16,
        };
        if (esp_codec_dev_open(spk, &fs) != ESP_CODEC_DEV_OK) {
            ESP_LOGW(TAG_WALL, "speaker did not open");
            spk = NULL;
        } else {
            sound_set_volume(S.volume);
        }
    } else {
        ESP_LOGW(TAG_WALL, "no speaker");
    }
    sound_q = xQueueCreate(8, sizeof(int));
    xTaskCreate(sound_task, "sound", 4096, NULL, 4, NULL);
}
