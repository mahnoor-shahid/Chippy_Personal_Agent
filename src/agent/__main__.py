"""CLI entry: test the brain from the terminal, no WhatsApp needed.

    python -m src.agent "What's new in AI in the last 24 hours?"
    python -m src.agent                 # uses a default digest prompt
"""
from __future__ import annotations

import asyncio
import sys

from .brain import ConfigError, run_agent

DEFAULT_PROMPT = "What's new in AI in the last 24 hours? Give me concise bullet points."


def _root_cause(exc: BaseException) -> BaseException:
    """MCP runs in a task group, so errors arrive wrapped in an ExceptionGroup."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


def main() -> None:
    # Windows consoles default to cp1252, which can't print emoji/bullets/arrows.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    prompt = " ".join(sys.argv[1:]).strip() or DEFAULT_PROMPT
    try:
        print(asyncio.run(run_agent(prompt)))
    except ConfigError as e:
        print(f"\nConfiguration error: {e}\n", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        root = _root_cause(e)
        print(f"\nAgent error: {type(root).__name__}: {root}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
