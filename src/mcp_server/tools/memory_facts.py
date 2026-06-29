"""Long-term facts/preferences the user asks Chippy to remember.

Distinct from conversation memory: these are durable, explicitly-saved facts the
user wants recalled across any future chat. Per-user, stored in the DB.
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def remember_fact(fact: str) -> dict:
        """Save a durable fact or preference about the user to recall later.

        Use when the user says things like "remember that I ...", "my X is ...",
        "I prefer ...". Keep each saved fact concise and self-contained.
        """
        from ..store import add_fact

        fid = add_fact(fact)
        return {"ok": True, "id": fid, "fact": fact}

    @mcp.tool()
    def recall_facts() -> dict:
        """Recall everything the user has asked Chippy to remember about them."""
        from ..store import list_facts

        facts = list_facts()
        return {"count": len(facts), "facts": facts}
