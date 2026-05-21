cmake_minimum_required(VERSION 3.16)
project(TaskDecomposerGUI LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 解决 MSVC 编译 UTF-8 源文件时的中文乱码与字符集解析错误
if(MSVC)
    add_compile_options(/utf-8)
endif()

# 启用 Qt 自动元对象编译和资源处理
set(CMAKE_AUTOMOC ON)
set(CMAKE_AUTOUIC ON)
set(CMAKE_AUTORCC ON)

# 优先查找 Qt 6，找不到则自动降级查找 Qt 5
find_package(Qt6 COMPONENTS Widgets Core Gui QUIET)
if(Qt6_FOUND)
    message(STATUS "发现 Qt 6，链接 Qt6 库")
    set(QT_LIBRARIES Qt6::Widgets Qt6::Core Qt6::Gui)
    # Qt6 可能会由于模块导出名字有细微变动，这里做一个统一处理
    if (TARGET Qt6::Widgets)
        set(QT_LIBRARIES Qt6::Widgets)
    endif()
else()
    find_package(Qt5 COMPONENTS Widgets Core Gui REQUIRED)
    message(STATUS "未发现 Qt 6，链接 Qt5 库")
    set(QT_LIBRARIES Qt5::Widgets Qt5::Core Qt5::Gui)
endif()

add_executable(TaskDecomposerGUI
    main.cpp
    mainwindow.h
    mainwindow.cpp
)

target_link_libraries(TaskDecomposerGUI PRIVATE ${QT_LIBRARIES})
