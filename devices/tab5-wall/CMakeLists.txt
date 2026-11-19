# The wall display for an M5Stack Tab5 (ESP32-P4): ESP-IDF 5.4, LVGL 9 through Espressif's Tab5 board package.
# Build: idf.py build (see README.md). The version is set by the build (WALL_VERSION), else "dev".
cmake_minimum_required(VERSION 3.16)
if(DEFINED ENV{WALL_VERSION})
    set(PROJECT_VER "$ENV{WALL_VERSION}")
else()
    set(PROJECT_VER "dev")
endif()
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(iowall)
