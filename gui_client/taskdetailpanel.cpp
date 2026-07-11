#include "taskdetailpanel.h"
#include "theme.h"
#include <QFormLayout>
#include <QFrame>
#include <QFont>

TaskDetailPanel::TaskDetailPanel(const Theme *theme, QWidget *parent)
    : QWidget(parent), m_theme(theme)
{
    setupUI();
    hide();
}

void TaskDetailPanel::setTheme(const Theme *theme) {
    m_theme = theme;
    if (m_theme) setStyleSheet(m_theme->detailPanelQSS());
    update();
}

void TaskDetailPanel::setupUI() {
    setFixedWidth(320);
    if (m_theme) setStyleSheet(m_theme->detailPanelQSS());

    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    mainLayout->setContentsMargins(12, 12, 12, 12);
    mainLayout->setSpacing(10);

    // ── 标题栏 ──
    QHBoxLayout *headerLayout = new QHBoxLayout();
    QString accentName = m_theme ? m_theme->accent.name() : "#ffb3ba";
    QString mutedName = m_theme ? m_theme->textMuted.name() : "#8e8e93";
    QString borderName = m_theme ? m_theme->borderPrimary.name() : "#2c2c38";
    QString delColor = m_theme ? m_theme->deleteBtn.name() : "#e74c3c";
    QString addColor = m_theme ? m_theme->addBtn.name() : "#2ecc71";
    QString ff = m_theme ? m_theme->fontFamily : "Consolas";

    QLabel *headerLabel = new QLabel("任务详情");
    headerLabel->setStyleSheet(QString("font-size: 14px; font-weight: bold; color: %1; font-family: '%2';").arg(accentName, ff));
    m_closeBtn = new QPushButton("×");
    m_closeBtn->setFixedSize(28, 28);
    m_closeBtn->setStyleSheet(QString(
        "QPushButton { border: none; color: %1; font-size: 16px; }"
        "QPushButton:hover { color: %2; }"
    ).arg(mutedName, delColor));
    headerLayout->addWidget(headerLabel);
    headerLayout->addStretch();
    headerLayout->addWidget(m_closeBtn);
    mainLayout->addLayout(headerLayout);

    // ── 分隔线 ──
    QFrame *sep1 = new QFrame();
    sep1->setFrameShape(QFrame::HLine);
    sep1->setStyleSheet(QString("color: %1;").arg(borderName));
    mainLayout->addWidget(sep1);

    // ── 基本信息 ──
    QLabel *titleLabel = new QLabel("标题");
    m_titleEdit = new QLineEdit();
    mainLayout->addWidget(titleLabel);
    mainLayout->addWidget(m_titleEdit);

    QLabel *statusLabel = new QLabel("状态");
    m_statusCombo = new QComboBox();
    m_statusCombo->addItem("○ 待办", "pending");
    m_statusCombo->addItem("● 进行中", "in_progress");
    m_statusCombo->addItem("✓ 完成", "done");
    m_statusCombo->addItem("⊘ 阻塞", "blocked");
    mainLayout->addWidget(statusLabel);
    mainLayout->addWidget(m_statusCombo);

    QLabel *actionLabel = new QLabel("行动");
    m_actionEdit = new QTextEdit();
    m_actionEdit->setMaximumHeight(80);
    mainLayout->addWidget(actionLabel);
    mainLayout->addWidget(m_actionEdit);

    QLabel *outputLabel = new QLabel("产出");
    m_outputEdit = new QTextEdit();
    m_outputEdit->setMaximumHeight(80);
    mainLayout->addWidget(outputLabel);
    mainLayout->addWidget(m_outputEdit);

    // ── 保存按钮 ──
    m_saveBtn = new QPushButton("保存修改");
    m_saveBtn->setStyleSheet(QString(
        "QPushButton { background-color: %1; color: #ffffff; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; }"
        "QPushButton:hover { background-color: %2; }"
    ).arg(m_theme ? m_theme->statusDone.name() : "#2ecc71",
         m_theme ? m_theme->statusDoneBorder.name() : "#27ae60"));
    mainLayout->addWidget(m_saveBtn);

    // ── 分隔线 ──
    QFrame *sep2 = new QFrame();
    sep2->setFrameShape(QFrame::HLine);
    sep2->setStyleSheet(QString("color: %1;").arg(borderName));
    mainLayout->addWidget(sep2);

    // ── 关系管理 ──
    QLabel *relHeaderLabel = new QLabel("任务关系");
    relHeaderLabel->setStyleSheet(QString("font-size: 13px; font-weight: bold; color: %1; font-family: '%2';").arg(accentName, ff));
    mainLayout->addWidget(relHeaderLabel);

    m_relationsList = new QListWidget();
    m_relationsList->setMaximumHeight(120);
    mainLayout->addWidget(m_relationsList);

    QPushButton *delRelBtn = new QPushButton("删除选中关系");
    delRelBtn->setStyleSheet(QString(
        "QPushButton { color: %1; border-color: %1; }"
        "QPushButton:hover { background-color: %1; color: #ffffff; }"
    ).arg(delColor));
    mainLayout->addWidget(delRelBtn);

    // ── 添加关系 ──
    QLabel *addRelLabel = new QLabel("添加关系");
    addRelLabel->setStyleSheet(QString("font-size: 12px; color: %1; margin-top: 6px; font-family: '%2';").arg(mutedName, ff));
    mainLayout->addWidget(addRelLabel);

    QHBoxLayout *newRelLayout = new QHBoxLayout();
    m_newRelTargetCombo = new QComboBox();
    m_newRelTypeCombo = new QComboBox();
    m_newRelTypeCombo->addItem("顺序", "sequential");
    m_newRelTypeCombo->addItem("并行", "parallel");
    m_newRelTypeCombo->addItem("阻塞", "blocking");
    m_newRelTypeCombo->addItem("嵌套", "nesting");
    m_addRelBtn = new QPushButton("添加");
    newRelLayout->addWidget(m_newRelTargetCombo, 2);
    newRelLayout->addWidget(m_newRelTypeCombo, 1);
    newRelLayout->addWidget(m_addRelBtn);
    mainLayout->addLayout(newRelLayout);

    mainLayout->addStretch();

    // ── 信号连接 ──
    connect(m_saveBtn, &QPushButton::clicked, this, &TaskDetailPanel::onSaveClicked);
    connect(m_closeBtn, &QPushButton::clicked, this, &TaskDetailPanel::onCloseClicked);
    connect(delRelBtn, &QPushButton::clicked, this, &TaskDetailPanel::onDeleteRelationClicked);
    connect(m_addRelBtn, &QPushButton::clicked, this, &TaskDetailPanel::onAddRelationClicked);
}

void TaskDetailPanel::loadTask(const QJsonObject &taskData, const QJsonArray &allRelations,
                               const QJsonArray &allTasks) {
    m_currentTaskId = taskData["task_id"].toString();
    m_currentTaskData = taskData;
    m_allTasks = allTasks;

    m_titleEdit->setText(taskData["title"].toString());
    m_actionEdit->setPlainText(taskData["action"].toString());
    m_outputEdit->setPlainText(taskData["output"].toString());

    QString status = taskData["status"].toString("pending");
    for (int i = 0; i < m_statusCombo->count(); ++i) {
        if (m_statusCombo->itemData(i).toString() == status) {
            m_statusCombo->setCurrentIndex(i);
            break;
        }
    }

    // 刷新关系列表
    refreshRelationsList(allRelations, allTasks);

    // 刷新添加关系的目标下拉框
    m_newRelTargetCombo->clear();
    for (const QJsonValue &val : allTasks) {
        QJsonObject t = val.toObject();
        QString tid = t["task_id"].toString();
        if (tid != m_currentTaskId) {
            m_newRelTargetCombo->addItem(t["title"].toString(), tid);
        }
    }

    show();
}

void TaskDetailPanel::clear() {
    m_currentTaskId.clear();
    m_currentTaskData = QJsonObject();
    m_titleEdit->clear();
    m_actionEdit->clear();
    m_outputEdit->clear();
    m_statusCombo->setCurrentIndex(0);
    m_relationsList->clear();
    m_newRelTargetCombo->clear();
}

void TaskDetailPanel::refreshRelationsList(const QJsonArray &relations, const QJsonArray &allTasks) {
    m_relationsList->clear();

    // 构建 task_id → title 映射
    QMap<QString, QString> titleMap;
    for (const QJsonValue &val : allTasks) {
        QJsonObject t = val.toObject();
        titleMap[t["task_id"].toString()] = t["title"].toString();
    }

    for (const QJsonValue &val : relations) {
        QJsonObject rel = val.toObject();
        QString srcId = rel["source_id"].toString();
        QString tgtId = rel["target_id"].toString();
        QString rtype = rel["relation_type"].toString();

        // 只显示与当前任务相关的关系
        if (srcId != m_currentTaskId && tgtId != m_currentTaskId) continue;

        QString typeLabel;
        if (rtype == "sequential") typeLabel = "顺序";
        else if (rtype == "parallel") typeLabel = "并行";
        else if (rtype == "blocking") typeLabel = "阻塞";
        else if (rtype == "nesting") typeLabel = "嵌套";
        else typeLabel = rtype;

        QString srcTitle = titleMap.value(srcId, srcId);
        QString tgtTitle = titleMap.value(tgtId, tgtId);
        QString display = QString("%1 --[%2]--> %3").arg(srcTitle, typeLabel, tgtTitle);

        QListWidgetItem *item = new QListWidgetItem(display);
        item->setData(Qt::UserRole, srcId);
        item->setData(Qt::UserRole + 1, tgtId);
        m_relationsList->addItem(item);
    }
}

bool TaskDetailPanel::isPanelVisible() const {
    return isVisible();
}

void TaskDetailPanel::showPanel() { show(); }
void TaskDetailPanel::hidePanel() { hide(); emit closed(); }

void TaskDetailPanel::onCloseClicked() { hidePanel(); }

void TaskDetailPanel::onSaveClicked() {
    if (m_currentTaskId.isEmpty()) return;

    QJsonObject changes;
    changes["task_id"] = m_currentTaskId;
    changes["title"] = m_titleEdit->text();
    changes["action"] = m_actionEdit->toPlainText();
    changes["output"] = m_outputEdit->toPlainText();
    changes["status"] = m_statusCombo->currentData().toString();

    emit saveRequested(m_currentTaskId, changes);
}

void TaskDetailPanel::onDeleteRelationClicked() {
    QListWidgetItem *item = m_relationsList->currentItem();
    if (!item) return;

    QString srcId = item->data(Qt::UserRole).toString();
    QString tgtId = item->data(Qt::UserRole + 1).toString();
    emit removeRelationRequested(srcId, tgtId);
}

void TaskDetailPanel::onAddRelationClicked() {
    if (m_currentTaskId.isEmpty()) return;
    int idx = m_newRelTargetCombo->currentIndex();
    if (idx < 0) return;

    QString targetId = m_newRelTargetCombo->currentData().toString();
    QString relType = m_newRelTypeCombo->currentData().toString();
    emit addRelationRequested(m_currentTaskId, targetId, relType);
}
