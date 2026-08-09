"""Android Status screen API double — gateway health + kill switches.

Mirrors the production companion Status surface from
agent-plan/channels/android-companion.md and config/android.example.yaml.
Gateway owns kill-switch state; Android renders and toggles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from policy.action_gateway import ActionGateway
from policy.approvals import ApprovalStatus


@dataclass(frozen=True)
class StatusProjection:
    """Android-facing Status screen (v1 control plane)."""

    gateway_online: bool
    paired: bool
    agent_paused: bool
    spend_frozen: bool
    self_mod_frozen: bool
    pending_approvals: int
    open_todos: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "gateway_online": self.gateway_online,
            "paired": self.paired,
            "agent_paused": self.agent_paused,
            "spend_frozen": self.spend_frozen,
            "self_mod_frozen": self.self_mod_frozen,
            "pending_approvals": self.pending_approvals,
            "open_todos": self.open_todos,
            "kill_switches": {
                "pause_agent": self.agent_paused,
                "freeze_spending": self.spend_frozen,
                "freeze_self_mod": self.self_mod_frozen,
            },
        }


class AndroidStatusApi:
    """API-level Android Status screen — kill switches + counts."""

    def __init__(
        self,
        gateway: ActionGateway,
        *,
        gateway_online: bool = True,
        paired: bool = True,
    ) -> None:
        self.gateway = gateway
        self.gateway_online = gateway_online
        self.paired = paired

    def get(self) -> StatusProjection:
        todos = self.gateway.todos
        open_todos = len(todos.list_open()) if todos is not None else 0
        pending = len(self.gateway.approvals.list(status=ApprovalStatus.PENDING))
        kill = self.gateway.kill.snapshot()
        return StatusProjection(
            gateway_online=self.gateway_online,
            paired=self.paired,
            agent_paused=bool(kill.get("pause_agent")),
            spend_frozen=bool(kill.get("freeze_spending")),
            self_mod_frozen=bool(kill.get("freeze_self_mod")),
            pending_approvals=pending,
            open_todos=open_todos,
        )

    def pause_agent(self) -> StatusProjection:
        self.gateway.pause_agent()
        return self.get()

    def resume_agent(self) -> StatusProjection:
        self.gateway.resume_agent()
        return self.get()

    def freeze_spending(self) -> StatusProjection:
        self.gateway.freeze_spending()
        return self.get()

    def unfreeze_spending(self) -> StatusProjection:
        self.gateway.unfreeze_spending()
        return self.get()

    def freeze_self_mod(self) -> StatusProjection:
        self.gateway.freeze_self_mod()
        return self.get()

    def unfreeze_self_mod(self) -> StatusProjection:
        self.gateway.unfreeze_self_mod()
        return self.get()

    def cancel_pending(self) -> tuple[StatusProjection, list[str]]:
        cancelled = self.gateway.cancel_pending()
        return self.get(), list(cancelled)

    def snapshot(self) -> dict[str, Any]:
        return self.get().to_dict()
