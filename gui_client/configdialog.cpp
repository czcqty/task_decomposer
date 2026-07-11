#include "configdialog.h"
#include "theme.h"

#include <QFormLayout>
#include <QPushButton>
#include <QLabel>
#include <QScrollArea>
#include <QHBoxLayout>

ConfigDialog::ConfigDialog(const QJsonObject &config, const Theme *theme, QWidget *parent)
    : QDialog(parent), m_theme(theme)
{
    setWindowTitle("配置面板 - Task Decomposer");
    resize(640, 580);

    if (m_theme) setStyleSheet(m_theme->configDialogQSS());

    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    m_tabWidget = new QTabWidget(this);

    // Tab 1: Model Config (Dynamic Card Key Pool)
    QWidget *modelTab = new QWidget(this);
    QVBoxLayout *modelTabLayout = new QVBoxLayout(modelTab);
    modelTabLayout->setContentsMargins(10, 10, 10, 10);
    modelTabLayout->setSpacing(8);

    // Key Pool header
    QString accentName = m_theme ? m_theme->accent.name() : "#ffb3ba";
    QString addColor = m_theme ? m_theme->addBtn.name() : "#2ecc71";
    QString delColor = m_theme ? m_theme->deleteBtn.name() : "#ff6b6b";

    QLabel *poolLabel = new QLabel("多密钥池配置 (Model Key Pool):", this);
    poolLabel->setStyleSheet(QString("font-weight: bold; color: %1; margin-top: 4px; margin-bottom: 2px;").arg(accentName));
    modelTabLayout->addWidget(poolLabel);

    // Key Pool scroll area
    QScrollArea *scrollArea = new QScrollArea(this);
    scrollArea->setWidgetResizable(true);
    QWidget *scrollContainer = new QWidget(scrollArea);
    m_rowsLayout = new QVBoxLayout(scrollContainer);
    m_rowsLayout->setContentsMargins(0, 0, 0, 0);
    m_rowsLayout->setSpacing(10);
    m_rowsLayout->addStretch(1); // Bottom spacer
    scrollArea->setWidget(scrollContainer);
    modelTabLayout->addWidget(scrollArea, 1);

    // Add Key Button
    QHBoxLayout *addBtnLayout = new QHBoxLayout();
    QPushButton *addBtn = new QPushButton("＋ 添加密钥配置", this);
    addBtn->setStyleSheet(QString(
        "QPushButton { background-color: transparent; color: %1; border: 1px solid %1; border-radius: 4px; padding: 6px 12px; font-weight: bold; }"
        "QPushButton:hover { background-color: %1; color: #ffffff; }"
    ).arg(addColor));
    addBtnLayout->addStretch();
    addBtnLayout->addWidget(addBtn);
    modelTabLayout->addLayout(addBtnLayout);

    m_tabWidget->addTab(modelTab, "模型配置");

    // Tab 2: Search Config
    QWidget *searchTab = new QWidget(this);
    QFormLayout *searchLayout = new QFormLayout(searchTab);
    searchLayout->setContentsMargins(15, 15, 15, 15);
    searchLayout->setSpacing(10);
    m_searchEnabledCheck = new QCheckBox("启用联网搜索", this);
    m_searchProviderCombo = new QComboBox(this);
    m_searchProviderCombo->addItems(QStringList() << "duckduckgo" << "tavily");
    m_tavilyKeyEdit = new QLineEdit(this);
    m_tavilyKeyEdit->setEchoMode(QLineEdit::PasswordEchoOnEdit);
    m_maxResultsCombo = new QComboBox(this);
    m_maxResultsCombo->addItems(QStringList() << "3" << "5" << "8" << "10");

    searchLayout->addRow("", m_searchEnabledCheck);
    searchLayout->addRow("搜索服务商:", m_searchProviderCombo);
    searchLayout->addRow("Tavily API Key:", m_tavilyKeyEdit);
    searchLayout->addRow("最大检索条数:", m_maxResultsCombo);
    m_tabWidget->addTab(searchTab, "联网检索");

    // Tab 3: Security
    QWidget *securityTab = new QWidget(this);
    QFormLayout *securityLayout = new QFormLayout(securityTab);
    securityLayout->setContentsMargins(15, 15, 15, 15);
    m_passwordEdit = new QLineEdit(this);
    m_passwordEdit->setEchoMode(QLineEdit::PasswordEchoOnEdit);
    securityLayout->addRow("账户登录密码(可选):", m_passwordEdit);
    m_tabWidget->addTab(securityTab, "安全校验");

    mainLayout->addWidget(m_tabWidget);

    // Bottom dialog buttons
    QHBoxLayout *btnLayout = new QHBoxLayout();
    QPushButton *cancelBtn = new QPushButton("取消", this);
    QPushButton *saveBtn = new QPushButton("保存配置", this);
    btnLayout->addStretch();
    btnLayout->addWidget(cancelBtn);
    btnLayout->addWidget(saveBtn);
    mainLayout->addLayout(btnLayout);

    connect(cancelBtn, &QPushButton::clicked, this, &QDialog::reject);
    connect(saveBtn, &QPushButton::clicked, this, &QDialog::accept);
    connect(addBtn, &QPushButton::clicked, this, [this]() {
        addKeyCard("", "openai", "", "", "");
    });

    // Populate dynamic keys
    QJsonArray keyPool = config["key_pool"].toArray();
    if (keyPool.isEmpty()) {
        addKeyCard("deepseek", "openai", "deepseek-chat", "", "https://api.deepseek.com");
    } else {
        for (int i = 0; i < keyPool.size(); ++i) {
            QJsonObject item = keyPool[i].toObject();
            addKeyCard(
                item["provider"].toString("deepseek"),
                item["protocol"].toString("openai"),
                item["model"].toString("deepseek-chat"),
                item["api_key"].toString(),
                item["base_url"].toString()
            );
        }
    }

    // Populate search & password
    QJsonObject searchObj = config["search"].toObject();
    m_searchEnabledCheck->setChecked(searchObj["enabled"].toBool(true));
    m_searchProviderCombo->setCurrentText(searchObj["provider"].toString("duckduckgo"));
    QJsonObject searchKeys = searchObj["api_keys"].toObject();
    if (searchKeys.contains("tavily")) {
        if (searchKeys["tavily"].isArray()) {
            QJsonArray arr = searchKeys["tavily"].toArray();
            if (!arr.isEmpty()) m_tavilyKeyEdit->setText(arr[0].toString());
        } else {
            m_tavilyKeyEdit->setText(searchKeys["tavily"].toString());
        }
    }
    m_maxResultsCombo->setCurrentText(QString::number(searchObj["max_results"].toInt(5)));
    m_passwordEdit->setText(config["password"].toString());
}

QJsonObject ConfigDialog::getUpdatedConfig() const {
    QJsonObject config;

    QString defaultProvider = "deepseek";
    QString defaultModel = "deepseek-chat";
    QString defaultBaseUrl = "";

    // Key Pool list of objects
    QJsonArray keyPool;
    for (QWidget *widget : m_rowWidgets) {
        QGroupBox *cardBox = qobject_cast<QGroupBox *>(widget);
        if (!cardBox) continue;

        QLineEdit *provEdit = cardBox->findChild<QLineEdit *>("providerEdit");
        QComboBox *protoCombo = cardBox->findChild<QComboBox *>("protocolCombo");
        QLineEdit *modelEdit = cardBox->findChild<QLineEdit *>("modelEdit");
        QLineEdit *keyEdit = cardBox->findChild<QLineEdit *>("keyEdit");
        QLineEdit *urlEdit = cardBox->findChild<QLineEdit *>("urlEdit");

        if (keyEdit && !keyEdit->text().trimmed().isEmpty()) {
            QJsonObject item;
            QString provider = provEdit ? provEdit->text().trimmed() : "deepseek";
            QString protocol = protoCombo ? protoCombo->currentText() : "openai";
            QString model = modelEdit ? modelEdit->text().trimmed() : "deepseek-chat";
            QString apiKey = keyEdit->text().trimmed();
            QString baseUrl = urlEdit ? urlEdit->text().trimmed() : "";

            item["provider"] = provider;
            item["protocol"] = protocol;
            item["model"] = model;
            item["api_key"] = apiKey;
            item["base_url"] = baseUrl;
            keyPool.append(item);

            // Use the first valid configuration as fallback default
            if (keyPool.size() == 1) {
                defaultProvider = provider;
                defaultModel = model;
                defaultBaseUrl = baseUrl;
            }
        }
    }
    config["key_pool"] = keyPool;
    config["provider"] = defaultProvider;
    config["model"] = defaultModel;
    config["base_url"] = defaultBaseUrl;

    // Search
    QJsonObject searchObj;
    searchObj["enabled"] = m_searchEnabledCheck->isChecked();
    searchObj["provider"] = m_searchProviderCombo->currentText();
    searchObj["max_results"] = m_maxResultsCombo->currentText().toInt();
    QJsonObject searchKeys;
    if (!m_tavilyKeyEdit->text().trimmed().isEmpty()) {
        QJsonArray arr;
        arr.append(m_tavilyKeyEdit->text().trimmed());
        searchKeys["tavily"] = arr;
    }
    searchObj["api_keys"] = searchKeys;
    config["search"] = searchObj;

    config["password"] = m_passwordEdit->text();
    return config;
}

void ConfigDialog::addKeyCard(const QString &provider, const QString &protocol,
                              const QString &model, const QString &apiKey, const QString &baseUrl) {
    QGroupBox *cardBox = new QGroupBox(this);
    cardBox->setObjectName("keyCard");

    QVBoxLayout *cardLayout = new QVBoxLayout(cardBox);
    cardLayout->setContentsMargins(15, 15, 15, 12);
    cardLayout->setSpacing(8);

    // Row 1: Provider, Protocol, Model Name
    QHBoxLayout *row1 = new QHBoxLayout();
    row1->setSpacing(8);

    QLabel *provLabel = new QLabel("供应商:", cardBox);
    QLineEdit *provEdit = new QLineEdit(cardBox);
    provEdit->setObjectName("providerEdit");
    provEdit->setPlaceholderText("例如: deepseek");
    provEdit->setText(provider.isEmpty() ? "deepseek" : provider);
    provEdit->setMinimumWidth(100);

    QLabel *protoLabel = new QLabel("协议:", cardBox);
    QComboBox *protoCombo = new QComboBox(cardBox);
    protoCombo->setObjectName("protocolCombo");
    protoCombo->addItems(QStringList() << "openai" << "claude");
    protoCombo->setCurrentText(protocol.isEmpty() ? "openai" : protocol.trimmed().toLower());
    protoCombo->setMinimumWidth(80);

    QLabel *modelLabel = new QLabel("模型名称:", cardBox);
    QLineEdit *modelEdit = new QLineEdit(cardBox);
    modelEdit->setObjectName("modelEdit");
    modelEdit->setPlaceholderText("例如: deepseek-chat");
    modelEdit->setText(model.isEmpty() ? "deepseek-chat" : model);

    row1->addWidget(provLabel);
    row1->addWidget(provEdit, 2);
    row1->addWidget(protoLabel);
    row1->addWidget(protoCombo, 1);
    row1->addWidget(modelLabel);
    row1->addWidget(modelEdit, 3);

    // Row 2: API Key and Base URL
    QHBoxLayout *row2 = new QHBoxLayout();
    row2->setSpacing(8);

    QLabel *keyLabel = new QLabel("API Key:", cardBox);
    QLineEdit *keyEdit = new QLineEdit(cardBox);
    keyEdit->setObjectName("keyEdit");
    keyEdit->setEchoMode(QLineEdit::PasswordEchoOnEdit);
    keyEdit->setPlaceholderText("请输入 API Key");
    keyEdit->setText(apiKey);

    QLabel *urlLabel = new QLabel("Base URL:", cardBox);
    QLineEdit *urlEdit = new QLineEdit(cardBox);
    urlEdit->setObjectName("urlEdit");
    urlEdit->setPlaceholderText("自定义 Base URL (可选)");
    urlEdit->setText(baseUrl);

    row2->addWidget(keyLabel);
    row2->addWidget(keyEdit, 2);
    row2->addWidget(urlLabel);
    row2->addWidget(urlEdit, 2);

    // Row 3: Action buttons
    QHBoxLayout *row3 = new QHBoxLayout();
    row3->addStretch(1);
    QPushButton *delBtn = new QPushButton("删除密钥", cardBox);
    QString dc = m_theme ? m_theme->deleteBtn.name() : "#ff6b6b";
    delBtn->setStyleSheet(QString(
        "QPushButton { background-color: transparent; color: %1; border: 1px solid %1; padding: 4px 10px; font-weight: normal; font-size: 12px; border-radius: 4px; }"
        "QPushButton:hover { background-color: %1; color: #ffffff; }"
    ).arg(dc));
    row3->addWidget(delBtn);

    cardLayout->addLayout(row1);
    cardLayout->addLayout(row2);
    cardLayout->addLayout(row3);

    // Remove the bottom spacer before inserting the card
    m_rowsLayout->takeAt(m_rowsLayout->count() - 1);
    m_rowsLayout->addWidget(cardBox);
    m_rowsLayout->addStretch(1); // Re-append spacer at the bottom

    m_rowWidgets.append(cardBox);

    // Renumber all cards
    renumberCards();

    connect(delBtn, &QPushButton::clicked, this, [this, cardBox]() {
        m_rowWidgets.removeOne(cardBox);
        cardBox->deleteLater();
        renumberCards();
    });

    // Smart autofill helper based on provider text edits
    connect(provEdit, &QLineEdit::textChanged, this, [provEdit, protoCombo, modelEdit, urlEdit](const QString &text) {
        QString clean = text.trimmed().toLower();
        if (clean == "deepseek") {
            protoCombo->setCurrentText("openai");
            if (modelEdit->text().trimmed().isEmpty() || modelEdit->text() == "gpt-4.1-mini" || modelEdit->text() == "claude-3-5-haiku-latest") {
                modelEdit->setText("deepseek-chat");
            }
            if (urlEdit->text().trimmed().isEmpty() || urlEdit->text().contains("openai.com") || urlEdit->text().contains("anthropic.com")) {
                urlEdit->setText("https://api.deepseek.com");
            }
        } else if (clean == "openai") {
            protoCombo->setCurrentText("openai");
            if (modelEdit->text().trimmed().isEmpty() || modelEdit->text() == "deepseek-chat" || modelEdit->text() == "claude-3-5-haiku-latest") {
                modelEdit->setText("gpt-4.1-mini");
            }
            if (urlEdit->text().trimmed() == "https://api.deepseek.com" || urlEdit->text().contains("anthropic.com")) {
                urlEdit->setText("");
            }
        } else if (clean == "claude" || clean == "anthropic") {
            protoCombo->setCurrentText("claude");
            if (modelEdit->text().trimmed().isEmpty() || modelEdit->text() == "deepseek-chat" || modelEdit->text() == "gpt-4.1-mini") {
                modelEdit->setText("claude-3-5-haiku-latest");
            }
            if (urlEdit->text().trimmed() == "https://api.deepseek.com" || urlEdit->text().contains("openai.com")) {
                urlEdit->setText("");
            }
        }
    });
}

void ConfigDialog::renumberCards() {
    int index = 1;
    for (QWidget *widget : m_rowWidgets) {
        QGroupBox *cardBox = qobject_cast<QGroupBox *>(widget);
        if (cardBox) {
            cardBox->setTitle(QString("#%1").arg(index++));
        }
    }
}
