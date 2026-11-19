/* Made by tools/make_icons.py: do not edit. */
#pragma once
#include "lvgl.h"

typedef enum {ICON_SUN, ICON_MOON, ICON_PARTLY_DAY, ICON_PARTLY_NIGHT, ICON_CLOUD, ICON_RAIN, ICON_THUNDER, ICON_SNOW, ICON_SLEET, ICON_FOG, ICON_WIND, ICON_COUNT} icon_kind_t;

extern const lv_image_dsc_t icon_sun_big;
extern const lv_image_dsc_t icon_moon_big;
extern const lv_image_dsc_t icon_partly_day_big;
extern const lv_image_dsc_t icon_partly_night_big;
extern const lv_image_dsc_t icon_cloud_big;
extern const lv_image_dsc_t icon_rain_big;
extern const lv_image_dsc_t icon_thunder_big;
extern const lv_image_dsc_t icon_snow_big;
extern const lv_image_dsc_t icon_sleet_big;
extern const lv_image_dsc_t icon_fog_big;
extern const lv_image_dsc_t icon_wind_big;
extern const lv_image_dsc_t *const icons_big[ICON_COUNT];
extern const lv_image_dsc_t icon_sun_small;
extern const lv_image_dsc_t icon_moon_small;
extern const lv_image_dsc_t icon_partly_day_small;
extern const lv_image_dsc_t icon_partly_night_small;
extern const lv_image_dsc_t icon_cloud_small;
extern const lv_image_dsc_t icon_rain_small;
extern const lv_image_dsc_t icon_thunder_small;
extern const lv_image_dsc_t icon_snow_small;
extern const lv_image_dsc_t icon_sleet_small;
extern const lv_image_dsc_t icon_fog_small;
extern const lv_image_dsc_t icon_wind_small;
extern const lv_image_dsc_t *const icons_small[ICON_COUNT];

/** The icon for an AccuWeather icon number (1-44); day says which of sun/moon when the number does not. */
icon_kind_t icon_for_accuweather(int n, bool day);

