"""OpenAI-compatible provider. Used for both OpenAI and OpenRouter (which speaks
the same wire protocol behind a different base URL).

Named `openai_provider` (not `openai`) so it doesn't shadow the SDK.
"""
from __future__ import annotations

import json

from .base import Tool, ToolExecutor


class OpenAIProvider:
    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        from openai import AsyncOpenAI  # imported lazily

        kwargs: dict = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        if default_headers:
            kwargs["default_headers"] = default_headers
        self.client = AsyncOpenAI(**kwargs)  # falls back to OPENAI_API_KEY env
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
        oa_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]
        messages: list[dict] = [
            {"role": "system", "content": system},
            *(history or []),
            {"role": "user", "content": user},
        ]

        while True:
            resp = await self.client.chat.completions.create(
                model=self.model, messages=messages, tools=oa_tools
            )
            # Free/rate-limited models sometimes return an error payload with no
            # choices instead of a normal completion — surface it clearly.
            if not resp.choices:
                err = getattr(resp, "error", None) or resp
                raise RuntimeError(f"LLM returned no choices (likely rate-limited): {err}")
            msg = resp.choices[0].message

            if not msg.tool_calls:
                return msg.content or ""

            messages.append(msg.model_dump(exclude_none=True))  # assistant turn w/ tool_calls
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                output = await execute(tc.function.name, args)
                messages.append(
                    {"role": "tool", "tool_call_id": tc.id, "content": output}
                )
