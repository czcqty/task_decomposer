import importlib.util
import os
import subprocess
import sys
from pathlib import Path


REQUIREMENT_IMPORTS = {
    "python-dotenv": "dotenv",
}


def ensure_cli_environment(project_root: Path) -> None:
    venv_dir = project_root / ".venv"
    try:
        ensure_project_venv(venv_dir)
        reexec_in_venv(venv_dir)
        ensure_requirements(project_root, venv_dir)
    except Exception as error:
        print_bootstrap_failure(error)
        raise SystemExit(1) from error


def ensure_project_venv(venv_dir: Path) -> None:
    python_path = venv_python(venv_dir)
    if python_path.exists():
        return
    completed = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(command_failure_message("创建虚拟环境失败", completed.stdout))


def reexec_in_venv(venv_dir: Path) -> None:
    python_path = venv_python(venv_dir)
    if is_running_in_venv(venv_dir):
        return

    os.environ["VIRTUAL_ENV"] = str(venv_dir.resolve())
    os.environ["PATH"] = str(python_path.parent) + os.pathsep + os.environ.get("PATH", "")
    if os.name == "nt":
        completed = subprocess.run([str(python_path), *sys.argv])
        raise SystemExit(completed.returncode)
    os.execv(str(python_path), [str(python_path), *sys.argv])


def is_running_in_venv(venv_dir: Path) -> bool:
    prefix = Path(sys.prefix).resolve()
    base_prefix = Path(getattr(sys, "base_prefix", sys.prefix)).resolve()
    return prefix == venv_dir.resolve() and prefix != base_prefix


def ensure_requirements(project_root: Path, venv_dir: Path) -> None:
    requirements_path = project_root / "requirements.txt"
    if not requirements_path.exists():
        return

    missing = missing_requirements(requirements_path)
    if not missing:
        return

    python_path = venv_python(venv_dir)
    completed = subprocess.run(
        [str(python_path), "-m", "pip", "install", "-r", str(requirements_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(command_failure_message("安装依赖失败", completed.stdout))

    still_missing = missing_requirements(requirements_path)
    if still_missing:
        raise RuntimeError(f"依赖安装后仍无法导入：{', '.join(still_missing)}")


def missing_requirements(requirements_path: Path) -> list[str]:
    missing = []
    for package_name in iter_requirement_names(requirements_path):
        import_name = REQUIREMENT_IMPORTS.get(package_name, package_name.replace("-", "_"))
        if importlib.util.find_spec(import_name) is None:
            missing.append(package_name)
    return missing


def iter_requirement_names(requirements_path: Path) -> list[str]:
    names = []
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        name = line
        for marker in ["==", ">=", "<=", "~=", "!=", ">", "<", "["]:
            if marker in name:
                name = name.split(marker, 1)[0]
        if name:
            names.append(name.strip().lower())
    return names


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def command_failure_message(title: str, output: str) -> str:
    output = output.strip()
    if not output:
        return title
    return f"{title}：\n{output}"


def missing_dependency_message(package: str | None = None) -> str:
    platform_name, commands = dependency_setup_instructions()
    command_text = "\n".join(f"  {command}" for command in commands)
    package_note = f"未能自动安装 {package} 依赖。" if package else "未能自动完成虚拟环境或依赖安装。"
    return (
        f"{package_note}\n"
        f"当前平台：{platform_name}\n"
        "请手动创建并启用虚拟环境，再在虚拟环境里安装依赖：\n"
        f"{command_text}"
    )


def print_bootstrap_failure(error: Exception) -> None:
    print("CLI 自动环境准备失败：")
    print(error)
    print()
    print(missing_dependency_message())


def dependency_setup_instructions() -> tuple[str, list[str]]:
    if sys.platform.startswith("win"):
        return (
            "Windows",
            [
                "py -m venv .venv",
                ".venv\\Scripts\\Activate.ps1",
                "python -m pip install -r requirements.txt",
            ],
        )

    if sys.platform == "darwin":
        return (
            "macOS",
            [
                "python3 -m venv .venv",
                "source .venv/bin/activate",
                "python -m pip install -r requirements.txt",
            ],
        )

    if sys.platform.startswith("linux"):
        distro = detect_linux_distro()
        distro_note = distro["pretty_name"] or distro["id"] or "Linux"
        return distro_note, linux_dependency_commands(distro)

    return (
        sys.platform,
        [
            "python -m venv .venv",
            "source .venv/bin/activate",
            "python -m pip install -r requirements.txt",
        ],
    )


def detect_linux_distro() -> dict[str, str]:
    data = {"id": "", "id_like": "", "pretty_name": ""}
    os_release = Path("/etc/os-release")
    if not os_release.exists():
        return data

    for raw_line in os_release.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip().lower()
        value = value.strip().strip('"')
        if key == "id":
            data["id"] = value.lower()
        elif key == "id_like":
            data["id_like"] = value.lower()
        elif key == "pretty_name":
            data["pretty_name"] = value
    return data


def linux_dependency_commands(distro: dict[str, str]) -> list[str]:
    distro_ids = {part for part in [distro["id"], *distro["id_like"].split()] if part}
    commands: list[str] = []

    if distro_ids & {"debian", "ubuntu", "linuxmint", "pop"}:
        commands.append("sudo apt install python3-full")
    elif distro_ids & {"fedora", "rhel", "centos", "rocky", "almalinux"}:
        commands.append("sudo dnf install python3 python3-pip")
    elif distro_ids & {"arch", "manjaro"}:
        commands.append("sudo pacman -S python python-pip")
    elif distro_ids & {"opensuse", "suse"}:
        commands.append("sudo zypper install python3 python3-pip")

    commands.extend(
        [
            "python3 -m venv .venv",
            "source .venv/bin/activate",
            "python -m pip install -r requirements.txt",
        ]
    )
    return commands
