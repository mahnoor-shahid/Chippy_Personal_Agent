"""Fetch the latest issue of a beehiiv newsletter (e.g. 'What's Up in AI').

beehiiv is a JS app, but each post page is server-rendered for SEO, so we can
pull the latest post link off the homepage and extract its text blocks with lxml.
No API key. Returns raw text; the LLM turns it into highlighted bullets.
"""
from __future__ import annotations

import re

import httpx
from lxml import html as lhtml

_UA = {"User-Agent": "Mozilla/5.0 (personal-agent/1.0)"}


def _extract_text(raw: str) -> str:
    doc = lhtml.fromstring(raw)
    for bad in doc.xpath("//script|//style|//noscript"):
        bad.getparent().remove(bad)

    seen: set[str] = set()
    blocks: list[str] = []
    for el in doc.xpath("//h1|//h2|//h3|//p|//li"):
        t = " ".join(el.text_content().split())
        if len(t) > 25 and t not in seen:
            seen.add(t)
            blocks.append(t)
    return "\n".join(blocks)


def fetch_latest_post(base_url: str, *, max_chars: int = 8000) -> dict:
    """Return {title, url, content} for the newsletter's most recent issue."""
    base = base_url.rstrip("/")
    home = httpx.get(base + "/", headers=_UA, timeout=25, follow_redirects=True).text

    slugs: list[str] = []
    for m in re.findall(r"/p/([a-z0-9\-]+)", home):
        if m not in slugs:
            slugs.append(m)
    if not slugs:
        return {"error": f"No posts found at {base}"}

    url = f"{base}/p/{slugs[0]}"  # homepage lists newest first
    raw = httpx.get(url, headers=_UA, timeout=25, follow_redirects=True).text

    doc = lhtml.fromstring(raw)
    og = doc.xpath('//meta[@property="og:title"]/@content')
    title = (og[0].strip() if og else slugs[0].replace("-", " ")).strip()

    return {"title": title, "url": url, "content": _extract_text(raw)[:max_chars]}
