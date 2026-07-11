#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QProcess>
#include <QLineEdit>
#include <QLabel>
#include <QJsonObject>
#include <QSplitter>
#include <QPushButton>

class TaskCanvas;
class TaskDetailPanel;
struct Theme;

// ────────────────────────────────────────────────────────────────
// MainWindow — 重构后的主窗口
// ────────────────────────────────────────────────────────────────
class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void onInputReturnPressed();
    void onDecomposeClicked();
    void onThemeSwitchClicked();
    void readBackendOutput();
    void readBackendError();
    void handleProcessFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void handleProcessError(QProcess::ProcessError error);

    // 画布交互 → IPC
    void onTaskClicked(const QString &taskId);
    void onTaskOrderChanged(const QStringList &taskIds);
    void onRelationCreated(const QString &sourceId, const QString &targetId, const QString &type);
    void onRelationDeleted(const QString &sourceId, const QString &targetId);
    void onTaskSaveRequested(const QString &taskId, const QJsonObject &changes);

private:
    void initUI();
    void applyTheme();
    void startBackendProcess();
    void sendCommandToBackend(const QJsonObject &json);
    void showWelcomeView();
    void showCanvasView();

    // UI 组件
    QSplitter *m_splitter;
    TaskCanvas *m_canvas;
    TaskDetailPanel *m_detailPanel;
    QLabel *m_promptLabel;
    QLineEdit *m_input;
    QPushButton *m_decomposeBtn;
    QPushButton *m_themeSwitchBtn;
    QWidget *m_welcomeWidget;

    // 后端进程
    QProcess *m_process;

    // 运行状态
    QString m_projectName;
    QString m_conversationId;
    bool m_isShowingWelcome;

    // 缓存
    QJsonObject m_lastPlan;
    QString m_lastGoal;

    // 主题
    Theme *m_theme;
    bool m_isModernTheme;
};

#endif // MAINWINDOW_H
