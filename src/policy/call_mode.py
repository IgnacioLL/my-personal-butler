"""Call-mode policy helpers — INV-APPR-005 for production + harness.

During a live call session only read-only tools are available. Buy / book /
self-mod-apply are hard-forbidden. Production skill policy lives at
``src/skills/voice-calls/policy.json`` and
``config/production/call-mode.policy.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from channels.voice.allowlist import (
    CALL_MODE_ALLOWED_TOOLS,
    CALL_MODE_FORBIDDEN_TOOLS,
    call_mode_block_reason,
    is_call_mode_allowed,
)

# Repo-relative policy paths (stdlib Path; no package installs).
_REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_POLICY_PATH = _REPO_ROOT / "src" / "skills" / "voice-calls" / "policy.json"
PRODUCTION_POLICY_PATH = (
    _REPO_ROOT / "config" / "production" / "call-mode.policy.json"
)


def load_call_mode_policy(path: Path | str | None = None) -> dict[str, Any]:
    """Load call-mode policy JSON (skill policy by default)."""
    target = Path(path) if path is not None else SKILL_POLICY_PATH
    raw = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"call-mode policy must be an object: {target}")
    return raw


def allowed_tools_from_policy(policy: dict[str, Any]) -> frozenset[str]:
    call_mode = policy.get("call_mode") or policy
    tools = call_mode.get("allowed_tools") or policy.get("allowed_tools") or []
    return frozenset(str(t) for t in tools)


def forbidden_tools_from_policy(policy: dict[str, Any]) -> frozenset[str]:
    call_mode = policy.get("call_mode") or policy
    tools = call_mode.get("forbidden_tools") or policy.get("forbidden_tools") or []
    return frozenset(str(t) for t in tools)


def policy_matches_allowlist(policy: dict[str, Any] | None = None) -> list[str]:
    """Return mismatch messages if policy drifts from code allowlist (empty = ok)."""
    data = policy if policy is not None else load_call_mode_policy()
    failures: list[str] = []
    allowed = allowed_tools_from_policy(data)
    forbidden = forbidden_tools_from_policy(data)
    if allowed != CALL_MODE_ALLOWED_TOOLS:
        failures.append(
            f"allowed_tools mismatch: policy={sorted(allowed)} "
            f"code={sorted(CALL_MODE_ALLOWED_TOOLS)}"
        )
    if forbidden != CALL_MODE_FORBIDDEN_TOOLS:
        failures.append(
            f"forbidden_tools mismatch: policy={sorted(forbidden)} "
            f"code={sorted(CALL_MODE_FORBIDDEN_TOOLS)}"
        )
    return failures


def gate_tool(tool: str, *, call_mode_active: bool) -> Optional[str]:
    """If call mode is active, return block reason for *tool*; else None."""
    if not call_mode_active:
        return None
    return call_mode_block_reason(tool)


__all__ = [
    "CALL_MODE_ALLOWED_TOOLS",
    "CALL_MODE_FORBIDDEN_TOOLS",
    "PRODUCTION_POLICY_PATH",
    "SKILL_POLICY_PATH",
    "allowed_tools_from_policy",
    "call_mode_block_reason",
    "forbidden_tools_from_policy",
    "gate_tool",
    "is_call_mode_allowed",
    "load_call_mode_policy",
    "policy_matches_allowlist",
]
