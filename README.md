# Task Decomposer Agent

Task Decomposer Agent 是一个现代化、用户-项目驱动的高性能任务拆解型 Agent 系统。它能将复杂的自然语言目标拆解为清晰、有序、高可执行性的任务树计划，并支持多模型供应商、API Key 轮询密钥池、多开sub-Agent 协同、联网搜索（Tavily / DuckDuckGo）、多轮对话修订、运行期导出、自包含免密沙箱，以及精美的**双模命令行/双模图形化复古终端模拟器**交互。

---

## 核心特性

- **多模型供应商与密钥池**：内置支持 OpenAI、Claude、DeepSeek 核心模型及任何兼容 OpenAI 协议的自定义接口。支持配置 **API Key 密钥池数组**，在并发请求时通过跨进程持久化 Round-Robin 进行轮询分配，有效避免 Rate Limit 频率限制。
- **主从协同（主 Agent + Sub-Agent）架构**：
  - **主 Agent**：负责目标澄清、多方调度、建议合并及最终计划合成。
  - **Sub-Agent**：从“执行路径”、“风险审查”、“用户价值”等独立视角参与分析与交叉评审。
- **项目级自治 Skills**：废弃全局 Skills 概念。所有技能 Prompt 严格自治、物理收拢在对应的项目和 Agent 目录下，实现零全局污染。
- **免密演示沙箱 (`demo`)**：内置开箱即用的安全演示沙箱。演示用户支持免密运行本地模拟引擎，且启用搜索时会自动路由至 **DuckDuckGo**（无需 API Key 即可进行真公网检索）。沙箱具备“动态数据瞬态擦除”与“静态修改 pristine 样板还原”机制，确保磁盘零垃圾残留，系统永远如初。
- **去环境变量与目录隔离**：废弃全局环境文件，转为 **“配置（Code/Config）”与“状态（Data/Runtime）”完全物理分离的目录驱动架构**。
- **双模交互式终端**：
  - **CLI 双模控制台**：支持 `Tab` 键无缝切换 `chat>`（目标沟通）和 `console>`（斜杠控制命令），伴随精美平滑的异步 TTY ASCII mascot 动静态视觉绘制。
  - **C++ Qt 双栏复古图形客户端**：原生 HTML/CSS 流式富文本卡片列表排版，支持发光活动边框、ASCII Mascot 经典逐帧动画，通过双向 IPC（JSON）管道异步连接 Python 核心。

---

## 项目物理结构

系统架构设计为极其精简、代码态（只读/静态配置）与数据态（动态日志/缓存）100% 分离的两个物理根目录：

```text
.
├── task_decomposer.py              # 统一入口脚本（CLI 终端，带 --gui-server 启动 IPC 后端）
├── requirements.txt                # Python 依赖列表
├── task_decomposer_app/            # 核心主应用包
│   ├── bootstrap.py                # 自动虚拟环境检测、自适应依赖安装与环境重定向
│   ├── core_engine.py              # 核心业务层。承载完整的四重项目校验、LLM 密钥轮询与核心拆解链路
│   ├── cli_renderer.py             # CLI 终端渲染层。负责中英文等宽排版、ANSI mascot 视觉绘制与控制台面板绘制
│   ├── cli.py                      # CLI 交互层。双模输入状态机、交互命令解析与 Session 控制
│   ├── terminal_input.py           # 跨平台无阻塞 TTY 键盘监听器，支持 Tab 键值切模
│   ├── gui_backend.py              # 协议适配层。GUI 后端的轻量级 JSON IPC 管道接口，支持 stderr 实时泵送
│   ├── agent.py                    # 主 Agent、模糊需求澄清、任务拆解与多 Agent 结果融合
│   ├── llm.py                      # 统一 LLM 客户端包装（OpenAI/Claude 协议自适应）
│   ├── config.py                   # 模型供应商定义与配置项映射
│   ├── runtime.py                  # 运行期数据持久化（会话、Markdown 产物、运行日志、并发安全搜索缓存）
│   ├── project.py                  # 项目配置加载与 Agent 级技能结构树解析
│   ├── skills.py                   # 项目技能（Skill）注册与 Prompt 自动合成
│   ├── search.py                   # Tavily / DuckDuckGo 双搜索引擎自适应切换
│   ├── models.py                   # 强类型数据模型（Provider, Plan, Task, Skill 等）
│   └── utils.py                    # 严格 JSON 容错解析等工具函数
├── gui_client/                     # C++ Qt 图形客户端（Retro 双模终端模拟器）
│   ├── CMakeLists.txt              # CMake 构建配置（基于 Qt6 构建）
│   ├── main.cpp                    # 客户端启动入口
│   └── mainwindow.cpp              # 富文本渲染、本地 Mascot 帧动画、QProcess 异步 JSON 通信
├── config/                         # 静态配置与定义目录（建议提交 Git 仓库）
│   └── user/
│         └── demo/                 # 内置 demo 沙箱用户
│               ├── config.json     # 全局无密配置文件
│               └── project/
│                     ├── demo/     # 内置只读演示项目模板 (main 与各 sub-agent 技能 Prompt)
│                     └── demo_pristine/ # 只读原始备份样板 (退出时自动物理复制还原 demo 沙箱)
└── runtime/                        # 运行期状态目录（除了 demo 占位符外，已在 .gitignore 中完全忽略）
      └── user/
            └── [username]/         # 每个用户的状态数据完全物理隔离，极易整体打包分发
                  └── project/
                        └── [projectname]/
                              ├── cache/        # 联网搜索缓存（search.json，多进程文件锁原子安全读写）
                              ├── conversation/ # 多轮会话历史 .jsonl 文件
                              ├── log/          # 运行成功与失败日志 runs.jsonl
                              └── output/       # 导出的任务计划 .json 与 .md 报告
```

---

## 快速开始

### 自动安装（推荐）

首次运行主入口脚本时，系统会自动检测 `.venv` 虚拟环境。若不存在，将自动创建虚拟环境、更新 `pip` 并安装 `requirements.txt` 中的依赖，然后重新将自己拉起。

```bash
python task_decomposer.py --help
```

---

## 免密特权沙箱与瞬态隔离机制 (`demo`)

系统内置了极其健壮的 `demo` 沙箱机制，面向“无密试玩”场景：

1. **唯一免密特权**：`demo` 用户是系统唯一允许不配置任何 API Key 即可启动的用户。在调用模型时会自动重定向到本地模拟引擎（Local Mock Engine），无需配置密钥或联网扣费。
2. **免密公网检索**：当演示用户开启 `--search` 时，系统会自动将检索端强行路由至 **DuckDuckGo**。因其完全不需要 API Key，可在零配密的前提下演示公网检索。
3. **动态数据瞬态擦除**：在 `/leave`、`/switch` 或程序退出时，`runtime/user/demo/project/demo/` 下产生的所有动态缓存、对话历史、日志与 output 被**彻底无痕清空擦除**。
4. **静态只读还原**：如果演示用户对沙箱项目中的静态 Prompt （如 `planning/SKILL.md`）进行了修改，退出时系统会自动通过只读备份目录 `demo_pristine/` 进行**物理覆盖重置**，确保下一次启动永远洁净如初。
5. **临时项目销毁**：演示用户在沙箱中创建的任何其他自定义临时项目目录，在程序退出或切换时，将被**物理彻底递归销毁**，不留下任何垃圾。

---

## 用户级配置与向导

普通用户强制校验 API 密钥，配置与密钥池保存在：
`config/user/[username]/config.json`

### 1. 新用户温和引导流 (Smooth Onboarding Flow)

当您传入一个系统中尚不存在的新用户时（例如 `python task_decomposer.py --user new_developer`），系统不会报错崩溃，而是提供温和的交互式询问：
> `[提示] 未检测到用户 'new_developer'。是否为您自动初始化一套属于该用户的配置与 demo 项目样板脚手架？(y/n):`

选择 `y`，系统会自动将 `demo` 用户脚手架克隆为该用户的独享工作区，并自动拉起配置向导。

### 2. 步骤向导式配置命令 (`--setup-user`)

使用以下指令启动分步向导（Wizard），自动为新用户或已有用户配置密钥池：

```bash
python task_decomposer.py --setup-user --user my_name
```

向导将引导您分步：
- 选择默认的模型供应商及录入 **API Key 数组**（支持逗号分隔录入多个密钥，初始化为密钥池，以进行并发 Round-Robin 轮询）。
- 配置检索服务提供商及密钥池。
- 安全写入 JSON 文件，完全规避手动编辑 JSON 产生语法错误。

---

## 常用运行命令

### 1. 交互式多轮对话终端 (无参默认进入)

```bash
# 默认使用 demo 演示沙箱用户与 demo 项目
python task_decomposer.py

# 使用您自己配置的用户与定制项目
python task_decomposer.py --user alice --project my-novel-agent
```

### 2. 单次命令行执行拆解

```bash
# 本地免密模拟快速预览
python task_decomposer.py "我想写一本关于科幻的小说" --user demo --project demo --local --skip-clarify

# 正式大模型拆解
python task_decomposer.py "我要写一篇关于 Agent 架构的论文" --user alice --project paper-writer
```

### 3. 项目深层校验 (`--validate-project`)

对用户的密钥配置、定义目录、技能多开子目录及联网搜索模块执行全方位的四重工业级校验：

```bash
python task_decomposer.py --user demo --project demo --validate-project
```

### 4. 预览运行 (Dry Run)

预览本次目标将会分配给哪些 Agent，加载哪些 Skills，配置何种 LLM 密钥回退与检索参数，不调用模型与联网：

```bash
python task_decomposer.py "我要开发一个小程序" --user demo --project demo --dry-run
```

---

## 双模交互终端指令

在 `console>` 提示符下（或在 `chat>` 模式下输入以 `/` 开头的指令），支持以下运行期命令：

| 命令 | 用途 | 示例 |
| --- | --- | --- |
| `/help` 或 `/?` | 显示可用命令说明及 Tab 键切模（切换 chat/console 模式）指南。 | `/help` |
| `/status` | 显示当前加载的用户、项目（project）与对话 ID（conversation）。 | `/status` |
| `/switch <id>` | 切换到指定对话 ID 的运行期上下文。 | `/switch novel_writing` |
| `/new [id]` | 新建一个对话上下文。不加 id 参数时自动生成时间戳 ID。 | `/new my_task_1` |
| `/leave` | 卸载并退出当前对话，保留交互终端。 | `/leave` |
| `/clear` | 重绘终端，重新呼出 UFO 经典逐帧 Mascot 欢迎动画。 | `/clear` |
| `/exit` | 安全退出终端或图形客户端。 | `/exit` |

---

## 许可证

本项目采用 [GNU Affero General Public License v3.0 or later](LICENSE) (`AGPL-3.0-or-later`) 开源许可证。

### 简要释义：
- **自由共享**：您可以自由学习、复制、修改、分发与进行商业化运作。
- **开源传染**：对本项目代码做出的任何修改或衍生作品，分发时必须继续以 AGPL 协议开源。
- **云端开源**：如果您通过网络提供修改版 Task Decomposer 的在线服务（如 SaaS），也必须无偿向与服务交互的远程用户公开修改版源码。
