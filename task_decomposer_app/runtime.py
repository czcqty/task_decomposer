import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter

from task_decomposer_app.config import build_provider_config
from task_decomposer_app.models import AgentRunResult, ProviderConfig, SearchResult
from task_decomposer_app.utils import first_env


SEARCH_CACHE_TTL_SECONDS = 24 * 60 * 60


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
    api_keys: dict[str, str] = field(default_factory=dict)
    model: str = ""
    base_url: str = ""


def ensure_runtime_template(runtime_root: str = "project", project_name: str = "demo") -> None:
    root = Path(runtime_root)
    files = {
        root / "config" / project_name / "main" / "config.json": {
            "name": "main",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "role": "主 Agent，负责综合 sub-agent 建议并输出最终任务拆解。",
        },
        root / "config" / project_name / "sub-agent1" / "config.json": {
            "name": "sub-agent1",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key_env": "DEEPSEEK_API_KEY",
            "role": "执行路径设计者，关注任务顺序、MVP 和里程碑。",
        },
        root / "config" / project_name / "sub-agent2" / "config.json": {
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
    ensure_project_runtime_dirs(runtime_root, project_name)


def ensure_project_runtime_dirs(runtime_root: str, project_name: str) -> None:
    root = Path(runtime_root)
    for dirname in ["conversation", "output", "cache", "log"]:
        target = root / dirname / project_name
        target.mkdir(parents=True, exist_ok=True)
        keep = target / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")


def user_config_path(runtime_root: str, user_name: str) -> Path:
    safe_name = user_name.strip().replace("/", "_").replace("\\", "_")
    return Path(runtime_root) / "users" / safe_name / "config.json"


def load_user_runtime_config(runtime_root: str, user_name: str | None) -> UserRuntimeConfig | None:
    if not user_name:
        return None
    path = user_config_path(runtime_root, user_name)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return UserRuntimeConfig(
        name=str(data.get("name") or user_name),
        provider=str(data.get("provider") or ""),
        api_keys={str(key): str(value) for key, value in data.get("api_keys", {}).items()},
        model=str(data.get("model") or ""),
        base_url=str(data.get("base_url") or ""),
    )


def save_user_runtime_config(runtime_root: str, config: UserRuntimeConfig) -> Path:
    path = user_config_path(runtime_root, config.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "name": config.name,
        "provider": config.provider,
        "api_keys": config.api_keys,
        "model": config.model,
        "base_url": config.base_url,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def runtime_timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def load_runtime_project(project_name: str | None, runtime_root: str = "project") -> RuntimeProjectConfig | None:
    if not project_name:
        return None

    config_root = Path(runtime_root) / "config" / project_name
    if not config_root.exists():
        return None

    main = load_agent_runtime_config(config_root / "main" / "config.json")
    agents: dict[str, AgentRuntimeConfig] = {}
    for path in sorted(config_root.iterdir()):
        if not path.is_dir() or path.name == "main":
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


def resolve_runtime_provider(config: AgentRuntimeConfig | None) -> ProviderConfig | None:
    if config is None or not config.provider:
        return None

    env_names = []
    if config.api_key_env:
        env_names.append(config.api_key_env)
    env_names.extend(config.api_key_envs)
    api_key = first_env(env_names)
    if not api_key:
        raise RuntimeError(f"未检测到 {config.name} 的 API Key：{', '.join(env_names) or '未配置 api_key_env'}")

    return build_provider_config(
        provider=config.provider,
        api_key=api_key,
        model=config.model or None,
        base_url=config.base_url or None,
    )


def conversation_path(runtime_root: str, project_name: str, conversation_id: str) -> Path:
    safe_id = conversation_id.replace("/", "_").replace("\\", "_")
    return Path(runtime_root) / "conversation" / project_name / f"{safe_id}.jsonl"


def load_conversation_context(runtime_root: str, project_name: str, conversation_id: str) -> str:
    path = conversation_path(runtime_root, project_name, conversation_id)
    if not path.exists():
        return ""

    lines = []
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
    return "\n\n".join(lines)


def append_conversation(
    runtime_root: str,
    project_name: str,
    conversation_id: str,
    goal: str,
    context: str,
    result: AgentRunResult,
) -> Path:
    path = conversation_path(runtime_root, project_name, conversation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "goal": goal,
        "context": context,
        "plan": {
            "goal": result.plan.goal,
            "tasks": [
                {"title": task.title, "action": task.action, "output": task.output}
                for task in result.plan.tasks
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


def export_plan(runtime_root: str, project_name: str, result: AgentRunResult, run_id: str | None = None) -> dict[str, Path]:
    ensure_project_runtime_dirs(runtime_root, project_name)
    output_dir = Path(runtime_root) / "output" / project_name
    run_id = run_id or runtime_timestamp()
    json_path = output_dir / f"{run_id}.json"
    markdown_path = output_dir / f"{run_id}.md"

    payload = {
        "goal": result.plan.goal,
        "tasks": [
            {"title": task.title, "action": task.action, "output": task.output}
            for task in result.plan.tasks
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
    update_output_index(runtime_root, project_name, run_id, result, json_path, markdown_path)
    return {"json": json_path, "markdown": markdown_path}


def update_output_index(
    runtime_root: str,
    project_name: str,
    run_id: str,
    result: AgentRunResult,
    json_path: Path,
    markdown_path: Path,
) -> Path:
    output_dir = Path(runtime_root) / "output" / project_name
    index_path = output_dir / "index.json"
    if index_path.exists():
        data = json.loads(index_path.read_text(encoding="utf-8"))
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
                f"## {index}. {task.title}",
                "",
                f"- 行动：{task.action}",
                f"- 产出：{task.output}",
                "",
            ]
        )
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
    project_name: str,
    run_id: str,
    goal: str,
    result: AgentRunResult,
    elapsed_seconds: float,
    mode: str,
) -> Path:
    ensure_project_runtime_dirs(runtime_root, project_name)
    path = Path(runtime_root) / "log" / project_name / "runs.jsonl"
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
    project_name: str,
    run_id: str,
    goal: str,
    stage: str,
    error: Exception | str,
    elapsed_seconds: float,
    mode: str = "",
) -> Path:
    ensure_project_runtime_dirs(runtime_root, project_name)
    path = Path(runtime_root) / "log" / project_name / "runs.jsonl"
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


def search_cache_path(runtime_root: str, project_name: str) -> Path:
    ensure_project_runtime_dirs(runtime_root, project_name)
    return Path(runtime_root) / "cache" / project_name / "search.json"


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
    project_name: str,
    provider: str,
    query: str,
    max_results: int,
) -> list[SearchResult] | None:
    path = search_cache_path(runtime_root, project_name)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    key = cache_key(provider, query, str(max_results))
    item = data.get(key)
    if not item:
        return None
    if is_cache_item_expired(item):
        data.pop(key, None)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
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
    project_name: str,
    provider: str,
    query: str,
    max_results: int,
    results: list[SearchResult],
) -> Path:
    path = search_cache_path(runtime_root, project_name)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    key = cache_key(provider, query, str(max_results))
    created_at = datetime.now(timezone.utc).isoformat()
    data[key] = {
        "provider": provider,
        "query": query,
        "max_results": max_results,
        "created_at": created_at,
        "expires_at": cache_expires_at(created_at),
        "results": [
            {"title": result.title, "url": result.url, "content": result.content}
            for result in results
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_cache_entries(runtime_root: str, project_name: str) -> list[dict]:
    path = search_cache_path(runtime_root, project_name)
    entries = []
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
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


def clear_cache(runtime_root: str, project_name: str) -> int:
    ensure_project_runtime_dirs(runtime_root, project_name)
    cache_dir = Path(runtime_root) / "cache" / project_name
    removed = 0
    for path in cache_dir.iterdir():
        if path.name == ".gitkeep":
            continue
        if path.is_file():
            path.unlink()
            removed += 1
    return removed
