# the board, from the environment (../CMakeLists.txt sets it): this file is also read on its own, for what it requires
if("$ENV{WALL_BOARD}" STREQUAL "waveshare7b")
    set(BOARD_PACKAGE waveshare__esp32_p4_wifi6_touch_lcd_7b)   # its full name: the short one is not found below
else()
    set(BOARD_PACKAGE m5stack_tab5)
endif()
idf_component_register(
    SRCS "main.c" "settings.c" "net.c" "api.c" "feed.c" "alarm.c" "ota.c" "boot.c" "power.c"
         "ui.c" "ui_wall.c" "ui_views.c" "ui_setup.c" "ui_panels.c" "icons.c"
    INCLUDE_DIRS "."
    EMBED_FILES "fonts/Inter-Regular.ttf" "fonts/Inter-SemiBold.ttf" "fonts/InterDisplay-Light.ttf"
    REQUIRES ${BOARD_PACKAGE} esp_wifi esp_wifi_remote esp_netif esp_event nvs_flash esp_http_client esp_https_ota
             app_update esp_app_format json esp_driver_jpeg esp_timer mbedtls lwip esp_hw_support
)
# text is cut to fit its buffer on purpose throughout (a long title, a long address)
target_compile_options(${COMPONENT_LIB} PRIVATE -Wno-format-truncation)
# boot.c keeps what a panic said, to show it at the next start
target_link_libraries(${COMPONENT_LIB} INTERFACE "-Wl,--wrap=esp_panic_handler")
# the board (board.h) and the name of its app in the release (ota.c)
if("$ENV{WALL_BOARD}" STREQUAL "waveshare7b")
    target_compile_definitions(${COMPONENT_LIB} PRIVATE WALL_BOARD_WAVESHARE7B=1)
    # Waveshare's package calls memcpy without including string.h, which only compiles when another header happens
    # to bring it in
    idf_component_get_property(board_lib ${BOARD_PACKAGE} COMPONENT_LIB)
    target_compile_options(${board_lib} PRIVATE -include string.h)
else()
    target_compile_definitions(${COMPONENT_LIB} PRIVATE WALL_BOARD_TAB5=1)
endif()
target_compile_definitions(${COMPONENT_LIB} PRIVATE WALL_OTA_FILE="${WALL_FILE}.bin")
