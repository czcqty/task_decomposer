from pathlib import Path

from task_decomposer_app.bootstrap import ensure_cli_environment


ensure_cli_environment(Path(__file__).resolve().parent)

from task_decomposer_app.cli import main  # noqa: E402


if __name__ == "__main__":
    main()
