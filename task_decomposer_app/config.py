import os

from task_decomposer_app.models import ProviderConfig, SearchConfig
from task_decomposer_app.utils import first_env


PROVIDER_ALIASES = {
    "chatgpt": "openai",
    "gpt": "openai",
    "openai": "openai",
    "anthropic": "claude",
    "claude": "claude",
    "cladue": "claude",
    "deepseek": "deepseek",
    "custom": "custom",
    "openai-compatible": "custom",
}

PROVIDER_DEFAULTS = {
    "openai": {
        "model": "gpt-4.1-mini",
        "api_key_envs": ["OPENAI_API_KEY", "CHATGPT_API_KEY", "LLM_API_KEY"],
        "base_url": None,
    },
    "claude": {
        "model": "claude-3-5-haiku-latest",
        "api_key_envs": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "LLM_API_KEY"],
        "base_url": None,
    },
    "deepseek": {
        "model": "deepseek-chat",
        "api_key_envs": ["DEEPSEEK_API_KEY", "LLM_API_KEY"],
        "base_url": "https://api.deepseek.com",
    },
    "custom": {
        "model": "gpt-4.1-mini",
        "api_key_envs": ["CUSTOM_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "LLM_API_KEY"],
        "base_url": None,
    },
}


def normalize_provider(provider: str) -> str:
    value = provider.strip().lower()
    if value == "auto":
        return "auto"
    if value not in PROVIDER_ALIASES:
        supported = "openai/chatgpt, claude, deepseek, custom"
        raise RuntimeError(f"不支持的供应商：{provider}。支持：{supported}")
    return PROVIDER_ALIASES[value]


def detect_provider() -> str | None:
    if first_env(["OPENAI_API_KEY", "CHATGPT_API_KEY"]):
        return "openai"
    if first_env(["ANTHROPIC_API_KEY", "CLAUDE_API_KEY"]):
        return "claude"
    if first_env(["DEEPSEEK_API_KEY"]):
        return "deepseek"
    if first_env(["CUSTOM_API_KEY", "OPENAI_COMPATIBLE_API_KEY", "LLM_API_KEY"]):
        return "custom"
    return None


def resolve_provider(provider: str, model: str | None, base_url: str | None) -> ProviderConfig | None:
    name = normalize_provider(provider)
    if name == "auto":
        name = detect_provider()
        if name is None:
            return None

    defaults = PROVIDER_DEFAULTS[name]
    env_prefix = name.upper()
    api_key = first_env(defaults["api_key_envs"])
    if not api_key:
        raise RuntimeError(f"未检测到 {name} 的 API Key")

    resolved_model = model or os.getenv("MODEL") or os.getenv(f"{env_prefix}_MODEL") or defaults["model"]
    resolved_base_url = (
        base_url
        or os.getenv("BASE_URL")
        or os.getenv(f"{env_prefix}_BASE_URL")
        or defaults["base_url"]
    )
    return ProviderConfig(name=name, api_key=api_key, model=resolved_model, base_url=resolved_base_url)


def build_provider_config(
    provider: str,
    api_key: str,
    model: str | None = None,
    base_url: str | None = None,
) -> ProviderConfig | None:
    name = normalize_provider(provider)
    if name == "auto":
        name = detect_provider()
        if name is None:
            return None

    defaults = PROVIDER_DEFAULTS[name]
    resolved_model = model or defaults["model"]
    resolved_base_url = base_url or defaults["base_url"]
    return ProviderConfig(name=name, api_key=api_key, model=resolved_model, base_url=resolved_base_url)


def resolve_search_config(enabled: bool, provider: str, max_results: int) -> SearchConfig:
    if not enabled:
        return SearchConfig(enabled=False)

    selected = (provider or os.getenv("SEARCH_PROVIDER") or "auto").strip().lower()
    tavily_key = first_env(["TAVILY_API_KEY", "SEARCH_API_KEY"])

    if selected == "auto":
        selected = "tavily" if tavily_key else "duckduckgo"

    if selected == "tavily":
        if not tavily_key:
            raise RuntimeError("已选择 Tavily 搜索，但未检测到 TAVILY_API_KEY")
        return SearchConfig(enabled=True, provider="tavily", api_key=tavily_key, max_results=max_results)

    if selected in {"duckduckgo", "ddg"}:
        return SearchConfig(enabled=True, provider="duckduckgo", max_results=max_results)

    raise RuntimeError("不支持的搜索供应商。支持：auto、tavily、duckduckgo")
