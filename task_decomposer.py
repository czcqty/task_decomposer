import sys
from pathlib import Path

from task_decomposer_app.bootstrap import ensure_cli_environment


ensure_cli_environment(Path(__file__).resolve().parent)

if "--gui-server" in sys.argv:
    from task_decomposer_app.gui_backend import main as gui_main
    if __name__ == "__main__":
        gui_main()
else:
    from task_decomposer_app.cli import main  # noqa: E402

    if __name__ == "__main__":
        main()
