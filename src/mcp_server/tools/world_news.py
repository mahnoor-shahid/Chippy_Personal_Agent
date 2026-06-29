"""The `get_world_news` tool — global daily headlines (Deutsche Welle top stories).

Reuses the RSS source. Feeds are configurable via WORLD_NEWS_FEEDS (comma-separated).
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

DEFAULT_WORLD_FEEDS = ["https://rss.dw.com/xml/rss-en-top"]


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_world_news(max_items: int = 10) -> dict:
        """Get the latest global/world news headlines (Deutsche Welle top stories).

        Use this for "what's happening in the world" and the daily briefing.
        Returns structured items (title, link, source, published, summary).
        """
        from ..sources.rss import fetch_news

        env = os.getenv("WORLD_NEWS_FEEDS", "").strip()
        feeds = [f.strip() for f in env.split(",") if f.strip()] or DEFAULT_WORLD_FEEDS
        items = fetch_news(feeds, since_hours=48, max_items=max_items)
        return {"count": len(items), "items": [i.as_dict() for i in items]}
