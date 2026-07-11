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

# 查找 Qt 6 (必须使用 Qt6)
find_package(Qt6 COMPONENTS Widgets Core Gui REQUIRED)
message(STATUS "发现 Qt 6，链接 Qt6 库")
set(QT_LIBRARIES Qt6::Widgets Qt6::Core Qt6::Gui)
# Qt6 可能会由于模块导出名字有细微变动，这里做一个统一处理
if (TARGET Qt6::Widgets)
    set(QT_LIBRARIES Qt6::Widgets)
endif()

add_executable(TaskDecomposerGUI
    main.cpp
    mainwindow.h
    mainwindow.cpp
    configdialog.h
    configdialog.cpp
    taskcanvas.h
    taskcanvas.cpp
    taskcarditem.h
    taskcarditem.cpp
    relationshipline.h
    relationshipline.cpp
    taskdetailpanel.h
    taskdetailpanel.cpp
    theme.h
    theme.cpp
)

target_link_libraries(TaskDecomposerGUI PRIVATE ${QT_LIBRARIES})

# 自动拷贝 Qt 平台插件到生成的可执行文件目录，解决插件加载失败错误
add_custom_command(TARGET TaskDecomposerGUI POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_directory
        "D:/ProgramData/vcpkg/installed/x64-windows/$<IF:$<CONFIG:Debug>,debug/,>Qt6/plugins/platforms"
        "$<TARGET_FILE_DIR:TaskDecomposerGUI>/platforms"
)
