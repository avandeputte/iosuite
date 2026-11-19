/* Wi-Fi through the board's ESP32-C6 (ESP-Hosted over SDIO: esp_wifi_remote gives the usual esp_wifi_* calls), and
 * the clock from the network. A dropped connection is tried again by itself, more slowly each time. */
#include <string.h>
#include <sys/time.h>
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_wifi.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "bsp/esp-bsp.h"
#include "wall.h"

static volatile net_state_t state = NET_OFF;
static char ip[20];
static char why[64];
static esp_netif_t *sta;
static bool started, sntp_on;
static int tries;
static esp_timer_handle_t retry_timer;
static SemaphoreHandle_t scan_lock;

net_state_t net_state(void) { return state; }
const char *net_ip(void) { return ip; }
const char *net_why(void) { return why; }

bool clock_is_set(void)
{
    return time(NULL) > 1700000000;  /* after 2023: the network (or the feed) set it */
}

void clock_set_zone(const char *posix)
{
    if (posix && *posix) {
        setenv("TZ", posix, 1);
        tzset();
    }
}

static void retry(void *arg)
{
    if (state != NET_UP && S.ssid[0]) {
        state = NET_CONNECTING;
        esp_wifi_connect();
    }
}

static const char *reason_text(int r)
{
    switch (r) {
    case WIFI_REASON_AUTH_FAIL:
    case WIFI_REASON_4WAY_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_HANDSHAKE_TIMEOUT:
    case WIFI_REASON_MIC_FAILURE:
        return "Wrong password?";
    case WIFI_REASON_NO_AP_FOUND:
        return "Network not found";
    case WIFI_REASON_BEACON_TIMEOUT:
        return "Signal lost";
    default:
        return "Disconnected";
    }
}

static void on_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == WIFI_EVENT && id == WIFI_EVENT_STA_START) {
        if (S.ssid[0]) {
            state = NET_CONNECTING;
            esp_wifi_connect();
        }
    } else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED) {
        wifi_event_sta_disconnected_t *d = data;
        ip[0] = 0;
        snprintf(why, sizeof why, "%s", reason_text(d->reason));
        tries++;
        state = tries >= 3 ? NET_FAILED : NET_CONNECTING;
        /* 2 s, 4 s, 8 s … at most a minute */
        int64_t wait = 2000000LL << (tries < 5 ? tries : 5);
        if (wait > 60000000LL) wait = 60000000LL;
        esp_timer_stop(retry_timer);
        esp_timer_start_once(retry_timer, wait);
        ESP_LOGW(TAG_WALL, "Wi-Fi: %s (reason %d), again in %lld s", why, d->reason, wait / 1000000);
    } else if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *e = data;
        snprintf(ip, sizeof ip, IPSTR, IP2STR(&e->ip_info.ip));
        why[0] = 0;
        tries = 0;
        state = NET_UP;
        ESP_LOGI(TAG_WALL, "Wi-Fi up: %s", ip);
        if (!sntp_on) {
            esp_sntp_config_t c = ESP_NETIF_SNTP_DEFAULT_CONFIG_MULTIPLE(2, ESP_SNTP_SERVER_LIST("pool.ntp.org", "time.google.com"));
            c.start = true;
            esp_netif_sntp_init(&c);
            sntp_on = true;
        }
        feed_refresh();
    }
}

void net_init(void)
{
    scan_lock = xSemaphoreCreateMutex();
    esp_timer_create_args_t ta = {.callback = retry, .name = "wifi-retry"};
    esp_timer_create(&ta, &retry_timer);
    ESP_ERROR_CHECK(esp_netif_init());
    esp_err_t e = esp_event_loop_create_default();
    if (e != ESP_OK && e != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(e);
    }
    BOARD_WIFI_ON();
    vTaskDelay(pdMS_TO_TICKS(300));
    sta = esp_netif_create_default_wifi_sta();
    esp_netif_set_hostname(sta, "iowall");
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    e = esp_wifi_init(&cfg);
    if (e != ESP_OK) {
        ESP_LOGE(TAG_WALL, "Wi-Fi did not start: %s", esp_err_to_name(e));
        snprintf(why, sizeof why, "Wi-Fi did not start (%s)", esp_err_to_name(e));
        state = NET_FAILED;
        return;
    }
    esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, on_event, NULL);
    esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, on_event, NULL);
    esp_wifi_set_storage(WIFI_STORAGE_RAM);
    esp_wifi_set_mode(WIFI_MODE_STA);
    if (S.ssid[0]) {
        wifi_config_t wc = {0};
        strlcpy((char *)wc.sta.ssid, S.ssid, sizeof wc.sta.ssid);
        strlcpy((char *)wc.sta.password, S.wifi_pass, sizeof wc.sta.password);
        wc.sta.threshold.authmode = S.wifi_pass[0] ? WIFI_AUTH_WPA_PSK : WIFI_AUTH_OPEN;
        wc.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
        wc.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
        esp_wifi_set_config(WIFI_IF_STA, &wc);
    }
    esp_wifi_start();
    esp_wifi_set_ps(WIFI_PS_NONE);  /* on USB power: answers quickly */
    started = true;
}

void net_connect(const char *ssid, const char *pass)
{
    strlcpy(S.ssid, ssid, sizeof S.ssid);
    strlcpy(S.wifi_pass, pass ? pass : "", sizeof S.wifi_pass);
    settings_save();
    if (!started) {
        return;
    }
    wifi_config_t wc = {0};
    strlcpy((char *)wc.sta.ssid, S.ssid, sizeof wc.sta.ssid);
    strlcpy((char *)wc.sta.password, S.wifi_pass, sizeof wc.sta.password);
    wc.sta.threshold.authmode = S.wifi_pass[0] ? WIFI_AUTH_WPA_PSK : WIFI_AUTH_OPEN;
    wc.sta.scan_method = WIFI_ALL_CHANNEL_SCAN;
    wc.sta.sort_method = WIFI_CONNECT_AP_BY_SIGNAL;
    tries = 0;
    why[0] = 0;
    esp_timer_stop(retry_timer);
    esp_wifi_disconnect();
    esp_wifi_set_config(WIFI_IF_STA, &wc);
    state = NET_CONNECTING;
    esp_wifi_connect();
}

int net_scan(net_ap_t *out, int max)
{
    /* the first screen asks before the Wi-Fi chip is up: wait for it a while */
    for (int i = 0; i < 100 && !started; i++) {
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    if (!started) {
        return 0;
    }
    xSemaphoreTake(scan_lock, portMAX_DELAY);
    int n = 0;
    wifi_scan_config_t sc = {.show_hidden = false};
    if (state == NET_CONNECTING) {
        esp_timer_stop(retry_timer);
        esp_wifi_disconnect();  /* a scan does not run while it tries to connect */
    }
    if (esp_wifi_scan_start(&sc, true) == ESP_OK) {
        uint16_t count = 0;
        esp_wifi_scan_get_ap_num(&count);
        if (count > 40) count = 40;
        wifi_ap_record_t *recs = calloc(count ? count : 1, sizeof *recs);
        if (recs && esp_wifi_scan_get_ap_records(&count, recs) == ESP_OK) {
            for (int i = 0; i < count && n < max; i++) {
                const char *s = (const char *)recs[i].ssid;
                if (!*s) continue;
                bool dup = false;
                for (int j = 0; j < n; j++) {
                    if (!strcmp(out[j].ssid, s)) { dup = true; break; }
                }
                if (dup) continue;
                strlcpy(out[n].ssid, s, sizeof out[n].ssid);
                out[n].rssi = recs[i].rssi;
                out[n].open = recs[i].authmode == WIFI_AUTH_OPEN;
                n++;
            }
        }
        free(recs);
    }
    xSemaphoreGive(scan_lock);
    if (state != NET_UP && S.ssid[0]) {
        retry(NULL);
    }
    return n;
}
