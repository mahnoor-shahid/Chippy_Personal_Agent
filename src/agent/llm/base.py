"""The provider-agnostic contract.

The brain owns the MCP connection and gives each provider two things:
  - a normalized list of `Tool`s (name + description + JSON schema), and
  - an async `execute(name, args)` it can call to run a tool.

Each provider implements `run()` using its own native message format internally,
so we never try to translate message history between Anthropic and OpenAI.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema, straight from MCP


# Runs one MCP tool and returns its text result.
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


class LLMProvider(Protocol):
    async def run(
        self,
        *,
        system: str,
        user: str,
        tools: list[Tool],
        execute: ToolExecutor,
        history: list[dict] | None = None,
    ) -> str:
        """Answer `user`, calling tools via `execute` as needed. Returns text.

        `history` is prior turns as [{"role": "user"|"assistant", "content": str}]
        in chronological order, prepended so the model has conversation memory.
        """
        ...
