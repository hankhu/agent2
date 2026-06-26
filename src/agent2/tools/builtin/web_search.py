"""Built-in tool: web search (simulated / pluggable)."""

from __future__ import annotations

import httpx

from agent2.tools.base import tool


@tool(description="Search the web for information on a given query. Returns a summary of search results.")
async def web_search(query: str, max_results: int = 5) -> str:
    """Search the web using DuckDuckGo's instant answer API.

    This is a lightweight implementation that uses DuckDuckGo's API.
    For production use, replace with a proper search API (Google, Bing, etc.).
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_html": 1},
            )
            resp.raise_for_status()
            data = resp.json()

        results: list[str] = []

        # Abstract (instant answer)
        if data.get("Abstract"):
            results.append(f"**Summary**: {data['Abstract']}")
            if data.get("AbstractSource"):
                results.append(f"Source: {data['AbstractSource']}")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text']}")

        if not results:
            return f"No results found for '{query}'. Try rephrasing your search."

        return "\n".join(results)

    except Exception as e:
        return f"Search failed: {e}. Consider using a different search query."
