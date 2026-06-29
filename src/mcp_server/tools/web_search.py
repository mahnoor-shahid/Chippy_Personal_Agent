"""The `web_search` MCP tool — general-purpose web lookup via DuckDuckGo.

Free, no API key. Lets Chippy answer about anything current/factual, not just the
curated AI feeds. Returns structured results; the LLM does the summarizing.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def web_search(query: str, max_results: int = 5) -> dict:
        """Search the web for current or factual information.

        Use this for general questions, recent events, facts, products, places —
        anything not covered by a more specific tool. Returns a list of results
        (title, url, snippet) to summarize or cite.

        Args:
            query: What to search for.
            max_results: How many results to return (1-10).
        """
        from ddgs import DDGS

        max_results = max(1, min(max_results, 10))
        results = []
        for r in DDGS().text(query, max_results=max_results):
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
            )
        return {"query": query, "count": len(results), "results": results}
