"""Android approval inbox API double — list pending, Accept, Deny, Edit.

Same API surface the product Android companion would use. Gateway owns
canonical approval state; Accept executes once after marking accepted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from policy.action_gateway import ActionGateway, ExecuteResult
from policy.approvals import ApprovalItem, ApprovalStatus, ApprovalTier


@dataclass(frozen=True)
class ApprovalProjection:
    """Android-facing approval card shape (v1 inbox)."""

    id: str
    action_type: str
    summary: str
    tier: str
    status: str
    payload: dict[str, Any]
    estimated_cost: Optional[float] = None
    expires_at: Optional[str] = None
    source_channel: Optional[str] = None
    source_utterance: Optional[str] = None
    subtype: Optional[str] = None
    diff_summary: Optional[str] = None
    files_touched: Optional[list[str]] = None
    rollback_ref: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action_type": self.action_type,
            "summary": self.summary,
            "tier": self.tier,
            "status": self.status,
            "payload": dict(self.payload),
            "estimated_cost": self.estimated_cost,
            "expires_at": self.expires_at,
            "source_channel": self.source_channel,
            "source_utterance": self.source_utterance,
            "subtype": self.subtype,
            "diff_summary": self.diff_summary,
            "files_touched": list(self.files_touched) if self.files_touched else None,
            "rollback_ref": self.rollback_ref,
        }


def _project(item: ApprovalItem) -> ApprovalProjection:
    return ApprovalProjection(
        id=item.id,
        action_type=item.action_type,
        summary=item.summary,
        tier=item.tier.value if isinstance(item.tier, ApprovalTier) else str(item.tier),
        status=item.status.value if isinstance(item.status, ApprovalStatus) else str(item.status),
        payload=dict(item.payload),
        estimated_cost=item.estimated_cost,
        expires_at=item.expires_at.isoformat() if item.expires_at else None,
        source_channel=item.source_channel,
        source_utterance=item.source_utterance,
        subtype=item.subtype,
        diff_summary=item.diff_summary,
        files_touched=list(item.files_touched) if item.files_touched else None,
        rollback_ref=item.rollback_ref,
    )


@dataclass
class AcceptResult:
    """Result of Android Accept (accept + execute)."""

    ok: bool
    approval: ApprovalProjection
    execute: Optional[ExecuteResult] = None
    reason: str = ""


class AndroidApprovalInboxApi:
    """API-level Android approval inbox — Accept / Deny / Edit / list pending."""

    def __init__(self, gateway: ActionGateway) -> None:
        self.gateway = gateway

    def list_pending(self) -> list[ApprovalProjection]:
        items = self.gateway.approvals.list(status=ApprovalStatus.PENDING)
        return [_project(i) for i in items]

    def list_all(self) -> list[ApprovalProjection]:
        return [_project(i) for i in self.gateway.approvals.list()]

    def get(self, approval_id: str) -> Optional[ApprovalProjection]:
        item = self.gateway.approvals.get(approval_id)
        return _project(item) if item else None

    def accept(self, approval_id: str) -> AcceptResult:
        """Accept once then execute — same UX as tapping Accept on Android."""
        self.gateway.accept(approval_id)
        executed = self.gateway.execute(approval_id)
        item = self.gateway.approvals.get(approval_id)
        if item is None:
            return AcceptResult(
                ok=False,
                approval=ApprovalProjection(
                    id=approval_id,
                    action_type="",
                    summary="",
                    tier="",
                    status="missing",
                    payload={},
                ),
                execute=executed,
                reason="not_found_after_accept",
            )
        return AcceptResult(
            ok=executed.ok,
            approval=_project(item),
            execute=executed,
            reason=executed.reason if executed else "executed",
        )

    def deny(self, approval_id: str) -> ApprovalProjection:
        """Deny pending approval — never executes adapters."""
        item = self.gateway.deny(approval_id)
        return _project(item)

    def edit(
        self,
        approval_id: str,
        *,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
        payload_patch: dict[str, Any] | None = None,
        estimated_cost: float | None = None,
    ) -> ApprovalProjection:
        """Edit pending details before Accept/Deny."""
        item = self.gateway.edit(
            approval_id,
            summary=summary,
            payload=payload,
            payload_patch=payload_patch,
            estimated_cost=estimated_cost,
        )
        return _project(item)

    def snapshot(self) -> dict[str, Any]:
        pending = self.list_pending()
        return {
            "pending": [p.to_dict() for p in pending],
            "pending_count": len(pending),
            "all": [p.to_dict() for p in self.list_all()],
        }
