from __future__ import annotations

import json
from typing import Any

# Импортируем FastMCP вместо MCPServer
from mcp.server.fastmcp import FastMCP

# Инициализируем сервер через FastMCP
mcp = FastMCP("duckduckgo-search")


def _search_ddg_sync(
    query: str, max_results: int = 5, region: str = "wt-wt"
) -> list[dict[str, Any]]:
    """Выполняет веб-поиск через ddgs (с fallback на duckduckgo_search)."""
    try:
        from ddgs import DDGS  # type: ignore[import-not-found]
    except ImportError:
        from duckduckgo_search import DDGS  # type: ignore[import-not-found]

    results: list[dict[str, Any]] = []
    with DDGS() as ddgs:
        raw_items = ddgs.text(query, region=region, max_results=max_results)
        for item in raw_items or []:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                }
            )
    return results


def _news_ddg_sync(
    query: str, max_results: int = 5, region: str = "wt-wt"
) -> list[dict[str, Any]]:
    """Выполняет поиск новостей через ddgs (с fallback на duckduckgo_search)."""
    try:
        from ddgs import DDGS  # type: ignore[import-not-found]
    except ImportError:
        from duckduckgo_search import DDGS  # type: ignore[import-not-found]

    results: list[dict[str, Any]] = []
    with DDGS() as ddgs:
        raw_items = ddgs.news(query, region=region, max_results=max_results)
        for item in raw_items or []:
            results.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                    "date": item.get("date", ""),
                    "snippet": item.get("body", ""),
                }
            )
    return results


@mcp.tool()
def web_search(query: str, max_results: int = 5, region: str = "wt-wt") -> str:
    """Search the web using DuckDuckGo and return JSON results with title, url, and snippet."""
    safe_limit = max(1, min(int(max_results), 20))
    try:
        items = _search_ddg_sync(query=query, max_results=safe_limit, region=region)
        return json.dumps(
            {
                "query": query,
                "count": len(items),
                "results": items,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps(
            {
                "query": query,
                "error": str(exc),
                "results": [],
            },
            ensure_ascii=False,
            indent=2,
        )


@mcp.tool()
def news_search(query: str, max_results: int = 5, region: str = "wt-wt") -> str:
    """Search recent news via DuckDuckGo and return JSON results."""
    safe_limit = max(1, min(int(max_results), 20))
    try:
        items = _news_ddg_sync(query=query, max_results=safe_limit, region=region)
        return json.dumps(
            {
                "query": query,
                "count": len(items),
                "results": items,
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:
        return json.dumps(
            {
                "query": query,
                "error": str(exc),
                "results": [],
            },
            ensure_ascii=False,
            indent=2,
        )


if __name__ == "__main__":
    # FastMCP автоматически обрабатывает запуск через stdio
    mcp.run()
