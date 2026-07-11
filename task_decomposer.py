import sys
from pathlib import Path

from task_decomposer_app.bootstrap import ensure_cli_environment

ensure_cli_environment(Path(__file__).resolve().parent)

if "--gui-server" in sys.argv:
    from task_decomposer_app.gui_backend import main as gui_main
    if __name__ == "__main__":
        gui_main()
else:
    print("CLI 交互式终端已移除。请通过 GUI 客户端使用 Task Decomposer。")
    print("启动方式：运行 gui_client 编译产物，或使用 --gui-server 参数启动后端引擎。")
    sys.exit(1)
