"""Action gateway — propose / accept / deny / execute with approval gates.

Hard actions (buy, book, self_mod_apply, policy_change) cannot execute unless
approval.status == accepted. Soft calendar writes are likewise gated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

from harness.adapters import (
    StubCalendarAdapter,
    StubCommerceAdapter,
    StubCronEmitter,
    StubSelfModAdapter,
)
from harness.clock import FakeClock
from policy.approvals import (
    HARD_ACTION_TYPES,
    ApprovalError,
    ApprovalStatus,
    ApprovalStore,
    ApprovalTier,
    is_hard_action,
    tier_for,
)
from policy.audit import AuditLog
from policy.kill_switches import KillSwitches


@dataclass
class ExecuteResult:
    ok: bool
    reason: str
    approval_id: Optional[str] = None
    result: Any = None
    audit_id: Optional[str] = None


@dataclass
class ProposeResult:
    ok: bool
    reason: str
    approval_id: Optional[str] = None
    tier: Optional[str] = None
    auto_result: Any = None
    executed: bool = False


@dataclass
class ActionGateway:
    """Single entry for gated side effects used by INV-* contract tests."""

    clock: FakeClock
    approvals_path: Path | str | None = None
    approvals: ApprovalStore = field(init=False)
    kill: KillSwitches = field(default_factory=KillSwitches)
    audit: AuditLog = field(init=False)
    calendar: StubCalendarAdapter = field(default_factory=StubCalendarAdapter)
    commerce: StubCommerceAdapter = field(default_factory=StubCommerceAdapter)
    selfmod: StubSelfModAdapter = field(default_factory=StubSelfModAdapter)
    cron: StubCronEmitter = field(init=False)
    execute_attempts: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.approvals = ApprovalStore(self.clock, persist_path=self.approvals_path)
        self.audit = AuditLog(self.clock)
        self.cron = StubCronEmitter(self.kill)

    # --- Kill switches -------------------------------------------------

    def pause_agent(self) -> None:
        self.kill.pause()

    def resume_agent(self) -> None:
        self.kill.resume()

    def freeze_spending(self) -> None:
        self.kill.freeze_spending()

    def freeze_self_mod(self) -> None:
        self.kill.freeze_self_mod()

    def cancel_pending(self) -> list[str]:
        cancelled = self.approvals.cancel_pending()
        return [c.id for c in cancelled]

    # --- Propose / decide ----------------------------------------------

    def propose(
        self,
        action_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        *,
        expires_in: timedelta | None = None,
        **kwargs: Any,
    ) -> ProposeResult:
        tier = tier_for(action_type)
        if tier == ApprovalTier.FORBIDDEN:
            return ProposeResult(
                ok=False,
                reason="forbidden",
                tier=tier.value,
            )

        if tier == ApprovalTier.AUTO:
            result = self._run_adapter(action_type, payload or {})
            # Auto side effects are not approval-gated; still audit without approval id.
            self.audit.record(
                action_type,
                approval_id=None,
                success=True,
                detail={"tier": "auto", "result": result},
            )
            return ProposeResult(
                ok=True,
                reason="auto_executed",
                tier=tier.value,
                auto_result=result,
                executed=True,
            )

        item = self.approvals.create(
            action_type,
            summary,
            payload,
            expires_in=expires_in,
            **kwargs,
        )
        return ProposeResult(
            ok=True,
            reason="pending_approval",
            approval_id=item.id,
            tier=tier.value,
            executed=False,
        )

    def accept(self, approval_id: str) -> Any:
        return self.approvals.accept(approval_id)

    def deny(self, approval_id: str) -> Any:
        return self.approvals.deny(approval_id)

    # --- Execute (gated) -----------------------------------------------

    def execute(self, approval_id: str) -> ExecuteResult:
        """Execute only when approval.status == accepted (and not kill-blocked)."""
        self.approvals.expire_due()
        item = self.approvals.get(approval_id)
        attempt = {
            "approval_id": approval_id,
            "action_type": item.action_type if item else None,
            "status_before": item.status.value if item else None,
        }
        self.execute_attempts.append(attempt)

        if item is None:
            return ExecuteResult(ok=False, reason="not_found", approval_id=approval_id)

        if item.status != ApprovalStatus.ACCEPTED:
            return ExecuteResult(
                ok=False,
                reason=f"status={item.status.value}",
                approval_id=approval_id,
            )

        blocked, block_reason = self.kill.blocks_execute(item.action_type)
        if blocked:
            return ExecuteResult(
                ok=False,
                reason=block_reason,
                approval_id=approval_id,
            )

        try:
            adapter_result = self._run_adapter(item.action_type, item.payload)
            self.approvals.mark_executed(approval_id)
            audit = self.audit.record(
                item.action_type,
                approval_id=approval_id,
                success=True,
                detail={"result": adapter_result},
            )
            return ExecuteResult(
                ok=True,
                reason="executed",
                approval_id=approval_id,
                result=adapter_result,
                audit_id=audit.id,
            )
        except Exception as exc:  # noqa: BLE001
            self.approvals.mark_failed(approval_id, str(exc))
            self.audit.record(
                item.action_type,
                approval_id=approval_id,
                success=False,
                detail={"error": str(exc)},
            )
            return ExecuteResult(
                ok=False,
                reason=f"failed:{exc}",
                approval_id=approval_id,
            )

    def try_hard_action_without_approval(
        self,
        action_type: str,
        payload: dict[str, Any] | None = None,
    ) -> ExecuteResult:
        """Policy layer: hard actions cannot bypass the approval gate.

        Models/skills that try to call execute adapters directly are blocked.
        """
        if not is_hard_action(action_type) and action_type not in HARD_ACTION_TYPES:
            # Soft/auto may still go through propose; this helper is for hard-path abuse.
            pass
        if is_hard_action(action_type):
            self.execute_attempts.append(
                {
                    "approval_id": None,
                    "action_type": action_type,
                    "status_before": None,
                    "bypass_attempt": True,
                }
            )
            return ExecuteResult(
                ok=False,
                reason="hard_action_requires_accepted_approval",
                approval_id=None,
            )
        # Soft path without approval also blocked at this entry.
        if tier_for(action_type) == ApprovalTier.SOFT_CONFIRM:
            return ExecuteResult(
                ok=False,
                reason="soft_action_requires_accepted_approval",
                approval_id=None,
            )
        return ExecuteResult(ok=False, reason="unsupported", approval_id=None)

    def _run_adapter(self, action_type: str, payload: dict[str, Any]) -> Any:
        if action_type == "buy":
            return self.commerce.buy(payload)
        if action_type == "book":
            return self.commerce.book(payload)
        if action_type == "self_mod_apply":
            return self.selfmod.apply(payload)
        if action_type == "policy_change":
            return self.selfmod.policy_change(payload)
        if action_type == "calendar_create":
            return self.calendar.create(payload)
        if action_type == "calendar_modify":
            return self.calendar.modify(payload.get("id", ""), payload)
        if action_type == "calendar_cancel":
            return self.calendar.cancel(payload.get("id", ""))
        if action_type in {
            "todo_add",
            "reminder_create",
            "habit_create",
            "diet_draft",
            "whatsapp_reply",
            "calendar_read",
            "memory_read",
            "todo_read",
            "source_read",
            "memory_update",
            "self_mod_propose",
        }:
            return {"stub": True, "action_type": action_type, "payload": payload}
        raise ApprovalError("unknown_adapter", f"no adapter for {action_type!r}")
