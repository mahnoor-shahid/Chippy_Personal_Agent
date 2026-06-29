"""Reminders / to-dos — per-user, stored in the DB.

Scoped to the current user via store.current_user() (set by the agent brain).
"""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def add_reminder(text: str, due: str = "") -> dict:
        """Add a reminder or to-do item for the user.

        Args:
            text: What to be reminded of / the task.
            due: Optional free-text time like "tomorrow 6pm" or "Friday".
        """
        from ..store import add_reminder as _add

        rid = _add(text, due or None)
        return {"ok": True, "id": rid, "text": text, "due": due or None}

    @mcp.tool()
    def list_reminders(include_done: bool = False) -> dict:
        """List the user's reminders / to-dos (open ones by default)."""
        from ..store import list_reminders as _list

        items = _list(include_done)
        return {"count": len(items), "reminders": items}

    @mcp.tool()
    def complete_reminder(id: int) -> dict:
        """Mark a reminder as done by its id."""
        from ..store import complete_reminder as _complete

        return {"ok": _complete(id), "id": id}
