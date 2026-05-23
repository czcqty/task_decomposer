import os
import json
from pathlib import Path
from task_decomposer_app.agent import TaskDecomposerAgent
from task_decomposer_app.config import PROVIDER_DEFAULTS, normalize_provider, resolve_provider, resolve_search_config
from task_decomposer_app.llm import LLMClient
from task_decomposer_app.models import SubAgentSpec
from task_decomposer_app.project import ProjectConfig, ProjectSubAgentConfig, load_project_config, project_root_for_create
from task_decomposer_app.runtime import (
    append_conversation,
    append_failure_log,
    append_run_log,
    clear_cache,
    elapsed_since,
    ensure_project_runtime_dirs,
    ensure_runtime_template,
    export_plan,
    is_cache_item_expired,
    list_cache_entries,
    load_agent_runtime_config,
    load_cached_search_results,
    load_conversation_context,
    load_runtime_project,
    load_user_runtime_config,
    resolve_runtime_provider,
    runtime_timestamp,
    save_user_runtime_config,
    save_cached_search_results,
    start_timer,
    UserRuntimeConfig,
    KEY_ROTATOR,
)
from task_decomposer_app.search import SearchService
from task_decomposer_app.skills import SkillRegistry


class CachedSearchService:
    def __init__(self, service: SearchService, runtime_root: str, project_name: str, username: str = "default"):
        self.service = service
        self.runtime_root = runtime_root
        self.project_name = project_name
        self.username = username
        self.config = service.config

    def search(self, query: str):
        cached = load_cached_search_results(
            self.runtime_root,
            self.username,
            self.project_name,
            self.config.provider,
            query,
            self.config.max_results,
        )
        if cached is not None:
            return cached
        results = self.service.search(query)
        save_cached_search_results(
            self.runtime_root,
            self.username,
            self.project_name,
            self.config.provider,
            query,
            self.config.max_results,
            results,
        )
        return results


def build_llm_client(args, runtime_main_config=None, user_config=None) -> LLMClient | None:
    if getattr(args, "local", False):
        return None

    config = resolve_runtime_provider(runtime_main_config, user_config) if runtime_main_config else None
    if config is None:
        config = resolve_provider(
            getattr(args, "provider", "auto"),
            getattr(args, "model", None),
            getattr(args, "base_url", None)
        )
    if config is None:
        if user_config is not None and user_config.name == "demo":
            return None
        raise RuntimeError("未检测到可用模型供应商配置。请先配置 API Key，或显式使用 --local 进入本地演示模式。")

    return LLMClient(config) if config else None


def build_search_service(args, project_name: str, user_config: UserRuntimeConfig | None = None) -> SearchService | None:
    if not getattr(args, "search", False):
        return None

    try:
        search_data = {}
        if user_config is not None and isinstance(user_config.raw_data, dict):
            search_data = user_config.raw_data.get("search", {})
        
        provider = getattr(args, "search_provider", None) or search_data.get("provider", "auto")
        if provider == "auto":
            if user_config is not None and user_config.name == "demo":
                provider = "duckduckgo"
            else:
                keys = search_data.get("api_keys", {}).get("tavily", [])
                provider = "tavily" if keys else "duckduckgo"

        max_results = getattr(args, "max_results", None)
        if max_results is None:
            max_results = int(search_data.get("max_results", 5))

        api_key = ""
        if provider == "tavily":
            keys = search_data.get("api_keys", {}).get("tavily", [])
            if keys:
                api_key = KEY_ROTATOR.get_key(user_config.name if user_config else "default", "tavily", keys)
            else:
                api_key = os.getenv("TAVILY_API_KEY") or os.getenv("SEARCH_API_KEY") or ""
                if not api_key:
                    if user_config is not None and user_config.name == "demo":
                        api_key = "demo_mock_search_key"
                    else:
                        raise RuntimeError("未配置 Tavily API Key。")

        from task_decomposer_app.config import SearchConfig
        config = SearchConfig(enabled=True, provider=provider, api_key=api_key, max_results=max_results)
    except Exception as error:
        raise RuntimeError(f"搜索配置不可用，已关闭联网搜索：{error}")

    return CachedSearchService(
        SearchService(config),
        getattr(args, "runtime_dir", "runtime"),
        project_name,
        username=(user_config.name if user_config else "default")
    )


def load_main_skills(registry: SkillRegistry, args, project: ProjectConfig | None) -> list:
    if project is None:
        return []

    return registry.load_project_agent_skills(str(project.root), "main", project.main_skills or None)


def load_sub_agents(
    registry: SkillRegistry,
    args,
    project: ProjectConfig | None,
    runtime_project=None,
    goal: str = "",
    user_config=None,
) -> list[SubAgentSpec]:
    specs: list[ProjectSubAgentConfig] = []
    if project is not None:
        specs.extend(project.sub_agents)
    specs.extend(parse_cli_sub_agents(getattr(args, "sub_agent", [])))

    specs = filter_sub_agent_specs(specs, getattr(args, "sub_agent_mode", "all"), goal)

    sub_agents: list[SubAgentSpec] = []
    for spec in specs:
        runtime_config = runtime_project.agents.get(spec.name) if runtime_project else None
        skills = []
        if project is not None:
            skills = registry.load_project_agent_skills(str(project.root), spec.name, spec.skills or None)

        model_config = None
        if runtime_config and not getattr(args, "local", False):
            model_config = resolve_runtime_provider(runtime_config, user_config)

        sub_agents.append(
            SubAgentSpec(
                name=spec.name,
                role=runtime_config.role if runtime_config and runtime_config.role else spec.role,
                skills=skills,
                model_config=model_config,
                provider=runtime_config.provider if runtime_config else "",
            )
        )
    return sub_agents


def filter_sub_agent_specs(
    specs: list[ProjectSubAgentConfig],
    mode: str,
    goal: str,
) -> list[ProjectSubAgentConfig]:
    if mode == "all":
        return specs
    if mode == "risk-only":
        return [spec for spec in specs if is_risk_agent(spec)]
    if mode == "auto":
        selected = []
        for spec in specs:
            text = f"{spec.name} {spec.role} {' '.join(spec.skills)}"
            if any(word in goal for word in ["风险", "验收", "依赖", "检查", "质量"]):
                if is_risk_agent(spec):
                    selected.append(spec)
            if any(word in goal for word in ["项目", "开发", "实现", "MVP", "里程碑", "做一个"]):
                if has_any(text, ["执行", "execution", "MVP", "里程碑"]):
                    selected.append(spec)
            if any(word in goal for word in ["用户", "体验", "产品", "场景", "价值"]):
                if has_any(text, ["用户", "价值", "体验", "user-value"]):
                    selected.append(spec)
        if not selected:
            return specs
        deduped = []
        seen = set()
        for spec in selected:
            if spec.name not in seen:
                deduped.append(spec)
                seen.add(spec.name)
        return deduped
    return specs


def is_risk_agent(spec: ProjectSubAgentConfig) -> bool:
    text = f"{spec.name} {spec.role} {' '.join(spec.skills)}"
    return has_any(text, ["风险", "审查", "验收", "risk-review"])


def has_any(text: str, words: list[str]) -> bool:
    return any(word in text for word in words)


def parse_cli_sub_agents(values: list[str]) -> list[ProjectSubAgentConfig]:
    specs = []
    for value in values:
        if ":" in value:
            name, role = value.split(":", 1)
        else:
            name, role = value, ""
        name = name.strip()
        if name:
            specs.append(ProjectSubAgentConfig(name=name, role=role.strip()))
    return specs


def build_conversation_context(args, project: ProjectConfig | None, project_name: str | None = None) -> str:
    conversation_id = getattr(args, "conversation", "")
    if not conversation_id:
        return ""
    resolved_project_name = project.name if project else (project_name or "default")
    username = getattr(args, "user", "demo")
    history_context = load_conversation_context(getattr(args, "runtime_dir", "runtime"), username, resolved_project_name, conversation_id)
    if not history_context:
        return ""
    return f"以下是本次多轮修改的历史上下文，请基于它继续修改计划：\n{history_context}"


def run_token_count(llm_client: LLMClient | None, result, goal: str, context: str) -> int:
    if llm_client is not None and getattr(llm_client, "total_tokens", 0) > 0:
        return int(llm_client.total_tokens)
    return estimate_result_tokens(result, goal, context)


def estimate_result_tokens(result, goal: str, context: str) -> int:
    parts = [goal, context, result.plan.goal, result.plan.next_step]
    for task in result.plan.tasks:
        parts.extend([task.title, task.action, task.output])
    for run in result.sub_agent_runs:
        parts.extend([run.name, run.role, run.plan.goal, run.plan.next_step])
        for task in run.plan.tasks:
            parts.extend([task.title, task.action, task.output])
    text = "\n".join(part for part in parts if part)
    return max(1, int(len(text) / 3))


def setup_user_config(args, prompt_api_key_callback=None, force: bool = False) -> None:
    config_dir = getattr(args, "config_dir", "config")
    user_name = getattr(args, "user", "").strip()
    if not user_name:
        if prompt_api_key_callback is None:
            return
        user_name = prompt_api_key_callback("user_name", "请输入用户名称：").strip()
        args.user = user_name
    if not user_name:
        return

    config = load_user_runtime_config(config_dir, user_name) or UserRuntimeConfig(name=user_name)
    save_user_runtime_config(config_dir, config)


def default_api_key_env(provider: str) -> str:
    defaults = PROVIDER_DEFAULTS[provider]
    return defaults["api_key_envs"][0]


def required_user_api_key_envs(args) -> list[str]:
    project_name = getattr(args, "project", "") or (Path(args.project_dir).name if getattr(args, "project_dir", None) else "")
    username = getattr(args, "user", "demo")
    user_config_root = Path(getattr(args, "config_dir", "config")) / "user" / username
    project_root = user_config_root / "project" / project_name
    runtime_project = load_runtime_project(project_name, project_root)
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


def validate_project(
    args,
    project_ref: str | None,
    require_api_keys: bool = False,
) -> list[tuple[str, str]]:
    checks: list[tuple[str, str]] = []
    if not project_ref:
        return [("ERROR", "请通过 --project 或 --project-dir 指定项目")]

    config_dir = getattr(args, "config_dir", "config")
    runtime_dir = getattr(args, "runtime_dir", "runtime")
    username = getattr(args, "user", "demo")

    user_config = None
    if username == "demo":
        checks.append(("OK", "演示用户 'demo' 激活 (唯一免密特权沙箱)"))
    else:
        try:
            user_config = load_user_runtime_config(config_dir, username)
            if user_config is None:
                return [("ERROR", f"用户 '{username}' 配置文件不存在。可运行 --setup-user 初始化用户。")]
            checks.append(("OK", f"用户配置文件存在：{user_config_path(config_dir, username)}"))
            
            has_keys = False
            for provider, keys in user_config.api_keys.items():
                if keys and any(k.strip() for k in keys if k.strip()):
                    has_keys = True
                    checks.append(("OK", f"已配置 {provider} 密钥池，包含 {len(keys)} 个密钥"))
            if not has_keys and require_api_keys:
                return [("ERROR", f"用户 '{username}' 未配置任何 API Key，请先通过 --setup-user 配置")]
        except Exception as error:
            return [("ERROR", f"加载用户配置失败：{error}")]

    try:
        user_config_root = Path(config_dir) / "user" / username
        project = load_project_config(project_ref, str(user_config_root))
    except Exception as error:
        return [("ERROR", f"加载项目 config 失败：{error}")]

    if project is None:
        return [("ERROR", "项目 config 不可用")]

    checks.append(("OK", f"项目配置/定义目录：{project.root}"))
    main_root = project.root / "main"
    if not main_root.exists():
        checks.append(("ERROR", f"缺少主 agent 定义目录：{main_root}"))
    else:
        main_config_path = main_root / "config.json"
        if not main_config_path.exists():
            checks.append(("ERROR", f"缺少主 agent 配置文件：{main_config_path}"))
        else:
            checks.append(("OK", f"主 agent 配置文件：{main_config_path}"))

    for sub_agent in project.sub_agents:
        agent_dir = project.root / sub_agent.name
        config_path = agent_dir / "config.json"
        if not config_path.exists():
            checks.append(("ERROR", f"子 Agent {sub_agent.name} 缺少配置文件：{config_path}"))
        else:
            checks.append(("OK", f"子 Agent {sub_agent.name} 配置文件：{config_path}"))

        if sub_agent.skills:
            checks.append(("OK", f"子 Agent {sub_agent.name} 包含技能：{', '.join(sub_agent.skills)}"))
        else:
            checks.append(("WARN", f"子 Agent {sub_agent.name} 没有可用技能目录/SKILL.md"))

    if getattr(args, "search", False):
        if username == "demo":
            checks.append(("OK", "演示模式联网搜索：DuckDuckGo (无需 API Key)"))
        else:
            search_data = user_config.raw_data.get("search", {}) if user_config else {}
            provider = search_data.get("provider", "auto")
            keys = search_data.get("api_keys", {}).get("tavily", [])
            if provider == "tavily" and not keys and not os.getenv("TAVILY_API_KEY") and not os.getenv("SEARCH_API_KEY"):
                checks.append(("WARN", "联网搜索使用 Tavily 但未配置 API Key，将无法正常发起公网搜索"))
            else:
                checks.append(("OK", f"联网搜索配置：provider={provider} max_results={search_data.get('max_results', 5)}"))

    for dirname in ["cache", "conversation", "log", "output"]:
        path = Path(runtime_dir) / "user" / username / "project" / project.name / dirname
        if path.exists():
            checks.append(("OK", f"动态运行态目录存在：{path}"))
        else:
            checks.append(("WARN", f"动态运行态目录不存在：{path}，正常运行时会自动创建"))

    return checks


def run_core_decomposition(
    args,
    goal: str,
    status_callback=None,
    prompt_api_key_callback=None,
) -> dict:
    """执行核心拆解流程，返回结构化字典数据，并通过 status_callback 发送状态事件"""
    run_id = runtime_timestamp()
    timer = start_timer()
    
    if not goal:
        raise ValueError("输入目标不能为空。")

    config_dir = getattr(args, "config_dir", "config")
    project_ref = getattr(args, "project_dir", None) or getattr(args, "project", None)
    project_name = getattr(args, "project", "demo") or "demo"
    runtime_dir = getattr(args, "runtime_dir", "runtime")
    username = getattr(args, "user", "demo") or "demo"

    if username == "demo":
        setattr(args, "local", True)

    if status_callback:
        status_callback("preparing", "正在准备运行上下文并校验配置...")

    user_config = load_user_runtime_config(config_dir, username) or UserRuntimeConfig(name=username)
    if username != "demo" and not getattr(args, "local", False):
        has_keys = False
        for keys in user_config.api_keys.values():
            if keys and any(k.strip() for k in keys):
                has_keys = True
        if not has_keys:
            raise RuntimeError(f"用户 '{username}' 未配置任何 API Key，请先配置。")
        
        checks = validate_project(args, project_ref, require_api_keys=True) if project_ref else []
        blocking = [msg for lvl, msg in checks if lvl == "ERROR"]
        if blocking:
            raise RuntimeError(f"模型配置未通过校验: {blocking[0]}")

    if status_callback:
        status_callback("loading", "正在加载项目技能与运行上下文...")

    registry = SkillRegistry(config_dir)
    user_config_root = Path(config_dir) / "user" / username
    project = load_project_config(project_ref, str(user_config_root)) if project_ref else None
    
    project_root = user_config_root / "project" / project_name
    runtime_project = load_runtime_project(project_name, project_root)

    llm_client = build_llm_client(args, runtime_project.main if runtime_project else None, user_config)
    main_skills = load_main_skills(registry, args, project)
    sub_agents = load_sub_agents(registry, args, project, runtime_project, goal, user_config)
    search_service = build_search_service(args, project_name, user_config)

    agent = TaskDecomposerAgent(
        llm_client=llm_client,
        search_service=search_service,
        skills=main_skills,
        sub_agents=sub_agents,
    )

    context = build_conversation_context(args, project, project_name)
    clarify_questions = []

    if not getattr(args, "skip_clarify", False):
        if status_callback:
            status_callback("clarifying", "正在分析需求清晰度...")
        try:
            questions = agent.clarify(goal)
            if questions:
                clarify_questions = questions
        except Exception as error:
            raise RuntimeError(f"模型需求澄清失败: {error}")

    if status_callback:
        status_callback("synthesizing", "正在合成并分析任务分解树...")

    try:
        result = agent.run(goal, context=context, search_query=getattr(args, "search_query", ""))
    except Exception as error:
        raise RuntimeError(f"模型任务拆解与合并失败: {error}")

    elapsed_seconds = elapsed_since(timer)
    token_count = run_token_count(llm_client, result, goal, context)
    token_note = " estimated" if llm_client is None or getattr(llm_client, "total_tokens", 0) <= 0 else ""

    mode = "local" if agent.llm_client is None else "model"
    if getattr(args, "conversation", ""):
        append_conversation(runtime_dir, username, project_name, args.conversation, goal, context, result)
    exported = export_plan(runtime_dir, username, project_name, result, run_id=run_id)
    append_run_log(runtime_dir, username, project_name, run_id, goal, result, elapsed_seconds, mode=mode)

    tasks_list = []
    for t in result.plan.tasks:
        tasks_list.append({
            "title": t.title,
            "action": t.action,
            "output": t.output
        })

    plan_data = {
        "goal": result.plan.goal,
        "tasks": tasks_list,
        "next_step": result.plan.next_step
    }

    return {
        "elapsed": elapsed_seconds,
        "tokens": token_count,
        "token_note": token_note,
        "plan": plan_data,
        "questions": clarify_questions,
        "markdown_path": str(exported.get("markdown", ""))
    }


def get_default_options() -> dict:
    return {
        "local": False,
        "provider": "auto",
        "model": None,
        "base_url": None,
        "skip_clarify": False,
        "user": "demo",
        "project": "demo",
        "project_dir": None,
        "sub_agent": [],
        "sub_agent_mode": "all",
        "runtime_dir": "runtime",
        "conversation": "default",
        "search": True,
        "search_provider": "auto",
        "search_query": "",
        "max_results": 5,
        "feedback": "",
    }


class DecomposerArgs:
    def __init__(self, **kwargs):
        defaults = get_default_options()
        for k, v in defaults.items():
            setattr(self, k, v)
        for k, v in kwargs.items():
            if v is not None:
                if k in {"local", "skip_clarify", "search"}:
                    setattr(self, k, bool(v))
                elif k in {"max_results"}:
                    setattr(self, k, int(v))
                elif k in {"sub_agent"}:
                    setattr(self, k, list(v) if isinstance(v, (list, tuple)) else [v])
                else:
                    if isinstance(v, bool):
                        setattr(self, k, v)
                    else:
                        setattr(self, k, str(v))
            else:
                if k not in defaults:
                    setattr(self, k, None)
