/* ioWall for the M5Stack Tab5: the start page's wall on the wall. */
#include "bsp/esp-bsp.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "wall.h"

void app_main(void)
{
    boot_begin();
    settings_load();
    if (S.posix[0]) clock_set_zone(S.posix);   /* the clock in local time before the network is up */

    boot_step(BOOT_SCREEN);
    /* as M5Stack's own firmware sets the screen up: two whole-screen buffers in the PSRAM, so a change is drawn and
     * sent in one go (small buffers in internal memory sent a screen in dozens of strips, each turned by itself:
     * a second or two per touch) */
    bsp_display_cfg_t cfg = {
        .lvgl_port_cfg = ESP_LVGL_PORT_INIT_CONFIG(),
        .buffer_size = BSP_LCD_H_RES * BSP_LCD_V_RES,
        .double_buffer = true,
        .flags = {
            .buff_dma = true,
            .buff_spiram = true,
            .sw_rotate = true,   /* turned on its side by the P4's pixel processor (LVGL_PORT_ENABLE_PPA) */
        },
    };
    cfg.lvgl_port_cfg.task_stack = 32768;   /* the TrueType rasterizer draws on this stack */
    cfg.lvgl_port_cfg.task_affinity = 0;
    lv_display_t *disp = bsp_display_start_with_config(&cfg);
    if (!disp) {
        ESP_LOGE(TAG_WALL, "no display");
        return;
    }
    bsp_display_backlight_on();
    ESP_LOGI(TAG_WALL, "screen up; internal memory free: %u", (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));

    /* the last start stopped somewhere: say where, then go on without that part when the wall can do without it */
    boot_report(boot_skip(BOOT_SOUND) || boot_skip(BOOT_WIFI) || boot_skip(BOOT_OTA) || boot_skip(BOOT_RUNNING));

    /* each step waits a moment before the next, so a stop is put down to the step that caused it */
    if (!boot_skip(BOOT_SOUND)) {
        boot_step(BOOT_SOUND);
        alarm_start();   /* before the screens: the volume, and a ring's sound */
        vTaskDelay(pdMS_TO_TICKS(300));
    }

    boot_step(BOOT_ROTATE);
    ui_lock();
    bsp_display_rotate(disp, S.flip ? LV_DISPLAY_ROTATION_270 : LV_DISPLAY_ROTATION_90);
    lv_obj_set_style_bg_color(lv_screen_active(), lv_color_black(), 0);
    ui_unlock();
    vTaskDelay(pdMS_TO_TICKS(600));

    boot_step(BOOT_UI);
    feed_init();   /* the screens read the feed and hand their calls to its task from the first moment */
    ui_lock();
    ui_start(disp);
    ui_unlock();
    vTaskDelay(pdMS_TO_TICKS(1500));

    if (!boot_skip(BOOT_WIFI)) {
        boot_step(BOOT_WIFI);
        net_init();
        vTaskDelay(pdMS_TO_TICKS(3000));
    }
    boot_step(BOOT_FEED);
    feed_start();
    vTaskDelay(pdMS_TO_TICKS(1000));
    if (!boot_skip(BOOT_OTA)) {
        boot_step(BOOT_OTA);
        ota_start();
        vTaskDelay(pdMS_TO_TICKS(500));
    }
    boot_running();
    ESP_LOGI(TAG_WALL, "ioWall %s", wall_version());
}
