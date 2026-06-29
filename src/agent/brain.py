"""The agent brain: connect to our MCP server, expose its tools to an LLM, and
run the prompt -> tool-call -> answer loop.

This is the single reusable entry point. WhatsApp and the scheduler will both
just call `run_agent(prompt)`.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .llm.base import LLMProvider, Tool
from .persona import system_prompt

load_dotenv()

# Path to the MCP server we spawn. Launched by file path so its sys.path
# bootstrap handles imports regardless of cwd.
SERVER_PATH = str(Path(__file__).resolve().parents[1] / "mcp_server" / "server.py")


class ConfigError(RuntimeError):
    """Raised when required LLM configuration is missing."""


SUPPORTED_PROVIDERS = ("openrouter", "anthropic", "openai", "ollama")


def _require(var: str, provider: str) -> str:
    val = os.getenv(var, "").strip()
    if not val:
        raise ConfigError(
            f"{var} is required for LLM_PROVIDER={provider!r} but is not set. "
            f"Add it to your .env file."
        )
    return val


def make_provider(model_override: str | None = None) -> LLMProvider:
    """Build the configured LLM provider. A real API key is mandatory.

    `model_override` lets callers (e.g. the scheduler) use a different model than
    the default LLM_MODEL while keeping the same provider/credentials.
    """
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    model = (model_override or os.getenv("LLM_MODEL", "")).strip()

    if not provider:
        raise ConfigError(
            "LLM_PROVIDER is not set. Set it in .env to one of: "
            f"{', '.join(SUPPORTED_PROVIDERS)}."
        )

    if provider == "openrouter":
        key = _require("OPENROUTER_API_KEY", provider)
        from .llm.openai_provider import OpenAIProvider

        return OpenAIProvider(
            model or "openai/gpt-4o-mini",
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/personal-agent",
                "X-Title": "Personal Agent",
            },
        )

    if provider == "anthropic":
        _require("ANTHROPIC_API_KEY", provider)
        from .llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(model or "claude-haiku-4-5")

    if provider == "openai":
        _require("OPENAI_API_KEY", provider)
        from .llm.openai_provider import OpenAIProvider

        return OpenAIProvider(model or "gpt-4o-mini")

    if provider == "ollama":
        # Local open-source models. No API key — Ollama exposes an
        # OpenAI-compatible endpoint, so we reuse the same provider.
        # Use a tool-capable model (e.g. llama3.1, qwen2.5, mistral-nemo).
        from .llm.openai_provider import OpenAIProvider

        base = os.getenv("OLLAMA_HOST", "http://localhost:11434/v1").strip()
        return OpenAIProvider(model or "llama3.1", api_key="ollama", base_url=base)

    raise ConfigError(
        f"Unknown LLM_PROVIDER={provider!r}. Use one of: "
        f"{', '.join(SUPPORTED_PROVIDERS)}."
    )


def _result_text(result) -> str:
    """Flatten an MCP CallToolResult into plain text (our tools return JSON text)."""
    parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    return "\n".join(parts) if parts else "(no content)"


async def run_agent(
    prompt: str, conversation_id: str | None = None, model: str | None = None
) -> str:
    """Run one full turn against the MCP server and return the assistant's reply.

    If `conversation_id` is given, prior turns are loaded as memory and this
    exchange is persisted, so follow-up messages have context. `model` overrides
    the default LLM_MODEL for this call (used by the scheduler).
    """
    provider = make_provider(model)  # fail fast on bad config, before spawning server

    history: list[dict] = []
    if conversation_id:
        from . import storage

        history = await asyncio.to_thread(storage.recent_messages, conversation_id)

    # Inject the user identity into the server process so per-user tools
    # (reminders, remembered facts) are scoped securely — the LLM never controls
    # whose data it touches.
    server_env = {**os.environ}
    if conversation_id:
        server_env["CONVERSATION_ID"] = conversation_id
    server = StdioServerParameters(
        command=sys.executable, args=[SERVER_PATH], env=server_env
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            tools = [
                Tool(t.name, t.description or "", t.inputSchema) for t in listed.tools
            ]

            async def execute(name: str, args: dict) -> str:
                return _result_text(await session.call_tool(name, args))

            reply = await provider.run(
                system=system_prompt(),
                user=prompt,
                tools=tools,
                execute=execute,
                history=history,
            )

    if conversation_id:
        from . import storage

        await asyncio.to_thread(storage.save_message, conversation_id, "user", prompt)
        await asyncio.to_thread(storage.save_message, conversation_id, "assistant", reply)

    return reply
