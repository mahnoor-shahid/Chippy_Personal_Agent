"""Latest video + transcript for a YouTube channel.

- Resolve a channel handle/URL to its channel_id (a consent cookie avoids the EU
  cookie wall), then read the newest upload from YouTube's free RSS feed.
- Fetch the transcript via youtube-transcript-api (free, no key).
"""
from __future__ import annotations

import re

import feedparser
import httpx

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_COOKIES = {"CONSENT": "YES+cb", "SOCS": "CAI"}  # skip the EU consent interstitial


def resolve_channel_id(channel: str) -> str | None:
    if re.fullmatch(r"UC[\w-]{22}", channel):
        return channel
    url = channel if channel.startswith("http") else f"https://www.youtube.com/{channel.lstrip('/')}"
    html = httpx.get(url, headers=_UA, cookies=_COOKIES, timeout=25, follow_redirects=True).text
    m = re.search(r'"externalId":"(UC[\w-]{22})"', html) or re.search(r"channel/(UC[\w-]{22})", html)
    return m.group(1) if m else None


def latest_video(channel: str) -> dict | None:
    cid = resolve_channel_id(channel)
    if not cid:
        return None
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
    if not feed.entries:
        return None
    e = feed.entries[0]
    return {
        "video_id": e.get("yt_videoid"),
        "title": e.get("title"),
        "url": e.get("link"),
        "published": e.get("published"),
    }


def get_transcript(video_id: str, max_chars: int = 12000) -> str:
    """Fetch a transcript in any available language (prefer English, else
    translate to English when possible; otherwise return the original language)."""
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    listing = api.list(video_id)

    transcript = None
    try:
        transcript = listing.find_transcript(["en", "en-US", "en-GB"])
    except Exception:
        transcript = next(iter(listing), None)  # e.g. Hindi auto-generated

    if transcript is None:
        raise RuntimeError("No transcript available for this video.")

    try:
        if transcript.language_code.split("-")[0] != "en" and transcript.is_translatable:
            transcript = transcript.translate("en")
    except Exception:
        pass  # fall back to original language; the LLM can still read it

    fetched = transcript.fetch()
    return " ".join(s.text for s in fetched)[:max_chars]


def latest_video_transcript(channel: str) -> dict:
    v = latest_video(channel)
    if not v:
        return {"error": f"Could not find the latest video for {channel!r}."}
    v["channel"] = channel
    try:
        v["transcript"] = get_transcript(v["video_id"])
    except Exception as e:
        v["transcript"] = ""
        v["transcript_error"] = f"{type(e).__name__}: {e}"
    return v
