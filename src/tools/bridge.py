"""Bridge OpenClaw tool calls to harness ActionGateway + services."""

from __future__ import annotations

from typing import Any, Optional

from operations.heartbeat import HeartbeatService
from policy.action_gateway import ActionGateway, ExecuteResult, ProposeResult
from tools.registry import ACTION_FOR_TOOL


class SkillToolBridge:
    """Dispatch documented tool names through the same gates as CI harness."""

    def __init__(
        self,
        gateway: ActionGateway,
        *,
        heartbeat: HeartbeatService | None = None,
    ) -> None:
        self.gateway = gateway
        self.heartbeat = heartbeat

    def call_tool(self, tool_name: str, payload: dict[str, Any] | None = None) -> Any:
        action_type = ACTION_FOR_TOOL.get(tool_name)
        if action_type is None:
            raise ValueError(f"unknown tool: {tool_name}")

        if action_type == "heartbeat_morning_brief":
            if self.heartbeat is None:
                raise RuntimeError("heartbeat service not attached")
            result = self.heartbeat.maybe_morning_brief()
            return result.to_dict()

        if action_type == "heartbeat_weekly_review":
            if self.heartbeat is None:
                raise RuntimeError("heartbeat service not attached")
            result = self.heartbeat.maybe_weekly_review()
            return result.to_dict()

        propose = self.gateway.propose(
            action_type,
            summary=f"tool:{tool_name}",
            payload=payload or {},
        )
        if propose.executed:
            return propose.auto_result
        if propose.approval_id is None:
            return ProposeResult(
                ok=propose.ok,
                reason=propose.reason,
                tier=propose.tier,
            )
        return propose

    def accept_and_execute(self, approval_id: str) -> ExecuteResult:
        self.gateway.accept(approval_id)
        return self.gateway.execute(approval_id)


__all__ = ["SkillToolBridge"]
