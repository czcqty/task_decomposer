"""CLI 辅助函数模块。

仅保留 gui_backend.py 和启动流程所需的函数：
  - parse_args, apply_user_config
  - auto_initialize_user_scaffold, repair_user_config_if_damaged, login_verify_password
  - setup_user_config, prompt_provider, default_api_key_env, required_user_api_key_envs
  - configure_stdio, _enable_windows_vt_processing

原有的交互式终端界面、ANSI 渲染、动画等代码已移除。
"""

import argparse
import getpass
import json
import os
import shutil
import sys
from pathlib import Path

from task_decomposer_app.config import PROVIDER_DEFAULTS, normalize_provider
from task_decomposer_app.runtime import (
    load_runtime_project,
    load_user_runtime_config,
    save_user_runtime_config,
    UserRuntimeConfig,
)
from task_decomposer_app.terminal_input import read_text_input

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


# ────────────────────────────────────────────────────────────────
# 参数解析
# ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="任务拆解型 Agent（Task Decomposer）")
    parser.add_argument("goal", nargs="*", help="需要拆解的目标")
    parser.add_argument("--provider", default=os.getenv("LLM_PROVIDER", "auto"), help="模型供应商")
    parser.add_argument("--model", help="覆盖默认模型名称")
    parser.add_argument("--base-url", help="OpenAI 兼容接口的 Base URL")
    parser.add_argument("--skip-clarify", action="store_true", help="跳过模糊需求澄清")
    parser.add_argument("--local", action="store_true", help="强制本地演示模式")
    parser.add_argument("--user", default=os.getenv("TASK_DECOMPOSER_USER") or os.getenv("USERNAME") or os.getenv("USER"), help="用户级配置名称")
    parser.add_argument("--setup-user", action="store_true", help="创建或更新用户级 API Key 配置后退出")
    parser.add_argument("--global-skill", action="append", default=[], help="加载全局 Skill")
    parser.add_argument("--config-dir", dest="config_dir", default="config", help="配置根目录")
    parser.add_argument("--skills-dir", dest="config_dir", help=argparse.SUPPRESS)
    parser.add_argument("--project", default="demo", help="项目名")
    parser.add_argument("--project-dir", default=None, help="项目配置目录路径")
    parser.add_argument("--init-project", help="创建项目配置模板")
    parser.add_argument("--list-project-skills", action="store_true", help="列出项目技能后退出")
    parser.add_argument("--sub-agent", action="append", default=[], help="临时追加 sub-agent")
    parser.add_argument("--sub-agent-mode", choices=["all", "risk-only", "auto"], default=os.getenv("SUB_AGENT_MODE", "all"), help="sub-agent 运行策略")
    parser.add_argument("--runtime-dir", default=os.getenv("RUNTIME_DIR", "runtime"), help="运行态目录")
    parser.add_argument("--init-runtime", action="store_true", help="初始化运行态目录后退出")
    parser.add_argument("--conversation", default=os.getenv("CONVERSATION_ID", ""), help="对话 ID")
    parser.add_argument("--feedback", default="", help="本轮修改意见")
    parser.add_argument("--validate-project", action="store_true", help="校验项目配置后退出")
    parser.add_argument("--dry-run", action="store_true", help="预览运行配置后退出")
    parser.add_argument("--cache-list", action="store_true", help="列出搜索缓存后退出")
    parser.add_argument("--cache-clear", action="store_true", help="清空搜索缓存后退出")
    parser.add_argument("--search", action="store_true", help="启用联网搜索")
    parser.add_argument("--search-provider", default=os.getenv("SEARCH_PROVIDER", "auto"), help="搜索供应商")
    parser.add_argument("--search-query", default="", help="覆盖搜索词")
    parser.add_argument("--max-results", type=int, default=int(os.getenv("SEARCH_MAX_RESULTS", "5")), help="最大搜索结果数")
    parser.add_argument("--gui-server", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


# ────────────────────────────────────────────────────────────────
# stdio 配置
# ────────────────────────────────────────────────────────────────

def configure_stdio() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
    if os.name == "nt":
        _enable_windows_vt_processing()


def _enable_windows_vt_processing() -> None:
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


# ────────────────────────────────────────────────────────────────
# 用户配置管理
# ────────────────────────────────────────────────────────────────

def apply_user_config(config: UserRuntimeConfig) -> None:
    for env_name, api_key in config.api_keys.items():
        if not api_key:
            continue
        val = api_key[0] if isinstance(api_key, list) else api_key
        if val:
            os.environ[env_name] = str(val)
    if config.provider:
        os.environ["LLM_PROVIDER"] = config.provider
    if config.model:
        os.environ["MODEL"] = config.model
    if config.base_url:
        os.environ["BASE_URL"] = config.base_url


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


def auto_initialize_user_scaffold(args: argparse.Namespace) -> bool:
    config_dir = Path(args.config_dir)
    user_dir = config_dir / "user" / args.user
    if user_dir.exists():
        return True

    is_interactive = sys.stdin.isatty()

    if is_interactive:
        try:
            choice = read_text_input(f"[提示] 未检测到用户 '{args.user}' 的配置。是否需要为您创建一个新用户？(y/n): ").strip().lower()
            if choice not in ("y", "yes"):
                print("已取消创建新用户。您可以重新运行并指定 --user demo 进入演示模式。")
                return False
        except (KeyboardInterrupt, EOFError):
            print()
            return False

    demo_dir = config_dir / "user" / "demo"
    if not demo_dir.exists():
        print(f"错误：模板用户 'demo' 目录不存在于：{demo_dir}")
        return False

    try:
        shutil.copytree(demo_dir, user_dir)
        config_path = user_dir / "config.json"

        chosen_user = args.user
        password = ""

        if is_interactive:
            try:
                custom_name = read_text_input(f"请输入您的自定义用户名 [默认: {args.user}]: ").strip()
                if custom_name:
                    chosen_user = custom_name
                    new_user_dir = config_dir / "user" / chosen_user
                    if new_user_dir.exists():
                        print(f"用户 '{chosen_user}' 已存在，将直接使用现有用户目录。")
                        shutil.rmtree(user_dir)
                        args.user = chosen_user
                        return True
                    else:
                        user_dir.rename(new_user_dir)
                        user_dir = new_user_dir
                        config_path = user_dir / "config.json"
                        args.user = chosen_user

                password = getpass.getpass("请输入您的账户密码（可选，直接回车则不使用密码）：").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return False

        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["name"] = chosen_user
                data["password"] = password
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"保存配置文件时更新字段失败：{e}")

        print(f"成功为用户 '{chosen_user}' 初始化配置与 demo 项目脚手架！")

        if is_interactive:
            choice_keys = read_text_input("是否现在配置您的 API Key 密钥池？(y/n): ").strip().lower()
            if choice_keys in ("y", "yes"):
                setup_user_config(args, force=True)
            else:
                print("已跳过 API Key 配置。您可以使用 --local 运行本地演示模式，或稍后运行 --setup-user 进行配置。")
        return True
    except Exception as e:
        print(f"初始化用户目录失败：{e}")
        return False


def login_verify_password(args: argparse.Namespace) -> bool:
    config_dir = Path(args.config_dir)
    config_path = config_dir / "user" / args.user / "config.json"
    if not config_path.exists():
        return True

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        password = str(data.get("password") or "")
    except Exception:
        return True

    if not password:
        return True

    is_interactive = sys.stdin.isatty()

    if not is_interactive:
        try:
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            entered = simpledialog.askstring(
                "身份校验 - Task Decomposer",
                f"请输入用户 '{args.user}' 的密码以登录：",
                show='*'
            )
            root.destroy()

            if entered == password:
                return True
            else:
                sys.stderr.write("密码校验失败，登录拒绝。\n")
                sys.stderr.flush()
                return False
        except Exception as e:
            sys.stderr.write(f"GUI 密码校验组件加载异常：{e}\n")
            sys.stderr.flush()
            return False
    else:
        try:
            for attempt in range(3):
                entered = getpass.getpass(f"请输入用户 '{args.user}' 的密码以登录：").strip()
                if entered == password:
                    print("登录成功！")
                    return True
                else:
                    print(f"密码错误！（剩余尝试次数：{2 - attempt}）")
            print("尝试次数过多，登录失败！")
            return False
        except (KeyboardInterrupt, EOFError):
            print()
            return False


def repair_user_config_if_damaged(args: argparse.Namespace) -> bool:
    config_dir = Path(args.config_dir)
    user_dir = config_dir / "user" / args.user
    if not user_dir.exists():
        return True

    demo_project_dir = user_dir / "project" / "demo"
    config_path = user_dir / "config.json"

    is_damaged = False
    reasons = []

    if not config_path.exists():
        is_damaged = True
        reasons.append("缺少主 config.json 配置文件")
    if not demo_project_dir.exists() or not (demo_project_dir / "main").exists():
        is_damaged = True
        reasons.append("缺少内置的 demo 项目脚手架目录")

    if not is_damaged:
        return True

    print(f"\n[警告] 检测到用户 '{args.user}' 的配置受损：{', '.join(reasons)}")

    is_interactive = sys.stdin.isatty()
    if is_interactive:
        try:
            choice = read_text_input("是否执行受损配置自动修复流程以补齐缺失的 demo 样板？(y/n): ").strip().lower()
            if choice not in ("y", "yes"):
                print("已取消修复，但部分功能可能无法运行。")
                return True
        except (KeyboardInterrupt, EOFError):
            print()
            return True

    demo_template_dir = config_dir / "user" / "demo"
    if not demo_template_dir.exists():
        print(f"错误：模板用户 'demo' 目录不存在，无法进行修复。")
        return False

    try:
        if not config_path.exists():
            shutil.copy2(demo_template_dir / "config.json", config_path)
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["name"] = args.user
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("✔ 已恢复主配置文件 config.json")

        if not demo_project_dir.exists() or not (demo_project_dir / "main").exists():
            demo_project_dir.parent.mkdir(parents=True, exist_ok=True)
            if demo_project_dir.exists():
                shutil.rmtree(demo_project_dir)
            shutil.copytree(demo_template_dir / "project" / "demo", demo_project_dir)
            pristine_dir = user_dir / "project" / "demo_pristine"
            if not pristine_dir.exists():
                shutil.copytree(demo_template_dir / "project" / "demo_pristine", pristine_dir)
            print("✔ 已恢复受损的 demo 样板项目脚手架")

        print("✔ 用户配置与脚手架修复完成！\n")
        return True
    except Exception as e:
        print(f"修复用户目录失败：{e}")
        return False


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
