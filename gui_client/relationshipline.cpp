#include "relationshipline.h"
#include "taskcarditem.h"
#include "theme.h"
#include <QPen>
#include <QPainter>
#include <QPainterPath>
#include <QFont>
#include <QFontMetrics>
#include <QtMath>

RelationshipLine::RelationshipLine(TaskCardItem *source, TaskCardItem *target,
                                   const QString &relationType, const Theme *theme,
                                   QGraphicsItem *parent)
    : QGraphicsPathItem(parent)
    , m_source(source)
    , m_target(target)
    , m_relationType(relationType)
    , m_theme(theme)
{
    setZValue(-1);
    setFlag(QGraphicsItem::ItemIsSelectable, true);
    updatePath();
}

void RelationshipLine::setTheme(const Theme *theme) {
    m_theme = theme;
    update();
}

QString RelationshipLine::sourceId() const { return m_source ? m_source->taskId() : ""; }
QString RelationshipLine::targetId() const { return m_target ? m_target->taskId() : ""; }
QString RelationshipLine::relationType() const { return m_relationType; }

QJsonObject RelationshipLine::toJson() const {
    QJsonObject obj;
    obj["source_id"] = sourceId();
    obj["target_id"] = targetId();
    obj["relation_type"] = m_relationType;
    return obj;
}

QColor RelationshipLine::lineColor() const {
    if (!m_theme) {
        if (m_relationType == "blocking") return QColor("#e74c3c");
        if (m_relationType == "parallel") return QColor("#9b59b6");
        return QColor("#5dade2");
    }
    if (m_relationType == "blocking") return m_theme->lineBlocking;
    if (m_relationType == "parallel") return m_theme->lineParallel;
    return m_theme->lineSequential;
}

// ── 路径计算 ─────────────────────────────────────────────────────

void RelationshipLine::updatePath() {
    if (!m_source || !m_target) return;
    setPath(buildPath());
}

QPainterPath RelationshipLine::buildPath() const {
    QPointF start, end;

    // 计算最佳锚点方向
    QPointF sCenter = m_source->pos() + QPointF(260 / 2, m_source->boundingRect().height() / 2);
    QPointF tCenter = m_target->pos() + QPointF(260 / 2, m_target->boundingRect().height() / 2);
    QPointF delta = tCenter - sCenter;

    if (qAbs(delta.x()) > qAbs(delta.y())) {
        // 水平方向为主
        if (delta.x() > 0) {
            start = m_source->rightAnchor();
            end = m_target->leftAnchor();
        } else {
            start = m_source->leftAnchor();
            end = m_target->rightAnchor();
        }
    } else {
        // 垂直方向为主
        if (delta.y() > 0) {
            start = m_source->bottomAnchor();
            end = m_target->topAnchor();
        } else {
            start = m_source->topAnchor();
            end = m_target->bottomAnchor();
        }
    }

    // 贝塞尔曲线，使连线更平滑
    QPainterPath path(start);
    qreal dx = end.x() - start.x();
    qreal dy = end.y() - start.y();
    QPointF ctrl1, ctrl2;

    if (qAbs(dx) > qAbs(dy)) {
        ctrl1 = start + QPointF(dx * 0.4, 0);
        ctrl2 = end - QPointF(dx * 0.4, 0);
    } else {
        ctrl1 = start + QPointF(0, dy * 0.4);
        ctrl2 = end - QPointF(0, dy * 0.4);
    }

    path.cubicTo(ctrl1, ctrl2, end);
    return path;
}

// ── 绘制 ────────────────────────────────────────────────────────

void RelationshipLine::paint(QPainter *paint, const QStyleOptionGraphicsItem *opt, QWidget *) {
    Q_UNUSED(opt);
    if (!m_source || !m_target) return;

    updatePath();
    QColor color = lineColor();

    QPen pen;
    pen.setColor(color);
    pen.setWidthF(2.0);

    if (m_relationType == "parallel") {
        pen.setStyle(Qt::DashLine);
        pen.setDashPattern({6, 4});
    } else {
        pen.setStyle(Qt::SolidLine);
    }

    paint->setPen(pen);
    paint->setBrush(Qt::NoBrush);
    paint->drawPath(path());

    // 箭头 / 端点
    QPainterPath p = path();
    QPointF endPoint = p.pointAtPercent(1.0);
    QPointF nearEnd = p.pointAtPercent(0.95);

    if (m_relationType == "blocking") {
        drawTBar(paint, endPoint, nearEnd);
    } else if (m_relationType == "sequential") {
        drawArrowHead(paint, endPoint, nearEnd);
    } else if (m_relationType == "parallel") {
        drawArrowHead(paint, endPoint, nearEnd);
        QPointF startPoint = p.pointAtPercent(0.0);
        QPointF nearStart = p.pointAtPercent(0.05);
        drawArrowHead(paint, startPoint, nearStart);
    }

    // 关系类型标签（悬停时显示，简化为始终显示小标签）
    QPointF mid = p.pointAtPercent(0.5);
    QFont labelFont("Consolas", 8);
    paint->setFont(labelFont);
    paint->setPen(color);

    QString label;
    if (m_relationType == "sequential") label = "顺序";
    else if (m_relationType == "parallel") label = "并行";
    else if (m_relationType == "blocking") label = "阻塞";
    else label = m_relationType;

    QFontMetrics fm(labelFont);
    int tw = fm.horizontalAdvance(label) + 8;
    int th = fm.height() + 4;
    QRectF labelRect(mid.x() - tw / 2, mid.y() - th / 2, tw, th);

    paint->setBrush(m_theme ? m_theme->bgPrimary : QColor("#0c0c0d"));
    paint->setPen(QPen(color, 1));
    paint->drawRoundedRect(labelRect, 3, 3);
    paint->drawText(labelRect, Qt::AlignCenter, label);
}

QRectF RelationshipLine::boundingRect() const {
    return path().boundingRect().adjusted(-10, -10, 10, 10);
}

void RelationshipLine::drawArrowHead(QPainter *paint, const QPointF &tip, const QPointF &from, qreal size) const {
    QPolygonF arrow;
    arrow << tip;
    qreal angle = std::atan2(tip.y() - from.y(), tip.x() - from.x());
    arrow << tip - QPointF(std::cos(angle - 0.4) * size, std::sin(angle - 0.4) * size);
    arrow << tip - QPointF(std::cos(angle + 0.4) * size, std::sin(angle + 0.4) * size);
    paint->setBrush(lineColor());
    paint->setPen(Qt::NoPen);
    paint->drawPolygon(arrow);
}

void RelationshipLine::drawTBar(QPainter *paint, const QPointF &tip, const QPointF &from, qreal size) const {
    qreal angle = std::atan2(tip.y() - from.y(), tip.x() - from.x());
    qreal perpAngle = angle + M_PI / 2;
    QPointF p1 = tip + QPointF(std::cos(perpAngle) * size / 2, std::sin(perpAngle) * size / 2);
    QPointF p2 = tip - QPointF(std::cos(perpAngle) * size / 2, std::sin(perpAngle) * size / 2);

    QPen pen = paint->pen();
    pen.setWidthF(3);
    pen.setColor(lineColor());
    paint->setPen(pen);
    paint->drawLine(p1, p2);
}
