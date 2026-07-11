#ifndef TASKCARDITEM_H
#define TASKCARDITEM_H

#include <QGraphicsItem>
#include <QJsonObject>
#include <QGraphicsSceneMouseEvent>
#include <QColor>

struct Theme;

// ────────────────────────────────────────────────────────────────
// TaskCardItem — 一个可拖拽的任务卡片方块
// ────────────────────────────────────────────────────────────────
class TaskCardItem : public QGraphicsItem {
public:
    enum { Type = QGraphicsItem::UserType + 1 };
    int type() const override { return Type; }

    explicit TaskCardItem(const QJsonObject &taskData, const Theme *theme, QGraphicsItem *parent = nullptr);

    // 数据访问
    QString taskId() const;
    QString title() const;
    QString action() const;
    QString output() const;
    QString status() const;
    void setData(const QJsonObject &data);
    QJsonObject toJson() const;

    // 布局
    QRectF boundingRect() const override;
    void paint(QPainter *paint, const QStyleOptionGraphicsItem *opt, QWidget *w) override;
    void updateLayout();

    // 嵌套子任务
    void addChildCard(TaskCardItem *child);
    void removeChildCard(TaskCardItem *child);
    QList<TaskCardItem *> childCards() const;
    TaskCardItem *parentCard() const;

    // 连线锚点
    QPointF topAnchor() const;
    QPointF bottomAnchor() const;
    QPointF leftAnchor() const;
    QPointF rightAnchor() const;

    // 选中态
    void setSelected(bool selected);

    // 主题
    void setTheme(const Theme *theme);

protected:
    void mousePressEvent(QGraphicsSceneMouseEvent *event) override;
    void mouseReleaseEvent(QGraphicsSceneMouseEvent *event) override;
    void hoverEnterEvent(QGraphicsSceneHoverEvent *event) override;
    void hoverLeaveEvent(QGraphicsSceneHoverEvent *event) override;

private:
    void drawBackground(QPainter *paint, const QRectF &rect, const QColor &borderColor);
    void drawStatusBadge(QPainter *paint, const QRectF &rect, const QString &status);
    QColor statusColor(const QString &status) const;
    QColor borderColorForStatus(const QString &status) const;

    const Theme *m_theme;

    QString m_taskId;
    QString m_title;
    QString m_action;
    QString m_output;
    QString m_status;

    qreal m_width = 260;
    qreal m_titleHeight = 32;
    qreal m_actionHeight = 0;
    qreal m_outputHeight = 0;
    qreal m_padding = 12;
    qreal m_totalHeight = 80;

    bool m_hovered = false;
    bool m_selected = false;

    QList<TaskCardItem *> m_children;
};

#endif // TASKCARDITEM_H
