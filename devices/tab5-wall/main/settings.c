/* What the wall keeps across restarts: one blob in NVS ("wall"/"cfg"). A blob of another version is not read
 * (pre-release: it starts afresh, set up again on the device). */
#include <string.h>
#include "esp_log.h"
#include "nvs_flash.h"
#include "nvs.h"
#include "wall.h"

#define CFG_VERSION 3

wall_settings_t S;
uint32_t VIEWS_OFF;

static void defaults(void)
{
    memset(&S, 0, sizeof S);
    S.version = CFG_VERSION;
    S.clock24 = false;
    S.night_from = 22;
    S.night_to = 6;
    S.day_bright = 90;
    S.night_bright = 12;
    S.volume = 70;
    S.auto_update = true;
    S.snooze_min = 9;
    S.alarms[0] = (wall_alarm_t){.hour = 7, .minute = 0, .days = 0x3e, .on = false, .label = "Weekdays"};
    S.alarms[1] = (wall_alarm_t){.hour = 8, .minute = 30, .days = 0x41, .on = false, .label = "Weekend"};
    S.alarms[2] = (wall_alarm_t){.hour = 6, .minute = 30, .days = 0, .on = false, .label = ""};
    S.alarms[3] = (wall_alarm_t){.hour = 12, .minute = 0, .days = 0, .on = false, .label = ""};
}

void settings_load(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    defaults();
    nvs_handle_t h;
    if (nvs_open("wall", NVS_READONLY, &h) != ESP_OK) {
        return;
    }
    if (nvs_get_u32(h, "views_off", &VIEWS_OFF) != ESP_OK) VIEWS_OFF = 0;
    wall_settings_t got;
    size_t n = sizeof got;
    if (nvs_get_blob(h, "cfg", &got, &n) == ESP_OK && n == sizeof got && got.version == CFG_VERSION) {
        S = got;
        S.ssid[sizeof S.ssid - 1] = 0;
        S.server[sizeof S.server - 1] = 0;
        S.token[sizeof S.token - 1] = 0;
    } else {
        ESP_LOGI(TAG_WALL, "no settings yet (or of another version): set up on the device");
    }
    nvs_close(h);
}

void settings_save(void)
{
    nvs_handle_t h;
    if (nvs_open("wall", NVS_READWRITE, &h) != ESP_OK) {
        ESP_LOGE(TAG_WALL, "settings not saved: NVS");
        return;
    }
    nvs_set_blob(h, "cfg", &S, sizeof S);
    nvs_commit(h);
    nvs_close(h);
}

void settings_save_views(void)
{
    nvs_handle_t h;
    if (nvs_open("wall", NVS_READWRITE, &h) != ESP_OK) return;
    nvs_set_u32(h, "views_off", VIEWS_OFF);
    nvs_commit(h);
    nvs_close(h);
}

void settings_forget_sign_in(void)
{
    S.token[0] = 0;
    S.user[0] = 0;
    settings_save();
}

void settings_reset(void)
{
    defaults();
    settings_save();
    VIEWS_OFF = 0;
    settings_save_views();
}
