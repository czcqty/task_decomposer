#ifndef TASKCANVAS_H
#define TASKCANVAS_H

#include <QGraphicsView>
#include <QGraphicsScene>
#include <QJsonObject>
#include <QJsonArray>
#include <QMap>
#include <QPointF>
#include <QTimer>

class TaskCardItem;
class RelationshipLine;
struct Theme;

// ────────────────────────────────────────────────────────────────
// TaskCanvas — 任务可视化画布
//
// 功能：
//   - 显示任务卡片（TaskCardItem）
//   - 显示关系连线（RelationshipLine）
//   - 支持拖拽移动、平移缩放
//   - Shift+拖拽创建新关系
//   - 自动布局算法
// ────────────────────────────────────────────────────────────────
class TaskCanvas : public QGraphicsView {
    Q_OBJECT

public:
    explicit TaskCanvas(const Theme *theme, QWidget *parent = nullptr);

    // 从后端 plan 数据加载画布内容
    void loadPlan(const QJsonObject &plan);

    // 主题切换
    void setTheme(const Theme *theme);

    // 更新单个任务（后端确认后刷新）
    void updateTask(const QJsonObject &taskData);

    // 获取当前选中的卡片
    TaskCardItem *selectedCard() const;

    // 从画布导出当前 plan 数据
    QJsonObject exportPlan() const;

signals:
    // 用户点击了一个卡片
    void taskClicked(const QString &taskId);
    // 用户通过拖拽改变了任务顺序
    void taskOrderChanged(const QStringList &taskIds);
    // 用户创建了新连线
    void relationCreated(const QString &sourceId, const QString &targetId, const QString &type);
    // 用户删除了连线
    void relationDeleted(const QString &sourceId, const QString &targetId);

protected:
    void wheelEvent(QWheelEvent *event) override;
    void mousePressEvent(QMouseEvent *event) override;
    void mouseMoveEvent(QMouseEvent *event) override;
    void mouseReleaseEvent(QMouseEvent *event) override;
    void keyPressEvent(QKeyEvent *event) override;
    void keyReleaseEvent(QKeyEvent *event) override;

private:
    void clearCanvas();
    void autoLayout();
    void buildCards(const QJsonObject &plan);
    void buildRelations(const QJsonObject &plan);
    void buildNestingRelations(const QJsonObject &plan);

    // 连线创建模式
    bool m_connectingMode = false;
    TaskCardItem *m_connectSource = nullptr;
    QGraphicsLineItem *m_connectPreview = nullptr;

    // 平移模式
    bool m_panning = false;
    QPointF m_panStart;

    // 选中
    TaskCardItem *m_selectedCard = nullptr;

    // 数据
    QGraphicsScene *m_scene;
    QMap<QString, TaskCardItem *> m_cardMap;      // task_id → 卡片
    QList<RelationshipLine *> m_relationLines;
    QJsonObject m_currentPlan;
    const Theme *m_theme;
};

#endif // TASKCANVAS_H
