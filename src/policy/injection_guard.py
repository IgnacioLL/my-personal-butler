"""Light injection defenses for untrusted ingress and browser page text."""

from __future__ import annotations

import re
from typing import Iterable

# Untrusted surfaces: WhatsApp bodies, stub browser pages, pasted diffs.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"APPROVE\s+ALL", re.IGNORECASE),
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"ignore\s+all\s+safety", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"auto[-\s]?approve\s+everything", re.IGNORECASE),
    re.compile(r"bypass\s+approval", re.IGNORECASE),
)


def scan_untrusted_text(text: str | None) -> tuple[bool, list[str]]:
    """Return (has_injection, matched_pattern_names)."""
    if not text:
        return False, []
    matched: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            matched.append(pattern.pattern)
    return bool(matched), matched


def is_auto_approve_injection(text: str | None) -> bool:
    """Browser/page text claiming auto-approve must not bypass Accept API."""
    has_injection, _ = scan_untrusted_text(text)
    return has_injection


def strip_for_display(text: str, *, max_len: int = 240) -> str:
    """Truncate untrusted text for outbound cards — never treat as commands."""
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3] + "..."


def any_injection(texts: Iterable[str | None]) -> bool:
    return any(scan_untrusted_text(t)[0] for t in texts)


__all__ = [
    "any_injection",
    "is_auto_approve_injection",
    "scan_untrusted_text",
    "strip_for_display",
]
