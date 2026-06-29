"""Anthropic (Claude) provider. Requires ANTHROPIC_API_KEY.

Named `anthropic_provider` (not `anthropic`) so it doesn't shadow the SDK.
"""
from __future__ import annotations

from .base import Tool, ToolExecutor


class AnthropicProvider:
    def __init__(self, model: str) -> None:
        from anthropic import AsyncAnthropic  # imported lazily so no key = no import

        self.client = AsyncAnthropic()  # reads ANTHROPIC_API_KEY
        self.model = model

    async def run(
        self,
        *,
        system: str,
        user: str,
        tools: list[Tool],
        execute: ToolExecutor,
        history: list[dict] | None = None,
    ) -> str:
        anthropic_tools = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in tools
        ]
        messages: list[dict] = list(history or []) + [{"role": "user", "content": user}]

        while True:
            resp = await self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system,
                tools=anthropic_tools,
                messages=messages,
            )

            if resp.stop_reason != "tool_use":
                return "".join(b.text for b in resp.content if b.type == "text")

            # Echo the assistant turn back, then answer every tool_use block.
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    output = await execute(block.name, dict(block.input))
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": output}
                    )
            messages.append({"role": "user", "content": results})
