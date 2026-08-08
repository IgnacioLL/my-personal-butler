"""Minimal WhatsApp-like ingress turn stub for harness contract tests.

Not a Gateway replacement — exercises allowlist + outbound catcher side effects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness.outbound import OutboundMessageCatcher
from policy.ingress import evaluate_ingress


@dataclass
class TurnResult:
    allowed: bool
    reason: str
    tool_calls: list[str] = field(default_factory=list)
    outbound_count: int = 0


class IngressSimulator:
    """Route an inbound DM/group message through allowlist policy into stubs."""

    def __init__(
        self,
        allowlist: list[str],
        catcher: OutboundMessageCatcher,
        *,
        groups_enabled: bool = False,
        broken_allow_all: bool = False,
    ) -> None:
        self.allowlist = list(allowlist)
        self.catcher = catcher
        self.groups_enabled = groups_enabled
        self.broken_allow_all = broken_allow_all
        self.tool_calls: list[str] = []

    def handle(
        self,
        sender: str,
        body: str,
        *,
        is_group: bool = False,
    ) -> TurnResult:
        decision = evaluate_ingress(
            sender,
            self.allowlist,
            is_group=is_group,
            groups_enabled=self.groups_enabled,
            broken_allow_all=self.broken_allow_all,
        )
        if not decision.allowed:
            return TurnResult(
                allowed=False,
                reason=decision.reason,
                tool_calls=[],
                outbound_count=0,
            )

        # Allowlisted path may invoke tools and send outbound (stub).
        self.tool_calls.append("agent.respond")
        self.catcher.send("whatsapp", sender, f"ack:{body}", kind="reply")
        return TurnResult(
            allowed=True,
            reason=decision.reason,
            tool_calls=["agent.respond"],
            outbound_count=1,
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "tool_calls": list(self.tool_calls),
            "outbound": self.catcher.to_list(),
        }
