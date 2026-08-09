"""Booking task store — user-facing status for INV-BOOK-002."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4


class BookingStatus(str, Enum):
    PROPOSED = "proposed"
    PENDING_APPROVAL = "pending_approval"
    BOOKED = "booked"
    FAILED = "failed"
    DENIED = "denied"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


# User-facing "success" statuses — failed path must never land here.
SUCCESS_STATUSES = frozenset({BookingStatus.BOOKED})


@dataclass
class BookingTask:
    id: str
    shop: str
    service: str
    status: BookingStatus
    options: list[dict[str, Any]] = field(default_factory=list)
    chosen_slot_index: int = 0
    approval_id: Optional[str] = None
    booking_id: Optional[str] = None
    calendar_event_id: Optional[str] = None
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
            "shop": self.shop,
            "service": self.service,
            "status": self.status.value,
            "is_success": self.is_success,
            "options": list(self.options),
            "chosen_slot_index": self.chosen_slot_index,
            "approval_id": self.approval_id,
            "booking_id": self.booking_id,
            "calendar_event_id": self.calendar_event_id,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "meta": dict(self.meta),
        }


class BookingStore:
    """Authoritative in-memory booking tasks (user-facing success/fail)."""

    def __init__(self) -> None:
        self.tasks: dict[str, BookingTask] = {}

    def create(
        self,
        *,
        shop: str,
        service: str,
        options: list[dict[str, Any]],
        status: BookingStatus = BookingStatus.PROPOSED,
        chosen_slot_index: int = 0,
        created_at: datetime | None = None,
        meta: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> BookingTask:
        tid = task_id or f"bk-{uuid4().hex[:12]}"
        now = created_at
        task = BookingTask(
            id=tid,
            shop=shop,
            service=service,
            status=status,
            options=list(options),
            chosen_slot_index=chosen_slot_index,
            created_at=now,
            updated_at=now,
            meta=dict(meta or {}),
        )
        self.tasks[tid] = task
        return task

    def get(self, task_id: str) -> Optional[BookingTask]:
        return self.tasks.get(task_id)

    def list_all(self) -> list[BookingTask]:
        return list(self.tasks.values())

    def set_approval(self, task_id: str, approval_id: str, *, at: datetime | None = None) -> BookingTask:
        task = self._require(task_id)
        task.approval_id = approval_id
        task.status = BookingStatus.PENDING_APPROVAL
        task.updated_at = at or task.updated_at
        return task

    def mark_booked(
        self,
        task_id: str,
        *,
        booking_id: str,
        calendar_event_id: str | None = None,
        at: datetime | None = None,
    ) -> BookingTask:
        task = self._require(task_id)
        task.status = BookingStatus.BOOKED
        task.booking_id = booking_id
        task.calendar_event_id = calendar_event_id
        task.error = None
        task.updated_at = at or task.updated_at
        return task

    def mark_failed(
        self,
        task_id: str,
        error: str,
        *,
        at: datetime | None = None,
    ) -> BookingTask:
        """INV-BOOK-002: failed booking never lands in a success status."""
        task = self._require(task_id)
        task.status = BookingStatus.FAILED
        task.error = error
        task.booking_id = None
        task.updated_at = at or task.updated_at
        return task

    def mark_denied(self, task_id: str, *, at: datetime | None = None) -> BookingTask:
        task = self._require(task_id)
        task.status = BookingStatus.DENIED
        task.updated_at = at or task.updated_at
        return task

    def to_dict(self) -> dict[str, Any]:
        return {"tasks": [t.to_dict() for t in self.tasks.values()]}

    def _require(self, task_id: str) -> BookingTask:
        task = self.tasks.get(task_id)
        if task is None:
            raise KeyError(f"unknown booking task: {task_id}")
        return task
