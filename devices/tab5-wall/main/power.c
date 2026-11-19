/* The battery, on a board that can measure it (board.h: BOARD_BATTERY). The Tab5 has a power monitor (INA226, on the
 * board's I2C bus at 0x41) across a 5 mΩ resistor in the battery's line: the battery's voltage, and the current
 * into it (charging) or out of it (running on it). Read every ten seconds from the screen's tick. Settings shows
 * the readings as they are, since which way the current reads was never seen on a board here. */
#include <stdio.h>
#include "bsp/esp-bsp.h"
#include "driver/i2c_master.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "wall.h"

#if BOARD_BATTERY

#define INA226_ADDR 0x41
#define REG_CONFIG 0x00
#define REG_SHUNT 0x01   /* signed, 2.5 µV a step: across 5 mΩ, half a milliamp */
#define REG_BUS 0x02     /* 1.25 mV a step */

static i2c_master_dev_handle_t dev;
static bool known, on_battery, charging;
static int percent, millivolts, milliamps;

static bool reg_read(uint8_t reg, uint16_t *v)
{
    uint8_t b[2];
    if (i2c_master_transmit_receive(dev, &reg, 1, b, 2, 50) != ESP_OK) return false;
    *v = (uint16_t)(b[0] << 8 | b[1]);
    return true;
}

/* an NP-F battery is two lithium cells: full at 8.4 V, cut off near 6 V; the level by its voltage while it gives
 * what the screen and the Wi-Fi draw */
static int level(int mv)
{
    static const struct { int mv, pct; } curve[] = {
        {8200, 100}, {7900, 80}, {7600, 55}, {7400, 35}, {7200, 20}, {7000, 10}, {6600, 0},
    };
    const int n = sizeof curve / sizeof curve[0];
    if (mv >= curve[0].mv) return 100;
    for (int i = 1; i < n; i++) {
        if (mv >= curve[i].mv) {
            return curve[i].pct + (mv - curve[i].mv) * (curve[i - 1].pct - curve[i].pct) / (curve[i - 1].mv - curve[i].mv);
        }
    }
    return 0;
}

void power_start(void)
{
    i2c_master_bus_handle_t bus = bsp_i2c_get_handle();
    if (!bus || i2c_master_probe(bus, INA226_ADDR, 50) != ESP_OK) {
        ESP_LOGW(TAG_WALL, "no power monitor: the battery's level is not shown");
        return;
    }
    i2c_device_config_t dc = {.dev_addr_length = I2C_ADDR_BIT_LEN_7, .device_address = INA226_ADDR, .scl_speed_hz = 400000};
    if (i2c_master_bus_add_device(bus, &dc, &dev) != ESP_OK) {
        dev = NULL;
        return;
    }
    /* 16 readings averaged, 1.1 ms each, the voltage and the current, all the time (as M5Stack's firmware sets it) */
    uint8_t cfg[3] = {REG_CONFIG, 0x45, 0x27};
    i2c_master_transmit(dev, cfg, sizeof cfg, 50);
    vTaskDelay(pdMS_TO_TICKS(60));
    power_tick();
    ESP_LOGI(TAG_WALL, "battery: %d mV, %d mA, %s", millivolts, milliamps, on_battery ? "running on it" : "on USB power");
}

void power_tick(void)
{
    if (!dev) return;
    uint16_t bus, shunt;
    if (!reg_read(REG_BUS, &bus) || !reg_read(REG_SHUNT, &shunt)) return;
    millivolts = bus * 5 / 4;
    milliamps = (int16_t)shunt / 2;
    /* A battery there at all, and more than a trickle through it either way: out of it (negative, as M5Stack's own
     * firmware reads it) while the board runs on it, into it while USB power charges it. The level shows in both
     * cases, so a board whose current reads the other way round still shows it. */
    bool now = millivolts > 5000 && (milliamps < -30 || milliamps > 30);
    charging = milliamps > 30;
    /* two readings in a row agree before the wall says so: a plug going in or out makes the current jump about */
    static bool last;
    if (now == last || !known) on_battery = now;
    last = now;
    percent = level(millivolts);
    known = true;
}

bool power_on_battery(int *pct)
{
    if (!known || !on_battery) return false;
    if (pct) *pct = percent;
    return true;
}

bool power_charging(void) { return known && on_battery && charging; }

void power_text(char *out, size_t n)
{
    if (!dev) snprintf(out, n, "No power monitor answers on this board");
    else if (!known) snprintf(out, n, "Not read yet");
    else snprintf(out, n, "%d.%02d V, %d mA%s", millivolts / 1000, millivolts % 1000 / 10, milliamps,
                  millivolts <= 5000 ? " (no battery)" : milliamps < -30 ? " (out of the battery)" : milliamps > 30 ? " (into the battery)" : " (battery idle)");
}

#else

void power_start(void) {}
void power_tick(void) {}
bool power_on_battery(int *pct) { return false; }
bool power_charging(void) { return false; }
void power_text(char *out, size_t n) { snprintf(out, n, "This board does not measure its battery"); }

#endif
