from typing import Any

from task_decomposer_app.bootstrap import missing_dependency_message
from task_decomposer_app.models import ProviderConfig
from task_decomposer_app.utils import parse_json_object

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - handled at runtime
    OpenAI = None

try:
    from anthropic import Anthropic
except ImportError:  # pragma: no cover - handled at runtime
    Anthropic = None


class LLMClient:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.total_tokens = 0

    def complete_json(self, system_prompt: str, user_input: str) -> dict[str, Any]:
        if self.config.name == "claude":
            return self._call_claude(system_prompt, user_input)
        return self._call_openai_compatible(system_prompt, user_input)

    def _call_openai_compatible(self, system_prompt: str, user_input: str) -> dict[str, Any]:
        if OpenAI is None:
            raise RuntimeError(missing_dependency_message("openai"))

        import httpx
        # 用自定义 httpx 客户端绕过中转节点/代理下极易触发的 SSL UNEXPECTED_EOF_WHILE_READING 协议异常
        limits = httpx.Limits(max_keepalive_connections=1, max_connections=5, keepalive_expiry=5.0)
        http_client = httpx.Client(
            http2=False,
            limits=limits,
            trust_env=True
        )

        client_kwargs: dict[str, Any] = {
            "api_key": self.config.api_key,
            "http_client": http_client
        }
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url

        client = OpenAI(**client_kwargs)
        try:
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": user_input.strip()},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            if getattr(response, "usage", None) is not None:
                self.total_tokens += int(getattr(response.usage, "total_tokens", 0) or 0)
            content = response.choices[0].message.content or "{}"
            return parse_json_object(content)
        finally:
            http_client.close()

    def _call_claude(self, system_prompt: str, user_input: str) -> dict[str, Any]:
        if Anthropic is None:
            raise RuntimeError(missing_dependency_message("anthropic"))

        import httpx
        limits = httpx.Limits(max_keepalive_connections=1, max_connections=5, keepalive_expiry=5.0)
        http_client = httpx.Client(
            http2=False,
            limits=limits,
            trust_env=True
        )
        client_kwargs = {
            "api_key": self.config.api_key,
            "http_client": http_client
        }
        if self.config.base_url:
            client_kwargs["base_url"] = self.config.base_url
        client = Anthropic(**client_kwargs)
        try:
            response = client.messages.create(
                model=self.config.model,
                max_tokens=1800,
                temperature=0.3,
                system=system_prompt.strip(),
                messages=[{"role": "user", "content": user_input.strip()}],
            )
            if getattr(response, "usage", None) is not None:
                input_tokens = int(getattr(response.usage, "input_tokens", 0) or 0)
                output_tokens = int(getattr(response.usage, "output_tokens", 0) or 0)
                self.total_tokens += input_tokens + output_tokens
            content = "".join(block.text for block in response.content if getattr(block, "type", "") == "text")
            return parse_json_object(content or "{}")
        finally:
            http_client.close()
