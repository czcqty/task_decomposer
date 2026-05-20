import json
import urllib.parse
import urllib.request
from typing import Any

from task_decomposer_app.models import SearchConfig, SearchResult


class SearchService:
    def __init__(self, config: SearchConfig):
        self.config = config

    def search(self, query: str) -> list[SearchResult]:
        if not self.config.enabled:
            return []
        if self.config.provider == "tavily":
            return self._search_tavily(query)
        if self.config.provider == "duckduckgo":
            return self._search_duckduckgo_instant(query)
        return []

    def _search_tavily(self, query: str) -> list[SearchResult]:
        payload = {
            "query": query,
            "search_depth": "basic",
            "max_results": self.config.max_results,
            "include_answer": True,
        }
        request = urllib.request.Request(
            "https://api.tavily.com/search",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        results: list[SearchResult] = []
        answer = data.get("answer")
        if answer:
            results.append(SearchResult(title="Tavily Answer", url="", content=str(answer)))

        for item in data.get("results", [])[: self.config.max_results]:
            if not isinstance(item, dict):
                continue
            results.append(
                SearchResult(
                    title=str(item.get("title") or "Untitled"),
                    url=str(item.get("url") or ""),
                    content=str(item.get("content") or ""),
                )
            )
        return results[: self.config.max_results]

    def _search_duckduckgo_instant(self, query: str) -> list[SearchResult]:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "format": "json",
                "no_redirect": "1",
                "no_html": "1",
            }
        )
        url = f"https://api.duckduckgo.com/?{params}"
        request = urllib.request.Request(url, headers={"User-Agent": "TaskDecomposer/0.2"})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))

        results: list[SearchResult] = []
        abstract = data.get("AbstractText")
        abstract_url = data.get("AbstractURL")
        heading = data.get("Heading") or "DuckDuckGo Instant Answer"
        if abstract:
            results.append(SearchResult(title=str(heading), url=str(abstract_url or ""), content=str(abstract)))

        for topic in data.get("RelatedTopics", []):
            self._append_related_topic(results, topic)
            if len(results) >= self.config.max_results:
                break
        return results[: self.config.max_results]

    def _append_related_topic(self, results: list[SearchResult], topic: dict[str, Any]) -> None:
        if "Topics" in topic:
            for nested in topic.get("Topics", []):
                if isinstance(nested, dict):
                    self._append_related_topic(results, nested)
            return

        text = topic.get("Text")
        url = topic.get("FirstURL")
        if text:
            title = str(text).split(" - ")[0][:80]
            results.append(SearchResult(title=title, url=str(url or ""), content=str(text)))


def format_search_results_for_prompt(results: list[SearchResult]) -> str:
    if not results:
        return ""

    lines = []
    for index, result in enumerate(results, start=1):
        url = result.url or "无 URL"
        content = result.content[:1200]
        lines.append(f"[{index}] {result.title}\nURL: {url}\n摘要: {content}")
    return "\n\n".join(lines)
