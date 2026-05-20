import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "task_decomposer.py"


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, "-B", str(ENTRY), *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        print(result.stdout)
        raise SystemExit(result.returncode)
    return result


def main() -> None:
    run_command(["--project", "demo", "--validate-project"])

    with tempfile.TemporaryDirectory(prefix="task-decomposer-smoke-") as runtime_dir:
        runtime = str(Path(runtime_dir))
        run_command(
            [
                "我想做一个任务拆解Agent",
                "--project",
                "demo",
                "--runtime-dir",
                runtime,
                "--dry-run",
            ]
        )

        if (Path(runtime) / "output").exists():
            raise SystemExit("dry-run should not create runtime output directories")

        run_command(
            [
                "我想做一个任务拆解Agent",
                "--project",
                "demo",
                "--runtime-dir",
                runtime,
                "--local",
                "--skip-clarify",
            ]
        )

        output_dir = Path(runtime) / "output" / "demo"
        log_path = Path(runtime) / "log" / "demo" / "runs.jsonl"
        if not list(output_dir.glob("*.md")) or not list(output_dir.glob("*.json")):
            raise SystemExit("local demo did not export markdown/json plans")
        if not log_path.exists():
            raise SystemExit("local demo did not write runs.jsonl")

        run_command(["--project", "demo", "--runtime-dir", runtime, "--cache-list"])
        run_command(["--project", "demo", "--runtime-dir", runtime, "--cache-clear"])

    print("smoke test passed")


if __name__ == "__main__":
    main()
