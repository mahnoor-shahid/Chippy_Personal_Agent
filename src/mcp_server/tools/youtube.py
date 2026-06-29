"""The `get_latest_video_transcript` tool — newest video of a channel + transcript.

Powers Chippy's daily opinion/LinkedIn posts: fetch the latest video from a
channel and its transcript so Chippy can write an opinionated take on it.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def get_latest_video_transcript(channel: str) -> dict:
        """Get a YouTube channel's newest video and its transcript.

        `channel` may be a handle URL (https://www.youtube.com/@TLDRnews), an
        @handle, or a UC… channel id. Returns title, url, published, transcript.
        Use this to write an opinion piece / LinkedIn post about the latest video.
        """
        from ..sources.youtube import latest_video_transcript

        return latest_video_transcript(channel)
