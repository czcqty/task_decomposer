#include "mainwindow.h"
#include "taskcanvas.h"
#include "taskdetailpanel.h"
#include "configdialog.h"
#include "theme.h"

#include <QHBoxLayout>
#include <QVBoxLayout>
#include <QSplitter>
#include <QJsonDocument>
#include <QJsonArray>
#include <QFile>
#include <QCoreApplication>
#include <QDir>
#include <QSettings>
#include <QFileDialog>
#include <QMessageBox>
#include <QFont>
#include <QLabel>
#include <QProcessEnvironment>

// ────────────────────────────────────────────────────────────────
// 构造 / 析构
// ────────────────────────────────────────────────────────────────

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent), m_process(nullptr)
{
    setWindowTitle("Task Decomposer");
    resize(1200, 750);

    m_projectName = "demo";
    m_conversationId = "default";
    m_isShowingWelcome = true;

    // 加载主题偏好
    QSettings settings("TaskDecomposer", "GUI");
    m_isModernTheme = settings.value("theme/modern", true).toBool();
    m_theme = new Theme(m_isModernTheme ? modernTheme() : retroTheme());

    initUI();
    applyTheme();
    showWelcomeView();
    startBackendProcess();
}

MainWindow::~MainWindow() {
    if (m_process && m_process->state() == QProcess::Running) {
        m_process->terminate();
        m_process->waitForFinished(3000);
    }
    delete m_theme;
}

// ────────────────────────────────────────────────────────────────
// 主题切换
// ────────────────────────────────────────────────────────────────

void MainWindow::onThemeSwitchClicked() {
    m_isModernTheme = !m_isModernTheme;
    *m_theme = m_isModernTheme ? modernTheme() : retroTheme();

    // 持久化
    QSettings settings("TaskDecomposer", "GUI");
    settings.setValue("theme/modern", m_isModernTheme);

    // 更新所有组件
    applyTheme();
    m_canvas->setTheme(m_theme);
    m_detailPanel->setTheme(m_theme);
}

// ────────────────────────────────────────────────────────────────
// UI 初始化
// ────────────────────────────────────────────────────────────────

void MainWindow::initUI() {
    QWidget *centralWidget = new QWidget(this);
    setCentralWidget(centralWidget);

    QVBoxLayout *mainLayout = new QVBoxLayout(centralWidget);
    mainLayout->setContentsMargins(8, 8, 8, 8);
    mainLayout->setSpacing(6);

    // ── 画布 + 详情面板 分割器 ──
    m_splitter = new QSplitter(Qt::Horizontal, this);
    m_splitter->setHandleWidth(3);

    // 欢迎视图
    m_welcomeWidget = new QWidget(this);
    QVBoxLayout *welcomeLayout = new QVBoxLayout(m_welcomeWidget);
    welcomeLayout->setAlignment(Qt::AlignCenter);

    QLabel *welcomeTitle = new QLabel("✦ Task Decomposer ✦", m_welcomeWidget);
    welcomeTitle->setObjectName("welcomeTitle");
    welcomeTitle->setAlignment(Qt::AlignCenter);
    welcomeLayout->addWidget(welcomeTitle);

    QLabel *welcomeHint = new QLabel("在下方输入目标，点击「分解」开始任务拆解", m_welcomeWidget);
    welcomeHint->setObjectName("welcomeHint");
    welcomeHint->setAlignment(Qt::AlignCenter);
    welcomeLayout->addWidget(welcomeHint);

    QLabel *welcomeTips = new QLabel(
        "提示：\n"
        "• 输入自然语言目标，AI 会自动拆解为可执行任务\n"
        "• 分解后可拖拽卡片调整位置\n"
        "• Shift+拖拽在两个任务间创建关系\n"
        "• 点击任务卡片编辑详情\n"
        "• Ctrl+滚轮缩放画布",
        m_welcomeWidget
    );
    welcomeTips->setObjectName("welcomeTips");
    welcomeTips->setAlignment(Qt::AlignCenter);
    welcomeLayout->addWidget(welcomeTips);

    // 任务画布
    m_canvas = new TaskCanvas(m_theme, this);
    m_canvas->setVisible(false);

    // 任务详情面板
    m_detailPanel = new TaskDetailPanel(m_theme, this);
    m_detailPanel->setVisible(false);

    // 连接画布信号
    connect(m_canvas, &TaskCanvas::taskClicked, this, &MainWindow::onTaskClicked);
    connect(m_canvas, &TaskCanvas::taskOrderChanged, this, &MainWindow::onTaskOrderChanged);
    connect(m_canvas, &TaskCanvas::relationCreated, this, &MainWindow::onRelationCreated);
    connect(m_canvas, &TaskCanvas::relationDeleted, this, &MainWindow::onRelationDeleted);

    // 连接详情面板信号
    connect(m_detailPanel, &TaskDetailPanel::saveRequested, this, &MainWindow::onTaskSaveRequested);
    connect(m_detailPanel, &TaskDetailPanel::removeRelationRequested, this, &MainWindow::onRelationDeleted);
    connect(m_detailPanel, &TaskDetailPanel::addRelationRequested, this, &MainWindow::onRelationCreated);

    m_splitter->addWidget(m_welcomeWidget);
    m_splitter->addWidget(m_canvas);
    m_splitter->addWidget(m_detailPanel);
    m_splitter->setStretchFactor(0, 5);
    m_splitter->setStretchFactor(1, 5);
    m_splitter->setStretchFactor(2, 0);

    mainLayout->addWidget(m_splitter, 1);

    // ── 底部输入栏 ──
    QHBoxLayout *inputLayout = new QHBoxLayout();
    inputLayout->setContentsMargins(4, 4, 4, 4);
    inputLayout->setSpacing(6);

    m_promptLabel = new QLabel("chat>", this);
    m_promptLabel->setObjectName("promptLabel");

    QFont monoFont(m_theme->fontFamilyMono, 12);
    m_promptLabel->setFont(monoFont);

    m_input = new QLineEdit(this);
    m_input->setFont(QFont(m_theme->fontFamily, 13));
    m_input->setObjectName("terminalInput");
    m_input->setPlaceholderText("输入目标，按 Enter 或点击「分解」开始...");

    m_decomposeBtn = new QPushButton("分解", this);
    m_decomposeBtn->setObjectName("decomposeBtn");
    m_decomposeBtn->setFixedWidth(70);

    m_themeSwitchBtn = new QPushButton(m_isModernTheme ? "🌙 复古" : "☀ 现代", this);
    m_themeSwitchBtn->setObjectName("themeSwitchBtn");
    m_themeSwitchBtn->setFixedWidth(80);

    inputLayout->addWidget(m_promptLabel);
    inputLayout->addWidget(m_input, 1);
    inputLayout->addWidget(m_decomposeBtn);
    inputLayout->addWidget(m_themeSwitchBtn);

    QWidget *inputContainer = new QWidget(this);
    inputContainer->setObjectName("inputContainer");
    inputContainer->setLayout(inputLayout);

    mainLayout->addWidget(inputContainer);

    connect(m_input, &QLineEdit::returnPressed, this, &MainWindow::onInputReturnPressed);
    connect(m_decomposeBtn, &QPushButton::clicked, this, &MainWindow::onDecomposeClicked);
    connect(m_themeSwitchBtn, &QPushButton::clicked, this, &MainWindow::onThemeSwitchClicked);
}

void MainWindow::applyTheme() {
    setStyleSheet(m_theme->globalQSS());
    m_splitter->setStyleSheet(QString("QSplitter::handle { background-color: %1; }").arg(m_theme->borderSubtle.name()));

    // 更新主题切换按钮文字
    if (m_themeSwitchBtn) {
        m_themeSwitchBtn->setText(m_isModernTheme ? "🌙 复古" : "☀ 现代");
    }

    // 更新字体
    if (m_promptLabel) m_promptLabel->setFont(QFont(m_theme->fontFamilyMono, 12));
    if (m_input) m_input->setFont(QFont(m_theme->fontFamily, 13));
}

void MainWindow::showWelcomeView() {
    m_isShowingWelcome = true;
    m_welcomeWidget->setVisible(true);
    m_canvas->setVisible(false);
    m_detailPanel->setVisible(false);
}

void MainWindow::showCanvasView() {
    m_isShowingWelcome = false;
    m_welcomeWidget->setVisible(false);
    m_canvas->setVisible(true);
}

// ────────────────────────────────────────────────────────────────
// 输入处理
// ────────────────────────────────────────────────────────────────

void MainWindow::onInputReturnPressed() {
    onDecomposeClicked();
}

void MainWindow::onDecomposeClicked() {
    QString goal = m_input->text().trimmed();
    if (goal.isEmpty()) return;

    m_lastGoal = goal;
    m_input->setEnabled(false);
    m_decomposeBtn->setEnabled(false);

    QJsonObject cmd;
    cmd["command"] = "run";
    cmd["goal"] = goal;
    cmd["project"] = m_projectName;
    cmd["conversation"] = m_conversationId;
    cmd["search"] = true;
    sendCommandToBackend(cmd);
}

// ────────────────────────────────────────────────────────────────
// 后端进程管理
// ────────────────────────────────────────────────────────────────

void MainWindow::startBackendProcess() {
    m_process = new QProcess(this);

    QString configPath = QDir(QCoreApplication::applicationDirPath()).filePath("config.ini");
    QSettings settings(configPath, QSettings::IniFormat);
    QString savedRoot = settings.value("project_root").toString();
    QString finalRoot;

    if (!savedRoot.isEmpty() && QFile::exists(QDir(savedRoot).absoluteFilePath("task_decomposer.py"))) {
        finalRoot = savedRoot;
    }

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
        QMessageBox::information(this, "定位后端引擎",
            "未能自动检测到后端脚本入口 'task_decomposer.py'。\n请手动选择项目根目录下的文件。");
        QString selectedFile = QFileDialog::getOpenFileName(this,
            "选择后端入口脚本", QCoreApplication::applicationDirPath(),
            "Python 脚本 (task_decomposer.py);;所有文件 (*.*)");
        if (!selectedFile.isEmpty()) {
            finalRoot = QFileInfo(selectedFile).absolutePath();
        }
    }

    if (!finalRoot.isEmpty()) {
        settings.setValue("project_root", finalRoot);
        m_process->setWorkingDirectory(finalRoot);

        QProcessEnvironment env = QProcessEnvironment::systemEnvironment();
        env.insert("PYTHONIOENCODING", "utf-8");
        env.insert("PYTHONUTF8", "1");
        m_process->setProcessEnvironment(env);

        connect(m_process, &QProcess::readyReadStandardOutput, this, &MainWindow::readBackendOutput);
        connect(m_process, &QProcess::readyReadStandardError, this, &MainWindow::readBackendError);
        connect(m_process, QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
                this, &MainWindow::handleProcessFinished);
        connect(m_process, &QProcess::errorOccurred, this, &MainWindow::handleProcessError);

        m_process->start("python", QStringList() << "task_decomposer.py" << "--gui-server");
    }
}

void MainWindow::sendCommandToBackend(const QJsonObject &json) {
    if (!m_process || m_process->state() != QProcess::Running) {
        m_input->setEnabled(true);
        m_decomposeBtn->setEnabled(true);
        return;
    }
    QJsonDocument doc(json);
    QByteArray bytes = doc.toJson(QJsonDocument::Compact) + "\n";
    m_process->write(bytes);
}

// ────────────────────────────────────────────────────────────────
// IPC 消息处理
// ────────────────────────────────────────────────────────────────

void MainWindow::readBackendOutput() {
    while (m_process->canReadLine()) {
        QByteArray line = m_process->readLine().trimmed();
        if (line.isEmpty()) continue;

        QJsonDocument doc = QJsonDocument::fromJson(line);
        if (doc.isNull() || !doc.isObject()) continue;

        QJsonObject obj = doc.object();
        QString type = obj["type"].toString();

        if (type == "status") continue;

        if (type == "error") {
            QMessageBox::warning(this, "错误", obj["message"].toString());
            m_input->setEnabled(true);
            m_decomposeBtn->setEnabled(true);
            m_input->setFocus();
            continue;
        }

        if (type == "config_data") {
            QJsonObject config = obj["config"].toObject();
            ConfigDialog dlg(config, m_theme, this);
            if (dlg.exec() == QDialog::Accepted) {
                QJsonObject updated = dlg.getUpdatedConfig();
                QJsonObject saveCmd;
                saveCmd["command"] = "save_config";
                saveCmd["user"] = config["name"].toString();
                saveCmd["config"] = updated;
                sendCommandToBackend(saveCmd);
            }
            continue;
        }

        if (type == "success") {
            m_lastPlan = obj["plan"].toObject();
            showCanvasView();
            m_canvas->loadPlan(m_lastPlan);
            m_input->setEnabled(true);
            m_decomposeBtn->setEnabled(true);
            m_input->clear();
            m_input->setFocus();
            continue;
        }

        if (type == "plan_updated") {
            m_lastPlan = obj["plan"].toObject();
            m_canvas->loadPlan(m_lastPlan);
            continue;
        }
    }
}

void MainWindow::readBackendError() {
    Q_UNUSED(m_process->readAllStandardError());
}

void MainWindow::handleProcessFinished(int, QProcess::ExitStatus) {
    m_input->setEnabled(true);
    m_decomposeBtn->setEnabled(true);
}

void MainWindow::handleProcessError(QProcess::ProcessError) {
    m_input->setEnabled(true);
    m_decomposeBtn->setEnabled(true);
}

// ────────────────────────────────────────────────────────────────
// 画布交互 → IPC 命令
// ────────────────────────────────────────────────────────────────

void MainWindow::onTaskClicked(const QString &taskId) {
    QJsonArray tasks = m_lastPlan["tasks"].toArray();
    QJsonArray relations = m_lastPlan["relations"].toArray();

    for (const QJsonValue &val : tasks) {
        QJsonObject task = val.toObject();
        if (task["task_id"].toString() == taskId) {
            m_detailPanel->loadTask(task, relations, tasks);
            if (m_detailPanel->width() < 50) {
                QList<int> sizes = m_splitter->sizes();
                if (sizes.size() >= 3) {
                    int total = sizes[0] + sizes[1] + sizes[2];
                    int detailW = 320;
                    int canvasW = total - detailW;
                    m_splitter->setSizes({canvasW / 2, canvasW / 2, detailW});
                }
            }
            break;
        }
    }
}

void MainWindow::onTaskOrderChanged(const QStringList &taskIds) {
    QJsonObject cmd;
    cmd["command"] = "reorder_tasks";
    QJsonArray ids;
    for (const QString &id : taskIds) ids.append(id);
    cmd["task_ids"] = ids;
    sendCommandToBackend(cmd);
}

void MainWindow::onRelationCreated(const QString &sourceId, const QString &targetId, const QString &type) {
    QJsonObject cmd;
    cmd["command"] = "add_relation";
    cmd["source_id"] = sourceId;
    cmd["target_id"] = targetId;
    cmd["relation_type"] = type;
    sendCommandToBackend(cmd);
}

void MainWindow::onRelationDeleted(const QString &sourceId, const QString &targetId) {
    QJsonObject cmd;
    cmd["command"] = "remove_relation";
    cmd["source_id"] = sourceId;
    cmd["target_id"] = targetId;
    sendCommandToBackend(cmd);
}

void MainWindow::onTaskSaveRequested(const QString &taskId, const QJsonObject &changes) {
    QJsonObject cmd;
    cmd["command"] = "update_task";
    cmd["task_id"] = taskId;
    cmd["title"] = changes["title"].toString();
    cmd["action"] = changes["action"].toString();
    cmd["output"] = changes["output"].toString();
    cmd["status"] = changes["status"].toString();
    sendCommandToBackend(cmd);
}
