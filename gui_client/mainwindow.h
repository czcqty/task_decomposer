#ifndef MAINWINDOW_H
#define MAINWINDOW_H

#include <QMainWindow>
#include <QProcess>
#include <QLineEdit>
#include <QTextEdit>
#include <QLabel>
#include <QTimer>
#include <QJsonObject>
#include <QJsonArray>
#include <QVector>
#include <QResizeEvent>
#include <QSplitter>

class MainWindow : public QMainWindow {
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
    void resizeEvent(QResizeEvent *event) override;

private slots:
    void onInputReturnPressed();
    void onMascotTimerTimeout();
    void readBackendOutput();
    void readBackendError();
    void handleProcessFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void handleProcessError(QProcess::ProcessError error);

private:
    void initUI();
    void applyTheme();
    void startBackendProcess();
    void loadMascotFromJson();
    void logMascotLoader(const QString &msg);
    void sendCommandToBackend(const QJsonObject &json);

    // 终端与主界面渲染（通过富文本 HTML）
    void printWelcomePanel(int frame);
    void printResultWorkspace();
    void printHelp();
    void printStatus();
    
    // 输入与指令处理
    void handleInput(const QString &input);
    void executeSlashCommand(const QString &cmd, const QString &args);
    void handleMascotCommand(const QString &args);
    void appendTerminalText(const QString &text, const QString &colorHtml);
    void appendLeftText(const QString &text, const QString &colorHtml);
    void appendRightText(const QString &text, const QString &colorHtml);
    void updatePrompt();

    QStringList renderMascotFrame(int frame) const;

    // UI 组件
    QSplitter *m_splitter;
    QTextEdit *m_leftDisplay;
    QTextEdit *m_rightDisplay;
    QLabel *m_promptLabel;
    QLineEdit *m_terminalInput;

    // 后端进程与本地动画计时器
    QProcess *m_process;
    QTimer *m_mascotTimer;
    QVector<QStringList> m_customMascotFrames;

    // 运行状态与配置
    QString m_currentMode;      // "chat" 或 "console"
    QString m_projectName;      // 当前项目名，如 "demo"
    QString m_conversationId;   // 当前会话，如 "default"
    int m_mascotFrame;          // Mascot 动画当前帧
    bool m_isShowingWelcome;    // 是否处于欢迎动画界面
    
    // 缓存数据（核心引擎事件传递过来后缓存起来，直接用 HTML 渲染出来）
    double m_lastElapsed;
    int m_lastTokens;
    QString m_lastTokenNote;
    QJsonObject m_lastPlan;
    QJsonArray m_lastQuestions;
    QString m_lastGoal;
};

#endif // MAINWINDOW_H
