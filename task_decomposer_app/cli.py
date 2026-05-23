import argparse
import getpass
import json
import os
import shutil
import sys
import threading
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from task_decomposer_app.agent import TaskDecomposerAgent
from task_decomposer_app.config import PROVIDER_DEFAULTS, normalize_provider, resolve_provider, resolve_search_config
from task_decomposer_app.llm import LLMClient
from task_decomposer_app.cli_renderer import render_mascot_frame
from task_decomposer_app import core_engine
from task_decomposer_app.models import SubAgentSpec
from task_decomposer_app.project import ProjectConfig, ProjectSubAgentConfig, load_project_config, project_root_for_create
from task_decomposer_app.runtime import (
    append_conversation,
    append_failure_log,
    append_run_log,
    clear_cache,
    elapsed_since,
    ensure_project_runtime_dirs,
    ensure_runtime_template,
    export_plan,
    is_cache_item_expired,
    list_cache_entries,
    load_agent_runtime_config,
    load_cached_search_results,
    load_conversation_context,
    load_runtime_project,
    load_user_runtime_config,
    resolve_runtime_provider,
    runtime_timestamp,
    save_user_runtime_config,
    save_cached_search_results,
    start_timer,
    UserRuntimeConfig,
)
from task_decomposer_app.search import SearchService
from task_decomposer_app.skills import SkillRegistry
from task_decomposer_app.terminal_input import TerminalInputConfig, read_mode_input, read_text_input, _vt_supported

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional convenience dependency
    load_dotenv = None


ANSI_RESET = "\033[0m"
ANSI_CLEAR_TO_END = "\033[K"
ANSI_CLEAR_DOWN = "\033[J"
CONSOLE_COLOR = "\033[90m"
CHAT_COLOR = "\033[97m"
WORKING_COLOR = "\033[33m"
ACCENT_COLOR = "\033[38;5;217m"
BORDER_COLOR = ACCENT_COLOR
MUTED_COLOR = "\033[38;5;245m"
WELCOME_ANIMATION_INTERVAL = 0.22
WELCOME_ANIMATION_STATE: dict[str, object] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="任务拆解型 Agent（Task Decomposer）")
    parser.add_argument("goal", nargs="*", help="需要拆解的目标，例如：我想写一本小说")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "auto"), help="无项目运行配置时使用的模型供应商")
    parser.add_argument("--model", help="覆盖默认模型名称")
    parser.add_argument("--base-url", help="OpenAI 兼容接口的 Base URL")
    parser.add_argument("--skip-clarify", action="store_true", help="跳过模糊需求澄清")
    parser.add_argument("--local", action="store_true", help="强制使用本地演示模式，不调用模型 API")
    parser.add_argument("--user", default=os.getenv("TASK_DECOMPOSER_USER") or os.getenv("USERNAME") or os.getenv("USER"), help="用户级配置名称，默认使用当前系统用户")
    parser.add_argument("--setup-user", action="store_true", help="创建或更新用户级 API Key 配置后退出")

    parser.add_argument("--global-skill", action="append", default=[], help="加载全局 Skill，可重复使用，也可用逗号分隔")
    parser.add_argument("--config-dir", dest="config_dir", default="config", help="配置与定义根目录")
    parser.add_argument("--skills-dir", dest="config_dir", help=argparse.SUPPRESS)

    parser.add_argument("--project", default="demo", help="项目名，默认解析为 config/user/<user>/project/<项目名>")
    parser.add_argument("--project-dir", default=None, help="项目配置目录路径；通常建议使用 --project")
    parser.add_argument("--init-project", help="创建项目配置与技能模板。")
    parser.add_argument("--list-project-skills", action="store_true", help="列出项目 main/sub-agent 技能后退出")
    parser.add_argument("--sub-agent", action="append", default=[], help="临时追加 sub-agent，格式：name:role")
    parser.add_argument(
        "--sub-agent-mode",
        choices=["all", "risk-only", "auto"],
        default=os.getenv("SUB_AGENT_MODE", "all"),
        help="sub-agent 运行策略：all、risk-only、auto",
    )

    parser.add_argument("--runtime-dir", default=os.getenv("RUNTIME_DIR", "runtime"), help="运行态目录，保存 conversation、cache、log、output")
    parser.add_argument("--init-runtime", action="store_true", help="初始化运行态目录模板后退出")
    parser.add_argument("--conversation", default=os.getenv("CONVERSATION_ID", ""), help="对话 ID；设置后会加载并保存多轮修改历史")
    parser.add_argument("--feedback", default="", help="本轮修改意见，可与 --conversation 一起使用")
    parser.add_argument("--validate-project", action="store_true", help="校验项目 config、agent 配置和运行态目录后退出")
    parser.add_argument("--dry-run", action="store_true", help="预览本次运行会加载的项目、skills、sub-agent、模型和搜索配置后退出")
    parser.add_argument("--cache-list", action="store_true", help="列出当前项目的搜索缓存后退出")
    parser.add_argument("--cache-clear", action="store_true", help="清空当前项目的搜索缓存后退出")

    parser.add_argument("--search", action="store_true", help="启用联网搜索，并把搜索资料注入任务拆解上下文")
    parser.add_argument("--search-provider", default=os.getenv("SEARCH_PROVIDER", "auto"), help="搜索供应商：auto、tavily、duckduckgo")
    parser.add_argument("--search-query", default="", help="覆盖默认搜索词，默认使用用户目标")
    parser.add_argument("--max-results", type=int, default=int(os.getenv("SEARCH_MAX_RESULTS", "5")), help="最大搜索结果数量")
    return parser.parse_args()


def main() -> None:
    configure_stdio()
    if load_dotenv is not None:
        load_dotenv()

    args = parse_args()
    registry = SkillRegistry(args.config_dir)

    if args.setup_user:
        setup_user_config(args, force=True)
        return

    if args.init_runtime:
        ensure_runtime_template(args.runtime_dir, args.project or "demo")
        print(f"已初始化运行态目录：{args.runtime_dir}")
        return

    if args.init_project:
        init_project_template(args.init_project, args.config_dir)
        return

    project_ref = args.project_dir or args.project
    if args.validate_project:
        print_project_validation(args, project_ref)
        return

    run_id = runtime_timestamp()
    timer = start_timer()
    user_config_root = Path(args.config_dir) / "user" / args.user
    try:
        project = load_project_config(project_ref, str(user_config_root))
        project_root = user_config_root / "project" / (project.name if project else args.project)
        runtime_project = load_runtime_project(project.name if project else args.project, project_root)
    except Exception as error:
        if args.dry_run:
            print(f"Dry run 失败：{error}")
            raise SystemExit(1) from error
        project_name = args.project or (Path(project_ref).name if project_ref else "default")
        log_path = append_failure_log(
            args.runtime_dir,
            project_name,
            run_id,
            args.feedback.strip() or " ".join(args.goal).strip(),
            "project-load",
            error,
            elapsed_since(timer),
        )
        print(f"运行失败，已写入失败日志：{log_path}")
        raise SystemExit(1) from error

    project_name = project.name if project else (args.project or "default")

    if args.cache_list:
        ensure_project_runtime_dirs(args.runtime_dir, args.user, project_name)
        print_cache_entries(args.runtime_dir, args.user, project_name)
        return

    if args.cache_clear:
        ensure_project_runtime_dirs(args.runtime_dir, args.user, project_name)
        removed = clear_cache(args.runtime_dir, args.user, project_name)
        print(f"已清空缓存：project={project_name}，删除文件数={removed}")
        return


    if args.list_project_skills:
        print_project_skills(registry, project)
        return

    goal = args.feedback.strip() or " ".join(args.goal).strip()
    if args.dry_run:
        print_dry_run(registry, args, project, runtime_project, project_name, goal)
        return

    ensure_project_runtime_dirs(args.runtime_dir, args.user, project_name)

    if should_run_interactive(args):
        run_interactive_loop(args, registry, project, runtime_project, project_name, project_ref, goal)
        return

    if not goal:
        goal = read_text_input("请输入你想拆解或修改的目标：").strip()
    if not run_goal_once(args, registry, project, runtime_project, project_name, project_ref, goal):
        raise SystemExit(1)


def should_run_interactive(args: argparse.Namespace) -> bool:
    return sys.stdin.isatty() and not args.dry_run


def run_interactive_loop(
    args: argparse.Namespace,
    registry: SkillRegistry,
    project: ProjectConfig | None,
    runtime_project,
    project_name: str,
    project_ref: str | None,
    initial_goal: str,
) -> None:
    if not args.conversation:
        args.conversation = "default"
    args._interactive_color = True

    print_interactive_frame(project_name, args.conversation)
    goal = initial_goal
    if goal:
        WELCOME_ANIMATION_STATE.clear()
    input_mode = "chat"
    while True:
        if not goal:
            try:
                input_mode, user_input = read_mode_input(input_mode, terminal_input_config())
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if user_input is None:
                continue
            user_input = user_input.strip()
            if not user_input:
                continue
            WELCOME_ANIMATION_STATE.clear()
            if input_mode == "console" or user_input.startswith("/"):
                should_exit = handle_interactive_command(user_input, args, project_name)
                if should_exit:
                    return
                continue
            if not args.conversation:
                console_print("✻ 当前没有挂载对话。使用 /new [id] 或 /switch <id> 进入一个对话。")
                continue
            goal = user_input
        if not goal:
            continue

        success = run_goal_once(args, registry, project, runtime_project, project_name, project_ref, goal)
        if success and getattr(args, "_last_result", None) is not None:
            print_current_workspace(args, project_name, input_mode)
        goal = ""


def print_interactive_frame(project_name: str, conversation_id: str, active_mode: str = "chat") -> None:
    console_print("")
    line_count = print_welcome_panel(project_name, conversation_id, active_mode)
    remember_welcome_animation(project_name, conversation_id, active_mode, line_count)
    if active_mode == "console":
        colored_print("  console> 输入内置命令。按 Tab 切换到 chat>，输入 /help 查看命令。", MUTED_COLOR)
    else:
        colored_print("  chat> 输入要拆解的目标。按 Tab 切换到 console>，输入 /help 查看命令。", MUTED_COLOR)
    console_print("")


def print_current_workspace(args: argparse.Namespace, project_name: str, active_mode: str) -> None:
    result = getattr(args, "_last_result", None)
    if result is None:
        print_interactive_frame(project_name, args.conversation or "未挂载", active_mode)
        return
    print_result_workspace(args, project_name, args.conversation or "未挂载", active_mode, result)


def handle_interactive_command(
    raw_input: str,
    args: argparse.Namespace,
    project_name: str,
) -> bool:
    if not raw_input:
        return False

    parts = raw_input.split(maxsplit=1)
    command = parts[0].lower().lstrip("/")
    value = parts[1].strip() if len(parts) > 1 else ""

    if command in {"exit", "quit", "q"}:
        console_print("✻ Done")
        return True
    if command in {"help", "?"}:
        print_interactive_help()
        return False
    if command in {"current", "status"}:
        conversation = args.conversation or "未挂载"
        console_print(f"✻ project {project_name} · conversation {conversation}")
        return False
    if command == "clear":
        print_current_workspace(args, project_name, "console")
        return False
    if command in {"switch", "conversation", "use"}:
        if not value:
            console_print("✻ 用法：/switch <conversation-id>")
            return False
        args.conversation = normalize_conversation_id(value)
        console_print(f"✻ 已切换到对话：{args.conversation}")
        print_interactive_frame(project_name, args.conversation)
        return False
    if command in {"new", "start"}:
        args.conversation = normalize_conversation_id(value or runtime_timestamp())
        console_print(f"✻ 已进入新对话：{args.conversation}")
        print_interactive_frame(project_name, args.conversation)
        return False
    if command in {"leave", "close", "end"}:
        old_conversation = args.conversation or "未挂载"
        args.conversation = ""
        console_print(f"✻ 已退出当前对话：{old_conversation}。使用 /switch <id> 或 /new [id] 进入下一个对话。")
        return False

    console_print(f"✻ 未知命令：/{command}。输入 /help 查看可用命令。")
    return False


def normalize_conversation_id(value: str) -> str:
    return value.strip().replace("/", "_").replace("\\", "_") or "default"


def print_interactive_help() -> None:
    print_ui_box(
        "slash commands",
        [
            "Tab            在 chat> 和 console> 之间切换",
            "/help          显示这份帮助",
            "/status        查看当前 project 和 conversation",
            "/switch <id>   切换到已有或指定对话",
            "/new [id]      新建并切换到一个对话；不传 id 时自动生成",
            "/clear         重新显示欢迎面板",
            "/leave         退出当前对话但保留交互终端",
            "/exit          退出交互模式",
        ],
        CONSOLE_COLOR,
    )


def print_welcome_panel(project_name: str, conversation_id: str, active_mode: str = "chat", mascot_frame: int = 0) -> int:
    width = terminal_ui_width()
    inner_width = width - 2
    left_width = max(30, min(46, inner_width // 3 + 8))
    right_width = inner_width - left_width - 1
    cwd = str(Path.cwd())
    if visual_width(cwd) > left_width - 2:
        cwd = "..." + cwd[-(left_width - 5):]

    top_label = " Task Decomposer "
    top = f"╭{top_label}{'─' * max(0, width - visual_width(top_label) - 2)}╮"
    bottom = f"╰{'─' * (width - 2)}╯"
    colored_print(top, BORDER_COLOR)

    mascot = render_mascot_frame(
        mascot_frame,
        left_width,
        frames_path=os.getenv("TASK_DECOMPOSER_MASCOT_FRAMES"),
    )
    left_lines = [
        "",
        center_visual("Welcome back!", left_width),
        "",
        *mascot,
        "",
        center_visual("DeepSeek-V4-pro · API Usage Billing", left_width),
        center_visual(cwd, left_width),
    ]
    right_lines = [
        "Tips for getting started",
        f"active input: {active_mode}>",
        "chat> 直接输入目标，让 agent 拆解任务",
        "按 Tab 切换到 console> 输入命令",
        "常用命令：/status · /switch <id> · /new [id]",
        "conversation 会持续挂在当前对话",
        "",
        "What's new",
        "保留 chat/console 标识，并用 Tab 切换",
        "任务运行时显示阶段、耗时和 token",
        f"project {project_name} · conversation {conversation_id}",
    ]

    row_count = max(len(left_lines), len(right_lines))
    for index in range(row_count):
        left = left_lines[index] if index < len(left_lines) else ""
        right = right_lines[index] if index < len(right_lines) else ""
        left_cell = pad_visual(left, left_width)
        right_cell = pad_visual(right, right_width)
        colored_print(f"│{left_cell}│{right_cell}│", BORDER_COLOR)
    colored_print(bottom, BORDER_COLOR)
    return row_count + 2


def remember_welcome_animation(project_name: str, conversation_id: str, active_mode: str, line_count: int) -> None:
    WELCOME_ANIMATION_STATE.clear()
    if not color_enabled():
        return
    WELCOME_ANIMATION_STATE.update(
        {
            "project_name": project_name,
            "conversation_id": conversation_id,
            "active_mode": active_mode,
            "line_count": line_count,
            "frame": 0,
            "last_tick": time.monotonic(),
        }
    )


def refresh_welcome_animation(mode: str, *, force: bool = False) -> bool:
    if not WELCOME_ANIMATION_STATE or not color_enabled():
        return False
    if not _vt_supported():
        return False
    now = time.monotonic()
    last_tick = float(WELCOME_ANIMATION_STATE.get("last_tick", 0.0))
    if not force and now - last_tick < WELCOME_ANIMATION_INTERVAL:
        return False

    WELCOME_ANIMATION_STATE["last_tick"] = now
    WELCOME_ANIMATION_STATE["active_mode"] = mode
    frame = int(WELCOME_ANIMATION_STATE.get("frame", 0)) + 1
    WELCOME_ANIMATION_STATE["frame"] = frame
    line_count = int(WELCOME_ANIMATION_STATE.get("line_count", 0))
    if line_count <= 0:
        return False

    project_name = str(WELCOME_ANIMATION_STATE.get("project_name", "default"))
    conversation_id = str(WELCOME_ANIMATION_STATE.get("conversation_id", "default"))
    active_mode = str(WELCOME_ANIMATION_STATE.get("active_mode", mode))
    lines_to_panel_top = line_count + 2
    # Cleanly clear the entire region from the top of the welcome panel to the bottom of the terminal before drawing.
    sys.stdout.write(f"\r\033[{lines_to_panel_top}A\033[J")
    sys.stdout.flush()
    new_line_count = print_welcome_panel(project_name, conversation_id, active_mode, mascot_frame=frame)
    WELCOME_ANIMATION_STATE["line_count"] = new_line_count
    if active_mode == "console":
        colored_print("  console> 输入内置命令。按 Tab 切换到 chat>，输入 /help 查看命令。", MUTED_COLOR)
    else:
        colored_print("  chat> 输入要拆解的目标。按 Tab 切换到 console>，输入 /help 查看命令。", MUTED_COLOR)
    console_print("")
    return True


def update_welcome_animation_mode(mode: str) -> None:
    if WELCOME_ANIMATION_STATE:
        WELCOME_ANIMATION_STATE["active_mode"] = mode
        refresh_welcome_animation(mode, force=True)


def print_result_workspace(
    args: argparse.Namespace,
    project_name: str,
    conversation_id: str,
    active_mode: str,
    result,
) -> None:
    WELCOME_ANIMATION_STATE.clear()
    questions = getattr(args, "_last_questions", []) or []
    elapsed = getattr(args, "_last_elapsed_seconds", 0.0)
    tokens = getattr(args, "_last_token_count", 0)
    token_note = getattr(args, "_last_token_note", "")

    left_lines = task_summary_lines(result)
    right_lines = console_panel_lines(project_name, conversation_id, active_mode, elapsed, tokens, token_note)
    bottom_lines = question_panel_lines(questions)
    print_split_panel("Task Decomposer", left_lines, right_lines)
    for line in bottom_lines:
        colored_print(f"  {line}", MUTED_COLOR if line.startswith("模糊点") else CHAT_COLOR)
    console_print("")


def task_summary_lines(result) -> list[str]:
    lines = ["chat> 拆解结果", f"目标：{result.plan.goal}", "", f"任务（共 {len(result.plan.tasks)} 个）："]
    for index, task in enumerate(result.plan.tasks, start=1):
        lines.append(f"{index}. {task.title}")
    lines.extend(["", f"下一步：{result.plan.next_step}"])
    return lines


def console_panel_lines(
    project_name: str,
    conversation_id: str,
    active_mode: str,
    elapsed: float,
    tokens: int,
    token_note: str,
) -> list[str]:
    return [
        "console> 控制台",
        "/help          显示命令",
        "/status        查看状态",
        "/switch <id>   切换对话",
        "/new [id]      新对话",
        "/clear         重绘界面",
        "/exit          退出",
        "",
        f"project {project_name}",
        f"conversation {conversation_id}",
        f"last run {format_duration(elapsed)} · {format_token_count(tokens)} tokens{token_note}",
    ]


def question_panel_lines(questions: list[str]) -> list[str]:
    if questions:
        lines = ["模糊点：请补充下面信息，或按 Tab 到 console> 输入命令。"]
        lines.extend(f"- {question}" for question in questions[:3])
        return lines
    return ["模糊点：还有哪些约束、验收标准、时间安排或输出格式需要补充？"]


def print_split_panel(title: str, left_lines: list[str], right_lines: list[str]) -> None:
    width = terminal_ui_width()
    inner_width = width - 2
    left_width = max(30, min(56, inner_width // 2 - 1))
    right_width = inner_width - left_width - 1
    top_label = f" {title} "
    colored_print(f"╭{top_label}{'─' * max(0, width - visual_width(top_label) - 2)}╮", BORDER_COLOR)
    row_count = max(len(left_lines), len(right_lines))
    for index in range(row_count):
        left = left_lines[index] if index < len(left_lines) else ""
        right = right_lines[index] if index < len(right_lines) else ""
        left_wrapped = wrap_visual(left, left_width)
        right_wrapped = wrap_visual(right, right_width)
        wrapped_count = max(len(left_wrapped), len(right_wrapped))
        for wrap_index in range(wrapped_count):
            left_part = left_wrapped[wrap_index] if wrap_index < len(left_wrapped) else ""
            right_part = right_wrapped[wrap_index] if wrap_index < len(right_wrapped) else ""
            colored_print(f"│{pad_visual_untruncated(left_part, left_width)}│{pad_visual_untruncated(right_part, right_width)}│", BORDER_COLOR)
    colored_print(f"╰{'─' * (width - 2)}╯", BORDER_COLOR)


def terminal_ui_width() -> int:
    return max(72, min(120, shutil.get_terminal_size((96, 20)).columns))


def print_ui_box(title: str, lines: list[str], color: str) -> None:
    width = terminal_ui_width()
    label = f" {title} "
    top_fill = max(0, width - visual_width(label) - 2)
    top = f"╭{label}{'─' * top_fill}╮"
    bottom = f"╰{'─' * (width - 2)}╯"
    colored_print(top, color)
    for line in lines:
        content = f" {line}"
        for wrapped_line in wrap_visual(content, width - 2):
            colored_print(f"│{pad_visual_untruncated(wrapped_line, width - 2)}│", color)
    colored_print(bottom, color)


def pad_visual(text: str, width: int) -> str:
    text = truncate_visual(text, width)
    return text + (" " * max(0, width - visual_width(text)))


def pad_visual_untruncated(text: str, width: int) -> str:
    return text + (" " * max(0, width - visual_width(text)))


def wrap_visual(text: str, width: int) -> list[str]:
    if width <= 0:
        return [""]
    if not text:
        return [""]

    lines: list[str] = []
    for raw_line in text.splitlines() or [""]:
        current: list[str] = []
        used = 0
        for char in raw_line:
            char_width = visual_width(char)
            if used > 0 and used + char_width > width:
                lines.append("".join(current))
                current = []
                used = 0
            current.append(char)
            used += char_width
        lines.append("".join(current))
    return lines or [""]


def truncate_visual(text: str, width: int) -> str:
    if visual_width(text) <= width:
        return text
    if width <= 1:
        return ""

    result = []
    used = 0
    marker = "…"
    marker_width = visual_width(marker)
    limit = max(0, width - marker_width)
    for char in text:
        char_width = visual_width(char)
        if used + char_width > limit:
            break
        result.append(char)
        used += char_width
    return "".join(result) + marker


def center_visual(text: str, width: int) -> str:
    text = truncate_visual(text, width)
    padding = max(0, width - visual_width(text))
    left = padding // 2
    right = padding - left
    return (" " * left) + text + (" " * right)


def visual_width(text: str) -> int:
    wide_chars = {"F", "W"}
    return sum(2 if unicodedata.east_asian_width(char) in wide_chars else 1 for char in text)


def color_enabled() -> bool:
    return sys.stdout.isatty()


def terminal_input_config() -> TerminalInputConfig:
    return TerminalInputConfig(
        chat_color=CHAT_COLOR,
        console_color=CONSOLE_COLOR,
        reset=ANSI_RESET,
        clear_to_end=ANSI_CLEAR_TO_END,
        color_enabled=color_enabled,
        idle_callback=refresh_welcome_animation,
        mode_changed_callback=update_welcome_animation_mode,
    )


def console_print(message: str = "") -> None:
    colored_print(message, CONSOLE_COLOR)


def chat_print(message: str = "") -> None:
    colored_print(message, CHAT_COLOR)


def colored_print(message: str, color: str) -> None:
    if color_enabled():
        print(f"{color}{message}{ANSI_RESET}")
    else:
        print(message)


class ColorizedStdout:
    def __init__(self, stream, color: str):
        self.stream = stream
        self.color = color

    def write(self, text: str) -> int:
        if text and self.stream.isatty():
            self.stream.write(f"{self.color}{text}{ANSI_RESET}")
        else:
            self.stream.write(text)
        return len(text)

    def flush(self) -> None:
        self.stream.flush()

    def isatty(self) -> bool:
        return self.stream.isatty()

    def __getattr__(self, name: str):
        return getattr(self.stream, name)


@contextmanager
def output_color(color: str):
    if not color_enabled():
        yield
        return

    original_stdout = sys.stdout
    sys.stdout = ColorizedStdout(original_stdout, color)
    try:
        yield
    finally:
        sys.stdout = original_stdout


class AnimatedRunStatus:
    def __init__(self, args: argparse.Namespace, message: str):
        self.should_print = bool(getattr(args, "_interactive_color", False))
        self.enabled = bool(self.should_print and color_enabled())
        self.message = message
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.stream = getattr(sys.stdout, "stream", sys.stdout)

    def __enter__(self):
        if not self.enabled:
            if self.should_print and getattr(self, "message", ""):
                interactive_run_status_message(self.message)
            return self
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        if not self.enabled:
            return False
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=0.4)
        self.stream.write(f"\r{ANSI_CLEAR_TO_END}")
        self.stream.flush()
        return False

    def _animate(self) -> None:
        stars = ["✦", "✧", "✶", "✧"]
        index = 0
        while not self.stop_event.is_set():
            star = stars[index % len(stars)]
            index += 1
            self.stream.write(f"\r{WORKING_COLOR}{star} {self.message}{ANSI_RESET}{ANSI_CLEAR_TO_END}")
            self.stream.flush()
            self.stop_event.wait(0.16)


def animated_run_status(args: argparse.Namespace, message: str) -> AnimatedRunStatus:
    return AnimatedRunStatus(args, message)


def interactive_run_status_message(message: str) -> None:
    if color_enabled():
        print(f"{WORKING_COLOR}{message}{ANSI_RESET}")
    else:
        print(message)


def run_goal_once(
    args: argparse.Namespace,
    registry: SkillRegistry,
    project: ProjectConfig | None,
    runtime_project,
    project_name: str,
    project_ref: str | None,
    goal: str,
) -> bool:
    if getattr(args, "_interactive_color", False):
        with output_color(CONSOLE_COLOR):
            return _run_goal_once(args, registry, project, runtime_project, project_name, project_ref, goal)
    return _run_goal_once(args, registry, project, runtime_project, project_name, project_ref, goal)


def _run_goal_once(
    args: argparse.Namespace,
    registry: SkillRegistry,
    project: ProjectConfig | None,
    runtime_project,
    project_name: str,
    project_ref: str | None,
    goal: str,
) -> bool:
    if not goal:
        print("目标不能为空。")
        return False

    def status_callback(stage, message):
        interactive_run_status(args, f"运行中：{message}")

    try:
        result_dict = core_engine.run_core_decomposition(
            args=args,
            goal=goal,
            status_callback=status_callback,
            prompt_api_key_callback=read_text_input
        )
        print_run_result_dict(result_dict)
        return True
    except Exception as error:
        print(f"运行失败：{error}")
        return False


def interactive_run_status(args: argparse.Namespace, message: str) -> None:
    if getattr(args, "_interactive_color", False):
        interactive_run_status_message(message)


def run_token_count(
    llm_client: LLMClient | None,
    result,
    goal: str,
    context: str,
) -> int:
    if llm_client is not None and getattr(llm_client, "total_tokens", 0) > 0:
        return int(llm_client.total_tokens)
    return estimate_result_tokens(result, goal, context)


def estimate_result_tokens(result, goal: str, context: str) -> int:
    parts = [goal, context, result.plan.goal, result.plan.next_step]
    for task in result.plan.tasks:
        parts.extend([task.title, task.action, task.output])
    for run in result.sub_agent_runs:
        parts.extend([run.name, run.role, run.plan.goal, run.plan.next_step])
        for task in run.plan.tasks:
            parts.extend([task.title, task.action, task.output])
    text = "\n".join(part for part in parts if part)
    return max(1, int(len(text) / 3))


def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remainder = int(seconds % 60)
    return f"{minutes}m {remainder}s"


def format_token_count(tokens: int) -> str:
    if tokens >= 1000:
        value = tokens / 1000
        return f"{value:.1f}k"
    return str(tokens)


def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if os.name == "nt":
        _enable_windows_vt_processing()


def _enable_windows_vt_processing() -> None:
    """Enable ANSI / VT escape sequence processing on Windows.

    Without this flag the console prints escape codes as literal text,
    which breaks \033[K (clear to end of line), \033[nD (cursor left),
    colour codes, and every other ANSI sequence the app relies on.
    """
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        STD_OUTPUT_HANDLE = -11
        STD_ERROR_HANDLE = -12

        for handle_id in (STD_OUTPUT_HANDLE, STD_ERROR_HANDLE):
            handle = kernel32.GetStdHandle(handle_id)
            if handle == -1:
                continue
            mode = wintypes.DWORD()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                continue
            new_mode = mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, new_mode)
    except Exception:
        pass


def setup_user_config(args: argparse.Namespace, force: bool = False) -> None:
    user_name = (args.user or "").strip()
    if not user_name:
        if not sys.stdin.isatty():
            return
        user_name = read_text_input("请输入用户名称：").strip()
        args.user = user_name
    if not user_name:
        return

    config = load_user_runtime_config(args.runtime_dir, user_name) or UserRuntimeConfig(name=user_name)
    apply_user_config(config)
    required_envs = required_user_api_key_envs(args)
    if not required_envs:
        provider = prompt_provider(args.provider) if force else normalize_provider(args.provider)
        if provider == "auto":
            provider = "deepseek"
        required_envs = [default_api_key_env(provider)]
        config.provider = config.provider or provider

    missing_envs = [
        env_name
        for env_name in required_envs
        if not os.getenv(env_name) and not config.api_keys.get(env_name)
    ]
    if not force and not missing_envs:
        return

    if not sys.stdin.isatty():
        if force:
            raise RuntimeError("--setup-user 需要在交互式终端中输入用户名称和 API Key")
        return

    print(f"正在创建或更新用户级配置：{user_name}")
    for env_name in missing_envs:
        api_key = getpass.getpass(f"请输入 {env_name}：").strip()
        if not api_key:
            raise RuntimeError(f"{env_name} 不能为空")
        config.api_keys[env_name] = api_key

    path = save_user_runtime_config(args.runtime_dir, config)
    apply_user_config(config)
    print(f"用户级配置已保存：{path}")


def apply_user_config(config: UserRuntimeConfig) -> None:
    for env_name, api_key in config.api_keys.items():
        if api_key and not os.getenv(env_name):
            os.environ[env_name] = api_key
    if config.provider and not os.getenv("LLM_PROVIDER"):
        os.environ["LLM_PROVIDER"] = config.provider
    if config.model and not os.getenv("MODEL"):
        os.environ["MODEL"] = config.model
    if config.base_url and not os.getenv("BASE_URL"):
        os.environ["BASE_URL"] = config.base_url


def prompt_provider(default_provider: str) -> str:
    fallback = "deepseek" if (default_provider or "auto") == "auto" else default_provider
    while True:
        raw_value = read_text_input(f"请选择模型供应商 openai/claude/deepseek/custom [{fallback}]：").strip() or fallback
        try:
            provider = normalize_provider(raw_value)
        except RuntimeError as error:
            print(error)
            continue
        if provider == "auto":
            provider = "deepseek"
        return provider


def default_api_key_env(provider: str) -> str:
    defaults = PROVIDER_DEFAULTS[provider]
    return defaults["api_key_envs"][0]


def required_user_api_key_envs(args: argparse.Namespace) -> list[str]:
    project_name = args.project or (Path(args.project_dir).name if args.project_dir else "")
    runtime_project = load_runtime_project(project_name, args.runtime_dir)
    if runtime_project is None:
        return []

    env_names: list[str] = []
    configs = [runtime_project.main, *runtime_project.agents.values()]
    for config in configs:
        if config is None or not config.enabled:
            continue
        if config.api_key_env:
            env_names.append(config.api_key_env)
        env_names.extend(config.api_key_envs)

    deduped = []
    seen = set()
    for env_name in env_names:
        if env_name and env_name not in seen:
            deduped.append(env_name)
            seen.add(env_name)
    return deduped


def build_conversation_context(
    args: argparse.Namespace,
    project: ProjectConfig | None,
    project_name: str | None = None,
) -> str:
    if not args.conversation:
        return ""
    resolved_project_name = project.name if project else (project_name or "default")
    history_context = load_conversation_context(args.runtime_dir, resolved_project_name, args.conversation)
    if not history_context:
        return ""
    return f"以下是本次多轮修改的历史上下文，请基于它继续修改计划：\n{history_context}"


def filter_sub_agent_specs(
    specs: list[ProjectSubAgentConfig],
    mode: str,
    goal: str,
) -> list[ProjectSubAgentConfig]:
    if mode == "all":
        return specs
    if mode == "risk-only":
        return [spec for spec in specs if is_risk_agent(spec)]
    if mode == "auto":
        selected = []
        for spec in specs:
            text = f"{spec.name} {spec.role} {' '.join(spec.skills)}"
            if any(word in goal for word in ["风险", "验收", "依赖", "检查", "质量"]):
                if is_risk_agent(spec):
                    selected.append(spec)
            if any(word in goal for word in ["项目", "开发", "实现", "MVP", "里程碑", "做一个"]):
                if has_any(text, ["执行", "execution", "MVP", "里程碑"]):
                    selected.append(spec)
            if any(word in goal for word in ["用户", "体验", "产品", "场景", "价值"]):
                if has_any(text, ["用户", "价值", "体验", "user-value"]):
                    selected.append(spec)
        if not selected:
            return specs
        deduped = []
        seen = set()
        for spec in selected:
            if spec.name not in seen:
                deduped.append(spec)
                seen.add(spec.name)
        return deduped
    return specs


def is_risk_agent(spec: ProjectSubAgentConfig) -> bool:
    text = f"{spec.name} {spec.role} {' '.join(spec.skills)}"
    return has_any(text, ["风险", "审查", "验收", "risk-review"])


def has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def parse_cli_sub_agents(values: list[str]) -> list[ProjectSubAgentConfig]:
    specs = []
    for value in values:
        if ":" in value:
            name, role = value.split(":", 1)
        else:
            name, role = value, ""
        name = name.strip()
        if name:
            specs.append(ProjectSubAgentConfig(name=name, role=role.strip()))
    return specs


def init_project_template(project_ref: str, config_dir: str) -> None:
    root = project_root_for_create(project_ref, config_dir)
    root.mkdir(parents=True, exist_ok=True)
    files = {
        root / "main" / "planning" / "SKILL.md": "# Planning Skill\n\n主 Agent 使用：负责综合目标、搜索结果和 sub-agent 建议，输出最终执行计划。\n",
        root / "sub-agent1" / "execution" / "SKILL.md": "# Execution Skill\n\nsub-agent1 使用：关注任务顺序、MVP、里程碑和可执行路径。\n",
        root / "sub-agent2" / "risk-review" / "SKILL.md": "# Risk Review Skill\n\nsub-agent2 使用：关注遗漏任务、风险、依赖和验收标准。\n",
    }
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    print(f"已创建项目配置与技能模板：{root}")


def print_cache_entries(runtime_dir: str, username: str, project_name: str) -> None:
    entries = list_cache_entries(runtime_dir, username, project_name)
    if not entries:
        print(f"当前项目没有缓存：{project_name}")
        return

    print(f"缓存列表：{project_name}")
    for index, entry in enumerate(entries, start=1):
        status = "expired" if entry.get("expired") else "valid"
        print(
            f"{index}. provider={entry['provider']} "
            f"query={entry['query']} "
            f"max_results={entry['max_results']} "
            f"results={entry['result_count']} "
            f"created_at={entry['created_at']} "
            f"expires_at={entry['expires_at']} "
            f"status={status}"
        )


def print_dry_run(
    registry: SkillRegistry,
    args: argparse.Namespace,
    project: ProjectConfig | None,
    runtime_project,
    project_name: str,
    goal: str,
) -> None:
    print("Dry run：本次不会调用模型、不会联网、不会写入 output/log/conversation")
    print(f"项目：{project_name}")
    print(f"运行态目录：{args.runtime_dir}")
    print(f"目标：{goal or '未提供'}")

    if project is None:
        print("项目 skills：未指定")
    else:
        print(f"项目 skills 目录：{project.root}")
        main_skills = registry.list_project_agent_skills(str(project.root), "main")
        print("main skills：" + (", ".join(main_skills) if main_skills else "无"))

    global_skills = [name for raw_name in args.global_skill for name in raw_name.split(",") if name.strip()]
    print("global skills：" + (", ".join(global_skills) if global_skills else "无"))

    main_config = runtime_project.main if runtime_project else None
    print_agent_dry_run("main", main_config)

    specs: list[ProjectSubAgentConfig] = []
    if project is not None:
        specs.extend(project.sub_agents)
    specs.extend(parse_cli_sub_agents(args.sub_agent))
    selected_specs = filter_sub_agent_specs(specs, args.sub_agent_mode, goal)
    print(f"sub-agent 策略：{args.sub_agent_mode}")
    if not selected_specs:
        print("sub-agents：无")
    for spec in selected_specs:
        runtime_config = runtime_project.agents.get(spec.name) if runtime_project else None
        skills = registry.list_project_agent_skills(str(project.root), spec.name) if project is not None else []
        print_agent_dry_run(spec.name, runtime_config, skills)

    if args.search:
        query = args.search_query or goal
        cache_summary = dry_run_cache_summary(args.runtime_dir, args.user, project_name)
        print(f"联网搜索：启用 provider={args.search_provider} max_results={args.max_results} query={query or '未提供'}")
        print(f"搜索缓存：{cache_summary}")
    else:
        print("联网搜索：未启用")


def print_agent_dry_run(agent_name: str, config, skills: list[str] | None = None) -> None:
    skills = skills or []
    if config is None:
        print(f"- {agent_name}：未找到运行态配置" + (f"，skills={', '.join(skills)}" if skills else ""))
        return

    env_names = []
    if config.api_key_env:
        env_names.append(config.api_key_env)
    env_names.extend(config.api_key_envs)
    env_status = "未配置"
    if env_names:
        env_status = "已检测到" if any(os.getenv(name) for name in env_names) else "未检测到"

    skill_note = f"，skills={', '.join(skills)}" if skills else ""
    print(
        f"- {agent_name}：provider={config.provider or '未配置'} "
        f"model={config.model or '未配置'} "
        f"enabled={config.enabled} "
        f"api_key_env={', '.join(env_names) if env_names else '未配置'}({env_status})"
        f"{skill_note}"
    )


def dry_run_cache_summary(runtime_dir: str, username: str, project_name: str) -> str:
    path = Path(runtime_dir) / "user" / username / "project" / project_name / "cache" / "search.json"
    if not path.exists():
        return f"无缓存文件 ({path})"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return f"缓存文件不可读取 ({path})：{error}"

    valid_count = 0
    expired_count = 0
    for item in data.values():
        if is_cache_item_expired(item):
            expired_count += 1
        else:
            valid_count += 1
    return f"{path}，有效 {valid_count} 条，过期 {expired_count} 条"


def print_project_validation(args: argparse.Namespace, project_ref: str | None) -> None:
    checks = core_engine.validate_project(args, project_ref)
    project_name = args.project or (Path(project_ref).name if project_ref else "default")
    print(f"项目校验：{project_name}")
    for level, message in checks:
        print(f"[{level}] {message}")

    errors = [message for level, message in checks if level == "ERROR"]
    if errors:
        print(f"校验未通过：{len(errors)} 个错误")
        raise SystemExit(1)
    print("校验通过")


def print_configuration_diagnostics(
    args: argparse.Namespace,
    project_ref: str | None,
    checks: list[tuple[str, str]] | None = None,
) -> None:
    if args.local:
        return
    print("\n配置检查结果：")
    checks = checks if checks is not None else core_engine.validate_project(args, project_ref, require_api_keys=True)
    if not checks:
        print("[ERROR] 未找到可校验的项目配置")
    for level, message in checks:
        if level in {"ERROR", "WARN"}:
            print(f"[{level}] {message}")
    print("\n调整方式：")
    print(f"- 创建或更新用户级配置：python task_decomposer.py --setup-user --user {args.user or '<用户名>'}")
    print("- 或在 .env / 系统环境变量中设置对应的 API Key，例如 DEEPSEEK_API_KEY、OPENAI_API_KEY、ANTHROPIC_API_KEY")
    print("- 如果只是想看本地演示结果，请显式加 --local")
    if project_ref:
        print(f"- 查看完整项目检查：python task_decomposer.py --project {args.project or project_ref} --validate-project")


def print_project_skills(registry: SkillRegistry, project: ProjectConfig | None) -> None:
    if project is None:
        print("请先通过 --project 或 --project-dir 指定项目。")
        return

    print(f"项目：{project.name}")
    main_skills = registry.list_project_agent_skills(str(project.root), "main")
    print("main skills：" + (", ".join(main_skills) if main_skills else "无"))
    for sub_agent in project.sub_agents:
        names = registry.list_project_agent_skills(str(project.root), sub_agent.name)
        print(f"{sub_agent.name} skills：" + (", ".join(names) if names else "无"))


def print_runtime_info(
    llm_client: LLMClient | None,
    skills,
    sub_agents: list[SubAgentSpec],
    search_service: SearchService | None,
    project: ProjectConfig | None,
    runtime_dir: str,
    has_runtime_project: bool,
) -> None:
    if project is not None:
        print(f"当前项目：{project.name}")
    if has_runtime_project:
        print(f"运行态配置：{runtime_dir}")

    if llm_client is None:
        print("当前模型：本地演示模式")
    else:
        config = llm_client.config
        print(f"当前主模型：{config.name} / {config.model}")

    if skills:
        print("主 Agent Skills：" + "、".join(skill.name for skill in skills))

    if sub_agents:
        print("已启用 sub-agents：" + "、".join(agent.name for agent in sub_agents))
        for agent in sub_agents:
            skill_names = "、".join(skill.name for skill in agent.skills) or "无"
            provider_note = f"；Provider：{agent.provider}" if agent.provider else ""
            model_note = f"；模型：{agent.model_config.name}/{agent.model_config.model}" if agent.model_config else ""
            print(f"- {agent.name}：{agent.role or '未指定角色'}；Skills：{skill_names}{provider_note}{model_note}")

    if search_service is not None:
        print(f"联网搜索：已启用（{search_service.config.provider}）")


def print_run_result_dict(result_dict: dict) -> None:
    plan = result_dict.get("plan", {})
    print("\n=== 任务拆解结果 ===")
    print(f"目标：{plan.get('goal', '')}\n")
    for index, task in enumerate(plan.get("tasks", []), start=1):
        print(f"{index}. {task.get('title', '')}")
        print(f"   行动：{task.get('action', '')}")
        print(f"   产出：{task.get('output', '')}")
    print(f"\n下一步建议：{plan.get('next_step', '')}")


def print_run_result(result) -> None:
    for warning in result.warnings:
        print(f"提示：{warning}")

    if result.sub_agent_runs:
        print("\n=== sub-agent 建议摘要 ===")
        for run in result.sub_agent_runs:
            print(f"- {run.name}：{run.role or '未指定角色'}，产出 {len(run.plan.tasks)} 个建议任务")

    plan = result.plan
    print("\n=== 任务拆解结果 ===")
    print(f"目标：{plan.goal}\n")
    for index, task in enumerate(plan.tasks, start=1):
        print(f"{index}. {task.title}")
        print(f"   行动：{task.action}")
        print(f"   产出：{task.output}")
    print(f"\n下一步建议：{plan.next_step}")

    if plan.sources:
        print("\n参考来源：")
        for source in plan.sources:
            print(f"- {source}")