"""Approval item schema, tier matrix, and status machine.

Product rules: agent-plan/trust-and-safety/approval-matrix.md
Statuses: pending | accepted | denied | expired | executed | failed | cancelled
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from harness.clock import FakeClock


class ApprovalTier(str, Enum):
    AUTO = "auto"
    SOFT_CONFIRM = "soft_confirm"
    HARD_APPROVE = "hard_approve"
    FORBIDDEN = "forbidden"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DENIED = "denied"
    EXPIRED = "expired"
    EXECUTED = "executed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Terminal statuses — no further transitions except failed→(none) after execute attempt.
TERMINAL_STATUSES = frozenset(
    {
        ApprovalStatus.DENIED,
        ApprovalStatus.EXPIRED,
        ApprovalStatus.EXECUTED,
        ApprovalStatus.FAILED,
        ApprovalStatus.CANCELLED,
    }
)

# Hard actions that must never run without status == accepted.
HARD_ACTION_TYPES = frozenset(
    {
        "buy",
        "book",
        "self_mod_apply",
        "policy_change",
    }
)

SOFT_ACTION_TYPES = frozenset(
    {
        "calendar_create",
        "calendar_modify",
        "calendar_cancel",
        "memory_update",
    }
)

AUTO_ACTION_TYPES = frozenset(
    {
        "calendar_read",
        "memory_read",
        "todo_read",
        "todo_add",
        "todo_complete",
        "reminder_create",
        "habit_create",
        "diet_draft",
        "whatsapp_reply",
        "source_read",
    }
)

FORBIDDEN_ACTION_TYPES = frozenset(
    {
        "transfer_money",
        "subscription_change",
        "write_secrets",
        "edit_outside_allowlist",
        "message_third_party",
    }
)

DEFAULT_HARD_EXPIRY = timedelta(hours=4)
DEFAULT_SOFT_EXPIRY = timedelta(hours=24)

# action_type → tier (table-driven; extend with one row)
ACTION_TIER_MATRIX: dict[str, ApprovalTier] = {
    **{a: ApprovalTier.AUTO for a in AUTO_ACTION_TYPES},
    **{a: ApprovalTier.SOFT_CONFIRM for a in SOFT_ACTION_TYPES},
    **{a: ApprovalTier.HARD_APPROVE for a in HARD_ACTION_TYPES},
    **{a: ApprovalTier.FORBIDDEN for a in FORBIDDEN_ACTION_TYPES},
    # Propose patch is soft by default; apply is hard (separate action_type).
    "self_mod_propose": ApprovalTier.SOFT_CONFIRM,
}


def tier_for(action_type: str) -> ApprovalTier:
    if action_type in ACTION_TIER_MATRIX:
        return ACTION_TIER_MATRIX[action_type]
    # Unknown actions fail closed as hard (must Accept) rather than auto.
    return ApprovalTier.HARD_APPROVE


def is_hard_action(action_type: str) -> bool:
    return action_type in HARD_ACTION_TYPES or tier_for(action_type) == ApprovalTier.HARD_APPROVE


def default_expiry_for(tier: ApprovalTier) -> Optional[timedelta]:
    if tier == ApprovalTier.HARD_APPROVE:
        return DEFAULT_HARD_EXPIRY
    if tier == ApprovalTier.SOFT_CONFIRM:
        return DEFAULT_SOFT_EXPIRY
    return None


@dataclass
class ApprovalItem:
    id: str
    action_type: str
    summary: str
    payload: dict[str, Any]
    tier: ApprovalTier
    status: ApprovalStatus
    created_at: datetime
    expires_at: Optional[datetime] = None
    estimated_cost: Optional[float] = None
    diff_summary: Optional[str] = None
    files_touched: Optional[list[str]] = None
    rollback_ref: Optional[str] = None
    source_channel: Optional[str] = None
    source_utterance: Optional[str] = None
    subtype: Optional[str] = None  # e. and. "policy-change"
    decided_at: Optional[datetime] = None
    executed_at: Optional[datetime] = None
    error: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["tier"] = self.tier.value
        data["status"] = self.status.value
        for key in ("created_at", "expires_at", "decided_at", "executed_at"):
            val = getattr(self, key)
            data[key] = val.isoformat() if val is not None else None
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApprovalItem":
        def parse_dt(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, datetime):
                return val
            return datetime.fromisoformat(str(val))

        return cls(
            id=data["id"],
            action_type=data["action_type"],
            summary=data["summary"],
            payload=dict(data.get("payload") or {}),
            tier=ApprovalTier(data["tier"]),
            status=ApprovalStatus(data["status"]),
            created_at=parse_dt(data["created_at"]),
            expires_at=parse_dt(data.get("expires_at")),
            estimated_cost=data.get("estimated_cost"),
            diff_summary=data.get("diff_summary"),
            files_touched=data.get("files_touched"),
            rollback_ref=data.get("rollback_ref"),
            source_channel=data.get("source_channel"),
            source_utterance=data.get("source_utterance"),
            subtype=data.get("subtype"),
            decided_at=parse_dt(data.get("decided_at")),
            executed_at=parse_dt(data.get("executed_at")),
            error=data.get("error"),
            meta=dict(data.get("meta") or {}),
        )


class ApprovalError(Exception):
    """Raised when an illegal approval transition or execute is attempted."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ApprovalStore:
    """Approval items with status machine + optional disk durability."""

    def __init__(
        self,
        clock: FakeClock,
        *,
        persist_path: Path | str | None = None,
    ) -> None:
        self.clock = clock
        self._persist_path = Path(persist_path) if persist_path is not None else None
        self._items: dict[str, ApprovalItem] = {}
        if self._persist_path is not None and self._persist_path.exists():
            self._load_from_disk()

    @classmethod
    def open(cls, path: Path | str, clock: FakeClock) -> "ApprovalStore":
        """Re-open a durable store from disk (harness Gateway restart)."""
        return cls(clock, persist_path=path)

    def get(self, approval_id: str) -> Optional[ApprovalItem]:
        self.expire_due()
        return self._items.get(approval_id)

    def list(
        self,
        *,
        status: Optional[ApprovalStatus] = None,
    ) -> list[ApprovalItem]:
        self.expire_due()
        items = list(self._items.values())
        if status is not None:
            items = [i for i in items if i.status == status]
        return items

    def create(
        self,
        action_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        *,
        estimated_cost: float | None = None,
        diff_summary: str | None = None,
        files_touched: list[str] | None = None,
        rollback_ref: str | None = None,
        source_channel: str | None = None,
        source_utterance: str | None = None,
        subtype: str | None = None,
        expires_in: timedelta | None = None,
        approval_id: str | None = None,
    ) -> ApprovalItem:
        tier = tier_for(action_type)
        if tier == ApprovalTier.FORBIDDEN:
            raise ApprovalError(
                "forbidden",
                f"action_type={action_type!r} is Forbidden — refuse without redesign",
            )
        if tier == ApprovalTier.AUTO:
            raise ApprovalError(
                "auto_no_approval",
                f"action_type={action_type!r} is Auto — execute without approval item",
            )

        now = self.clock.now()
        ttl = expires_in if expires_in is not None else default_expiry_for(tier)
        expires_at = (now + ttl) if ttl is not None else None

        # Policy-change subtype for policy_change actions.
        if action_type == "policy_change" and subtype is None:
            subtype = "policy-change"

        item = ApprovalItem(
            id=approval_id or str(uuid4()),
            action_type=action_type,
            summary=summary,
            payload=dict(payload or {}),
            tier=tier,
            status=ApprovalStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
            estimated_cost=estimated_cost,
            diff_summary=diff_summary,
            files_touched=list(files_touched) if files_touched else None,
            rollback_ref=rollback_ref,
            source_channel=source_channel,
            source_utterance=source_utterance,
            subtype=subtype,
        )
        self._items[item.id] = item
        self._maybe_persist()
        return item

    def accept(self, approval_id: str) -> ApprovalItem:
        item = self._require(approval_id)
        self.expire_due()
        item = self._items[approval_id]
        if item.status == ApprovalStatus.EXPIRED:
            raise ApprovalError("expired", f"approval {approval_id} already expired")
        if item.status != ApprovalStatus.PENDING:
            raise ApprovalError(
                "invalid_transition",
                f"cannot accept from status={item.status.value}",
            )
        item.status = ApprovalStatus.ACCEPTED
        item.decided_at = self.clock.now()
        self._maybe_persist()
        return item

    def deny(self, approval_id: str) -> ApprovalItem:
        item = self._require(approval_id)
        self.expire_due()
        item = self._items[approval_id]
        if item.status != ApprovalStatus.PENDING:
            raise ApprovalError(
                "invalid_transition",
                f"cannot deny from status={item.status.value}",
            )
        item.status = ApprovalStatus.DENIED
        item.decided_at = self.clock.now()
        self._maybe_persist()
        return item

    def edit(
        self,
        approval_id: str,
        *,
        summary: str | None = None,
        payload: dict[str, Any] | None = None,
        payload_patch: dict[str, Any] | None = None,
        estimated_cost: float | None = None,
    ) -> ApprovalItem:
        """Edit pending approval details (Android Edit) before Accept/Deny.

        ``payload`` replaces the whole payload; ``payload_patch`` merges into it.
        Only pending items may be edited — denied/expired/executed stay terminal.
        """
        self.expire_due()
        item = self._require(approval_id)
        if item.status != ApprovalStatus.PENDING:
            raise ApprovalError(
                "invalid_transition",
                f"cannot edit from status={item.status.value}",
            )
        if summary is not None:
            item.summary = summary
        if payload is not None:
            item.payload = dict(payload)
        if payload_patch is not None:
            merged = dict(item.payload)
            merged.update(payload_patch)
            item.payload = merged
        if estimated_cost is not None:
            item.estimated_cost = estimated_cost
        self._maybe_persist()
        return item

    def mark_executed(self, approval_id: str) -> ApprovalItem:
        item = self._require(approval_id)
        if item.status != ApprovalStatus.ACCEPTED:
            raise ApprovalError(
                "not_accepted",
                f"cannot mark executed: status={item.status.value} (need accepted)",
            )
        item.status = ApprovalStatus.EXECUTED
        item.executed_at = self.clock.now()
        self._maybe_persist()
        return item

    def mark_failed(self, approval_id: str, error: str) -> ApprovalItem:
        item = self._require(approval_id)
        if item.status not in {ApprovalStatus.ACCEPTED, ApprovalStatus.PENDING}:
            raise ApprovalError(
                "invalid_transition",
                f"cannot mark failed from status={item.status.value}",
            )
        item.status = ApprovalStatus.FAILED
        item.error = error
        item.executed_at = self.clock.now()
        self._maybe_persist()
        return item

    def cancel_pending(self) -> list[ApprovalItem]:
        """Kill switch: flip all pending → cancelled. Returns cancelled items."""
        self.expire_due()
        cancelled: list[ApprovalItem] = []
        now = self.clock.now()
        for item in self._items.values():
            if item.status == ApprovalStatus.PENDING:
                item.status = ApprovalStatus.CANCELLED
                item.decided_at = now
                cancelled.append(item)
        if cancelled:
            self._maybe_persist()
        return cancelled

    def expire_due(self) -> list[ApprovalItem]:
        """Advance status pending→expired when clock.now() >= expires_at."""
        now = self.clock.now()
        expired: list[ApprovalItem] = []
        for item in self._items.values():
            if (
                item.status == ApprovalStatus.PENDING
                and item.expires_at is not None
                and now >= item.expires_at
            ):
                item.status = ApprovalStatus.EXPIRED
                item.decided_at = now
                expired.append(item)
        if expired:
            self._maybe_persist()
        return expired

    def can_execute(self, approval_id: str) -> tuple[bool, str]:
        """Return (ok, reason). Only accepted (non-expired) approvals may execute."""
        self.expire_due()
        item = self._items.get(approval_id)
        if item is None:
            return False, "not_found"
        if item.status == ApprovalStatus.ACCEPTED:
            return True, "accepted"
        return False, f"status={item.status.value}"

    def _require(self, approval_id: str) -> ApprovalItem:
        item = self._items.get(approval_id)
        if item is None:
            raise ApprovalError("not_found", f"approval {approval_id} not found")
        return item

    def snapshot(self) -> list[dict[str, Any]]:
        self.expire_due()
        return [i.to_dict() for i in self._items.values()]

    @property
    def persist_path(self) -> Path | None:
        return self._persist_path

    def _load_from_disk(self) -> None:
        if self._persist_path is None:
            return
        raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
        self._items.clear()
        for item_data in raw.get("items", []):
            item = ApprovalItem.from_dict(item_data)
            self._items[item.id] = item

    def _maybe_persist(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "items": [i.to_dict() for i in self._items.values()],
        }
        tmp = self._persist_path.with_suffix(self._persist_path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(self._persist_path)
