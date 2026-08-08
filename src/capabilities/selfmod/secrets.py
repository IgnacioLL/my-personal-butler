"""Secret-pattern scanner for proposed self-mod diffs (INV-SELF-004)."""

from __future__ import annotations

from typing import Any

from intelligence.memory.secrets import (
    contains_secret_pattern,
    redact_secrets,
)


class SelfModSecretsError(ValueError):
    """Raised when a proposed patch contains credential-like content."""


def scan_diff_for_secrets(text: str) -> list[str]:
    """Return human-readable hits if *text* looks like it embeds secrets."""
    if not text:
        return []
    if contains_secret_pattern(text):
        return ["secret_pattern_match"]
    return []


def validate_patch_no_secrets(value: Any, *, path: str = "patch") -> None:
    """Recursively reject secret-like strings in patch payloads."""
    if isinstance(value, str):
        if contains_secret_pattern(value):
            raise SelfModSecretsError(
                f"secret-like pattern rejected at {path!r} — "
                "credentials stay in env/secret store, not commits"
            )
        return
    if isinstance(value, dict):
        for key, child in value.items():
            validate_patch_no_secrets(child, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for idx, child in enumerate(value):
            validate_patch_no_secrets(child, path=f"{path}[{idx}]")
        return


def redact_patch_text(text: str) -> str:
    return redact_secrets(text)
