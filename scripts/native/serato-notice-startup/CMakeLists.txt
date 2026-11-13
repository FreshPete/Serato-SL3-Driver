cmake_minimum_required(VERSION 3.15)
project(sl3_notice_startup LANGUAGES CXX)

if(NOT MSVC OR NOT CMAKE_VS_PLATFORM_NAME STREQUAL "x64")
  message(FATAL_ERROR "The notice helper requires MSVC and an x64 build")
endif()

add_library(sl3-owned-notice SHARED notice-startup.cpp)
add_executable(sl3-notice-retirement-tests notice-retirement-tests.cpp)
foreach(target sl3-owned-notice sl3-notice-retirement-tests)
  target_compile_features(${target} PRIVATE cxx_std_17)
  target_compile_options(${target} PRIVATE /W4 /WX /permissive-)
  target_link_libraries(${target} PRIVATE user32)
endforeach()

enable_testing()
add_test(NAME sl3-notice-retirement-tests COMMAND sl3-notice-retirement-tests)
