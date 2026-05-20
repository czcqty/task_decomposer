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
    scope: str = "global"
    owner: str = "shared"


@dataclass
class SearchResult:
    title: str
    url: str
    content: str


@dataclass
class DecomposedTask:
    title: str
    action: str
    output: str


@dataclass
class Plan:
    goal: str
    tasks: list[DecomposedTask]
    next_step: str
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
