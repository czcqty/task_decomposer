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
    void sendCommandToBackend(const QJsonObject &json);

    // 终端模拟器渲染
    void printWelcomePanel(int frame);
    void printResultWorkspace();
    void printSplitPanel(const QString &title, const QStringList &leftLines, const QStringList &rightLines);
    void printHelp();
    void printStatus();
    
    // 输入与命令处理
    void handleInput(const QString &input);
    void executeSlashCommand(const QString &cmd, const QString &args);
    void appendTerminalText(const QString &text, const QString &colorHtml);
    void appendLeftText(const QString &text, const QString &colorHtml);
    void appendRightText(const QString &text, const QString &colorHtml);
    void updatePrompt();

    // 视觉排版对齐计算（兼容中英文等宽排列）
    int terminalUiWidth() const;
    int visualWidth(const QString &text) const;
    QString truncateVisual(const QString &text, int width) const;
    QString padVisual(const QString &text, int width) const;
    QString padVisualUntruncated(const QString &text, int width) const;
    QStringList wrapVisual(const QString &text, int width) const;
    QString centerVisual(const QString &text, int width) const;

    // UFO ASCII Mascot 牵引光束吸人逐帧绘制器
    QStringList renderDefaultMascotFrame(int frame, int width) const;
    void drawBeam(QVector<QString> &canvas, int center, int phase) const;
    void drawWalkingPerson(QVector<QString> &canvas, int row, int col, int phase) const;
    void drawPerson(QVector<QString> &canvas, int row, int col) const;
    void drawSmallPerson(QVector<QString> &canvas, int row, int col) const;
    void overlay(QVector<QString> &canvas, int row, int col, const QString &text) const;

    // UI 组件
    QSplitter *m_splitter;
    QTextEdit *m_leftDisplay;

    QTextEdit *m_rightDisplay;
    QLabel *m_promptLabel;
    QLineEdit *m_terminalInput;

    // 后端进程与动画计时器
    QProcess *m_process;
    QTimer *m_mascotTimer;

    // 运行状态与配置
    QString m_currentMode;      // "chat" 或 "console"
    QString m_projectName;      // 当前项目名，如 "demo"
    QString m_conversationId;   // 当前会话，如 "default"
    int m_mascotFrame;          // Mascot 动画当前帧
    bool m_isShowingWelcome;    // 是否处于欢迎动画界面
    
    // 缓存最近一次拆解的运行数据以用于渲染
    double m_lastElapsed;
    int m_lastTokens;
    QString m_lastTokenNote;
    QJsonObject m_lastPlan;
    QJsonArray m_lastQuestions;
    QString m_lastGoal;
};

#endif // MAINWINDOW_H
