# Task Decomposer Agent

Task Decomposer Agent 是一个可扩展的任务拆解型 Agent 系统。它能够将复杂的自然语言目标拆解为清晰、有序、高可执行性的任务树计划，并支持多模型供应商、项目级 Skills、多 sub-agent 协作、联网搜索、多轮对话修订、运行期导出、用户级 API Key 配置，以及精美的**命令行/双模图形化复古终端模拟器**交互。

---

## 核心特性

- **多模型供应商**：内置支持 OpenAI、Claude、DeepSeek 核心模型，以及任何兼容 OpenAI 协议的自定义第三方接口。
- **主从协同（主 Agent + Sub-Agent）架构**：
  - **主 Agent**：负责目标澄清、多方调度、建议合并及最终计划合成。
  - **Sub-Agent**：可从“执行落地”、“风险阻碍”、“用户价值”等多元视角独立分析，对计划进行交叉审查。
- **Skills 规则系统**：支持全局 Skills 规则与项目/Agent 级个性化 Skills 规则，实现特定领域的拆解深度。
- **联网搜索增强**：集成 Tavily Search API 和 DuckDuckGo Instant Answer，支持 24 小时本地高速缓存，自动抓取背景资料注入大模型上下文。
- **运行期持久化与分析**：自动保存会话上下文（conversation）、结构化产物（output/markdown/json）、搜索缓存（cache）及运行分析日志（log）。
- **双模交互式终端**：
  - **CLI 双模控制台**：支持 `Tab` 键零延迟无缝切换 `chat>`（拆解目标）和 `console>`（斜杠控制命令），带平滑的异步动画。
  - **C++ Qt 双栏复古图形客户端**：采用流式响应式双栏布局，自适应窗口缩放及折叠，具备像素级的中英文等宽对齐机制、动态发光活动边框、UFO 飞碟牵引光束 ASCII Mascot 经典逐帧动画，并通过高能管道双向 IPC（JSON）连接 Python 核心。
- **自动环境管理**：入口脚本具有自举能力，会自动检测并创建 `.venv` 虚拟环境、自动补齐缺失依赖，并无感 re-exec 重定向至隔离环境。

---

## 项目结构

```text
.
├── task_decomposer.py              # 统一入口脚本（无参进入 CLI 终端，带 --gui-server 启动 IPC 后端）
├── requirements.txt                # Python 依赖列表
├── .env.example                    # 环境变量/ API Key 模板
├── task_decomposer_app/            # 核心主应用包
│   ├── bootstrap.py                # 自动创建虚拟环境、自适应安装依赖及环境重定向
│   ├── cli.py                      # CLI 参数、双栏交互终端、平滑异步动画渲染与运行编排
│   ├── terminal_input.py           # 跨平台无阻塞 TTY 键盘监听器，支持 Tab 切模及 Windows/POSIX 键值映射
│   ├── gui_backend.py              # C++ GUI 客户端的 Python 桥接引擎，实现标准 IO JSON 管道通信 IPC
│   ├── agent.py                    # 主 Agent、模糊需求澄清、任务拆解与多 Agent 结果融合
│   ├── llm.py                      # 统一 LLM 客户端包装（OpenAI/Claude 协议自适应）
│   ├── config.py                   # 默认模型提供商配置、搜索服务配置及环境参数解析
│   ├── runtime.py                  # 运行期持久化（对话、Markdown 产物、运行日志、搜索缓存、用户配置）
│   ├── project.py                  # 项目配置加载与 Sub-Agent 个性化属性解析
│   ├── skills.py                   # 规则技能（Skill）注册、多层级加载与 Prompt 自动合成
│   ├── search.py                   # Tavily / DuckDuckGo 双搜索引擎自适应切换
│   ├── mascot.py                   # UFO 飞碟牵引光束 ASCII Mascot 经典逐帧动画素材集
│   ├── models.py                   # 强类型数据模型（Provider, Plan, Task, Skill 等）
│   └── utils.py                    # 环境变量安全读取、严格 JSON 容错解析等工具函数
├── gui_client/                     # C++ Qt 图形客户端（Retro 双模终端模拟器）
│   ├── CMakeLists.txt              # CMake 构建配置（兼容 Qt5/Qt6 自动降级自适应）
│   ├── main.cpp                    # 客户端启动入口
│   ├── mainwindow.h                # 主窗口定义及中英文等宽对齐计算头文件
│   └── mainwindow.cpp              # 终端模拟器 UI 绘制、UFO 逐帧动画、QProcess 后端进程双向通信
├── skills/                         # 规则配置目录
│   ├── global/                     # 全局通用规则（Skills）
│   └── project/demo/               # demo 项目特定规则（分发至 main 与各 sub-agent）
│       ├── main/
│       ├── sub-agent1/
│       ├── sub-agent2/
│       └── sub-agent3/
├── project/                        # 运行期数据存放目录（可自定义）
│   ├── config/<project>/<agent>/config.json
│   ├── conversation/<project>/*.jsonl
│   ├── output/<project>/*.md|*.json
│   ├── cache/<project>/search.json
│   ├── log/<project>/runs.jsonl
│   └── users/<user>/config.json
└── scripts/                        # 脚本及开发辅助工具
    ├── smoke_test.py               # 最小系统端到端 E2E 冒烟测试
    └── debug_input.py              # 终端输入及 VT 转义序列诊断工具
```

---

## 架构概览

Task Decomposer Agent 采用前端交互（CLI / GUI）与核心逻辑解耦、单进程管道 IPC 协同的松耦合架构：

```text
  ┌─────────────────────────────────────────────────────────────┐
  │                   用户图形交互界面 (C++ Qt)                  │
  │      - 像素级 CJK 对齐、UFO 飞碟 ASCII Mascot 经典逐帧动画      │
  │      - 响应式双栏布局 (折叠)、Tab 键无缝切换 Chat/Console 模式   │
  └───────────────┬─────────────────────────────▲───────────────┘
                  │ 标准输入 (命令 JSON)          │ 标准输出 (结果 JSON) [IPC]
                  ▼                             │
  ┌─────────────────────────────────────────────┴───────────────┐
  │               Python 桥接引擎 (gui_backend)                 │
  │  - 全局 sys.stdout 重定向至 stderr，防止日志污染 JSON 通信流  │
  └───────────────┬─────────────────────────────────────────────┘
                  ▼ 启动调用
  ┌─────────────────────────────────────────────────────────────┐
  │                 CLI 控制台 / 终端 (cli.py)                  │
  └───────────────┬─────────────────────────────────────────────┘
                  ▼
  ┌─────────────────────────────────────────────────────────────┐
  │             大语言模型 Agent 核心 (agent.py)                │
  │     ├─ clarify：多维模糊需求澄清与追问机制                    │
  │     ├─ search：基于缓存（24h）的 Tavily/DDG 联网检索增强     │
  │     ├─ sub-agents：多重角色（执行、风险、价值）分布式拆解     │
  │     └─ merge / decompose：跨 Agent 异构计划智能合并与输出   │
  └───────────────┬─────────────────────────────────────────────┘
                  ▼ 状态存盘
  ┌─────────────────────────────────────────────────────────────┐
  │                    运行时数据层 (runtime.py)                │
  │     ├─ conversation：多轮修订历史关联上下文                  │
  │     ├─ output：自动导出高可读 Markdown 及 JSON 任务数据     │
  │     ├─ cache：搜索结果序列化缓存                            │
  │     └─ log：分析诊断日志（包含用时、异常诊断、Token 消耗）   │
  └─────────────────────────────────────────────────────────────┘
```

---

## 安装说明

### 环境要求

- **Python**：`3.10` 或更高版本。
- **C++ GUI 构建**（仅在编译图形客户端时需要）：
  - **CMake**：`3.16` 或更高版本。
  - **Qt 库**：`Qt 5.15` 或 `Qt 6.x`（Widgets, Core, Gui 模块）。
  - 支持 **C++17** 标准的编译器（如 MSVC, GCC, Clang 等）。

### 自动安装（推荐）

首次运行主入口脚本时，系统会自动检测 `.venv` 虚拟环境。若不存在，将自动创建、更新 `pip` 并安装 `requirements.txt` 中的依赖，然后重新将自己拉起。

```bash
python task_decomposer.py --help
```

### 手动安装 Python 环境

```bash
# Windows
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt

# Linux / macOS
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

---

## 环境变量配置

复制根目录下的 `.env.example` 并重命名为 `.env`，填入对应模型提供商的 API Key：

```ini
# 默认大模型提供商配置：auto（按已配 Key 自动探测）、openai、claude、deepseek、custom
LLM_PROVIDER=auto

# 模型 API 密钥
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
CUSTOM_API_KEY=your_custom_api_key_here

# 联网搜索配置
SEARCH_PROVIDER=auto
SEARCH_MAX_RESULTS=5
TAVILY_API_KEY=your_tavily_api_key_here
```

---

## C++ Qt 图形客户端编译与运行

### 1. 编译客户端

在安装好 CMake 和 Qt 的环境下，进入 `gui_client` 文件夹并执行构建：

```bash
cd gui_client
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build . --config Release
```

> [!NOTE]
> `CMakeLists.txt` 已内置自适应降级寻找逻辑。程序会优先寻找 Qt6。若未检测到，将自动降级寻找 Qt5 库并调整链接参数。在 Windows MSVC 编译环境下，自动开启了 `/utf-8` 编译选项，彻底避免中文字符集解析乱码。

### 2. 运行客户端

编译完成后，可以直接双击运行生成的 `TaskDecomposerGUI` 可执行程序，或在命令行中运行：

```bash
# Windows
TaskDecomposerGUI.exe

# Linux / macOS
./TaskDecomposerGUI
```

> [!IMPORTANT]
> **智能后端定位机制**：
> - 客户端启动时会自动在**自身所在目录及往上最多五层目录**中探测 Python 入口脚本 `task_decomposer.py`。
> - 如果在上述层级中未能自动匹配（例如您将 exe 移动到了其他位置分发），客户端将自动弹出标准系统对话框，引导您手动选择项目根目录下的 `task_decomposer.py`，并将该路径保存至系统注册表/配置文件中（下次无感加载）。
> - 客户端定位到后端后，会自动探测是否存在 `.venv` 虚拟环境，并使用虚拟环境中的 Python 解释器拉起后端。如果未找到虚拟环境，将退而求其次使用系统全局 `python`，并自动传入 `--gui-server` 参数，开启安全 JSON 通信。
> - 进程级环境变量注入：客户端拉起 Python 子进程时，会自动注入 `PYTHONIOENCODING=utf-8` 与 `PYTHONUTF8=1` 环境变量，确保中文字符在标准 IO 管道传输中万无一失。

---

## 快速开始

### 本地安全演示（免 API 调用）

为了确保系统安装正常，你可以使用 `--local` 本地假数据演示模式。该模式将跳过模型调用和联网，瞬间合成计划：

```bash
python task_decomposer.py "我想写一本关于科幻的小说" --local --skip-clarify --project demo
```

### 使用大模型正式运行

```bash
python task_decomposer.py "我想写一本关于科幻的小说" --project demo --skip-clarify
```

### 预览配置加载（不调用模型与联网）

使用 `--dry-run` 预览本次目标将会分配给哪些 Agent，加载哪些 Skills，配置何种 LLM 参数：

```bash
python task_decomposer.py "我想写一本关于科幻的小说" --project demo --dry-run
```

### 命令行多轮交互式终端

如果不指定具体目标，将进入 CLI 交互终端：

```bash
python task_decomposer.py --project demo
```

---

## 双模交互终端与图形界面设计

无论是 CLI 交互终端还是 Qt 图形客户端，均贯彻了**双模极客设计**：

| 输入模式 | 终端提示符 | 用途与操作 |
| --- | --- | --- |
| **Chat 模式** | `chat> ` | 直接输入你的拆解目标、反馈或修改意见。按 `Enter` 发送给 Agent 进行深度任务拆解。 |
| **Console 模式**| `console>` | 用于输入 `/` 开头的斜杠控制命令，配置或管理当前的运行会话。 |

> [!TIP]
> 无论是 CLI 还是图形客户端，你均可以在输入框中按 **`Tab`** 键随时切换当前输入模式。

### 交互命令集

在 `console>` 提示符下（或在 `chat>` 模式下输入以 `/` 开头的指令），支持以下命令：

| 命令 | 用途 | 示例 |
| --- | --- | --- |
| `/help` 或 `/?` | 显示可用命令说明及 Tab 键切模指南。 | `/help` |
| `/status` | 显示当前加载的项目（project）与对话 ID（conversation）。 | `/status` |
| `/switch <id>` | 切换到指定对话 ID 的上下文。 | `/switch novel_writing` |
| `/new [id]` | 新建一个对话上下文。不加 id 参数时自动生成时间戳 ID。 | `/new my_task_1` |
| `/leave` | 卸载并退出当前对话，保留交互终端（只执行单次拆解）。 | `/leave` |
| `/clear` | 重绘终端，重新呼出 UFO 飞碟牵引光束 ASCII Mascot 经典逐帧欢迎动画。 | `/clear` |
| `/exit` | 安全退出终端或图形客户端。 | `/exit` |

### 图形界面客户端的特色功能

1. **响应式自适应布局**：
   图形界面采用流式布局。在窗口宽度被压缩（小于 720 像素）或高宽比呈纵向狭长状态时，左右双栏会无缝、平滑地折叠转换为上下堆叠布局，完全契合移动端/窄侧边栏的使用场景。
2. **活动窗格发光效果**：
   左右面板会根据当前所处的输入模式，对对应的活动面板进行粉红荧光（`#ffb3ba`）边框高亮。
3. **像素级中英文排版对齐**：
   为了防止宽字符（CJK 中文字符、标点）在单色/等宽终端排版时与窄字符（英文、半角符号）混排发生换行错位，客户端在 C++ 底层实现了高精度的 Visual Width 计算（CJK 宽字符计为 2，半角计为 1），实现了精细的居中对齐、右对齐和自动视觉折行（wrap）。
4. **Mascot 动画的精准同步**：
   经典 CLI 终端下的 UFO 飞碟牵引光束吸人 ASCII Mascot 动画被完美移植到客户端。C++ 定时器以 220ms 间隔驱动重绘，与原版 CLI 拥有等同的丝滑极客质感。

---

## 项目与规则 (Skills) 系统

### 目录映射

项目级 Skills 与 Agent 的绑定关系严格基于目录树的命名：

```text
skills/project/<project-name>/
├── main/<skill-name>/SKILL.md             # 注入主 Agent 的专用规则
├── sub-agent1/<skill-name>/SKILL.md       # 仅对名为 sub-agent1 的 Agent 生效
└── sub-agent2/<skill-name>/SKILL.md       # 仅对名为 sub-agent2 的 Agent 生效
```

主 Agent 的 Skill 只会在主决策阶段生效，Sub-Agent 独享的 Skill 则会在它们独立分析时发挥作用。

### 初始化项目与 Skills 模板

如果你需要为一个新的定制任务创建规则结构，可以使用以下命令快速生成结构树：

```bash
python task_decomposer.py --init-project my-novel-agent
```

这将会在 `skills/project/my-novel-agent` 中初始化标准的 main 与各 sub-agent 模板结构。

### 列出加载技能

```bash
# 列出全局所有 Skills
python task_decomposer.py --list-skills

# 列出指定项目已挂载的所有层级 Skills
python task_decomposer.py --project demo --list-project-skills
```

---

## 运行期配置与定制

### 运行期目录

运行期数据（包含配置与日志）默认保存在 `project/` 下，若要指定其他位置，可传递 `--runtime-dir <path>`。

你可以快速为项目初始化运行期默认模板（如 Agent 的模型参数、API Key 的环境变量指向等）：

```bash
python task_decomposer.py --init-runtime --project my-novel-agent
```

### 1. 配置 Agent 大模型属性

在运行期目录下，例如 `project/config/demo/sub-agent2/config.json` 中配置 sub-agent 的大模型、角色：

```json
{
  "name": "sub-agent2",
  "provider": "claude",
  "model": "claude-3-5-haiku-latest",
  "api_key_env": "ANTHROPIC_API_KEY",
  "role": "风险分析师。你的主要目标是评估计划在实际执行中的风险、前置依赖、隐性技术债和验证验收标准。"
}
```

### 2. 配置 DeepSeek / OpenAI-compatible 属性

```json
{
  "name": "main",
  "provider": "deepseek",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com",
  "api_key_env": "DEEPSEEK_API_KEY",
  "role": "核心任务拆解器。负责提炼各 Sub-Agent 的专业反馈，输出终版结构化执行树。"
}
```

> [!TIP]
> - 在配置项中将 `"enabled": false` 即可在运行时禁用该 Sub-Agent。
> - `api_key_envs` 支持传入一组环境变量名数组作为回退链。

### 用户级配置隔离

用户级别的 API Key 优先于环境变量读取，文件位置保存在：

```text
project/users/<user_name>/config.json
```

可通过以下指令启动命令行快速配置向导：

```bash
python task_decomposer.py --setup-user --user my_name
```

---

## 联网搜索与搜索缓存

### 开启搜索增强

```bash
python task_decomposer.py "研究一下最新 DeepSeek 架构" --project demo --search
```

### 覆盖默认搜索关键词

默认使用任务目标去联网。您也可以显式指定搜索词：

```bash
python task_decomposer.py "目标" --project demo --search --search-query "DeepSeek-V3 paper architectural highlights"
```

### 搜索结果高速缓存

搜索缓存自动写入 `project/cache/<project-name>/search.json`，缓存有效生命期为 **24 小时**。

```bash
# 查看当前缓存的所有项目和过期状态
python task_decomposer.py --project demo --cache-list

# 立即清空指定项目的缓存
python task_decomposer.py --project demo --cache-clear
```

---

## 系统测试

运行最小核心及端到端（E2E）冒烟测试：

```bash
python scripts/smoke_test.py
```

该脚本会启动一个临时的沙箱运行时目录，自动测试包括项目校验、dry-run、本地演示生成、会话存盘历史、运行日志及搜索缓存读写的完整链路。

---

## 许可证

本项目采用 [GNU Affero General Public License v3.0 or later](LICENSE) (`AGPL-3.0-or-later`) 开源许可证。

选择 AGPL 是由于其强 Copyleft 约束：任何分发本项目修改版或派生作品的主体，必须以同等自由的许可证公开源码。对于通过网络运行本项目的修改版（如 SaaS 云服务），亦须向远程用户公开对应版本的修改源码，防止把代码部署成封闭服务而不履行开源反馈义务。

### 简要释义：
- **自由共享**：您可以自由学习、复制、修改、分发与进行商业化运作。
- **开源传染**：对本项目代码做出的任何修改或衍生作品，分发时必须继续以 AGPL 协议开源。
- **云端开源**：如果您通过网络提供修改版 Task Decomposer 的在线服务，也必须无偿向与服务交互的用户公开修改版源码。
- **聚合兼容**：与本项目同册并列分发且保持独立的外部组件，不会被本许可证自动覆盖。

许可证的最终法律解释请严格以项目根目录下的 `LICENSE` 英文正式文本为准。
