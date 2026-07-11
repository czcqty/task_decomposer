from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    name: str
    api_key: str
    model: str
    base_url: str | None = None


@dataclass
class SearchConfig:
    enabled: bool = False
    provider: str = "none"
    api_key: str = ""
    max_results: int = 5


@dataclass
class Skill:
    name: str
    content: str
    path: str


@dataclass
class SearchResult:
    title: str
    url: str
    content: str


@dataclass
class DecomposedTask:
    task_id: str
    title: str
    action: str
    output: str
    status: str = "pending"  # pending | in_progress | done | blocked


@dataclass
class TaskRelation:
    """两个任务之间的关系。"""
    source_id: str       # 关系起点任务 ID
    target_id: str       # 关系终点任务 ID
    relation_type: str   # "sequential" | "parallel" | "blocking" | "nesting"


@dataclass
class Plan:
    goal: str
    tasks: list[DecomposedTask]
    next_step: str
    relations: list[TaskRelation] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)


@dataclass
class SubAgentSpec:
    name: str
    role: str
    skills: list[Skill] = field(default_factory=list)
    model_config: ProviderConfig | None = None
    provider: str = ""


@dataclass
class SubAgentRun:
    name: str
    role: str
    plan: Plan
    skills: list[str] = field(default_factory=list)


@dataclass
class AgentRunResult:
    plan: Plan
    warnings: list[str] = field(default_factory=list)
    search_results: list[SearchResult] = field(default_factory=list)
    sub_agent_runs: list[SubAgentRun] = field(default_factory=list)
