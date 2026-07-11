#include "taskcarditem.h"
#include "theme.h"
#include <QFontMetrics>
#include <QGraphicsScene>
#include <QPainter>
#include <QCursor>

TaskCardItem::TaskCardItem(const QJsonObject &taskData, const Theme *theme, QGraphicsItem *parent)
    : QGraphicsItem(parent), m_theme(theme)
{
    setFlag(QGraphicsItem::ItemIsMovable, true);
    setFlag(QGraphicsItem::ItemSendsGeometryChanges, true);
    setAcceptHoverEvents(true);
    setData(taskData);
}

// ── 数据 ────────────────────────────────────────────────────────

QString TaskCardItem::taskId() const { return m_taskId; }
QString TaskCardItem::title() const { return m_title; }
QString TaskCardItem::action() const { return m_action; }
QString TaskCardItem::output() const { return m_output; }
QString TaskCardItem::status() const { return m_status; }

void TaskCardItem::setData(const QJsonObject &data) {
    m_taskId = data["task_id"].toString();
    m_title = data["title"].toString();
    m_action = data["action"].toString();
    m_output = data["output"].toString();
    m_status = data["status"].toString("pending");
    updateLayout();
}

QJsonObject TaskCardItem::toJson() const {
    QJsonObject obj;
    obj["task_id"] = m_taskId;
    obj["title"] = m_title;
    obj["action"] = m_action;
    obj["output"] = m_output;
    obj["status"] = m_status;
    return obj;
}

void TaskCardItem::setTheme(const Theme *theme) {
    m_theme = theme;
    update();
}

// ── 尺寸计算 ─────────────────────────────────────────────────────

QRectF TaskCardItem::boundingRect() const {
    return QRectF(-2, -2, m_width + 4, m_totalHeight + 4);
}

void TaskCardItem::updateLayout() {
    QString ff = m_theme ? m_theme->fontFamilyMono : "Consolas";
    QFont titleFont(ff, 12, QFont::Bold);
    QFont bodyFont(ff, 10);
    QFontMetrics titleFm(titleFont);
    QFontMetrics bodyFm(bodyFont);

    qreal textWidth = m_width - m_padding * 2;

    m_titleHeight = titleFm.boundingRect(QRectF(0, 0, textWidth, 0).toRect(),
                                         Qt::TextWordWrap, m_title).height() + 8;
    m_actionHeight = bodyFm.boundingRect(QRectF(0, 0, textWidth, 0).toRect(),
                                         Qt::TextWordWrap, m_action).height() + 4;
    m_outputHeight = bodyFm.boundingRect(QRectF(0, 0, textWidth, 0).toRect(),
                                         Qt::TextWordWrap, m_output).height() + 4;

    m_totalHeight = m_padding + m_titleHeight + 4 + m_actionHeight + 4 + m_outputHeight + m_padding;

    if (!m_children.isEmpty()) {
        m_totalHeight += 16;
        for (auto *child : m_children) {
            m_totalHeight += child->boundingRect().height() + 8;
        }
        m_totalHeight += 8;
    }

    prepareGeometryChange();
    update();
}

// ── 绘制 ────────────────────────────────────────────────────────

void TaskCardItem::paint(QPainter *paint, const QStyleOptionGraphicsItem *, QWidget *) {
    paint->setRenderHint(QPainter::Antialiasing, true);

    QRectF rect(0, 0, m_width, m_totalHeight);
    QColor border = m_selected
        ? (m_theme ? m_theme->accent : QColor("#ffb3ba"))
        : borderColorForStatus(m_status);
    if (m_hovered && !m_selected) border = border.lighter(130);

    drawBackground(paint, rect, border);
    drawStatusBadge(paint, rect, m_status);

    // 标题
    QString ff = m_theme ? m_theme->fontFamilyMono : "Consolas";
    QFont titleFont(ff, 12, QFont::Bold);
    paint->setFont(titleFont);
    paint->setPen(m_theme ? m_theme->textPrimary : QColor("#ffffff"));
    QRectF titleRect(m_padding, m_padding, m_width - m_padding * 2 - 60, m_titleHeight);
    paint->drawText(titleRect, Qt::TextWordWrap | Qt::AlignLeft | Qt::AlignVCenter, m_title);

    // action
    QFont bodyFont(ff, 10);
    paint->setFont(bodyFont);
    paint->setPen(m_theme ? m_theme->textSecondary : QColor("#b0b0b8"));
    qreal y = m_padding + m_titleHeight + 4;
    QRectF actionRect(m_padding, y, m_width - m_padding * 2, m_actionHeight);
    paint->drawText(actionRect, Qt::TextWordWrap | Qt::AlignLeft | Qt::AlignTop, m_action);

    // output
    y += m_actionHeight + 4;
    paint->setPen(m_theme ? m_theme->textMuted : QColor("#8e8e93"));
    QRectF outputRect(m_padding, y, m_width - m_padding * 2, m_outputHeight);
    paint->drawText(outputRect, Qt::TextWordWrap | Qt::AlignLeft | Qt::AlignTop, m_output);
}

void TaskCardItem::drawBackground(QPainter *paint, const QRectF &rect, const QColor &borderColor) {
    if (m_hovered || m_selected) {
        paint->setPen(Qt::NoPen);
        paint->setBrush(QColor(0, 0, 0, m_theme && m_theme->textPrimary.lightness() < 128 ? 25 : 60));
        paint->drawRoundedRect(rect.translated(2, 2), 8, 8);
    }
    paint->setBrush(m_theme ? m_theme->bgCard : QColor("#16161c"));
    paint->setPen(QPen(borderColor, m_selected ? 2.0 : 1.2));
    paint->drawRoundedRect(rect, 8, 8);
}

void TaskCardItem::drawStatusBadge(QPainter *paint, const QRectF &rect, const QString &status) {
    QString ff = m_theme ? m_theme->fontFamilyMono : "Consolas";
    QFont badgeFont(ff, 9, QFont::Bold);
    QFontMetrics fm(badgeFont);
    QString label;
    if (status == "done") label = "✓ Done";
    else if (status == "in_progress") label = "● Active";
    else if (status == "blocked") label = "⊘ Blocked";
    else label = "○ Pending";

    int tw = fm.horizontalAdvance(label) + 12;
    int th = fm.height() + 4;
    QRectF badgeRect(rect.right() - m_padding - tw, m_padding, tw, th);

    paint->setBrush(statusColor(status));
    paint->setPen(Qt::NoPen);
    paint->drawRoundedRect(badgeRect, 4, 4);

    paint->setFont(badgeFont);
    paint->setPen(m_theme ? m_theme->textPrimary : QColor("#ffffff"));
    paint->drawText(badgeRect, Qt::AlignCenter, label);
}

QColor TaskCardItem::statusColor(const QString &status) const {
    if (!m_theme) {
        if (status == "done") return QColor("#2ecc71");
        if (status == "in_progress") return QColor("#3498db");
        if (status == "blocked") return QColor("#e74c3c");
        return QColor("#7f8c8d");
    }
    if (status == "done") return m_theme->statusDone;
    if (status == "in_progress") return m_theme->statusProgress;
    if (status == "blocked") return m_theme->statusBlocked;
    return m_theme->statusPending;
}

QColor TaskCardItem::borderColorForStatus(const QString &status) const {
    if (!m_theme) {
        if (status == "done") return QColor("#27ae60");
        if (status == "in_progress") return QColor("#2980b9");
        if (status == "blocked") return QColor("#c0392b");
        return QColor("#3c3c4a");
    }
    if (status == "done") return m_theme->statusDoneBorder;
    if (status == "in_progress") return m_theme->statusProgressBorder;
    if (status == "blocked") return m_theme->statusBlockedBorder;
    return m_theme->statusPendingBorder;
}

// ── 锚点 ────────────────────────────────────────────────────────

QPointF TaskCardItem::topAnchor() const {
    return pos() + QPointF(m_width / 2, 0);
}

QPointF TaskCardItem::bottomAnchor() const {
    return pos() + QPointF(m_width / 2, m_totalHeight);
}

QPointF TaskCardItem::leftAnchor() const {
    return pos() + QPointF(0, m_totalHeight / 2);
}

QPointF TaskCardItem::rightAnchor() const {
    return pos() + QPointF(m_width, m_totalHeight / 2);
}

// ── 嵌套子任务 ──────────────────────────────────────────────────

void TaskCardItem::addChildCard(TaskCardItem *child) {
    if (!child || m_children.contains(child)) return;
    m_children.append(child);
    child->setParentItem(this);
    qreal yOffset = m_padding + m_titleHeight + 4 + m_actionHeight + 4 + m_outputHeight + 16;
    for (auto *c : m_children) {
        if (c == child) break;
        yOffset += c->boundingRect().height() + 8;
    }
    child->setPos(m_padding + 8, yOffset);
    updateLayout();
}

void TaskCardItem::removeChildCard(TaskCardItem *child) {
    if (!child) return;
    m_children.removeOne(child);
    child->setParentItem(nullptr);
    updateLayout();
}

QList<TaskCardItem *> TaskCardItem::childCards() const { return m_children; }

TaskCardItem *TaskCardItem::parentCard() const {
    return dynamic_cast<TaskCardItem *>(parentItem());
}

// ── 鼠标交互 ────────────────────────────────────────────────────

void TaskCardItem::setSelected(bool sel) {
    if (m_selected == sel) return;
    m_selected = sel;
    update();
}

void TaskCardItem::mousePressEvent(QGraphicsSceneMouseEvent *event) {
    QGraphicsItem::mousePressEvent(event);
}

void TaskCardItem::mouseReleaseEvent(QGraphicsSceneMouseEvent *event) {
    QGraphicsItem::mouseReleaseEvent(event);
}

void TaskCardItem::hoverEnterEvent(QGraphicsSceneHoverEvent *) {
    m_hovered = true;
    setCursor(Qt::PointingHandCursor);
    update();
}

void TaskCardItem::hoverLeaveEvent(QGraphicsSceneHoverEvent *) {
    m_hovered = false;
    unsetCursor();
    update();
}
