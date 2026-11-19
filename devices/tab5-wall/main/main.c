/* ioWall for the M5Stack Tab5: the start page's wall on the wall. */
#include "bsp/esp-bsp.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "wall.h"

void app_main(void)
{
    settings_load();
    if (S.posix[0]) clock_set_zone(S.posix);   /* the clock in local time before the network is up */

    bsp_display_cfg_t cfg = {
        .lvgl_port_cfg = ESP_LVGL_PORT_INIT_CONFIG(),
        .buffer_size = BSP_LCD_H_RES * CONFIG_BSP_LCD_DRAW_BUF_HEIGHT,
        .double_buffer = CONFIG_BSP_LCD_DRAW_BUF_DOUBLE,
        .flags = {
            .buff_dma = true,
            .buff_spiram = false,
            .sw_rotate = true,   /* turned on its side by the P4's pixel processor (LVGL_PORT_ENABLE_PPA) */
        },
    };
    cfg.lvgl_port_cfg.task_stack = 16384;
    cfg.lvgl_port_cfg.task_affinity = 0;
    lv_display_t *disp = bsp_display_start_with_config(&cfg);
    if (!disp) {
        ESP_LOGE(TAG_WALL, "no display");
        return;
    }
    bsp_display_backlight_on();
    ESP_LOGI(TAG_WALL, "screen up; internal memory free: %u", (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));

    alarm_start();   /* before the screens: the volume, and a ring's sound */
    ui_lock();
    ui_start(disp);
    ui_unlock();

    net_init();
    feed_start();
    ota_start();
    ESP_LOGI(TAG_WALL, "ioWall %s", wall_version());
}
