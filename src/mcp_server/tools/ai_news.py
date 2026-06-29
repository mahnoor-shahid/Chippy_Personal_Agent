"""The `get_ai_news` MCP tool.

Pattern: every tool module exposes `register(mcp)`. server.py calls it. To add a
new capability you write a new module + one import line — nothing else changes.

Design note: this tool returns *structured data*, not prose. Summarizing into
bullet points is the LLM brain's job (or ChatGPT's). Keeping the tool
deterministic makes it reusable and testable.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..config import ai_news_feeds
from ..sources.rss import fetch_news


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_ai_news(since_hours: int = 24, max_items: int = 25) -> dict:
        """Fetch recent AI/ML news items from curated feeds.

        Returns structured items (title, link, source, published, summary) so the
        caller can summarize them into bullet points. Use this for "what's new in
        AI" style requests and for the morning digest.

        Args:
            since_hours: Only include items published within this many hours.
            max_items: Maximum number of items to return (newest first).
        """
        items = fetch_news(
            ai_news_feeds(),
            since_hours=since_hours,
            max_items=max_items,
        )
        return {
            "count": len(items),
            "since_hours": since_hours,
            "items": [i.as_dict() for i in items],
        }
