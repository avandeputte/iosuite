/* A newer firmware over the air, from this repository's GitHub release "wall-latest": version.txt says which
 * version it holds, iowall.bin is the app (WALL_OTA_FILE: each board has its own). Looked at a minute after starting (to show it in Settings), and at
 * 3 AM it installs a new one when automatic updates are on. A new firmware that does not get as far as a
 * minute of running is rolled back by the bootloader. */
#include <string.h>
#include "esp_app_desc.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"
#include "esp_https_ota.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "wall.h"

#define RELEASE "https://github.com/avandeputte/iosuite/releases/download/wall-latest/"

static volatile ota_state_t state = OTA_IDLE;
static char text[96] = "Not looked yet";
static char found[24];
static volatile int want;        /* 0 nothing, 1 check, 2 check and install */
static TaskHandle_t task;

const char *wall_version(void) { return esp_app_get_description()->version; }
ota_state_t ota_state(void) { return state; }
const char *ota_text(void) { return text; }

static esp_http_client_config_t client(const char *url)
{
    return (esp_http_client_config_t){
        .url = url,
        .timeout_ms = 20000,
        .buffer_size = 4096,      /* GitHub's redirect to its file store is a long Location */
        .buffer_size_tx = 2048,
        .crt_bundle_attach = esp_crt_bundle_attach,
        .max_redirection_count = 4,
        .user_agent = "ioWall " BOARD_NAME,
        .keep_alive_enable = true,
    };
}

/* the version the release holds, into found; false when it could not be read */
static bool latest(void)
{
    esp_http_client_config_t c = client(RELEASE "version.txt");
    esp_http_client_handle_t h = esp_http_client_init(&c);
    if (!h) return false;
    bool ok = false;
    int status = 0;
    for (int hop = 0; hop < 4; hop++) {
        if (esp_http_client_open(h, 0) != ESP_OK) break;
        esp_http_client_fetch_headers(h);
        status = esp_http_client_get_status_code(h);
        if (status >= 300 && status < 400) {
            esp_http_client_set_redirection(h);
            esp_http_client_close(h);
            continue;
        }
        break;
    }
    if (status == 200) {
        char buf[sizeof found] = {0};
        int n = esp_http_client_read(h, buf, sizeof buf - 1);
        if (n > 0) {
            buf[n] = 0;
            char *e = buf + strlen(buf);
            while (e > buf && (e[-1] == '\n' || e[-1] == '\r' || e[-1] == ' ')) *--e = 0;
            strlcpy(found, buf, sizeof found);
            ok = found[0] != 0;
        }
    } else {
        snprintf(text, sizeof text, "Could not look (%d)", status);
    }
    esp_http_client_close(h);
    esp_http_client_cleanup(h);
    return ok;
}

static void install(void)
{
    state = OTA_UPDATING;
    snprintf(text, sizeof text, "Installing %s…", found);
    esp_http_client_config_t c = client(RELEASE WALL_OTA_FILE);
    esp_https_ota_config_t o = {.http_config = &c};
    esp_https_ota_handle_t h = NULL;
    if (esp_https_ota_begin(&o, &h) != ESP_OK) {
        state = OTA_FAILED;
        strlcpy(text, "The update could not start", sizeof text);
        return;
    }
    int size = esp_https_ota_get_image_size(h);
    esp_err_t e;
    while ((e = esp_https_ota_perform(h)) == ESP_ERR_HTTPS_OTA_IN_PROGRESS) {
        int got = esp_https_ota_get_image_len_read(h);
        if (size > 0) snprintf(text, sizeof text, "Installing %s… %d%%", found, got * 100 / size);
    }
    if (e != ESP_OK || !esp_https_ota_is_complete_data_received(h)) {
        esp_https_ota_abort(h);
        state = OTA_FAILED;
        snprintf(text, sizeof text, "The update failed (%s)", esp_err_to_name(e));
        return;
    }
    if (esp_https_ota_finish(h) != ESP_OK) {
        state = OTA_FAILED;
        strlcpy(text, "The update was not whole", sizeof text);
        return;
    }
    strlcpy(text, "Restarting…", sizeof text);
    vTaskDelay(pdMS_TO_TICKS(1500));
    esp_restart();
}

static void check(bool and_install)
{
    if (net_state() != NET_UP) {
        state = OTA_FAILED;
        strlcpy(text, "No Wi-Fi", sizeof text);
        return;
    }
    state = OTA_CHECKING;
    strlcpy(text, "Looking for a newer version…", sizeof text);
    if (!latest()) {
        state = OTA_FAILED;
        if (!strncmp(text, "Looking", 7)) strlcpy(text, "Could not look for a newer version", sizeof text);
        return;
    }
    /* "dev": built by hand, never replaced by itself */
    if (!strcmp(found, wall_version()) || (!strcmp(wall_version(), "dev") && !and_install)) {
        state = OTA_NONE;
        snprintf(text, sizeof text, "Up to date (%s)", wall_version());
        return;
    }
    state = OTA_FOUND;
    snprintf(text, sizeof text, "Version %s is out", found);
    if (and_install) install();
}

static void ota_loop(void *arg)
{
    bool valid = false, looked = false;
    int last_day = -1;
    for (;;) {
        uint32_t n = ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(30000));
        int64_t up = esp_timer_get_time() / 1000000;
        if (!valid && up > 60) {
            esp_ota_mark_app_valid_cancel_rollback();
            valid = true;
        }
        if (n && want) {
            int w = want;
            want = 0;
            check(w == 2);
            continue;
        }
        if (!looked && up > 60 && net_state() == NET_UP) {
            looked = true;
            check(false);
        }
        if (S.auto_update && clock_is_set() && strcmp(wall_version(), "dev")) {
            time_t now = time(NULL);
            struct tm t;
            localtime_r(&now, &t);
            if (t.tm_hour == 3 && t.tm_yday != last_day && !alarm_ringing()) {
                last_day = t.tm_yday;
                check(true);
            }
        }
    }
}

void ota_check_now(bool and_install)
{
    want = and_install ? 2 : 1;
    if (task) xTaskNotifyGive(task);
}

void ota_start(void)
{
    xTaskCreate(ota_loop, "ota", 8192, NULL, 2, &task);
}
