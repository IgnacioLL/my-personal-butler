"""Call-mode tool allowlist — INV-APPR-005.

During a live call session only read-only tools are available.
Buy / book / self-mod-apply are hard-forbidden mid-call.
"""

from __future__ import annotations

from typing import Optional

# Read-only tools permitted while a call session is active.
CALL_MODE_ALLOWED_TOOLS = frozenset(
    {
        "calendar_read",
        "memory_read",
        "todo_read",
        "source_read",
    }
)

# Hard actions that must never run mid-call (INV-APPR-005).
CALL_MODE_FORBIDDEN_TOOLS = frozenset(
    {
        "buy",
        "book",
        "self_mod_apply",
    }
)


def is_call_mode_allowed(tool: str) -> bool:
    """True iff *tool* may be invoked during an active call session."""
    return tool in CALL_MODE_ALLOWED_TOOLS


def call_mode_block_reason(tool: str) -> Optional[str]:
    """Return a stable block reason, or None if the tool is allowed."""
    if tool in CALL_MODE_ALLOWED_TOOLS:
        return None
    if tool in CALL_MODE_FORBIDDEN_TOOLS:
        return "call_mode_forbidden_hard_action"
    return "call_mode_tool_not_allowlisted"
