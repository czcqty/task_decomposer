#ifndef CONFIGDIALOG_H
#define CONFIGDIALOG_H

#include <QDialog>
#include <QJsonObject>
#include <QJsonArray>
#include <QTabWidget>
#include <QVBoxLayout>
#include <QLineEdit>
#include <QComboBox>
#include <QCheckBox>
#include <QList>
#include <QWidget>
#include <QGroupBox>

struct Theme;

// ────────────────────────────────────────────────────────────────
// ConfigDialog — 配置面板对话框
// 从 MainWindow 拆出的独立组件
// ────────────────────────────────────────────────────────────────
class ConfigDialog : public QDialog {
    Q_OBJECT

public:
    explicit ConfigDialog(const QJsonObject &config, const Theme *theme, QWidget *parent = nullptr);
    QJsonObject getUpdatedConfig() const;

private:
    void addKeyCard(const QString &provider, const QString &protocol,
                    const QString &model, const QString &apiKey, const QString &baseUrl);
    void renumberCards();

    QTabWidget *m_tabWidget;
    QVBoxLayout *m_rowsLayout;
    QList<QWidget *> m_rowWidgets;

    QCheckBox *m_searchEnabledCheck;
    QComboBox *m_searchProviderCombo;
    QLineEdit *m_tavilyKeyEdit;
    QComboBox *m_maxResultsCombo;
    QLineEdit *m_passwordEdit;
    const Theme *m_theme;
};

#endif // CONFIGDIALOG_H
