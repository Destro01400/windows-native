cmake_minimum_required(VERSION 3.24)
project({{APP_NAME}} LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable({{APP_NAME}} WIN32
    src/main.cpp
    src/d2d_window.hpp
    app.manifest
)

target_compile_definitions({{APP_NAME}} PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    NOMINMAX
)

target_compile_options({{APP_NAME}} PRIVATE
    $<$<CXX_COMPILER_ID:MSVC>:/permissive- /utf-8 /EHsc /W4 /WX>
)

target_link_libraries({{APP_NAME}} PRIVATE
    d3d11
    dxgi
    d2d1
    dcomp
    dwmapi
    dwrite
    user32
    windowsapp
)
