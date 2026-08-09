"""Natural-language todo intent parsing (WhatsApp text / STT turns)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_ADD_TODO = re.compile(
    r"^(?:\[Audio\]\s*)?(?:add\s+(?:a\s+)?todo[:\s]+)(.+?)\.?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedTodo:
    title: str


def parse_todo(utterance: str) -> ParsedTodo:
    """Parse 'Add todo: buy oat milk.' (and audio-prefixed variants)."""
    text = (utterance or "").strip()
    match = _ADD_TODO.match(text)
    if not match:
        raise ValueError(f"not a todo add utterance: {utterance!r}")
    title = match.group(1).strip().rstrip(".")
    if not title:
        raise ValueError("todo title is empty")
    return ParsedTodo(title=title)


def looks_like_todo_add(body: str) -> bool:
    """Fast intent check for agent routing."""
    return bool(_ADD_TODO.match((body or "").strip()))
