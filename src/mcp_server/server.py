"""FastMCP application entry point.

This file does one thing: create the MCP server and register every tool module.
Adding a feature = import its module and call `register(mcp)`.

Run:
    mcp dev src/mcp_server/server.py       # interactive inspector
    python -m src.mcp_server.server        # stdio server
"""
from __future__ import annotations

import sys
from pathlib import Path

# `mcp dev` imports this file by PATH, so it has no parent package and relative
# imports (`from .tools ...`) fail. Put the project root on sys.path and use an
# absolute import so the entry point works as a module, a script, OR by-path.
_ROOT = Path(__file__).resolve().parents[2]  # d:\personal_agent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP

from src.mcp_server.tools import (
    ai_news,
    ai_newsletter,
    memory_facts,
    psx,
    reminders,
    web_search,
    weather,
    world_news,
    youtube,
)

# Declared so `mcp dev`'s isolated environment installs them too.
mcp = FastMCP(
    "personal-agent",
    dependencies=[
        "feedparser",
        "httpx",
        "ddgs",
        "sqlalchemy",
        "lxml",
        "youtube-transcript-api",
    ],
)

# --- register tools (one line per capability) ---
ai_news.register(mcp)
ai_newsletter.register(mcp)
world_news.register(mcp)
psx.register(mcp)
web_search.register(mcp)
reminders.register(mcp)
memory_facts.register(mcp)
weather.register(mcp)
youtube.register(mcp)


def main() -> None:
    mcp.run()  # defaults to stdio transport


if __name__ == "__main__":
    main()
