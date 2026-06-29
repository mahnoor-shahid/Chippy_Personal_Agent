"""The `get_ai_newsletter` tool — latest issue of the 'What's Up in AI' newsletter.

This is the preferred source for the daily digest: it returns the full text of the
most recent issue so the LLM can boil it down to highlighted bullet points.
"""
from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

DEFAULT_NEWSLETTER = "https://whatsupinai.beehiiv.com"


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_ai_newsletter() -> dict:
        """Fetch the latest issue of the configured AI newsletters (full text each).

        Use this for the daily AI digest. For each newsletter, summarize its
        `content` into short, punchy bullets grouped by section, keeping the key
        highlights. Skip ads / sponsor blocks (e.g. paid promos, "engaged Beehiiv
        to publish"). Configure sources via NEWSLETTER_URLS (comma-separated).
        """
        from ..sources.newsletter import fetch_latest_post

        env = os.getenv("NEWSLETTER_URLS") or os.getenv("NEWSLETTER_URL") or DEFAULT_NEWSLETTER
        urls = [u.strip() for u in env.split(",") if u.strip()]

        issues = []
        for url in urls:
            try:
                issues.append(fetch_latest_post(url, max_chars=4500))
            except Exception as e:  # one bad source shouldn't sink the digest
                issues.append({"url": url, "error": f"{type(e).__name__}: {e}"})
        return {"count": len(issues), "newsletters": issues}
