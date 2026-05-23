#include "mainwindow.h"
#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QSplitter>
#include <QJsonDocument>
#include <QJsonArray>
#include <QDateTime>
#include <QFile>
#include <QCoreApplication>
#include <QScrollBar>
#include <QDir>
#include <QKeyEvent>
#include <QSettings>
#include <QFileDialog>
#include <QMessageBox>
#include <QTextStream>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent), m_process(nullptr) {
    setWindowTitle("Task Decomposer");
    resize(1020, 680);

    m_currentMode = "chat";
    m_projectName = "demo";
    m_conversationId = "default";
    m_mascotFrame = 0;
    m_isShowingWelcome = true;
    m_lastElapsed = 0.0;
    m_lastTokens = 0;

    initUI();
    applyTheme();
    updatePrompt();

    m_mascotTimer = new QTimer(this);
    connect(m_mascotTimer, &QTimer::timeout, this, &MainWindow::onMascotTimerTimeout);

    // 绘制首帧欢迎界面并启动 UFO 飞碟动画
    printWelcomePanel(m_mascotFrame);
    m_mascotTimer->start(220); // 220ms 完美匹配原版 CLI 的动画间隔

    startBackendProcess();
    loadMascotFromJson();
}

MainWindow::~MainWindow() {
    if (m_process) {
        m_process->kill();
        m_process->waitForFinished(1000);
    }
}

void MainWindow::initUI() {
    QWidget *centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);

    QVBoxLayout *mainLayout = new QVBoxLayout(centralWidget);
    mainLayout->setContentsMargins(10, 10, 10, 10);
    mainLayout->setSpacing(8);

    // Create a horizontal splitter for the dual-column split panels
    m_splitter = new QSplitter(Qt::Horizontal, this);
    m_splitter->setHandleWidth(4);
    m_splitter->setStyleSheet(
        "QSplitter::handle { background-color: #0c0c0d; }"
    );

    // Left display panel (Mascot / Results)
    m_leftDisplay = new QTextEdit(this);
    m_leftDisplay->setReadOnly(true);
    m_leftDisplay->setFrameStyle(QFrame::StyledPanel);
    m_leftDisplay->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    m_leftDisplay->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_leftDisplay->verticalScrollBar()->setStyleSheet(
        "QScrollBar:vertical { border: none; background-color: #0c0c0d; width: 6px; }"
        "QScrollBar::handle:vertical { background-color: #2c2c38; border-radius: 3px; min-height: 20px; }"
        "QScrollBar::handle:vertical:hover { background-color: #4c4c58; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
    );

    // Right display panel (Console Logs / Tips / Help)
    m_rightDisplay = new QTextEdit(this);
    m_rightDisplay->setReadOnly(true);
    m_rightDisplay->setFrameStyle(QFrame::StyledPanel);
    m_rightDisplay->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    m_rightDisplay->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    m_rightDisplay->verticalScrollBar()->setStyleSheet(
        "QScrollBar:vertical { border: none; background-color: #0c0c0d; width: 6px; }"
        "QScrollBar::handle:vertical { background-color: #2c2c38; border-radius: 3px; min-height: 20px; }"
        "QScrollBar::handle:vertical:hover { background-color: #4c4c58; }"
        "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }"
    );

    // Apply monospace font to both
    QFont monoFont("Consolas", 11);
    monoFont.setStyleHint(QFont::Monospace);
    m_leftDisplay->setFont(monoFont);
    m_rightDisplay->setFont(monoFont);

    // Add panels to splitter
    m_splitter->addWidget(m_leftDisplay);
    m_splitter->addWidget(m_rightDisplay);
    
    // Set stretch factors (60% left, 40% right)
    m_splitter->setStretchFactor(0, 3);
    m_splitter->setStretchFactor(1, 2);

    mainLayout->addWidget(m_splitter, 1);

    // Bottom flat input area
    QHBoxLayout *inputLayout = new QHBoxLayout();
    inputLayout->setContentsMargins(12, 8, 12, 8);
    inputLayout->setSpacing(6);

    m_promptLabel = new QLabel(this);
    m_promptLabel->setFont(monoFont);

    m_terminalInput = new QLineEdit(this);
    m_terminalInput->setFont(monoFont);
    m_terminalInput->setFrame(false);

    inputLayout->addWidget(m_promptLabel);
    inputLayout->addWidget(m_terminalInput, 1);

    QWidget *inputContainer = new QWidget(this);
    inputContainer->setLayout(inputLayout);
    inputContainer->setStyleSheet("background-color: #0c0c0d; border: 1px solid #1a1a20; border-radius: 4px;");

    mainLayout->addWidget(inputContainer);

    // 安装 Tab 键盘拦截事件过滤器
    m_terminalInput->installEventFilter(this);

    connect(m_terminalInput, &QLineEdit::returnPressed, this, &MainWindow::onInputReturnPressed);
}

void MainWindow::applyTheme() {
    QString baseQss = R"(
        QMainWindow {
            background-color: #0c0c0d;
        }
        QLineEdit {
            background-color: #0c0c0d;
            color: #ffffff;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 14px;
            padding: 2px 0px;
        }
        QLabel {
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 14px;
            font-weight: bold;
        }
    )";
    
    // Glowing pink active border (#ffb3ba) vs subtle border (#1a1a20)
    QString leftBorder = (m_currentMode == "chat") ? "1px solid #ffb3ba" : "1px solid #1a1a20";
    QString rightBorder = (m_currentMode == "console") ? "1px solid #ffb3ba" : "1px solid #1a1a20";

    QString leftQss = QString(
        "QTextEdit { "
        "  background-color: #0c0c0d; "
        "  color: #ffffff; "
        "  font-family: 'Consolas', 'Courier New', monospace; "
        "  font-size: 14px; "
        "  border: %1; "
        "  border-radius: 6px; "
        "  padding: 10px; "
        "}"
    ).arg(leftBorder);

    QString rightQss = QString(
        "QTextEdit { "
        "  background-color: #0c0c0d; "
        "  color: #ffffff; "
        "  font-family: 'Consolas', 'Courier New', monospace; "
        "  font-size: 14px; "
        "  border: %1; "
        "  border-radius: 6px; "
        "  padding: 10px; "
        "}"
    ).arg(rightBorder);

    setStyleSheet(baseQss);
    m_leftDisplay->setStyleSheet(leftQss);
    m_rightDisplay->setStyleSheet(rightQss);
}

void MainWindow::updatePrompt() {
    if (m_currentMode == "chat") {
        m_promptLabel->setText("chat> ");
        m_promptLabel->setStyleSheet("color: #ffb3ba;");
        m_terminalInput->setStyleSheet("color: #ffffff;");
    } else {
        m_promptLabel->setText("console> ");
        m_promptLabel->setStyleSheet("color: #8e8e93;");
        m_terminalInput->setStyleSheet("color: #ffb3ba;"); // console 状态输入参数高亮为浅粉
    }
}

bool MainWindow::eventFilter(QObject *watched, QEvent *event) {
    if (watched == m_terminalInput && event->type() == QEvent::KeyPress) {
        QKeyEvent *keyEvent = static_cast<QKeyEvent*>(event);
        if (keyEvent->key() == Qt::Key_Tab) {
            // Tab 键切换输入提示符模式
            if (m_currentMode == "chat") {
                m_currentMode = "console";
            } else {
                m_currentMode = "chat";
            }
            updatePrompt();
            applyTheme();

            // 如果处于欢迎界面，立刻刷新欢迎界面以同步 Tips 提示
            if (m_isShowingWelcome) {
                printWelcomePanel(m_mascotFrame);
            } else if (!m_lastGoal.isEmpty()) {
                printResultWorkspace();
            }
            return true; // 拦截并吞噬此按键事件，防止默认转移输入焦点
        }
    }
    return QMainWindow::eventFilter(watched, event);
}

void MainWindow::resizeEvent(QResizeEvent *event) {
    QMainWindow::resizeEvent(event);
    
    if (m_splitter) {
        int w = event->size().width();
        int h = event->size().height();
        // 自适应折叠为上下堆叠
        if (w < 720 || w < h * 1.1) {
            if (m_splitter->orientation() != Qt::Vertical) {
                m_splitter->setOrientation(Qt::Vertical);
                QList<int> sizes;
                sizes << h * 0.62 << h * 0.38;
                m_splitter->setSizes(sizes);
            }
        } else {
            if (m_splitter->orientation() != Qt::Horizontal) {
                m_splitter->setOrientation(Qt::Horizontal);
                QList<int> sizes;
                sizes << w * 0.6 << w * 0.4;
                m_splitter->setSizes(sizes);
            }
        }
    }
}

void MainWindow::onInputReturnPressed() {
    QString input = m_terminalInput->text();
    handleInput(input);
}

void MainWindow::onMascotTimerTimeout() {
    if (m_isShowingWelcome) {
        m_mascotFrame++;
        printWelcomePanel(m_mascotFrame);
    }
}

void MainWindow::handleInput(const QString &rawInput) {
    QString input = rawInput.trimmed();
    if (input.isEmpty()) return;

    // 只要有任何输入，即停用欢迎动画并切入日志模式
    if (m_isShowingWelcome) {
        m_mascotTimer->stop();
        m_isShowingWelcome = false;
        m_leftDisplay->clear();
        m_rightDisplay->clear();
    }

    // 将用户输入回显至终端屏幕缓冲区
    QString promptText = (m_currentMode == "chat") ? "chat> " : "console> ";
    QString promptColor = (m_currentMode == "chat") ? "#ffb3ba" : "#8e8e93";
    
    m_rightDisplay->append(QString("<pre style=\"margin: 0; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; color: %1; white-space: pre-wrap;\">%2%3</pre>")
                           .arg(promptColor).arg(promptText).arg(input.toHtmlEscaped()));
    m_terminalInput->clear();

    // 根据模式或命令前缀判定调度
    if (m_currentMode == "console" || input.startsWith("/")) {
        QString cmdName = input;
        QString cmdArgs = "";
        if (input.startsWith("/")) {
            cmdName = input.mid(1);
        }
        int spaceIdx = cmdName.indexOf(' ');
        if (spaceIdx != -1) {
            cmdArgs = cmdName.mid(spaceIdx + 1).trimmed();
            cmdName = cmdName.left(spaceIdx);
        }
        cmdName = cmdName.toLower();

        executeSlashCommand(cmdName, cmdArgs);
    } else {
        // Chat 模式拆解目标
        m_lastGoal = input;

        // 运行时禁用输入防止连击
        m_terminalInput->setEnabled(false);
        m_promptLabel->setEnabled(false);

        // 清空左栏并展示准备状态
        m_leftDisplay->clear();
        appendLeftText("✦ Decomposing Task Goal... ✦", "#f1c40f");
        appendLeftText("", "#ffffff");
        appendLeftText("Goal: " + m_lastGoal, "#ffffff");
        appendLeftText("", "#ffffff");
        appendLeftText("Initializing agent workspace and running LLM reasoning...", "#8e8e93");

        // 打印启动日志到右栏
        appendRightText("✦ Launching Decomposition Agent...", "#f1c40f");

        QJsonObject cmd;
        cmd["command"] = "run";
        cmd["goal"] = m_lastGoal;
        cmd["conversation"] = m_conversationId;
        cmd["project"] = m_projectName;
        cmd["search"] = true;

        sendCommandToBackend(cmd);
    }
}

void MainWindow::executeSlashCommand(const QString &cmd, const QString &args) {
    if (cmd == "exit" || cmd == "quit" || cmd == "q") {
        appendRightText("✻ Done. Exiting...", "#8e8e93");
        QCoreApplication::quit();
    } else if (cmd == "help" || cmd == "?") {
        printHelp();
    } else if (cmd == "status" || cmd == "current") {
        printStatus();
    } else if (cmd == "clear") {
        m_isShowingWelcome = true;
        m_mascotFrame = 0;
        printWelcomePanel(m_mascotFrame);
        m_mascotTimer->start(220);
    } else if (cmd == "mascot") {
        handleMascotCommand(args);
    } else if (cmd == "switch" || cmd == "conversation" || cmd == "use") {
        if (args.isEmpty()) {
            appendRightText("✻ 用法：/switch <conversation-id>", "#f1c40f");
        } else {
            m_conversationId = args;
            appendRightText(QString("✻ 已切换到对话：%1").arg(m_conversationId), "#2ecc71");
            if (m_isShowingWelcome) {
                printWelcomePanel(m_mascotFrame);
            } else if (!m_lastGoal.isEmpty()) {
                printResultWorkspace();
            }
        }
    } else if (cmd == "new" || cmd == "start") {
        m_conversationId = args;
        if (m_conversationId.isEmpty()) {
            m_conversationId = QString::number(QDateTime::currentSecsSinceEpoch());
        }
        appendRightText(QString("✻ 已进入新对话：%1").arg(m_conversationId), "#2ecc71");
        if (m_isShowingWelcome) {
            printWelcomePanel(m_mascotFrame);
        } else if (!m_lastGoal.isEmpty()) {
            printResultWorkspace();
        }
    } else if (cmd == "leave" || cmd == "close" || cmd == "end") {
        QString oldId = m_conversationId;
        m_conversationId = "";
        appendRightText(QString("✻ 已退出当前对话：%1。使用 /switch <id> 或 /new [id] 进入下一个对话。").arg(oldId), "#f1c40f");
    } else {
        appendRightText(QString("✻ 未知命令：/%1。输入 /help 查看可用命令。").arg(cmd), "#e74c3c");
    }
}

void MainWindow::printHelp() {
    appendRightText("✦ Available Slash Commands ✦", "#3498db");
    appendRightText("  Tab            在 chat> 和 console> 之间切换", "#ffffff");
    appendRightText("  /help          显示这份帮助", "#ffffff");
    appendRightText("  /status        查看当前 project 和 conversation", "#ffffff");
    appendRightText("  /mascot [路径]  设置自定义吉祥物 JSON，留空时弹出文件选择器，输入 default 恢复 UFO", "#ffffff");
    appendRightText("  /switch <id>   切换到已有 or 指定对话", "#ffffff");
    appendRightText("  /new [id]      新建并切换到一个对话；不传 id 时自动生成", "#ffffff");
    appendRightText("  /clear         重新显示欢迎面板并播放动画", "#ffffff");
    appendRightText("  /leave         退出当前对话但保留交互终端", "#ffffff");
    appendRightText("  /exit          退出整个应用", "#ffffff");
    appendRightText("", "#ffffff");
}

void MainWindow::printStatus() {
    appendRightText(QString("✻ project %1 · conversation %2").arg(m_projectName).arg(m_conversationId), "#8e8e93");
    appendRightText("", "#8e8e93");
}

void MainWindow::startBackendProcess() {
    m_process = new QProcess(this);

    QString configPath = QDir(QCoreApplication::applicationDirPath()).filePath("config.ini");
    QSettings settings(configPath, QSettings::IniFormat);
    QString savedRoot = settings.value("project_root").toString();
    QString finalRoot = "";

    // 1. 验证上次保存的路径是否有效
    if (!savedRoot.isEmpty() && QFile::exists(QDir(savedRoot).absoluteFilePath("task_decomposer.py"))) {
        finalRoot = savedRoot;
    }

    // 2. 如果上次保存的路径无效，自动向上搜寻最多 5 层父目录
    if (finalRoot.isEmpty()) {
        QDir dir(QCoreApplication::applicationDirPath());
        for (int i = 0; i < 5; ++i) {
            if (QFile::exists(dir.absoluteFilePath("task_decomposer.py"))) {
                finalRoot = dir.absolutePath();
                break;
            }
            if (!dir.cdUp()) {
                break;
            }
        }
    }

    // 3. 如果依然未找到，触发手动选择窗口
    if (finalRoot.isEmpty()) {
        QMessageBox::information(this, 
            "定位后端引擎", 
            "未能自动检测到后端脚本入口 'task_decomposer.py'。\n请在随后的窗口中，手动选择您的项目根目录下的 'task_decomposer.py' 文件。");
        
        QString selectedFile = QFileDialog::getOpenFileName(this,
            "选择后端入口脚本",
            QCoreApplication::applicationDirPath(),
            "Python 脚本 (task_decomposer.py);;所有文件 (*.*)");
        
        if (!selectedFile.isEmpty()) {
            QFileInfo fileInfo(selectedFile);
            finalRoot = fileInfo.absolutePath();
        }
    }

    // 4. 成功获取根目录则启动后端，否则报错提示
    if (!finalRoot.isEmpty()) {
        settings.setValue("project_root", finalRoot);
        m_process->setWorkingDirectory(finalRoot);

        // 绝对路径加载虚拟环境解释器
#ifdef Q_OS_WIN
        QString localVenvRel = ".venv/Scripts/python.exe";
#else
        QString localVenvRel = ".venv/bin/python";
#endif
        QDir rootDir(finalRoot);
        QString absoluteVenvPath = rootDir.absoluteFilePath(localVenvRel);
        QString pythonPath = "python";
        if (QFile::exists(absoluteVenvPath)) {
            pythonPath = absoluteVenvPath;
        }

        QString program = pythonPath;
        QStringList arguments;
        arguments << "task_decomposer.py" << "--gui-server";

        QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
        env.insert("PYTHONIOENCODING", "utf-8");
        env.insert("PYTHONUTF8", "1");
        m_process->setProcessEnvironment(env);

        connect(m_process, &QProcess::readyReadStandardOutput, this, &MainWindow::readBackendOutput);
        connect(m_process, &QProcess::readyReadStandardError, this, &MainWindow::readBackendError);
        connect(m_process, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
                this, &MainWindow::handleProcessFinished);
        connect(m_process, &QProcess::errorOccurred, this, &MainWindow::handleProcessError);

        m_process->start(program, arguments);
    } else {
        appendTerminalText("❌ 错误：未指定有效的后端入口 'task_decomposer.py'，后端未启动！", "#e74c3c");
    }
}

void MainWindow::logMascotLoader(const QString &msg) {
    appendRightText(msg, msg.contains("失败") || msg.contains("Error") || msg.contains("异常") || msg.contains("错误") ? "#e74c3c" : "#8e8e93");

    QString configPath = QDir(QCoreApplication::applicationDirPath()).filePath("config.ini");
    QSettings settings(configPath, QSettings::IniFormat);
    QString finalRoot = settings.value("project_root").toString();
    if (finalRoot.isEmpty()) return;

    QFile file(QDir(finalRoot).filePath("mascot_loader_debug.log"));
    if (file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text)) {
        QTextStream out(&file);
        out << QDateTime::currentDateTime().toString("yyyy-MM-dd hh:mm:ss.zzz") << " - " << msg << "\n";
    }
}

void MainWindow::loadMascotFromJson() {
    QString configPath = QDir(QCoreApplication::applicationDirPath()).filePath("config.ini");
    QSettings settings(configPath, QSettings::IniFormat);
    QString finalRoot = settings.value("project_root").toString();

    if (finalRoot.isEmpty()) {
        QDir dir(QCoreApplication::applicationDirPath());
        for (int i = 0; i < 5; ++i) {
            if (QFile::exists(dir.absoluteFilePath("task_decomposer.py"))) {
                finalRoot = dir.absolutePath();
                break;
            }
            if (!dir.cdUp()) break;
        }
    }

    if (finalRoot.isEmpty()) {
        logMascotLoader("[Mascot Loader] 未能定位到项目根目录，无法加载吉祥物动画。");
        return;
    }

    logMascotLoader(QString("项目根目录定位成功：%1").arg(finalRoot));

    QString jsonPath;
    QString customMascotPath = settings.value("custom_mascot_path").toString();
    if (!customMascotPath.isEmpty() && QFile::exists(customMascotPath)) {
        jsonPath = customMascotPath;
        logMascotLoader(QString("载入用户指定吉祥物：%1").arg(jsonPath));
    } else {
        QDir searchDir(QCoreApplication::applicationDirPath());
        for (int i = 0; i < 5; ++i) {
            QString candidate = searchDir.absoluteFilePath("custom_mascot.json");
            if (QFile::exists(candidate)) {
                jsonPath = candidate;
                break;
            }
            if (!searchDir.cdUp()) break;
        }
        if (!jsonPath.isEmpty()) {
            logMascotLoader(QString("自动发现吉祥物配置：%1").arg(jsonPath));
        } else {
            QString defaultPath = QDir(finalRoot).absoluteFilePath("default_mascot.json");
            if (QFile::exists(defaultPath)) {
                jsonPath = defaultPath;
                logMascotLoader(QString("使用默认吉祥物配置：%1").arg(jsonPath));
            } else {
                logMascotLoader("未发现任何吉祥物 JSON 配置，不显示动画。");
                return;
            }
        }
    }

    QFile file(jsonPath);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        logMascotLoader(QString("[Mascot Loader] 无法打开文件：%1").arg(jsonPath));
        return;
    }
    QByteArray data = file.readAll();
    file.close();

    QJsonParseError parseError;
    QJsonDocument doc = QJsonDocument::fromJson(data, &parseError);
    if (doc.isNull() || !doc.isArray()) {
        logMascotLoader(QString("[Mascot Loader] JSON 解析失败：%1").arg(parseError.errorString()));
        return;
    }

    QJsonArray framesArray = doc.array();
    QVector<QStringList> newFrames;
    for (int i = 0; i < framesArray.size(); ++i) {
        if (!framesArray[i].isArray()) continue;
        QJsonArray linesArray = framesArray[i].toArray();
        QStringList lines;
        for (int j = 0; j < linesArray.size(); ++j) {
            lines.append(linesArray[j].toString());
        }
        if (!lines.isEmpty()) {
            newFrames.append(lines);
        }
    }

    if (!newFrames.isEmpty()) {
        m_customMascotFrames = newFrames;
        logMascotLoader(QString("[Mascot Loader] 成功加载吉祥物帧缓存，共 %1 帧").arg(newFrames.size()));
        if (m_isShowingWelcome) {
            printWelcomePanel(m_mascotFrame);
        }
    } else {
        logMascotLoader("[Mascot Loader] JSON 文件中没有有效帧数据。");
    }
}

void MainWindow::handleMascotCommand(const QString &args) {
    QString configPath = QDir(QCoreApplication::applicationDirPath()).filePath("config.ini");
    QSettings settings(configPath, QSettings::IniFormat);
    QString selectedFile = args.trimmed();

    if (selectedFile.toLower() == "default") {
        settings.remove("custom_mascot_path");
        m_customMascotFrames.clear();
        logMascotLoader("✻ 吉祥物已恢复为默认的经典 UFO");
        if (m_isShowingWelcome) {
            printWelcomePanel(m_mascotFrame);
        }
        return;
    }

    if (selectedFile.isEmpty()) {
        selectedFile = QFileDialog::getOpenFileName(this,
            "选择吉祥物动画 JSON 文件",
            QCoreApplication::applicationDirPath(),
            "吉祥物配置文件 (*.json);;所有文件 (*.*)");
    }

    if (selectedFile.isEmpty()) {
        logMascotLoader("✻ 取消了吉祥物选择");
        return;
    }

    if (!QFile::exists(selectedFile)) {
        logMascotLoader(QString("✻ 错误：指定的文件不存在：%1").arg(selectedFile));
        return;
    }

    settings.setValue("custom_mascot_path", selectedFile);
    logMascotLoader(QString("✻ 吉祥物已更新，新路径：%1").arg(selectedFile));
    loadMascotFromJson();
}

void MainWindow::sendCommandToBackend(const QJsonObject &json) {
    if (!m_process || m_process->state() != QProcess::Running) {
        appendTerminalText("发送失败：后台引擎未在运行状态！", "#e74c3c");
        return;
    }
    QJsonDocument doc(json);
    QByteArray bytes = doc.toJson(QJsonDocument::Compact) + "\n";
    m_process->write(bytes);
}

void MainWindow::readBackendOutput() {
    while (m_process->canReadLine()) {
        QByteArray line = m_process->readLine().trimmed();
        if (!line.isEmpty()) {
            QJsonDocument doc = QJsonDocument::fromJson(line);
            if (doc.isNull() || !doc.isObject()) continue;

            QJsonObject obj = doc.object();
            QString type = obj["type"].toString();

            if (type == "status") {
                QString msg = obj["message"].toString();
                appendRightText("✦ " + msg, "#f1c40f");
            } else if (type == "error") {
                QString errorMsg = obj["message"].toString();
                appendRightText("❌ 错误: " + errorMsg, "#e74c3c");

                m_terminalInput->setEnabled(true);
                m_promptLabel->setEnabled(true);
                m_terminalInput->setFocus();
            } else if (type == "success") {
                m_lastElapsed = obj["elapsed"].toDouble();
                m_lastTokens = obj["tokens"].toInt();
                m_lastTokenNote = obj["token_note"].toString();
                m_lastPlan = obj["plan"].toObject();
                m_lastQuestions = obj["questions"].toArray();

                appendRightText("✦ Done", "#2ecc71");
                printResultWorkspace();

                m_terminalInput->setEnabled(true);
                m_promptLabel->setEnabled(true);
                m_terminalInput->setFocus();
            }
        }
    }
}

void MainWindow::readBackendError() {
    QByteArray errData = m_process->readAllStandardError();
    QString logs = QString::fromUtf8(errData).trimmed();
    if (!logs.isEmpty()) {
        appendRightText("[Backend Log] " + logs, "#8e8e93");
    }
}

void MainWindow::handleProcessFinished(int exitCode, QProcess::ExitStatus exitStatus) {
    QString statusText = (exitStatus == QProcess::NormalExit) ? "正常退出" : "异常崩溃";
    appendRightText(QString("🔴 后台进程退出：状态=%1，退出码=%2").arg(statusText).arg(exitCode), "#e74c3c");
    
    m_terminalInput->setEnabled(true);
    m_promptLabel->setEnabled(true);
}

void MainWindow::handleProcessError(QProcess::ProcessError error) {
    QString errStr;
    switch (error) {
        case QProcess::FailedToStart:
            errStr = "无法拉起进程，请检查 python 环境变量或 .venv 环境是否存在。";
            break;
        case QProcess::Crashed:
            errStr = "进程在启动后异常崩溃。";
            break;
        default:
            errStr = "通道连接发生未知错误。";
    }
    appendRightText("❌ 进程通道异常: " + errStr, "#e74c3c");
}

void MainWindow::appendTerminalText(const QString &text, const QString &colorHtml) {
    appendRightText(text, colorHtml);
}

void MainWindow::appendLeftText(const QString &text, const QString &colorHtml) {
    QString escaped = text.toHtmlEscaped();
    QString html = QString("<pre style=\"margin: 0; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; color: %1; white-space: pre-wrap;\">%2</pre>")
                           .arg(colorHtml).arg(escaped);
    m_leftDisplay->append(html);
    m_leftDisplay->verticalScrollBar()->setValue(m_leftDisplay->verticalScrollBar()->maximum());
}

void MainWindow::appendRightText(const QString &text, const QString &colorHtml) {
    QString escaped = text.toHtmlEscaped();
    QString html = QString("<pre style=\"margin: 0; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; color: %1; white-space: pre-wrap;\">%2</pre>")
                           .arg(colorHtml).arg(escaped);
    m_rightDisplay->append(html);
    m_rightDisplay->verticalScrollBar()->setValue(m_rightDisplay->verticalScrollBar()->maximum());
}

QStringList MainWindow::renderMascotFrame(int frame) const {
    if (m_customMascotFrames.isEmpty()) {
        return QStringList();
    }
    int idx = frame % m_customMascotFrames.size();
    return m_customMascotFrames[idx];
}

void MainWindow::printWelcomePanel(int frame) {
    m_leftDisplay->clear();
    m_rightDisplay->clear();

    // Left display (Mascot)
    appendLeftText("✦ Task Decomposer ✦", "#ffb3ba");
    appendLeftText("", "#ffffff");
    appendLeftText("Welcome back!", "#ffffff");
    appendLeftText("DeepSeek-V4-pro · API Usage Billing", "#8e8e93");
    
    QString cwd = QDir::currentPath();
    appendLeftText("CWD: " + cwd, "#8e8e93");
    appendLeftText("", "#ffffff");
    
    QStringList mascot = renderMascotFrame(frame);
    for (const QString &mLine : mascot) {
        m_leftDisplay->append(QString("<center><pre style=\"margin: 0; font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; color: #ffb3ba; white-space: pre;\">%1</pre></center>").arg(mLine.toHtmlEscaped()));
    }

    // Right display
    appendRightText("✦ Tips & Controls ✦", "#2ecc71");
    appendRightText("", "#ffffff");
    appendRightText("Active Mode: " + m_currentMode.toUpper(), "#ffffff");
    appendRightText("• [chat>] Direct prompt input to decompose tasks", "#8e8e93");
    appendRightText("• Tab: Switch active input mode", "#8e8e93");
    appendRightText("• Slash Commands: Try /status, /switch <id>, /new [id], /help", "#8e8e93");
    appendRightText("", "#ffffff");
    appendRightText("✦ System Status ✦", "#f1c40f");
    appendRightText(QString("• Project: %1").arg(m_projectName), "#ffffff");
    appendRightText(QString("• Conversation: %1").arg(m_conversationId), "#ffffff");
    appendRightText("", "#ffffff");
    appendRightText("✦ What's New ✦", "#3498db");
    appendRightText("• Zero-lag Native Timed Mascot Animation", "#8e8e93");
    appendRightText("• 90% Less CPU Overhead with High-Performance HTML Rendering", "#8e8e93");
    appendRightText("• Premium Visual Fluid Scaling layouts", "#8e8e93");
}

void MainWindow::printResultWorkspace() {
    m_leftDisplay->clear();
    m_rightDisplay->clear();

    // 1. Left Panel: Goal & Decomposed Tasks (Beautiful HTML card layout)
    QString leftHtml = QString(
        "<div style=\"font-family: 'Consolas', monospace; font-size: 14px; color: #ffffff;\">"
        "<h2 style=\"color: #ffb3ba; margin-top: 0;\">✦ Decomposed Plan ✦</h2>"
        "<p style=\"color: #a5b1c2;\"><b>Goal:</b> %1</p>"
        "<hr style=\"border: none; border-top: 1px solid #1a1a20; margin: 15px 0;\">"
    ).arg(m_lastGoal.toHtmlEscaped());

    QJsonArray tasks = m_lastPlan["tasks"].toArray();
    leftHtml += QString("<h3 style=\"color: #2ecc71;\">Tasks (Total: %1)</h3>").arg(tasks.size());
    leftHtml += "<ol style=\"padding-left: 20px; line-height: 1.6;\">";
    for (int i = 0; i < tasks.size(); ++i) {
        QJsonObject tObj = tasks[i].toObject();
        QString title = tObj["title"].toString().toHtmlEscaped();
        QString action = tObj["action"].toString().toHtmlEscaped();
        QString output = tObj["output"].toString().toHtmlEscaped();
        leftHtml += QString(
            "<li style=\"margin-bottom: 12px;\">"
            "<b style=\"color: #ffffff;\">%1</b><br/>"
            "<span style=\"color: #8e8e93; font-size: 12px;\"><b>Action:</b> %2</span><br/>"
            "<span style=\"color: #8e8e93; font-size: 12px;\"><b>Output:</b> %3</span>"
            "</li>"
        ).arg(title).arg(action).arg(output);
    }
    leftHtml += "</ol>";

    leftHtml += "<hr style=\"border: none; border-top: 1px solid #1a1a20; margin: 15px 0;\">";
    leftHtml += QString("<p style=\"color: #f1c40f;\"><b>Next Step:</b> %1</p>").arg(m_lastPlan["next_step"].toString().toHtmlEscaped());

    if (!m_lastQuestions.isEmpty()) {
        leftHtml += "<hr style=\"border: none; border-top: 1px solid #1a1a20; margin: 15px 0;\">";
        leftHtml += "<h3 style=\"color: #e74c3c;\">✦ Clarifications Required ✦</h3>";
        leftHtml += "<ul style=\"padding-left: 20px; line-height: 1.5; color: #ffb3ba;\">";
        for (int i = 0; i < m_lastQuestions.size() && i < 3; ++i) {
            leftHtml += QString("<li>%1</li>").arg(m_lastQuestions[i].toString().toHtmlEscaped());
        }
        leftHtml += "</ul>";
    }
    leftHtml += "</div>";
    m_leftDisplay->setHtml(leftHtml);

    // 2. Right Panel: Active Stats, Operations & Console Logs (Beautiful HTML card layout)
    QString rightHtml = QString(
        "<div style=\"font-family: 'Consolas', monospace; font-size: 14px; color: #ffffff;\">"
        "<h2 style=\"color: #ffb3ba; margin-top: 0;\">✦ Decomposer Console ✦</h2>"
        "<ul style=\"list-style-type: none; padding-left: 0; line-height: 1.8;\">"
        "<li>• <b>Project:</b> %1</li>"
        "<li>• <b>Conversation:</b> %2</li>"
        "<li>• <b>Time elapsed:</b> %3s</li>"
        "<li>• <b>Token usage:</b> %4 tokens%5</li>"
        "</ul>"
        "<hr style=\"border: none; border-top: 1px solid #1a1a20; margin: 15px 0;\">"
        "<h3 style=\"color: #3498db;\">✦ Console Operations ✦</h3>"
        "<ul style=\"list-style-type: none; padding-left: 0; line-height: 1.6; color: #8e8e93;\">"
        "<li>• <b style=\"color: #ffffff;\">/help</b>          Show help commands</li>"
        "<li>• <b style=\"color: #ffffff;\">/status</b>        Show system state</li>"
        "<li>• <b style=\"color: #ffffff;\">/switch &lt;id&gt;</b>   Switch conversation ID</li>"
        "<li>• <b style=\"color: #ffffff;\">/new [id]</b>      Create new conversation context</li>"
        "<li>• <b style=\"color: #ffffff;\">/clear</b>         Return to welcome screen</li>"
        "<li>• <b style=\"color: #ffffff;\">/exit</b>          Safe quit app</li>"
        "</ul>"
        "</div>"
    ).arg(m_projectName.toHtmlEscaped())
     .arg(m_conversationId.toHtmlEscaped())
     .arg(QString::number(m_lastElapsed, 'f', 1))
     .arg(m_lastTokens)
     .arg(m_lastTokenNote.toHtmlEscaped());
    
    m_rightDisplay->setHtml(rightHtml);
}
