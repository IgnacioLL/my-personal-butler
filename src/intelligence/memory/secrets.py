"""Reject or redact secret-like patterns from memory file writes."""

from __future__ import annotations

import re
from typing import Any

# Basic patterns — expand as self-mod scanner lands (INV-SELF-004).
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(
        r"(?i)\b(api[_-]?key|password|secret|token|bearer)\b\s*[:=]\s*\S+"
    ),
    re.compile(r"(?i)\bghp_[a-zA-Z0-9]{20,}\b"),
    re.compile(r"(?i)\bxox[baprs]-[a-zA-Z0-9-]{10,}\b"),
)


class MemorySecretsError(ValueError):
    """Raised when content looks like a credential and must not be stored in memory."""


def contains_secret_pattern(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def redact_secrets(text: str) -> str:
    """Replace matched secret substrings with a fixed redaction token."""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def validate_no_secrets(value: Any, *, path: str = "root") -> None:
    """Recursively scan strings in *value*; raise if any secret pattern matches."""
    if isinstance(value, str):
        if contains_secret_pattern(value):
            raise MemorySecretsError(
                f"secret-like pattern rejected at {path!r} — use secret store, not memory files"
            )
        return
    if isinstance(value, dict):
        for key, child in value.items():
            validate_no_secrets(child, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for idx, child in enumerate(value):
            validate_no_secrets(child, path=f"{path}[{idx}]")
        return
