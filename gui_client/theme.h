#ifndef THEME_H
#define THEME_H

#include <QColor>
#include <QString>

// ────────────────────────────────────────────────────────────────
// Theme — 统一颜色主题定义
//
// 所有颜色从这里读取，不再硬编码。
// 提供 modernTheme() 和 retroTheme() 两套预设。
// ────────────────────────────────────────────────────────────────
struct Theme {
    // 背景层级（由深到浅）
    QColor bgPrimary;       // 主窗口背景
    QColor bgCanvas;        // 画布背景
    QColor bgSurface;       // 面板/GroupBox 背景
    QColor bgCard;          // 卡片填充
    QColor bgInput;         // 输入框/控件背景

    // 边框
    QColor borderPrimary;   // 标准边框
    QColor borderSubtle;    // 微妙分隔线
    QColor borderHover;     // 悬停边框/滚动条

    // 文字
    QColor textPrimary;     // 主文字
    QColor textSecondary;   // 次要文字
    QColor textMuted;       // 弱化/标签文字
    QColor textDisabled;    // 禁用文字

    // 强调色
    QColor accent;          // 主强调色
    QColor accentHover;     // 悬停
    QColor accentPressed;   // 按下

    // 语义状态色（填充 + 边框）
    QColor statusDone;
    QColor statusDoneBorder;
    QColor statusProgress;
    QColor statusProgressBorder;
    QColor statusBlocked;
    QColor statusBlockedBorder;
    QColor statusPending;
    QColor statusPendingBorder;

    // 关系线
    QColor lineSequential;
    QColor lineParallel;
    QColor lineBlocking;

    // 特殊
    QColor deleteBtn;
    QColor deleteBtnHover;
    QColor addBtn;

    // 字体族
    QString fontFamily;       // 正文/UI 字体
    QString fontFamilyMono;   // 等宽/代码字体

    // ── QSS 生成 ──
    QString globalQSS() const;
    QString dialogQSS() const;
    QString detailPanelQSS() const;
    QString canvasScrollbarQSS() const;
    QString configDialogQSS() const;
};

// 两套预设
Theme modernTheme();
Theme retroTheme();

#endif // THEME_H
