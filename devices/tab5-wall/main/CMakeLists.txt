idf_component_register(
    SRCS "main.c" "settings.c" "net.c" "api.c" "feed.c" "alarm.c" "ota.c"
         "ui.c" "ui_wall.c" "ui_setup.c" "ui_panels.c" "icons.c"
    INCLUDE_DIRS "."
    EMBED_FILES "fonts/Inter-Regular.ttf" "fonts/Inter-SemiBold.ttf" "fonts/InterDisplay-Light.ttf"
    REQUIRES m5stack_tab5 esp_wifi esp_wifi_remote esp_netif esp_event nvs_flash esp_http_client esp_https_ota
             app_update esp_app_format json esp_driver_jpeg esp_timer mbedtls lwip esp_hw_support
)
# text is cut to fit its buffer on purpose throughout (a long title, a long address)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-format-truncation)
