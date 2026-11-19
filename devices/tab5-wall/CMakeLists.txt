# The wall display for an ESP32-P4 touch screen: ESP-IDF 5.4, LVGL 9 through the board's package.
# Build: idf.py build (see README.md). The version is set by the build (WALL_VERSION), else "dev".
#
# The board is WALL_BOARD in the environment when the build folder is first made (kept there afterwards):
#   tab5 (the default)   M5Stack Tab5
#   waveshare7b          Waveshare ESP32-P4-WIFI6-Touch-LCD-7B
# WALL_CHIP=rev3 builds for an ESP32-P4 of revision 3 or later, which does not run a build for the earlier ones
# (nor they its).
cmake_minimum_required(VERSION 3.16)
if(DEFINED ENV{WALL_VERSION})
    set(PROJECT_VER "$ENV{WALL_VERSION}")
else()
    set(PROJECT_VER "dev")
endif()

if(NOT DEFINED WALL_BOARD)
    if(DEFINED ENV{WALL_BOARD})
        set(WALL_BOARD "$ENV{WALL_BOARD}")
    else()
        set(WALL_BOARD "tab5")
    endif()
endif()
set(WALL_BOARD "${WALL_BOARD}" CACHE STRING "tab5 or waveshare7b")
if(NOT DEFINED WALL_CHIP)
    if(DEFINED ENV{WALL_CHIP})
        set(WALL_CHIP "$ENV{WALL_CHIP}")
    else()
        set(WALL_CHIP "rev1")
    endif()
endif()
set(WALL_CHIP "${WALL_CHIP}" CACHE STRING "rev1 (an ESP32-P4 before revision 3) or rev3")
if(NOT WALL_BOARD STREQUAL "tab5" AND NOT WALL_BOARD STREQUAL "waveshare7b")
    message(FATAL_ERROR "WALL_BOARD is tab5 or waveshare7b, not '${WALL_BOARD}'")
endif()
if(NOT WALL_CHIP STREQUAL "rev1" AND NOT WALL_CHIP STREQUAL "rev3")
    message(FATAL_ERROR "WALL_CHIP is rev1 or rev3, not '${WALL_CHIP}'")
endif()
# main/idf_component.yml picks the board's package by this
set(ENV{WALL_BOARD} "${WALL_BOARD}")

set(SDKCONFIG_DEFAULTS "sdkconfig.defaults;sdkconfig.${WALL_BOARD}")
if(WALL_CHIP STREQUAL "rev3")
    list(APPEND SDKCONFIG_DEFAULTS "sdkconfig.rev3")
endif()

# the app's name in the release, which the device updates itself from: iowall.bin is the Tab5's
set(WALL_FILE "iowall")
if(NOT WALL_BOARD STREQUAL "tab5")
    string(APPEND WALL_FILE "-${WALL_BOARD}")
endif()
if(WALL_CHIP STREQUAL "rev3")
    string(APPEND WALL_FILE "-rev3")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(iowall)
