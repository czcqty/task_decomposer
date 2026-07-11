# Task Decomposer Agent

Task Decomposer Agent 是一个任务拆解型 Agent 系统。它能将自然语言目标拆解为可执行的任务计划，并以可视化画布的形式呈现——支持拖拽卡片、关系连线、主题切换，以及多模型供应商、API Key 轮询密钥池、多 Sub-Agent 协同、联网搜索和多轮对话修订。

---

## 核心特性

- **可视化任务画布**：任务以可拖拽的卡片形式呈现在画布上，支持平移缩放、自动布局。点击卡片打开编辑面板，可修改标题、状态、行动和产出。
- **四种任务关系**：
  - **顺序**（实线箭头）：A 完成后执行 B
  - **并行**（虚线双向箭头）：A 和 B 可同时进行
  - **阻塞**（红色 T 形端点）：A 阻塞 B 的开始
  - **嵌套**（父子包含）：B 是 A 的子任务
- **双主题系统**：默认现代风格（浅色，类 Notion/Linear），可切换为复古深色霓虹风格。一键切换，持久化保存。
- **多模型供应商与密钥池**：支持 OpenAI、Claude、DeepSeek 及任何 OpenAI 兼容接口。API Key 密钥池支持 Round-Robin 轮询分配。
- **主从协同架构**：主 Agent 负责目标澄清与计划合成，Sub-Agent 从执行、风险、用户价值等独立视角参与分析。
- **联网搜索**：支持 Tavily / DuckDuckGo 搜索引擎，将搜索结果注入任务拆解上下文。
- **项目级 Skills**：每个项目和 Agent 可配置独立的技能 Prompt，实现零全局污染。

---

## 项目结构

```text
.
├── task_decomposer.py              # 入口脚本（--gui-server 启动 IPC 后端）
├── task_decomposer_app/            # 核心应用包
│   ├── core_engine.py              # 核心拆解链路
│   ├── gui_backend.py              # GUI IPC 后端（JSON over stdin/stdout）
│   ├── agent.py                    # 主 Agent 与 Sub-Agent 拆解逻辑
│   ├── llm.py                      # LLM 客户端（OpenAI/Claude 协议自适应）
│   ├── models.py                   # 数据模型（Plan, Task, TaskRelation 等）
│   ├── runtime.py                  # 运行期持久化（会话、导出、搜索缓存）
│   ├── cli.py                      # 启动辅助函数（用户配置、密码校验）
│   └── ...
├── gui_client/                     # C++ Qt 图形客户端
│   ├── CMakeLists.txt              # CMake 构建配置（Qt6）
│   ├── main.cpp                    # 入口
│   ├── mainwindow.h/.cpp           # 主窗口（画布 + 输入栏 + 主题切换）
│   ├── taskcanvas.h/.cpp           # 任务可视化画布（QGraphicsScene）
│   ├── taskcarditem.h/.cpp         # 可拖拽任务卡片
│   ├── relationshipline.h/.cpp     # 关系连线
│   ├── taskdetailpanel.h/.cpp      # 任务编辑侧边面板
│   ├── configdialog.h/.cpp         # 配置对话框
│   └── theme.h/.cpp                # 主题系统（现代 + 复古）
├── config/                         # 静态配置目录
│   └── user/demo/                  # 内置 demo 用户
└── runtime/                        # 运行期状态（.gitignore 忽略）
```

---

## 快速开始

### 安装

首次运行时自动创建虚拟环境并安装依赖：

```bash
python task_decomposer.py --help
```

### 启动 GUI

1. 用 CMake 构建 `gui_client/` 目录（需要 Qt6）
2. 运行编译产物 `TaskDecomposerGUI.exe`
3. 在输入框输入目标，点击「分解」或按 Enter

### 命令行模式（GUI 后端）

```bash
# 启动 IPC 后端供 GUI 客户端调用
python task_decomposer.py --gui-server

# 配置用户 API Key
python task_decomposer.py --setup-user --user my_name
```

---

## GUI 交互

| 操作 | 说明 |
|------|------|
| 输入目标 + Enter | 发送分解请求 |
| 点击卡片 | 打开右侧编辑面板 |
| 拖拽卡片 | 移动任务位置 |
| Shift + 拖拽 | 在两个任务间创建关系 |
| Ctrl + 滚轮 | 缩放画布 |
| 中键拖拽 | 平移画布 |
| 底部「🌙 复古」按钮 | 切换主题 |

---

## 数据模型

### Task（任务）

```json
{
  "task_id": "task_1",
  "title": "任务标题",
  "action": "具体行动",
  "output": "预期产出",
  "status": "pending"
}
```

状态值：`pending` | `in_progress` | `done` | `blocked`

### Relation（关系）

```json
{
  "source_id": "task_1",
  "target_id": "task_2",
  "relation_type": "sequential"
}
```

类型值：`sequential` | `parallel` | `blocking` | `nesting`

---

## 许可证

[AGPL-3.0-or-later](LICENSE)
