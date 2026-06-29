"""Raw news fetching. No LLM, no formatting decisions here.

This layer's only job: turn a list of RSS/Atom feed URLs into a clean,
de-duplicated, time-filtered list of NewsItem. The MCP tool wraps this; the
LLM brain later turns items into bullet points.
"""
from __future__ import annotations

import html
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class NewsItem:
    title: str
    link: str
    source: str
    published: str  # ISO 8601, UTC
    summary: str

    def as_dict(self) -> dict:
        return asdict(self)


def _clean(text: str, limit: int = 400) -> str:
    """Strip HTML tags/entities and collapse whitespace."""
    text = _TAG_RE.sub(" ", text or "")
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _published_dt(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)


def fetch_news(
    feeds: list[str],
    *,
    since_hours: int = 24,
    max_items: int = 25,
) -> list[NewsItem]:
    """Fetch and merge feeds, keeping items newer than `since_hours`.

    Items without a parseable date are kept (some feeds omit dates) but sorted
    last. Results are de-duplicated by link and capped at `max_items`.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    items: list[NewsItem] = []
    seen: set[str] = set()

    for url in feeds:
        parsed = feedparser.parse(url)
        source = _clean(parsed.feed.get("title", url), limit=60) or url
        for entry in parsed.entries:
            link = entry.get("link", "")
            if not link or link in seen:
                continue
            dt = _published_dt(entry)
            if dt is not None and dt < cutoff:
                continue
            seen.add(link)
            items.append(
                NewsItem(
                    title=_clean(entry.get("title", "(untitled)"), limit=200),
                    link=link,
                    source=source,
                    published=(dt or datetime.now(timezone.utc)).isoformat(),
                    summary=_clean(entry.get("summary", "")),
                )
            )

    items.sort(key=lambda i: i.published, reverse=True)
    return items[:max_items]
