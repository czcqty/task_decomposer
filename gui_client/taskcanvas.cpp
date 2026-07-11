#include "taskcanvas.h"
#include "taskcarditem.h"
#include "relationshipline.h"
#include "theme.h"
#include <QWheelEvent>
#include <QKeyEvent>
#include <QScrollBar>
#include <QGraphicsLineItem>
#include <QtMath>

TaskCanvas::TaskCanvas(const Theme *theme, QWidget *parent)
    : QGraphicsView(parent), m_theme(theme)
{
    m_scene = new QGraphicsScene(this);
    setScene(m_scene);

    setBackgroundBrush(m_theme ? m_theme->bgCanvas : QColor("#0a0a0f"));
    setRenderHint(QPainter::Antialiasing, true);
    setRenderHint(QPainter::SmoothPixmapTransform, true);
    setDragMode(QGraphicsView::NoDrag);
    setViewportUpdateMode(FullViewportUpdate);
    setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);

    if (m_theme) setStyleSheet(m_theme->canvasScrollbarQSS());

    setTransformationAnchor(AnchorUnderMouse);

    m_connectPreview = new QGraphicsLineItem();
    m_connectPreview->setPen(QPen(m_theme ? m_theme->accent : QColor("#ffb3ba"), 2, Qt::DashLine));
    m_connectPreview->setZValue(10);
    m_connectPreview->setVisible(false);
    m_scene->addItem(m_connectPreview);
}

void TaskCanvas::setTheme(const Theme *theme) {
    m_theme = theme;
    setBackgroundBrush(m_theme ? m_theme->bgCanvas : QColor("#0a0a0f"));
    if (m_theme) setStyleSheet(m_theme->canvasScrollbarQSS());
    m_connectPreview->setPen(QPen(m_theme ? m_theme->accent : QColor("#ffb3ba"), 2, Qt::DashLine));

    // 更新所有卡片和连线的主题
    for (auto *card : m_cardMap) card->setTheme(m_theme);
    for (auto *line : m_relationLines) line->setTheme(m_theme);
    update();
}

// ── 加载 Plan ───────────────────────────────────────────────────

void TaskCanvas::loadPlan(const QJsonObject &plan) {
    clearCanvas();
    m_currentPlan = plan;
    buildCards(plan);
    buildRelations(plan);
    buildNestingRelations(plan);
    autoLayout();
}

void TaskCanvas::clearCanvas() {
    m_scene->clear();
    m_cardMap.clear();
    m_relationLines.clear();
    m_selectedCard = nullptr;
    m_connectSource = nullptr;

    // 重新添加连线预览线（clear 会删除它）
    m_connectPreview = new QGraphicsLineItem();
    m_connectPreview->setPen(QPen(m_theme ? m_theme->accent : QColor("#ffb3ba"), 2, Qt::DashLine));
    m_connectPreview->setZValue(10);
    m_connectPreview->setVisible(false);
    m_scene->addItem(m_connectPreview);
}

void TaskCanvas::buildCards(const QJsonObject &plan) {
    QJsonArray tasks = plan["tasks"].toArray();
    for (const QJsonValue &val : tasks) {
        QJsonObject taskObj = val.toObject();
        QString tid = taskObj["task_id"].toString();
        if (tid.isEmpty()) continue;

        auto *card = new TaskCardItem(taskObj, m_theme);
        m_scene->addItem(card);
        m_cardMap[tid] = card;
    }
}

void TaskCanvas::buildRelations(const QJsonObject &plan) {
    QJsonArray relations = plan["relations"].toArray();
    for (const QJsonValue &val : relations) {
        QJsonObject rel = val.toObject();
        QString srcId = rel["source_id"].toString();
        QString tgtId = rel["target_id"].toString();
        QString rtype = rel["relation_type"].toString();

        // nesting 关系由父子包含表示，不画连线
        if (rtype == "nesting") continue;

        TaskCardItem *src = m_cardMap.value(srcId);
        TaskCardItem *tgt = m_cardMap.value(tgtId);
        if (!src || !tgt) continue;

        auto *line = new RelationshipLine(src, tgt, rtype, m_theme);
        m_scene->addItem(line);
        m_relationLines.append(line);
    }
}

void TaskCanvas::buildNestingRelations(const QJsonObject &plan) {
    QJsonArray relations = plan["relations"].toArray();
    for (const QJsonValue &val : relations) {
        QJsonObject rel = val.toObject();
        if (rel["relation_type"].toString() != "nesting") continue;

        QString parentId = rel["source_id"].toString();
        QString childId = rel["target_id"].toString();
        TaskCardItem *parent = m_cardMap.value(parentId);
        TaskCardItem *child = m_cardMap.value(childId);
        if (!parent || !child) continue;
        if (child->parentCard() == parent) continue;  // 已经嵌套

        parent->addChildCard(child);
    }
}

// ── 自动布局 ─────────────────────────────────────────────────────

void TaskCanvas::autoLayout() {
    // 分层布局：顶层任务水平排列，子任务在父任务内部
    QList<TaskCardItem *> topLevel;
    for (auto *card : m_cardMap) {
        if (!card->parentCard()) {
            topLevel.append(card);
        }
    }

    // 按 task_id 排序（保持原始顺序）
    std::sort(topLevel.begin(), topLevel.end(), [](TaskCardItem *a, TaskCardItem *b) {
        return a->taskId() < b->taskId();
    });

    // 尝试按顺序关系排列
    // 构建后继映射
    QMap<QString, QString> successor;  // source_id → target_id (sequential)
    QJsonArray relations = m_currentPlan["relations"].toArray();
    for (const QJsonValue &val : relations) {
        QJsonObject rel = val.toObject();
        if (rel["relation_type"].toString() == "sequential") {
            successor[rel["source_id"].toString()] = rel["target_id"].toString();
        }
    }

    // 从第一个无前驱的任务开始，按顺序链排列
    QSet<QString> hasPredecessor;
    for (auto it = successor.begin(); it != successor.end(); ++it) {
        hasPredecessor.insert(it.value());
    }

    QList<TaskCardItem *> ordered;
    QSet<QString> placed;

    // 先排顺序链
    for (auto *card : topLevel) {
        if (hasPredecessor.contains(card->taskId())) continue;
        // 从这个卡片开始沿链排
        TaskCardItem *cur = card;
        while (cur && !placed.contains(cur->taskId())) {
            ordered.append(cur);
            placed.insert(cur->taskId());
            QString nextId = successor.value(cur->taskId());
            cur = m_cardMap.value(nextId);
            if (cur && cur->parentCard()) cur = nullptr;  // 子任务不参与顶层排列
        }
    }

    // 剩余顶层任务追加
    for (auto *card : topLevel) {
        if (!placed.contains(card->taskId())) {
            ordered.append(card);
            placed.insert(card->taskId());
        }
    }

    // 布局计算
    const qreal cardWidth = 260;
    const qreal hGap = 40;
    const qreal vGap = 30;
    const qreal startX = 40;
    const qreal startY = 40;

    qreal x = startX;
    qreal maxY = startY;

    for (auto *card : ordered) {
        card->setPos(x, startY);
        x += cardWidth + hGap;
        qreal bottom = startY + card->boundingRect().height();
        if (bottom > maxY) maxY = bottom;
    }

    // 调整 scene rect
    m_scene->setSceneRect(-20, -20, x + 60, maxY + 60);

    // 更新所有连线
    for (auto *line : m_relationLines) {
        line->updatePath();
    }
}

// ── 更新单个任务 ────────────────────────────────────────────────

void TaskCanvas::updateTask(const QJsonObject &taskData) {
    QString tid = taskData["task_id"].toString();
    TaskCardItem *card = m_cardMap.value(tid);
    if (!card) return;
    card->setData(taskData);
    for (auto *line : m_relationLines) {
        line->updatePath();
    }
}

TaskCardItem *TaskCanvas::selectedCard() const { return m_selectedCard; }

QJsonObject TaskCanvas::exportPlan() const {
    QJsonObject plan = m_currentPlan;

    // 用卡片当前数据更新 tasks 数组
    QJsonArray tasks;
    for (auto it = m_cardMap.begin(); it != m_cardMap.end(); ++it) {
        tasks.append(it.value()->toJson());
    }
    plan["tasks"] = tasks;

    // 用当前连线更新 relations 数组
    QJsonArray relations;
    // 保留 nesting 关系（它们不在 m_relationLines 中）
    QJsonArray oldRels = m_currentPlan["relations"].toArray();
    for (const QJsonValue &val : oldRels) {
        if (val.toObject()["relation_type"].toString() == "nesting") {
            relations.append(val);
        }
    }
    for (auto *line : m_relationLines) {
        relations.append(line->toJson());
    }
    plan["relations"] = relations;

    return plan;
}

// ── 缩放 ────────────────────────────────────────────────────────

void TaskCanvas::wheelEvent(QWheelEvent *event) {
    if (event->modifiers() & Qt::ControlModifier) {
        double factor = (event->angleDelta().y() > 0) ? 1.15 : 1.0 / 1.15;
        scale(factor, factor);
    } else {
        QGraphicsView::wheelEvent(event);
    }
}

// ── 鼠标交互 ────────────────────────────────────────────────────

void TaskCanvas::mousePressEvent(QMouseEvent *event) {
    if (event->button() == Qt::MiddleButton ||
        (event->button() == Qt::LeftButton && event->modifiers() & Qt::AltModifier)) {
        // 平移模式
        m_panning = true;
        m_panStart = event->pos();
        setCursor(Qt::ClosedHandCursor);
        return;
    }

    if (event->button() == Qt::LeftButton) {
        QGraphicsItem *item = itemAt(event->pos());

        // Shift+左键：连线创建模式
        if (event->modifiers() & Qt::ShiftModifier) {
            auto *card = dynamic_cast<TaskCardItem *>(item);
            if (card) {
                m_connectingMode = true;
                m_connectSource = card;
                m_connectPreview->setVisible(true);
                QPointF start = card->pos() + QPointF(130, card->boundingRect().height() / 2);
                m_connectPreview->setLine(start.x(), start.y(), start.x(), start.y());
            }
            return;
        }

        // 普通左键：选中卡片
        auto *card = dynamic_cast<TaskCardItem *>(item);
        if (card) {
            if (m_selectedCard && m_selectedCard != card) {
                m_selectedCard->setSelected(false);
            }
            m_selectedCard = card;
            m_selectedCard->setSelected(true);
            emit taskClicked(card->taskId());
        } else {
            // 点击空白：取消选中
            if (m_selectedCard) {
                m_selectedCard->setSelected(false);
                m_selectedCard = nullptr;
            }
        }
    }

    QGraphicsView::mousePressEvent(event);
}

void TaskCanvas::mouseMoveEvent(QMouseEvent *event) {
    if (m_panning) {
        QPointF delta = event->pos() - m_panStart;
        m_panStart = event->pos();
        horizontalScrollBar()->setValue(horizontalScrollBar()->value() - delta.x());
        verticalScrollBar()->setValue(verticalScrollBar()->value() - delta.y());
        return;
    }

    if (m_connectingMode && m_connectSource) {
        QPointF start = m_connectSource->pos() + QPointF(130, m_connectSource->boundingRect().height() / 2);
        QPointF end = mapToScene(event->pos());
        m_connectPreview->setLine(start.x(), start.y(), end.x(), end.y());
        return;
    }

    QGraphicsView::mouseMoveEvent(event);
}

void TaskCanvas::mouseReleaseEvent(QMouseEvent *event) {
    if (m_panning) {
        m_panning = false;
        unsetCursor();
        return;
    }

    if (m_connectingMode && m_connectSource) {
        m_connectingMode = false;
        m_connectPreview->setVisible(false);

        QGraphicsItem *item = itemAt(event->pos());
        auto *target = dynamic_cast<TaskCardItem *>(item);
        if (target && target != m_connectSource) {
            emit relationCreated(m_connectSource->taskId(), target->taskId(), "sequential");
        }
        m_connectSource = nullptr;
        return;
    }

    QGraphicsView::mouseReleaseEvent(event);
}

void TaskCanvas::keyPressEvent(QKeyEvent *event) {
    if (event->key() == Qt::Key_Shift) {
        // Shift 按下时进入连线准备态（实际连线在 Shift+左键 时触发）
    }
    QGraphicsView::keyPressEvent(event);
}

void TaskCanvas::keyReleaseEvent(QKeyEvent *event) {
    QGraphicsView::keyReleaseEvent(event);
}
