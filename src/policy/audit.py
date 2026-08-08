"""Side-effect audit log — gated successes must reference approval id."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from harness.clock import FakeClock


@dataclass
class AuditRecord:
    id: str
    action_type: str
    ts: str
    approval_id: Optional[str]
    success: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLog:
    """Append-only audit store for harness assertions (INV-AUDIT-*)."""

    def __init__(self, clock: FakeClock | None = None) -> None:
        self.clock = clock
        self.records: list[AuditRecord] = []

    def record(
        self,
        action_type: str,
        *,
        approval_id: str | None,
        success: bool,
        detail: dict[str, Any] | None = None,
        ts: datetime | None = None,
    ) -> AuditRecord:
        when = ts
        if when is None and self.clock is not None:
            when = self.clock.now()
        if when is None:
            when = datetime.now(timezone.utc)
        entry = AuditRecord(
            id=str(uuid4()),
            action_type=action_type,
            ts=when.isoformat(),
            approval_id=approval_id,
            success=success,
            detail=dict(detail or {}),
        )
        self.records.append(entry)
        return entry

    def for_approval(self, approval_id: str) -> list[AuditRecord]:
        return [r for r in self.records if r.approval_id == approval_id]

    def successful_gated(self) -> list[AuditRecord]:
        return [r for r in self.records if r.success and r.approval_id]

    def clear(self) -> None:
        self.records.clear()

    def snapshot(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records]
