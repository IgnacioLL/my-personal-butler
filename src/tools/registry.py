"""Tool name ↔ action_type registry for PROD-04 skills pack."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / "src" / "skills"
_SCHEMAS_PATH = Path(__file__).resolve().parent / "schemas.json"

SKILL_PACK_NAMES: tuple[str, ...] = (
    "personal-memory",
    "reminders-habits",
    "personal-todos",
    "heartbeat-ops",
)

# OpenClaw tool name → ActionGateway action_type (harness contract).
ACTION_FOR_TOOL: dict[str, str] = {
    "memory_read": "memory_read",
    "memory_update": "memory_update",
    "reminder_create": "reminder_create",
    "habit_create": "habit_create",
    "reminder_list": "reminder_list",
    "reminder_snooze": "reminder_snooze",
    "reminder_cancel": "reminder_cancel",
    "todo_add": "todo_add",
    "todo_complete": "todo_complete",
    "todo_read": "todo_read",
    "todo_cancel": "todo_cancel",
    "heartbeat_morning_brief": "heartbeat_morning_brief",
    "heartbeat_weekly_review": "heartbeat_weekly_review",
}

TOOL_FOR_ACTION: dict[str, str] = {v: k for k, v in ACTION_FOR_TOOL.items()}

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
_NAME_RE = re.compile(r"^name:\s*([^\s#]+)", re.MULTILINE)
_DESC_RE = re.compile(r"^description:\s*(.+)$", re.MULTILINE)


def load_tool_schemas() -> list[dict[str, Any]]:
    """Load documented tool schemas for Gateway registration."""
    raw = json.loads(_SCHEMAS_PATH.read_text(encoding="utf-8"))
    tools = raw.get("tools") or []
    return list(tools)


def validate_skill_pack() -> dict[str, Any]:
    """Structural validation for CI — SKILL.md presence and frontmatter."""
    errors: list[str] = []
    found: list[str] = []

    for name in SKILL_PACK_NAMES:
        skill_dir = _SKILLS_ROOT / name
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            errors.append(f"missing {skill_md}")
            continue
        text = skill_md.read_text(encoding="utf-8")
        if not _FRONTMATTER_RE.search(text):
            errors.append(f"{name}: no YAML frontmatter")
        name_m = _NAME_RE.search(text)
        desc_m = _DESC_RE.search(text)
        if not name_m:
            errors.append(f"{name}: missing name in frontmatter")
        elif name_m.group(1) != name:
            errors.append(f"{name}: frontmatter name {name_m.group(1)!r} != dir")
        if not desc_m:
            errors.append(f"{name}: missing description in frontmatter")
        found.append(name)

    schema_tools = {t["name"] for t in load_tool_schemas()}
    for tool_name in ACTION_FOR_TOOL:
        if tool_name not in schema_tools:
            errors.append(f"schema missing tool {tool_name}")

    prod_cfg = _REPO_ROOT / "config" / "openclaw" / "skills-production.json5"
    if not prod_cfg.is_file():
        errors.append(f"missing {prod_cfg}")

    return {
        "ok": not errors,
        "skills": found,
        "errors": errors,
        "tool_count": len(schema_tools),
    }


__all__ = [
    "ACTION_FOR_TOOL",
    "SKILL_PACK_NAMES",
    "TOOL_FOR_ACTION",
    "load_tool_schemas",
    "validate_skill_pack",
]
