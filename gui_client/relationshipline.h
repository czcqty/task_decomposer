#ifndef RELATIONSHIPLINE_H
#define RELATIONSHIPLINE_H

#include <QGraphicsPathItem>
#include <QJsonObject>
#include <QColor>

class TaskCardItem;
struct Theme;

// ────────────────────────────────────────────────────────────────
// RelationshipLine — 任务之间的关系连线
//
// 视觉样式：
//   sequential → 实线 + 箭头
//   parallel   ↔ 虚线 + 双向箭头
//   blocking   ─┤ 红色实线 + T 形端点
//   nesting    不使用连线（用父子包含表示）
// ────────────────────────────────────────────────────────────────
class RelationshipLine : public QGraphicsPathItem {
public:
    enum { Type = QGraphicsItem::UserType + 2 };
    int type() const override { return Type; }

    RelationshipLine(TaskCardItem *source, TaskCardItem *target,
                     const QString &relationType, const Theme *theme,
                     QGraphicsItem *parent = nullptr);

    // 数据
    QString sourceId() const;
    QString targetId() const;
    QString relationType() const;
    QJsonObject toJson() const;

    // 更新连线路径（卡片移动后调用）
    void updatePath();

    // 主题
    void setTheme(const Theme *theme);

    // 视觉
    void paint(QPainter *paint, const QStyleOptionGraphicsItem *opt, QWidget *w) override;
    QRectF boundingRect() const override;

    // 两端卡片
    TaskCardItem *sourceCard() const { return m_source; }
    TaskCardItem *targetCard() const { return m_target; }

private:
    QPainterPath buildPath() const;
    void drawArrowHead(QPainter *paint, const QPointF &tip, const QPointF &from, qreal size = 10) const;
    void drawTBar(QPainter *paint, const QPointF &tip, const QPointF &from, qreal size = 12) const;
    QColor lineColor() const;

    TaskCardItem *m_source;
    TaskCardItem *m_target;
    QString m_relationType;  // "sequential" | "parallel" | "blocking"
    const Theme *m_theme;
};

#endif // RELATIONSHIPLINE_H
