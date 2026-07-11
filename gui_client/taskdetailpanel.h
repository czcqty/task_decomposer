#ifndef TASKDETAILPANEL_H
#define TASKDETAILPANEL_H

#include <QWidget>
#include <QJsonObject>
#include <QJsonArray>
#include <QLineEdit>
#include <QTextEdit>
#include <QComboBox>
#include <QPushButton>
#include <QLabel>
#include <QVBoxLayout>
#include <QListWidget>

struct Theme;

// ────────────────────────────────────────────────────────────────
// TaskDetailPanel — 右侧任务编辑面板
//
// 点击卡片时打开，显示任务的完整信息。
// 所有字段可编辑，修改后点保存通过信号发送。
// ────────────────────────────────────────────────────────────────
class TaskDetailPanel : public QWidget {
    Q_OBJECT

public:
    explicit TaskDetailPanel(const Theme *theme, QWidget *parent = nullptr);

    // 显示指定任务的详情
    void setTheme(const Theme *theme);
    void loadTask(const QJsonObject &taskData, const QJsonArray &allRelations,
                  const QJsonArray &allTasks);
    // 清空面板
    void clear();

    // 面板是否可见
    bool isPanelVisible() const;

signals:
    // 用户点击了保存
    void saveRequested(const QString &taskId, const QJsonObject &changes);
    // 用户点击了删除关系
    void removeRelationRequested(const QString &sourceId, const QString &targetId);
    // 用户点击了添加关系
    void addRelationRequested(const QString &sourceId, const QString &targetId, const QString &type);
    // 用户关闭了面板
    void closed();

public slots:
    void showPanel();
    void hidePanel();

private slots:
    void onSaveClicked();
    void onDeleteRelationClicked();
    void onAddRelationClicked();
    void onCloseClicked();

private:
    void setupUI();
    void refreshRelationsList(const QJsonArray &relations, const QJsonArray &allTasks);

    // 输入控件
    QLineEdit *m_titleEdit;
    QComboBox *m_statusCombo;
    QTextEdit *m_actionEdit;
    QTextEdit *m_outputEdit;

    // 关系列表
    QListWidget *m_relationsList;
    QComboBox *m_newRelTargetCombo;
    QComboBox *m_newRelTypeCombo;

    // 按钮
    QPushButton *m_saveBtn;
    QPushButton *m_closeBtn;
    QPushButton *m_addRelBtn;

    // 主题
    const Theme *m_theme;

    // 当前任务数据
    QString m_currentTaskId;
    QJsonObject m_currentTaskData;
    QJsonArray m_allTasks;
};

#endif // TASKDETAILPANEL_H
