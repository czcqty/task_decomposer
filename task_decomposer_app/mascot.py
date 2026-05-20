import argparse
import json
import shutil
import sys
import time
import unicodedata
from functools import lru_cache
from pathlib import Path


ANSI_CLEAR_SCREEN = "\033[2J\033[H"
ANSI_HIDE_CURSOR = "\033[?25l"
ANSI_SHOW_CURSOR = "\033[?25h"
ANSI_RESET = "\033[0m"
MASCOT_COLOR = "\033[38;5;217m"
DEFAULT_MASCOT_FRAME_COUNT = 12


def render_mascot_frame(
    frame: int,
    width: int | None = None,
    *,
    frames_path: str | None = None,
    centered: bool = True,
) -> list[str]:
    if not frames_path:
        return render_default_ufo_frame(frame, width or 44, centered=centered)

    frames = load_mascot_frames(frames_path)
    if not frames:
        return render_default_ufo_frame(frame, width or 44, centered=centered)

    lines = frames[frame % len(frames)]
    if width is None or not centered:
        return list(lines)
    return [center_visual(line, width) for line in lines]


def load_mascot_frames(path: str | None) -> list[list[str]]:
    if not path:
        return [render_default_ufo_frame(frame, 44, centered=False) for frame in range(DEFAULT_MASCOT_FRAME_COUNT)]
    return _load_mascot_frames_cached(str(Path(path).expanduser().resolve()))


def render_default_ufo_frame(frame: int, width: int, *, centered: bool = True) -> list[str]:
    scene_width = max(28, width)
    scene_height = 9
    canvas = [[" " for _ in range(scene_width)] for _ in range(scene_height)]
    phase = frame % DEFAULT_MASCOT_FRAME_COUNT
    person_x = max(4, scene_width // 2 - 1)

    ufo_positions = [
        scene_width - 9,
        scene_width - 12,
        scene_width - 15,
        person_x + 4,
        person_x - 2,
        person_x - 2,
        person_x - 2,
        person_x - 2,
        person_x - 6,
        person_x - 12,
        -2,
        -8,
    ]
    ufo_x = ufo_positions[phase]

    overlay(canvas, 0, ufo_x, "  _.-._  ")
    overlay(canvas, 1, ufo_x, " /_o_o_\\ ")
    overlay(canvas, 2, ufo_x, "<--===-->")

    if 4 <= phase <= 7:
        draw_beam(canvas, ufo_x + 4, phase)

    if phase <= 3:
        draw_walking_person(canvas, 5, person_x, phase)
    elif phase == 4:
        draw_person(canvas, 5, person_x)
    elif phase == 5:
        draw_person(canvas, 4, person_x)
    elif phase == 6:
        draw_small_person(canvas, 3, person_x)
    elif phase == 7:
        overlay(canvas, 3, person_x, "(o)")

    overlay(canvas, 8, 0, "_" * scene_width)
    lines = ["".join(row).rstrip() for row in canvas]
    if centered and width > scene_width:
        return [center_visual(line, width) for line in lines]
    return lines


def overlay(canvas: list[list[str]], row: int, col: int, text: str) -> None:
    if row < 0 or row >= len(canvas):
        return
    width = len(canvas[row])
    for offset, char in enumerate(text):
        target = col + offset
        if 0 <= target < width and char != " ":
            canvas[row][target] = char


def draw_beam(canvas: list[list[str]], center: int, phase: int) -> None:
    widths = [3, 5, 7, 9]
    for index, row in enumerate(range(3, 7)):
        beam_width = widths[min(index, len(widths) - 1)]
        if phase == 7:
            beam_width = max(1, beam_width - 2)
        left = center - beam_width // 2
        right = left + beam_width - 1
        overlay(canvas, row, left, "/")
        overlay(canvas, row, right, "\\")
        for col in range(left + 1, right):
            if 0 <= col < len(canvas[row]) and (col + row + phase) % 2 == 0:
                canvas[row][col] = "."


def draw_walking_person(canvas: list[list[str]], row: int, col: int, phase: int) -> None:
    if phase % 2 == 0:
        pose = [" o/", "/| ", "/ \\"]
    else:
        pose = ["\\o ", " |\\", "/ \\"]
    for offset, line in enumerate(pose):
        overlay(canvas, row + offset, col, line)


def draw_person(canvas: list[list[str]], row: int, col: int) -> None:
    for offset, line in enumerate([" o ", "/|\\", "/ \\"]):
        overlay(canvas, row + offset, col, line)


def draw_small_person(canvas: list[list[str]], row: int, col: int) -> None:
    for offset, line in enumerate([" o ", " | ", "/ \\"]):
        overlay(canvas, row + offset, col, line)


@lru_cache(maxsize=8)
def _load_mascot_frames_cached(path: str) -> list[list[str]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    frames = data.get("frames", data) if isinstance(data, dict) else data
    if not isinstance(frames, list):
        raise ValueError("mascot frames must be a list, or an object with a frames list")

    normalized: list[list[str]] = []
    for frame in frames:
        if not isinstance(frame, list) or not all(isinstance(line, str) for line in frame):
            raise ValueError("each mascot frame must be a list of strings")
        normalized.append(frame)
    if not normalized:
        raise ValueError("mascot frames cannot be empty")
    return normalized


def animate_mascot(frames_path: str | None, width: int, interval: float, color: bool, cycles: int = 0) -> None:
    frame = 0
    frame_count = len(load_mascot_frames(frames_path))
    max_frames = frame_count * cycles if cycles > 0 else 0
    sys.stdout.write(ANSI_HIDE_CURSOR)
    try:
        while True:
            if max_frames and frame >= max_frames:
                break
            lines = render_mascot_frame(frame, width, frames_path=frames_path)
            frame += 1
            sys.stdout.write(ANSI_CLEAR_SCREEN)
            for line in lines:
                if color and sys.stdout.isatty():
                    sys.stdout.write(f"{MASCOT_COLOR}{line}{ANSI_RESET}\n")
                else:
                    sys.stdout.write(f"{line}\n")
            sys.stdout.flush()
            time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        sys.stdout.write(ANSI_SHOW_CURSOR + ANSI_RESET + "\n")
        sys.stdout.flush()


def print_frame(frames_path: str | None, frame: int, width: int, color: bool) -> None:
    lines = render_mascot_frame(frame, width, frames_path=frames_path)
    for line in lines:
        if color and sys.stdout.isatty():
            print(f"{MASCOT_COLOR}{line}{ANSI_RESET}")
        else:
            print(line)


def visual_width(text: str) -> int:
    wide_chars = {"F", "W"}
    return sum(2 if unicodedata.east_asian_width(char) in wide_chars else 1 for char in text)


def center_visual(text: str, width: int) -> str:
    padding = max(0, width - visual_width(text))
    left = padding // 2
    right = padding - left
    return (" " * left) + text + (" " * right)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render or preview the Task Decomposer terminal mascot.")
    parser.add_argument("--frames", help="JSON file with frames: [[line, ...], ...] or {\"frames\": [...]} ")
    parser.add_argument("--frame", type=int, help="Render one frame and exit")
    parser.add_argument("--width", type=int, default=shutil.get_terminal_size((40, 20)).columns, help="Render width")
    parser.add_argument("--fps", type=float, default=5.0, help="Animation frames per second")
    parser.add_argument("--cycles", type=int, default=0, help="Animation loops before exiting; 0 means forever")
    parser.add_argument("--animate", action="store_true", help="Loop the mascot animation; this is the default without --frame")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color")
    return parser.parse_args()


def main() -> None:
    configure_stdio()
    args = parse_args()
    interval = 1 / max(args.fps, 0.1)
    if args.frame is not None:
        print_frame(args.frames, args.frame, args.width, not args.no_color)
        return
    animate_mascot(args.frames, args.width, interval, not args.no_color, args.cycles)


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


if __name__ == "__main__":
    main()
