"""诊断脚本：验证 VT 处理修复。
运行方式：python scripts/debug_input.py
"""
import os
import sys
import shutil

# 先运行 cli 的 configure_stdio 来启用 VT
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from task_decomposer_app.cli import configure_stdio
configure_stdio()


def check_terminal():
    print("=== 终端环境诊断 ===")
    print(f"Python 版本: {sys.version}")
    print(f"操作系统: {os.name} / {sys.platform}")
    print(f"stdout.encoding: {sys.stdout.encoding}")
    cols, lines = shutil.get_terminal_size((80, 24))
    print(f"终端尺寸: {cols} 列 x {lines} 行")

    # 检查 VT 处理状态
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)
            mode = wintypes.DWORD()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            vt_enabled = bool(mode.value & 0x0004)
            print(f"VT 处理已启用: {vt_enabled} (console mode = 0x{mode.value:04x})")
        except Exception as e:
            print(f"VT 检测失败: {e}")
    print()

    # 测试 VT 转义序列
    print("=== VT 转义序列测试 ===")
    sys.stdout.write("测试清除到行尾: [AAA")
    sys.stdout.write("\033[K")
    sys.stdout.write("]\n")
    sys.stdout.flush()
    print("(如果上面显示 [] 说明 VT 清除正常)")
    print("(如果上面显示 [AAA] 说明 VT 清除不工作)")
    print()

    sys.stdout.write("测试光标移动: [ABCDE")
    sys.stdout.write("\033[3D")
    sys.stdout.write("X")
    sys.stdout.write("\033[K")
    sys.stdout.write("]\n")
    sys.stdout.flush()
    print("(如果上面显示 [ABX] 说明光标移动正常)")
    print()

    # 测试颜色
    sys.stdout.write("\033[97m亮白色\033[0m  ")
    sys.stdout.write("\033[90m灰色\033[0m  ")
    sys.stdout.write("\033[38;5;217m粉色\033[0m\n")
    sys.stdout.flush()
    print("(如果上面有不同颜色，说明颜色正常)")
    print()


def test_input():
    if os.name != "nt" or not sys.stdin.isatty():
        print("跳过 msvcrt 输入测试")
        return

    import msvcrt
    import time

    print("=== 输入测试（含中文）===")
    print("请输入一些字符（包括中文），按 Enter 结束：")
    buffer = []
    cursor = 0
    prompt = "test> "

    def redraw():
        text = "".join(buffer)
        line = prompt + text
        sys.stdout.write(f"\r\033[97m{line}\033[0m\033[K")
        # 定位光标
        import unicodedata
        suffix = "".join(buffer[cursor:])
        w = sum(2 if unicodedata.east_asian_width(c) in {"F","W"} else 1 for c in suffix)
        if w:
            sys.stdout.write(f"\033[{w}D")
        sys.stdout.flush()

    redraw()
    while True:
        if not msvcrt.kbhit():
            time.sleep(0.03)
            continue
        char = msvcrt.getwch()
        if char in {"\r", "\n"}:
            sys.stdout.write("\033[0m\n")
            sys.stdout.flush()
            break
        if char == "\x03":
            print("\n中断")
            return
        if char in {"\b", "\x7f"}:
            if cursor > 0:
                buffer.pop(cursor - 1)
                cursor -= 1
        elif char == "\x00" or char == "\xe0":
            key = msvcrt.getwch()
            if key == "K" and cursor > 0:
                cursor -= 1
            elif key == "M" and cursor < len(buffer):
                cursor += 1
            else:
                continue
        else:
            buffer.insert(cursor, char)
            cursor += 1
        redraw()

    result = "".join(buffer)
    print(f"你输入的内容: [{result}]")
    print(f"字符数: {len(result)}")


if __name__ == "__main__":
    check_terminal()
    test_input()
    print("\n=== 诊断完成 ===")
