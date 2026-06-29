"""Turn the model's Markdown-ish output into clean WhatsApp text.

WhatsApp supports *bold*, _italic_, ~strike~, ```mono``` — but NOT Markdown
headers (#), bold (**), tables, or [text](url) links. The model emits Markdown,
so we normalize it here so messages look tidy instead of full of `###` / `**`.
"""
from __future__ import annotations

import re

_HR = re.compile(r"^\s*([-*_])\1{2,}\s*$")          # --- *** ___
_HEADER = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*$")     # ## Heading
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")         # - item / * item
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_BOLD_U = re.compile(r"__(.+?)__")
_MULTI_NL = re.compile(r"\n{3,}")


def to_whatsapp(text: str) -> str:
    if not text:
        return text

    lines: list[str] = []
    for line in text.splitlines():
        if _HR.match(line):
            continue  # drop horizontal rules entirely
        h = _HEADER.match(line)
        if h:
            lines.append(f"*{h.group(1)}*")  # heading -> bold line
            continue
        b = _BULLET.match(line)
        if b:
            lines.append(f"{b.group(1)}• {b.group(2)}")
            continue
        lines.append(line)
    text = "\n".join(lines)

    text = _LINK.sub(r"\1: \2", text)   # [title](url) -> "title: url"
    text = _BOLD.sub(r"*\1*", text)     # **x** -> *x*
    text = _BOLD_U.sub(r"*\1*", text)   # __x__ -> *x*
    text = _MULTI_NL.sub("\n\n", text)  # collapse big gaps
    return text.strip()


def _wrap_words(line: str, size: int) -> list[str]:
    out, cur = [], ""
    for word in line.split(" "):
        cand = word if not cur else f"{cur} {word}"
        if len(cand) <= size:
            cur = cand
        else:
            if cur:
                out.append(cur)
            while len(word) > size:
                out.append(word[:size])
                word = word[size:]
            cur = word
    if cur:
        out.append(cur)
    return out


def split_message(text: str, size: int) -> list[str]:
    """Split into <=size chunks, preferring paragraph then line then word breaks."""
    text = (text or "(empty reply)").strip()
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    cur = ""

    def flush() -> None:
        nonlocal cur
        if cur.strip():
            chunks.append(cur.strip())
        cur = ""

    for para in text.split("\n\n"):
        if len(para) <= size and len(cur) + len(para) + 2 <= size:
            cur = para if not cur else f"{cur}\n\n{para}"
            continue
        flush()
        if len(para) <= size:
            cur = para
            continue
        for line in para.split("\n"):
            for piece in ([line] if len(line) <= size else _wrap_words(line, size)):
                if len(cur) + len(piece) + 1 > size:
                    flush()
                cur = piece if not cur else f"{cur}\n{piece}"
    flush()
    return chunks or ["(empty reply)"]
