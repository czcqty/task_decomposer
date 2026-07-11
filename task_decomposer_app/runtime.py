import json
import hashlib
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from task_decomposer_app.config import build_provider_config
from task_decomposer_app.models import AgentRunResult, ProviderConfig, SearchResult
from task_decomposer_app.utils import first_env


SEARCH_CACHE_TTL_SECONDS = 24 * 60 * 60
CACHE_LOCK = threading.Lock()


@dataclass
class AgentRuntimeConfig:
    name: str
    role: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key_env: str = ""
    api_key_envs: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class RuntimeProjectConfig:
    project_name: str
    root: Path
    main: AgentRuntimeConfig | None = None
    agents: dict[str, AgentRuntimeConfig] = field(default_factory=dict)


@dataclass
class UserRuntimeConfig:
    name: str
    provider: str = ""
    api_keys: dict[str, list[str]] = field(default_factory=dict)
    model: str = ""
    base_url: str = ""
    password: str = ""
    raw_data: dict = field(default_factory=dict)


class KeyRotator:
    def __init__(self):
        self._lock = threading.Lock()

    def _get_state_path(self, username: str) -> Path:
        return Path("runtime") / "user" / username / "key_rotation_state.json"

    def get_key(self, username: str, provider: str, keys: list[str]) -> str:
        if not keys:
            raise RuntimeError(f"用户 {username} 未配置 {provider} 的 API Key。")
        
        if len(keys) == 1:
            return keys[0]

        with self._lock:
            state_path = self._get_state_path(username)
            state = {}
            if state_path.exists():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            
            current_index = state.get(provider, 0)
            selected_key = keys[current_index % len(keys)]
            state[provider] = (current_index + 1) % len(keys)
            
            try:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            return selected_key


KEY_ROTATOR = KeyRotator()


def ensure_runtime_template(config_root: str = "config", username: str = "demo", project_name: str = "demo") -> None:
    # config/user/[username]/project/[projectname]
    root = Path(config_root) / "user" / username / "project" / project_name
    files = {
        root / "main" / "config.json": {
            "name": "main",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "role": "主 Agent，负责综合 sub-agent 建议并输出最终任务拆解。",
        },
        root / "sub-agent1" / "config.json": {
            "name": "sub-agent1",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "role": "执行路径设计者，关注任务顺序、MVP 和里程碑。",
        },
        root / "sub-agent2" / "config.json": {
            "name": "sub-agent2",
            "provider": "claude",
            "model": "claude-3-5-haiku-latest",
            "api_key_env": "ANTHROPIC_API_KEY",
            "role": "风险审查者，关注遗漏、依赖、风险和验收标准。",
        },
    }
    for path, data in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    ensure_project_runtime_dirs("runtime", username, project_name)


def ensure_project_runtime_dirs(runtime_root: str, username: str, project_name: str) -> None:
    # runtime/user/[username]/project/[projectname]/[dirname]
    root = Path(runtime_root) / "user" / username / "project" / project_name
    for dirname in ["cache", "conversation", "log", "output"]:
        target = root / dirname
        target.mkdir(parents=True, exist_ok=True)
        keep = target / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")


def user_config_path(config_root: str, user_name: str) -> Path:
    safe_name = user_name.strip().replace("/", "_").replace("\\", "_")
    return Path(config_root) / "user" / safe_name / "config.json"


def detect_provider_and_env(api_key: str, base_url: str) -> tuple[str, str]:
    api_key = api_key.strip()
    base_url = base_url.strip().lower()
    
    # 1. Claude
    if api_key.startswith("sk-ant-") or "anthropic" in base_url:
        return "claude", "ANTHROPIC_API_KEY"
    # 2. OpenAI
    if "openai" in base_url or api_key.startswith("sk-proj-"):
        return "openai", "OPENAI_API_KEY"
    # 3. DeepSeek
    if "deepseek" in base_url or api_key.startswith("sk-"):
        return "deepseek", "DEEPSEEK_API_KEY"
        
    # Default fallback
    return "deepseek", "DEEPSEEK_API_KEY"


def load_user_runtime_config(config_root: str, user_name: str | None) -> UserRuntimeConfig | None:
    if not user_name:
        return None
    path = user_config_path(config_root, user_name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    key_pool = data.get("key_pool", [])
    api_keys = {}
    
    for item in key_pool:
        provider = str(item.get("provider", "deepseek")).strip().lower()
        protocol = str(item.get("protocol", "openai")).strip().lower()
        api_key = str(item.get("api_key", "")).strip()
        if not api_key:
            continue
        
        env_name = f"{provider.upper()}_API_KEY"
        if provider == "openai":
            env_name = "OPENAI_API_KEY"
        elif provider in ("claude", "anthropic"):
            env_name = "ANTHROPIC_API_KEY"
        elif provider == "deepseek":
            env_name = "DEEPSEEK_API_KEY"
        elif provider == "custom":
            env_name = "CUSTOM_API_KEY"
            
        if env_name not in api_keys:
            api_keys[env_name] = []
        api_keys[env_name].append(api_key)

        # Also register under direct provider name for easy direct lookups
        if provider not in api_keys:
            api_keys[provider] = []
        if api_key not in api_keys[provider]:
            api_keys[provider].append(api_key)

    # Automatically infer default provider, model, and base_url from the first entry in the key pool
    default_provider = "deepseek"
    default_model = "deepseek-chat"
    default_base_url = "https://api.deepseek.com"
    if key_pool:
        first_item = key_pool[0]
        default_provider = str(first_item.get("provider") or "deepseek").strip().lower()
        default_model = str(first_item.get("model") or "deepseek-chat").strip()
        default_base_url = str(first_item.get("base_url") or "").strip()

    return UserRuntimeConfig(
        name=user_name,
        provider=default_provider,
        api_keys=api_keys,
        model=default_model,
        base_url=default_base_url,
        password=str(data.get("password") or ""),
        raw_data=data
    )


def save_user_runtime_config(config_root: str, config: UserRuntimeConfig) -> Path:
    path = user_config_path(config_root, config.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # 动态从 key_pool 中重新生成 api_keys 映射
    key_pool = config.raw_data.get("key_pool", [])
    
    # If key_pool is empty but config.api_keys exists (e.g. from CLI onboarding), let's populate key_pool!
    if not key_pool and config.api_keys:
        key_pool = []
        for env_name, keys in config.api_keys.items():
            if env_name in ("deepseek", "openai", "claude", "custom"):
                continue
            val_list = keys if isinstance(keys, list) else [keys]
            for k in val_list:
                prov_name = "deepseek"
                model_name = "deepseek-chat"
                base_url = ""
                protocol = "openai"
                if env_name == "DEEPSEEK_API_KEY":
                    prov_name = "deepseek"
                    model_name = "deepseek-chat"
                    base_url = "https://api.deepseek.com"
                    protocol = "openai"
                elif env_name == "OPENAI_API_KEY":
                    prov_name = "openai"
                    model_name = "gpt-4o"
                    base_url = "https://api.openai.com/v1"
                    protocol = "openai"
                elif env_name == "ANTHROPIC_API_KEY":
                    prov_name = "claude"
                    model_name = "claude-3-5-haiku-latest"
                    base_url = "https://api.anthropic.com"
                    protocol = "claude"
                elif env_name == "CUSTOM_API_KEY":
                    prov_name = "custom"
                    model_name = "gpt-4.1-mini"
                    base_url = ""
                    protocol = "openai"
                key_pool.append({
                    "provider": prov_name,
                    "protocol": protocol,
                    "model": model_name,
                    "api_key": str(k),
                    "base_url": base_url
                })
        config.raw_data["key_pool"] = key_pool

    api_keys = {}
    for item in key_pool:
        provider = str(item.get("provider", "deepseek")).strip().lower()
        protocol = str(item.get("protocol", "openai")).strip().lower()
        api_key = str(item.get("api_key", "")).strip()
        if not api_key:
            continue
        
        env_name = f"{provider.upper()}_API_KEY"
        if provider == "openai":
            env_name = "OPENAI_API_KEY"
        elif provider in ("claude", "anthropic"):
            env_name = "ANTHROPIC_API_KEY"
        elif provider == "deepseek":
            env_name = "DEEPSEEK_API_KEY"
        elif provider == "custom":
            env_name = "CUSTOM_API_KEY"
            
        if env_name not in api_keys:
            api_keys[env_name] = []
        api_keys[env_name].append(api_key)

        # Also register under direct provider name for easy direct lookups
        if provider not in api_keys:
            api_keys[provider] = []
        if api_key not in api_keys[provider]:
            api_keys[provider].append(api_key)
    
    config.api_keys = api_keys
    
    payload = {
        "name": config.name,
        "password": config.password,
        "key_pool": key_pool,
        "search": config.raw_data.get("search", {}) if isinstance(config.raw_data, dict) else {}
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def runtime_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_runtime_project(project_name: str | None, config_root: Path) -> RuntimeProjectConfig | None:
    if not project_name or not config_root.exists():
        return None

    main = load_agent_runtime_config(config_root / "main" / "config.json")
    agents: dict[str, AgentRuntimeConfig] = {}
    for path in sorted(config_root.iterdir()):
        if not path.is_dir() or path.name == "main" or path.name == "demo_pristine":
            continue
        config = load_agent_runtime_config(path / "config.json")
        if config is not None and config.enabled:
            agents[path.name] = config
    return RuntimeProjectConfig(project_name=project_name, root=config_root, main=main, agents=agents)


def load_agent_runtime_config(path: Path) -> AgentRuntimeConfig | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return AgentRuntimeConfig(
        name=str(data.get("name") or path.parent.name),
        role=str(data.get("role") or ""),
        provider=str(data.get("provider") or ""),
        model=str(data.get("model") or ""),
        base_url=str(data.get("base_url") or ""),
        api_key_env=str(data.get("api_key_env") or ""),
        api_key_envs=[str(name) for name in data.get("api_key_envs", [])],
        enabled=bool(data.get("enabled", True)),
    )


def resolve_runtime_provider(config: AgentRuntimeConfig | None, user_config: UserRuntimeConfig | None = None) -> ProviderConfig | None:
    if config is None or not config.provider:
        return None

    api_key = None
    resolved_provider = config.provider.strip().lower()
    
    if user_config is not None:
        # 1. 尝试直接以供应商名查找 key
        keys = user_config.api_keys.get(resolved_provider, [])
        
        # 2. 若未精确找到，则根据 Agent 供应商所需的协议类型（claude/anthropic 为 claude，其余默认均为 openai）智能从 key_pool 中寻找符合协议的 API Key
        if not keys and "key_pool" in user_config.raw_data:
            target_protocol = "claude" if resolved_provider in ("claude", "anthropic") else "openai"
            keys = []
            for item in user_config.raw_data.get("key_pool", []):
                proto = str(item.get("protocol", "openai")).strip().lower()
                k = str(item.get("api_key", "")).strip()
                if proto == target_protocol and k:
                    keys.append(k)
                    
        # 3. 若依然没有，则在 key_pool 中选取任意有 key 的卡片 fallback
        if not keys and "key_pool" in user_config.raw_data:
            keys = [
                str(item.get("api_key", "")).strip()
                for item in user_config.raw_data.get("key_pool", [])
                if str(item.get("api_key", "")).strip()
            ]
                    
        if keys:
            api_key = KEY_ROTATOR.get_key(user_config.name, resolved_provider, keys)
            
    if not api_key:
        env_names = []
        if config.api_key_env:
            env_names.append(config.api_key_env)
        env_names.extend(config.api_key_envs)
        api_key = first_env(env_names)

    if not api_key and user_config is not None and user_config.name == "demo":
        api_key = "demo_mock_key"

    if not api_key:
        raise RuntimeError(f"未检测到 {config.name} 的 API Key：{', '.join(env_names) or '未配置 api_key_env'}")

    # 提取 API 属性覆盖与接口协议
    selected_base_url = config.base_url or None
    selected_model = config.model or None
    selected_protocol = "openai"  # 默认协议

    if user_config is not None and "key_pool" in user_config.raw_data:
        for item in user_config.raw_data.get("key_pool", []):
            if str(item.get("api_key")).strip() == api_key:
                if item.get("base_url"):
                    selected_base_url = str(item.get("base_url")).strip()
                if item.get("model"):
                    selected_model = str(item.get("model")).strip()
                if item.get("protocol"):
                    selected_protocol = str(item.get("protocol")).strip().lower()
                break

    # 映射协议至标准的 openai 或 claude 规整名，避开 normalize_provider 校验异常
    routing_provider = "claude" if selected_protocol == "claude" else "openai"

    return build_provider_config(
        provider=routing_provider,
        api_key=api_key,
        model=selected_model,
        base_url=selected_base_url,
    )


def conversation_path(runtime_root: str, username: str, project_name: str, conversation_id: str) -> Path:
    safe_id = conversation_id.replace("/", "_").replace("\\", "_")
    return Path(runtime_root) / "user" / username / "project" / project_name / "conversation" / f"{safe_id}.jsonl"


def load_conversation_context(runtime_root: str, username: str, project_name: str, conversation_id: str) -> str:
    path = conversation_path(runtime_root, username, project_name, conversation_id)
    if not path.exists():
        return ""

    lines = []
    try:
        for raw_line in path.read_text(encoding="utf-8").splitlines()[-6:]:
            if not raw_line.strip():
                continue
            item = json.loads(raw_line)
            lines.append(
                "历史轮次：\n"
                f"用户目标/修改：{item.get('goal', '')}\n"
                f"最终目标：{item.get('plan', {}).get('goal', '')}\n"
                f"下一步：{item.get('plan', {}).get('next_step', '')}"
            )
    except Exception:
        return ""
    return "\n\n".join(lines)


def append_conversation(
    runtime_root: str,
    username: str,
    project_name: str,
    conversation_id: str,
    goal: str,
    context: str,
    result: AgentRunResult,
) -> Path:
    path = conversation_path(runtime_root, username, project_name, conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "goal": goal,
        "context": context,
        "plan": {
            "goal": result.plan.goal,
            "tasks": [
                {"task_id": task.task_id, "title": task.title, "action": task.action, "output": task.output, "status": task.status}
                for task in result.plan.tasks
            ],
            "relations": [
                {"source_id": r.source_id, "target_id": r.target_id, "relation_type": r.relation_type}
                for r in result.plan.relations
            ],
            "next_step": result.plan.next_step,
            "sources": result.plan.sources,
        },
        "sub_agents": [
            {
                "name": run.name,
                "role": run.role,
                "skills": run.skills,
                "task_count": len(run.plan.tasks),
            }
            for run in result.sub_agent_runs
        ],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def export_plan(runtime_root: str, username: str, project_name: str, result: AgentRunResult, run_id: str | None = None) -> dict[str, Path]:
    ensure_project_runtime_dirs(runtime_root, username, project_name)
    output_dir = Path(runtime_root) / "user" / username / "project" / project_name / "output"
    run_id = run_id or runtime_timestamp()
    json_path = output_dir / f"{run_id}.json"
    markdown_path = output_dir / f"{run_id}.md"

    payload = {
        "goal": result.plan.goal,
        "tasks": [
            {"task_id": task.task_id, "title": task.title, "action": task.action, "output": task.output, "status": task.status}
            for task in result.plan.tasks
        ],
        "relations": [
            {"source_id": r.source_id, "target_id": r.target_id, "relation_type": r.relation_type}
            for r in result.plan.relations
        ],
        "next_step": result.plan.next_step,
        "sources": result.plan.sources,
        "sub_agents": [
            {
                "name": run.name,
                "role": run.role,
                "skills": run.skills,
                "task_count": len(run.plan.tasks),
            }
            for run in result.sub_agent_runs
        ],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(format_plan_markdown(result), encoding="utf-8")
    update_output_index(runtime_root, username, project_name, run_id, result, json_path, markdown_path)
    return {"json": json_path, "markdown": markdown_path}


def update_output_index(
    runtime_root: str,
    username: str,
    project_name: str,
    run_id: str,
    result: AgentRunResult,
    json_path: Path,
    markdown_path: Path,
) -> Path:
    output_dir = Path(runtime_root) / "user" / username / "project" / project_name / "output"
    index_path = output_dir / "index.json"
    if index_path.exists():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            data = {"project": project_name, "runs": []}
    else:
        data = {"project": project_name, "runs": []}

    data["runs"].append(
        {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "goal": result.plan.goal,
            "task_count": len(result.plan.tasks),
            "sub_agent_count": len(result.sub_agent_runs),
            "files": {
                "json": str(json_path),
                "markdown": str(markdown_path),
            },
        }
    )
    index_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return index_path


def format_plan_markdown(result: AgentRunResult) -> str:
    lines = [f"# {result.plan.goal}", ""]
    for index, task in enumerate(result.plan.tasks, start=1):
        lines.extend(
            [
                f"## {index}. [{task.task_id}] {task.title}",
                "",
                f"- 行动：{task.action}",
                f"- 产出：{task.output}",
                f"- 状态：{task.status}",
                "",
            ]
        )
    if result.plan.relations:
        lines.extend(["## 任务关系", ""])
        type_labels = {"sequential": "顺序", "parallel": "并行", "blocking": "阻塞", "nesting": "嵌套"}
        for r in result.plan.relations:
            label = type_labels.get(r.relation_type, r.relation_type)
            lines.append(f"- {r.source_id} --[{label}]--> {r.target_id}")
        lines.append("")
    lines.extend(["## 下一步", "", result.plan.next_step, ""])
    if result.plan.sources:
        lines.extend(["## 参考来源", ""])
        lines.extend(f"- {source}" for source in result.plan.sources)
        lines.append("")
    if result.sub_agent_runs:
        lines.extend(["## sub-agent 摘要", ""])
        for run in result.sub_agent_runs:
            lines.append(f"- {run.name}：{run.role}（{len(run.plan.tasks)} 个建议任务）")
    return "\n".join(lines)


def append_run_log(
    runtime_root: str,
    username: str,
    project_name: str,
    run_id: str,
    goal: str,
    result: AgentRunResult,
    elapsed_seconds: float,
    mode: str,
) -> Path:
    ensure_project_runtime_dirs(runtime_root, username, project_name)
    path = Path(runtime_root) / "user" / username / "project" / project_name / "log" / "runs.jsonl"
    record = {
        "run_id": run_id,
        "status": "success",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "goal": goal,
        "mode": mode,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "task_count": len(result.plan.tasks),
        "sub_agent_count": len(result.sub_agent_runs),
        "warnings": result.warnings,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def append_failure_log(
    runtime_root: str,
    username: str,
    project_name: str,
    run_id: str,
    goal: str,
    stage: str,
    error: Exception | str,
    elapsed_seconds: float,
    mode: str = "",
) -> Path:
    ensure_project_runtime_dirs(runtime_root, username, project_name)
    path = Path(runtime_root) / "user" / username / "project" / project_name / "log" / "runs.jsonl"
    record = {
        "run_id": run_id,
        "status": "failed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "goal": goal,
        "mode": mode,
        "stage": stage,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "error_type": type(error).__name__ if isinstance(error, Exception) else "Error",
        "error": str(error),
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def start_timer() -> float:
    return perf_counter()


def elapsed_since(start: float) -> float:
    return perf_counter() - start


def cache_key(*parts: str) -> str:
    joined = "\n".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def search_cache_path(runtime_root: str, username: str, project_name: str) -> Path:
    ensure_project_runtime_dirs(runtime_root, username, project_name)
    return Path(runtime_root) / "user" / username / "project" / project_name / "cache" / "search.json"


def parse_cache_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def cache_expires_at(created_at: str) -> str:
    created = parse_cache_datetime(created_at) or datetime.now(timezone.utc)
    return (created + timedelta(seconds=SEARCH_CACHE_TTL_SECONDS)).isoformat()


def is_cache_item_expired(item: dict, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    expires_at = parse_cache_datetime(str(item.get("expires_at") or ""))
    if expires_at is None:
        created_at = parse_cache_datetime(str(item.get("created_at") or ""))
        if created_at is None:
            return True
        expires_at = created_at + timedelta(seconds=SEARCH_CACHE_TTL_SECONDS)
    return now >= expires_at


def load_cached_search_results(
    runtime_root: str,
    username: str,
    project_name: str,
    provider: str,
    query: str,
    max_results: int,
) -> list[SearchResult] | None:
    path = search_cache_path(runtime_root, username, project_name)
    if not path.exists():
        return None
    with CACHE_LOCK:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        key = cache_key(provider, query, str(max_results))
        item = data.get(key)
        if not item:
            return None
        if is_cache_item_expired(item):
            data.pop(key, None)
            try:
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            return None
        return [
            SearchResult(
                title=str(result.get("title", "")),
                url=str(result.get("url", "")),
                content=str(result.get("content", "")),
            )
            for result in item.get("results", [])
        ]


def save_cached_search_results(
    runtime_root: str,
    username: str,
    project_name: str,
    provider: str,
    query: str,
    max_results: int,
    results: list[SearchResult],
) -> Path:
    path = search_cache_path(runtime_root, username, project_name)
    with CACHE_LOCK:
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        key = cache_key(provider, query, str(max_results))
        created_at = datetime.now(timezone.utc).isoformat()
        data[key] = {
            "provider": provider,
            "query": provider,
            "max_results": max_results,
            "created_at": created_at,
            "expires_at": cache_expires_at(created_at),
            "results": [
                {"title": result.title, "url": result.url, "content": result.content}
                for result in results
            ],
        }
        try:
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            if temp_path.exists():
                if path.exists():
                    path.unlink()
                temp_path.rename(path)
        except Exception:
            pass
    return path


def list_cache_entries(runtime_root: str, username: str, project_name: str) -> list[dict]:
    path = search_cache_path(runtime_root, username, project_name)
    entries = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        for key, item in data.items():
            entries.append(
                {
                    "key": key,
                    "provider": item.get("provider", ""),
                    "query": item.get("query", ""),
                    "max_results": item.get("max_results", 0),
                    "created_at": item.get("created_at", ""),
                    "expires_at": item.get("expires_at", cache_expires_at(str(item.get("created_at", "")))),
                    "expired": is_cache_item_expired(item),
                    "result_count": len(item.get("results", [])),
                }
            )
    return entries


def clear_cache(runtime_root: str, username: str, project_name: str) -> int:
    ensure_project_runtime_dirs(runtime_root, username, project_name)
    cache_dir = Path(runtime_root) / "user" / username / "project" / project_name / "cache"
    removed = 0
    for path in cache_dir.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_file():
            path.unlink()
            removed += 1
    return removed
