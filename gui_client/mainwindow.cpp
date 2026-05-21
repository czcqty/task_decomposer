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
        // 宽度太小或呈纵向狭长比例时，自适应折叠为上下堆叠
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

    // 只要有任何输入，即停用欢迎飞碟动画并切入日志模式
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
    appendRightText("  /switch <id>   切换到已有或指定对话", "#ffffff");
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

    QSettings settings("DeepMindTaskDecomposer", "TaskDecomposerGUI");
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

    // 3. 如果依然未找到（例如 exe 文件被单独移动或分发），触发手动选择窗口
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

int MainWindow::terminalUiWidth() const {
    QFontMetrics fm(m_leftDisplay->font());
    int charWidth = fm.averageCharWidth();
    if (charWidth <= 0) charWidth = 8;
    int viewportWidth = m_leftDisplay->viewport()->width();
    int numCols = (viewportWidth - 24) / charWidth;
    return qMax(30, numCols);
}

int MainWindow::visualWidth(const QString &text) const {
    int width = 0;
    for (const QChar &ch : text) {
        ushort unicode = ch.unicode();
        // CJK 等宽中文字符的 unicode 范围判定，占用 2 字符宽度
        if ((unicode >= 0x4E00 && unicode <= 0x9FFF) ||
            (unicode >= 0x3000 && unicode <= 0x303F) ||
            (unicode >= 0xFF00 && unicode <= 0xFFEF)) {
            width += 2;
        } else {
            width += 1;
        }
    }
    return width;
}

QString MainWindow::truncateVisual(const QString &text, int width) const {
    if (visualWidth(text) <= width) return text;
    if (width <= 1) return "";

    QString result = "";
    int used = 0;
    QString marker = "…";
    int markerWidth = visualWidth(marker);
    int limit = qMax(0, width - markerWidth);

    for (const QChar &ch : text) {
        int charWidth = visualWidth(QString(ch));
        if (used + charWidth > limit) break;
        result += ch;
        used += charWidth;
    }
    return result + marker;
}

QString MainWindow::padVisual(const QString &text, int width) const {
    QString truncated = truncateVisual(text, width);
    return truncated + QString(qMax(0, width - visualWidth(truncated)), ' ');
}

QString MainWindow::padVisualUntruncated(const QString &text, int width) const {
    return text + QString(qMax(0, width - visualWidth(text)), ' ');
}

QString MainWindow::centerVisual(const QString &text, int width) const {
    QString truncated = truncateVisual(text, width);
    int padding = qMax(0, width - visualWidth(truncated));
    int left = padding / 2;
    int right = padding - left;
    return QString(left, ' ') + truncated + QString(right, ' ');
}

QStringList MainWindow::wrapVisual(const QString &text, int width) const {
    if (width <= 0) return QStringList("");
    if (text.isEmpty()) return QStringList("");

    QStringList lines;
    QStringList rawLines = text.split('\n');
    for (const QString &rawLine : rawLines) {
        QString current = "";
        int used = 0;
        for (const QChar &ch : rawLine) {
            int charWidth = visualWidth(QString(ch));
            if (used > 0 && used + charWidth > width) {
                lines.append(current);
                current = "";
                used = 0;
            }
            current += ch;
            used += charWidth;
        }
        lines.append(current);
    }
    return lines;
}

// =========================================================================
// UFO ASCII Mascot 牵引光束吸人逐帧绘制器实现 (Ported from mascot.py)
// =========================================================================

void MainWindow::overlay(QVector<QString> &canvas, int row, int col, const QString &text) const {
    if (row < 0 || row >= canvas.size()) return;
    int width = canvas[row].size();
    for (int i = 0; i < text.size(); ++i) {
        int target = col + i;
        if (target >= 0 && target < width && text[i] != ' ') {
            canvas[row][target] = text[i];
        }
    }
}

void MainWindow::drawBeam(QVector<QString> &canvas, int center, int phase) const {
    int widths[] = {3, 5, 7, 9};
    for (int index = 0; index < 4; ++index) {
        int row = 3 + index;
        int beam_width = widths[index];
        if (phase == 7) {
            beam_width = qMax(1, beam_width - 2);
        }
        int left = center - beam_width / 2;
        int right = left + beam_width - 1;
        overlay(canvas, row, left, "/");
        overlay(canvas, row, right, "\\");
        for (int col = left + 1; col < right; ++col) {
            if (col >= 0 && col < canvas[row].size() && (col + row + phase) % 2 == 0) {
                canvas[row][col] = '.';
            }
        }
    }
}

void MainWindow::drawWalkingPerson(QVector<QString> &canvas, int row, int col, int phase) const {
    QStringList pose;
    if (phase % 2 == 0) {
        pose << " o/" << "/| " << "/ \\";
    } else {
        pose << "\\o " << " |\\" << "/ \\";
    }
    for (int i = 0; i < pose.size(); ++i) {
        overlay(canvas, row + i, col, pose[i]);
    }
}

void MainWindow::drawPerson(QVector<QString> &canvas, int row, int col) const {
    QStringList pose;
    pose << " o " << "/|\\" << "/ \\";
    for (int i = 0; i < pose.size(); ++i) {
        overlay(canvas, row + i, col, pose[i]);
    }
}

void MainWindow::drawSmallPerson(QVector<QString> &canvas, int row, int col) const {
    QStringList pose;
    pose << " o " << " | " << "/ \\";
    for (int i = 0; i < pose.size(); ++i) {
        overlay(canvas, row + i, col, pose[i]);
    }
}

QStringList MainWindow::renderDefaultMascotFrame(int frame, int width) const {
    int sceneWidth = qMax(28, width);
    int sceneHeight = 9;
    QVector<QString> canvas(sceneHeight, QString(sceneWidth, ' '));

    int phase = frame % 12;
    int person_x = qMax(4, sceneWidth / 2 - 1);

    int ufo_positions[] = {
        sceneWidth - 9,
        sceneWidth - 12,
        sceneWidth - 15,
        person_x + 4,
        person_x - 2,
        person_x - 2,
        person_x - 2,
        person_x - 2,
        person_x - 6,
        person_x - 12,
        -2,
        -8
    };
    int ufo_x = ufo_positions[phase];

    overlay(canvas, 0, ufo_x, "  _.-._  ");
    overlay(canvas, 1, ufo_x, " /_o_o_\\ ");
    overlay(canvas, 2, ufo_x, "<--===-->");

    if (phase >= 4 && phase <= 7) {
        drawBeam(canvas, ufo_x + 4, phase);
    }

    if (phase <= 3) {
        drawWalkingPerson(canvas, 5, person_x, phase);
    } else if (phase == 4) {
        drawPerson(canvas, 5, person_x);
    } else if (phase == 5) {
        drawPerson(canvas, 4, person_x);
    } else if (phase == 6) {
        drawSmallPerson(canvas, 3, person_x);
    } else if (phase == 7) {
        overlay(canvas, 3, person_x, "(o)");
    }

    overlay(canvas, 8, 0, QString(sceneWidth, '_'));

    QStringList lines;
    for (int r = 0; r < sceneHeight; ++r) {
        lines.append(canvas[r].trimmed());
    }

    QStringList centeredLines;
    for (const QString &l : lines) {
        centeredLines.append(centerVisual(l, width));
    }
    return centeredLines;
}

void MainWindow::printWelcomePanel(int frame) {
    m_leftDisplay->clear();
    m_rightDisplay->clear();

    // Left display
    appendLeftText("✦ Task Decomposer ✦", "#ffb3ba");
    appendLeftText("", "#ffffff");
    appendLeftText("Welcome back!", "#ffffff");
    appendLeftText("DeepSeek-V4-pro · API Usage Billing", "#8e8e93");
    
    QString cwd = QDir::currentPath();
    appendLeftText("CWD: " + cwd, "#8e8e93");
    appendLeftText("", "#ffffff");
    
    // 锁定飞碟动画内部虚拟宽度为 48，实现完美精细的居中，避免随窗口抖动
    QStringList mascot = renderDefaultMascotFrame(frame, 48);
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
    appendRightText("• Real-time fluid split-pane layout", "#8e8e93");
    appendRightText("• Smooth pixel-perfect OS resizing", "#8e8e93");
    appendRightText("• Active pane dynamic glow highlights", "#8e8e93");
}

void MainWindow::printResultWorkspace() {
    m_leftDisplay->clear();
    m_rightDisplay->clear();

    // 1. Left Panel: Goal & Decomposed Tasks
    appendLeftText("✦ Decomposed Plan ✦", "#ffb3ba");
    appendLeftText("", "#ffffff");
    appendLeftText("Goal: " + m_lastGoal, "#ffffff");
    appendLeftText("", "#ffffff");

    QJsonArray tasks = m_lastPlan["tasks"].toArray();
    appendLeftText(QString("Tasks (Total: %1)").arg(tasks.size()), "#2ecc71");
    for (int i = 0; i < tasks.size(); ++i) {
        QJsonObject tObj = tasks[i].toObject();
        appendLeftText(QString("%1. %2").arg(i + 1).arg(tObj["title"].toString()), "#ffffff");
    }
    
    appendLeftText("", "#ffffff");
    appendLeftText("Next Step: " + m_lastPlan["next_step"].toString(), "#f1c40f");

    if (!m_lastQuestions.isEmpty()) {
        appendLeftText("", "#ffffff");
        appendLeftText("✦ Clarifications Required ✦", "#e74c3c");
        for (int i = 0; i < m_lastQuestions.size() && i < 3; ++i) {
            appendLeftText("• " + m_lastQuestions[i].toString(), "#ffffff");
        }
    }

    // 2. Right Panel: Active Stats, Operations & Console Logs
    appendRightText("✦ Decomposer Console ✦", "#ffb3ba");
    appendRightText("", "#ffffff");
    appendRightText(QString("• Project: %1").arg(m_projectName), "#ffffff");
    appendRightText(QString("• Conversation: %1").arg(m_conversationId), "#ffffff");
    appendRightText(QString("• Time elapsed: %1s").arg(m_lastElapsed, 0, 'f', 1), "#ffffff");
    appendRightText(QString("• Token usage: %1 tokens%2").arg(m_lastTokens).arg(m_lastTokenNote), "#ffffff");
    appendRightText("", "#ffffff");

    appendRightText("✦ Console Operations ✦", "#3498db");
    appendRightText("• /help          Show help commands", "#8e8e93");
    appendRightText("• /status        Show system state", "#8e8e93");
    appendRightText("• /switch <id>   Switch conversation ID", "#8e8e93");
    appendRightText("• /new [id]      Create new conversation context", "#8e8e93");
    appendRightText("• /clear         Return to welcome ufo animation screen", "#8e8e93");
    appendRightText("• /exit          Safe quit app", "#8e8e93");
}

void MainWindow::printSplitPanel(const QString &title, const QStringList &leftLines, const QStringList &rightLines) {
    Q_UNUSED(title);
    Q_UNUSED(leftLines);
    Q_UNUSED(rightLines);
    printResultWorkspace();
}
