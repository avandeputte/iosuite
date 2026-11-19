/* What happened the last time it started. Each step of starting is written down in memory that outlives a restart
 * (not a power cut); when the firmware stops (a panic, an assert, a watchdog), what it said is kept there too.
 * The next start then shows it on the screen in plain words, and goes on without the step that failed when the
 * wall can do without it (the sound, Wi-Fi, updates). After three stops in a row it stays on that screen, so a
 * fault never turns into restarting for ever. */
#include <stdio.h>
#include <string.h>
#include "bsp/esp-bsp.h"
#include "esp_attr.h"
#include "esp_private/panic_internal.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "wall.h"

#define MAGIC 0x10a11b07u

typedef struct {
    uint32_t magic;
    uint32_t step;       /* boot_step_t: the step it was in */
    uint32_t stops;      /* stops in a row */
    uint32_t addr;
    char why[120];
    char task[16];
} boot_note_t;

static RTC_NOINIT_ATTR boot_note_t note;
static boot_note_t last;       /* the note as the last run left it */
static bool stopped;           /* the last run ended in a stop */

static const char *STEP[] = {"starting", "the screen", "the sound", "turning the picture", "the first screen",
                             "the Wi-Fi chip", "the feed", "updates", "running"};

/* the panic handler, with a line of ours first (the linker wraps it: main/CMakeLists.txt). No heap, no locks. */
void __real_esp_panic_handler(panic_info_t *info);

void __wrap_esp_panic_handler(panic_info_t *info)
{
    if (note.magic == MAGIC) {
        const char *w = g_panic_abort ? g_panic_abort_details : info->reason;
        strlcpy(note.why, w ? w : "(no reason given)", sizeof note.why);
        note.addr = (uint32_t)(uintptr_t)info->addr;
        TaskHandle_t t = xTaskGetCurrentTaskHandleForCore(info->core);
        const char *n = t ? pcTaskGetName(t) : NULL;
        strlcpy(note.task, n ? n : "?", sizeof note.task);
    }
    __real_esp_panic_handler(info);
}

void boot_begin(void)
{
    esp_reset_reason_t r = esp_reset_reason();
    bool fault = r == ESP_RST_PANIC || r == ESP_RST_INT_WDT || r == ESP_RST_TASK_WDT || r == ESP_RST_WDT ||
                 r == ESP_RST_BROWNOUT || r == ESP_RST_CPU_LOCKUP;
    if (note.magic == MAGIC && fault) {
        last = note;
        stopped = true;
        if (!last.why[0]) {
            snprintf(last.why, sizeof last.why, r == ESP_RST_BROWNOUT ? "the power dipped (brownout)" : "a watchdog (reset reason %d)", (int)r);
        }
        if (last.step >= sizeof STEP / sizeof STEP[0]) last.step = 0;
        note.stops = last.stops + 1;
    } else {
        memset(&note, 0, sizeof note);
        note.magic = MAGIC;
    }
    note.why[0] = 0;
    note.task[0] = 0;
    note.addr = 0;
    note.step = BOOT_BEGIN;
}

void boot_step(boot_step_t s) { note.step = s; }

bool boot_skip(boot_step_t s) { return stopped && last.step == (uint32_t)s; }

static void settled(void *arg) { note.stops = 0; }

void boot_running(void)
{
    note.step = BOOT_RUNNING;
    /* two minutes without a stop: the count starts again */
    static esp_timer_handle_t t;
    esp_timer_create_args_t a = {.callback = settled, .name = "settled"};
    if (esp_timer_create(&a, &t) == ESP_OK) esp_timer_start_once(t, 120LL * 1000000);
}

/* The last stop on the screen, in LVGL's built-in font (nothing of ours that could be what failed). Returns after
 * 20 seconds, or never when starting should not go on. */
void boot_report(bool can_go_on)
{
    if (!stopped) return;
    bool stay = !can_go_on || note.stops >= 3;
    bsp_display_lock(0);
    /* the picture is turned only when turning it is not what failed */
    if (last.step > BOOT_ROTATE) bsp_display_rotate(lv_display_get_default(), BOARD_ROTATION(S.flip));
    lv_obj_t *scr = lv_screen_active();
    lv_obj_set_style_bg_color(scr, lv_color_black(), 0);
    lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);
    lv_obj_t *l = lv_label_create(scr);
    lv_obj_set_width(l, lv_pct(90));
    lv_label_set_long_mode(l, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_color(l, lv_color_white(), 0);
    lv_obj_set_style_text_font(l, font_symbols(28), 0);
    lv_label_set_text_fmt(l,
        "ioWall %s stopped while it was in: %s\n\n%s\n\ntask %s, at 0x%08x, stop %u in a row\n\n%s",
        wall_version(), STEP[last.step], last.why, last.task[0] ? last.task : "?", (unsigned)last.addr,
        (unsigned)note.stops,
        stay ? "It stays here so it does not restart for ever. Send a photo of this screen; press reset to try again."
             : "Send a photo of this screen. It goes on in 20 seconds, without that part where it can.");
    lv_obj_center(l);
    bsp_display_unlock();
    if (stay) {
        note.stops = 0;   /* a press of reset tries afresh */
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    vTaskDelay(pdMS_TO_TICKS(20000));
    bsp_display_lock(0);
    lv_obj_delete(l);
    bsp_display_unlock();
}
