"""Central config, read from environment (with sensible defaults).

Keeping this in one place means tools never reach into os.environ directly.
"""
from __future__ import annotations

import os

# Default AI/ML news feeds. Override with AI_NEWS_FEEDS (comma-separated).
DEFAULT_AI_NEWS_FEEDS: list[str] = [
    "https://hnrss.org/newest?q=AI+OR+LLM+OR+%22machine+learning%22",  # Hacker News
    "http://export.arxiv.org/rss/cs.AI",                                # arXiv cs.AI
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://venturebeat.com/category/ai/feed/",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://huggingface.co/blog/feed.xml",
]


def ai_news_feeds() -> list[str]:
    raw = os.getenv("AI_NEWS_FEEDS", "").strip()
    if not raw:
        return DEFAULT_AI_NEWS_FEEDS
    return [u.strip() for u in raw.split(",") if u.strip()]
