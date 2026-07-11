#include "theme.h"

// ────────────────────────────────────────────────────────────────
// 现代主题（默认）— 类似 Notion / Linear / Raycast
// ────────────────────────────────────────────────────────────────
Theme modernTheme() {
    Theme t;

    t.bgPrimary     = QColor("#f8f9fa");
    t.bgCanvas      = QColor("#ffffff");
    t.bgSurface     = QColor("#ffffff");
    t.bgCard        = QColor("#ffffff");
    t.bgInput       = QColor("#f0f2f5");

    t.borderPrimary = QColor("#e5e7eb");
    t.borderSubtle  = QColor("#f0f0f0");
    t.borderHover   = QColor("#c7d2fe");

    t.textPrimary   = QColor("#1f2937");
    t.textSecondary = QColor("#6b7280");
    t.textMuted     = QColor("#9ca3af");
    t.textDisabled  = QColor("#d1d5db");

    t.accent        = QColor("#6366f1");  // indigo-500
    t.accentHover   = QColor("#818cf8");  // indigo-400
    t.accentPressed = QColor("#4f46e5");  // indigo-600

    t.statusDone           = QColor("#10b981");  // emerald-500
    t.statusDoneBorder     = QColor("#059669");  // emerald-600
    t.statusProgress       = QColor("#3b82f6");  // blue-500
    t.statusProgressBorder = QColor("#2563eb");  // blue-600
    t.statusBlocked        = QColor("#ef4444");  // red-500
    t.statusBlockedBorder  = QColor("#dc2626");  // red-600
    t.statusPending        = QColor("#6b7280");  // gray-500
    t.statusPendingBorder  = QColor("#9ca3af");  // gray-400

    t.lineSequential = QColor("#6366f1");  // indigo
    t.lineParallel   = QColor("#8b5cf6");  // violet
    t.lineBlocking   = QColor("#ef4444");  // red

    t.deleteBtn      = QColor("#ef4444");
    t.deleteBtnHover = QColor("#dc2626");
    t.addBtn         = QColor("#10b981");

    t.fontFamily     = "Segoe UI, Microsoft YaHei, sans-serif";
    t.fontFamilyMono = "Cascadia Code, Consolas, monospace";

    return t;
}

// ────────────────────────────────────────────────────────────────
// 复古主题 — 现有深色霓虹风
// ────────────────────────────────────────────────────────────────
Theme retroTheme() {
    Theme t;

    t.bgPrimary     = QColor("#0c0c0d");
    t.bgCanvas      = QColor("#0a0a0f");
    t.bgSurface     = QColor("#111115");
    t.bgCard        = QColor("#16161c");
    t.bgInput       = QColor("#1a1a20");

    t.borderPrimary = QColor("#2c2c38");
    t.borderSubtle  = QColor("#1a1a20");
    t.borderHover   = QColor("#4c4c58");

    t.textPrimary   = QColor("#ffffff");
    t.textSecondary = QColor("#b0b0b8");
    t.textMuted     = QColor("#8e8e93");
    t.textDisabled  = QColor("#555555");

    t.accent        = QColor("#ffb3ba");
    t.accentHover   = QColor("#ffc0cb");
    t.accentPressed = QColor("#ff9da6");

    t.statusDone           = QColor("#2ecc71");
    t.statusDoneBorder     = QColor("#27ae60");
    t.statusProgress       = QColor("#3498db");
    t.statusProgressBorder = QColor("#2980b9");
    t.statusBlocked        = QColor("#e74c3c");
    t.statusBlockedBorder  = QColor("#c0392b");
    t.statusPending        = QColor("#7f8c8d");
    t.statusPendingBorder  = QColor("#3c3c4a");

    t.lineSequential = QColor("#5dade2");
    t.lineParallel   = QColor("#9b59b6");
    t.lineBlocking   = QColor("#e74c3c");

    t.deleteBtn      = QColor("#ff6b6b");
    t.deleteBtnHover = QColor("#e74c3c");
    t.addBtn         = QColor("#2ecc71");

    t.fontFamily     = "Consolas, Courier New, monospace";
    t.fontFamilyMono = "Consolas, Courier New, monospace";

    return t;
}

// ────────────────────────────────────────────────────────────────
// QSS 生成
// ────────────────────────────────────────────────────────────────

QString Theme::globalQSS() const {
    return QString(R"(
        QMainWindow { background-color: %1; }
        #promptLabel { color: %2; font-weight: bold; padding: 0 8px; }
        #terminalInput {
            background-color: %3; color: %4; border: 1px solid %5;
            border-radius: 6px; padding: 8px 12px; font-family: '%6'; font-size: 13px;
        }
        #terminalInput:focus { border: 1px solid %7; }
        #inputContainer { background-color: %1; border: 1px solid %5; border-radius: 8px; }
        #decomposeBtn {
            background-color: %7; color: %8; border: none; border-radius: 6px;
            padding: 8px 20px; font-weight: bold; font-family: '%6'; font-size: 13px;
        }
        #decomposeBtn:hover { background-color: %9; }
        #decomposeBtn:pressed { background-color: %10; }
        #decomposeBtn:disabled { background-color: %11; color: %12; }
        #themeSwitchBtn {
            background-color: transparent; color: %13; border: 1px solid %5;
            border-radius: 6px; padding: 6px 12px; font-family: '%6'; font-size: 11px;
        }
        #themeSwitchBtn:hover { border-color: %7; color: %7; }
        #welcomeTitle { color: %7; font-size: 28px; font-family: '%6'; font-weight: bold; }
        #welcomeHint { color: %13; font-size: 14px; font-family: '%6'; margin-top: 12px; }
        #welcomeTips { color: %12; font-size: 12px; font-family: '%6'; margin-top: 24px; line-height: 1.8; }
    )")
    .arg(bgPrimary.name())         // %1
    .arg(accent.name())            // %2  prompt label
    .arg(bgInput.name())           // %3  input bg
    .arg(textPrimary.name())       // %4  input text
    .arg(borderPrimary.name())     // %5  border
    .arg(fontFamily)               // %6  font
    .arg(accent.name())            // %7  accent
    .arg(bgPrimary.name())         // %8  btn text (dark on light, light on dark)
    .arg(accentHover.name())       // %9  btn hover
    .arg(accentPressed.name())     // %10 btn pressed
    .arg(bgInput.name())           // %11 disabled bg
    .arg(textDisabled.name())      // %12 disabled text
    .arg(textMuted.name())         // %13 muted text
    ;
}

QString Theme::dialogQSS() const {
    // 对于现代主题，对话框用深色文字；复古主题用浅色文字
    bool isDark = textPrimary.lightness() > 128;
    QString dialogBg = isDark ? bgPrimary.name() : bgPrimary.name();
    QString dialogText = textPrimary.name();

    return QString(R"(
        QDialog { background-color: %1; color: %2; }
        QLabel { color: %3; font-family: '%4'; font-size: 13px; }
        QLineEdit { background-color: %5; color: %2; border: 1px solid %6; border-radius: 4px; padding: 6px; font-family: '%4'; font-size: 13px; }
        QLineEdit:focus { border: 1px solid %7; }
        QComboBox { background-color: %5; color: %2; border: 1px solid %6; border-radius: 4px; padding: 4px; font-family: '%4'; }
        QCheckBox { color: %3; font-family: '%4'; }
        QTabWidget::panel { border: 1px solid %6; background-color: %1; border-radius: 4px; }
        QTabBar::tab { background-color: %5; color: %3; padding: 8px 12px; border-top-left-radius: 4px; border-top-right-radius: 4px; font-family: '%4'; }
        QTabBar::tab:selected { background-color: %1; color: %7; border: 1px solid %6; border-bottom: none; }
        QPushButton { background-color: %5; color: %2; border: 1px solid %6; border-radius: 4px; padding: 6px 12px; font-weight: bold; font-family: '%4'; }
        QPushButton:hover { border: 1px solid %7; color: %7; }
        QPushButton:pressed { background-color: %6; }
        QScrollArea { border: none; background-color: %1; }
        QGroupBox { border: 1px solid %6; border-radius: 6px; margin-top: 15px; padding-top: 22px; background-color: %8; }
        QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 12px; padding: 0 5px; color: %7; font-family: '%4'; font-weight: bold; font-size: 13px; }
    )")
    .arg(dialogBg)                 // %1
    .arg(dialogText)               // %2
    .arg(textMuted.name())         // %3
    .arg(fontFamily)               // %4
    .arg(bgInput.name())           // %5
    .arg(borderPrimary.name())     // %6
    .arg(accent.name())            // %7
    .arg(bgSurface.name())         // %8
    ;
}

QString Theme::detailPanelQSS() const {
    return QString(R"(
        QWidget { background-color: %1; color: %2; }
        QLabel { color: %3; font-family: '%4'; font-size: 12px; }
        QLineEdit { background-color: %5; color: %2; border: 1px solid %6; border-radius: 4px; padding: 6px; font-family: '%4'; font-size: 12px; }
        QLineEdit:focus { border: 1px solid %7; }
        QTextEdit { background-color: %5; color: %2; border: 1px solid %6; border-radius: 4px; padding: 6px; font-family: '%4'; font-size: 12px; }
        QTextEdit:focus { border: 1px solid %7; }
        QComboBox { background-color: %5; color: %2; border: 1px solid %6; border-radius: 4px; padding: 4px; font-family: '%4'; }
        QPushButton { background-color: %5; color: %2; border: 1px solid %6; border-radius: 4px; padding: 6px 12px; font-weight: bold; font-family: '%4'; }
        QPushButton:hover { border: 1px solid %7; color: %7; }
        QPushButton:pressed { background-color: %6; }
        QListWidget { background-color: %5; color: %8; border: 1px solid %6; border-radius: 4px; font-family: '%4'; font-size: 11px; }
    )")
    .arg(bgSurface.name())         // %1
    .arg(textPrimary.name())       // %2
    .arg(textMuted.name())         // %3
    .arg(fontFamily)               // %4
    .arg(bgInput.name())           // %5
    .arg(borderPrimary.name())     // %6
    .arg(accent.name())            // %7
    .arg(textSecondary.name())     // %8
    ;
}

QString Theme::canvasScrollbarQSS() const {
    return QString(R"(
        QScrollBar:vertical { border: none; background-color: %1; width: 6px; }
        QScrollBar::handle:vertical { background-color: %2; border-radius: 3px; min-height: 20px; }
        QScrollBar::handle:vertical:hover { background-color: %3; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QScrollBar:horizontal { border: none; background-color: %1; height: 6px; }
        QScrollBar::handle:horizontal { background-color: %2; border-radius: 3px; min-width: 20px; }
        QScrollBar::handle:horizontal:hover { background-color: %3; }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
    )")
    .arg(bgPrimary.name())         // %1
    .arg(borderPrimary.name())     // %2
    .arg(borderHover.name())       // %3
    ;
}

QString Theme::configDialogQSS() const {
    return dialogQSS();  // 复用对话框样式
}
