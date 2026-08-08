"""Global kill switches for trust and safety.

- pause agent — no proactive work
- freeze spending — shopping execute blocked
- freeze self-mod — source write/apply disabled
- cancel pending — all pending approvals → cancelled (delegates to ApprovalStore)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class KillSwitchState:
    pause_agent: bool = False
    freeze_spending: bool = False
    freeze_self_mod: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class KillSwitches:
    """Mutable kill-switch panel shared by gateway, cron, and skills."""

    def __init__(self) -> None:
        self.state = KillSwitchState()

    def pause(self) -> None:
        self.state.pause_agent = True

    def resume(self) -> None:
        self.state.pause_agent = False

    def freeze_spending(self) -> None:
        self.state.freeze_spending = True

    def unfreeze_spending(self) -> None:
        self.state.freeze_spending = False

    def freeze_self_mod(self) -> None:
        self.state.freeze_self_mod = True

    def unfreeze_self_mod(self) -> None:
        self.state.freeze_self_mod = False

    @property
    def is_paused(self) -> bool:
        return self.state.pause_agent

    @property
    def spending_frozen(self) -> bool:
        return self.state.freeze_spending

    @property
    def self_mod_frozen(self) -> bool:
        return self.state.freeze_self_mod

    def blocks_execute(self, action_type: str) -> tuple[bool, str]:
        """Return (blocked, reason) for execute-time kill checks."""
        if action_type == "buy" and self.state.freeze_spending:
            return True, "freeze_spending"
        if action_type in {"self_mod_apply", "policy_change"} and self.state.freeze_self_mod:
            return True, "freeze_self_mod"
        if self.state.pause_agent and action_type.startswith("proactive_"):
            return True, "pause_agent"
        return False, ""

    def snapshot(self) -> dict[str, Any]:
        return self.state.to_dict()
