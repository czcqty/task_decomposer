import os
import sys
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass


ANSI_RESET = "\033[0m"
ANSI_CLEAR_TO_END = "\033[K"


@dataclass(frozen=True)
class TerminalInputConfig:
    chat_color: str = ""
    console_color: str = ""
    reset: str = ANSI_RESET
    clear_to_end: str = ANSI_CLEAR_TO_END
    poll_interval: float = 0.03
    color_enabled: Callable[[], bool] | None = None
    idle_callback: Callable[[str], None] | None = None
    mode_changed_callback: Callable[[str], None] | None = None
    prompt_for_mode: Callable[[str], str] | None = None


def read_mode_input(mode: str, config: TerminalInputConfig | None = None) -> tuple[str, str | None]:
    config = config or TerminalInputConfig()
    prompt_for_mode = config.prompt_for_mode or mode_prompt
    
    # 兼容模式：若非 TTY 或启用了 TASK_DECOMPOSER_COMPAT_INPUT=1，则使用标准 input()
    # 标准 input() 能完美支持系统的输入法（IME）以及中文字符输入
    if not sys.stdin.isatty() or os.environ.get("TASK_DECOMPOSER_COMPAT_INPUT") == "1":
        try:
            user_input = input(prompt_for_mode(mode))
            return mode, user_input
        except (KeyboardInterrupt, EOFError):
            sys.stdout.write("\n")
            sys.stdout.flush()
            return mode, None

    if os.name == "nt":
        return _read_mode_input_windows(mode, config)
    return _read_mode_input_posix(mode, config)


def read_text_input(
    prompt: str,
    *,
    color: str = "",
    color_enabled: Callable[[], bool] | None = None,
    reset: str = ANSI_RESET,
) -> str:
    if not _should_color(color_enabled):
        return input(prompt)
    try:
        return input(f"{color}{prompt}")
    finally:
        sys.stdout.write(reset)
        sys.stdout.flush()


def mode_prompt(mode: str) -> str:
    return f"{mode}> "


def toggle_input_mode(mode: str) -> str:
    return "console" if mode == "chat" else "chat"


_last_line_width = 0
_last_activity_time = 0.0


# _move_cursor is no longer needed since we redraw the entire line to handle cursor updates robustly.


def _read_mode_input_windows(mode: str, config: TerminalInputConfig) -> tuple[str, str | None]:
    import msvcrt
    global _last_line_width
    _last_line_width = 0

    buffer: list[str] = []
    cursor = 0
    _redraw_input_line(mode, buffer, cursor, config)
    while True:
        if not msvcrt.kbhit():
            _handle_idle(mode, buffer, cursor, config)
            time.sleep(config.poll_interval)
            continue
        global _last_activity_time
        _last_activity_time = time.monotonic()
        char = msvcrt.getwch()
        if char in {"\r", "\n"}:
            _finish_input_line(config)
            return mode, "".join(buffer)
        if char == "\x03":
            _reset_output(config)
            raise KeyboardInterrupt
        if char == "\t":
            mode, cursor = _switch_input_mode(mode, buffer, config)
            continue
        if char in {"\b", "\x7f"}:
            if cursor > 0:
                buffer.pop(cursor - 1)
                cursor -= 1
                _redraw_input_line(mode, buffer, cursor, config)
            continue
        if char == "\x00" or char == "\xe0":
            key = msvcrt.getwch()
            if key == "K" and cursor > 0:
                cursor -= 1
                _redraw_input_line(mode, buffer, cursor, config)
            elif key == "M" and cursor < len(buffer):
                cursor += 1
                _redraw_input_line(mode, buffer, cursor, config)
            elif key == "S" and cursor < len(buffer):
                buffer.pop(cursor)
                _redraw_input_line(mode, buffer, cursor, config)
            elif key == "G":
                cursor = 0
                _redraw_input_line(mode, buffer, cursor, config)
            elif key == "O":
                cursor = len(buffer)
                _redraw_input_line(mode, buffer, cursor, config)
            continue
        if char.isprintable():
            buffer.insert(cursor, char)
            cursor += 1
            _redraw_input_line(mode, buffer, cursor, config)


def _read_mode_input_posix(mode: str, config: TerminalInputConfig) -> tuple[str, str | None]:
    import select
    import termios
    import tty
    global _last_line_width
    _last_line_width = 0

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    buffer: list[str] = []
    cursor = 0
    _redraw_input_line(mode, buffer, cursor, config)
    try:
        tty.setraw(fd)
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], config.poll_interval)
            if not ready:
                _handle_idle(mode, buffer, cursor, config)
                continue
            global _last_activity_time
            _last_activity_time = time.monotonic()
            char = sys.stdin.read(1)
            if char in {"\r", "\n"}:
                _finish_input_line(config)
                return mode, "".join(buffer)
            if char == "\x03":
                _reset_output(config)
                raise KeyboardInterrupt
            if char == "\x04":
                _reset_output(config)
                raise EOFError
            if char == "\t":
                mode, cursor = _switch_input_mode(mode, buffer, config)
                continue
            if char in {"\x7f", "\b"}:
                if cursor > 0:
                    buffer.pop(cursor - 1)
                    cursor -= 1
                    _redraw_input_line(mode, buffer, cursor, config)
                continue
            if char == "\x1b":
                sequence = sys.stdin.read(2)
                if sequence == "[D" and cursor > 0:
                    cursor -= 1
                    _redraw_input_line(mode, buffer, cursor, config)
                elif sequence == "[C" and cursor < len(buffer):
                    cursor += 1
                    _redraw_input_line(mode, buffer, cursor, config)
                elif sequence == "[H":
                    cursor = 0
                    _redraw_input_line(mode, buffer, cursor, config)
                elif sequence == "[F":
                    cursor = len(buffer)
                    _redraw_input_line(mode, buffer, cursor, config)
                elif sequence == "[1":
                    sys.stdin.read(1)
                    cursor = 0
                    _redraw_input_line(mode, buffer, cursor, config)
                elif sequence == "[4":
                    sys.stdin.read(1)
                    cursor = len(buffer)
                    _redraw_input_line(mode, buffer, cursor, config)
                elif sequence == "[3":
                    suffix = sys.stdin.read(1)
                    if suffix == "~" and cursor < len(buffer):
                        buffer.pop(cursor)
                        _redraw_input_line(mode, buffer, cursor, config)
                continue
            if char.isprintable():
                buffer.insert(cursor, char)
                cursor += 1
                _redraw_input_line(mode, buffer, cursor, config)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def _switch_input_mode(mode: str, buffer: list[str], config: TerminalInputConfig) -> tuple[str, int]:
    global _last_line_width
    mode = toggle_input_mode(mode)
    buffer.clear()
    cursor = 0
    if config.mode_changed_callback is not None:
        config.mode_changed_callback(mode)
    _last_line_width = 0
    _redraw_input_line(mode, buffer, cursor, config)
    return mode, cursor


def _redraw_input_line(mode: str, buffer: list[str], cursor: int, config: TerminalInputConfig) -> None:
    global _last_line_width
    color = _mode_color(mode, config)
    prompt_for_mode = config.prompt_for_mode or mode_prompt
    prompt = prompt_for_mode(mode)
    text = "".join(buffer)
    line = prompt + text

    use_color = bool(color and _should_color(config.color_enabled))
    vt = _vt_supported()

    line_width = _visual_width(line)
    padding = max(0, _last_line_width - line_width)
    _last_line_width = line_width

    # Pad with spaces to cleanly overwrite any old character remnants.
    # This is 100% reliable across all standard/legacy shells and buggy VT implementations.
    if use_color:
        sys.stdout.write(f"\r{color}{line}{' ' * padding}{config.reset}")
    else:
        sys.stdout.write(f"\r{line}{' ' * padding}")

    if vt:
        # Extra safeguard: VT terminal erase-to-end-of-line
        sys.stdout.write("\033[K")

    # Move cursor back: padding + suffix
    suffix_width = _visual_width("".join(buffer[cursor:]))
    backtrack = padding + suffix_width
    if backtrack > 0:
        if vt:
            sys.stdout.write(f"\033[{backtrack}D")
        else:
            sys.stdout.write("\b" * backtrack)
    sys.stdout.flush()


def _finish_input_line(config: TerminalInputConfig) -> None:
    sys.stdout.write(config.reset + "\n")
    sys.stdout.flush()


def _reset_output(config: TerminalInputConfig) -> None:
    sys.stdout.write(config.reset)
    sys.stdout.flush()


def _handle_idle(mode: str, buffer: list[str], cursor: int, config: TerminalInputConfig) -> None:
    if config.idle_callback is not None:
        # Pause animation completely if there is any text in the buffer
        if len(buffer) > 0:
            return
        # Use a safe threshold to avoid conflicts with active typing / IME composition.
        # On Windows, background writes during IME composition corrupt the console state,
        # so we use a very safe 5.0s inactivity threshold. On POSIX, we use 1.5s.
        global _last_activity_time
        threshold = 5.0 if os.name == "nt" else 1.5
        if time.monotonic() - _last_activity_time < threshold:
            return
        if config.idle_callback(mode):
            global _last_line_width
            _last_line_width = 0
            _redraw_input_line(mode, buffer, cursor, config)


def _mode_color(mode: str, config: TerminalInputConfig) -> str:
    return config.chat_color if mode == "chat" else config.console_color


def _should_color(color_enabled: Callable[[], bool] | None) -> bool:
    return color_enabled() if color_enabled is not None else sys.stdout.isatty()


def _visual_width(text: str) -> int:
    wide_chars = {"F", "W", "A"}
    return sum(2 if unicodedata.east_asian_width(char) in wide_chars else 1 for char in text)


def _terminal_columns() -> int:
    try:
        import shutil
        return shutil.get_terminal_size((80, 24)).columns
    except Exception:
        return 80


_vt_ok: bool | None = None


def _vt_supported() -> bool:
    """Check whether the console handles VT / ANSI escape sequences."""
    global _vt_ok
    if _vt_ok is not None:
        return _vt_ok

    if os.name != "nt":
        _vt_ok = sys.stdout.isatty()
        return _vt_ok

    # On Windows, check if ENABLE_VIRTUAL_TERMINAL_PROCESSING is set.
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = wintypes.DWORD()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            _vt_ok = bool(mode.value & 0x0004)
        else:
            # Fallback for TTYs like Git Bash / MSYS2 / VS Code bash
            _vt_ok = sys.stdout.isatty() and any(
                var in os.environ for var in ("TERM", "COLORTERM", "ANSICON", "MSYSTEM")
            )
    except Exception:
        _vt_ok = False
    return _vt_ok
