# Task Decomposer Agent

Task Decomposer Agent 是一个可扩展的任务拆解型 Agent。它把自然语言目标拆成清晰、有序、可执行的计划，并支持多模型供应商、项目级 Skills、多 sub-agent 协作、联网搜索、多轮对话修订、运行期导出和用户级 API Key 配置。

## 特性

- 多模型供应商：OpenAI、Claude、DeepSeek，以及其他 OpenAI-compatible 接口。
- 主 Agent + sub-agent 架构：主 Agent 负责澄清、调度、合并，sub-agent 从执行、风险、用户价值等角度独立分析。
- Skills 系统：支持全局 Skills 和项目内按 agent 分配的 Skills。
- 联网搜索：支持 Tavily Search API 和 DuckDuckGo Instant Answer，并带 24 小时本地缓存。
- 运行期持久化：保存 conversation、output、cache、log 和用户配置。
- 自动环境管理：入口脚本会创建 `.venv`、安装缺失依赖，并 re-exec 到虚拟环境。
- 交互式终端：无目标参数时可进入 chat/console 双模式交互。

## 项目结构

```text
.
├── task_decomposer.py              # 入口脚本，调用 bootstrap 后进入 CLI
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── task_decomposer_app/            # 主应用包
│   ├── bootstrap.py                # 自动创建虚拟环境、安装依赖、re-exec
│   ├── cli.py                      # CLI 参数、交互式终端、运行编排
│   ├── agent.py                    # 主 Agent、澄清、拆解、sub-agent 调度和合并
│   ├── llm.py                      # LLM 客户端，封装 OpenAI-compatible 和 Claude
│   ├── config.py                   # 模型供应商、搜索供应商和默认配置解析
│   ├── runtime.py                  # 运行期目录、对话、导出、日志、缓存、用户配置
│   ├── project.py                  # 项目级 Skills 结构解析
│   ├── skills.py                   # Skill 注册、加载和 prompt 格式化
│   ├── search.py                   # Tavily / DuckDuckGo 搜索实现
│   ├── mascot.py                   # 交互式终端欢迎界面和动画素材
│   ├── models.py                   # Provider、Plan、Task、Skill 等数据模型
│   └── utils.py                    # 环境变量读取、JSON 解析等工具函数
├── skills/
│   ├── global/                     # 全局 Skills
│   └── project/demo/               # demo 项目级 Skills
│       ├── main/
│       ├── sub-agent1/
│       ├── sub-agent2/
│       └── sub-agent3/
├── project/                        # 默认运行期数据目录
│   ├── config/<project>/<agent>/config.json
│   ├── conversation/<project>/*.jsonl
│   ├── output/<project>/*.md|*.json
│   ├── cache/<project>/search.json
│   ├── log/<project>/runs.jsonl
│   └── users/<user>/config.json
└── scripts/
    └── smoke_test.py               # 最小端到端 smoke test
```

## 架构概览

```text
用户目标 / 反馈
    │
    ▼
CLI
    ├─ 加载 .env、项目配置、用户配置、Skills
    ├─ 解析模型供应商、搜索供应商和 sub-agent 策略
    └─ 管理交互式终端、dry-run、缓存、导出、日志
    │
    ▼
TaskDecomposerAgent
    ├─ clarify：判断目标是否需要补充信息
    ├─ search：按需获取联网资料并使用运行期缓存
    ├─ sub-agents：让多个角色独立拆解目标
    └─ merge / decompose：合并最终计划或直接拆解
    │
    ▼
Runtime
    ├─ conversation：多轮修订上下文
    ├─ output：Markdown / JSON 计划产物
    ├─ cache：搜索缓存
    └─ log：成功或失败运行记录
```

## 安装

需要 Python 3.10 或更高版本。首次运行入口脚本会自动准备虚拟环境和依赖。

```bash
python task_decomposer.py --help
```

也可以手动安装：

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Linux / macOS：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 环境变量

复制 `.env.example` 为 `.env`，然后填入至少一个模型供应商的 API Key。

```text
LLM_PROVIDER=auto

OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here
DEEPSEEK_API_KEY=your_deepseek_api_key_here
CUSTOM_API_KEY=your_custom_api_key_here

SEARCH_PROVIDER=auto
SEARCH_MAX_RESULTS=5
TAVILY_API_KEY=your_tavily_api_key_here
```

`LLM_PROVIDER=auto` 会按已配置的 Key 自动选择供应商。没有检测到模型 API Key 时，可使用 `--local` 运行本地演示模式。

## 支持的模型供应商

| 供应商 | 别名 | 默认模型 | API Key |
| --- | --- | --- | --- |
| OpenAI | `openai`, `chatgpt`, `gpt` | `gpt-4.1-mini` | `OPENAI_API_KEY`, `CHATGPT_API_KEY`, `LLM_API_KEY` |
| Claude | `claude`, `anthropic` | `claude-3-5-haiku-latest` | `ANTHROPIC_API_KEY`, `CLAUDE_API_KEY`, `LLM_API_KEY` |
| DeepSeek | `deepseek` | `deepseek-chat` | `DEEPSEEK_API_KEY`, `LLM_API_KEY` |
| Custom | `custom`, `openai-compatible` | `gpt-4.1-mini` | `CUSTOM_API_KEY`, `OPENAI_COMPATIBLE_API_KEY`, `LLM_API_KEY` |

## 快速开始

本地演示，不调用模型 API：

```bash
python task_decomposer.py "我想做一个任务拆解 Agent" --local --skip-clarify --project demo
```

使用 demo 项目的 Skills 和运行期 agent 配置：

```bash
python task_decomposer.py "我想做一个任务拆解 Agent" --project demo --skip-clarify
```

预览本次会加载的配置，不调用模型、不联网、不写入运行期产物：

```bash
python task_decomposer.py "我想做一个任务拆解 Agent" --project demo --dry-run
```

进入交互式终端：

```bash
python task_decomposer.py --project demo
```

## 交互式终端

交互式终端包含两种输入模式，可按 `Tab` 切换：

| 模式 | 用途 |
| --- | --- |
| `chat>` | 输入目标或反馈，让 Agent 拆解任务 |
| `console>` | 输入 slash 命令管理会话 |

常用命令：

| 命令 | 说明 |
| --- | --- |
| `/help` | 显示帮助 |
| `/status` | 查看当前 project 和 conversation |
| `/switch <id>` | 切换到指定对话 |
| `/new [id]` | 新建对话，不传 id 时自动生成 |
| `/clear` | 重新显示欢迎面板 |
| `/leave` | 离开当前对话但保留终端 |
| `/exit` | 退出交互式终端 |

## 项目和 Skills

项目 Skills 默认位于：

```text
skills/project/<project-name>/
├── main/<skill-name>/SKILL.md
├── sub-agent1/<skill-name>/SKILL.md
└── sub-agent2/<skill-name>/SKILL.md
```

程序会扫描 `main` 和所有 `sub-agent*` 目录。`main` Skills 注入主 Agent，sub-agent 目录下的 Skills 只注入对应 sub-agent。

初始化项目 Skills 模板：

```bash
python task_decomposer.py --init-project my-agent-project
```

列出全局 Skills：

```bash
python task_decomposer.py --list-skills
```

列出项目 Skills：

```bash
python task_decomposer.py --project demo --list-project-skills
```

## 运行期配置

运行期数据默认保存在 `project/`。你可以通过 `--runtime-dir` 改变位置。

初始化运行期模板：

```bash
python task_decomposer.py --init-runtime --project my-agent-project
```

典型 agent 配置：

```json
{
  "name": "sub-agent2",
  "provider": "claude",
  "model": "claude-3-5-haiku-latest",
  "api_key_env": "ANTHROPIC_API_KEY",
  "role": "风险审查者，关注遗漏、依赖、风险和验收标准。"
}
```

DeepSeek / OpenAI-compatible 配置：

```json
{
  "name": "main",
  "provider": "deepseek",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com",
  "api_key_env": "DEEPSEEK_API_KEY",
  "role": "主 Agent，负责综合 sub-agent 建议并输出最终任务拆解。"
}
```

`enabled=false` 可禁用某个 sub-agent。`api_key_envs` 可配置多个环境变量作为回退。

## 用户级配置

用户级配置保存到：

```text
project/users/<user>/config.json
```

创建或更新用户配置：

```bash
python task_decomposer.py --setup-user --user <user>
```

默认用户名来自 `TASK_DECOMPOSER_USER`、`USERNAME` 或 `USER`。

## Sub-Agent 策略

运行所有 sub-agent：

```bash
python task_decomposer.py "目标" --project demo --sub-agent-mode all
```

只运行风险审查类 sub-agent：

```bash
python task_decomposer.py "目标" --project demo --sub-agent-mode risk-only
```

按目标关键词自动选择：

```bash
python task_decomposer.py "目标" --project demo --sub-agent-mode auto
```

临时追加 sub-agent：

```bash
python task_decomposer.py "目标" --sub-agent "reviewer:从风险和验收标准角度审查计划"
```

## 联网搜索和缓存

启用搜索：

```bash
python task_decomposer.py "我想做一个 AI Agent 项目" --project demo --search
```

指定搜索词：

```bash
python task_decomposer.py "目标" --project demo --search --search-query "AI Agent architecture"
```

搜索供应商：

| 值 | 说明 |
| --- | --- |
| `auto` | 有 `TAVILY_API_KEY` 时使用 Tavily，否则使用 DuckDuckGo |
| `tavily` | 使用 Tavily Search API |
| `duckduckgo` | 使用 DuckDuckGo Instant Answer，无需 API Key |

搜索缓存写入：

```text
project/cache/<project>/search.json
```

缓存有效期为 24 小时。查看或清空缓存：

```bash
python task_decomposer.py --project demo --cache-list
python task_decomposer.py --project demo --cache-clear
```

## 多轮修订和导出

指定 conversation 后，每轮目标和计划都会被写入对话历史，并在后续运行中作为上下文使用。

```bash
python task_decomposer.py "我想做一个任务拆解 Agent" --project demo --conversation default
python task_decomposer.py --project demo --conversation default --feedback "增加验收标准和时间安排"
```

每次成功运行会写入：

```text
project/output/<project>/<run_id>.md
project/output/<project>/<run_id>.json
project/output/<project>/index.json
project/log/<project>/runs.jsonl
```

失败运行会记录到 `runs.jsonl`，包含失败阶段、错误类型、错误信息和耗时。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `python task_decomposer.py --help` | 查看完整 CLI 参数 |
| `python task_decomposer.py --project demo --validate-project` | 校验项目 Skills、agent 配置和运行期目录 |
| `python task_decomposer.py --project demo --dry-run "目标"` | 预览配置 |
| `python task_decomposer.py --project demo --list-project-skills` | 列出项目 Skills |
| `python task_decomposer.py --project demo --cache-list` | 查看搜索缓存 |
| `python task_decomposer.py --setup-user --user <user>` | 配置用户级 API Key |

## 测试

运行 smoke test：

```bash
python scripts/smoke_test.py
```

该脚本会使用临时运行目录验证项目校验、dry-run、本地 demo 导出、日志和缓存管理。

## 许可证

本项目采用 [GNU Affero General Public License v3.0 or later](LICENSE)（`AGPL-3.0-or-later`）。

选择 AGPL 的原因是它提供强 copyleft 约束：任何人如果分发本项目的修改版，或基于本项目形成派生作品，相关作品必须继续以同等自由的许可证开放对应源码。对于通过网络提供服务的修改版，AGPL 也要求向远程用户提供对应源码，从而避免只把代码部署成服务却不公开修改内容的情况。

简要理解：

- 可以自由使用、学习、复制、修改、分发和商用。
- 修改本项目或基于本项目形成派生作品时，必须继续开放对应源码。
- 通过网络运行修改版并让用户交互时，也需要向这些用户提供对应源码。
- 与本项目只是并列分发、且彼此独立的组件，通常不因为简单聚合而自动变成 AGPL。

许可证解释以 `LICENSE` 中的英文正式文本为准。
