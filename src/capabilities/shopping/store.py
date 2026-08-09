"""Shopping purchase task store — proposals, receipts, deny/fail statuses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class PurchaseStatus(str, Enum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    PURCHASED = "purchased"
    FAILED = "failed"
    DENIED = "denied"
    BLOCKED_CAP = "blocked_cap"
    BLOCKED_FREEZE = "blocked_freeze"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


SUCCESS_STATUSES = frozenset({PurchaseStatus.PURCHASED})


@dataclass
class PurchaseTask:
    id: str
    merchant: str
    sku: str
    name: str
    price: float
    currency: str
    status: PurchaseStatus
    options: list[dict[str, Any]] = field(default_factory=list)
    chosen_index: int = 0
    approval_id: Optional[str] = None
    receipt_id: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status in SUCCESS_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "merchant": self.merchant,
            "sku": self.sku,
            "name": self.name,
            "price": self.price,
            "currency": self.currency,
            "status": self.status.value,
            "is_success": self.is_success,
            "options": list(self.options),
            "chosen_index": self.chosen_index,
            "approval_id": self.approval_id,
            "receipt_id": self.receipt_id,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "meta": dict(self.meta),
        }


class PurchaseStore:
    """Authoritative in-memory purchase tasks + receipt index."""

    def __init__(self) -> None:
        self.tasks: dict[str, PurchaseTask] = {}
        self.receipts: list[dict[str, Any]] = []

    def create(
        self,
        *,
        merchant: str,
        sku: str,
        name: str,
        price: float,
        currency: str,
        options: list[dict[str, Any]],
        status: PurchaseStatus = PurchaseStatus.PROPOSED,
        chosen_index: int = 0,
        created_at: datetime | None = None,
        meta: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> PurchaseTask:
        tid = task_id or f"buy-{uuid4().hex[:12]}"
        now = created_at
        task = PurchaseTask(
            id=tid,
            merchant=merchant,
            sku=sku,
            name=name,
            price=float(price),
            currency=currency,
            status=status,
            options=list(options),
            chosen_index=chosen_index,
            created_at=now,
            updated_at=now,
            meta=dict(meta or {}),
        )
        self.tasks[tid] = task
        return task

    def get(self, task_id: str) -> Optional[PurchaseTask]:
        return self.tasks.get(task_id)

    def list_all(self) -> list[PurchaseTask]:
        return list(self.tasks.values())

    def set_approval(
        self, task_id: str, approval_id: str, *, at: datetime | None = None
    ) -> PurchaseTask:
        task = self._require(task_id)
        task.approval_id = approval_id
        task.status = PurchaseStatus.PENDING_APPROVAL
        task.updated_at = at or task.updated_at
        return task

    def mark_purchased(
        self,
        task_id: str,
        *,
        receipt_id: str,
        at: datetime | None = None,
        receipt: dict[str, Any] | None = None,
    ) -> PurchaseTask:
        task = self._require(task_id)
        task.status = PurchaseStatus.PURCHASED
        task.receipt_id = receipt_id
        task.error = None
        task.updated_at = at or task.updated_at
        if receipt is not None:
            self.receipts.append(dict(receipt))
        return task

    def mark_failed(
        self,
        task_id: str,
        error: str,
        *,
        at: datetime | None = None,
    ) -> PurchaseTask:
        task = self._require(task_id)
        task.status = PurchaseStatus.FAILED
        task.error = error
        task.receipt_id = None
        task.updated_at = at or task.updated_at
        return task

    def mark_denied(self, task_id: str, *, at: datetime | None = None) -> PurchaseTask:
        task = self._require(task_id)
        task.status = PurchaseStatus.DENIED
        task.updated_at = at or task.updated_at
        return task

    def mark_blocked(
        self,
        task_id: str,
        reason: str,
        *,
        at: datetime | None = None,
    ) -> PurchaseTask:
        task = self._require(task_id)
        if reason == "freeze_spending" or reason.startswith("freeze"):
            task.status = PurchaseStatus.BLOCKED_FREEZE
        elif reason.startswith("spend_cap"):
            task.status = PurchaseStatus.BLOCKED_CAP
        else:
            task.status = PurchaseStatus.FAILED
        task.error = reason
        task.updated_at = at or task.updated_at
        return task

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [t.to_dict() for t in self.tasks.values()],
            "receipts": list(self.receipts),
        }

    def _require(self, task_id: str) -> PurchaseTask:
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(f"unknown purchase task: {task_id}")
        return task
