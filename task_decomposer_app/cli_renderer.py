import os
import sys
import time
import shutil
import unicodedata
from pathlib import Path
from contextlib import contextmanager

# ANSI Escape Codes & Configs
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
_MASCOT_FRAMES_CACHE: list[list[str]] = []
_MASCOT_FRAMES_LOADED_PATH: str | None = None


def _resolve_mascot_json_path(env_path: str | None = None) -> str | None:
    if env_path:
        resolved = Path(env_path).expanduser().resolve()
        if resolved.is_file():
            return str(resolved)

    search_dir = Path.cwd().resolve()
    for _name in ("custom_mascot.json", "default_mascot.json"):
        current = search_dir
        for _ in range(5):
            candidate = current / _name
            if candidate.is_file():
                return str(candidate)
            parent = current.parent
            if parent == current:
                break
            current = parent
    return None


def _load_mascot_frames(frames_path: str | None = None) -> list[list[str]]:
    global _MASCOT_FRAMES_CACHE, _MASCOT_FRAMES_LOADED_PATH
    resolved = _resolve_mascot_json_path(frames_path)
    if resolved is None:
        return []
    if resolved == _MASCOT_FRAMES_LOADED_PATH and _MASCOT_FRAMES_CACHE:
        return _MASCOT_FRAMES_CACHE
    try:
        import json
        data = json.loads(Path(resolved).read_text(encoding="utf-8"))
        frames = data.get("frames", data) if isinstance(data, dict) else data
        if not isinstance(frames, list):
            return []
        result = [f for f in frames if isinstance(f, list) and all(isinstance(line, str) for line in f)]
        _MASCOT_FRAMES_CACHE = result
        _MASCOT_FRAMES_LOADED_PATH = resolved
        return result
    except Exception:
        return []


def render_mascot_frame(frame: int, width: int, *, frames_path: str | None = None) -> list[str]:
    frames = _load_mascot_frames(frames_path)
    if not frames:
        return []
    lines = frames[frame % len(frames)]
    return [center_visual(line, width) for line in lines]


def color_enabled() -> bool:
    return sys.stdout.isatty()


def colored_print(message: str, color: str) -> None:
    if color_enabled():
        print(f"{color}{message}{ANSI_RESET}")
    else:
        print(message)


def console_print(message: str = "") -> None:
    colored_print(message, CONSOLE_COLOR)


def chat_print(message: str = "") -> None:
    colored_print(message, CHAT_COLOR)


def terminal_ui_width() -> int:
    return max(72, min(120, shutil.get_terminal_size((96, 20)).columns))


def visual_width(text: str) -> int:
    wide_chars = {"F", "W"}
    return sum(2 if unicodedata.east_asian_width(char) in wide_chars else 1 for char in text)


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


def pad_visual(text: str, width: int) -> str:
    text = truncate_visual(text, width)
    return text + (" " * max(0, width - visual_width(text)))


def pad_visual_untruncated(text: str, width: int) -> str:
    return text + (" " * max(0, width - visual_width(text)))


def center_visual(text: str, width: int) -> str:
    text = truncate_visual(text, width)
    padding = max(0, width - visual_width(text))
    left = padding // 2
    right = padding - left
    return (" " * left) + text + (" " * right)


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
    from task_decomposer_app.terminal_input import _vt_supported
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
    project_name: str,
    conversation_id: str,
    active_mode: str,
    result_dict: dict,
) -> None:
    WELCOME_ANIMATION_STATE.clear()
    questions = result_dict.get("questions", []) or []
    elapsed = result_dict.get("elapsed", 0.0)
    tokens = result_dict.get("tokens", 0)
    token_note = result_dict.get("token_note", "")
    plan = result_dict.get("plan", {})

    left_lines = task_summary_lines(plan)
    right_lines = console_panel_lines(project_name, conversation_id, active_mode, elapsed, tokens, token_note)
    bottom_lines = question_panel_lines(questions)
    print_split_panel("Task Decomposer", left_lines, right_lines)
    for line in bottom_lines:
        colored_print(f"  {line}", MUTED_COLOR if line.startswith("模糊点") else CHAT_COLOR)
    console_print("")


def task_summary_lines(plan: dict) -> list[str]:
    lines = ["chat> 拆解结果", f"目标：{plan.get('goal', '')}", "", f"任务（共 {len(plan.get('tasks', []))} 个）："]
    for index, task in enumerate(plan.get("tasks", []), start=1):
        lines.append(f"{index}. {task.get('title', '')}")
    lines.extend(["", f"下一步：{plan.get('next_step', '')}"])
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
    def __init__(self, args, message: str):
        self.should_print = bool(getattr(args, "_interactive_color", False))
        self.enabled = bool(self.should_print and color_enabled())
        self.message = message
        import threading
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.stream = getattr(sys.stdout, "stream", sys.stdout)

    def __enter__(self):
        if not self.enabled:
            if self.should_print and getattr(self, "message", ""):
                if color_enabled():
                    print(f"{WORKING_COLOR}{self.message}{ANSI_RESET}")
                else:
                    print(self.message)
            return self
        import threading
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
